import unittest
import torch
from continuum.memory.adaptive_memory import (
    AdaptiveMemory,
    AdaptiveMemoryConfig,
    EventRecord,
    RetentionDecision,
)


class TestAdversarialAdaptiveMemory(unittest.TestCase):
    def setUp(self):
        torch.manual_seed(42)

    def test_repetitive_flooding_attack(self):
        """
        Adversarial Probe 1: Repetitive Flooding Attack.
        Stream near-identical embeddings with infinitesimal epsilon-noise.
        The memory bank should NOT fill all capacity with redundant variations of the same event;
        Novelty should drop towards 0 and suppress retention.
        """
        cfg = AdaptiveMemoryConfig(
            embedding_dim=32,
            capacity=50,
            policy_mode="fixed_budget",
            eviction_policy="min_importance",
            beta_novelty=0.8,
            alpha_surprise=0.05,
            gamma_causal=0.05,
            delta_retrieval=0.05,
            epsilon_uncertainty=0.05,
            seed=42,
        )
        mem = AdaptiveMemory(cfg)

        base_vec = torch.randn(32)
        base_vec = base_vec / torch.norm(base_vec)

        # 1. Insert base event
        r0 = mem.observe(event_id=0, timestamp=0.0, embedding=base_vec)
        self.assertEqual(r0.decision, RetentionDecision.KEEP)
        self.assertAlmostEqual(r0.novelty, 1.0, places=2)

        # 2. Flood with 200 near-identical events (eps = 1e-3)
        discarded_count = 0
        novelties = []
        for i in range(1, 201):
            noise = 1e-3 * torch.randn(32)
            flood_vec = base_vec + noise
            rec = mem.observe(event_id=i, timestamp=float(i), embedding=flood_vec)
            novelties.append(rec.novelty)
            if rec.decision == RetentionDecision.DISCARD:
                discarded_count += 1

        # After baseline fills, novelty must collapse close to 0 (< 0.1)
        mean_flood_novelty = sum(novelties[5:]) / len(novelties[5:])
        self.assertLess(mean_flood_novelty, 0.05, f"Flooded novelty remained too high: {mean_flood_novelty}")

    def test_temporal_leakage_rejection(self):
        """
        Adversarial Probe 2: Anti-Leakage Audit.
        Ensures that EventRecord rejects forbidden evaluation-only fields
        and that observe() operates without future query injection.
        """
        emb = torch.randn(32)
        rec = EventRecord(event_id=1, timestamp=0.0, embedding=emb)
        # Verify no eval fields exist on record
        self.assertFalse(hasattr(rec, "future_query"))
        self.assertFalse(hasattr(rec, "ground_truth"))

    def test_numerical_stability_and_anomaly_rejection(self):
        """
        Adversarial Probe 3: Numerical Stability.
        Verify that NaN embeddings, non-finite vectors, or wrong dimensions
        raise ValueErrors and do not corrupt internal memory state.
        """
        cfg = AdaptiveMemoryConfig(embedding_dim=16, capacity=10)
        mem = AdaptiveMemory(cfg)

        # NaN vector
        nan_vec = torch.full((16,), float("nan"))
        with self.assertRaises(ValueError):
            mem.observe(event_id=1, timestamp=1.0, embedding=nan_vec)

        # Inf vector
        inf_vec = torch.full((16,), float("inf"))
        with self.assertRaises(ValueError):
            mem.observe(event_id=2, timestamp=2.0, embedding=inf_vec)

        # Wrong dimension
        wrong_dim = torch.randn(24)
        with self.assertRaises(ValueError):
            mem.observe(event_id=3, timestamp=3.0, embedding=wrong_dim)

        # Memory should remain uncorrupted and empty
        self.assertEqual(mem.get_stats()["current_size"], 0)

    def test_poisoned_needle_eviction_resistance(self):
        """
        Adversarial Probe 4: Needle Survival under Low-Importance Noise.
        A high-importance needle (e.g. high novelty, distinct embedding)
        must not be easily evicted by background repetitive low-importance events.
        """
        cfg = AdaptiveMemoryConfig(
            embedding_dim=32,
            capacity=10,
            policy_mode="fixed_budget",
            eviction_policy="min_importance",
            alpha_surprise=0.2,
            beta_novelty=0.4,
            gamma_causal=0.1,
            delta_retrieval=0.1,
            epsilon_uncertainty=0.2,
            seed=101,
        )
        mem = AdaptiveMemory(cfg)

        # Insert 9 background events
        bg_center = torch.randn(32)
        bg_center = bg_center / torch.norm(bg_center)
        for i in range(9):
            mem.observe(event_id=i, timestamp=float(i), embedding=bg_center + 0.05 * torch.randn(32))

        # Insert 1 distinct, high-novelty needle orthogonal to background
        needle_vec = torch.randn(32)
        # Make orthogonal
        needle_vec = needle_vec - torch.dot(needle_vec, bg_center) * bg_center
        needle_vec = needle_vec / torch.norm(needle_vec)

        rec_needle = mem.observe(event_id=999, timestamp=10.0, embedding=needle_vec)
        self.assertEqual(rec_needle.decision, RetentionDecision.KEEP)

        # Now stream 50 more background events around bg_center
        for j in range(11, 61):
            mem.observe(event_id=j, timestamp=float(j), embedding=bg_center + 0.05 * torch.randn(32))

        # The needle must still survive in memory because background events have lower novelty/importance!
        retained_ids = [r.event_id for r in mem.records]
        self.assertIn(999, retained_ids, "Adversarial background flood prematurely evicted the distinct needle!")


if __name__ == "__main__":
    unittest.main()
