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


def run_m1_experiment(
    variant: str,  # 'M1-A_current' or 'M1-B_discard_to_cold'
    seed: int,
    emb_dim: int = 32,
    state_dim: int = 32,
    stream_length: int = 3000,
) -> dict[str, Any]:
    """
    M1 — Admission Isolation Experiment
    Evaluates causal chain A -> B -> D (L=3).
    Compares:
      M1-A Current: DISCARD events do not enter cold memory (standard observe).
      M1-B Experimental: DISCARD events are archived to cold memory.
    All other parameters strictly identical.
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

    # Tracking records for A, B, D
    event_tracker: dict[int, dict[str, Any]] = {
        root_id: {"event_id": root_id, "role": "Root (A)", "timestamp": float(root_id)},
        b_id: {"event_id": b_id, "role": "Intermediate (B)", "timestamp": float(b_id)},
        terminal_id: {"event_id": terminal_id, "role": "Terminal (D)", "timestamp": float(terminal_id)},
    }

    cold_eviction_tracker: dict[int, int | None] = {root_id: None, b_id: None}

    # Custom wrapper around cold.archive to track eviction from cold memory
    orig_evict_oldest = cold._evict_oldest
    def tracked_evict_oldest():
        if len(cold.records) > 0:
            evicted_rec = cold.records[0]
            if evicted_rec.event_id in cold_eviction_tracker:
                cold_eviction_tracker[evicted_rec.event_id] = current_step
        orig_evict_oldest()
    cold._evict_oldest = tracked_evict_oldest

    current_step = 0
    for t in range(stream_length):
        current_step = t
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

        if variant == "M1-B_discard_to_cold" and rec.decision == RetentionDecision.DISCARD:
            # M1-B experimental modification: archive discarded event to cold memory
            cold.archive(
                event_id=rec.event_id,
                timestamp=rec.timestamp,
                embedding=rec.embedding,
                temporal_state=h_state[0],
                importance=rec.importance,
                provenance=f"discarded_at_step_{t}",
            )

        if t in event_tracker:
            event_tracker[t]["admission_score"] = float(rec.importance)
            event_tracker[t]["admission_decision"] = rec.decision.value

    # Terminal evidence D at stream_length triggers revision
    current_step = terminal_id
    h_state = temporal_model.step(5.0 * vec_terminal.unsqueeze(0), h_state).state
    rec_d, revs = am.observe_with_revision(
        event_id=terminal_id,
        timestamp=float(terminal_id),
        embedding=vec_terminal,
        temporal_state=h_state[0],
        cold_memory=cold,
        revision_engine=engine,
    )

    event_tracker[terminal_id]["admission_score"] = float(rec_d.importance)
    event_tracker[terminal_id]["admission_decision"] = rec_d.decision.value

    elapsed_ms = (time.perf_counter() - t0) * 1000

    # Evaluate Presence in Hot and Cold
    hot_eids = {r.event_id for r in am.records}
    cold_eids = {r.event_id for r in cold.records}

    for eid in [root_id, b_id]:
        event_tracker[eid]["hot_presence"] = eid in hot_eids
        event_tracker[eid]["cold_presence"] = eid in cold_eids
        event_tracker[eid]["cold_eviction_time"] = cold_eviction_tracker[eid]

    event_tracker[terminal_id]["hot_presence"] = terminal_id in hot_eids
    event_tracker[terminal_id]["cold_presence"] = terminal_id in cold_eids
    event_tracker[terminal_id]["cold_eviction_time"] = None

    # Candidate ranking in cold memory if present
    scored_cold = []
    for r in cold.records:
        sc, comp = engine._compute_revision_score_with_components(
            r, vec_terminal, h_state[0], float(terminal_id)
        )
        scored_cold.append((r.event_id, sc, comp))
    scored_cold.sort(key=lambda x: x[1], reverse=True)
    ranks = {item[0]: rank + 1 for rank, item in enumerate(scored_cold)}
    scores = {item[0]: item[1] for item in scored_cold}

    for eid in [root_id, b_id]:
        event_tracker[eid]["candidate_rank"] = ranks.get(eid, None)
        event_tracker[eid]["candidate_score"] = scores.get(eid, None)

    # Restoration outcomes
    restored_ids = [r.candidate.event_id for r in revs if r.decision == "restore"]
    false_revisions = 0
    true_revisions = 0
    for r_id in restored_ids:
        if r_id in chain_nodes:
            true_revisions += 1
        else:
            false_revisions += 1

    root_restored = root_id in restored_ids
    intermediate_restored = b_id in restored_ids
    chain_restored = root_restored and intermediate_restored

    # Hot Presence check after revision
    root_in_hot = any(r.event_id == root_id for r in am.records)
    intermediate_in_hot = any(r.event_id == b_id for r in am.records)

    for eid in [root_id, b_id]:
        event_tracker[eid]["restored"] = eid in restored_ids

    total_revs = len(restored_ids)
    revision_precision = true_revisions / total_revs if total_revs > 0 else 0.0

    return {
        "variant": variant,
        "seed": seed,
        "root_restored": root_restored,
        "intermediate_restored": intermediate_restored,
        "chain_restored": chain_restored,
        "root_recall": 1.0 if root_restored else 0.0,
        "intermediate_recall": 1.0 if intermediate_restored else 0.0,
        "chain_recall": 1.0 if chain_restored else 0.0,
        "root_in_hot": root_in_hot,
        "intermediate_in_hot": intermediate_in_hot,
        "revision_precision": revision_precision,
        "false_revision_rate": float(false_revisions),
        "restored_ids": restored_ids,
        "event_tracker": event_tracker,
        "cold_slots_used": len(cold.records),
        "latency_ms": elapsed_ms,
    }


def run_m1_suite(seeds: list[int] = [101, 202, 303]) -> dict[str, list[dict[str, Any]]]:
    variants = ["M1-A_current", "M1-B_discard_to_cold"]
    results: dict[str, list[dict[str, Any]]] = {}
    for v in variants:
        runs = []
        for s in seeds:
            runs.append(run_m1_experiment(variant=v, seed=s))
        results[v] = runs
    return results


if __name__ == "__main__":
    import json
    res = run_m1_suite([999])
    print("M1 smoke test passed.")
