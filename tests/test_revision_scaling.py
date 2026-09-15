from __future__ import annotations

import unittest
from benchmarks.revision_scaling.delay_scaling import run_delay_experiment
from benchmarks.revision_scaling.chain_length_scaling import run_chain_experiment
from benchmarks.revision_scaling.distractor_scaling import run_distractor_experiment
from benchmarks.revision_scaling.budget_scaling import run_budget_experiment
from benchmarks.revision_scaling.revision_ablation import run_ablation_experiment


class TestRevisionScaling(unittest.TestCase):
    def test_delay_scaling_smoke(self):
        res = run_delay_experiment(delta_t=100, seed=101, emb_dim=16, state_dim=16, k_hot=50, k_cold=100)
        self.assertIn("top1_accuracy", res)
        self.assertIn("restoration_recall", res)

    def test_chain_length_smoke(self):
        res = run_chain_experiment(chain_length=2, seed=101, emb_dim=16, state_dim=16, stream_length=500)
        self.assertIn("chain_length", res)
        self.assertEqual(res["chain_length"], 2)

    def test_distractor_scaling_smoke(self):
        res = run_distractor_experiment(n_distractors=5, seed=101, emb_dim=16, state_dim=16, stream_length=500)
        self.assertIn("false_revision_rate", res)

    def test_budget_scaling_smoke(self):
        res = run_budget_experiment(k_hot=50, ratio=1.0, seed=101, emb_dim=16, state_dim=16, stream_length=500)
        self.assertIn("efficiency", res)
        self.assertEqual(res["k_total"], 100)

    def test_revision_ablation_smoke(self):
        res = run_ablation_experiment(
            config_name="Test_Full",
            weights=(0.4, 0.3, 0.2, 0.1),
            theta_trigger=0.45,
            theta_restore=0.25,
            seed=101,
            emb_dim=16,
            state_dim=16,
            stream_length=500,
        )
        self.assertIn("revision_precision", res)


if __name__ == "__main__":
    unittest.main()
