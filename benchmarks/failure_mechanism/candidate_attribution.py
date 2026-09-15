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


def run_candidate_attribution_experiment(
    condition: str,  # 'clean_chain_L3', 'distractor_500', 'delay_1000'
    seed: int,
    emb_dim: int = 32,
    state_dim: int = 32,
    stream_length: int = 3000,
) -> dict[str, Any]:
    """
    Experiment A: Candidate Attribution Audit.
    Traces exact fate of root cause vs decoys:
    - Did root enter cold memory?
    - What was its raw cosine similarity rank in cold memory?
    - Did it enter Top-K (=100) search candidates?
    - What was its final RevisionScore and rank after scoring?
    - Who won Top-1 restoration and what was the margin?
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

    chain_nodes: dict[int, Tensor] = {root_id: vec_root}
    distractor_indices: set[int] = set()

    if condition == 'clean_chain_L3':
        # A -> B -> D (L=3)
        b_id = (stream_length + root_id) // 2  # 1550
        vec_b = 0.80 * subsystem + 0.20 * torch.randn(emb_dim)
        vec_b /= torch.norm(vec_b)
        chain_nodes[b_id] = vec_b
    elif condition == 'distractor_500':
        available = [t for t in range(200, stream_length - 50) if t != root_id]
        chosen = random.sample(available, min(500, len(available)))
        distractor_indices = set(chosen)
    elif condition == 'delay_1000':
        # Direct A -> D with stream_length = 1100 (so delta_t = 1000)
        stream_length = 1100

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
        elif t in distractor_indices:
            emb = 0.35 * vec_terminal + 0.65 * torch.randn(emb_dim)
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

    # Prepare terminal event
    h_state = temporal_model.step(5.0 * vec_terminal.unsqueeze(0), h_state).state
    terminal_id = stream_length
    terminal_ts = float(terminal_id)
    terminal_emb = vec_terminal
    terminal_state = h_state[0]

    # Detailed audit of Cold Memory before revision execution
    root_in_cold = any(r.event_id == root_id for r in cold.records)
    root_record: ColdCandidateRecord | None = None
    for r in cold.records:
        if r.event_id == root_id:
            root_record = r
            break

    # 1. Raw Cosine Similarity Search over entire cold memory
    all_sims: list[tuple[int, float, ColdCandidateRecord]] = []
    if cold.embeddings_tensor is not None and len(cold.records) > 0:
        q = terminal_emb / torch.norm(terminal_emb, p=2)
        sim_tensor = torch.mv(cold.embeddings_tensor, q)
        for idx, rec in enumerate(cold.records):
            all_sims.append((rec.event_id, float(sim_tensor[idx].item()), rec))
    
    all_sims.sort(key=lambda x: x[1], reverse=True)
    raw_sim_ranks = {rec_id: rank + 1 for rank, (rec_id, _, _) in enumerate(all_sims)}
    root_raw_sim_rank = raw_sim_ranks.get(root_id, -1)

    # 2. Search candidates returned by cold_memory.search(top_k=100)
    top100_candidates = cold.search(terminal_emb, top_k=min(100, len(cold.records)))
    top100_ids = [cand.event_id for cand, _ in top100_candidates]
    root_in_top100 = root_id in top100_ids

    # 3. Full Revision Scoring over ALL cold records for forensic diagnosis
    all_scored = []
    for rec in cold.records:
        score, comps = engine._compute_revision_score_with_components(
            rec, terminal_emb, terminal_state, terminal_ts
        )
        c_type = "background"
        if rec.event_id == root_id:
            c_type = "true_root"
        elif rec.event_id in chain_nodes:
            c_type = "intermediate_hop"
        elif rec.event_id in distractor_indices:
            c_type = "distractor"
        all_scored.append({
            "event_id": rec.event_id,
            "type": c_type,
            "revision_score": score,
            "components": comps,
            "in_top100_search": rec.event_id in top100_ids,
        })

    all_scored.sort(key=lambda x: x["revision_score"], reverse=True)
    score_ranks = {item["event_id"]: rank + 1 for rank, item in enumerate(all_scored)}
    root_score_rank = score_ranks.get(root_id, -1)

    root_score_data = next((item for item in all_scored if item["event_id"] == root_id), None)
    top1_data = all_scored[0] if all_scored else None

    # Execute standard observe_with_revision to observe live system decision
    rec, revs = am.observe_with_revision(
        event_id=terminal_id,
        timestamp=terminal_ts,
        embedding=terminal_emb,
        temporal_state=terminal_state,
        cold_memory=cold,
        revision_engine=engine,
    )

    restored_ids = [r.candidate.event_id for r in revs if r.decision == "restore"]
    root_restored = root_id in restored_ids

    elapsed_ms = (time.perf_counter() - t0) * 1000

    return {
        "condition": condition,
        "seed": seed,
        "root_id": root_id,
        "root_in_cold": root_in_cold,
        "root_raw_sim_rank": root_raw_sim_rank,
        "root_in_top100": root_in_top100,
        "root_score_rank": root_score_rank,
        "root_revision_score": root_score_data["revision_score"] if root_score_data else 0.0,
        "root_components": root_score_data["components"] if root_score_data else {},
        "top1_winner_id": top1_data["event_id"] if top1_data else None,
        "top1_winner_type": top1_data["type"] if top1_data else None,
        "top1_winner_score": top1_data["revision_score"] if top1_data else 0.0,
        "top1_winner_components": top1_data["components"] if top1_data else {},
        "margin_to_root": (top1_data["revision_score"] - root_score_data["revision_score"]) if (top1_data and root_score_data) else 0.0,
        "root_restored": root_restored,
        "restored_ids": restored_ids,
        "cold_size": len(cold.records),
        "latency_ms": elapsed_ms,
    }


def run_candidate_attribution_suite(seeds: list[int] = [101, 202, 303]) -> dict[str, Any]:
    conditions = ["clean_chain_L3", "distractor_500", "delay_1000"]
    results_by_cond: dict[str, list[dict[str, Any]]] = {}

    for cond in conditions:
        runs = []
        for s in seeds:
            res = run_candidate_attribution_experiment(condition=cond, seed=s)
            runs.append(res)
        results_by_cond[cond] = runs

    return results_by_cond


if __name__ == "__main__":
    import json
    suite_res = run_candidate_attribution_suite()
    print(json.dumps(suite_res, indent=2))
