import unittest
import torch

from benchmarks.strong_baselines.strong_baselines import StrongBaseline_DeltaNet, StrongBaseline_GatedSSM


class TestStrongBaselines(unittest.TestCase):
    def test_deltanet_lifecycle(self):
        model = StrongBaseline_DeltaNet(emb_dim=16, key_dim=8, val_dim=8)
        for t in range(25):
            model.observe(t, float(t), torch.randn(16))
        self.assertEqual(model.get_memory_slots(), 0)
        self.assertEqual(model.query_causal(torch.randn(16)), [])

        # Read associative output
        out = model.read_associative(torch.randn(16))
        self.assertEqual(out.shape[0], 16)

        model.reset_state()
        self.assertEqual(torch.norm(model.S).item(), 0.0)

    def test_gated_ssm_lifecycle(self):
        model = StrongBaseline_GatedSSM(emb_dim=16, d_state=16)
        for t in range(25):
            model.observe(t, float(t), torch.randn(16))
        self.assertEqual(model.get_memory_slots(), 0)
        self.assertEqual(model.query_causal(torch.randn(16)), [])

        model.reset_state()
        self.assertEqual(torch.norm(model.h).item(), 0.0)


if __name__ == "__main__":
    unittest.main()
