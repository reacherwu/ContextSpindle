"""Continuum: Continuous Temporal Intelligence Engine."""

from continuum.api import CausalMatch, ContinuumConfig, ContinuumEngine, StreamStepResult
from continuum.state import TemporalState, TemporalStateConfig, TemporalStateStep

__version__ = "0.1.0-alpha"

__all__ = (
    "ContinuumEngine",
    "ContinuumConfig",
    "StreamStepResult",
    "CausalMatch",
    "TemporalState",
    "TemporalStateConfig",
    "TemporalStateStep",
    "__version__",
)
