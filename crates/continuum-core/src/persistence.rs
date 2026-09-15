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

pub fn save_engine(engine: &ContinuumEngine, path: impl AsRef<Path>) -> io::Result<()> {
    let file = File::create(path)?;
    let mut writer = BufWriter::new(file);

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

    writer.flush()?;
    Ok(())
}

pub fn load_engine(path: impl AsRef<Path>) -> io::Result<ContinuumEngine> {
    let file = File::open(path)?;
    let mut reader = BufReader::new(file);

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
