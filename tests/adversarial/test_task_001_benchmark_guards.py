"""Independent fixture checks for TASK-001 benchmark leakage and shift probes."""

from __future__ import annotations

import torch

from experiments.adversarial.task_001_cases import (
    TemporalGapCase,
    assert_delayed_target_schema,
    make_temporal_gap_case,
)


def test_delayed_copy_fixture_has_no_contemporaneous_target_leak() -> None:
    case = make_temporal_gap_case(seed=71, batch_size=8, steps=32, gap=5)
    assert_delayed_target_schema(case)
    assert case.feature_schema == ("signal_now", "nuisance_now")
    assert case.target_schema == "signal_delayed"


def test_schema_guard_rejects_an_explicit_label_feature() -> None:
    case = make_temporal_gap_case(seed=71, batch_size=8, steps=32, gap=5)
    leaked = case.features.clone()
    leaked[:, case.gap :, 0] = case.targets
    leaked_case = TemporalGapCase(features=leaked, targets=case.targets, gap=case.gap)
    try:
        assert_delayed_target_schema(leaked_case)
    except AssertionError as error:
        assert "leaked" in str(error)
    else:
        raise AssertionError("schema guard accepted a contemporaneous target")


def test_distribution_shift_fixture_changes_gap_and_nuisance_scale_without_changing_schema() -> None:
    """Benchmark owners must report these OOD slices separately from aggregate IID."""
    iid = make_temporal_gap_case(seed=71, batch_size=8, steps=32, gap=3)
    shifted_gap = make_temporal_gap_case(seed=72, batch_size=8, steps=32, gap=9)
    shifted_noise = make_temporal_gap_case(seed=73, batch_size=8, steps=32, gap=3)
    shifted_noise.features[..., 1].mul_(25.0)
    for case in (iid, shifted_gap, shifted_noise):
        assert_delayed_target_schema(case)
    assert shifted_gap.gap > iid.gap
    assert torch.std(shifted_noise.features[..., 1]) > torch.std(iid.features[..., 1])
