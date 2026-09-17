//! Continuum Core: Continuous Temporal Intelligence Engine in Rust.
//!
//! Provides deterministic O(K) bounded memory, O(1) state recurrence,
//! subspace diversity deduplication, and retrospective causal revision.

pub mod cold_memory;
pub mod embedder;
pub mod engine;
pub mod ffi;
pub mod hot_memory;
pub mod lock;
pub mod math;
pub mod persistence;
pub mod revision;
pub mod recovery;
pub mod semantic_bridge;
pub mod temporal;
pub mod types;

pub use embedder::RealTextEmbedder;
pub use engine::ContinuumEngine;
pub use lock::FileLockGuard;
pub use persistence::{load_engine, mutate_engine_transactional, save_engine};
pub use recovery::{SnapshotInfo, backup_engine, check_snapshot, restore_engine};
pub use semantic_bridge::SemanticCausalBridge;
pub use types::{CausalMatch, ContinuumConfig, ScoreComponents, StreamStepResult};

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_bounded_memory_invariant() {
        let config = ContinuumConfig {
            embedding_dim: 8,
            state_dim: 8,
            hot_capacity: 10,
            cold_capacity: 20,
            sim_threshold: 0.70,
            ..Default::default()
        };
        let mut engine = ContinuumEngine::new(config);

        // Ingest 1000 events
        for t in 0..1000 {
            let mut emb = vec![0.0f32; 8];
            emb[t % 8] = 1.0;
            let res = engine.step(&emb, t as f64, &format!("event_{t}"));
            assert!(res.total_slots_used <= 30);
        }

        assert_eq!(engine.total_slots(), 30);
        assert_eq!(engine.hot_memory.len(), 10);
        assert_eq!(engine.cold_memory.len(), 20);
    }

    #[test]
    fn test_retrospective_causal_query() {
        let config = ContinuumConfig {
            embedding_dim: 4,
            state_dim: 4,
            hot_capacity: 5,
            cold_capacity: 10,
            causal_exempt_threshold: Some(0.30),
            ..Default::default()
        };
        let mut engine = ContinuumEngine::new(config);

        // Root cause at t=5
        let root_vec = vec![1.0, 0.0, 0.0, 0.0];
        engine.step(&root_vec, 5.0, "root_cause_config");

        // Noise
        for t in 6..50 {
            let noise = vec![0.0, 1.0, 0.0, 0.0];
            engine.step(&noise, t as f64, &format!("noise_{t}"));
        }

        // Query matching root cause
        let query_vec = vec![0.9, 0.1, 0.0, 0.0];
        let matches = engine.query(&query_vec, 3);

        assert!(!matches.is_empty());
        // Root cause (first step event_id = 0, timestamp = 5.0) should be retrieved
        assert!(matches.iter().any(|m| m.event_id == 0 || m.timestamp == 5.0));
    }

    #[test]
    fn test_causal_supersession_and_contradiction_resolution() {
        let config = ContinuumConfig {
            embedding_dim: 4,
            state_dim: 4,
            hot_capacity: 5,
            cold_capacity: 10,
            sim_threshold: 0.65,
            causal_exempt_threshold: Some(0.30),
            ..Default::default()
        };
        let mut engine = ContinuumEngine::new(config);

        // Turn 5: Rule v1: db_pool = 5
        let rule_v1_vec = vec![1.0, 0.0, 0.0, 0.0];
        engine.step(&rule_v1_vec, 5.0, "db_pool_limit = 5");

        // Turns 6..30: Background noise
        for t in 6..30 {
            let noise = vec![0.0, 1.0, 0.0, 0.0];
            engine.step(&noise, t as f64, &format!("noise_{t}"));
        }

        // Turn 31: Rule v2 (Contradiction / Override): db_pool = 20
        let rule_v2_vec = vec![0.95, 0.1, 0.0, 0.0];
        engine.step(&rule_v2_vec, 31.0, "db_pool_limit = 20 (supersedes limit 5)");

        // Turns 32..60: More background noise
        for t in 32..60 {
            let noise = vec![0.0, 1.0, 0.0, 0.0];
            engine.step(&noise, t as f64, &format!("noise_{t}"));
        }

        // Query for db_pool configuration
        let query_vec = vec![0.98, 0.05, 0.0, 0.0];
        let matches = engine.query(&query_vec, 5);

        assert!(!matches.is_empty());
        // Rank #1 MUST be the newer override rule (Rule v2 at t=31.0)
        assert_eq!(matches[0].timestamp, 31.0);
        assert!(matches[0].provenance.contains("db_pool_limit = 20"));

        // If Rule v1 is present in matches, it must be marked as superseded
        if let Some(v1_match) = matches.iter().find(|m| m.timestamp == 5.0) {
            assert!(v1_match.provenance.contains("[superseded by #"));
            assert!(matches[0].revision_score > v1_match.revision_score);
        }
    }

    #[test]
    fn test_native_embedder_and_semantic_bridge() {
        let embedder = RealTextEmbedder::new(16, 42);
        let bridge = SemanticCausalBridge::new();

        let query = "Agent failure: TLS handshake failure SSLV3_ALERT_HANDSHAKE_FAILURE";
        let (v_bridged, exp) = bridge.project_query(query, &embedder, 0.5);

        assert_eq!(v_bridged.len(), 16);
        assert!(exp.matched_domains.contains(&"tls_crypto_configuration".to_string()));
        assert!(exp.expanded_concepts.contains(&"openssl".to_string()));

        let v_cause = embedder.embed("updated openssl.conf with legacy crypto");
        let sim = crate::math::cosine_similarity(&v_bridged, &v_cause);
        assert!(sim > 0.0);
    }

    #[test]
    fn test_engine_save_load_roundtrip() {
        let config = ContinuumConfig {
            embedding_dim: 8,
            state_dim: 8,
            hot_capacity: 10,
            cold_capacity: 20,
            sim_threshold: 0.70,
            causal_exempt_threshold: Some(0.25),
            ..Default::default()
        };
        let mut engine = ContinuumEngine::new(config);

        for t in 0..50 {
            let mut emb = vec![0.0f32; 8];
            emb[t % 8] = 1.0;
            engine.step(&emb, t as f64, &format!("log_event_{t}"));
        }

        let query = vec![1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0];
        let original_matches = engine.query(&query, 5);

        let temp_dir = std::env::temp_dir();
        let snapshot_path = temp_dir.join(format!("continuum_test_{}.bin", std::process::id()));

        // Save
        engine.save_to_file(&snapshot_path).expect("Failed to save snapshot");
        assert!(snapshot_path.exists());

        // Load into brand new engine instance (simulating restart after shutdown)
        let restored_engine = ContinuumEngine::load_from_file(&snapshot_path).expect("Failed to load snapshot");
        let _ = std::fs::remove_file(&snapshot_path);

        assert_eq!(engine.step_count, restored_engine.step_count);
        assert_eq!(engine.total_slots(), restored_engine.total_slots());
        assert_eq!(engine.hot_memory.len(), restored_engine.hot_memory.len());
        assert_eq!(engine.cold_memory.len(), restored_engine.cold_memory.len());

        // Check query equivalence
        let restored_matches = restored_engine.query(&query, 5);
        assert_eq!(original_matches.len(), restored_matches.len());
        for (m1, m2) in original_matches.iter().zip(&restored_matches) {
            assert_eq!(m1.event_id, m2.event_id);
            assert!((m1.revision_score - m2.revision_score).abs() < 1e-6);
        }
    }
}
