"""Frozen adversarial data cases for the TASK-001 benchmark adapter.

This module intentionally has no dependency on ``continuum.state``.  The
benchmark owner may import it to test an adapter, while its schema checks keep
the target outside contemporaneous features.
"""

from __future__ import annotations

from dataclasses import dataclass

import torch


@dataclass(frozen=True)
class TemporalGapCase:
    """A feature stream and labels that become available only after ``gap``."""

    features: torch.Tensor  # [B, T, 2]: signal at t and independent nuisance
    targets: torch.Tensor  # [B, T-gap]: signal from t, predicted at t + gap
    gap: int
    feature_schema: tuple[str, str] = ("signal_now", "nuisance_now")
    target_schema: str = "signal_delayed"


def make_temporal_gap_case(*, seed: int, batch_size: int = 4, steps: int = 24, gap: int = 3) -> TemporalGapCase:
    """Return a seeded delayed-copy task with no label feature at prediction time."""
    if batch_size <= 0 or steps <= gap or gap <= 0:
        raise ValueError("require batch_size > 0, gap > 0, and steps > gap")
    generator = torch.Generator().manual_seed(seed)
    signal = torch.randint(0, 2, (batch_size, steps), generator=generator, dtype=torch.int64).float() * 2 - 1
    nuisance = torch.randn((batch_size, steps), generator=generator)
    features = torch.stack((signal, nuisance), dim=-1)
    # Target position k is evaluated at event time k + gap; it is never a
    # feature at that same event time.
    targets = signal[:, : steps - gap].clone()
    return TemporalGapCase(features=features, targets=targets, gap=gap)


def assert_delayed_target_schema(case: TemporalGapCase) -> None:
    """Fail if a caller changes the fixture into a contemporaneous-label task."""
    if case.features.ndim != 3 or case.targets.ndim != 2:
        raise AssertionError("unexpected temporal-gap tensor ranks")
    batch, steps, width = case.features.shape
    if width != 2 or case.targets.shape != (batch, steps - case.gap):
        raise AssertionError("unexpected temporal-gap tensor shape")
    # At the target's evaluation time, both feature columns must differ from
    # the delayed target vector.  Fixed seed makes this a strong exact guard,
    # not a statistical claim about arbitrary data.
    evaluation_features = case.features[:, case.gap :, :]
    delayed_target = case.targets
    if torch.equal(evaluation_features[..., 0], delayed_target) or torch.equal(evaluation_features[..., 1], delayed_target):
        raise AssertionError("target leaked into a contemporaneous feature")
