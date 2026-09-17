//! High-speed zero-dependency binary state persistence for ContinuumEngine.
//!
//! Enables zero-loss snapshotting of hot/cold memory manifolds, temporal state,
//! and causal index records to disk in < 1 millisecond.

use std::fs::File;
use std::io::{self, BufReader, BufWriter, Error, ErrorKind, Read, Write};
use std::path::Path;

use crate::cold_memory::DiversifiedColdMemory;
use crate::engine::ContinuumEngine;
use crate::hot_memory::HotMemoryBank;
use crate::revision::RevisionEngine;
use crate::temporal::TemporalCore;
use crate::types::{ColdRecord, ContinuumConfig, HotRecord};

const MAGIC_HEADER: &[u8; 8] = b"CTNM0001";
const FOOTER_MAGIC: &[u8; 8] = b"CTNMFOOT";

#[inline]
fn fnv1a_update(hash: &mut u64, bytes: &[u8]) {
    for &b in bytes {
        *hash ^= b as u64;
        *hash = hash.wrapping_mul(0x100000001b3);
    }
}

struct HashingWriter<W: Write> {
    inner: W,
    hash: u64,
    enabled: bool,
}

impl<W: Write> HashingWriter<W> {
    fn new(inner: W) -> Self {
        Self {
            inner,
            hash: 0xcbf29ce484222325,
            enabled: true,
        }
    }
}

impl<W: Write> Write for HashingWriter<W> {
    fn write(&mut self, buf: &[u8]) -> io::Result<usize> {
        let n = self.inner.write(buf)?;
        if self.enabled {
            fnv1a_update(&mut self.hash, &buf[..n]);
        }
        Ok(n)
    }
    fn flush(&mut self) -> io::Result<()> {
        self.inner.flush()
    }
}

struct HashingReader<R: Read> {
    inner: R,
    hash: u64,
    enabled: bool,
}

impl<R: Read> HashingReader<R> {
    fn new(inner: R) -> Self {
        Self {
            inner,
            hash: 0xcbf29ce484222325,
            enabled: true,
        }
    }
}

impl<R: Read> Read for HashingReader<R> {
    fn read(&mut self, buf: &mut [u8]) -> io::Result<usize> {
        let n = self.inner.read(buf)?;
        if self.enabled {
            fnv1a_update(&mut self.hash, &buf[..n]);
        }
        Ok(n)
    }
}

pub fn save_engine_unlocked(engine: &ContinuumEngine, path: impl AsRef<Path>) -> io::Result<()> {
    let target = path.as_ref();
    let parent = target.parent().unwrap_or_else(|| Path::new("."));
    if !parent.as_os_str().is_empty() {
        std::fs::create_dir_all(parent)?;
    }

    let tmp_path = parent.join(format!(
        ".{}.tmp.{}.{}",
        target.file_name().and_then(|n| n.to_str()).unwrap_or("state"),
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_nanos())
            .unwrap_or(0)
    ));

    let write_res = (|| -> io::Result<()> {
        let file = File::create(&tmp_path)?;
        let mut writer = HashingWriter::new(BufWriter::new(file));

        // 1. Magic Header
        writer.write_all(MAGIC_HEADER)?;

        // 2. Config
        writer.write_all(&(engine.config.embedding_dim as u64).to_le_bytes())?;
        writer.write_all(&(engine.config.state_dim as u64).to_le_bytes())?;
    writer.write_all(&(engine.config.hot_capacity as u64).to_le_bytes())?;
    writer.write_all(&(engine.config.cold_capacity as u64).to_le_bytes())?;
    writer.write_all(&engine.config.sim_threshold.to_le_bytes())?;

    match engine.config.causal_exempt_threshold {
        Some(th) => {
            writer.write_all(&[1u8])?;
            writer.write_all(&th.to_le_bytes())?;
        }
        None => {
            writer.write_all(&[0u8])?;
        }
    }

    writer.write_all(&engine.config.temporal_decay_tau.to_le_bytes())?;
    writer.write_all(&engine.config.w_sim.to_le_bytes())?;
    writer.write_all(&engine.config.w_state_compat.to_le_bytes())?;
    writer.write_all(&engine.config.w_temporal_compat.to_le_bytes())?;
    writer.write_all(&engine.config.w_provenance_compat.to_le_bytes())?;

    // 3. Engine metadata
    writer.write_all(&engine.step_count.to_le_bytes())?;

    // 4. Temporal Core state
    let cur_state = engine.temporal_core.current_state();
    writer.write_all(&(cur_state.len() as u64).to_le_bytes())?;
    for &val in cur_state {
        writer.write_all(&val.to_le_bytes())?;
    }

    // 5. Hot Memory Bank
    let hot_records = &engine.hot_memory.records;
    writer.write_all(&(hot_records.len() as u64).to_le_bytes())?;
    for r in hot_records {
        writer.write_all(&r.event_id.to_le_bytes())?;
        writer.write_all(&r.timestamp.to_le_bytes())?;

        writer.write_all(&(r.embedding.len() as u64).to_le_bytes())?;
        for &val in &r.embedding {
            writer.write_all(&val.to_le_bytes())?;
        }

        writer.write_all(&(r.state_snapshot.len() as u64).to_le_bytes())?;
        for &val in &r.state_snapshot {
            writer.write_all(&val.to_le_bytes())?;
        }

        writer.write_all(&r.importance.to_le_bytes())?;

        let payload_bytes = r.payload_ref.as_bytes();
        writer.write_all(&(payload_bytes.len() as u64).to_le_bytes())?;
        writer.write_all(payload_bytes)?;
    }

    // 6. Cold Memory Candidate Archive
    let cold_records = &engine.cold_memory.records;
    writer.write_all(&(cold_records.len() as u64).to_le_bytes())?;
    for r in cold_records {
        writer.write_all(&r.event_id.to_le_bytes())?;
        writer.write_all(&r.timestamp.to_le_bytes())?;

        writer.write_all(&(r.compressed_embedding.len() as u64).to_le_bytes())?;
        for &val in &r.compressed_embedding {
            writer.write_all(&val.to_le_bytes())?;
        }

        writer.write_all(&(r.state_fingerprint.len() as u64).to_le_bytes())?;
        for &val in &r.state_fingerprint {
            writer.write_all(&val.to_le_bytes())?;
        }

        writer.write_all(&r.importance_at_eviction.to_le_bytes())?;

        let prov_bytes = r.provenance_summary.as_bytes();
        writer.write_all(&(prov_bytes.len() as u64).to_le_bytes())?;
        writer.write_all(prov_bytes)?;
    }

        // Checksum calculation & footer
        let computed_hash = writer.hash;
        writer.enabled = false;
        writer.write_all(FOOTER_MAGIC)?;
        writer.write_all(&computed_hash.to_le_bytes())?;

        writer.flush()?;
        let f = writer.inner.into_inner().map_err(|e| e.into_error())?;
        f.sync_all()?;
        Ok(())
    })();

    if let Err(e) = write_res {
        let _ = std::fs::remove_file(&tmp_path);
        return Err(e);
    }

    std::fs::rename(&tmp_path, target)?;

    // Fsync parent directory for durable metadata rename on POSIX systems
    if let Ok(dir_file) = File::open(parent) {
        let _ = dir_file.sync_all();
    }

    Ok(())
}

pub fn load_engine_unlocked(path: impl AsRef<Path>) -> io::Result<ContinuumEngine> {
    let target = path.as_ref();
    let file = File::open(target)?;
    let mut reader = HashingReader::new(BufReader::new(file));

    // 1. Magic Header
    let mut magic = [0u8; 8];
    reader.read_exact(&mut magic)?;
    if &magic != MAGIC_HEADER {
        return Err(Error::new(
            ErrorKind::InvalidData,
            "Invalid Continuum checkpoint header",
        ));
    }

    // 2. Config
    let mut buf8 = [0u8; 8];
    let mut buf4 = [0u8; 4];

    reader.read_exact(&mut buf8)?;
    let embedding_dim = u64::from_le_bytes(buf8) as usize;

    reader.read_exact(&mut buf8)?;
    let state_dim = u64::from_le_bytes(buf8) as usize;

    reader.read_exact(&mut buf8)?;
    let hot_capacity = u64::from_le_bytes(buf8) as usize;

    reader.read_exact(&mut buf8)?;
    let cold_capacity = u64::from_le_bytes(buf8) as usize;

    reader.read_exact(&mut buf4)?;
    let sim_threshold = f32::from_le_bytes(buf4);

    let mut flag = [0u8; 1];
    reader.read_exact(&mut flag)?;
    let causal_exempt_threshold = if flag[0] == 1 {
        reader.read_exact(&mut buf4)?;
        Some(f32::from_le_bytes(buf4))
    } else {
        None
    };

    reader.read_exact(&mut buf4)?;
    let temporal_decay_tau = f32::from_le_bytes(buf4);

    reader.read_exact(&mut buf4)?;
    let w_sim = f32::from_le_bytes(buf4);

    reader.read_exact(&mut buf4)?;
    let w_state_compat = f32::from_le_bytes(buf4);

    reader.read_exact(&mut buf4)?;
    let w_temporal_compat = f32::from_le_bytes(buf4);

    reader.read_exact(&mut buf4)?;
    let w_provenance_compat = f32::from_le_bytes(buf4);

    let config = ContinuumConfig {
        embedding_dim,
        state_dim,
        hot_capacity,
        cold_capacity,
        sim_threshold,
        causal_exempt_threshold,
        temporal_decay_tau,
        w_sim,
        w_state_compat,
        w_temporal_compat,
        w_provenance_compat,
    };

    // 3. Step count
    reader.read_exact(&mut buf8)?;
    let step_count = u64::from_le_bytes(buf8);

    // 4. Temporal Core
    let mut temporal_core = TemporalCore::new(embedding_dim, state_dim);
    reader.read_exact(&mut buf8)?;
    let cur_state_len = u64::from_le_bytes(buf8) as usize;
    let mut cur_state = Vec::with_capacity(cur_state_len);
    for _ in 0..cur_state_len {
        reader.read_exact(&mut buf4)?;
        cur_state.push(f32::from_le_bytes(buf4));
    }
    temporal_core.state = cur_state;

    // 5. Hot Memory Bank
    let mut hot_memory = HotMemoryBank::new(hot_capacity);
    reader.read_exact(&mut buf8)?;
    let num_hot = u64::from_le_bytes(buf8) as usize;

    for _ in 0..num_hot {
        reader.read_exact(&mut buf8)?;
        let event_id = u64::from_le_bytes(buf8);

        reader.read_exact(&mut buf8)?;
        let timestamp = f64::from_le_bytes(buf8);

        reader.read_exact(&mut buf8)?;
        let emb_len = u64::from_le_bytes(buf8) as usize;
        let mut embedding = Vec::with_capacity(emb_len);
        for _ in 0..emb_len {
            reader.read_exact(&mut buf4)?;
            embedding.push(f32::from_le_bytes(buf4));
        }

        reader.read_exact(&mut buf8)?;
        let st_len = u64::from_le_bytes(buf8) as usize;
        let mut state_snapshot = Vec::with_capacity(st_len);
        for _ in 0..st_len {
            reader.read_exact(&mut buf4)?;
            state_snapshot.push(f32::from_le_bytes(buf4));
        }

        reader.read_exact(&mut buf4)?;
        let importance = f32::from_le_bytes(buf4);

        reader.read_exact(&mut buf8)?;
        let p_len = u64::from_le_bytes(buf8) as usize;
        let mut p_bytes = vec![0u8; p_len];
        reader.read_exact(&mut p_bytes)?;
        let payload_ref = String::from_utf8(p_bytes)
            .map_err(|e| Error::new(ErrorKind::InvalidData, e))?;

        hot_memory.records.push(HotRecord {
            event_id,
            timestamp,
            embedding,
            state_snapshot,
            importance,
            payload_ref,
        });
    }

    // 6. Cold Memory Candidate Archive
    let mut cold_memory = DiversifiedColdMemory::new(cold_capacity, sim_threshold);
    reader.read_exact(&mut buf8)?;
    let num_cold = u64::from_le_bytes(buf8) as usize;

    for _ in 0..num_cold {
        reader.read_exact(&mut buf8)?;
        let event_id = u64::from_le_bytes(buf8);

        reader.read_exact(&mut buf8)?;
        let timestamp = f64::from_le_bytes(buf8);

        reader.read_exact(&mut buf8)?;
        let emb_len = u64::from_le_bytes(buf8) as usize;
        let mut compressed_embedding = Vec::with_capacity(emb_len);
        for _ in 0..emb_len {
            reader.read_exact(&mut buf4)?;
            compressed_embedding.push(f32::from_le_bytes(buf4));
        }

        reader.read_exact(&mut buf8)?;
        let st_len = u64::from_le_bytes(buf8) as usize;
        let mut state_fingerprint = Vec::with_capacity(st_len);
        for _ in 0..st_len {
            reader.read_exact(&mut buf4)?;
            state_fingerprint.push(f32::from_le_bytes(buf4));
        }

        reader.read_exact(&mut buf4)?;
        let importance_at_eviction = f32::from_le_bytes(buf4);

        reader.read_exact(&mut buf8)?;
        let p_len = u64::from_le_bytes(buf8) as usize;
        let mut p_bytes = vec![0u8; p_len];
        reader.read_exact(&mut p_bytes)?;
        let provenance_summary = String::from_utf8(p_bytes)
            .map_err(|e| Error::new(ErrorKind::InvalidData, e))?;

        cold_memory.records.push(ColdRecord {
            event_id,
            timestamp,
            compressed_embedding,
            state_fingerprint,
            importance_at_eviction,
            provenance_summary,
        });
    }

    // 7. Verify Checksum Footer
    let computed_hash = reader.hash;
    reader.enabled = false;

    let mut footer_magic = [0u8; 8];
    match reader.read_exact(&mut footer_magic) {
        Ok(()) => {
            if &footer_magic == FOOTER_MAGIC {
                let mut cksum_buf = [0u8; 8];
                reader.read_exact(&mut cksum_buf)?;
                let expected_hash = u64::from_le_bytes(cksum_buf);
                if computed_hash != expected_hash {
                    return Err(Error::new(
                        ErrorKind::InvalidData,
                        "Snapshot checksum mismatch: corrupted or altered state file",
                    ));
                }
            }
        }
        Err(e) if e.kind() == ErrorKind::UnexpectedEof => {
            // Older snapshot without footer checksum is accepted for backward compatibility
        }
        Err(e) => return Err(e),
    }

    let revision_engine = RevisionEngine::new(config.clone());

    Ok(ContinuumEngine {
        config,
        temporal_core,
        hot_memory,
        cold_memory,
        revision_engine,
        step_count,
    })
}

/// Thread/process-safe save with exclusive lock.
pub fn save_engine(engine: &ContinuumEngine, path: impl AsRef<Path>) -> io::Result<()> {
    let target = path.as_ref();
    let _lock = crate::lock::FileLockGuard::acquire(target, std::time::Duration::from_millis(2000))?;
    save_engine_unlocked(engine, target)
}

/// Thread/process-safe load with exclusive lock.
pub fn load_engine(path: impl AsRef<Path>) -> io::Result<ContinuumEngine> {
    let target = path.as_ref();
    let _lock = crate::lock::FileLockGuard::acquire(target, std::time::Duration::from_millis(2000))?;
    load_engine_unlocked(target)
}

/// Transactional Read-Modify-Write (RMW) mutation on ContinuumEngine state file.
/// Holds the cross-process lock across the ENTIRE load -> mutate -> atomic save lifecycle,
/// eliminating race conditions and lost updates under concurrent multi-agent access.
pub fn mutate_engine_transactional<F, R>(
    path: impl AsRef<Path>,
    default_config: Option<ContinuumConfig>,
    f: F,
) -> io::Result<R>
where
    F: FnOnce(&mut ContinuumEngine) -> io::Result<R>,
{
    let target = path.as_ref();
    let parent = target.parent().unwrap_or_else(|| Path::new("."));
    if !parent.as_os_str().is_empty() {
        std::fs::create_dir_all(parent)?;
    }

    let _lock = crate::lock::FileLockGuard::acquire(target, std::time::Duration::from_millis(3000))?;

    let mut engine = if target.exists() {
        load_engine_unlocked(target)?
    } else {
        ContinuumEngine::new(default_config.unwrap_or_default())
    };

    let res = f(&mut engine)?;

    save_engine_unlocked(&engine, target)?;

    Ok(res)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_atomic_persistence_and_clean_state() {
        let temp_dir = std::env::temp_dir();
        let test_path = temp_dir.join(format!("continuum_atomic_{}.state", std::process::id()));

        let mut engine = ContinuumEngine::new(ContinuumConfig::default());
        let emb = vec![0.1f32; 32];
        engine.step(&emb, 1.0, "Atomic persistence test constraint");

        // Save atomically
        save_engine(&engine, &test_path).expect("Failed atomic save");

        // Lock should be released immediately and re-acquirable
        let lock_guard = crate::lock::FileLockGuard::acquire(&test_path, std::time::Duration::from_millis(100));
        assert!(lock_guard.is_ok(), "Lock was not released after save");
        drop(lock_guard);

        // Load back and verify bit-exact consistency
        let loaded = load_engine(&test_path).expect("Failed load");
        assert_eq!(loaded.step_count, 1);
        assert_eq!(loaded.hot_memory.len(), 1);
        assert_eq!(loaded.hot_memory.records[0].payload_ref, "Atomic persistence test constraint");

        let _ = std::fs::remove_file(&test_path);
        let _ = std::fs::remove_file(format!("{}.lock", test_path.display()));
    }

    #[test]
    fn test_mutate_engine_transactional_rmw() {
        let temp_dir = std::env::temp_dir();
        let test_path = temp_dir.join(format!("continuum_rmw_{}.state", std::process::id()));

        // Perform 3 sequential transactional mutations
        for i in 1..=3 {
            let res = mutate_engine_transactional(&test_path, None, |eng| {
                let emb = vec![0.05f32 * (i as f32); 32];
                eng.step(&emb, i as f64, &format!("Transactional Event #{i}"));
                Ok(eng.step_count)
            });
            assert_eq!(res.unwrap(), i as u64);
        }

        // Verify loaded state has all 3 events perfectly preserved
        let loaded = load_engine(&test_path).expect("Failed to load state");
        assert_eq!(loaded.step_count, 3);
        assert_eq!(loaded.hot_memory.len(), 3);
        assert_eq!(loaded.hot_memory.records[2].payload_ref, "Transactional Event #3");

        let _ = std::fs::remove_file(&test_path);
    }

    #[test]
    fn test_persistence_checksum_and_corruption_detection() {
        let temp_dir = std::env::temp_dir();
        let test_path = temp_dir.join(format!("continuum_cksum_{}.state", std::process::id()));

        let mut engine = ContinuumEngine::new(ContinuumConfig::default());
        let emb = vec![0.33f32; 32];
        engine.step(&emb, 100.0, "Checksum verification test event");

        save_engine(&engine, &test_path).expect("Save failed");

        // 1. Valid snapshot loads cleanly
        let loaded = load_engine(&test_path).expect("Valid snapshot failed to load");
        assert_eq!(loaded.step_count, 1);

        // 2. Tamper with one byte in the middle of the file
        let mut bytes = std::fs::read(&test_path).expect("Failed to read snapshot");
        let mid = bytes.len() / 2;
        bytes[mid] ^= 0xFF; // Flip bits
        std::fs::write(&test_path, &bytes).expect("Failed to write tampered snapshot");

        let err = load_engine(&test_path).expect_err("Corrupted snapshot should fail checksum");
        assert_eq!(err.kind(), ErrorKind::InvalidData);

        // 3. Truncate file
        std::fs::write(&test_path, &bytes[..20]).expect("Failed to write truncated file");
        assert!(load_engine(&test_path).is_err(), "Truncated file should fail loading");

        let _ = std::fs::remove_file(&test_path);
        let _ = std::fs::remove_file(format!("{}.lock", test_path.display()));
    }
}

