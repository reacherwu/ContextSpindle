import unittest
import torch
from benchmarks.causal_discrimination.benchmark_causal_discrimination import (
    run_mission_2_9_4_experiment,
    UniquenessBiasedColdMemory,
    RedundancyFIFOColdMemory,
    DynamicalTrajectoryColdMemory,
)


class TestMission294(unittest.TestCase):
    def test_m0_m1_smoke(self):
        res_m0 = run_mission_2_9_4_experiment("M0_fifo", seed=999, stream_length=500, n_traps=10, n_distractors=10)
        self.assertIn("cdr", res_m0)
        self.assertIn("causal_restored", res_m0)

        res_m1 = run_mission_2_9_4_experiment("M1_uniqueness_biased", seed=999, stream_length=500, n_traps=10, n_distractors=10)
        self.assertIn("cdr", res_m1)
        self.assertIn("traps_in_cold", res_m1)

    def test_m2_m3_smoke(self):
        res_m2 = run_mission_2_9_4_experiment("M2_redundancy_fifo", seed=999, stream_length=500, n_traps=10, n_distractors=10)
        self.assertIn("cdr", res_m2)
        self.assertTrue(res_m2["salient_in_cold"] or res_m2["salient_in_hot"])

        res_m3 = run_mission_2_9_4_experiment("M3_dynamical_trajectory", seed=999, stream_length=500, n_traps=10, n_distractors=10)
        self.assertIn("cdr", res_m3)
        self.assertIn("restored_ids", res_m3)


if __name__ == "__main__":
    unittest.main()
