//! Core type definitions and configurations for Continuum.

#[derive(Debug, Clone)]
pub struct ContinuumConfig {
    pub embedding_dim: usize,
    pub state_dim: usize,
    pub hot_capacity: usize,
    pub cold_capacity: usize,
    pub sim_threshold: f32,
    pub causal_exempt_threshold: Option<f32>,
    pub temporal_decay_tau: f32,
    pub w_sim: f32,
    pub w_state_compat: f32,
    pub w_temporal_compat: f32,
    pub w_provenance_compat: f32,
}

impl Default for ContinuumConfig {
    fn default() -> Self {
        Self {
            embedding_dim: 32,
            state_dim: 32,
            hot_capacity: 250,
            cold_capacity: 500,
            sim_threshold: 0.65,
            causal_exempt_threshold: Some(0.25),
            temporal_decay_tau: 1000.0,
            w_sim: 0.55,
            w_state_compat: 0.15,
            w_temporal_compat: 0.20,
            w_provenance_compat: 0.10,
        }
    }
}

#[derive(Debug, Clone)]
pub struct HotRecord {
    pub event_id: u64,
    pub timestamp: f64,
    pub embedding: Vec<f32>,
    pub state_snapshot: Vec<f32>,
    pub importance: f32,
    pub payload_ref: String,
}

#[derive(Debug, Clone)]
pub struct ColdRecord {
    pub event_id: u64,
    pub timestamp: f64,
    pub compressed_embedding: Vec<f32>,
    pub state_fingerprint: Vec<f32>,
    pub importance_at_eviction: f32,
    pub provenance_summary: String,
}

#[derive(Debug, Clone)]
pub struct ScoreComponents {
    pub sim: f32,
    pub state_compat: f32,
    pub temporal_compat: f32,
    pub provenance_compat: f32,
}

#[derive(Debug, Clone)]
pub struct CausalMatch {
    pub event_id: u64,
    pub timestamp: f64,
    pub revision_score: f32,
    pub components: ScoreComponents,
    pub provenance: String,
}

#[derive(Debug, Clone)]
pub struct StreamStepResult {
    pub event_id: u64,
    pub timestamp: f64,
    pub importance: f32,
    pub is_hot: bool,
    pub total_slots_used: usize,
    pub state_norm: f32,
}
