import unittest
import torch
from benchmarks.mechanism_separation.benchmark_mechanism_separation import (
    run_mission_2_9_5_experiment,
    NaiveDeltaColdMemory,
    PersistentDriftColdMemory,
    DiversifiedDynamicsColdMemory,
)


class TestMission295(unittest.TestCase):
    def test_p0_p1_smoke(self):
        res_p0 = run_mission_2_9_5_experiment("P0_naive_delta", seed=999, stream_length=400, n_regimes=3, n_transients=10, n_distractors=10)
        self.assertIn("csm", res_p0)
        self.assertIn("causal_retained", res_p0)

        res_p1 = run_mission_2_9_5_experiment("P1_persistent_drift", seed=999, stream_length=400, n_regimes=3, n_transients=10, n_distractors=10)
        self.assertIn("csm", res_p1)
        self.assertIn("regimes_in_cold", res_p1)

    def test_p2_p3_smoke(self):
        res_p2 = run_mission_2_9_5_experiment("P2_diversified_dynamics", seed=999, stream_length=400, n_regimes=3, n_transients=10, n_distractors=10)
        self.assertIn("csm", res_p2)
        self.assertTrue(res_p2["causal_retained"])

        res_p3 = run_mission_2_9_5_experiment("P3_two_stage_continuum", seed=999, stream_length=400, n_regimes=3, n_transients=10, n_distractors=10)
        self.assertIn("csm", res_p3)
        self.assertTrue(res_p3["causal_restored"])
        self.assertFalse(res_p3["regime_restored"])


if __name__ == "__main__":
    unittest.main()
