//! Bounded Hot Working Memory Bank.

use crate::math::{dot, normalize};
use crate::types::HotRecord;

#[derive(Debug, Clone)]
pub struct HotMemoryBank {
    pub capacity: usize,
    pub records: Vec<HotRecord>,
}

impl HotMemoryBank {
    pub fn new(capacity: usize) -> Self {
        Self {
            capacity,
            records: Vec::with_capacity(capacity),
        }
    }

    /// Computes multi-factor importance for incoming event.
    pub fn compute_importance(&self, x_norm: &[f32], temporal_state: &[f32]) -> f32 {
        // Novelty: 1 - max_similarity to active bank
        let novelty = if self.records.is_empty() {
            1.0f32
        } else {
            let mut max_s = 0.0f32;
            for r in &self.records {
                let s = dot(x_norm, &r.embedding);
                if s > max_s {
                    max_s = s;
                }
            }
            (1.0 - max_s).clamp(0.0, 1.0)
        };

        // State displacement proxy
        let state_mag = (dot(temporal_state, temporal_state)).sqrt();
        let causal_proxy = (state_mag / 2.0).tanh();

        let importance = 0.4 * novelty + 0.4 * causal_proxy + 0.2 * 0.5;
        importance.clamp(0.0, 1.0)
    }

    /// Observe an incoming event. Returns Some(evicted_record) if bank was full and evicted a record.
    pub fn observe(
        &mut self,
        event_id: u64,
        timestamp: f64,
        embedding: &[f32],
        temporal_state: &[f32],
        payload_ref: &str,
    ) -> (bool, f32, Option<HotRecord>) {
        let x_norm = normalize(embedding);
        let importance = self.compute_importance(&x_norm, temporal_state);

        if self.records.len() >= self.capacity {
            // Find record with minimal importance
            let mut min_imp = f32::MAX;
            let mut min_idx = 0;
            for (i, r) in self.records.iter().enumerate() {
                if r.importance < min_imp {
                    min_imp = r.importance;
                    min_idx = i;
                }
            }

            if importance > min_imp {
                let evicted = Some(self.records.remove(min_idx));
                self.records.push(HotRecord {
                    event_id,
                    timestamp,
                    embedding: x_norm,
                    state_snapshot: temporal_state.to_vec(),
                    importance,
                    payload_ref: payload_ref.to_string(),
                });
                (true, importance, evicted)
            } else {
                // Incoming item has lower importance than all stored items
                (false, importance, None)
            }
        } else {
            self.records.push(HotRecord {
                event_id,
                timestamp,
                embedding: x_norm,
                state_snapshot: temporal_state.to_vec(),
                importance,
                payload_ref: payload_ref.to_string(),
            });
            (true, importance, None)
        }
    }

    pub fn len(&self) -> usize {
        self.records.len()
    }

    pub fn is_empty(&self) -> bool {
        self.records.is_empty()
    }
}
