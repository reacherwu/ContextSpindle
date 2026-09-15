import unittest
from benchmarks.bounded_retention.benchmark_bounded_retention import (
    run_bounded_retention_experiment,
    UnifiedDynamicMemory,
)


class TestMission297(unittest.TestCase):
    def test_c0_c1_smoke(self):
        res_c0 = run_bounded_retention_experiment("C0_baseline", seed=999, stream_length=400, total_budget=200)
        self.assertIn("early_retained", res_c0)
        self.assertIn("total_slots_used", res_c0)

        res_c1 = run_bounded_retention_experiment("C1_cold_bypass", seed=999, stream_length=400, total_budget=200)
        self.assertIn("early_retained", res_c1)
        self.assertIn("both_retained", res_c1)

    def test_c3_unified_smoke(self):
        res_c3 = run_bounded_retention_experiment("C3_unified_dynamic", seed=999, stream_length=400, total_budget=200)
        self.assertIn("causal_restored", res_c3)
        self.assertLessEqual(res_c3["total_slots_used"], 200)


if __name__ == "__main__":
    unittest.main()
