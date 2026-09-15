"""Public API and high-level facade for the Continuum Temporal Intelligence Engine."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Sequence

import torch
from torch import Tensor

from continuum.memory.adaptive_memory import AdaptiveMemory, AdaptiveMemoryConfig, EventRecord, RetentionDecision
from continuum.memory.cold_memory import ColdCandidateRecord, DiversifiedDynamicsColdMemory
from continuum.memory.revision_engine import RevisionConfig, RevisionEngine, RevisionResult
from continuum.state.temporal_state import TemporalState, TemporalStateConfig


@dataclass(frozen=True)
class ContinuumConfig:
    """Production configuration for ContinuumEngine."""
    embedding_dim: int = 32
    state_dim: int = 32
    hot_capacity: int = 250
    cold_capacity: int = 500
    seed: int = 101
    sim_threshold: float = 0.65
    alpha_csm_gating: float = 3.0
    theta_trigger: float = 0.45
    theta_restore: float = 0.25
    max_restorations: int = 5
    w_sim: float = 0.55
    w_state_compat: float = 0.15
    w_temporal_compat: float = 0.20
    w_provenance_compat: float = 0.10
    causal_exempt_threshold: float | None = 0.25
    device: str = "cpu"
    backend: str = "python"  # "python" or "rust"


@dataclass(frozen=True)
class StreamStepResult:
    """Result of processing a single streaming event."""
    event_id: int
    timestamp: float
    importance: float
    decision: str
    is_hot: bool
    total_slots_used: int
    state_norm: float


@dataclass(frozen=True)
class CausalMatch:
    """Causal retrieval result."""
    event_id: int
    timestamp: float
    revision_score: float
    components: dict[str, float]
    provenance: str


class ContinuumEngine:
    """
    High-level facade for Continuum: Continuous Temporal Intelligence Engine.

    Unifies:
    - O(1) Gated Temporal State Recurrence
    - Two-Tier Manifold Memory (Hot Active Working Set + Cold Candidate Archive)
    - Subspace Diversity Redundancy Control
    - Retrospective Causal Revision Engine
    """

    def __new__(cls, config: ContinuumConfig | None = None):
        cfg = config or ContinuumConfig()
        if getattr(cfg, "backend", "python") == "rust":
            from continuum.native import RustNativeEngine
            return RustNativeEngine(cfg)
        return super().__new__(cls)

    def __init__(self, config: ContinuumConfig | None = None) -> None:
        self.config = config or ContinuumConfig()

        # 1. Temporal Recurrence Core
        self.temporal_config = TemporalStateConfig(
            input_size=self.config.embedding_dim,
            hidden_size=self.config.state_dim,
        )
        self.temporal_model = TemporalState(self.temporal_config)
        self.h_state = self.temporal_model.initial_state(1)

        # 2. Hot Memory Bank
        self.hot_config = AdaptiveMemoryConfig(
            embedding_dim=self.config.embedding_dim,
            state_dim=self.config.state_dim,
            capacity=self.config.hot_capacity,
            seed=self.config.seed,
            device=self.config.device,
        )
        self.hot_memory = AdaptiveMemory(self.hot_config)

        # 3. Cold Candidate Memory (Subspace Diversity)
        self.cold_memory = DiversifiedDynamicsColdMemory(
            capacity=self.config.cold_capacity,
            embedding_dim=self.config.embedding_dim,
            state_dim=self.config.state_dim,
            sim_thresh=self.config.sim_threshold,
        )

        # 4. Revision Engine
        self.rev_config = RevisionConfig(
            w_sim=self.config.w_sim,
            w_state_compat=self.config.w_state_compat,
            w_temporal_compat=self.config.w_temporal_compat,
            w_provenance_compat=self.config.w_provenance_compat,
            theta_trigger=self.config.theta_trigger,
            theta_restore=self.config.theta_restore,
            max_restorations_per_trigger=self.config.max_restorations,
            causal_exempt_threshold=self.config.causal_exempt_threshold,
        )
        self.revision_engine = RevisionEngine(self.rev_config)

        self.step_count = 0

    @classmethod
    def create(cls, **kwargs: Any) -> ContinuumEngine:
        """Factory constructor with keyword argument overrides."""
        cfg = ContinuumConfig(**kwargs)
        return cls(cfg)

    def _format_tensor(self, vector: Tensor | Sequence[float]) -> Tensor:
        if isinstance(vector, Tensor):
            t = vector.detach().float()
        else:
            t = torch.tensor(vector, dtype=torch.float32)
        if t.ndim > 1:
            t = t.squeeze()
        if t.shape[0] != self.config.embedding_dim:
            raise ValueError(
                f"Vector dimension mismatch: expected {self.config.embedding_dim}, got {t.shape[0]}"
            )
        norm = torch.norm(t, p=2)
        if norm > 1e-8:
            t = t / norm
        return t

    def step(
        self,
        vector: Tensor | Sequence[float],
        timestamp: float | None = None,
        payload_ref: str | None = None,
    ) -> StreamStepResult:
        """
        Process an incoming streaming event in O(1) time and memory.
        """
        x_t = self._format_tensor(vector)
        ts = float(self.step_count if timestamp is None else timestamp)
        event_id = self.step_count

        # Recurrent state update
        self.h_state = self.temporal_model.step(x_t.unsqueeze(0), self.h_state).state
        cur_h = self.h_state[0]

        # Hot memory observation
        rec = self.hot_memory.observe(
            event_id=event_id,
            timestamp=ts,
            embedding=x_t,
            temporal_state=cur_h,
            payload_ref=payload_ref,
            cold_memory=self.cold_memory,
        )

        # Bypass Admission: If hot memory rejects, cold evaluates for subspace diversity
        if rec.decision == RetentionDecision.DISCARD:
            self.cold_memory.archive(
                event_id=event_id,
                timestamp=ts,
                embedding=x_t,
                temporal_state=cur_h,
                importance=rec.importance,
                provenance=payload_ref or "stream_bypass",
            )

        self.step_count += 1

        is_hot = any(r.event_id == event_id for r in self.hot_memory.records)
        total_slots = len(self.hot_memory.records) + len(self.cold_memory.records)
        state_norm = float(torch.norm(cur_h, p=2).item())

        return StreamStepResult(
            event_id=event_id,
            timestamp=ts,
            importance=rec.importance,
            decision=str(rec.decision.value),
            is_hot=is_hot,
            total_slots_used=total_slots,
            state_norm=state_norm,
        )

    def query(
        self,
        query_vector: Tensor | Sequence[float],
        top_k: int = 5,
    ) -> list[CausalMatch]:
        """
        Retrospective causal query: searches stored candidates and evaluates
        causal compatibility against the query symptom.
        """
        q = self._format_tensor(query_vector)

        # Step recurrent state to incorporate query context without mutating streaming state
        q_state = self.temporal_model.step(q.unsqueeze(0), self.h_state).state
        cur_h = q_state[0]

        # Search candidates in cold candidate pool
        # Evaluate all cold candidates directly (O(K_cold) where K_cold <= 500 takes ~18.5us)
        # to prevent alert storms from prematurely truncating subtle causal roots via raw cosine sim.
        scored: list[tuple[float, ColdCandidateRecord, dict[str, float]]] = []
        for cand in self.cold_memory.records:
            score, comps = self.revision_engine._compute_revision_score_with_components(
                cand, q, cur_h, float(self.step_count)
            )
            scored.append((score, cand, comps))

        # Also search in active hot memory bank
        for h_rec in self.hot_memory.records:
            h_state = self.hot_memory._record_states.get(h_rec.event_id, cur_h)
            h_cand = ColdCandidateRecord(
                event_id=h_rec.event_id,
                timestamp=h_rec.timestamp,
                compressed_embedding=h_rec.embedding,
                state_fingerprint=h_state,
                importance_at_eviction=h_rec.importance,
                provenance_summary=h_rec.payload_ref or "hot_memory",
            )
            score, comps = self.revision_engine._compute_revision_score_with_components(
                h_cand, q, cur_h, float(self.step_count)
            )
            scored.append((score, h_cand, comps))

        scored.sort(key=lambda x: x[0], reverse=True)

        results: list[CausalMatch] = []
        for score, cand, comps in scored[:top_k]:
            results.append(
                CausalMatch(
                    event_id=cand.event_id,
                    timestamp=cand.timestamp,
                    revision_score=score,
                    components=comps,
                    provenance=cand.provenance_summary,
                )
            )
        return results

    def get_stats(self) -> dict[str, Any]:
        """Return runtime health and memory allocation metrics."""
        hot_slots = len(self.hot_memory.records)
        cold_slots = len(self.cold_memory.records)
        return {
            "step_count": self.step_count,
            "hot_slots": hot_slots,
            "cold_slots": cold_slots,
            "total_slots": hot_slots + cold_slots,
            "max_slots": self.config.hot_capacity + self.config.cold_capacity,
            "slot_utilization_pct": ((hot_slots + cold_slots) / (self.config.hot_capacity + self.config.cold_capacity)) * 100.0,
            "device": self.config.device,
        }

    def reset(self) -> None:
        """Reset internal memory banks and recurrent state."""
        self.temporal_model = TemporalState(self.temporal_config)
        self.h_state = self.temporal_model.initial_state(1)
        self.hot_memory.clear()
        self.cold_memory = DiversifiedDynamicsColdMemory(
            capacity=self.config.cold_capacity,
            embedding_dim=self.config.embedding_dim,
            state_dim=self.config.state_dim,
            sim_thresh=self.config.sim_threshold,
        )
        self.step_count = 0

    def save(self, filepath: str | Any) -> None:
        """Serialize engine state to disk for persistent long-term storage."""
        state_dict = {
            "config": self.config,
            "step_count": self.step_count,
            "h_state": self.h_state,
            "temporal_model_state": self.temporal_model.state_dict(),
            "hot_records": self.hot_memory.records,
            "hot_embeddings": self.hot_memory.embeddings_tensor,
            "hot_last_access": self.hot_memory.last_access_time,
            "hot_record_states": self.hot_memory._record_states,
            "cold_records": self.cold_memory.records,
            "cold_embeddings": self.cold_memory.embeddings_tensor,
        }
        torch.save(state_dict, str(filepath))

    @classmethod
    def load(cls, filepath: str | Any) -> ContinuumEngine:
        """Deserialize engine state from disk."""
        state_dict = torch.load(str(filepath), map_location="cpu", weights_only=False)
        cfg = state_dict["config"]
        engine = cls(cfg)
        engine.step_count = state_dict["step_count"]
        engine.h_state = state_dict["h_state"]
        engine.temporal_model.load_state_dict(state_dict["temporal_model_state"])
        engine.hot_memory.records = state_dict["hot_records"]
        engine.hot_memory.embeddings_tensor = state_dict["hot_embeddings"]
        engine.hot_memory.last_access_time = state_dict["hot_last_access"]
        engine.hot_memory._record_states = state_dict.get("hot_record_states", {})
        engine.cold_memory.records = state_dict["cold_records"]
        engine.cold_memory.embeddings_tensor = state_dict["cold_embeddings"]
        return engine

