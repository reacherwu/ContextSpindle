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


def run_chain_experiment(
    chain_length: int,
    seed: int,
    emb_dim: int = 32,
    state_dim: int = 32,
    stream_length: int = 3000,
) -> dict[str, Any]:
    """
    Evaluates Revision robustness across causal chains of varying lengths:
    - chain_length 2: A -> D
    - chain_length 3: A -> B -> D
    - chain_length 4: A -> B -> C -> D
    - chain_length 5: A -> B -> C -> D -> E
    - chain_length 6: A -> B -> C -> D -> E -> F
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

    # Generate chain vectors along causal subsystem subspace
    chain_nodes: dict[int, Tensor] = {}
    
    # Root A is always at t=100
    root_id = 100
    vec_root = 0.85 * subsystem + 0.15 * torch.randn(emb_dim)
    vec_root /= torch.norm(vec_root)
    chain_nodes[root_id] = vec_root

    # Intermediate hops evenly spaced between 100 and stream_length
    num_intermediates = chain_length - 2
    step_gap = (stream_length - 100) // (num_intermediates + 1) if num_intermediates > 0 else 0
    for i in range(num_intermediates):
        hop_t = 100 + (i + 1) * step_gap
        # Intermediate nodes have decaying causal alignment
        decay = 0.85 - 0.05 * (i + 1)
        v_hop = decay * subsystem + (1.0 - decay) * torch.randn(emb_dim)
        v_hop /= torch.norm(v_hop)
        chain_nodes[hop_t] = v_hop

    # Terminal node at stream_length
    terminal_id = stream_length
    vec_terminal = 0.85 * subsystem + 0.15 * torch.randn(emb_dim)
    vec_terminal /= torch.norm(vec_terminal)

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
        if t in chain_nodes:
            emb = chain_nodes[t]
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

    # Terminal trigger
    h_state = temporal_model.step(5.0 * vec_terminal.unsqueeze(0), h_state).state
    rec, revs = am.observe_with_revision(
        event_id=terminal_id,
        timestamp=float(terminal_id),
        embedding=vec_terminal,
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
            elif r.candidate.event_id in chain_nodes:
                # Restored valid intermediate causal predecessor
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
        "chain_length": chain_length,
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
