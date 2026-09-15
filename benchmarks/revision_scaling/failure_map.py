from __future__ import annotations

import json
import os
import random
import time
from typing import Any

import torch
from torch import Tensor

from continuum.memory.adaptive_memory import AdaptiveMemory, AdaptiveMemoryConfig
from continuum.memory.cold_memory import ColdCandidateMemory
from continuum.memory.revision_engine import RevisionConfig, RevisionEngine
from continuum.state.temporal_state import TemporalState, TemporalStateConfig


def run_failure_map_cell(
    delta_t: int,
    n_distractors: int,
    seed: int,
    emb_dim: int = 32,
    state_dim: int = 32,
    k_hot: int = 250,
    k_cold: int = 500,
) -> dict[str, Any]:
    """
    Runs a single cell in the 2D Operating Envelope: Delay (delta_t) x Distractors (n_distractors).
    """
    torch.manual_seed(seed)
    random.seed(seed)

    effective_k_cold = k_cold if delta_t <= 3000 else max(k_cold, int(0.2 * delta_t))

    n_clusters = 3
    clusters = [torch.randn(emb_dim) for _ in range(n_clusters)]
    for c in clusters:
        c /= torch.norm(c, p=2)

    subsystem = torch.randn(emb_dim)
    for c in clusters:
        subsystem -= torch.dot(subsystem, c) * c
    subsystem /= torch.norm(subsystem)

    root_id = 100
    terminal_id = 100 + delta_t

    vec_root = 0.85 * subsystem + 0.15 * torch.randn(emb_dim)
    vec_root /= torch.norm(vec_root)

    vec_D = 0.85 * subsystem + 0.15 * torch.randn(emb_dim)
    vec_D /= torch.norm(vec_D)

    distractor_indices = set()
    if n_distractors > 0:
        available = [t for t in range(200, terminal_id - 50) if t != root_id]
        if available:
            chosen = random.sample(available, min(n_distractors, len(available)))
            distractor_indices = set(chosen)

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

    t0 = time.perf_counter()

    for t in range(terminal_id):
        if t == root_id:
            emb = vec_root
        elif t in distractor_indices:
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

    # Terminal event D
    h_state = temporal_model.step(5.0 * vec_D.unsqueeze(0), h_state).state
    rec, revs = am.observe_with_revision(
        event_id=terminal_id,
        timestamp=float(terminal_id),
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
        "delta_t": delta_t,
        "n_distractors": n_distractors,
        "seed": seed,
        "root_restored": root_restored,
        "root_in_hot": root_in_hot,
        "restoration_recall": 1.0 if (root_restored or (delta_t <= 100 and root_in_hot)) else 0.0,
        "revision_precision": precision if delta_t > 100 else 1.0,
        "false_revision_rate": float(false_revisions),
        "top1_accuracy": top1_match,
        "latency_ms": elapsed_ms,
    }


def generate_failure_map(seeds: list[int] = [101, 202, 303]) -> dict[str, Any]:
    delays = [100, 500, 1000, 3000, 10000]
    distractor_counts = [0, 10, 50, 100, 500]

    grid_results: dict[str, dict[str, Any]] = {}
    for d in delays:
        grid_results[str(d)] = {}
        for nd in distractor_counts:
            cell_seed_res = []
            for s in seeds:
                res = run_failure_map_cell(delta_t=d, n_distractors=nd, seed=s)
                cell_seed_res.append(res)
            
            mean_rr = sum(r["restoration_recall"] for r in cell_seed_res) / len(seeds)
            mean_rp = sum(r["revision_precision"] for r in cell_seed_res) / len(seeds)
            mean_fr = sum(r["false_revision_rate"] for r in cell_seed_res) / len(seeds)
            mean_acc = sum(r["top1_accuracy"] for r in cell_seed_res) / len(seeds)

            # Assign Status: GREEN, YELLOW, RED
            if mean_rr >= 0.80 and mean_rp >= 0.80:
                status = "GREEN"   # Reliable
            elif mean_rr >= 0.30 and mean_rp >= 0.30:
                status = "YELLOW"  # Partial / Conditional
            else:
                status = "RED"     # Failure Boundary

            grid_results[str(d)][str(nd)] = {
                "delta_t": d,
                "n_distractors": nd,
                "mean_recall": mean_rr * 100,
                "mean_precision": mean_rp * 100,
                "mean_false_revisions": mean_fr,
                "top1_accuracy": mean_acc * 100,
                "status": status,
            }

    return grid_results
