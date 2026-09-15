from __future__ import annotations

import random
import time
from typing import Any

import torch
from torch import Tensor

from continuum.memory.adaptive_memory import AdaptiveMemory, AdaptiveMemoryConfig
from continuum.memory.cold_memory import ColdCandidateMemory
from continuum.memory.revision_engine import RevisionConfig, RevisionEngine
from continuum.state.temporal_state import TemporalState, TemporalStateConfig


def run_delay_experiment(
    delta_t: int,
    seed: int,
    emb_dim: int = 32,
    state_dim: int = 32,
    k_hot: int = 250,
    k_cold: int = 500,
    proportional_cold: bool = False,
) -> dict[str, Any]:
    """
    Measures Revision performance across varying temporal delays delta_t.
    Root event A occurs at t=100; terminal event D occurs at t=100 + delta_t.
    """
    torch.manual_seed(seed)
    random.seed(seed)

    effective_k_cold = k_cold if not proportional_cold else max(k_cold, int(0.2 * delta_t))

    n_clusters = 3
    clusters = [torch.randn(emb_dim) for _ in range(n_clusters)]
    for c in clusters:
        c /= torch.norm(c, p=2)

    subsystem = torch.randn(emb_dim)
    for c in clusters:
        subsystem -= torch.dot(subsystem, c) * c
    subsystem /= torch.norm(subsystem)

    vec_A = 0.85 * subsystem + 0.15 * torch.randn(emb_dim)
    vec_A /= torch.norm(vec_A)

    vec_D = 0.85 * subsystem + 0.15 * torch.randn(emb_dim)
    vec_D /= torch.norm(vec_D)

    t_cfg = TemporalStateConfig(input_size=emb_dim, hidden_size=state_dim)
    temporal_model = TemporalState(t_cfg)
    h_state = temporal_model.initial_state(1)

    cold = ColdCandidateMemory(capacity=effective_k_cold, embedding_dim=emb_dim, state_dim=state_dim)
    am = AdaptiveMemory(
        AdaptiveMemoryConfig(
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
    )
    engine = RevisionEngine(
        RevisionConfig(
            theta_trigger=0.45,
            theta_restore=0.25,
            max_restorations_per_trigger=1,
        )
    )

    root_id = 100
    terminal_t = 100 + delta_t
    root_importance_at_t100 = 0.0

    t0 = time.perf_counter()

    for t in range(terminal_t):
        if t == root_id:
            emb = vec_A
        else:
            c_idx = (t // 25) % n_clusters
            emb = clusters[c_idx] + 0.03 * torch.randn(emb_dim)
            emb /= torch.norm(emb, p=2)

        h_state = temporal_model.step(emb.unsqueeze(0), h_state).state
        rec = am.observe(
            event_id=t,
            timestamp=float(t),
            embedding=emb,
            temporal_state=h_state[0],
            cold_memory=cold,
        )
        if t == root_id:
            root_importance_at_t100 = rec.importance

    # Terminal event D at t=terminal_t triggers retrospective revision
    h_state = temporal_model.step(5.0 * vec_D.unsqueeze(0), h_state).state
    rec, revs = am.observe_with_revision(
        event_id=terminal_t,
        timestamp=float(terminal_t),
        embedding=vec_D,
        temporal_state=h_state[0],
        cold_memory=cold,
        revision_engine=engine,
    )

    elapsed_ms = (time.perf_counter() - t0) * 1000

    root_restored = False
    false_revisions = 0
    true_revisions = 0

    for r in revs:
        if r.decision == "restore":
            if r.candidate.event_id == root_id:
                root_restored = True
                true_revisions += 1
            else:
                false_revisions += 1

    total_revs = true_revisions + false_revisions
    precision = true_revisions / total_revs if total_revs > 0 else 0.0
    root_in_hot = any(r.event_id == root_id for r in am.records)
    root_in_cold = any(r.event_id == root_id for r in cold.records)

    # Downstream causal query for root cause A
    query_A = vec_A + 0.01 * torch.randn(emb_dim)
    query_A /= torch.norm(query_A)
    retrieved = am.retrieve(query_A, top_k=5)
    top1_match = 1.0 if (retrieved and retrieved[0][0].event_id == root_id) else 0.0

    return {
        "delta_t": delta_t,
        "seed": seed,
        "k_hot": k_hot,
        "k_cold": effective_k_cold,
        "proportional_cold": proportional_cold,
        "root_restored": root_restored,
        "root_in_hot": root_in_hot,
        "root_in_cold": root_in_cold,
        "restoration_recall": 1.0 if root_restored else 0.0,
        "revision_precision": precision,
        "false_revision_rate": float(false_revisions),
        "trigger_rate": 1.0 if len(revs) > 0 else 0.0,
        "top1_accuracy": top1_match,
        "latency_ms": elapsed_ms,
        "cold_slots_used": len(cold.records),
    }
