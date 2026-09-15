from __future__ import annotations

import math
from typing import Any

import torch
from torch import Tensor

from continuum.memory.adaptive_memory import AdaptiveMemory, AdaptiveMemoryConfig, EventRecord, RetentionDecision
from continuum.memory.cold_memory import ColdCandidateMemory, ColdCandidateRecord
from continuum.memory.revision_engine import RevisionConfig, RevisionEngine, RevisionResult
from continuum.state.temporal_state import TemporalState, TemporalStateConfig
from benchmarks.recency_trap.benchmark_recency_trap import DiversifiedDynamicsColdMemory, R3Engine


class ACMArchitecture:
    """
    Complete End-to-End Adaptive Causal Memory (ACM) Architecture.
    Strictly Bounded at K_total = 750 slots (K_hot = 250, K_cold = 500).

    Components:
    1. Temporal Recurrence Core (TemporalState) -> O(1) state dynamics
    2. Hot Memory Bank (AdaptiveMemory, 250 slots) -> 5-factor online scoring
    3. Cold Candidate Memory (DiversifiedDynamicsColdMemory, 500 slots) -> Subspace redundancy control
    4. Two-Tier Bypass Routing -> Discarded events route to cold memory instead of void
    5. Retrospective Revision Engine (R3Engine, CSM-Gated) -> Causal compatibility restoration
    """
    def __init__(
        self,
        emb_dim: int = 32,
        state_dim: int = 32,
        k_hot: int = 250,
        k_cold: int = 500,
        seed: int = 101,
        sim_thresh: float = 0.85,
        alpha_csm_gating: float = 3.0,
    ):
        self.emb_dim = emb_dim
        self.state_dim = state_dim
        self.k_hot = k_hot
        self.k_cold = k_cold
        self.k_total = k_hot + k_cold

        # 1. Temporal State Recurrence
        self.temporal_config = TemporalStateConfig(input_size=emb_dim, hidden_size=state_dim)
        self.temporal_model = TemporalState(self.temporal_config)
        self.h_state = self.temporal_model.initial_state(1)

        # 2. Hot Memory
        self.hot_config = AdaptiveMemoryConfig(
            embedding_dim=emb_dim,
            state_dim=state_dim,
            capacity=k_hot,
            seed=seed,
            alpha_surprise=0.2,
            beta_novelty=0.2,
            gamma_causal=0.2,
            delta_retrieval=0.2,
            epsilon_uncertainty=0.2,
        )
        self.hot_memory = AdaptiveMemory(self.hot_config)

        # 3. Cold Candidate Memory with Subspace Redundancy Suppression
        self.cold_memory = DiversifiedDynamicsColdMemory(
            capacity=k_cold,
            embedding_dim=emb_dim,
            state_dim=state_dim,
            sim_thresh=sim_thresh,
        )

        # 4. Revision Engine with CSM-Gated Temporal Decay
        self.rev_config = RevisionConfig(
            theta_trigger=0.45,
            theta_restore=0.25,
            max_restorations_per_trigger=2,
        )
        self.revision_engine = R3Engine(self.rev_config, alpha=alpha_csm_gating)

        self.step_count = 0

    def observe(self, event_id: int, timestamp: float, embedding: Tensor) -> EventRecord:
        emb = embedding.detach().float()
        if emb.ndim == 1:
            emb_unsq = emb.unsqueeze(0)
        else:
            emb_unsq = emb

        # Update recurrent state
        self.h_state = self.temporal_model.step(emb_unsq, self.h_state).state
        cur_h = self.h_state[0]

        # Observe in Hot Memory
        rec = self.hot_memory.observe(
            event_id=event_id,
            timestamp=timestamp,
            embedding=emb,
            temporal_state=cur_h,
            cold_memory=self.cold_memory,
        )

        # Bypass Admission: If hot memory discards, route to cold memory for subspace evaluation
        if rec.decision == RetentionDecision.DISCARD:
            self.cold_memory.archive(
                event_id=event_id,
                timestamp=timestamp,
                embedding=emb,
                temporal_state=cur_h,
                importance=rec.importance,
                provenance="acm_bypass_admission",
            )

        self.step_count += 1
        return rec

    def query_causal(self, query_embedding: Tensor, top_k: int = 5) -> list[int]:
        """
        Executes retrospective causal revision against terminal query/symptom.
        Searches cold candidate memory and evaluates via CSM-Gated RevisionEngine.
        """
        emb = query_embedding.detach().float()
        if emb.ndim == 1:
            emb_unsq = emb.unsqueeze(0)
        else:
            emb_unsq = emb

        self.h_state = self.temporal_model.step(emb_unsq, self.h_state).state
        cur_h = self.h_state[0]

        # Search cold memory
        candidates = self.cold_memory.search(query_embedding, top_k=min(100, len(self.cold_memory.records)))
        scored: list[tuple[float, int]] = []

        for cand, _ in candidates:
            score, _ = self.revision_engine._compute_revision_score_with_components(
                cand, query_embedding, cur_h, float(self.step_count)
            )
            if score > self.rev_config.theta_restore:
                scored.append((score, cand.event_id))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [eid for _, eid in scored[:top_k]]

    def get_memory_slots(self) -> int:
        hot_slots = len(self.hot_memory.records)
        cold_slots = len(self.cold_memory.records)
        return hot_slots + cold_slots
