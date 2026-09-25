//! Durable, append-only task records. This store is deliberately independent of
//! the bounded, evicting Continuum memory snapshot.
use crate::json::{JsonValue as J, parse_json};
use continuum_core::FileLockGuard;
use continuum_core::{ContinuumEngine, RealTextEmbedder, SemanticCausalBridge};
use std::fs::{self, File, OpenOptions};
use std::io::Write;
#[cfg(unix)]
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

static NONCE: AtomicU64 = AtomicU64::new(0);
const MAX_FIELD_BYTES: usize = 64 * 1024;
const MAX_RECORD_BYTES: u64 = 2 * 1024 * 1024;
const CHECKPOINT_INTERVAL: u64 = 256;

#[derive(Clone, Debug)]
pub struct Task {
    pub id: String,
    pub version: u64,
    pub created_ms: u64,
    pub updated_ms: u64,
    pub last_actor: String,
    pub goal: String,
    pub criteria: String,
    pub status: String,
    pub blocker: String,
    pub owner: String,
    pub next: String,
    pub parent: Option<String>,
    pub dependencies: Vec<String>,
    pub decisions: Vec<String>,
    pub evidence: Vec<String>,
    pub notes: Vec<String>,
}

fn string(value: &str) -> J {
    J::String(value.to_owned())
}
fn field(name: &str, value: J) -> (String, J) {
    (name.to_owned(), value)
}
fn strings(values: &[String]) -> J {
    J::Array(values.iter().map(|s| string(s)).collect())
}
fn clipped(value: &str, max_bytes: usize) -> (String, bool) {
    if value.len() <= max_bytes {
        return (value.into(), false);
    }
    let end = value
        .char_indices()
        .take_while(|(i, c)| i + c.len_utf8() <= max_bytes)
        .last()
        .map(|(i, c)| i + c.len_utf8())
        .unwrap_or(0);
    (value[..end].to_string(), true)
}

fn context_line(value: &str) -> String {
    value
        .chars()
        .map(|c| if c.is_control() { ' ' } else { c })
        .collect()
}

impl Task {
    fn apply_stored(&mut self, key: &str, value: &str) -> Result<(), String> {
        match key {
            "goal" => {
                validate_text(value, key, true)?;
                self.goal = value.into();
            }
            "criteria" => {
                validate_text(value, key, false)?;
                self.criteria = value.into();
            }
            "status" => {
                validate_status(value)?;
                self.status = value.into();
            }
            "owner" => {
                validate_text(value, key, false)?;
                self.owner = value.into();
            }
            "blocker" => {
                validate_text(value, key, false)?;
                self.blocker = value.into();
            }
            "next" => {
                validate_text(value, key, false)?;
                self.next = value.into();
            }
            "decision" => {
                validate_text(value, key, true)?;
                self.decisions.push(value.into());
            }
            "note" => {
                validate_text(value, key, true)?;
                self.notes.push(value.into());
            }
            "evidence" => {
                validate_text(value, key, true)?;
                self.evidence.push(value.into());
            }
            "dependency" => {
                validate_id(value)?;
                if !self.dependencies.iter().any(|v| v == value) {
                    self.dependencies.push(value.into());
                }
            }
            _ => return Err(format!("Unknown stored task field: {key}")),
        }
        Ok(())
    }
    pub fn summary_json(&self) -> J {
        let (goal, goal_truncated) = clipped(&self.goal, 160);
        let (next, next_truncated) = clipped(&self.next, 200);
        let (owner, owner_truncated) = clipped(&self.owner, 80);
        J::Object(vec![
            field("id", string(&self.id)),
            field("version", J::Number(self.version as f64)),
            field("goal", string(&goal)),
            field("goal_truncated", J::Bool(goal_truncated)),
            field("status", string(&self.status)),
            field("blocker", string(&clipped(&self.blocker, 160).0)),
            field("owner", string(&owner)),
            field("owner_truncated", J::Bool(owner_truncated)),
            field("next", string(&next)),
            field("next_truncated", J::Bool(next_truncated)),
            field("updated_ms", string(&self.updated_ms.to_string())),
            field("last_actor", string(&self.last_actor)),
        ])
    }
    pub fn json(&self) -> J {
        J::Object(vec![
            field("schema", J::Number(1.0)),
            field("id", string(&self.id)),
            field("version", J::Number(self.version as f64)),
            field("created_ms", string(&self.created_ms.to_string())),
            field("updated_ms", string(&self.updated_ms.to_string())),
            field("last_actor", string(&self.last_actor)),
            field("goal", string(&self.goal)),
            field("criteria", string(&self.criteria)),
            field("status", string(&self.status)),
            field("blocker", string(&self.blocker)),
            field("next", string(&self.next)),
            field("owner", string(&self.owner)),
            field(
                "parent",
                self.parent.as_deref().map(string).unwrap_or(J::Null),
            ),
            field("dependencies", strings(&self.dependencies)),
            field("decisions", strings(&self.decisions)),
            field("evidence", strings(&self.evidence)),
            field("notes", strings(&self.notes)),
        ])
    }

    fn from_json(j: &J) -> Result<Self, String> {
        let get = |key: &str| {
            j.get(key)
                .and_then(J::as_str)
                .map(str::to_owned)
                .ok_or_else(|| format!("Missing or invalid {key}"))
        };
        if j.get("schema").and_then(J::as_u64) != Some(1) {
            return Err("Unsupported task schema".into());
        }
        let list = |key: &str| -> Result<Vec<String>, String> {
            j.get(key)
                .and_then(J::as_array)
                .ok_or_else(|| format!("Missing {key}"))?
                .iter()
                .map(|x| {
                    x.as_str()
                        .map(str::to_owned)
                        .ok_or_else(|| format!("Invalid {key}"))
                })
                .collect()
        };
        let id = get("id")?;
        validate_id(&id)?;
        let status = get("status")?;
        validate_status(&status)?;
        Ok(Self {
            id,
            version: j
                .get("version")
                .and_then(J::as_u64)
                .filter(|n| *n > 0)
                .ok_or("Invalid version")?,
            created_ms: get("created_ms")?
                .parse()
                .map_err(|_| "Invalid created_ms")?,
            updated_ms: get("updated_ms")?
                .parse()
                .map_err(|_| "Invalid updated_ms")?,
            last_actor: j
                .get("last_actor")
                .and_then(J::as_str)
                .unwrap_or("unknown")
                .to_string(),
            goal: get("goal")?,
            criteria: get("criteria")?,
            status,
            blocker: j
                .get("blocker")
                .and_then(J::as_str)
                .unwrap_or("")
                .to_string(),
            next: get("next")?,
            owner: j.get("owner").and_then(J::as_str).unwrap_or("").to_string(),
            parent: match j.get("parent") {
                Some(J::Null) => None,
                Some(J::String(s)) => {
                    validate_id(s)?;
                    Some(s.clone())
                }
                _ => return Err("Invalid parent".into()),
            },
            dependencies: list("dependencies")?,
            decisions: list("decisions")?,
            evidence: match j.get("evidence") {
                Some(_) => list("evidence")?,
                None => Vec::new(),
            },
            notes: list("notes")?,
        })
    }
}

fn now_ms() -> Result<u64, String> {
    Ok(SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|e| e.to_string())?
        .as_millis() as u64)
}
fn actor_identity() -> String {
    let configured = std::env::var("CONTEXTSPINDLE_ACTOR").unwrap_or_default();
    let clean: String = configured
        .chars()
        .filter(|c| !c.is_control())
        .take(128)
        .collect();
    if clean.trim().is_empty() {
        format!("local-pid-{}", std::process::id())
    } else {
        clean
    }
}
fn validate_text(value: &str, name: &str, required: bool) -> Result<(), String> {
    if required && value.trim().is_empty() {
        return Err(format!("{name} cannot be empty"));
    }
    if value.len() > MAX_FIELD_BYTES {
        return Err(format!("{name} exceeds {MAX_FIELD_BYTES} bytes"));
    }
    Ok(())
}
fn validate_id(id: &str) -> Result<(), String> {
    if id.len() < 3
        || id.len() > 80
        || !id.starts_with("t-")
        || !id.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'-')
    {
        return Err("Invalid task ID".into());
    }
    Ok(())
}
fn validate_status(s: &str) -> Result<(), String> {
    if matches!(s, "open" | "active" | "blocked" | "done" | "cancelled") {
        Ok(())
    } else {
        Err("Status must be open, active, blocked, done, or cancelled".into())
    }
}
fn checksum(bytes: &[u8]) -> u64 {
    bytes.iter().fold(0xcbf29ce484222325u64, |h, b| {
        (h ^ (*b as u64)).wrapping_mul(0x100000001b3)
    })
}
fn sync_dir(path: &Path) -> Result<(), String> {
    #[cfg(unix)]
    {
        File::open(path)
            .and_then(|f| f.sync_all())
            .map_err(|e| e.to_string())?;
    }
    Ok(())
}
fn private_dir(path: &Path) -> Result<(), String> {
    if let Ok(meta) = fs::symlink_metadata(path) {
        if meta.file_type().is_symlink() {
            return Err(format!(
                "Refusing symlinked ledger directory: {}",
                path.display()
            ));
        }
    }
    fs::create_dir_all(path).map_err(|e| e.to_string())?;
    if fs::symlink_metadata(path)
        .map_err(|e| e.to_string())?
        .file_type()
        .is_symlink()
    {
        return Err(format!(
            "Refusing symlinked ledger directory: {}",
            path.display()
        ));
    }
    #[cfg(unix)]
    fs::set_permissions(path, fs::Permissions::from_mode(0o700)).map_err(|e| e.to_string())?;
    Ok(())
}
fn private_file_options() -> OpenOptions {
    let mut opts = OpenOptions::new();
    opts.write(true).create_new(true);
    #[cfg(unix)]
    opts.mode(0o600);
    opts
}

#[derive(Clone, Debug)]
pub struct Store {
    pub root: PathBuf,
}

impl Store {
    pub fn at(path: impl AsRef<Path>) -> Self {
        Self {
            root: path.as_ref().join(".contextspindle").join("tasks"),
        }
    }
    pub fn discover() -> Result<Self, String> {
        let cwd = std::env::current_dir().map_err(|e| e.to_string())?;
        for ancestor in cwd.ancestors() {
            let root = ancestor.join(".contextspindle").join("tasks");
            if root.is_dir() {
                let parent = root.parent().ok_or("Invalid ledger path")?;
                if fs::symlink_metadata(parent)
                    .map_err(|e| e.to_string())?
                    .file_type()
                    .is_symlink()
                {
                    return Err(format!(
                        "Refusing symlinked ledger directory: {}",
                        parent.display()
                    ));
                }
                if fs::symlink_metadata(&root)
                    .map_err(|e| e.to_string())?
                    .file_type()
                    .is_symlink()
                {
                    return Err(format!(
                        "Refusing symlinked ledger directory: {}",
                        root.display()
                    ));
                }
                return Ok(Self { root });
            }
        }
        Ok(Self::at(cwd))
    }
    pub fn init(&self) -> Result<(), String> {
        private_dir(self.root.parent().ok_or("Invalid ledger path")?)?;
        private_dir(&self.root)?;
        sync_dir(&self.root)
    }
    fn lock(&self) -> Result<FileLockGuard, String> {
        self.init()?;
        FileLockGuard::acquire(self.root.join("ledger"), Duration::from_secs(10))
            .map_err(|e| e.to_string())
    }
    fn dir(&self, id: &str) -> Result<PathBuf, String> {
        validate_id(id)?;
        let path = self.root.join(id);
        if let Ok(meta) = fs::symlink_metadata(&path) {
            if meta.file_type().is_symlink() {
                return Err(format!("Task directory {id} is a symlink"));
            }
        }
        Ok(path)
    }
    fn version_path(&self, id: &str, version: u64) -> Result<PathBuf, String> {
        Ok(self.dir(id)?.join(format!("{version:020}.json")))
    }
    fn versions(&self, id: &str) -> Result<Vec<u64>, String> {
        let dir = self.dir(id)?;
        if !dir.is_dir() {
            return Err(format!("Task {id} not found"));
        }
        let mut versions = Vec::new();
        for entry in fs::read_dir(dir).map_err(|e| e.to_string())? {
            let entry = entry.map_err(|e| e.to_string())?;
            let name = entry.file_name().to_string_lossy().to_string();
            if let Some(n) = name.strip_suffix(".json") {
                if n.len() == 20 && n.bytes().all(|b| b.is_ascii_digit()) {
                    versions.push(n.parse::<u64>().map_err(|e| e.to_string())?);
                }
            }
        }
        versions.sort_unstable();
        if versions.is_empty() {
            return Err(format!("Task {id} has no committed versions"));
        }
        for (index, version) in versions.iter().enumerate() {
            if *version != index as u64 + 1 {
                return Err(format!("Task {id} has a missing version"));
            }
        }
        Ok(versions)
    }
    fn read_record(&self, id: &str, version: u64) -> Result<J, String> {
        let path = self.version_path(id, version)?;
        if fs::symlink_metadata(&path)
            .map_err(|e| e.to_string())?
            .file_type()
            .is_symlink()
        {
            return Err(format!("Task record is a symlink: {}", path.display()));
        }
        let len = fs::metadata(&path)
            .map_err(|e| format!("{}: {e}", path.display()))?
            .len();
        if len > MAX_RECORD_BYTES {
            return Err(format!("{} exceeds record limit", path.display()));
        }
        let raw = fs::read_to_string(&path).map_err(|e| format!("{}: {e}", path.display()))?;
        let envelope = parse_json(&raw)?;
        let body = envelope
            .get("body")
            .and_then(J::as_str)
            .ok_or("Missing body")?;
        let hash = envelope
            .get("checksum")
            .and_then(J::as_str)
            .ok_or("Missing checksum")?;
        if format!("{:016x}", checksum(body.as_bytes())) != hash {
            return Err(format!("Checksum mismatch in {}", path.display()));
        }
        parse_json(body)
    }
    pub fn load_version(&self, id: &str, version: u64) -> Result<Task, String> {
        if version == 0 {
            return Err("Version must be positive".into());
        }
        let mut current: Option<Task> = None;
        let candidate = version / CHECKPOINT_INTERVAL * CHECKPOINT_INTERVAL;
        let start = if candidate > 0 {
            match self.read_record(id, candidate) {
                Ok(record) if record.get("schema").and_then(J::as_u64) == Some(1) => candidate,
                _ => 1,
            }
        } else {
            1
        };
        for v in start..=version {
            let record = self.read_record(id, v)?;
            match record.get("schema").and_then(J::as_u64) {
                Some(1) => {
                    let task = Task::from_json(&record)?;
                    if task.id != id || task.version != v {
                        return Err(format!("Identity/version mismatch at {id} v{v}"));
                    }
                    current = Some(task);
                }
                Some(2) => {
                    let task = current.as_mut().ok_or("Task delta without base snapshot")?;
                    if record.get("id").and_then(J::as_str) != Some(id)
                        || record.get("version").and_then(J::as_u64) != Some(v)
                    {
                        return Err(format!("Identity/version mismatch at {id} v{v}"));
                    }
                    let timestamp = record
                        .get("updated_ms")
                        .and_then(J::as_str)
                        .ok_or("Missing delta timestamp")?
                        .parse::<u64>()
                        .map_err(|_| "Invalid delta timestamp")?;
                    let changes = record
                        .get("changes")
                        .and_then(J::as_array)
                        .ok_or("Missing delta changes")?;
                    if changes.is_empty() {
                        return Err("Empty task delta".into());
                    }
                    for change in changes {
                        let key = change
                            .get("key")
                            .and_then(J::as_str)
                            .ok_or("Invalid delta key")?;
                        let value = change
                            .get("value")
                            .and_then(J::as_str)
                            .ok_or("Invalid delta value")?;
                        task.apply_stored(key, value)?;
                    }
                    task.version = v;
                    task.updated_ms = timestamp;
                    task.last_actor = record
                        .get("actor")
                        .and_then(J::as_str)
                        .unwrap_or("unknown")
                        .to_string();
                }
                _ => return Err(format!("Unsupported task record schema at {id} v{v}")),
            }
        }
        current.ok_or("Task has no base snapshot".into())
    }
    pub fn load(&self, id: &str) -> Result<Task, String> {
        let versions = self.versions(id)?;
        self.load_version(id, *versions.last().unwrap())
    }
    fn commit_in(&self, version: u64, record: J, dir: &Path) -> Result<(), String> {
        let body = record.to_json_string();
        let envelope = J::Object(vec![
            field(
                "checksum",
                string(&format!("{:016x}", checksum(body.as_bytes()))),
            ),
            field("body", string(&body)),
        ])
        .to_json_string();
        if envelope.len() as u64 > MAX_RECORD_BYTES {
            return Err("Task record exceeds size limit".into());
        }
        let final_path = dir.join(format!("{version:020}.json"));
        if final_path.exists() {
            return Err("Task version already exists".into());
        }
        let temp = dir.join(format!(
            ".pending-{}-{}",
            std::process::id(),
            NONCE.fetch_add(1, Ordering::Relaxed)
        ));
        let result = (|| -> Result<(), String> {
            let mut file = private_file_options()
                .open(&temp)
                .map_err(|e| e.to_string())?;
            file.write_all(envelope.as_bytes())
                .map_err(|e| e.to_string())?;
            file.sync_all().map_err(|e| e.to_string())?;
            fs::rename(&temp, &final_path).map_err(|e| e.to_string())?;
            sync_dir(&dir)?;
            Ok(())
        })();
        if result.is_err() {
            let _ = fs::remove_file(&temp);
        }
        result
    }
    fn commit_delta(&self, task: &Task, changes: &[(&str, &str)]) -> Result<(), String> {
        if task.version % CHECKPOINT_INTERVAL == 0 {
            let snapshot = task.json();
            if snapshot.to_json_string().len() < (MAX_RECORD_BYTES as usize / 2) {
                return self.commit_in(task.version, snapshot, &self.dir(&task.id)?);
            }
        }
        let items = changes
            .iter()
            .map(|(key, value)| {
                J::Object(vec![
                    field("key", string(key)),
                    field("value", string(value)),
                ])
            })
            .collect();
        let record = J::Object(vec![
            field("schema", J::Number(2.0)),
            field("id", string(&task.id)),
            field("version", J::Number(task.version as f64)),
            field("updated_ms", string(&task.updated_ms.to_string())),
            field("actor", string(&task.last_actor)),
            field("changes", J::Array(items)),
        ]);
        self.commit_in(task.version, record, &self.dir(&task.id)?)
    }
    #[cfg(test)]
    pub fn create(&self, goal: &str, criteria: &str, parent: Option<&str>) -> Result<Task, String> {
        self.create_with_key(goal, criteria, parent, None, "")
    }
    pub fn create_with_key(
        &self,
        goal: &str,
        criteria: &str,
        parent: Option<&str>,
        key: Option<&str>,
        owner: &str,
    ) -> Result<Task, String> {
        validate_text(goal, "goal", true)?;
        validate_text(criteria, "criteria", false)?;
        validate_text(owner, "owner", false)?;
        if let Some(key) = key {
            if key.is_empty()
                || key.len() > 60
                || !key.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'-')
            {
                return Err(
                    "idempotency key must be 1..60 ASCII letters, digits, or hyphens".into(),
                );
            }
        }
        let _guard = self.lock()?;
        if let Some(p) = parent {
            self.load(p)?;
        }
        let now = now_ms()?;
        for _ in 0..100 {
            let id = key.map(|k| format!("t-k-{k}")).unwrap_or_else(|| {
                format!(
                    "t-{now:013x}-{:08x}-{:08x}",
                    std::process::id(),
                    NONCE.fetch_add(1, Ordering::Relaxed)
                )
            });
            let dir = self.dir(&id)?;
            if dir.exists() {
                if key.is_some() {
                    let original = self.load_version(&id, 1)?;
                    if original.goal != goal
                        || original.criteria != criteria
                        || original.parent.as_deref() != parent
                        || original.owner != owner
                    {
                        return Err(
                            "Idempotency key already belongs to a different task request".into(),
                        );
                    }
                    return self.load(&id);
                }
                continue;
            }
            let stage = self.root.join(format!(
                ".creating-{}-{}",
                std::process::id(),
                NONCE.fetch_add(1, Ordering::Relaxed)
            ));
            match fs::create_dir(&stage) {
                Ok(()) => {
                    #[cfg(unix)]
                    fs::set_permissions(&stage, fs::Permissions::from_mode(0o700))
                        .map_err(|e| e.to_string())?;
                    let task = Task {
                        id,
                        version: 1,
                        created_ms: now,
                        updated_ms: now,
                        last_actor: actor_identity(),
                        goal: goal.into(),
                        criteria: criteria.into(),
                        status: "open".into(),
                        blocker: String::new(),
                        owner: owner.into(),
                        next: String::new(),
                        parent: parent.map(str::to_owned),
                        dependencies: Vec::new(),
                        decisions: Vec::new(),
                        evidence: Vec::new(),
                        notes: Vec::new(),
                    };
                    let result = (|| -> Result<(), String> {
                        self.commit_in(task.version, task.json(), &stage)?;
                        fs::rename(&stage, &dir).map_err(|e| e.to_string())?;
                        sync_dir(&self.root)
                    })();
                    if result.is_err() {
                        let _ = fs::remove_dir_all(&stage);
                    }
                    result?;
                    return Ok(task);
                }
                Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => continue,
                Err(e) => return Err(e.to_string()),
            }
        }
        Err("Unable to allocate unique task ID".into())
    }
    pub fn update(
        &self,
        id: &str,
        expected: Option<u64>,
        changes: &[(&str, &str)],
    ) -> Result<Task, String> {
        let _guard = self.lock()?;
        let mut task = self.load(id)?;
        if let Some(v) = expected {
            if task.version != v {
                return Err(format!(
                    "Version conflict: expected {v}, current {}",
                    task.version
                ));
            }
        }
        if changes.is_empty() {
            return Err("No changes supplied".into());
        }
        let has_decision = changes.iter().any(|(key, _)| *key == "decision");
        if changes
            .iter()
            .any(|(key, _)| matches!(*key, "goal" | "criteria"))
            && !has_decision
        {
            return Err("Changing goal or completion criteria requires a recorded decision".into());
        }
        if changes
            .iter()
            .any(|(key, value)| *key == "status" && *value == "cancelled")
            && !has_decision
        {
            return Err("Cancelling a task requires a recorded decision".into());
        }
        for (key, value) in changes {
            match *key {
                "goal" => {
                    validate_text(value, key, true)?;
                    task.goal = (*value).into();
                }
                "criteria" => {
                    validate_text(value, key, false)?;
                    task.criteria = (*value).into();
                }
                "status" => {
                    validate_status(value)?;
                    task.status = (*value).into();
                }
                "blocker" => {
                    validate_text(value, key, false)?;
                    task.blocker = (*value).into();
                }
                "owner" => {
                    validate_text(value, key, false)?;
                    task.owner = (*value).into();
                }
                "next" => {
                    validate_text(value, key, false)?;
                    task.next = (*value).into();
                }
                "decision" => {
                    validate_text(value, key, true)?;
                    task.decisions.push((*value).into());
                }
                "note" => {
                    validate_text(value, key, true)?;
                    task.notes.push((*value).into());
                }
                "evidence" => {
                    validate_text(value, key, true)?;
                    task.evidence.push((*value).into());
                }
                "dependency" => {
                    validate_id(value)?;
                    if *value == id {
                        return Err("Task cannot depend on itself".into());
                    }
                    self.load(value)?;
                    if self.depends_on(value, id)? {
                        return Err("Dependency would create a cycle".into());
                    }
                    if !task.dependencies.iter().any(|x| x == value) {
                        task.dependencies.push((*value).into());
                    }
                }
                _ => return Err(format!("Unknown update field: {key}")),
            }
        }
        if task.status == "blocked" && task.blocker.trim().is_empty() {
            return Err("Blocked tasks require an explicit blocker".into());
        }
        if task.status == "done" {
            if !task.blocker.trim().is_empty() {
                return Err("Clear the blocker before marking done".into());
            }
            if task.criteria.trim().is_empty() {
                return Err("Cannot mark a task done without completion criteria".into());
            }
            for dependency in &task.dependencies {
                if self.load(dependency)?.status != "done" {
                    return Err(format!(
                        "Cannot mark done while dependency {dependency} is unfinished"
                    ));
                }
            }
        }
        task.version = task.version.checked_add(1).ok_or("Version overflow")?;
        task.updated_ms = now_ms()?;
        task.last_actor = actor_identity();
        self.commit_delta(&task, changes)?;
        Ok(task)
    }
    fn depends_on(&self, from: &str, target: &str) -> Result<bool, String> {
        let mut pending = vec![from.to_owned()];
        let mut visited = std::collections::HashSet::new();
        while let Some(id) = pending.pop() {
            if id == target {
                return Ok(true);
            }
            if visited.insert(id.clone()) {
                pending.extend(self.load(&id)?.dependencies);
            }
        }
        Ok(false)
    }
    pub fn list(&self) -> Result<Vec<Task>, String> {
        if !self.root.exists() {
            return Ok(Vec::new());
        }
        let mut ids = Vec::new();
        for entry in fs::read_dir(&self.root).map_err(|e| e.to_string())? {
            let entry = entry.map_err(|e| e.to_string())?;
            let kind = entry.file_type().map_err(|e| e.to_string())?;
            let id = entry.file_name().to_string_lossy().to_string();
            if kind.is_symlink() && id.starts_with("t-") {
                return Err(format!("Task directory {id} is a symlink"));
            }
            if kind.is_dir() {
                if id.starts_with(".creating-") || id.starts_with(".restoring-") {
                    continue;
                }
                validate_id(&id)?;
                ids.push(id);
            }
        }
        ids.sort();
        ids.into_iter().map(|id| self.load(&id)).collect()
    }
    pub fn verify(&self) -> Result<usize, String> {
        let tasks = self.list()?;
        for task in &tasks {
            let mut state: Option<Task> = None;
            for version in self.versions(&task.id)? {
                let record = self.read_record(&task.id, version)?;
                if record.get("id").and_then(J::as_str) != Some(task.id.as_str())
                    || record.get("version").and_then(J::as_u64) != Some(version)
                {
                    return Err(format!(
                        "Identity/version mismatch at {} v{}",
                        task.id, version
                    ));
                }
                match record.get("schema").and_then(J::as_u64) {
                    Some(1) => {
                        state = Some(Task::from_json(&record)?);
                    }
                    Some(2) => {
                        let current = state.as_mut().ok_or("Delta without base snapshot")?;
                        let changes = record
                            .get("changes")
                            .and_then(J::as_array)
                            .filter(|x| !x.is_empty())
                            .ok_or("Invalid task delta")?;
                        for change in changes {
                            let key = change
                                .get("key")
                                .and_then(J::as_str)
                                .ok_or("Invalid delta key")?;
                            let value = change
                                .get("value")
                                .and_then(J::as_str)
                                .ok_or("Invalid delta value")?;
                            current.apply_stored(key, value)?;
                        }
                        current.version = version;
                        current.updated_ms = record
                            .get("updated_ms")
                            .and_then(J::as_str)
                            .ok_or("Missing delta timestamp")?
                            .parse::<u64>()
                            .map_err(|_| "Invalid delta timestamp")?;
                        current.last_actor = record
                            .get("actor")
                            .and_then(J::as_str)
                            .unwrap_or("unknown")
                            .to_string();
                    }
                    _ => return Err("Unsupported task record schema".into()),
                }
            }
            let state = state.ok_or("Missing task state")?;
            if state.json() != task.json() {
                return Err(format!("Task replay mismatch: {}", task.id));
            }
        }
        Ok(tasks.len())
    }
    #[cfg(test)]
    pub fn history(&self, id: &str) -> Result<Vec<Task>, String> {
        self.versions(id)?
            .into_iter()
            .map(|v| self.load_version(id, v))
            .collect()
    }
    pub fn backup(&self, destination: impl AsRef<Path>) -> Result<PathBuf, String> {
        let _guard = self.lock()?;
        self.verify()?;
        let destination = destination.as_ref();
        if destination.exists() {
            return Err("Backup destination already exists".into());
        }
        let parent = destination
            .parent()
            .filter(|p| !p.as_os_str().is_empty())
            .unwrap_or(Path::new("."));
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
        let parent = parent.canonicalize().map_err(|e| e.to_string())?;
        let name = destination
            .file_name()
            .ok_or("Invalid backup destination")?;
        let destination = parent.join(name);
        if destination.starts_with(&self.root.canonicalize().map_err(|e| e.to_string())?) {
            return Err("Backup cannot be inside the task ledger".into());
        }
        let stage = parent.join(format!(
            ".contextspindle-backup-{}-{}",
            std::process::id(),
            NONCE.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&stage).map_err(|e| e.to_string())?;
        #[cfg(unix)]
        fs::set_permissions(&stage, fs::Permissions::from_mode(0o700))
            .map_err(|e| e.to_string())?;
        let result = (|| -> Result<(), String> {
            for task in self.list()? {
                let target_dir = stage.join(&task.id);
                fs::create_dir(&target_dir).map_err(|e| e.to_string())?;
                #[cfg(unix)]
                fs::set_permissions(&target_dir, fs::Permissions::from_mode(0o700))
                    .map_err(|e| e.to_string())?;
                for version in self.versions(&task.id)? {
                    let name = format!("{version:020}.json");
                    let source = self.version_path(&task.id, version)?;
                    let target = target_dir.join(name);
                    fs::copy(source, &target).map_err(|e| e.to_string())?;
                    File::open(target)
                        .and_then(|f| f.sync_all())
                        .map_err(|e| e.to_string())?;
                }
                sync_dir(&target_dir)?;
            }
            sync_dir(&stage)?;
            let copy = Store {
                root: stage.clone(),
            };
            copy.verify()?;
            if destination.exists() {
                return Err("Backup destination appeared during copy".into());
            }
            fs::rename(&stage, &destination).map_err(|e| e.to_string())?;
            sync_dir(&parent)?;
            Ok(())
        })();
        if result.is_err() {
            let _ = fs::remove_dir_all(&stage);
        }
        result.map(|_| destination)
    }
    pub fn restore(&self, source_path: impl AsRef<Path>) -> Result<usize, String> {
        let source = Store {
            root: source_path
                .as_ref()
                .canonicalize()
                .map_err(|e| e.to_string())?,
        };
        if source.root
            == self
                .root
                .canonicalize()
                .unwrap_or_else(|_| self.root.clone())
        {
            return Err("Cannot restore a task ledger onto itself".into());
        }
        let source_tasks = source.list()?;
        source.verify()?;
        let _guard = self.lock()?;
        for task in &source_tasks {
            let destination = self.dir(&task.id)?;
            if destination.exists() {
                let dest_versions = self.versions(&task.id)?;
                let source_versions = source.versions(&task.id)?;
                if dest_versions != source_versions {
                    return Err(format!("Conflicting existing task {}", task.id));
                }
                for version in source_versions {
                    let a = fs::read(source.version_path(&task.id, version)?)
                        .map_err(|e| e.to_string())?;
                    let b = fs::read(self.version_path(&task.id, version)?)
                        .map_err(|e| e.to_string())?;
                    if a != b {
                        return Err(format!("Conflicting existing task {}", task.id));
                    }
                }
                continue;
            }
            let stage = self.root.join(format!(
                ".restoring-{}-{}",
                std::process::id(),
                NONCE.fetch_add(1, Ordering::Relaxed)
            ));
            fs::create_dir(&stage).map_err(|e| e.to_string())?;
            #[cfg(unix)]
            fs::set_permissions(&stage, fs::Permissions::from_mode(0o700))
                .map_err(|e| e.to_string())?;
            let result = (|| -> Result<(), String> {
                for version in source.versions(&task.id)? {
                    let target = stage.join(format!("{version:020}.json"));
                    fs::copy(source.version_path(&task.id, version)?, &target)
                        .map_err(|e| e.to_string())?;
                    File::open(&target)
                        .and_then(|f| f.sync_all())
                        .map_err(|e| e.to_string())?;
                }
                sync_dir(&stage)?;
                fs::rename(&stage, &destination).map_err(|e| e.to_string())?;
                sync_dir(&self.root)
            })();
            if result.is_err() {
                let _ = fs::remove_dir_all(&stage);
            }
            result?;
        }
        self.verify()?;
        Ok(source_tasks.len())
    }
    pub fn search(&self, query: &str, limit: usize) -> Result<Vec<Task>, String> {
        validate_text(query, "query", true)?;
        if limit == 0 || limit > 100 {
            return Err("limit must be 1..100".into());
        }
        let needle = query.to_lowercase();
        let mut matches: Vec<(u8, Task)> = self
            .list()?
            .into_iter()
            .filter_map(|task| {
                let goal = task.goal.to_lowercase();
                let criteria = task.criteria.to_lowercase();
                let next = task.next.to_lowercase();
                let score = if goal.contains(&needle) {
                    3
                } else if next.contains(&needle) {
                    2
                } else if criteria.contains(&needle) {
                    1
                } else {
                    0
                };
                if score > 0 { Some((score, task)) } else { None }
            })
            .collect();
        matches.sort_by(|a, b| {
            b.0.cmp(&a.0)
                .then_with(|| b.1.updated_ms.cmp(&a.1.updated_ms))
                .then_with(|| a.1.id.cmp(&b.1.id))
        });
        Ok(matches
            .into_iter()
            .take(limit)
            .map(|(_, task)| task)
            .collect())
    }
    pub fn children(&self, parent: &str) -> Result<Vec<Task>, String> {
        self.load(parent)?;
        let mut children: Vec<Task> = self
            .list()?
            .into_iter()
            .filter(|t| t.parent.as_deref() == Some(parent))
            .collect();
        children.sort_by(|a, b| a.id.cmp(&b.id));
        Ok(children)
    }
    pub fn inbox(&self, limit: usize) -> Result<Vec<Task>, String> {
        if limit == 0 || limit > 100 {
            return Err("limit must be 1..100".into());
        }
        let mut tasks: Vec<Task> = self
            .list()?
            .into_iter()
            .filter(|t| !matches!(t.status.as_str(), "done" | "cancelled"))
            .collect();
        let priority = |s: &str| match s {
            "active" => 0,
            "blocked" => 1,
            _ => 2,
        };
        tasks.sort_by(|a, b| {
            priority(&a.status)
                .cmp(&priority(&b.status))
                .then_with(|| b.updated_ms.cmp(&a.updated_ms))
                .then_with(|| a.id.cmp(&b.id))
        });
        tasks.truncate(limit);
        Ok(tasks)
    }
    pub fn context(&self, id: &str, budget: usize, memory: &[String]) -> Result<String, String> {
        if !(128..=1_000_000).contains(&budget) {
            return Err("budget must be 128..1000000 tokens".into());
        }
        let task = self.load(id)?;
        let mut out = format!(
            "Source: durable task ledger\nMemory hints are non-authoritative.\nTask: {} (v{})\nGoal: {}\nStatus: {}\nOwner: {}\nLast actor: {}\nCriteria: {}\nNext: {}\n",
            task.id,
            task.version,
            context_line(&task.goal),
            task.status,
            context_line(&task.owner),
            context_line(&task.last_actor),
            context_line(&task.criteria),
            context_line(&task.next)
        );
        if !task.blocker.is_empty() {
            out.push_str(&format!("Blocker: {}\n", context_line(&task.blocker)));
        }
        if let Some(parent) = &task.parent {
            out.push_str(&format!("Parent: {parent}\n"));
        }
        if !task.dependencies.is_empty() {
            out.push_str(&format!("Dependencies: {}\n", task.dependencies.join(", ")));
        }
        let mut related = Vec::new();
        if let Some(parent) = &task.parent {
            let ancestor = self.load(parent)?;
            related.push(format!(
                "parent {} [{}]: {}",
                parent,
                ancestor.status,
                context_line(&ancestor.goal)
            ));
        }
        for dependency in &task.dependencies {
            let dep = self.load(dependency)?;
            related.push(format!(
                "dependency {} [{}]: {}",
                dependency,
                dep.status,
                context_line(&dep.goal)
            ));
        }
        match self.children(id) {
            Ok(children) => {
                for child in children {
                    related.push(format!(
                        "child {} [{}]: {}",
                        child.id,
                        child.status,
                        context_line(&child.goal)
                    ));
                }
            }
            Err(e) => out.push_str(&format!("Warning: child index unavailable: {e}\n")),
        }
        const OMISSION_RESERVE: usize = 40;
        if out.len() + OMISSION_RESERVE > budget {
            return Err(format!(
                "budget too small for required task state: need at least {} conservative tokens",
                out.len() + OMISSION_RESERVE
            ));
        }
        let mut omitted = 0usize;
        let mut optional = Vec::new();
        for (index, item) in task.decisions.iter().enumerate().rev() {
            optional.push(format!("Decision {}: {}\n", index + 1, context_line(item)));
        }
        for (index, item) in task.evidence.iter().enumerate().rev() {
            optional.push(format!("Evidence {}: {}\n", index + 1, context_line(item)));
        }
        for (index, item) in related.iter().enumerate() {
            optional.push(format!("Related task {}: {}\n", index + 1, item));
        }
        for (index, item) in memory.iter().enumerate() {
            optional.push(format!(
                "Memory hint {}: {}\n",
                index + 1,
                context_line(item)
            ));
        }
        for (index, item) in task.notes.iter().enumerate().rev() {
            optional.push(format!("Note {}: {}\n", index + 1, context_line(item)));
        }
        for line in optional {
            if out.len() + line.len() + OMISSION_RESERVE <= budget {
                out.push_str(&line);
            } else {
                omitted += 1;
            }
        }
        out.push_str(&format!("Omitted optional items: {omitted}\n"));
        Ok(out)
    }
}

fn memory_hints(task: &Task) -> Result<Vec<String>, String> {
    let snapshot = crate::find_active_state_file();
    if !Path::new(&snapshot).exists() {
        return Ok(Vec::new());
    }
    let engine = ContinuumEngine::load_from_file(&snapshot)
        .map_err(|e| format!("Memory snapshot unreadable: {e}"))?;
    let embedder = RealTextEmbedder::new(engine.config.embedding_dim, 42);
    let query = format!("{} {} {}", task.goal, task.criteria, task.next);
    let (vector, _) = SemanticCausalBridge::new().project_query(&query, &embedder, 0.50);
    Ok(engine
        .query(&vector, 5)
        .into_iter()
        .map(|item| {
            let compact = item.provenance.replace(['\n', '\r'], " ");
            format!(
                "snapshot event {} score {:.3}: {}",
                item.event_id, item.revision_score, compact
            )
        })
        .collect())
}

pub fn run_cli(args: &[String]) -> Result<String, String> {
    let store = Store::discover()?;
    let sub = args.first().map(String::as_str).unwrap_or("help");
    match sub {
        "init" => { store.init()?; Ok(format!("Task ledger initialized: {}", store.root.display())) },
        "create" => {
            let goal = args.get(1).ok_or("Usage: task create <goal> [--criteria TEXT] [--parent ID]")?;
            let mut criteria = ""; let mut parent = None; let mut key = None; let mut owner = "";
            let mut i = 2;
            while i < args.len() { match args[i].as_str() {
                "--criteria" => { i += 1; criteria = args.get(i).ok_or("Missing criteria")?; },
                "--parent" => { i += 1; parent = Some(args.get(i).ok_or("Missing parent ID")?.as_str()); },
                "--idempotency-key" => { i += 1; key = Some(args.get(i).ok_or("Missing idempotency key")?.as_str()); },
                "--owner" => { i += 1; owner = args.get(i).ok_or("Missing owner")?; },
                other => return Err(format!("Unknown argument: {other}")),
            } i += 1; }
            Ok(store.create_with_key(goal, criteria, parent, key, owner)?.json().to_json_string())
        }
        "update" => {
            let id = args.get(1).ok_or("Usage: task update <id> --status|--next|--note|--decision|--goal|--criteria|--dependency VALUE [--expect-version N]")?;
            let mut changes = Vec::new(); let mut expected = None; let mut i = 2;
            while i < args.len() {
                let key = args[i].strip_prefix("--").ok_or("Expected --field")?;
                i += 1; let value = args.get(i).ok_or("Missing field value")?;
                if key == "expect-version" { expected = Some(value.parse().map_err(|_| "Invalid version")?); }
                else { changes.push((key, value.as_str())); }
                i += 1;
            }
            Ok(store.update(id, expected, &changes)?.json().to_json_string())
        }
        "show" => Ok(store.load(args.get(1).ok_or("Missing task ID")?)?.json().to_json_string()),
        "history" => {
            let id = args.get(1).ok_or("Missing task ID")?;
            let versions = store.versions(id)?;
            let total = versions.len();
            let limit = args.get(3).map(|x| x.parse::<usize>().map_err(|_| "Invalid limit")).transpose()?.unwrap_or(20);
            if !(1..=100).contains(&limit) { return Err("limit must be 1..100".into()); }
            let from = args.get(2).map(|x| x.parse::<usize>().map_err(|_| "Invalid start version")).transpose()?
                .unwrap_or_else(|| total.saturating_sub(limit) + 1);
            if from == 0 { return Err("start version must be positive".into()); }
            let end = from.saturating_add(limit).min(total + 1);
            let mut items = Vec::new();
            for version in from..end { items.push(store.load_version(id, version as u64)?.json()); }
            Ok(J::Object(vec![field("total_versions", J::Number(total as f64)), field("from", J::Number(from as f64)),
                field("next_version", if end <= total { J::Number(end as f64) } else { J::Null }),
                field("items", J::Array(items))]).to_json_string())
        },
        "children" => Ok(J::Array(store.children(args.get(1).ok_or("Missing task ID")?)?.iter().map(Task::summary_json).collect()).to_json_string()),
        "list" => {
            let offset = args.get(1).map(|x| x.parse::<usize>().map_err(|_| "Invalid offset")).transpose()?.unwrap_or(0);
            let limit = args.get(2).map(|x| x.parse::<usize>().map_err(|_| "Invalid limit")).transpose()?.unwrap_or(50);
            if !(1..=100).contains(&limit) { return Err("limit must be 1..100".into()); }
            let tasks = store.list()?;
            let total = tasks.len();
            let next = offset.saturating_add(limit);
            let items = tasks.iter().skip(offset).take(limit).map(Task::summary_json).collect();
            Ok(J::Object(vec![field("total", J::Number(total as f64)), field("offset", J::Number(offset as f64)),
                field("next_offset", if next < total { J::Number(next as f64) } else { J::Null }),
                field("items", J::Array(items))]).to_json_string())
        },
        "inbox" => {
            let limit = args.get(1).map(|x| x.parse::<usize>().map_err(|_| "Invalid limit")).transpose()?.unwrap_or(10);
            Ok(J::Array(store.inbox(limit)?.iter().map(Task::summary_json).collect()).to_json_string())
        }
        "search" => {
            let query = args.get(1).ok_or("Missing search query")?;
            let limit = args.get(2).map(|x| x.parse::<usize>().map_err(|_| "Invalid limit")).transpose()?.unwrap_or(10);
            Ok(J::Array(store.search(query, limit)?.iter().map(Task::summary_json).collect()).to_json_string())
        }
        "verify" => Ok(format!("Verified {} tasks and all committed versions", store.verify()?)),
        "backup" => Ok(format!("Verified task backup: {}", store.backup(args.get(1).ok_or("Missing backup destination")?)?.display())),
        "restore" => Ok(format!("Restored and verified {} tasks", store.restore(args.get(1).ok_or("Missing backup path")?)?)),
        "context" => {
            let id = args.get(1).ok_or("Missing task ID")?;
            let budget = args.get(2).map(|x| x.parse::<usize>().map_err(|_| "Invalid budget")).transpose()?.unwrap_or(2048);
            let task = store.load(id)?;
            let hints = match memory_hints(&task) {
                Ok(hints) => hints,
                Err(e) => {
                    eprintln!("Warning: bounded memory unavailable; durable task state remains readable: {e}");
                    vec![format!("bounded memory unavailable: {e}")]
                }
            };
            store.context(id, budget, &hints)
        }
        _ => Err("Usage: task <init|create|update|show|history|children|list|inbox|search|verify|backup|restore|context> ...".into()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_store(tag: &str) -> Store {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        Store::at(std::env::temp_dir().join(format!(
            "contextspindle_{tag}_{}_{}",
            std::process::id(),
            unique
        )))
    }

    #[test]
    fn interrupted_task_survives_unrelated_work_and_restart() {
        let store = temp_store("resume");
        let task = store
            .create("Publish the research report", "Approved and released", None)
            .unwrap();
        store
            .update(
                &task.id,
                Some(1),
                &[
                    ("status", "blocked"),
                    ("blocker", "Legal review pending"),
                    ("next", "Wait for legal review"),
                    ("decision", "Keep the original data"),
                ],
            )
            .unwrap();
        for i in 0..120 {
            store
                .create(&format!("Unrelated task {i}"), "", None)
                .unwrap();
        }
        let reopened = Store {
            root: store.root.clone(),
        };
        let recovered = reopened.load(&task.id).unwrap();
        assert_eq!(recovered.version, 2);
        assert_eq!(recovered.status, "blocked");
        assert_eq!(recovered.next, "Wait for legal review");
        assert_eq!(reopened.verify().unwrap(), 121);
        fs::remove_dir_all(store.root.parent().unwrap()).unwrap();
    }

    #[test]
    fn optimistic_version_and_history_are_lossless() {
        let store = temp_store("history");
        let task = store.create("Ship product", "Tests pass", None).unwrap();
        store
            .update(&task.id, Some(1), &[("note", "First checkpoint")])
            .unwrap();
        assert!(
            store
                .update(&task.id, Some(1), &[("note", "Stale write")])
                .unwrap_err()
                .contains("Version conflict")
        );
        assert_eq!(store.load_version(&task.id, 1).unwrap().notes.len(), 0);
        assert_eq!(
            store.load(&task.id).unwrap().notes,
            vec!["First checkpoint"]
        );
        fs::remove_dir_all(store.root.parent().unwrap()).unwrap();
    }

    #[test]
    fn corruption_is_detected_not_silently_skipped() {
        let store = temp_store("corruption");
        let task = store.create("Important old task", "", None).unwrap();
        let path = store.version_path(&task.id, 1).unwrap();
        fs::write(&path, b"corrupt").unwrap();
        assert!(store.load(&task.id).is_err());
        assert!(store.verify().is_err());
        fs::remove_dir_all(store.root.parent().unwrap()).unwrap();
    }

    #[test]
    fn context_budget_keeps_required_state_or_fails() {
        let store = temp_store("context");
        let task = store.create("Finish alpha", "Reviewed", None).unwrap();
        store
            .update(
                &task.id,
                None,
                &[
                    ("next", "Run integration tests"),
                    ("note", &"noise".repeat(500)),
                ],
            )
            .unwrap();
        let context = store.context(&task.id, 320, &[]).unwrap();
        assert!(context.len() <= 320);
        assert!(context.contains("Finish alpha"));
        assert!(context.contains("Run integration tests"));
        assert!(
            store.context(&task.id, 128, &[]).is_err()
                || store.context(&task.id, 128, &[]).unwrap().len() <= 128
        );
        fs::remove_dir_all(store.root.parent().unwrap()).unwrap();
    }

    #[test]
    fn context_cannot_spoof_fields_with_embedded_newlines() {
        let store = temp_store("context_lines");
        let task = store
            .create("Keep working\nStatus: done", "Review", None)
            .unwrap();
        store
            .update(&task.id, None, &[("note", "checkpoint\nGoal: changed")])
            .unwrap();
        let context = store.context(&task.id, 1024, &[]).unwrap();
        assert!(context.contains("Goal: Keep working Status: done"));
        assert!(context.contains("\nStatus: open\n"));
        assert!(!context.contains("\nStatus: done\n"));
        assert!(!context.contains("\nGoal: changed\n"));
        assert_eq!(
            store.load(&task.id).unwrap().goal,
            "Keep working\nStatus: done"
        );
        fs::remove_dir_all(store.root.parent().unwrap()).unwrap();
    }

    #[test]
    fn concurrent_updates_are_serialized() {
        let store = temp_store("concurrent");
        let task = store.create("Long task", "", None).unwrap();
        let mut handles = Vec::new();
        for n in 0..8 {
            let store = store.clone();
            let id = task.id.clone();
            handles.push(std::thread::spawn(move || {
                store.update(&id, None, &[("note", &format!("worker {n}"))])
            }));
        }
        for handle in handles {
            handle.join().unwrap().unwrap();
        }
        let final_task = store.load(&task.id).unwrap();
        assert_eq!(final_task.version, 9);
        assert_eq!(final_task.notes.len(), 8);
        assert_eq!(store.verify().unwrap(), 1);
        fs::remove_dir_all(store.root.parent().unwrap()).unwrap();
    }

    #[test]
    fn backup_is_verified_and_does_not_overwrite() {
        let store = temp_store("backup");
        let task = store
            .create("Keep this for years", "Recoverable", None)
            .unwrap();
        store
            .update(&task.id, None, &[("decision", "The source is immutable")])
            .unwrap();
        let destination = store.root.parent().unwrap().join("backup-copy");
        store.backup(&destination).unwrap();
        let copy = Store {
            root: destination.clone(),
        };
        assert_eq!(copy.verify().unwrap(), 1);
        assert_eq!(
            copy.load(&task.id).unwrap().decisions,
            vec!["The source is immutable"]
        );
        assert!(store.backup(&destination).is_err());
        let restored = Store::at(store.root.parent().unwrap().join("new-workspace"));
        assert_eq!(restored.restore(&destination).unwrap(), 1);
        assert_eq!(
            restored.load(&task.id).unwrap().decisions,
            vec!["The source is immutable"]
        );
        assert_eq!(restored.restore(&destination).unwrap(), 1);
        fs::remove_dir_all(store.root.parent().unwrap()).unwrap();
    }

    #[test]
    fn old_task_search_finds_goal_after_intervening_work() {
        let store = temp_store("search");
        let old = store
            .create("Renew the lunar archive", "Archive renewed", None)
            .unwrap();
        for i in 0..80 {
            store
                .create(&format!("Other mission {i}"), "", None)
                .unwrap();
        }
        let found = store.search("lunar archive", 10).unwrap();
        assert_eq!(found.len(), 1);
        assert_eq!(found[0].id, old.id);
        fs::remove_dir_all(store.root.parent().unwrap()).unwrap();
    }

    #[test]
    fn context_includes_live_parent_and_dependency_state() {
        let store = temp_store("relations");
        let parent = store.create("Publish the release", "", None).unwrap();
        let dep = store
            .create("Complete the audit", "", Some(&parent.id))
            .unwrap();
        let child = store
            .create("Write release notes", "", Some(&parent.id))
            .unwrap();
        store
            .update(&child.id, None, &[("dependency", &dep.id)])
            .unwrap();
        store
            .update(
                &dep.id,
                None,
                &[("status", "blocked"), ("blocker", "Audit input missing")],
            )
            .unwrap();
        let context = store.context(&child.id, 1024, &[]).unwrap();
        assert!(context.contains("Publish the release"));
        assert!(context.contains("Complete the audit"));
        assert!(context.contains("blocked"));
        assert!(context.len() <= 1024);
        let parent_context = store.context(&parent.id, 1024, &[]).unwrap();
        assert!(parent_context.contains("Write release notes"));
        assert_eq!(store.children(&parent.id).unwrap().len(), 2);
        fs::remove_dir_all(store.root.parent().unwrap()).unwrap();
    }

    #[test]
    fn completion_requires_criteria_and_finished_dependencies() {
        let store = temp_store("completion");
        let dependency = store.create("Finish audit", "Signed audit", None).unwrap();
        let task = store.create("Ship", "Published", None).unwrap();
        store
            .update(&task.id, None, &[("dependency", &dependency.id)])
            .unwrap();
        assert!(store.update(&task.id, None, &[("status", "done")]).is_err());
        store
            .update(&dependency.id, None, &[("status", "done")])
            .unwrap();
        store.update(&task.id, None, &[("status", "done")]).unwrap();
        assert_eq!(store.load(&task.id).unwrap().status, "done");
        let no_criteria = store.create("Unclear", "", None).unwrap();
        assert!(
            store
                .update(&no_criteria.id, None, &[("status", "done")])
                .is_err()
        );
        fs::remove_dir_all(store.root.parent().unwrap()).unwrap();
    }

    #[test]
    fn dependency_cycles_are_rejected() {
        let store = temp_store("cycle");
        let a = store.create("A", "", None).unwrap();
        let b = store.create("B", "", None).unwrap();
        store.update(&a.id, None, &[("dependency", &b.id)]).unwrap();
        assert!(store.update(&b.id, None, &[("dependency", &a.id)]).is_err());
        fs::remove_dir_all(store.root.parent().unwrap()).unwrap();
    }

    #[test]
    fn inbox_prioritizes_active_and_excludes_finished() {
        let store = temp_store("inbox");
        let open = store.create("Open task", "", None).unwrap();
        let active = store.create("Active task", "", None).unwrap();
        let done = store.create("Done task", "Completed", None).unwrap();
        store
            .update(&active.id, None, &[("status", "active")])
            .unwrap();
        store.update(&done.id, None, &[("status", "done")]).unwrap();
        let inbox = store.inbox(10).unwrap();
        assert_eq!(inbox.len(), 2);
        assert_eq!(inbox[0].id, active.id);
        assert_eq!(inbox[1].id, open.id);
        fs::remove_dir_all(store.root.parent().unwrap()).unwrap();
    }

    #[test]
    fn updates_store_compact_deltas_and_keep_full_history() {
        let store = temp_store("delta");
        let task = store
            .create("Long-lived goal", "Evidence accepted", None)
            .unwrap();
        let note = "checkpoint".repeat(1000);
        store.update(&task.id, None, &[("note", &note)]).unwrap();
        store
            .update(&task.id, None, &[("next", "Resume after interruption")])
            .unwrap();
        let first_update_size = fs::metadata(store.version_path(&task.id, 2).unwrap())
            .unwrap()
            .len();
        let second_update_size = fs::metadata(store.version_path(&task.id, 3).unwrap())
            .unwrap()
            .len();
        assert!(second_update_size < first_update_size / 10);
        let history = store.history(&task.id).unwrap();
        assert_eq!(history.len(), 3);
        assert_eq!(history[1].notes, vec![note]);
        assert_eq!(history[2].next, "Resume after interruption");
        assert_eq!(store.verify().unwrap(), 1);
        fs::remove_dir_all(store.root.parent().unwrap()).unwrap();
    }

    #[test]
    fn old_full_snapshot_versions_remain_readable() {
        let store = temp_store("migration");
        let base = store.create("Legacy task", "Done", None).unwrap();
        let mut old = base.clone();
        old.version = 2;
        old.next = "Old full snapshot".into();
        store
            .commit_in(2, old.json(), &store.dir(&base.id).unwrap())
            .unwrap();
        store
            .update(&base.id, None, &[("note", "New delta")])
            .unwrap();
        assert_eq!(
            store.load_version(&base.id, 2).unwrap().next,
            "Old full snapshot"
        );
        assert_eq!(store.load(&base.id).unwrap().notes, vec!["New delta"]);
        fs::remove_dir_all(store.root.parent().unwrap()).unwrap();
    }

    #[test]
    fn periodic_checkpoint_limits_resume_replay() {
        let store = temp_store("checkpoint");
        let task = store
            .create("Multi-year mission", "Complete", None)
            .unwrap();
        for n in 2..=257 {
            store
                .update(&task.id, None, &[("next", &format!("step {n}"))])
                .unwrap();
        }
        let checkpoint = store.read_record(&task.id, 256).unwrap();
        assert_eq!(checkpoint.get("schema").and_then(J::as_u64), Some(1));
        let delta = store.read_record(&task.id, 257).unwrap();
        assert_eq!(delta.get("schema").and_then(J::as_u64), Some(2));
        assert_eq!(store.load(&task.id).unwrap().next, "step 257");
        assert_eq!(store.verify().unwrap(), 1);
        fs::remove_dir_all(store.root.parent().unwrap()).unwrap();
    }

    #[cfg(unix)]
    #[test]
    fn symlinked_task_records_are_rejected() {
        use std::os::unix::fs::symlink;
        let store = temp_store("symlink");
        let task = store.create("Protected task", "", None).unwrap();
        let record = store.version_path(&task.id, 1).unwrap();
        let parked = record.with_extension("parked");
        fs::rename(&record, &parked).unwrap();
        symlink(&parked, &record).unwrap();
        assert!(store.load(&task.id).is_err());
        assert!(store.verify().is_err());
        fs::remove_dir_all(store.root.parent().unwrap()).unwrap();
    }

    #[test]
    fn unrelated_corruption_does_not_hide_current_task_goal() {
        let store = temp_store("isolation");
        let current = store.create("Preserve this goal", "", None).unwrap();
        let broken = store.create("Other task", "", None).unwrap();
        fs::write(store.version_path(&broken.id, 1).unwrap(), b"corrupt").unwrap();
        let context = store.context(&current.id, 1024, &[]).unwrap();
        assert!(context.contains("Preserve this goal"));
        assert!(context.contains("Warning: child index unavailable"));
        fs::remove_dir_all(store.root.parent().unwrap()).unwrap();
    }

    #[test]
    fn context_keeps_highest_ranked_memory_hint_first() {
        let store = temp_store("ranking");
        let task = store.create("Handle mission", "", None).unwrap();
        let hints = vec![
            "TOP-ranked evidence".to_string(),
            "LOW-ranked evidence".repeat(100),
        ];
        let context = store.context(&task.id, 512, &hints).unwrap();
        assert!(context.contains("TOP-ranked evidence"));
        assert!(!context.contains("LOW-ranked evidence"));
        assert!(context.contains("Omitted optional items: 1"));
        fs::remove_dir_all(store.root.parent().unwrap()).unwrap();
    }

    #[test]
    fn goal_revisions_and_cancellation_require_rationale() {
        let store = temp_store("rationale");
        let task = store
            .create("Original goal", "Original done", None)
            .unwrap();
        assert!(
            store
                .update(&task.id, None, &[("goal", "New goal")])
                .is_err()
        );
        store
            .update(
                &task.id,
                None,
                &[("goal", "New goal"), ("decision", "User changed scope")],
            )
            .unwrap();
        assert!(
            store
                .update(&task.id, None, &[("status", "cancelled")])
                .is_err()
        );
        store
            .update(
                &task.id,
                None,
                &[("status", "cancelled"), ("decision", "User cancelled")],
            )
            .unwrap();
        assert_eq!(
            store.load_version(&task.id, 1).unwrap().goal,
            "Original goal"
        );
        assert_eq!(store.load(&task.id).unwrap().status, "cancelled");
        fs::remove_dir_all(store.root.parent().unwrap()).unwrap();
    }

    #[test]
    fn blockers_and_evidence_survive_resume() {
        let store = temp_store("evidence");
        let task = store
            .create("Restore service", "Health check green", None)
            .unwrap();
        assert!(
            store
                .update(&task.id, None, &[("status", "blocked")])
                .is_err()
        );
        store
            .update(
                &task.id,
                None,
                &[
                    ("status", "blocked"),
                    ("blocker", "Waiting on credentials"),
                    ("evidence", "incident://ticket-42"),
                ],
            )
            .unwrap();
        let recovered = Store {
            root: store.root.clone(),
        }
        .load(&task.id)
        .unwrap();
        assert_eq!(recovered.blocker, "Waiting on credentials");
        assert_eq!(recovered.evidence, vec!["incident://ticket-42"]);
        let context = store.context(&task.id, 1024, &[]).unwrap();
        assert!(context.contains("Blocker: Waiting on credentials"));
        assert!(context.contains("Evidence 1: incident://ticket-42"));
        assert!(store.update(&task.id, None, &[("status", "done")]).is_err());
        store
            .update(&task.id, None, &[("blocker", ""), ("status", "done")])
            .unwrap();
        fs::remove_dir_all(store.root.parent().unwrap()).unwrap();
    }

    #[test]
    fn task_summaries_are_bounded_without_corrupting_unicode() {
        let store = temp_store("summary");
        let goal = "长期任务".repeat(100);
        let task = store.create(&goal, "", None).unwrap();
        let summary = task.summary_json();
        assert!(summary.get("goal_truncated").and_then(J::as_bool).unwrap());
        assert!(summary.get("goal").and_then(J::as_str).unwrap().len() <= 160);
        assert_eq!(store.load(&task.id).unwrap().goal, goal);
        fs::remove_dir_all(store.root.parent().unwrap()).unwrap();
    }

    #[test]
    fn idempotent_creation_reuses_task_without_overwriting_it() {
        let store = temp_store("idempotency");
        let first = store
            .create_with_key(
                "Ship feature",
                "Tests pass",
                None,
                Some("request-123"),
                "agent-alpha",
            )
            .unwrap();
        store
            .update(&first.id, None, &[("next", "Continue tomorrow")])
            .unwrap();
        let retry = store
            .create_with_key(
                "Ship feature",
                "Tests pass",
                None,
                Some("request-123"),
                "agent-alpha",
            )
            .unwrap();
        assert_eq!(retry.id, first.id);
        assert_eq!(retry.version, 2);
        assert_eq!(retry.next, "Continue tomorrow");
        assert!(
            store
                .create_with_key(
                    "Different goal",
                    "Tests pass",
                    None,
                    Some("request-123"),
                    "agent-alpha"
                )
                .is_err()
        );
        assert!(
            store
                .create_with_key(
                    "Ship feature",
                    "Tests pass",
                    None,
                    Some("request-123"),
                    "agent-beta"
                )
                .is_err()
        );
        assert_eq!(store.list().unwrap().len(), 1);
        fs::remove_dir_all(store.root.parent().unwrap()).unwrap();
    }
}
