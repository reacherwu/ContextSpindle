//! Retrospective Causal Revision Engine.

use crate::math::{cosine_similarity, dot, normalize};
use crate::types::{CausalMatch, ColdRecord, ContinuumConfig, ScoreComponents};

#[derive(Debug, Clone)]
pub struct RevisionEngine {
    pub config: ContinuumConfig,
}

impl RevisionEngine {
    pub fn new(config: ContinuumConfig) -> Self {
        Self { config }
    }

    /// Computes causal revision score for a candidate record against a query symptom.
    pub fn score_candidate(
        &self,
        record: &ColdRecord,
        query_emb: &[f32],
        current_state: &[f32],
        current_time: f64,
    ) -> CausalMatch {
        let q_norm = normalize(query_emb);

        // 1. Semantic Cosine Similarity
        let sim = dot(&record.compressed_embedding, &q_norm).clamp(0.0, 1.0);

        // 2. State Compatibility (cosine similarity of state fingerprints)
        let state_compat = cosine_similarity(&record.state_fingerprint, current_state);

        // 3. Temporal Compatibility with Causal Exemption
        let delta_t = (current_time - record.timestamp).abs() as f32;
        let temporal_compat = if let Some(thresh) = self.config.causal_exempt_threshold {
            if sim >= thresh {
                1.0f32
            } else {
                (-delta_t / self.config.temporal_decay_tau).exp()
            }
        } else {
            (-delta_t / self.config.temporal_decay_tau).exp()
        };

        // 4. Provenance compatibility
        let provenance_compat = 0.5f32;

        let revision_score = self.config.w_sim * sim
            + self.config.w_state_compat * state_compat
            + self.config.w_temporal_compat * temporal_compat
            + self.config.w_provenance_compat * provenance_compat;

        CausalMatch {
            event_id: record.event_id,
            timestamp: record.timestamp,
            revision_score,
            components: ScoreComponents {
                sim,
                state_compat,
                temporal_compat,
                provenance_compat,
            },
            provenance: record.provenance_summary.clone(),
        }
    }
}
