import unittest
from benchmarks.mechanism_isolation.m1_admission import run_m1_experiment
from benchmarks.mechanism_isolation.m2_retrieval import run_m2_experiment
from benchmarks.mechanism_isolation.m3_temporal import run_m3_experiment


class TestMechanismIsolation(unittest.TestCase):
    def test_m1_admission_smoke(self):
        res = run_m1_experiment(variant="M1-A_current", seed=999, stream_length=400)
        self.assertIn("root_recall", res)
        self.assertIn("intermediate_recall", res)
        self.assertIn("chain_recall", res)

    def test_m2_retrieval_smoke(self):
        res = run_m2_experiment(top_k_val=10, distractor_count=50, seed=999, stream_length=400)
        self.assertIn("root_in_top_k", res)
        self.assertIn("restoration_recall", res)

    def test_m3_temporal_smoke(self):
        res = run_m3_experiment(variant="M3-A_current", chain_length=3, seed=999, stream_length=400)
        self.assertIn("chain_nodes_audit", res)
        self.assertIn("root_restored", res)


if __name__ == "__main__":
    unittest.main()
