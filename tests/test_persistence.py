import tempfile
import unittest
from pathlib import Path
import torch

from continuum import ContinuumEngine, ContinuumConfig


class TestPersistence(unittest.TestCase):
    def test_save_and_load_roundtrip(self):
        cfg = ContinuumConfig(embedding_dim=16, state_dim=16, hot_capacity=15, cold_capacity=30, seed=101)
        engine1 = ContinuumEngine(cfg)

        torch.manual_seed(101)
        for t in range(50):
            engine1.step(torch.randn(16), payload_ref=f"event_{t}")

        stats1 = engine1.get_stats()
        query_vec = torch.randn(16)
        matches1 = engine1.query(query_vec, top_k=3)

        with tempfile.TemporaryDirectory() as tmpdir:
            save_path = Path(tmpdir) / "continuum_checkpoint.pt"
            engine1.save(save_path)
            self.assertTrue(save_path.exists())

            # Load into fresh engine
            engine2 = ContinuumEngine.load(save_path)
            stats2 = engine2.get_stats()

            self.assertEqual(stats1["step_count"], stats2["step_count"])
            self.assertEqual(stats1["total_slots"], stats2["total_slots"])
            self.assertEqual(stats1["hot_slots"], stats2["hot_slots"])
            self.assertEqual(stats1["cold_slots"], stats2["cold_slots"])

            # Verify identical queries
            matches2 = engine2.query(query_vec, top_k=3)
            self.assertEqual(len(matches1), len(matches2))
            for m1, m2 in zip(matches1, matches2):
                self.assertEqual(m1.event_id, m2.event_id)
                self.assertAlmostEqual(m1.revision_score, m2.revision_score, places=4)

    def test_rust_native_save_and_load_roundtrip(self):
        from continuum.native import RustNativeEngine, is_native_available
        if not is_native_available():
            self.skipTest("Rust native core not compiled")

        cfg = ContinuumConfig(embedding_dim=16, state_dim=16, hot_capacity=15, cold_capacity=30)
        engine1 = RustNativeEngine(cfg)

        torch.manual_seed(202)
        for t in range(50):
            engine1.step(torch.randn(16), timestamp=float(t), payload_ref=f"native_event_{t}")

        stats1 = engine1.get_stats()
        query_vec = torch.randn(16)
        matches1 = engine1.query(query_vec, top_k=3)

        with tempfile.TemporaryDirectory() as tmpdir:
            save_path = Path(tmpdir) / "continuum_native_checkpoint.bin"
            engine1.save(save_path)
            self.assertTrue(save_path.exists())

            # Load into fresh native engine
            engine2 = RustNativeEngine.load(save_path)
            stats2 = engine2.get_stats()

            self.assertEqual(stats1["step_count"], stats2["step_count"])
            self.assertEqual(stats1["total_slots"], stats2["total_slots"])
            self.assertEqual(stats1["hot_slots"], stats2["hot_slots"])
            self.assertEqual(stats1["cold_slots"], stats2["cold_slots"])

            # Verify identical queries
            matches2 = engine2.query(query_vec, top_k=3)
            self.assertEqual(len(matches1), len(matches2))
            for m1, m2 in zip(matches1, matches2):
                self.assertEqual(m1.event_id, m2.event_id)
                self.assertAlmostEqual(m1.revision_score, m2.revision_score, places=4)


if __name__ == "__main__":
    unittest.main()
