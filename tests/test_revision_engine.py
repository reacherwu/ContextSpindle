import unittest
import torch
import math
from continuum.memory.cold_memory import ColdCandidateMemory, ColdCandidateRecord
from continuum.memory.revision_engine import RevisionEngine, RevisionConfig
from continuum.memory.adaptive_memory import AdaptiveMemory, AdaptiveMemoryConfig

class TestRevisionEngine(unittest.TestCase):
    def setUp(self):
        self.config = RevisionConfig(
            w_sim=0.4,
            w_state_compat=0.3,
            w_temporal_compat=0.2,
            w_provenance_compat=0.1,
            theta_trigger=0.7,
            theta_restore=0.5,
            temporal_decay_tau=1000.0,
            max_restorations_per_trigger=1
        )
        self.engine = RevisionEngine(self.config)
        self.emb_dim = 16
        self.state_dim = 8
        self.cold_memory = ColdCandidateMemory(capacity=100, embedding_dim=self.emb_dim, state_dim=self.state_dim)
        
    def test_score_computation(self):
        # 1. Exact match setup
        c_emb = torch.zeros(self.emb_dim); c_emb[0] = 1.0
        c_state = torch.zeros(self.state_dim); c_state[0] = 1.0
        candidate = ColdCandidateRecord(
            event_id=1, timestamp=1000.0, compressed_embedding=c_emb, state_fingerprint=c_state,
            importance_at_eviction=0.8, provenance_summary=""
        )
        t_emb = c_emb.clone()
        t_state = c_state.clone()
        t_time = 1000.0
        
        score, comps = self.engine._compute_revision_score_with_components(candidate, t_emb, t_state, t_time)
        # sim=1.0, state=1.0, temp=1.0, prov=0.5
        # score = 0.4*1 + 0.3*1 + 0.2*1 + 0.1*0.5 = 0.95
        self.assertAlmostEqual(score, 0.95, places=4)
        
    def test_theta_trigger_gating(self):
        # Trigger importance = 0.6 <= 0.7 -> should return empty
        res = self.engine.try_revision(
            trigger_event_id=10, trigger_embedding=torch.randn(self.emb_dim),
            trigger_state=torch.randn(self.state_dim), trigger_timestamp=2000.0,
            trigger_importance=0.6, cold_memory=self.cold_memory
        )
        self.assertEqual(len(res), 0)

    def test_theta_restore_gating(self):
        # Set up a candidate that will score very low (orthogonal)
        c_emb = torch.zeros(self.emb_dim); c_emb[0] = 1.0
        c_state = torch.zeros(self.state_dim); c_state[0] = 1.0
        self.cold_memory.archive(event_id=1, timestamp=1000.0, embedding=c_emb, temporal_state=c_state, importance=0.8, provenance="test")
        
        t_emb = torch.zeros(self.emb_dim); t_emb[1] = 1.0  # orthogonal
        t_state = torch.zeros(self.state_dim); t_state[1] = 1.0 # orthogonal
        t_time = 2000.0
        
        res = self.engine.try_revision(
            trigger_event_id=10, trigger_embedding=t_emb, trigger_state=t_state, trigger_timestamp=t_time,
            trigger_importance=0.8, cold_memory=self.cold_memory
        )
        # Score will be: 0.4*0 + 0.3*0 + 0.2*exp(-1000/1000) + 0.1*0.5 
        # = 0 + 0 + 0.2*0.367 + 0.05 = ~0.123 < 0.5 (theta_restore)
        # Should return empty because try_revision filters by theta_restore
        self.assertEqual(len(res), 0)

    def test_temporal_decay(self):
        c_emb = torch.zeros(self.emb_dim); c_emb[0] = 1.0
        c_state = torch.zeros(self.state_dim); c_state[0] = 1.0
        candidate = ColdCandidateRecord(
            event_id=1, timestamp=0.0, compressed_embedding=c_emb, state_fingerprint=c_state,
            importance_at_eviction=0.8, provenance_summary=""
        )
        
        score, comps = self.engine._compute_revision_score_with_components(candidate, c_emb, c_state, 5000.0)
        expected_temporal = math.exp(-5000.0 / 1000.0)
        self.assertAlmostEqual(comps["temporal_compat"], expected_temporal, places=4)
        self.assertAlmostEqual(expected_temporal, 0.0067, places=3)

    def test_integration_observe_with_revision(self):
        mem_config = AdaptiveMemoryConfig(embedding_dim=self.emb_dim, state_dim=self.state_dim, capacity=1)
        am = AdaptiveMemory(mem_config)
        
        # Put something in cold memory
        c_emb = torch.zeros(self.emb_dim); c_emb[0] = 1.0
        c_state = torch.zeros(self.state_dim); c_state[0] = 1.0
        self.cold_memory.archive(event_id=1, timestamp=1000.0, embedding=c_emb, temporal_state=c_state, importance=0.9, provenance="test")
        
        # Trigger event, exactly similar
        # Since we use capacity=1, the new event might evict, but the revision should restore event 1
        t_emb = c_emb.clone()
        t_state = c_state.clone()
        
        # Test integration: observe_with_revision triggers revision on high-importance event
        # Mock engine config so any positive importance event triggers revision and restores
        self.engine.config = RevisionConfig(theta_trigger=-0.1, theta_restore=0.0)
        record, revisions = am.observe_with_revision(
            event_id=4, timestamp=1100.0, embedding=t_emb, temporal_state=t_state, 
            cold_memory=self.cold_memory, revision_engine=self.engine
        )
        self.assertEqual(len(revisions), 1)
        self.assertEqual(revisions[0].candidate.event_id, 1)
        self.assertEqual(revisions[0].decision, "restore")

if __name__ == "__main__":
    unittest.main()
