//! Bounded Cold Candidate Archive with Subspace Diversity Deduplication.

use crate::math::{dot, norm, normalize};
use crate::types::ColdRecord;

#[derive(Debug, Clone)]
pub struct DiversifiedColdMemory {
    pub capacity: usize,
    pub records: Vec<ColdRecord>,
    pub sim_thresh: f32,
}

impl DiversifiedColdMemory {
    pub fn new(capacity: usize, sim_thresh: f32) -> Self {
        Self {
            capacity,
            records: Vec::with_capacity(capacity),
            sim_thresh,
        }
    }

    /// Archive an evicted or bypassed record into cold memory.
    pub fn archive(
        &mut self,
        event_id: u64,
        timestamp: f64,
        embedding: &[f32],
        temporal_state: &[f32],
        importance: f32,
        provenance: &str,
    ) {
        let norm_emb = normalize(embedding);
        let record = ColdRecord {
            event_id,
            timestamp,
            compressed_embedding: norm_emb,
            state_fingerprint: temporal_state.to_vec(),
            importance_at_eviction: importance,
            provenance_summary: provenance.to_string(),
        };

        if self.records.len() >= self.capacity {
            self.evict_redundant_or_lowest();
        }

        self.records.push(record);
    }

    /// Evicts the candidate with the highest mutual redundancy (sim >= sim_thresh),
    /// or the lowest composite retention score.
    fn evict_redundant_or_lowest(&mut self) {
        if self.records.is_empty() {
            return;
        }

        let n = self.records.len();
        let mut max_sims = vec![0.0f32; n];

        // Compute max similarity for each record against all other records
        for i in 0..n {
            let mut best_sim = -1.0f32;
            for j in 0..n {
                if i != j {
                    let s = dot(&self.records[i].compressed_embedding, &self.records[j].compressed_embedding);
                    if s > best_sim {
                        best_sim = s;
                    }
                }
            }
            max_sims[i] = best_sim;
        }

        // Check if any record exceeds redundancy threshold
        let mut highest_sim = -1.0f32;
        let mut most_redundant_idx = None;
        for (i, &s) in max_sims.iter().enumerate() {
            if s >= self.sim_thresh && s > highest_sim {
                highest_sim = s;
                most_redundant_idx = Some(i);
            }
        }

        let evict_idx = if let Some(idx) = most_redundant_idx {
            idx
        } else {
            // Evict lowest score (0.4 * importance + 0.6 * state_norm)
            let mut min_score = f32::MAX;
            let mut min_idx = 0;
            for (i, rec) in self.records.iter().enumerate() {
                let st_n = norm(&rec.state_fingerprint);
                let sc = 0.4 * rec.importance_at_eviction + 0.6 * st_n;
                if sc < min_score {
                    min_score = sc;
                    min_idx = i;
                }
            }
            min_idx
        };

        self.records.remove(evict_idx);
    }

    pub fn len(&self) -> usize {
        self.records.len()
    }

    pub fn is_empty(&self) -> bool {
        self.records.is_empty()
    }
}
