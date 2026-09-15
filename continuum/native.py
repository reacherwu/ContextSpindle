"""
Native Rust Core Bindings for Continuum.
Provides zero-overhead ctypes integration with crates/continuum-core.
Eliminates Python heap fragmentation and delivers microsecond-level query speed.
"""

from __future__ import annotations

import ctypes
from ctypes import (
    POINTER,
    Structure,
    c_bool,
    c_char_p,
    c_double,
    c_float,
    c_int32,
    c_size_t,
    c_uint64,
    c_uint8,
    c_void_p,
)
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import torch
from torch import Tensor

from continuum.api import CausalMatch, ContinuumConfig, StreamStepResult

# Search locations for compiled Rust cdylib
_REPO_ROOT = Path(__file__).resolve().parent.parent
_LIB_SEARCH_PATHS = [
    _REPO_ROOT / "target" / "release" / "libcontinuum_core.dylib",
    _REPO_ROOT / "target" / "release" / "libcontinuum_core.so",
    _REPO_ROOT / "target" / "debug" / "libcontinuum_core.dylib",
    _REPO_ROOT / "target" / "debug" / "libcontinuum_core.so",
    _REPO_ROOT / "crates" / "continuum-core" / "target" / "release" / "libcontinuum_core.dylib",
]

_lib = None
_lib_path = None
for p in _LIB_SEARCH_PATHS:
    if p.exists():
        try:
            _lib = ctypes.CDLL(str(p))
            _lib_path = p
            break
        except Exception:
            pass


def is_native_available() -> bool:
    """Check if compiled native Rust continuum-core dylib is available."""
    return _lib is not None


def get_native_lib_path() -> Path | None:
    return _lib_path


# =========================================================================
# CTypes Structure Definitions Matching Rust ffi.rs
# =========================================================================

class _CContinuumConfig(Structure):
    _fields_ = [
        ("embedding_dim", c_size_t),
        ("state_dim", c_size_t),
        ("hot_capacity", c_size_t),
        ("cold_capacity", c_size_t),
        ("sim_threshold", c_float),
        ("causal_exempt_threshold", c_float),
        ("temporal_decay_tau", c_float),
        ("w_sim", c_float),
        ("w_state_compat", c_float),
        ("w_temporal_compat", c_float),
        ("w_provenance_compat", c_float),
    ]


class _CStreamStepResult(Structure):
    _fields_ = [
        ("event_id", c_uint64),
        ("timestamp", c_double),
        ("importance", c_float),
        ("is_hot", c_bool),
        ("total_slots_used", c_size_t),
        ("state_norm", c_float),
    ]


class _CCausalMatch(Structure):
    _fields_ = [
        ("event_id", c_uint64),
        ("timestamp", c_double),
        ("revision_score", c_float),
        ("sim", c_float),
        ("state_compat", c_float),
        ("temporal_compat", c_float),
        ("provenance_compat", c_float),
        ("provenance_buf", c_uint8 * 128),
        ("provenance_len", c_size_t),
    ]


# Setup function signatures if library loaded
if _lib is not None:
    _lib.continuum_engine_create.argtypes = [POINTER(_CContinuumConfig)]
    _lib.continuum_engine_create.restype = c_void_p

    _lib.continuum_engine_step.argtypes = [
        c_void_p,
        POINTER(c_float),
        c_size_t,
        c_double,
        c_char_p,
        POINTER(_CStreamStepResult),
    ]
    _lib.continuum_engine_step.restype = c_int32

    _lib.continuum_engine_query.argtypes = [
        c_void_p,
        POINTER(c_float),
        c_size_t,
        c_size_t,
        POINTER(_CCausalMatch),
        c_size_t,
    ]
    _lib.continuum_engine_query.restype = c_size_t

    _lib.continuum_engine_get_stats.argtypes = [
        c_void_p,
        POINTER(c_size_t),
        POINTER(c_size_t),
        POINTER(c_uint64),
    ]
    _lib.continuum_engine_get_stats.restype = c_int32

    _lib.continuum_engine_destroy.argtypes = [c_void_p]
    _lib.continuum_engine_destroy.restype = None

    _lib.continuum_engine_save.argtypes = [c_void_p, c_char_p]
    _lib.continuum_engine_save.restype = c_int32

    _lib.continuum_engine_load.argtypes = [c_char_p]
    _lib.continuum_engine_load.restype = c_void_p


class RustNativeEngine:
    """
    High-performance, zero-GC native Rust implementation of ContinuumEngine.
    Maintains physical O(K) memory in Rust with zero Python heap fragmentation.
    """
    def __init__(self, config: ContinuumConfig | None = None) -> None:
        if not is_native_available():
            raise RuntimeError(
                "Native Rust continuum-core dylib not found! "
                "Run `cargo build --release` in the project root first."
            )
        self.config = config or ContinuumConfig()

        c_cfg = _CContinuumConfig(
            embedding_dim=self.config.embedding_dim,
            state_dim=self.config.state_dim,
            hot_capacity=self.config.hot_capacity,
            cold_capacity=self.config.cold_capacity,
            sim_threshold=self.config.sim_threshold,
            causal_exempt_threshold=self.config.causal_exempt_threshold if self.config.causal_exempt_threshold is not None else -1.0,
            temporal_decay_tau=1000.0,
            w_sim=self.config.w_sim,
            w_state_compat=self.config.w_state_compat,
            w_temporal_compat=self.config.w_temporal_compat,
            w_provenance_compat=self.config.w_provenance_compat,
        )

        self._ptr = _lib.continuum_engine_create(ctypes.byref(c_cfg))
        if not self._ptr:
            raise MemoryError("Failed to allocate native ContinuumEngine in Rust.")
        self.step_count = 0

    def step(
        self,
        embedding: Tensor | Sequence[float],
        timestamp: float | None = None,
        payload_ref: str | None = None,
    ) -> StreamStepResult:
        if isinstance(embedding, Tensor):
            emb_arr = embedding.detach().cpu().float().contiguous().numpy()
        else:
            emb_arr = torch.tensor(embedding, dtype=torch.float32).numpy()

        ts = float(self.step_count if timestamp is None else timestamp)
        payload_bytes = (payload_ref or "").encode("utf-8")

        c_arr = (c_float * len(emb_arr))(*emb_arr)
        out_res = _CStreamStepResult()

        status = _lib.continuum_engine_step(
            self._ptr,
            c_arr,
            len(emb_arr),
            ts,
            payload_bytes,
            ctypes.byref(out_res),
        )

        if status != 0:
            raise RuntimeError(f"Native step failed with status code {status}")

        self.step_count += 1

        return StreamStepResult(
            event_id=out_res.event_id,
            timestamp=out_res.timestamp,
            importance=out_res.importance,
            decision="keep" if out_res.is_hot else "discard",
            is_hot=out_res.is_hot,
            total_slots_used=out_res.total_slots_used,
            state_norm=out_res.state_norm,
        )

    def query(
        self,
        query_vector: Tensor | Sequence[float],
        top_k: int = 5,
    ) -> list[CausalMatch]:
        if isinstance(query_vector, Tensor):
            q_arr = query_vector.detach().cpu().float().contiguous().numpy()
        else:
            q_arr = torch.tensor(query_vector, dtype=torch.float32).numpy()

        c_arr = (c_float * len(q_arr))(*q_arr)
        max_matches = max(10, top_k * 2)
        match_arr = (_CCausalMatch * max_matches)()

        count = _lib.continuum_engine_query(
            self._ptr,
            c_arr,
            len(q_arr),
            top_k,
            match_arr,
            max_matches,
        )

        results: list[CausalMatch] = []
        for i in range(min(count, top_k)):
            m = match_arr[i]
            raw_bytes = bytes(m.provenance_buf[:m.provenance_len])
            prov_str = raw_bytes.decode("utf-8", errors="replace")

            comps = {
                "sim": float(m.sim),
                "state_compat": float(m.state_compat),
                "temporal_compat": float(m.temporal_compat),
                "provenance_compat": float(m.provenance_compat),
            }

            results.append(
                CausalMatch(
                    event_id=int(m.event_id),
                    timestamp=float(m.timestamp),
                    revision_score=float(m.revision_score),
                    components=comps,
                    provenance=prov_str,
                )
            )

        return results

    def get_stats(self) -> dict[str, Any]:
        hot_slots = c_size_t(0)
        cold_slots = c_size_t(0)
        steps = c_uint64(0)
        _lib.continuum_engine_get_stats(
            self._ptr,
            ctypes.byref(hot_slots),
            ctypes.byref(cold_slots),
            ctypes.byref(steps),
        )
        total = hot_slots.value + cold_slots.value
        max_slots = self.config.hot_capacity + self.config.cold_capacity
        return {
            "step_count": steps.value,
            "hot_slots": hot_slots.value,
            "cold_slots": cold_slots.value,
            "total_slots": total,
            "max_slots": max_slots,
            "slot_utilization_pct": (total / max_slots) * 100.0 if max_slots > 0 else 0.0,
            "backend": "rust_native",
        }

    def save(self, filepath: str | Path) -> None:
        """Persist native Rust engine state to disk."""
        path_bytes = str(filepath).encode("utf-8")
        ret = _lib.continuum_engine_save(self._ptr, path_bytes)
        if ret != 0:
            raise IOError(f"Failed to persist native engine to {filepath} (code: {ret})")

    @classmethod
    def load(cls, filepath: str | Path) -> RustNativeEngine:
        """Restore native Rust engine state from disk."""
        if not is_native_available():
            raise RuntimeError("Native Rust continuum-core dylib not found!")
        path_bytes = str(filepath).encode("utf-8")
        ptr = _lib.continuum_engine_load(path_bytes)
        if not ptr:
            raise IOError(f"Failed to load native engine from {filepath}")
        engine = cls.__new__(cls)
        engine._ptr = ptr
        hot_slots = c_size_t(0)
        cold_slots = c_size_t(0)
        steps = c_uint64(0)
        _lib.continuum_engine_get_stats(
            ptr,
            ctypes.byref(hot_slots),
            ctypes.byref(cold_slots),
            ctypes.byref(steps),
        )
        engine.config = ContinuumConfig(
            hot_capacity=hot_slots.value,
            cold_capacity=cold_slots.value,
            backend="rust",
        )
        return engine

    def __del__(self) -> None:
        if hasattr(self, "_ptr") and self._ptr and _lib is not None:
            _lib.continuum_engine_destroy(self._ptr)
            self._ptr = None
