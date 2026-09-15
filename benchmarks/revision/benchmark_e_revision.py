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


def generate_stream(seed: int, stream_length: int = 3000, emb_dim: int = 32) -> tuple[list[tuple[int, Tensor, bool]], Tensor, Tensor]:
    """
    Generates a streaming environment with an antecedent causal chain:
    - Event A at t=100 (subtle degradation in subsystem, ordinary magnitude)
    - Background: routine operational cycling across 3 background clusters
    - Event D at t=3000 (terminal failure)
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

    vec_A = 0.85 * subsystem + 0.15 * torch.randn(emb_dim)
    vec_A /= torch.norm(vec_A)

    vec_D = 0.85 * subsystem + 0.15 * torch.randn(emb_dim)
    vec_D /= torch.norm(vec_D)

    stream: list[tuple[int, Tensor, bool]] = []
    for t in range(stream_length):
        if t == 100:
            emb = vec_A
            is_root = True
        else:
            c_idx = (t // 25) % n_clusters
            emb = clusters[c_idx] + 0.03 * torch.randn(emb_dim)
            emb /= torch.norm(emb, p=2)
            is_root = False
        stream.append((t, emb, is_root))

    return stream, vec_A, vec_D


def run_condition(condition_id: str, seed: int) -> dict[str, Any]:
    """
    Runs one of the 6 experimental conditions:
    - E0: FIFO eviction baseline
    - E1: LRU eviction baseline
    - E2: Random eviction baseline
    - E3: Hot-only Adaptive Memory (no cold, no revision)
    - E4: Hot + Cold without Revision (cold candidate buffer archives evicted records)
    - E5: Hot + Cold + Revision (RevisionEngine evaluates candidates and restores root cause)
    """
    stream_length = 3000
    emb_dim = 32
    state_dim = 32

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

    vec_A = 0.85 * subsystem + 0.15 * torch.randn(emb_dim)
    vec_A /= torch.norm(vec_A)

    vec_D = 0.85 * subsystem + 0.15 * torch.randn(emb_dim)
    vec_D /= torch.norm(vec_D)

    t_cfg = TemporalStateConfig(input_size=emb_dim, hidden_size=state_dim)
    temporal_model = TemporalState(t_cfg)
    h_state = temporal_model.initial_state(1)

    capacity = 250
    k_cold = 500

    eviction = (
        "fifo" if condition_id == "E0"
        else "lru" if condition_id == "E1"
        else "random" if condition_id == "E2"
        else "min_importance"
    )
    use_cold = condition_id in ["E4", "E5"]
    use_rev = condition_id == "E5"

    am_config = AdaptiveMemoryConfig(
        embedding_dim=emb_dim,
        state_dim=state_dim,
        capacity=capacity,
        eviction_policy=eviction,
        seed=seed,
        alpha_surprise=0.2,
        beta_novelty=0.2,
        gamma_causal=0.2,
        delta_retrieval=0.2,
        epsilon_uncertainty=0.2,
    )
    cold_mem = ColdCandidateMemory(capacity=k_cold, embedding_dim=emb_dim, state_dim=state_dim) if use_cold else None
    am = AdaptiveMemory(am_config)
    rev_engine = RevisionEngine(RevisionConfig(theta_trigger=0.45, theta_restore=0.25, max_restorations_per_trigger=1)) if use_rev else None

    root_event_id = 100
    root_event_importance = 0.0
    root_restored = False
    revisions_triggered = 0

    t0 = time.perf_counter()

    for t in range(stream_length):
        if t == 100:
            emb = vec_A
            is_root = True
        else:
            c_idx = (t // 25) % n_clusters
            emb = clusters[c_idx] + 0.03 * torch.randn(emb_dim)
            emb /= torch.norm(emb, p=2)
            is_root = False

        h_state = temporal_model.step(emb.unsqueeze(0), h_state).state
        record = am.observe(
            event_id=t,
            timestamp=float(t),
            embedding=emb,
            temporal_state=h_state[0],
            cold_memory=cold_mem,
        )

        if is_root:
            root_event_importance = record.importance

    # Terminal event D at t=stream_length
    if use_rev:
        h_state = temporal_model.step(5.0 * vec_D.unsqueeze(0), h_state).state
        record, revs = am.observe_with_revision(
            event_id=stream_length,
            timestamp=float(stream_length),
            embedding=vec_D,
            temporal_state=h_state[0],
            cold_memory=cold_mem,
            revision_engine=rev_engine,
        )
        if len(revs) > 0:
            revisions_triggered += len(revs)
            for r in revs:
                if r.candidate.event_id == root_event_id and r.decision == "restore":
                    root_restored = True
    else:
        h_state = temporal_model.step(vec_D.unsqueeze(0), h_state).state
        record = am.observe(
            event_id=stream_length,
            timestamp=float(stream_length),
            embedding=vec_D,
            temporal_state=h_state[0],
            cold_memory=cold_mem,
        )

    latency = (time.perf_counter() - t0) * 1000

    # Post-Stream Causal Query for Root Cause A
    query_A = vec_A + 0.01 * torch.randn(emb_dim)
    query_A /= torch.norm(query_A)
    results = am.retrieve(query_A, top_k=5)
    top1_match = 1.0 if (results and results[0][0].event_id == root_event_id) else 0.0

    root_in_hot = any(r.event_id == root_event_id for r in am.records)
    root_in_cold = any(r.event_id == root_event_id for r in cold_mem.records) if cold_mem else False

    return {
        "root_event_A_importance_at_t100": root_event_importance,
        "root_event_A_in_hot_at_t5100": root_in_hot,
        "root_event_A_in_cold_at_t5100": root_in_cold,
        "root_event_A_restored_by_revision": root_restored,
        "root_cause_retrieval_accuracy": top1_match,
        "cold_memory_size_at_end": len(cold_mem.records) if cold_mem else 0,
        "num_revisions_triggered": revisions_triggered,
        "revision_latency_ms": latency,
    }
