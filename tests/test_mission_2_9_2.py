import unittest
from benchmarks.minimal_fix_isolation.exp_a_retention import run_exp_a_experiment
from benchmarks.minimal_fix_isolation.exp_b_temporal import run_exp_b_experiment
from benchmarks.minimal_fix_isolation.exp_c_admission import run_exp_c_experiment


class TestMission292(unittest.TestCase):
    def test_exp_a_smoke(self):
        res = run_exp_a_experiment(condition="A0_current_fifo", seed=999, stream_length=300, n_distractors=20)
        self.assertIn("restoration_recall", res)
        self.assertIn("false_revision_rate", res)

    def test_exp_b_smoke(self):
        res = run_exp_b_experiment(mode="hop_conditioned", chain_length=3, seed=999, stream_length=300)
        self.assertIn("mean_old_decoy_score", res)
        self.assertIn("root_score", res)

    def test_exp_c_smoke(self):
        res = run_exp_c_experiment(condition="C1_only_causal_intermediate", seed=999, stream_length=300)
        self.assertIn("intermediate_recall", res)
        self.assertIn("chain_recall", res)


if __name__ == "__main__":
    unittest.main()
