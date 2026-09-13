"""Adversarial contract probes for RFC-0001 / TASK-001.

These tests deliberately use public ``TemporalState`` APIs only.  They are
not unit tests for a particular implementation: a conforming implementation
must pass them without adding any persistence or benchmark-specific branch.
"""

from __future__ import annotations

import pytest
import torch

from continuum.state.temporal_state import TemporalState, TemporalStateConfig


@pytest.fixture
def model() -> TemporalState:
    """A deterministic, asymmetric recurrence that makes ordering observable."""
    state = TemporalState(TemporalStateConfig(input_size=1, hidden_size=1))
    with torch.no_grad():
        state.W_g.fill_(1.0)
        state.U_g.fill_(0.0)
        state.b_g.fill_(0.0)
        state.W_c.fill_(1.0)
        state.U_c.fill_(0.35)
        state.b_c.fill_(0.0)
    return state


def _sequence(model: TemporalState, values: list[float]) -> torch.Tensor:
    return torch.tensor(values, dtype=next(model.parameters()).dtype).view(1, -1, 1)


def test_order_probe_rejects_pooling_sorting_or_order_erasure(model: TemporalState) -> None:
    """Two permutations with the same values must not collapse to one result."""
    states_forward, final_forward = model.forward_sequence(_sequence(model, [-0.8, 0.45]))
    states_reversed, final_reversed = model.forward_sequence(_sequence(model, [0.45, -0.8]))

    assert not torch.allclose(final_forward, final_reversed, atol=1e-6, rtol=1e-6)
    assert not torch.allclose(states_forward[:, -1], states_reversed[:, -1], atol=1e-6, rtol=1e-6)


def test_future_suffix_cannot_change_prefix_states(model: TemporalState) -> None:
    """A suffix mutation exposes bidirectional scans and sequence-level leakage."""
    prefix = [-0.3, 0.7, 0.1]
    original = _sequence(model, prefix + [-0.5, 0.2])
    changed_suffix = _sequence(model, prefix + [0.95, -0.9])

    original_states, _ = model.forward_sequence(original)
    changed_states, _ = model.forward_sequence(changed_suffix)

    torch.testing.assert_close(original_states[:, : len(prefix)], changed_states[:, : len(prefix)], rtol=0, atol=0)


def test_batch_perturbation_cannot_cross_talk(model: TemporalState) -> None:
    """One row's changed events and state cannot affect untouched rows."""
    x = torch.tensor(
        [[[-0.4], [0.3], [0.1]], [[0.2], [-0.2], [0.6]]], dtype=torch.float32
    )
    initial = torch.tensor([[0.1], [-0.15]], dtype=torch.float32)
    mutated_x = x.clone()
    mutated_initial = initial.clone()
    mutated_x[1] = torch.tensor([[0.9], [0.9], [0.9]])
    mutated_initial[1] = 0.8

    states, final_state = model.forward_sequence(x, initial)
    mutated_states, mutated_final = model.forward_sequence(mutated_x, mutated_initial)

    torch.testing.assert_close(states[0], mutated_states[0], rtol=0, atol=0)
    torch.testing.assert_close(final_state[0], mutated_final[0], rtol=0, atol=0)


def test_interleaved_caller_owned_streams_do_not_contaminate_each_other(model: TemporalState) -> None:
    """The module must not retain a hidden mutable stream state between calls."""
    a = [-0.6, 0.4, 0.1]
    b = [0.2, -0.7, 0.8]
    state_a = model.initial_state(1)
    state_b = model.initial_state(1)
    for x_a, x_b in zip(a, b, strict=True):
        state_a = model.step(_sequence(model, [x_a])[:, 0], state_a).state
        state_b = model.step(_sequence(model, [x_b])[:, 0], state_b).state

    _, expected_a = model.forward_sequence(_sequence(model, a))
    _, expected_b = model.forward_sequence(_sequence(model, b))
    torch.testing.assert_close(state_a, expected_a, rtol=0, atol=0)
    torch.testing.assert_close(state_b, expected_b, rtol=0, atol=0)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_input_and_state_fail_at_api_boundary(model: TemporalState, bad: float) -> None:
    x = torch.tensor([[bad]], dtype=torch.float32)
    state = model.initial_state(1)
    with pytest.raises((ValueError, RuntimeError)):
        model.step(x, state)
    with pytest.raises((ValueError, RuntimeError)):
        model.step(torch.zeros_like(x), torch.tensor([[bad]], dtype=torch.float32))
    with pytest.raises((ValueError, RuntimeError)):
        model.forward_sequence(x.unsqueeze(1))


def test_extreme_finite_values_do_not_create_nonfinite_returned_state(model: TemporalState) -> None:
    """Finite extremes may saturate nonlinearities, but outputs cannot poison state."""
    largest = torch.finfo(torch.float32).max
    x = torch.tensor([[[largest], [-largest], [largest]]], dtype=torch.float32)
    states, final_state = model.forward_sequence(x)
    assert torch.isfinite(states).all()
    assert torch.isfinite(final_state).all()


def test_gate_saturation_exposes_retain_and_overwrite_regimes(model: TemporalState) -> None:
    """Near-zero gates retain; near-one gates overwrite with the candidate."""
    prior = torch.tensor([[0.6]], dtype=torch.float32)
    x = torch.zeros((1, 1), dtype=torch.float32)
    with torch.no_grad():
        model.W_g.zero_()
        model.U_g.zero_()
        model.W_c.zero_()
        model.U_c.zero_()
        model.b_c.fill_(0.4)

        model.b_g.fill_(-20.0)
    retained = model.step(x, prior)
    assert retained.gate.item() < 1e-7
    torch.testing.assert_close(retained.state, prior, atol=1e-6, rtol=0)

    with torch.no_grad():
        model.b_g.fill_(20.0)
    overwritten = model.step(x, prior)
    assert overwritten.gate.item() > 1.0 - 1e-7
    torch.testing.assert_close(overwritten.state, overwritten.candidate, atol=1e-6, rtol=0)


@pytest.mark.parametrize("dtype", [torch.float32, torch.float64])
def test_bounded_state_holds_over_long_finite_stream(model: TemporalState, dtype: torch.dtype) -> None:
    """The claimed convex-combination bound must survive a long adversarial stream."""
    model = model.to(dtype=dtype)
    generator = torch.Generator().manual_seed(1009)
    x = torch.randn((3, 1024, 1), generator=generator, dtype=dtype) * 100.0
    initial = torch.tensor([[1.75], [-1.5], [0.25]], dtype=dtype)
    states, final_state = model.forward_sequence(x, initial)
    bound = max(initial.abs().max().item(), 1.0)
    tolerance = 2e-6 if dtype is torch.float32 else 2e-12
    assert states.abs().max().item() <= bound + tolerance
    assert final_state.abs().max().item() <= bound + tolerance
