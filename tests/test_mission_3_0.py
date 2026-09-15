import unittest
import torch
from benchmarks.mission_3_0.baselines import (
    B1_RecurrentStateOnly,
    B2_FixedBudgetLRU,
    B3_SlidingWindowAttention,
    B4_UnboundedArchive,
)
from benchmarks.mission_3_0.acm_architecture import ACMArchitecture
from benchmarks.mission_3_0.benchmark_e2e_validation import (
    run_causal_capability_experiment,
    run_efficiency_scaling_experiment,
)


class TestMission30(unittest.TestCase):
    def test_baselines_smoke(self):
        emb = torch.randn(32)
        b1 = B1_RecurrentStateOnly(emb_dim=32, state_dim=32)
        h = b1.step(emb)
        self.assertEqual(h.shape[0], 32)
        self.assertEqual(b1.get_memory_slots(), 0)

        b2 = B2_FixedBudgetLRU(capacity=10, emb_dim=32)
        for i in range(15):
            b2.observe(i, float(i), torch.randn(32))
        self.assertEqual(b2.get_memory_slots(), 10)
        ret_b2 = b2.query_causal(emb, top_k=3)
        self.assertEqual(len(ret_b2), 3)

        b3 = B3_SlidingWindowAttention(window_size=10, emb_dim=32)
        for i in range(15):
            b3.observe(i, float(i), torch.randn(32))
        self.assertEqual(b3.get_memory_slots(), 10)
        ret_b3 = b3.query_causal(emb, top_k=3)
        self.assertEqual(len(ret_b3), 3)

        b4 = B4_UnboundedArchive(emb_dim=32)
        for i in range(15):
            b4.observe(i, float(i), torch.randn(32))
        self.assertEqual(b4.get_memory_slots(), 15)

    def test_acm_architecture_smoke(self):
        acm = ACMArchitecture(emb_dim=32, state_dim=32, k_hot=10, k_cold=20, seed=999)
        for i in range(35):
            acm.observe(i, float(i), torch.randn(32))
        self.assertLessEqual(acm.get_memory_slots(), 30)
        ret_acm = acm.query_causal(torch.randn(32), top_k=2)
        self.assertIsInstance(ret_acm, list)

    def test_e2e_experiments_smoke(self):
        res_causal = run_causal_capability_experiment("ACM_architecture", seed=999, stream_length=300)
        self.assertIn("causal_retrieved", res_causal)

        res_eff = run_efficiency_scaling_experiment("ACM_architecture", stream_length=100, seed=999)
        self.assertIn("slots_used", res_eff)


if __name__ == "__main__":
    unittest.main()
