"""Engineering-owned direct contract tests for RFC-0001."""

from __future__ import annotations

import pytest
import torch

from continuum import TemporalState, TemporalStateConfig


def test_parameter_shapes_count_and_serialized_configuration() -> None:
    config = TemporalStateConfig(3, 2, gate_bias_init=0.75)
    model = TemporalState(config)
    assert model.W_g.shape == model.W_c.shape == (2, 3)
    assert model.U_g.shape == model.U_c.shape == (2, 2)
    assert model.b_g.shape == model.b_c.shape == (2,)
    assert sum(parameter.numel() for parameter in model.parameters()) == 2 * 2 * 3 + 2 * 2 * 2 + 2 * 2
    torch.testing.assert_close(model.b_g, torch.full((2,), 0.75))
    assert model.state_dict()['_extra_state'] == {
        'input_size': 3, 'hidden_size': 2, 'candidate_activation': 'tanh',
        'initial_state': 'zeros', 'gate_bias_init': 0.75,
    }


@pytest.mark.parametrize("config", [
    TemporalStateConfig(0, 1), TemporalStateConfig(1, -1),
    TemporalStateConfig(1, 1, candidate_activation="relu"),  # type: ignore[arg-type]
    TemporalStateConfig(1, 1, initial_state="learned"),  # type: ignore[arg-type]
    TemporalStateConfig(1, 1, gate_bias_init=float("nan")),
])
def test_invalid_configuration_fails(config: TemporalStateConfig) -> None:
    with pytest.raises(ValueError):
        TemporalState(config)


def test_hand_computed_step_matches_equations() -> None:
    model = TemporalState(TemporalStateConfig(1, 1))
    with torch.no_grad():
        model.W_g.fill_(0.5); model.U_g.fill_(0.25); model.b_g.fill_(-0.1)
        model.W_c.fill_(0.8); model.U_c.fill_(-0.2); model.b_c.fill_(0.3)
    x, previous = torch.tensor([[0.4]]), torch.tensor([[-0.6]])
    result = model.step(x, previous)
    gate = torch.sigmoid(torch.tensor([[0.5 * 0.4 + 0.25 * -0.6 - 0.1]]))
    candidate = torch.tanh(torch.tensor([[0.8 * 0.4 + -0.2 * -0.6 + 0.3]]))
    torch.testing.assert_close(result.gate, gate)
    torch.testing.assert_close(result.candidate, candidate)
    torch.testing.assert_close(result.state, (1 - gate) * previous + gate * candidate)


def test_sequence_step_equivalence_empty_sequence_and_autograd() -> None:
    model = TemporalState(TemporalStateConfig(2, 3))
    x = torch.randn(2, 4, 2, requires_grad=True)
    initial = torch.randn(2, 3)
    states, final = model.forward_sequence(x, initial)
    current, expected = initial, []
    for index in range(x.shape[1]):
        current = model.step(x[:, index], current).state
        expected.append(current)
    torch.testing.assert_close(states, torch.stack(expected, dim=1), rtol=0, atol=0)
    torch.testing.assert_close(final, current, rtol=0, atol=0)
    empty, empty_final = model.forward_sequence(torch.empty(2, 0, 2), initial)
    assert empty.shape == (2, 0, 3)
    torch.testing.assert_close(empty_final, initial)
    (states.sum() + final.sum()).backward()
    assert x.grad is not None and all(parameter.grad is not None for parameter in model.parameters())


def test_initial_state_is_fresh_and_preserves_requested_dtype() -> None:
    model = TemporalState(TemporalStateConfig(1, 2))
    first, second = model.initial_state(3, dtype=torch.float64), model.initial_state(3, dtype=torch.float64)
    assert first.shape == (3, 2) and first.dtype is torch.float64
    first[0, 0] = 1
    assert second[0, 0].item() == 0


@pytest.mark.parametrize("value", [torch.ones(1, 1, dtype=torch.int64), torch.ones(1, 1, dtype=torch.float64)])
def test_step_rejects_wrong_dtype(value: torch.Tensor) -> None:
    model = TemporalState(TemporalStateConfig(1, 1))
    with pytest.raises(ValueError):
        model.step(value, model.initial_state(1))
