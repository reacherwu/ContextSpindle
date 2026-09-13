import unittest
import torch
from continuum.memory.adaptive_memory import (
    AdaptiveMemory,
    AdaptiveMemoryConfig,
    EventRecord,
    RetentionDecision,
)


class TestEventRecord(unittest.TestCase):
    def test_valid_record(self):
        emb = torch.randn(64)
        emb = emb / torch.norm(emb)
        rec = EventRecord(
            event_id=1,
            timestamp=100.0,
            embedding=emb,
            surprise=0.3,
            novelty=0.8,
            importance=0.55,
            decision=RetentionDecision.KEEP,
        )
        self.assertEqual(rec.event_id, 1)
        self.assertEqual(rec.timestamp, 100.0)
        self.assertEqual(rec.decision, RetentionDecision.KEEP)

    def test_immutability(self):
        emb = torch.randn(64)
        rec = EventRecord(event_id=1, timestamp=0.0, embedding=emb)
        with self.assertRaises(Exception):
            rec.event_id = 2  # Frozen dataclass should reject modification

    def test_invalid_metrics_fail(self):
        emb = torch.randn(64)
        with self.assertRaises(ValueError):
            EventRecord(event_id=1, timestamp=0.0, embedding=emb, surprise=1.5)  # > 1.0


class TestAdaptiveMemory(unittest.TestCase):
    def setUp(self):
        torch.manual_seed(42)
        self.config = AdaptiveMemoryConfig(
            embedding_dim=32,
            state_dim=16,
            capacity=20,
            policy_mode="fixed_budget",
            eviction_policy="min_importance",
            alpha_surprise=0.2,
            beta_novelty=0.2,
            gamma_causal=0.2,
            delta_retrieval=0.2,
            epsilon_uncertainty=0.2,
            seed=42,
        )
        self.memory = AdaptiveMemory(self.config)

    def test_fixed_budget_capacity_strict_invariant(self):
        """Verify memory never exceeds bounded capacity K."""
        h = torch.randn(16)
        for t in range(100):
            x = torch.randn(32)
            rec = self.memory.observe(
                event_id=t,
                timestamp=float(t),
                embedding=x,
                temporal_state=h,
            )
            stats = self.memory.get_stats()
            self.assertLessEqual(stats["current_size"], self.config.capacity)

        final_stats = self.memory.get_stats()
        self.assertEqual(final_stats["current_size"], 20)
        self.assertEqual(final_stats["total_observed"], 100)
        self.assertEqual(final_stats["total_retained"] - final_stats["total_evicted"], 20)

    def test_retrieval_ranking(self):
        """Verify cosine similarity retrieval."""
        target_vec = torch.randn(32)
        target_vec = target_vec / torch.norm(target_vec)

        # Store target
        self.memory.observe(event_id=999, timestamp=1.0, embedding=target_vec)

        # Store distractors (orthogonal-ish)
        for i in range(10):
            d = torch.randn(32)
            self.memory.observe(event_id=i, timestamp=float(i + 2), embedding=d)

        # Query with target_vec + slight noise
        q = target_vec + 0.01 * torch.randn(32)
        retrieved = self.memory.retrieve(q, top_k=1)
        self.assertEqual(len(retrieved), 1)
        best_rec, sim = retrieved[0]
        self.assertEqual(best_rec.event_id, 999)
        self.assertGreater(sim, 0.95)

    def test_eviction_policies(self):
        """Test FIFO, Random, and LRU eviction policies."""
        for policy in ["fifo", "random", "lru"]:
            cfg = AdaptiveMemoryConfig(
                embedding_dim=16,
                capacity=5,
                policy_mode="fixed_budget",
                eviction_policy=policy,
                seed=101,
            )
            mem = AdaptiveMemory(cfg)
            for i in range(15):
                mem.observe(event_id=i, timestamp=float(i), embedding=torch.randn(16))
            stats = mem.get_stats()
            self.assertEqual(stats["current_size"], 5)
            self.assertEqual(stats["total_evicted"], 10)

    def test_factor_correlation_audit(self):
        """Verify correlation audit computation mandated by Gate Condition 5."""
        h = torch.randn(16)
        for t in range(50):
            # Dynamic state transition
            h = h + 0.1 * torch.randn(16)
            self.memory.observe(
                event_id=t,
                timestamp=float(t),
                embedding=torch.randn(32),
                temporal_state=h,
            )

        corrs = self.memory.compute_factor_correlations()
        self.assertIn("corr_surprise_causal", corrs)
        self.assertIn("corr_novelty_causal", corrs)
        self.assertIn("corr_surprise_novelty", corrs)
        self.assertGreaterEqual(corrs["sample_size"], 50)
        for k, v in corrs.items():
            if k != "sample_size":
                self.assertTrue(-1.0001 <= v <= 1.0001, f"{k} correlation out of bounds: {v}")


if __name__ == "__main__":
    unittest.main()
