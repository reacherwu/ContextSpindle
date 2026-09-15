import unittest
import torch

from continuum import ContinuumEngine, ContinuumConfig


class TestIntegrationV01(unittest.TestCase):
    def test_long_stream_bounded_memory(self):
        """Verify memory is strictly bounded and does not leak over 2000 steps."""
        config = ContinuumConfig(
            embedding_dim=16,
            state_dim=16,
            hot_capacity=40,
            cold_capacity=80,
            seed=101,
        )
        engine = ContinuumEngine(config)
        max_slots = config.hot_capacity + config.cold_capacity  # 120

        torch.manual_seed(101)
        for t in range(2000):
            x_t = torch.randn(16)
            res = engine.step(x_t)
            # Must never exceed max slots
            self.assertLessEqual(res.total_slots_used, max_slots)

        stats = engine.get_stats()
        self.assertEqual(stats["step_count"], 2000)
        self.assertLessEqual(stats["total_slots"], max_slots)
        self.assertAlmostEqual(stats["total_slots"], max_slots, delta=5)

    def test_causal_query_component_integrity(self):
        """Verify causal matches contain valid, finite components."""
        engine = ContinuumEngine.create(embedding_dim=16, state_dim=16, hot_capacity=20, cold_capacity=40)
        for t in range(100):
            engine.step(torch.randn(16))

        matches = engine.query(torch.randn(16), top_k=5)
        self.assertGreater(len(matches), 0)
        for m in matches:
            self.assertIn("sim", m.components)
            self.assertIn("state_compat", m.components)
            self.assertIn("temporal_compat", m.components)
            self.assertIn("provenance_compat", m.components)
            self.assertTrue(0.0 <= m.components["sim"] <= 1.0)
            self.assertTrue(0.0 <= m.components["state_compat"] <= 1.0)
            self.assertTrue(0.0 <= m.components["temporal_compat"] <= 1.0)

    def test_reproducibility_across_instances(self):
        """Verify identical streams with same seed produce identical state and results."""
        cfg = ContinuumConfig(embedding_dim=8, state_dim=8, hot_capacity=10, cold_capacity=20, seed=777)
        
        torch.manual_seed(777)
        engine1 = ContinuumEngine(cfg)
        
        torch.manual_seed(777)
        engine2 = ContinuumEngine(cfg)

        torch.manual_seed(777)
        stream_data = [torch.randn(8) for _ in range(50)]

        for vec in stream_data:
            r1 = engine1.step(vec)
            r2 = engine2.step(vec)
            self.assertEqual(r1.decision, r2.decision)
            self.assertAlmostEqual(r1.importance, r2.importance, places=5)
            self.assertAlmostEqual(r1.state_norm, r2.state_norm, places=5)


if __name__ == "__main__":
    unittest.main()
