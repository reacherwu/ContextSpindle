import unittest
from benchmarks.mission_2_9_3.benchmark_mission_2_9_3 import (
    run_mission_2_9_3_experiment,
    RedundancyFIFOEvictionColdMemory,
    OnlineDedupMergeColdMemory,
    DynamicValueColdMemory,
)
import torch


class TestMission293(unittest.TestCase):
    def test_c0_c1_c2_smoke(self):
        res_c0 = run_mission_2_9_3_experiment("C0_current_fifo", seed=999, stream_length=500, n_distractors=50)
        self.assertIn("restoration_recall", res_c0)

        res_c1 = run_mission_2_9_3_experiment("C1_oracle_protected", seed=999, stream_length=500, n_distractors=50)
        self.assertIn("restoration_recall", res_c1)
        self.assertTrue(res_c1["root_in_cold"])

        res_c2 = run_mission_2_9_3_experiment("C2_online_redundancy_fifo", seed=999, stream_length=500, n_distractors=50)
        self.assertIn("restoration_recall", res_c2)
        self.assertTrue(res_c2["root_in_cold"])

    def test_c3_c4_smoke(self):
        res_c3 = run_mission_2_9_3_experiment("C3_online_dedup_merge", seed=999, stream_length=500, n_distractors=50)
        self.assertIn("restoration_recall", res_c3)
        self.assertTrue(res_c3["root_in_cold"])

        res_c4 = run_mission_2_9_3_experiment("C4_dynamic_value", seed=999, stream_length=500, n_distractors=50)
        self.assertIn("restoration_recall", res_c4)
        self.assertTrue(res_c4["root_in_cold"])


if __name__ == "__main__":
    unittest.main()
