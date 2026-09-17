//! Explicit, single-attempt command wrapper. Recovery is an observation, never a cause.
//! No output, environment, arguments or inferred fixes are ingested into memory.
//! At most one pending and one recovery observation (1 KiB each) are retained per
//! canonical project. They expire after 24 hours, pruned on the next opted-in run.

use std::fs::{self, File, OpenOptions};
use std::io::{self, Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, ExitStatus, Stdio};
use std::time::{SystemTime, UNIX_EPOCH};

const PENDING: &str = "pending_observation.json";
const RECOVERY: &str = "recovery_observation.json";
const MAX_BYTES: u64 = 1024;
const RETENTION_SECS: u64 = 24 * 60 * 60;

#[derive(Clone)]
struct Observation {
    project: String,
    command: String,
    failed_at: u64,
    recovered_at: Option<u64>,
    exit_code: i32,
}

impl Observation {
    fn encode(&self) -> String {
        let kind = if self.recovered_at.is_some() { "recovery_observation" } else { "failure_observation" };
        let recovered = self.recovered_at.map_or("null".into(), |n| n.to_string());
        format!("{{\"version\":1,\"kind\":\"{kind}\",\"project_digest\":\"{}\",\"command_digest\":\"{}\",\"failed_at\":{},\"recovered_at\":{recovered},\"exit_code\":{},\"verified_cause\":false}}\n",
            self.project, self.command, self.failed_at, self.exit_code)
    }

    fn decode(text: &str) -> Option<Self> {
        let json = crate::json::parse_json(text).ok()?;
        let digest = |key| {
            let s = json.get(key)?.as_str()?;
            (s.len() == 64 && s.bytes().all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase()))
                .then(|| s.to_string())
        };
        let observation = Self {
            project: digest("project_digest")?,
            command: digest("command_digest")?,
            failed_at: json.get("failed_at")?.as_u64()?,
            recovered_at: match json.get("recovered_at")? {
                crate::json::JsonValue::Null => None,
                value => Some(value.as_u64()?),
            },
            exit_code: i32::try_from(json.get("exit_code")?.as_i64()?).ok()?,
        };
        // Only our exact, versioned schema is accepted: no legacy text, unknown
        // fields, fractional timestamps, duplicate keys or causal assertions.
        (observation.exit_code != 0 && observation.encode() == text).then_some(observation)
    }

    fn fresh(&self, now: u64) -> bool {
        self.failed_at <= now && now - self.failed_at < RETENTION_SECS
            && self.recovered_at.is_none_or(|t| t >= self.failed_at && t <= now)
    }
}

struct Session {
    directory: PathBuf,
    // Stable advisory-lock inode, kept locked across this single child execution.
    // Concurrent opted-in commands still run, but skip observations rather than
    // guessing execution order or waiting/retrying a command.
    _lock: File,
    project: String,
    command: String,
    prior: Option<Observation>,
}

impl Session {
    fn begin(args: &[String]) -> io::Result<Self> {
        let cwd = std::env::current_dir()?.canonicalize()?;
        let root = cwd.ancestors().find(|p| p.join(".continuum").exists() || p.join(".git").exists())
            .unwrap_or(&cwd);
        let directory = root.join(".continuum");
        fs::create_dir_all(&directory)?;
        if fs::symlink_metadata(&directory)?.file_type().is_symlink() {
            return Err(io::Error::other("observation directory must not be a symlink"));
        }
        let lock_path = directory.join("runner.lock");
        reject_nonregular(&lock_path)?;
        let lock = private_options().read(true).write(true).create(true).open(lock_path)?;
        lock.try_lock().map_err(io::Error::other)?;
        let now = now()?;
        // Do not parse or migrate legacy incidents containing raw user output.
        remove_if_present(&directory.join("pending_incident.json"))?;
        let prior = load_fresh(&directory.join(PENDING), now)?;
        let _ = load_fresh(&directory.join(RECOVERY), now)?;
        let mut project_hash = Sha256::new();
        project_hash.field(b"continuum-project-v1");
        project_hash.field(root.as_os_str().as_encoded_bytes());
        let mut command_hash = Sha256::new();
        command_hash.field(b"continuum-command-v1");
        // Same project does not imply the same execution context: keep cwd and
        // argument boundaries. Environment is intentionally not collected.
        command_hash.field(cwd.as_os_str().as_encoded_bytes());
        for arg in args { command_hash.field(arg.as_bytes()); }
        Ok(Self { directory, _lock: lock, project: project_hash.finish(), command: command_hash.finish(), prior })
    }

    fn record(self, exit_code: i32) -> io::Result<()> {
        let now = now()?;
        if exit_code != 0 {
            let observation = Observation {
                project: self.project, command: self.command, failed_at: now,
                recovered_at: None, exit_code,
            };
            save(&self.directory, PENDING, &observation)?;
        } else if let Some(mut prior) = self.prior
            && prior.fresh(now) && prior.recovered_at.is_none()
                && prior.project == self.project && prior.command == self.command {
                prior.recovered_at = Some(now);
                save(&self.directory, RECOVERY, &prior)?;
                remove_if_present(&self.directory.join(PENDING))?;
                diagnostic("Continuum: recovery observed; cause unverified, no memory ingested.");
            }
        Ok(())
    }
}

fn now() -> io::Result<u64> {
    SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_secs()).map_err(io::Error::other)
}

fn private_options() -> OpenOptions {
    let mut options = OpenOptions::new();
    #[cfg(unix)] {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    options
}

fn reject_nonregular(path: &Path) -> io::Result<()> {
    match fs::symlink_metadata(path) {
        Ok(meta) if meta.file_type().is_file() => Ok(()),
        Ok(_) => Err(io::Error::other("expected regular observation file")),
        Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(()),
        Err(e) => Err(e),
    }
}

fn remove_if_present(path: &Path) -> io::Result<()> {
    match fs::remove_file(path) {
        Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(()),
        result => result,
    }
}

fn load_fresh(path: &Path, now: u64) -> io::Result<Option<Observation>> {
    reject_nonregular(path)?;
    let file = match File::open(path) {
        Ok(file) => file,
        Err(e) if e.kind() == io::ErrorKind::NotFound => return Ok(None),
        Err(e) => return Err(e),
    };
    // The byte cap applies before parsing and allocation, not just when saving.
    let mut bytes = Vec::new();
    file.take(MAX_BYTES + 1).read_to_end(&mut bytes)?;
    let observation = if bytes.len() as u64 <= MAX_BYTES {
        std::str::from_utf8(&bytes).ok().and_then(Observation::decode).filter(|o| o.fresh(now))
    } else { None };
    if observation.is_none() { remove_if_present(path)?; }
    Ok(observation)
}

fn save(directory: &Path, name: &str, observation: &Observation) -> io::Result<()> {
    let text = observation.encode();
    if text.len() as u64 > MAX_BYTES { return Err(io::Error::other("observation exceeds limit")); }
    let temp = directory.join("runner-observation.tmp");
    // Only used while holding runner.lock. A prior interrupted save is discarded.
    remove_if_present(&temp)?;
    let result = (|| {
        let mut file = private_options().write(true).create_new(true).open(&temp)?;
        file.write_all(text.as_bytes())?;
        file.sync_all()?;
        fs::rename(&temp, directory.join(name))?;
        #[cfg(unix)] File::open(directory)?.sync_all()?;
        Ok(())
    })();
    if result.is_err() { let _ = remove_if_present(&temp); }
    result
}

fn diagnostic(message: &str) {
    // Never echo OS errors, paths, command arguments, stored data or child output.
    // A closed diagnostic pipe must not panic and replace the child exit status.
    let _ = writeln!(io::stderr().lock(), "{message}");
}

/// Execute exactly the requested program and arguments once, preserving its exit
/// code (Unix signal termination maps to the conventional 128 + signal). The
/// state-path parameter stays API-compatible but is never opened or ingested.
pub fn run_command(args: &[String], _state_path: &str) -> i32 {
    if args.is_empty() {
        diagnostic("Usage: continuum run <command> [args...]");
        return 1;
    }
    let session = Session::begin(args);
    if session.is_err() { diagnostic("Continuum: observations unavailable; requested command will still run."); }
    // Inherited streams preserve bytes, stdin and terminal behavior without any
    // line buffers, capture threads or output retained in the runner's memory.
    let status = Command::new(&args[0]).args(&args[1..])
        .stdin(Stdio::inherit()).stdout(Stdio::inherit()).stderr(Stdio::inherit()).status();
    let code = match status {
        Ok(status) => exit_code(status),
        Err(e) => {
            diagnostic("Continuum: requested command could not be executed.");
            return if e.kind() == io::ErrorKind::NotFound { 127 } else { 126 };
        }
    };
    if let Ok(session) = session
        && session.record(code).is_err() { diagnostic("Continuum: observation not saved; child exit status preserved."); }
    code
}

fn exit_code(status: ExitStatus) -> i32 {
    if let Some(code) = status.code() { return code; }
    #[cfg(unix)] {
        use std::os::unix::process::ExitStatusExt;
        if let Some(signal) = status.signal() { return 128 + signal; }
    }
    1
}

// SHA-256 identities avoid raw argument/path retention, not secrecy: low-entropy
// commands can still be guessed offline. Digests do not prove cause, identical
// executable contents, or identical environment. Streaming avoids copying args.
struct Sha256 { state: [u32; 8], block: [u8; 64], used: usize, bytes: u64 }
impl Sha256 {
    fn new() -> Self {
        Self { state: [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19], block: [0; 64], used: 0, bytes: 0 }
    }
    fn field(&mut self, bytes: &[u8]) {
        self.update(&(bytes.len() as u64).to_be_bytes());
        self.update(bytes);
    }
    fn update(&mut self, mut bytes: &[u8]) {
        self.bytes = self.bytes.wrapping_add(bytes.len() as u64);
        while !bytes.is_empty() {
            let n = (64 - self.used).min(bytes.len());
            self.block[self.used..self.used + n].copy_from_slice(&bytes[..n]);
            self.used += n;
            bytes = &bytes[n..];
            if self.used == 64 { self.compress(); self.used = 0; }
        }
    }
    fn finish(mut self) -> String {
        let bits = self.bytes.wrapping_mul(8);
        self.update(&[0x80]);
        while self.used != 56 { self.update(&[0]); }
        self.update(&bits.to_be_bytes());
        self.state.iter().map(|word| format!("{word:08x}")).collect()
    }
    fn compress(&mut self) {
        const K: [u32; 64] = [
            0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
            0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
            0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
            0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
            0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
            0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
            0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
            0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2,
        ];
        let mut w = [0u32; 64];
        for (i, chunk) in self.block.chunks_exact(4).enumerate() {
            w[i] = u32::from_be_bytes(chunk.try_into().unwrap());
        }
        for i in 16..64 {
            let s0 = w[i-15].rotate_right(7) ^ w[i-15].rotate_right(18) ^ (w[i-15] >> 3);
            let s1 = w[i-2].rotate_right(17) ^ w[i-2].rotate_right(19) ^ (w[i-2] >> 10);
            w[i] = w[i-16].wrapping_add(s0).wrapping_add(w[i-7]).wrapping_add(s1);
        }
        let [mut a, mut b, mut c, mut d, mut e, mut f, mut g, mut h] = self.state;
        for i in 0..64 {
            let s1 = e.rotate_right(6) ^ e.rotate_right(11) ^ e.rotate_right(25);
            let choice = (e & f) ^ (!e & g);
            let t1 = h.wrapping_add(s1).wrapping_add(choice).wrapping_add(K[i]).wrapping_add(w[i]);
            let s0 = a.rotate_right(2) ^ a.rotate_right(13) ^ a.rotate_right(22);
            let t2 = s0.wrapping_add((a & b) ^ (a & c) ^ (b & c));
            h = g; g = f; f = e; e = d.wrapping_add(t1); d = c; c = b; b = a; a = t1.wrapping_add(t2);
        }
        for (state, value) in self.state.iter_mut().zip([a,b,c,d,e,f,g,h]) { *state = state.wrapping_add(value); }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn sha256_standard_vectors() {
        assert_eq!(Sha256::new().finish(), "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
        let mut hash = Sha256::new(); hash.update(b"abc");
        assert_eq!(hash.finish(), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
        let mut hash = Sha256::new(); hash.update(&vec![b'a'; 1_000_000]);
        assert_eq!(hash.finish(), "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0");
    }
}
