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


def run_distractor_experiment(
    n_distractors: int,
    seed: int,
    emb_dim: int = 32,
    state_dim: int = 32,
    stream_length: int = 3000,
) -> dict[str, Any]:
    """
    Evaluates Revision Precision and False Revision Rate as candidate pool
    is flooded with n_distractors (with similarity to terminal event D).
    """
    torch.manual_seed(seed)
    random.seed(seed)

    n_clusters = 3
    clusters = [torch.randn(emb_dim) for _ in range(n_clusters)]
    for c in clusters:
        c /= torch.norm(c, p=2)

    subsystem = torch.randn(emb_dim)
    for c in clusters:
        subsystem -= torch.dot(subsystem, c) * c
    subsystem /= torch.norm(subsystem)

    root_id = 100
    vec_root = 0.85 * subsystem + 0.15 * torch.randn(emb_dim)
    vec_root /= torch.norm(vec_root)

    vec_D = 0.85 * subsystem + 0.15 * torch.randn(emb_dim)
    vec_D /= torch.norm(vec_D)

    # Distractor timestamps distributed across stream
    distractor_indices = set()
    if n_distractors > 0:
        available = [t for t in range(200, stream_length - 50) if t != root_id]
        chosen = random.sample(available, min(n_distractors, len(available)))
        distractor_indices = set(chosen)

    t_cfg = TemporalStateConfig(input_size=emb_dim, hidden_size=state_dim)
    temporal_model = TemporalState(t_cfg)
    h_state = temporal_model.initial_state(1)

    k_hot = 250
    k_cold = 500
    cold = ColdCandidateMemory(capacity=k_cold, embedding_dim=emb_dim, state_dim=state_dim)
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

    t0 = time.perf_counter()

    for t in range(stream_length):
        if t == root_id:
            emb = vec_root
        elif t in distractor_indices:
            # Distractor has partial alignment with D but is uncoupled from true causal subsystem
            emb = 0.35 * vec_D + 0.65 * torch.randn(emb_dim)
            emb /= torch.norm(emb, p=2)
        else:
            c_idx = (t // 25) % n_clusters
            emb = clusters[c_idx] + 0.03 * torch.randn(emb_dim)
            emb /= torch.norm(emb, p=2)

        h_state = temporal_model.step(emb.unsqueeze(0), h_state).state
        am.observe(
            event_id=t,
            timestamp=float(t),
            embedding=emb,
            temporal_state=h_state[0],
            cold_memory=cold,
        )

    # Terminal event D at t=stream_length triggers revision
    h_state = temporal_model.step(5.0 * vec_D.unsqueeze(0), h_state).state
    rec, revs = am.observe_with_revision(
        event_id=stream_length,
        timestamp=float(stream_length),
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

    query_A = vec_root + 0.01 * torch.randn(emb_dim)
    query_A /= torch.norm(query_A)
    retrieved = am.retrieve(query_A, top_k=5)
    top1_match = 1.0 if (retrieved and retrieved[0][0].event_id == root_id) else 0.0

    return {
        "n_distractors": n_distractors,
        "seed": seed,
        "root_restored": root_restored,
        "root_in_hot": root_in_hot,
        "restoration_recall": 1.0 if root_restored else 0.0,
        "revision_precision": precision,
        "false_revision_rate": float(false_revisions),
        "trigger_rate": 1.0 if len(revs) > 0 else 0.0,
        "top1_accuracy": top1_match,
        "latency_ms": elapsed_ms,
        "cold_slots_used": len(cold.records),
    }
