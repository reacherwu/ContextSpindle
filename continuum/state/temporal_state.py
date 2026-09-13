"""The RFC-0001 bounded gated temporal-state recurrence.

``TemporalState`` owns only its six trainable tensors.  Stream lifecycle is
always caller-owned: callers pass a state to :meth:`step` and retain the state
returned by it.  In particular, the module has no mutable per-stream cache.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from numbers import Real
from typing import Literal

import torch
from torch import Tensor, nn
from torch.nn import functional as F


@dataclass(frozen=True)
class TemporalStateConfig:
    """Serializable configuration for :class:`TemporalState`."""

    input_size: int
    hidden_size: int
    candidate_activation: Literal["tanh"] = "tanh"
    initial_state: Literal["zeros"] = "zeros"
    gate_bias_init: float = 0.0


@dataclass
class TemporalStateStep:
    """The state and diagnostics returned by one recurrence transition."""

    state: Tensor
    gate: Tensor
    candidate: Tensor


class TemporalState(nn.Module):
    """A single bounded gated state with the RFC-0001 recurrence.

    Finite input and state tensors are required at every public transition.
    In the exceptional case where a finite floating-point affine calculation
    overflows, its preactivation is saturated before the sigmoid/tanh.  This
    preserves finite public diagnostics and state while leaving all ordinary,
    non-overflowing recurrence calculations untouched.
    """

    def __init__(self, config: TemporalStateConfig) -> None:
        super().__init__()
        self._validate_config(config)
        self.config = config

        d, h = config.input_size, config.hidden_size
        self.W_g = nn.Parameter(torch.empty(h, d))
        self.W_c = nn.Parameter(torch.empty(h, d))
        self.U_g = nn.Parameter(torch.empty(h, h))
        self.U_c = nn.Parameter(torch.empty(h, h))
        self.b_g = nn.Parameter(torch.empty(h))
        self.b_c = nn.Parameter(torch.empty(h))
        self.reset_parameters()

    @staticmethod
    def _validate_config(config: TemporalStateConfig) -> None:
        if not isinstance(config, TemporalStateConfig):
            raise ValueError("config must be a TemporalStateConfig")
        for name in ("input_size", "hidden_size"):
            value = getattr(config, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive Python integer")
        if config.candidate_activation != "tanh":
            raise ValueError("candidate_activation must be 'tanh'")
        if config.initial_state != "zeros":
            raise ValueError("initial_state must be 'zeros'")
        if isinstance(config.gate_bias_init, bool) or not isinstance(config.gate_bias_init, Real):
            raise ValueError("gate_bias_init must be a finite real number")
        if not math.isfinite(float(config.gate_bias_init)):
            raise ValueError("gate_bias_init must be a finite real number")

    def reset_parameters(self) -> None:
        """Use standard PyTorch Kaiming-uniform weights and zero candidate bias."""
        nn.init.kaiming_uniform_(self.W_g, a=math.sqrt(5))
        nn.init.kaiming_uniform_(self.W_c, a=math.sqrt(5))
        nn.init.kaiming_uniform_(self.U_g, a=math.sqrt(5))
        nn.init.kaiming_uniform_(self.U_c, a=math.sqrt(5))
        nn.init.constant_(self.b_g, float(self.config.gate_bias_init))
        nn.init.zeros_(self.b_c)

    def get_extra_state(self) -> dict[str, object]:
        """Store the dataclass fields in ``state_dict`` for reproducibility."""
        return asdict(self.config)

    def set_extra_state(self, state: object) -> None:
        """Validate serialized configuration without mutating module topology."""
        if not isinstance(state, dict):
            raise ValueError("serialized TemporalState configuration must be a dictionary")
        try:
            restored = TemporalStateConfig(**state)
        except (TypeError, ValueError) as error:
            raise ValueError("invalid serialized TemporalState configuration") from error
        self._validate_config(restored)
        if restored != self.config:
            raise ValueError("serialized configuration does not match this TemporalState")

    @property
    def _parameter(self) -> nn.Parameter:
        return self.W_g

    @staticmethod
    def _is_floating_dtype(dtype: object) -> bool:
        return isinstance(dtype, torch.dtype) and dtype.is_floating_point

    @staticmethod
    def _validate_batch_size(batch_size: int) -> None:
        if type(batch_size) is not int or batch_size <= 0:
            raise ValueError("batch_size must be a positive Python integer")

    @staticmethod
    def _require_finite_tensor(value: object, name: str, rank: int) -> Tensor:
        if not isinstance(value, Tensor):
            raise ValueError(f"{name} must be a torch.Tensor")
        if value.ndim != rank:
            raise ValueError(f"{name} must have rank {rank}")
        if not value.dtype.is_floating_point:
            raise ValueError(f"{name} must have a floating-point dtype")
        if not bool(torch.isfinite(value).all()):
            raise ValueError(f"{name} must contain only finite values")
        return value

    def _validate_device_dtype(self, value: Tensor, name: str) -> None:
        parameter = self._parameter
        if value.device != parameter.device:
            raise ValueError(f"{name} device must match module parameters")
        if value.dtype != parameter.dtype:
            raise ValueError(f"{name} dtype must match module parameters")

    def initial_state(self, batch_size: int, *, device=None, dtype=None) -> Tensor:
        """Return a fresh zero state; this is the only reset operation."""
        self._validate_batch_size(batch_size)
        parameter = self._parameter
        actual_device = parameter.device if device is None else device
        actual_dtype = parameter.dtype if dtype is None else dtype
        if not self._is_floating_dtype(actual_dtype):
            raise ValueError("dtype must be a floating-point torch.dtype")
        try:
            return torch.zeros((batch_size, self.config.hidden_size), device=actual_device, dtype=actual_dtype)
        except (TypeError, RuntimeError) as error:
            raise ValueError("device must identify a valid torch device") from error

    def _validate_step_inputs(self, x_t: object, state: object) -> tuple[Tensor, Tensor]:
        x_t = self._require_finite_tensor(x_t, "x_t", 2)
        state = self._require_finite_tensor(state, "state", 2)
        self._validate_device_dtype(x_t, "x_t")
        self._validate_device_dtype(state, "state")
        if x_t.shape[0] <= 0:
            raise ValueError("x_t batch dimension must be positive")
        if x_t.shape != (x_t.shape[0], self.config.input_size):
            raise ValueError(f"x_t must have shape [B, {self.config.input_size}]")
        if state.shape != (x_t.shape[0], self.config.hidden_size):
            raise ValueError(f"state must have shape [B, {self.config.hidden_size}]")
        return x_t, state

    @staticmethod
    def _finite_preactivation(value: Tensor) -> Tensor:
        # Affine overflow from finite operands must not leak NaN/Inf through
        # diagnostics.  Saturating nonlinearities make +/- max an appropriate
        # finite representation; cancellation NaNs have no representable exact
        # float result, so use the neutral preactivation.
        limit = torch.finfo(value.dtype).max
        return torch.nan_to_num(value, nan=0.0, posinf=limit, neginf=-limit)

    def step(self, x_t: Tensor, state: Tensor) -> TemporalStateStep:
        """Apply one left-to-right transition without retaining stream state."""
        x_t, state = self._validate_step_inputs(x_t, state)
        gate_preactivation = F.linear(x_t, self.W_g, self.b_g) + F.linear(state, self.U_g)
        candidate_preactivation = F.linear(x_t, self.W_c, self.b_c) + F.linear(state, self.U_c)
        gate = torch.sigmoid(self._finite_preactivation(gate_preactivation))
        candidate = torch.tanh(self._finite_preactivation(candidate_preactivation))
        next_state = (1.0 - gate) * state + gate * candidate
        if not bool(torch.isfinite(gate).all() and torch.isfinite(candidate).all() and torch.isfinite(next_state).all()):
            raise RuntimeError("TemporalState produced non-finite output; check module parameters")
        return TemporalStateStep(state=next_state, gate=gate, candidate=candidate)

    def forward_sequence(self, x: Tensor, initial_state: Tensor | None = None) -> tuple[Tensor, Tensor]:
        """Process ``[B, T, D]`` in supplied order and return all states/final state."""
        x = self._require_finite_tensor(x, "x", 3)
        self._validate_device_dtype(x, "x")
        batch_size, steps, width = x.shape
        if batch_size <= 0:
            raise ValueError("x batch dimension must be positive")
        if width != self.config.input_size:
            raise ValueError(f"x must have shape [B, T, {self.config.input_size}]")
        if initial_state is None:
            current_state = self.initial_state(batch_size, device=x.device, dtype=x.dtype)
        else:
            # A rank-2 empty sequence cannot call step, so reuse the same
            # state validation boundary explicitly.
            placeholder = x[:, 0, :] if steps else torch.empty(
                (batch_size, self.config.input_size), device=x.device, dtype=x.dtype
            )
            _, current_state = self._validate_step_inputs(placeholder, initial_state)
        outputs: list[Tensor] = []
        for index in range(steps):
            current_state = self.step(x[:, index, :], current_state).state
            outputs.append(current_state)
        if not outputs:
            return x.new_empty((batch_size, 0, self.config.hidden_size)), current_state
        return torch.stack(outputs, dim=1), current_state
