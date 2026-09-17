//! Locked, bounded CTNM0001 snapshots. No checksum: structural validation cannot
//! detect every bit flip. Nonserialized runtime tuning is reset on load.
use std::fs::{File, OpenOptions};
use std::io::{self, Read, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;
use crate::{ContinuumConfig, ContinuumEngine, FileLockGuard};
use crate::types::{HotRecord, ColdRecord};

const MAGIC: &[u8; 8] = b"CTNM0001";
/// Maximum serialized snapshot size, including all text and vectors (64 MiB).
pub const MAX_SNAPSHOT_BYTES: usize = 64 * 1024 * 1024;
/// Maximum dimension of an embedding or temporal state.
pub const MAX_DIMENSION: usize = 4096;
/// Maximum capacity of either memory bank.
pub const MAX_CAPACITY: usize = 100_000;
/// Maximum UTF-8 bytes in one persisted payload/provenance string.
pub const MAX_TEXT_BYTES: usize = 1024 * 1024;
static NEXT_TEMP: AtomicU64 = AtomicU64::new(0);
fn invalid(message: &str) -> io::Error { io::Error::new(io::ErrorKind::InvalidData, message) }

pub(crate) fn parent(path: &Path) -> &Path {
    path.parent().filter(|p| !p.as_os_str().is_empty()).unwrap_or(Path::new("."))
}

// RAII handles all ordinary error/unwind paths; SIGKILL can leave a harmless
// unreferenced temp. Never clean up another writer's temp by age.
struct TempPath(PathBuf);
impl Drop for TempPath { fn drop(&mut self) { let _ = std::fs::remove_file(&self.0); } }

/// Publish only after flushing the complete temp file. Directory-sync failure
/// after publication is returned as an error: the new state may already be visible.
pub(crate) fn atomic_write(
    target: &Path, create_only: bool, write: impl FnOnce(&mut File) -> io::Result<()>,
) -> io::Result<()> {
    std::fs::create_dir_all(parent(target))?;
    let dir = File::open(parent(target))?;
    let (temp, mut file) = loop {
        let mut name = std::ffi::OsString::from(".");
        name.push(target.file_name().ok_or_else(|| invalid("Snapshot requires a filename"))?);
        name.push(format!(".tmp.{}.{}", std::process::id(), NEXT_TEMP.fetch_add(1, Ordering::Relaxed)));
        let path = parent(target).join(name);
        let mut options = OpenOptions::new(); options.write(true).create_new(true);
        #[cfg(unix)] { use std::os::unix::fs::OpenOptionsExt; options.mode(0o600); }
        match options.open(&path) {
            Ok(file) => break (TempPath(path), file),
            Err(e) if e.kind() == io::ErrorKind::AlreadyExists => continue,
            Err(e) => return Err(e),
        }
    };
    write(&mut file)?;
    file.sync_all()?;
    drop(file);
    if create_only {
        // Same-directory hard link is an atomic no-clobber publication.
        std::fs::hard_link(&temp.0, target)?;
        std::fs::remove_file(&temp.0)?;
    } else {
        std::fs::rename(&temp.0, target)?;
    }
    dir.sync_all()?;
    Ok(())
}

fn validate_config(c: &ContinuumConfig) -> io::Result<()> {
    if !(1..=MAX_DIMENSION).contains(&c.embedding_dim) || !(1..=MAX_DIMENSION).contains(&c.state_dim)
        || !(1..=MAX_CAPACITY).contains(&c.hot_capacity) || !(1..=MAX_CAPACITY).contains(&c.cold_capacity) {
        return Err(invalid("Dimensions/capacities outside supported snapshot limits"));
    }
    if !(-1.0..=1.0).contains(&c.sim_threshold)
        || c.causal_exempt_threshold.is_some_and(|v| !(-1.0..=1.0).contains(&v))
        || !c.temporal_decay_tau.is_finite() || c.temporal_decay_tau <= 0.0
        || [c.w_sim, c.w_state_compat, c.w_temporal_compat, c.w_provenance_compat].iter().any(|v| !v.is_finite() || *v < 0.0) {
        return Err(invalid("Invalid finite thresholds, decay or weights"));
    }
    Ok(())
}
fn validate_vector(v: &[f32], dim: usize) -> io::Result<()> {
    if v.len() != dim || v.iter().any(|x| !x.is_finite()) { return Err(invalid("Invalid vector dimensions or non-finite values")); }
    Ok(())
}
fn validate_engine(e: &ContinuumEngine) -> io::Result<()> {
    validate_config(&e.config)?;
    validate_vector(e.temporal_core.current_state(), e.config.state_dim)?;
    if e.hot_memory.len() > e.config.hot_capacity || e.cold_memory.len() > e.config.cold_capacity {
        return Err(invalid("Record count exceeds capacity"));
    }
    // Fixed header is <= 101 bytes; each record adds 44 plus vectors/text.
    let mut bytes = 101 + e.config.state_dim * 4;
    let mut ids = std::collections::HashSet::new();
    let records = e.hot_memory.records.iter().map(|r| (r.event_id, r.timestamp, &r.embedding, &r.state_snapshot, r.importance, &r.payload_ref))
        .chain(e.cold_memory.records.iter().map(|r| (r.event_id, r.timestamp, &r.compressed_embedding, &r.state_fingerprint, r.importance_at_eviction, &r.provenance_summary)));
    for (id, timestamp, embedding, state, importance, text) in records {
        validate_vector(embedding, e.config.embedding_dim)?;
        validate_vector(state, e.config.state_dim)?;
        if id >= e.step_count || !ids.insert(id) || !timestamp.is_finite() || !importance.is_finite() || text.len() > MAX_TEXT_BYTES {
            return Err(invalid("Invalid record metadata or text length"));
        }
        bytes += 44 + embedding.len() * 4 + state.len() * 4 + text.len();
        if bytes > MAX_SNAPSHOT_BYTES { return Err(invalid("Snapshot exceeds byte limit")); }
    }
    Ok(())
}

fn write_u64(w: &mut impl Write, v: u64) -> io::Result<()> { w.write_all(&v.to_le_bytes()) }
fn write_f32(w: &mut impl Write, v: f32) -> io::Result<()> { w.write_all(&v.to_le_bytes()) }
fn write_vector(w: &mut impl Write, v: &[f32]) -> io::Result<()> {
    write_u64(w, v.len() as u64)?;
    for &value in v { write_f32(w, value)?; } Ok(())
}
pub(crate) fn save_engine_unlocked(e: &ContinuumEngine, path: impl AsRef<Path>) -> io::Result<()> {
    validate_engine(e)?;
    atomic_write(path.as_ref(), false, |file| {
        let mut w = io::BufWriter::new(file);
        w.write_all(MAGIC)?;
        let c = &e.config;
        for v in [c.embedding_dim, c.state_dim, c.hot_capacity, c.cold_capacity] { write_u64(&mut w, v as u64)?; }
        write_f32(&mut w, c.sim_threshold)?;
        match c.causal_exempt_threshold {
            Some(v) => { w.write_all(&[1])?; write_f32(&mut w, v)?; }
            None => w.write_all(&[0])?,
        }
        for v in [c.temporal_decay_tau, c.w_sim, c.w_state_compat, c.w_temporal_compat, c.w_provenance_compat] { write_f32(&mut w, v)?; }
        write_u64(&mut w, e.step_count)?;
        write_vector(&mut w, e.temporal_core.current_state())?;
        write_u64(&mut w, e.hot_memory.len() as u64)?;
        for r in &e.hot_memory.records {
            write_record(&mut w, r.event_id, r.timestamp, &r.embedding, &r.state_snapshot, r.importance, &r.payload_ref)?;
        }
        write_u64(&mut w, e.cold_memory.len() as u64)?;
        for r in &e.cold_memory.records {
            write_record(&mut w, r.event_id, r.timestamp, &r.compressed_embedding, &r.state_fingerprint, r.importance_at_eviction, &r.provenance_summary)?;
        }
        w.flush()
    })
}
fn write_record(w: &mut impl Write, id: u64, timestamp: f64, embedding: &[f32], state: &[f32], importance: f32, text: &str) -> io::Result<()> {
    write_u64(w, id)?; w.write_all(&timestamp.to_le_bytes())?;
    write_vector(w, embedding)?; write_vector(w, state)?;
    write_f32(w, importance)?; write_u64(w, text.len() as u64)?; w.write_all(text.as_bytes())
}

// Slice reader checks lengths against remaining bytes BEFORE allocating.
struct Decoder<'a>(&'a [u8]);
impl<'a> Decoder<'a> {
    fn take(&mut self, n: usize) -> io::Result<&'a [u8]> {
        if n > self.0.len() { return Err(invalid("Truncated snapshot")); }
        let (value, rest) = self.0.split_at(n); self.0 = rest; Ok(value)
    }
    fn u64(&mut self) -> io::Result<u64> { Ok(u64::from_le_bytes(self.take(8)?.try_into().unwrap())) }
    fn f32(&mut self) -> io::Result<f32> { Ok(f32::from_le_bytes(self.take(4)?.try_into().unwrap())) }
    fn len(&mut self, max: usize) -> io::Result<usize> {
        let n = usize::try_from(self.u64()?).map_err(|_| invalid("Length not representable"))?;
        if n > max { return Err(invalid("Length exceeds supported limit")); } Ok(n)
    }
    fn vector(&mut self, dim: usize) -> io::Result<Vec<f32>> {
        if self.len(dim)? != dim { return Err(invalid("Vector length differs from configured dimension")); }
        let bytes = self.take(dim * 4)?;
        let v: Vec<f32> = bytes.chunks_exact(4).map(|b| f32::from_le_bytes(b.try_into().unwrap())).collect();
        validate_vector(&v, dim)?; Ok(v)
    }
    fn record(&mut self, c: &ContinuumConfig) -> io::Result<HotRecord> {
        let event_id = self.u64()?;
        let timestamp = f64::from_le_bytes(self.take(8)?.try_into().unwrap());
        let embedding = self.vector(c.embedding_dim)?;
        let state_snapshot = self.vector(c.state_dim)?;
        let importance = self.f32()?;
        let n = self.len(MAX_TEXT_BYTES)?;
        let payload_ref = std::str::from_utf8(self.take(n)?).map_err(|_| invalid("Invalid UTF-8 text"))?.to_owned();
        Ok(HotRecord { event_id, timestamp, embedding, state_snapshot, importance, payload_ref })
    }
}
pub(crate) fn read_snapshot_bytes(path: &Path) -> io::Result<Vec<u8>> {
    let file = File::open(path)?;
    if !file.metadata()?.is_file() { return Err(invalid("Snapshot must be a regular file")); }
    if file.metadata()?.len() > MAX_SNAPSHOT_BYTES as u64 { return Err(invalid("Snapshot exceeds byte limit")); }
    let mut bytes = Vec::new();
    file.take(MAX_SNAPSHOT_BYTES as u64 + 1).read_to_end(&mut bytes)?;
    if bytes.len() > MAX_SNAPSHOT_BYTES { return Err(invalid("Snapshot exceeds byte limit")); } Ok(bytes)
}
pub(crate) fn decode(bytes: &[u8]) -> io::Result<ContinuumEngine> {
    if bytes.len() > MAX_SNAPSHOT_BYTES { return Err(invalid("Snapshot exceeds byte limit")); }
    let mut r = Decoder(bytes);
    if r.take(8)? != MAGIC { return Err(invalid("Invalid Continuum checkpoint header")); }
    let embedding_dim = r.len(MAX_DIMENSION)?;
    let state_dim = r.len(MAX_DIMENSION)?;
    let hot_capacity = r.len(MAX_CAPACITY)?;
    let cold_capacity = r.len(MAX_CAPACITY)?;
    let sim_threshold = r.f32()?;
    let causal_exempt_threshold = match r.take(1)?[0] { 0 => None, 1 => Some(r.f32()?), _ => return Err(invalid("Invalid optional threshold flag")) };
    let c = ContinuumConfig { embedding_dim, state_dim, hot_capacity, cold_capacity, sim_threshold, causal_exempt_threshold,
        temporal_decay_tau: r.f32()?, w_sim: r.f32()?, w_state_compat: r.f32()?, w_temporal_compat: r.f32()?, w_provenance_compat: r.f32()? };
    validate_config(&c)?;
    let step_count = r.u64()?;
    let state = r.vector(state_dim)?;
    let mut e = ContinuumEngine::new(c);
    e.step_count = step_count; e.temporal_core.state = state;
    let count = r.len(hot_capacity)?;
    for _ in 0..count { e.hot_memory.records.push(r.record(&e.config)?); }
    let count = r.len(cold_capacity)?;
    for _ in 0..count {
        let h = r.record(&e.config)?;
        e.cold_memory.records.push(ColdRecord { event_id: h.event_id, timestamp: h.timestamp, compressed_embedding: h.embedding,
            state_fingerprint: h.state_snapshot, importance_at_eviction: h.importance, provenance_summary: h.payload_ref });
    }
    if !r.0.is_empty() { return Err(invalid("Unexpected trailing snapshot bytes")); }
    validate_engine(&e)?; Ok(e)
}
pub(crate) fn load_engine_unlocked(path: impl AsRef<Path>) -> io::Result<ContinuumEngine> {
    decode(&read_snapshot_bytes(path.as_ref())?)
}
/// Save under an exclusive lock. For read-modify-write use the transactional API,
/// not separate load/save calls. Stops old-protocol writers before first use.
pub fn save_engine(engine: &ContinuumEngine, path: impl AsRef<Path>) -> io::Result<()> {
    let target = path.as_ref(); std::fs::create_dir_all(parent(target))?;
    let _lock = FileLockGuard::acquire(target, Duration::from_secs(2))?;
    save_engine_unlocked(engine, target)
}
/// Load a validated snapshot under an exclusive advisory lock.
pub fn load_engine(path: impl AsRef<Path>) -> io::Result<ContinuumEngine> {
    let target = path.as_ref();
    let _lock = FileLockGuard::acquire(target, Duration::from_secs(2))?;
    load_engine_unlocked(target)
}
/// Hold the lock over the entire load/mutate/validate/atomic-save transaction.
/// Only NotFound initializes a new state. Closure errors do not commit.
/// Do not call a locking API for this path from inside the closure.
pub fn mutate_engine_transactional<F, R>(path: impl AsRef<Path>, default_config: Option<ContinuumConfig>, f: F) -> io::Result<R>
where F: FnOnce(&mut ContinuumEngine) -> io::Result<R> {
    let target = path.as_ref(); std::fs::create_dir_all(parent(target))?;
    let _lock = FileLockGuard::acquire(target, Duration::from_secs(3))?;
    let mut e = match load_engine_unlocked(target) {
        Ok(e) => e,
        Err(err) if err.kind() == io::ErrorKind::NotFound => {
            let c = default_config.unwrap_or_default(); validate_config(&c)?; ContinuumEngine::new(c)
        }
        Err(err) => return Err(err),
    };
    let result = f(&mut e)?; save_engine_unlocked(&e, target)?; Ok(result)
}
