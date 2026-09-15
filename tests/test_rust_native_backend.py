import unittest
import torch
from continuum import ContinuumConfig, ContinuumEngine
from continuum.native import is_native_available, RustNativeEngine


class TestRustNativeBackend(unittest.TestCase):
    def setUp(self):
        self.assertTrue(is_native_available(), "Rust native cdylib should be compiled and available")

    def test_direct_rust_engine(self):
        cfg = ContinuumConfig(
            embedding_dim=8,
            state_dim=8,
            hot_capacity=10,
            cold_capacity=20,
            causal_exempt_threshold=0.30,
        )
        engine = RustNativeEngine(cfg)

        # Ingest 100 events
        for t in range(100):
            v = torch.zeros(8)
            v[t % 8] = 1.0
            res = engine.step(v, timestamp=float(t), payload_ref=f"rust_{t}")
            self.assertLessEqual(res.total_slots_used, 30)

        stats = engine.get_stats()
        self.assertEqual(stats["backend"], "rust_native")
        self.assertEqual(stats["total_slots"], 30)
        self.assertEqual(stats["step_count"], 100)

        # Query
        query = torch.zeros(8)
        query[0] = 1.0
        matches = engine.query(query, top_k=5)
        self.assertEqual(len(matches), 5)
        self.assertGreater(matches[0].revision_score, 0.0)

    def test_facade_backend_dispatch(self):
        cfg = ContinuumConfig(
            embedding_dim=4,
            state_dim=4,
            hot_capacity=5,
            cold_capacity=10,
            backend="rust",
        )
        engine = ContinuumEngine(cfg)
        self.assertIsInstance(engine, RustNativeEngine)

        for t in range(25):
            res = engine.step([0.1, 0.2, 0.3, 0.4], timestamp=float(t))
            self.assertLessEqual(res.total_slots_used, 15)

        stats = engine.get_stats()
        self.assertEqual(stats["backend"], "rust_native")


if __name__ == "__main__":
    unittest.main()
