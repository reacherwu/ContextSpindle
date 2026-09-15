import unittest
from benchmarks.recency_trap.benchmark_recency_trap import (
    run_recency_trap_experiment,
    R0Engine,
    R1Engine,
    R2Engine,
    R3Engine,
)


class TestMission296(unittest.TestCase):
    def test_r0_r1_smoke(self):
        res_r0 = run_recency_trap_experiment("R0_current_decay", "dt2900", seed=999, stream_length=400, n_distractors=5)
        self.assertIn("a_restored", res_r0)
        self.assertIn("score_A", res_r0)
        self.assertIn("sim", res_r0["score_A"])

        res_r1 = run_recency_trap_experiment("R1_no_temporal", "dt2900", seed=999, stream_length=400, n_distractors=5)
        self.assertIn("a_restored", res_r1)
        # R1 temporal_compat should be 1.0 for all scored candidates
        if res_r1["score_A"]["total"] > 0:
            self.assertAlmostEqual(res_r1["score_A"]["temporal_compat"], 1.0, places=5)

    def test_r2_r3_smoke(self):
        res_r2 = run_recency_trap_experiment("R2_weak_decay", "dt2900", seed=999, stream_length=400, n_distractors=5)
        self.assertIn("a_restored", res_r2)

        res_r3 = run_recency_trap_experiment("R3_csm_gated", "dt2900", seed=999, stream_length=400, n_distractors=5)
        self.assertIn("a_restored", res_r3)
        self.assertIn("score_F", res_r3)


if __name__ == "__main__":
    unittest.main()
