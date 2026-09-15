import unittest
import torch

from continuum import ContinuumEngine, ContinuumConfig, StreamStepResult, CausalMatch, __version__


class TestPublicAPI(unittest.TestCase):
    def test_version_and_imports(self):
        self.assertTrue(__version__.startswith("0.1.0"))

    def test_engine_lifecycle(self):
        engine = ContinuumEngine.create(
            embedding_dim=16,
            state_dim=16,
            hot_capacity=10,
            cold_capacity=20,
            seed=42,
        )

        # Stream 25 events
        for i in range(25):
            vec = [float(x) for x in range(16)]
            res = engine.step(vec, payload_ref=f"event_{i}")
            self.assertIsInstance(res, StreamStepResult)
            self.assertEqual(res.event_id, i)
            self.assertLessEqual(res.total_slots_used, 30)

        stats = engine.get_stats()
        self.assertEqual(stats["step_count"], 25)
        self.assertLessEqual(stats["total_slots"], 30)
        self.assertEqual(stats["max_slots"], 30)

        # Query
        query_vec = [1.0] * 16
        matches = engine.query(query_vec, top_k=3)
        self.assertIsInstance(matches, list)
        self.assertLessEqual(len(matches), 3)
        if matches:
            self.assertIsInstance(matches[0], CausalMatch)
            self.assertIn("sim", matches[0].components)

        # Reset
        engine.reset()
        self.assertEqual(engine.get_stats()["step_count"], 0)
        self.assertEqual(engine.get_stats()["total_slots"], 0)


if __name__ == "__main__":
    unittest.main()
