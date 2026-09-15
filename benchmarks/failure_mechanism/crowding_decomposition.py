from __future__ import annotations

import math
import random
import time
from typing import Any

import torch
from torch import Tensor

from continuum.memory.adaptive_memory import AdaptiveMemory, AdaptiveMemoryConfig
from continuum.memory.cold_memory import ColdCandidateMemory, ColdCandidateRecord
from continuum.memory.revision_engine import RevisionConfig, RevisionEngine
from continuum.state.temporal_state import TemporalState, TemporalStateConfig


def run_crowding_decomposition_experiment(
    distractor_type: str,  # 'type1_sim_only', 'type2_state_only', 'type3_temporal_only', 'type4_random', 'type5_sim_and_state'
    n_distractors: int,
    seed: int,
    emb_dim: int = 32,
    state_dim: int = 32,
    stream_length: int = 3000,
) -> dict[str, Any]:
    """
    Experiment C: Crowding Factorial Decomposition.
    Dissects which feature dimension fools the Revision Judge:
    - Type 1: High Similarity Only (0.85 cos to D, random independent state)
    - Type 2: High State Compatibility Only (orthogonal embedding to D, aligned state)
    - Type 3: High Temporal Compatibility Only (random background embedding/state, timestamps close to D: T-100..T)
    - Type 4: Random Noise (independent random vectors across emb, state, ts)
    - Type 5: Dual Decoy (High Similarity + High State Compatibility)
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

    vec_terminal = 0.85 * subsystem + 0.15 * torch.randn(emb_dim)
    vec_terminal /= torch.norm(vec_terminal)

    # Distractor timestamps selection
    distractor_indices = set()
    if n_distractors > 0:
        if distractor_type == "type3_temporal_only":
            # Distractors packed tightly in the recent window [stream_length-150, stream_length-10]
            pool = list(range(max(200, stream_length - 200), stream_length - 5))
            chosen = random.sample(pool, min(n_distractors, len(pool)))
            distractor_indices = set(chosen)
        else:
            # Spread across stream
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
            if distractor_type == "type1_sim_only":
                # High similarity to D, independent state
                emb = 0.85 * vec_terminal + 0.15 * torch.randn(emb_dim)
                emb /= torch.norm(emb, p=2)
            elif distractor_type == "type2_state_only":
                # Orthogonal to D
                orth = torch.randn(emb_dim)
                orth -= torch.dot(orth, vec_terminal) * vec_terminal
                orth /= torch.norm(orth, p=2)
                emb = orth
            elif distractor_type == "type3_temporal_only":
                # Background cluster embedding, but timestamp close to D
                c_idx = (t // 25) % n_clusters
                emb = clusters[c_idx] + 0.03 * torch.randn(emb_dim)
                emb /= torch.norm(emb, p=2)
            elif distractor_type == "type4_random":
                # Pure isotropic noise
                emb = torch.randn(emb_dim)
                emb /= torch.norm(emb, p=2)
            elif distractor_type == "type5_sim_and_state":
                # Aligned to terminal subspace
                emb = 0.85 * vec_terminal + 0.15 * torch.randn(emb_dim)
                emb /= torch.norm(emb, p=2)
            else:
                emb = torch.randn(emb_dim)
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

    # Terminal trigger
    h_state = temporal_model.step(5.0 * vec_terminal.unsqueeze(0), h_state).state
    rec, revs = am.observe_with_revision(
        event_id=stream_length,
        timestamp=float(stream_length),
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
        "distractor_type": distractor_type,
        "n_distractors": n_distractors,
        "seed": seed,
        "root_restored": root_restored,
        "root_in_hot": root_in_hot,
        "restoration_recall": 1.0 if root_restored else 0.0,
        "revision_precision": precision,
        "false_revision_rate": float(false_revisions),
        "top1_accuracy": top1_match,
        "latency_ms": elapsed_ms,
        "cold_slots_used": len(cold.records),
    }


def run_crowding_decomposition_suite(
    seeds: list[int] = [101, 202, 303],
    distractor_counts: list[int] = [0, 10, 50, 100, 500],
) -> dict[str, dict[int, list[dict[str, Any]]]]:
    types = [
        "type1_sim_only",
        "type2_state_only",
        "type3_temporal_only",
        "type4_random",
        "type5_sim_and_state",
    ]
    results: dict[str, dict[int, list[dict[str, Any]]]] = {t: {} for t in types}

    for t_name in types:
        for n in distractor_counts:
            runs = []
            for s in seeds:
                runs.append(run_crowding_decomposition_experiment(
                    distractor_type=t_name,
                    n_distractors=n,
                    seed=s,
                ))
            results[t_name][n] = runs

    return results


if __name__ == "__main__":
    import json
    suite_res = run_crowding_decomposition_suite(seeds=[999], distractor_counts=[0, 50, 500])
    print("Crowding decomposition smoke completed.")
