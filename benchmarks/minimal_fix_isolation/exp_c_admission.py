from __future__ import annotations

import random
import time
from typing import Any

import torch
from torch import Tensor

from continuum.memory.adaptive_memory import AdaptiveMemory, AdaptiveMemoryConfig, RetentionDecision
from continuum.memory.cold_memory import ColdCandidateMemory
from continuum.memory.revision_engine import RevisionConfig, RevisionEngine
from continuum.state.temporal_state import TemporalState, TemporalStateConfig


def run_exp_c_experiment(
    condition: str,  # 'C0_current_discard', 'C1_only_causal_intermediate', 'C2_high_value_discard'
    seed: int,
    emb_dim: int = 32,
    state_dim: int = 32,
    stream_length: int = 3000,
) -> dict[str, Any]:
    """
    M2.9.2-C: Intermediate Admission Isolation.
    Evaluates causal chain A -> B -> D (L=3).
    Compares:
      C0: Current DISCARD (discarded events never enter cold memory).
      C1: Only causal/intermediate candidates enter cold memory upon discard (Oracle causal isolation).
      C2: High-value DISCARD (discarded events with online importance >= 0.40 enter cold memory).
    Evaluates:
      Root Recall, Intermediate Recall, Chain Recall.
      Answers: Is intermediate admission a necessary factor for multi-hop failure?
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

    # Intermediate hop B at t=1550 (matching chain_length_scaling.py L=3)
    b_id = 1550
    v_b = 0.80 * subsystem + 0.20 * torch.randn(emb_dim)
    v_b /= torch.norm(v_b)

    chain_nodes = {root_id: vec_root, b_id: v_b}

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
        rec = am.observe(
            event_id=t,
            timestamp=float(t),
            embedding=emb,
            temporal_state=h_state[0],
            cold_memory=cold,
        )

        if rec.decision == RetentionDecision.DISCARD:
            if condition == "C1_only_causal_intermediate":
                if t in chain_nodes and t != terminal_id:
                    cold.archive(
                        event_id=rec.event_id,
                        timestamp=rec.timestamp,
                        embedding=rec.embedding,
                        temporal_state=h_state[0],
                        importance=rec.importance,
                        provenance="discarded_causal_node",
                    )
            elif condition == "C2_high_value_discard":
                # Only high-value discards (importance >= 0.40) enter cold memory
                if rec.importance >= 0.40:
                    cold.archive(
                        event_id=rec.event_id,
                        timestamp=rec.timestamp,
                        embedding=rec.embedding,
                        temporal_state=h_state[0],
                        importance=rec.importance,
                        provenance="high_value_discard",
                    )
            elif condition == "C0_current_discard":
                pass  # Do not archive

    # Record cold presence before terminal revision
    root_in_cold = any(r.event_id == root_id for r in cold.records)
    inter_in_cold = any(r.event_id == b_id for r in cold.records)

    # Terminal revision trigger
    h_state = temporal_model.step(5.0 * vec_terminal.unsqueeze(0), h_state).state
    rec_d, revs = am.observe_with_revision(
        event_id=terminal_id,
        timestamp=float(terminal_id),
        embedding=vec_terminal,
        temporal_state=h_state[0],
        cold_memory=cold,
        revision_engine=engine,
    )

    elapsed_ms = (time.perf_counter() - t0) * 1000

    restored_ids = [r.candidate.event_id for r in revs if r.decision == "restore"]
    root_restored = root_id in restored_ids
    intermediate_restored = b_id in restored_ids
    chain_restored = root_restored and intermediate_restored

    # Check hot presence after revision
    root_in_hot = any(r.event_id == root_id for r in am.records)
    inter_in_hot = any(r.event_id == b_id for r in am.records)

    restoration_count = len(restored_ids)
    true_revision_count = sum(1 for eid in restored_ids if eid in chain_nodes)
    false_revision_count = sum(1 for eid in restored_ids if eid not in chain_nodes)

    root_recall = 1.0 if root_restored else 0.0
    intermediate_recall = 1.0 if intermediate_restored else 0.0
    chain_recall = 1.0 if chain_restored else 0.0

    if restoration_count > 0:
        revision_precision = true_revision_count / restoration_count
        false_revision_rate = false_revision_count / restoration_count
    else:
        revision_precision = 0.0
        false_revision_rate = 0.0

    return {
        "condition": condition,
        "seed": seed,
        "root_in_cold": root_in_cold,
        "intermediate_in_cold": inter_in_cold,
        "root_in_hot": root_in_hot,
        "intermediate_in_hot": inter_in_hot,
        "root_restored": root_restored,
        "intermediate_restored": intermediate_restored,
        "chain_restored": chain_restored,
        "root_recall": root_recall,
        "intermediate_recall": intermediate_recall,
        "chain_recall": chain_recall,
        "restoration_count": restoration_count,
        "true_revision_count": true_revision_count,
        "false_revision_count": false_revision_count,
        "revision_precision": revision_precision,
        "false_revision_rate": false_revision_rate,
        "cold_size": len(cold.records),
        "latency_ms": elapsed_ms,
    }


def run_exp_c_suite(seeds: list[int] = [101, 202, 303]) -> dict[str, list[dict[str, Any]]]:
    conditions = ["C0_current_discard", "C1_only_causal_intermediate", "C2_high_value_discard"]
    results: dict[str, list[dict[str, Any]]] = {c: [] for c in conditions}
    for c in conditions:
        for s in seeds:
            results[c].append(run_exp_c_experiment(condition=c, seed=s))
    return results


if __name__ == "__main__":
    res = run_exp_c_suite([999])
    print("Exp C smoke run passed.")
