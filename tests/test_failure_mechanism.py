import unittest
from benchmarks.failure_mechanism.candidate_attribution import run_candidate_attribution_experiment
from benchmarks.failure_mechanism.hop_attenuation import run_hop_attenuation_experiment
from benchmarks.failure_mechanism.crowding_decomposition import run_crowding_decomposition_experiment


class TestFailureMechanism(unittest.TestCase):
    def test_candidate_attribution_smoke(self):
        res = run_candidate_attribution_experiment(
            condition='delay_1000',
            seed=999,
            stream_length=300,
        )
        self.assertIn("root_in_cold", res)
        self.assertIn("root_raw_sim_rank", res)
        self.assertIn("root_score_rank", res)

    def test_hop_attenuation_smoke(self):
        res = run_hop_attenuation_experiment(
            chain_length=3,
            seed=999,
            stream_length=400,
        )
        self.assertIn("hop_profiles", res)
        self.assertEqual(len(res["hop_profiles"]), 2)  # A and B

    def test_crowding_decomposition_smoke(self):
        res = run_crowding_decomposition_experiment(
            distractor_type='type4_random',
            n_distractors=10,
            seed=999,
            stream_length=300,
        )
        self.assertIn("restoration_recall", res)
        self.assertIn("revision_precision", res)


if __name__ == '__main__':
    unittest.main()
