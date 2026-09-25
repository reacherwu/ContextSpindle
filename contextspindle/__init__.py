"""ContextSpindle's Python entry point and compatibility aliases."""

from continuum import (
    CausalMatch,
    ContinuumConfig,
    ContinuumEngine,
    StreamStepResult,
    TemporalState,
    TemporalStateConfig,
    TemporalStateStep,
    __version__,
)

ContextSpindleConfig = ContinuumConfig
ContextSpindleEngine = ContinuumEngine

__all__ = (
    "ContextSpindleConfig",
    "ContextSpindleEngine",
    "CausalMatch",
    "StreamStepResult",
    "TemporalState",
    "TemporalStateConfig",
    "TemporalStateStep",
    "__version__",
)
