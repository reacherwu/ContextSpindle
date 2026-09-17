//! Shared CLI/MCP memory operations. Success is returned only after durable storage succeeds.
use crate::json::JsonValue;
use continuum_core::{ContinuumConfig, ContinuumEngine, RealTextEmbedder, SemanticCausalBridge};
use std::io;

pub const MAX_TEXT_BYTES: usize = 1024 * 1024;
pub const MAX_TOP_K: usize = 10_000;
pub type Result<T> = std::result::Result<T, ApiError>;

#[derive(Debug)]
pub struct ApiError {
    pub code: &'static str,
    pub message: String,
}
impl ApiError {
    pub fn invalid(message: impl Into<String>) -> Self {
        Self { code: "INVALID_INPUT", message: message.into() }
    }
    pub fn json(&self) -> String {
        format!("{{\"schema_version\":1,\"ok\":false,\"error\":{{\"code\":{},\"message\":{}}}}}", quote(self.code), quote(&self.message))
    }
    pub fn exit_code(&self) -> i32 { if self.code == "INVALID_INPUT" { 2 } else { 1 } }
}
impl From<io::Error> for ApiError {
    fn from(error: io::Error) -> Self {
        let code = match error.kind() {
            io::ErrorKind::NotFound => "NOT_FOUND",
            io::ErrorKind::PermissionDenied => "PERMISSION_DENIED",
            io::ErrorKind::InvalidData | io::ErrorKind::UnexpectedEof => "INVALID_STATE",
            io::ErrorKind::InvalidInput => "INVALID_INPUT",
            io::ErrorKind::TimedOut | io::ErrorKind::WouldBlock => "LOCK_TIMEOUT",
            io::ErrorKind::AlreadyExists => "ALREADY_EXISTS",
            _ => "IO_ERROR",
        };
        Self { code, message: error.to_string() }
    }
}
pub fn quote(text: &str) -> String { JsonValue::String(text.to_owned()).to_json_string() }
pub fn validate_text(text: &str) -> Result<()> {
    if text.trim().is_empty() || text.len() > MAX_TEXT_BYTES {
        return Err(ApiError::invalid("text/query must be nonempty and at most 1048576 UTF-8 bytes"));
    }
    Ok(())
}
pub fn validate_path(path: &str) -> Result<()> {
    if path.trim().is_empty() || path.contains('\0') { return Err(ApiError::invalid("snapshot path must be nonempty and contain no NUL")); }
    Ok(())
}
pub fn top_k(value: Option<&str>, default: usize) -> Result<usize> {
    let k = match value { Some(value) => value.parse::<usize>().map_err(|_| ApiError::invalid("top_k must be an integer in 1..=10000"))?, None => default };
    if !(1..=MAX_TOP_K).contains(&k) { return Err(ApiError::invalid("top_k must be an integer in 1..=10000")); }
    Ok(k)
}
pub fn default_config() -> ContinuumConfig {
    ContinuumConfig { embedding_dim: 32, state_dim: 32, hot_capacity: 250, cold_capacity: 500, causal_exempt_threshold: Some(0.25), sim_threshold: 0.65, ..Default::default() }
}
pub fn load(path: &str) -> Result<ContinuumEngine> {
    validate_path(path)?;
    Ok(continuum_core::load_engine(path)?)
}

pub fn ingest(text: &str, path: &str) -> Result<String> {
    validate_text(text)?;
    validate_path(path)?;
    let (id, steps, slots) = continuum_core::mutate_engine_transactional(path, Some(default_config()), |engine| {
        if engine.step_count == u64::MAX { return Err(io::Error::new(io::ErrorKind::InvalidData, "event step counter exhausted")); }
        let id = engine.step_count;
        let embedder = RealTextEmbedder::new(engine.config.embedding_dim, 42);
        engine.step(&embedder.embed(text), id as f64, text);
        Ok((id, engine.step_count, engine.total_slots()))
    })?;
    // Decimal strings preserve u64 identity in clients whose JSON numbers are IEEE doubles.
    Ok(format!("{{\"schema_version\":1,\"ok\":true,\"operation\":\"ingest\",\"snapshot\":{},\"event_id\":\"{id}\",\"step_id\":\"{id}\",\"step_count\":\"{steps}\",\"total_slots\":{slots},\"text\":{}}}", quote(path), quote(text)))
}

pub fn query(query: &str, path: &str, k: usize) -> Result<String> {
    validate_text(query)?;
    top_k(Some(&k.to_string()), k)?;
    let engine = load(path)?;
    let embedder = RealTextEmbedder::new(engine.config.embedding_dim, 42);
    let (vector, _) = SemanticCausalBridge::new().project_query(query, &embedder, 0.50);
    let matches = engine.query(&vector, k);
    let rows: Vec<String> = matches.iter().map(|m| format!("{{\"event_id\":\"{}\",\"step_id\":\"{}\",\"timestamp\":{},\"score\":{},\"text\":{},\"provenance\":{},\"components\":{{\"sim\":{},\"state_compat\":{},\"temporal_compat\":{},\"provenance_compat\":{}}}}}", m.event_id, m.event_id, m.timestamp, m.revision_score, quote(&m.provenance), quote(&m.provenance), m.components.sim, m.components.state_compat, m.components.temporal_compat, m.components.provenance_compat)).collect();
    Ok(format!("{{\"schema_version\":1,\"ok\":true,\"operation\":\"query\",\"snapshot\":{},\"query\":{},\"top_k\":{k},\"matches\":[{}]}}", quote(path), quote(query), rows.join(",")))
}

pub fn inspect(path: &str) -> Result<String> {
    let engine = load(path)?;
    let mut rows = Vec::new();
    for r in &engine.hot_memory.records {
        rows.push((r.event_id, format!("{{\"event_id\":\"{}\",\"step_id\":\"{}\",\"tier\":\"hot\",\"timestamp\":{},\"text\":{}}}", r.event_id, r.event_id, r.timestamp, quote(&r.payload_ref))));
    }
    for r in &engine.cold_memory.records {
        rows.push((r.event_id, format!("{{\"event_id\":\"{}\",\"step_id\":\"{}\",\"tier\":\"cold\",\"timestamp\":{},\"text\":{}}}", r.event_id, r.event_id, r.timestamp, quote(&r.provenance_summary))));
    }
    rows.sort_by_key(|r| r.0);
    Ok(format!("{{\"schema_version\":1,\"ok\":true,\"operation\":\"inspect\",\"snapshot\":{},\"step_count\":\"{}\",\"total_slots\":{},\"hot_slots\":{},\"cold_slots\":{},\"hot_capacity\":{},\"cold_capacity\":{},\"embedding_dim\":{},\"state_dim\":{},\"records\":[{}]}}", quote(path), engine.step_count, engine.total_slots(), engine.hot_memory.len(), engine.cold_memory.len(), engine.config.hot_capacity, engine.config.cold_capacity, engine.config.embedding_dim, engine.config.state_dim, rows.into_iter().map(|r| r.1).collect::<Vec<_>>().join(",")))
}

// Recovery reports deliberately expose the core's integrity limits. Decimal
// step counts follow the existing CLI schema without losing u64 precision.
fn recovery_report(operation: &str, path: &str, info: continuum_core::SnapshotInfo) -> String {
    format!("{{\"schema_version\":1,\"ok\":true,\"operation\":{},\"snapshot\":{},\"format\":{},\"bytes\":{},\"step_count\":\"{}\",\"hot_records\":{},\"cold_records\":{},\"checksum_verified\":{}}}",
        quote(operation), quote(path), quote(info.format), info.bytes, info.step_count,
        info.hot_records, info.cold_records, info.checksum_verified)
}

pub fn check(path: &str) -> Result<String> {
    validate_path(path)?;
    Ok(recovery_report("check", path, continuum_core::check_snapshot(path)?))
}

pub fn backup(path: &str, backup: &str) -> Result<String> {
    validate_path(path)?;
    validate_path(backup)?;
    Ok(recovery_report("backup", backup, continuum_core::backup_engine(path, backup)?))
}

pub fn restore(backup: &str, path: &str, confirmed: bool) -> Result<String> {
    validate_path(backup)?;
    validate_path(path)?;
    // Never infer overwrite permission from a preflight exists() check: the
    // core enforces no-clobber under its lock even if another writer races us.
    Ok(recovery_report("restore", path, continuum_core::restore_engine(backup, path, confirmed)?))
}

pub fn inspect_human(path: &str) -> Result<()> {
    let engine = load(path)?;
    // The local adapter parses these labels/spacing; do not change the human format.
    println!("Continuum Engine Snapshot: '{}'", path);
    println!("  Total Slots Used: {} / {}", engine.total_slots(), engine.config.hot_capacity + engine.config.cold_capacity);
    println!("  Hot Memory:       {} / {}", engine.hot_memory.len(), engine.config.hot_capacity);
    println!("  Cold Memory:      {} / {}", engine.cold_memory.len(), engine.config.cold_capacity);
    println!("  Total Steps:      {}", engine.step_count);
    println!("  Embedding Dim:    {}", engine.config.embedding_dim);
    println!("  State Dim:        {}", engine.config.state_dim);
    println!("  Causal Exempt θ:  {:?}", engine.config.causal_exempt_threshold);
    Ok(())
}
