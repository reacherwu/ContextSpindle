//! C-compatible ABI exports for native bindings.
#![allow(unsafe_op_in_unsafe_fn)]

use std::ffi::CStr;
use std::os::raw::c_char;
use crate::engine::ContinuumEngine;
use crate::types::ContinuumConfig;

#[repr(C)]
#[derive(Debug, Clone, Copy)]
pub struct CContinuumConfig {
    pub embedding_dim: usize,
    pub state_dim: usize,
    pub hot_capacity: usize,
    pub cold_capacity: usize,
    pub sim_threshold: f32,
    pub causal_exempt_threshold: f32, // negative (< 0.0) means None
    pub temporal_decay_tau: f32,
    pub w_sim: f32,
    pub w_state_compat: f32,
    pub w_temporal_compat: f32,
    pub w_provenance_compat: f32,
}

#[repr(C)]
#[derive(Debug, Clone, Copy)]
pub struct CStreamStepResult {
    pub event_id: u64,
    pub timestamp: f64,
    pub importance: f32,
    pub is_hot: bool,
    pub total_slots_used: usize,
    pub state_norm: f32,
}

#[repr(C)]
#[derive(Debug, Clone, Copy)]
pub struct CCausalMatch {
    pub event_id: u64,
    pub timestamp: f64,
    pub revision_score: f32,
    pub sim: f32,
    pub state_compat: f32,
    pub temporal_compat: f32,
    pub provenance_compat: f32,
    pub provenance_buf: [u8; 128],
    pub provenance_len: usize,
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn continuum_engine_create(
    config: *const CContinuumConfig,
) -> *mut ContinuumEngine {
    let cfg = if config.is_null() {
        ContinuumConfig::default()
    } else {
        let c = &*config;
        ContinuumConfig {
            embedding_dim: c.embedding_dim,
            state_dim: c.state_dim,
            hot_capacity: c.hot_capacity,
            cold_capacity: c.cold_capacity,
            sim_threshold: c.sim_threshold,
            causal_exempt_threshold: if c.causal_exempt_threshold < 0.0 {
                None
            } else {
                Some(c.causal_exempt_threshold)
            },
            temporal_decay_tau: c.temporal_decay_tau,
            w_sim: c.w_sim,
            w_state_compat: c.w_state_compat,
            w_temporal_compat: c.w_temporal_compat,
            w_provenance_compat: c.w_provenance_compat,
        }
    };

    let engine = Box::new(ContinuumEngine::new(cfg));
    Box::into_raw(engine)
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn continuum_engine_step(
    engine: *mut ContinuumEngine,
    embedding: *const f32,
    emb_len: usize,
    timestamp: f64,
    payload_ptr: *const c_char,
    out_result: *mut CStreamStepResult,
) -> i32 {
    if engine.is_null() || embedding.is_null() {
        return -1;
    }

    let eng = &mut *engine;
    let emb_slice = std::slice::from_raw_parts(embedding, emb_len);

    let payload_str = if payload_ptr.is_null() {
        ""
    } else {
        match CStr::from_ptr(payload_ptr).to_str() {
            Ok(s) => s,
            Err(_) => return -2,
        }
    };

    let res = eng.step(emb_slice, timestamp, payload_str);

    if !out_result.is_null() {
        *out_result = CStreamStepResult {
            event_id: res.event_id,
            timestamp: res.timestamp,
            importance: res.importance,
            is_hot: res.is_hot,
            total_slots_used: res.total_slots_used,
            state_norm: res.state_norm,
        };
    }

    0
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn continuum_engine_query(
    engine: *mut ContinuumEngine,
    query_emb: *const f32,
    q_len: usize,
    top_k: usize,
    out_matches: *mut CCausalMatch,
    max_matches: usize,
) -> usize {
    if engine.is_null() || query_emb.is_null() || out_matches.is_null() || max_matches == 0 {
        return 0;
    }

    let eng = &*engine;
    let q_slice = std::slice::from_raw_parts(query_emb, q_len);
    let matches = eng.query(q_slice, top_k);

    let count = matches.len().min(max_matches);
    let out_slice = std::slice::from_raw_parts_mut(out_matches, count);

    for (i, m) in matches.iter().take(count).enumerate() {
        let mut buf = [0u8; 128];
        let bytes = m.provenance.as_bytes();
        let copy_len = bytes.len().min(127);
        buf[..copy_len].copy_from_slice(&bytes[..copy_len]);

        out_slice[i] = CCausalMatch {
            event_id: m.event_id,
            timestamp: m.timestamp,
            revision_score: m.revision_score,
            sim: m.components.sim,
            state_compat: m.components.state_compat,
            temporal_compat: m.components.temporal_compat,
            provenance_compat: m.components.provenance_compat,
            provenance_buf: buf,
            provenance_len: copy_len,
        };
    }

    count
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn continuum_engine_get_stats(
    engine: *const ContinuumEngine,
    out_hot_slots: *mut usize,
    out_cold_slots: *mut usize,
    out_step_count: *mut u64,
) -> i32 {
    if engine.is_null() {
        return -1;
    }
    let eng = &*engine;
    if !out_hot_slots.is_null() {
        *out_hot_slots = eng.hot_memory.len();
    }
    if !out_cold_slots.is_null() {
        *out_cold_slots = eng.cold_memory.len();
    }
    if !out_step_count.is_null() {
        *out_step_count = eng.step_count;
    }
    0
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn continuum_engine_destroy(engine: *mut ContinuumEngine) {
    if !engine.is_null() {
        drop(Box::from_raw(engine));
    }
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn continuum_engine_save(
    engine: *const ContinuumEngine,
    path_ptr: *const c_char,
) -> i32 {
    if engine.is_null() || path_ptr.is_null() {
        return -1;
    }
    let path_str = match CStr::from_ptr(path_ptr).to_str() {
        Ok(s) => s,
        Err(_) => return -2,
    };
    let eng = &*engine;
    match eng.save_to_file(path_str) {
        Ok(()) => 0,
        Err(_) => -3,
    }
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn continuum_engine_load(
    path_ptr: *const c_char,
) -> *mut ContinuumEngine {
    if path_ptr.is_null() {
        return std::ptr::null_mut();
    }
    let path_str = match CStr::from_ptr(path_ptr).to_str() {
        Ok(s) => s,
        Err(_) => return std::ptr::null_mut(),
    };
    match ContinuumEngine::load_from_file(path_str) {
        Ok(eng) => Box::into_raw(Box::new(eng)),
        Err(_) => std::ptr::null_mut(),
    }
}
