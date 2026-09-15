//! High-level facade for Continuum: Continuous Temporal Intelligence Engine in pure Rust.

use crate::cold_memory::DiversifiedColdMemory;
use crate::hot_memory::HotMemoryBank;
use crate::math::norm;
use crate::revision::RevisionEngine;
use crate::temporal::TemporalCore;
use crate::types::{CausalMatch, ColdRecord, ContinuumConfig, StreamStepResult};

#[derive(Debug, Clone)]
pub struct ContinuumEngine {
    pub config: ContinuumConfig,
    pub temporal_core: TemporalCore,
    pub hot_memory: HotMemoryBank,
    pub cold_memory: DiversifiedColdMemory,
    pub revision_engine: RevisionEngine,
    pub step_count: u64,
}

impl ContinuumEngine {
    pub fn new(config: ContinuumConfig) -> Self {
        let temporal_core = TemporalCore::new(config.embedding_dim, config.state_dim);
        let hot_memory = HotMemoryBank::new(config.hot_capacity);
        let cold_memory = DiversifiedColdMemory::new(config.cold_capacity, config.sim_threshold);
        let revision_engine = RevisionEngine::new(config.clone());

        Self {
            config,
            temporal_core,
            hot_memory,
            cold_memory,
            revision_engine,
            step_count: 0,
        }
    }

    /// Ingest a streaming event into Continuum.
    pub fn step(
        &mut self,
        embedding: &[f32],
        timestamp: f64,
        payload_ref: &str,
    ) -> StreamStepResult {
        let event_id = self.step_count;
        let cur_state = self.temporal_core.step(embedding);

        let (admitted_hot, importance, evicted_hot) = self.hot_memory.observe(
            event_id,
            timestamp,
            embedding,
            &cur_state,
            payload_ref,
        );

        if let Some(evicted) = evicted_hot {
            // Evicted hot item enters cold candidate archive
            self.cold_memory.archive(
                evicted.event_id,
                evicted.timestamp,
                &evicted.embedding,
                &evicted.state_snapshot,
                evicted.importance,
                &format!("evicted_from_hot_{}", evicted.payload_ref),
            );
        } else if !admitted_hot {
            // Bypass admission directly to cold candidate archive
            self.cold_memory.archive(
                event_id,
                timestamp,
                embedding,
                &cur_state,
                importance,
                payload_ref,
            );
        }

        self.step_count += 1;
        let total_slots = self.hot_memory.len() + self.cold_memory.len();
        let state_norm = norm(&cur_state);

        StreamStepResult {
            event_id,
            timestamp,
            importance,
            is_hot: admitted_hot,
            total_slots_used: total_slots,
            state_norm,
        }
    }

    /// Retrospective causal query across both active and cold candidate memory.
    pub fn query(&self, query_emb: &[f32], top_k: usize) -> Vec<CausalMatch> {
        let cur_state = self.temporal_core.current_state();
        let cur_time = self.step_count as f64;

        let mut scored = Vec::with_capacity(self.hot_memory.len() + self.cold_memory.len());

        // 1. Score all cold candidates
        for cand in &self.cold_memory.records {
            let m = self.revision_engine.score_candidate(cand, query_emb, cur_state, cur_time);
            scored.push(m);
        }

        // 2. Score all hot records
        for h_rec in &self.hot_memory.records {
            let cand = ColdRecord {
                event_id: h_rec.event_id,
                timestamp: h_rec.timestamp,
                compressed_embedding: h_rec.embedding.clone(),
                state_fingerprint: h_rec.state_snapshot.clone(),
                importance_at_eviction: h_rec.importance,
                provenance_summary: h_rec.payload_ref.clone(),
            };
            let m = self.revision_engine.score_candidate(&cand, query_emb, cur_state, cur_time);
            scored.push(m);
        }

        // Sort descending by revision_score
        scored.sort_by(|a, b| b.revision_score.partial_cmp(&a.revision_score).unwrap_or(std::cmp::Ordering::Equal));
        scored.truncate(top_k);
        scored
    }

    pub fn total_slots(&self) -> usize {
        self.hot_memory.len() + self.cold_memory.len()
    }

    /// Persist complete engine state to disk.
    pub fn save_to_file(&self, path: impl AsRef<std::path::Path>) -> std::io::Result<()> {
        crate::persistence::save_engine(self, path)
    }

    /// Restore complete engine state from disk.
    pub fn load_from_file(path: impl AsRef<std::path::Path>) -> std::io::Result<Self> {
        crate::persistence::load_engine(path)
    }
}
