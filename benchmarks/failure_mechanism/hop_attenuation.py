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


def run_hop_attenuation_experiment(
    chain_length: int,
    seed: int,
    emb_dim: int = 32,
    state_dim: int = 32,
    stream_length: int = 3000,
) -> dict[str, Any]:
    """
    Experiment B: Hop Attenuation Audit.
    For causal chains A -> ... -> D of length L (L in [2, 3, 4, 5, 6]),
    measures the attenuation curve of:
    - Cosine similarity to terminal D
    - Dynamical State compatibility to terminal D
    - Temporal compatibility e^(-delta_t / tau)
    - Full RevisionScore
    - Candidate rank in Cold Memory
    - Retention status (Hot, Cold, Evicted)
    - Restoration probability
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

    # Chain node mapping: hop_index -> (event_id, embedding, label)
    # hop_index = 0 is immediate predecessor to terminal D
    # hop_index = L-2 is root A
    chain_nodes: dict[int, dict[str, Any]] = {}
    
    num_intermediates = chain_length - 2
    step_gap = (stream_length - 100) // (num_intermediates + 1) if num_intermediates > 0 else 0

    # Intermediate nodes
    for i in range(num_intermediates):
        hop_t = 100 + (i + 1) * step_gap
        decay = 0.85 - 0.05 * (i + 1)
        v_hop = decay * subsystem + (1.0 - decay) * torch.randn(emb_dim)
        v_hop /= torch.norm(v_hop)
        
        # Label: node index from root (0=A, 1=B, 2=C, etc.)
        node_letter = chr(ord('B') + i)
        chain_nodes[hop_t] = {
            "event_id": hop_t,
            "embedding": v_hop,
            "label": node_letter,
            "hop_from_root": i + 1,
            "hop_from_terminal": (num_intermediates - i),
        }

    # Root node
    chain_nodes[root_id] = {
        "event_id": root_id,
        "embedding": vec_root,
        "label": "A (Root)",
        "hop_from_root": 0,
        "hop_from_terminal": num_intermediates + 1,
    }

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

    node_states: dict[int, Tensor] = {}

    for t in range(stream_length):
        if t in chain_nodes:
            emb = chain_nodes[t]["embedding"]
        else:
            c_idx = (t // 25) % n_clusters
            emb = clusters[c_idx] + 0.03 * torch.randn(emb_dim)
            emb /= torch.norm(emb, p=2)

        h_state = temporal_model.step(emb.unsqueeze(0), h_state).state
        if t in chain_nodes:
            node_states[t] = h_state[0].clone()

        am.observe(
            event_id=t,
            timestamp=float(t),
            embedding=emb,
            temporal_state=h_state[0],
            cold_memory=cold,
        )

    # Trigger terminal
    h_state = temporal_model.step(5.0 * vec_terminal.unsqueeze(0), h_state).state
    terminal_id = stream_length
    terminal_ts = float(terminal_id)
    terminal_emb = vec_terminal
    terminal_state = h_state[0]

    # Evaluate hop metrics against terminal D
    hop_profiles: list[dict[str, Any]] = []

    # Map cold records for quick lookup
    cold_records_by_id = {r.event_id: r for r in cold.records}
    hot_records_by_id = {r.event_id: r for r in am.records}

    # Score all cold candidates to determine true rank in cold pool
    cold_scores = {}
    for r in cold.records:
        sc, comp = engine._compute_revision_score_with_components(
            r, terminal_emb, terminal_state, terminal_ts
        )
        cold_scores[r.event_id] = (sc, comp)

    sorted_cold = sorted(cold_scores.items(), key=lambda x: x[1][0], reverse=True)
    cold_ranks = {eid: rank + 1 for rank, (eid, _) in enumerate(sorted_cold)}

    # Collect hop data sorted from terminal predecessor (hop_from_terminal=1) to root
    sorted_nodes = sorted(chain_nodes.values(), key=lambda x: x["hop_from_terminal"])

    for node_meta in sorted_nodes:
        eid = node_meta["event_id"]
        emb = node_meta["embedding"]
        st = node_states[eid]
        ts = float(eid)

        # Raw component computation against terminal
        sim = float(torch.dot(emb, terminal_emb).item())
        norm_st = torch.norm(st, p=2)
        norm_tst = torch.norm(terminal_state, p=2)
        state_compat = float(torch.dot(st / norm_st, terminal_state / norm_tst).item())
        delta_t = abs(terminal_ts - ts)
        temporal_compat = math.exp(-delta_t / engine.config.temporal_decay_tau)
        full_score = 0.4 * max(0.0, sim) + 0.3 * max(0.0, state_compat) + 0.2 * temporal_compat + 0.1 * 0.5

        in_hot = eid in hot_records_by_id
        in_cold = eid in cold_records_by_id
        cold_rank = cold_ranks.get(eid, None)
        cold_sc = cold_scores.get(eid, (None, None))[0]

        hop_profiles.append({
            "hop_from_terminal": node_meta["hop_from_terminal"],
            "hop_from_root": node_meta["hop_from_root"],
            "label": node_meta["label"],
            "event_id": eid,
            "timestamp": ts,
            "delta_t": delta_t,
            "cosine_sim": sim,
            "state_compat": state_compat,
            "temporal_compat": temporal_compat,
            "revision_score": full_score,
            "in_hot": in_hot,
            "in_cold": in_cold,
            "cold_rank": cold_rank,
            "cold_score": cold_sc,
        })

    # Execute actual observe_with_revision
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

    return {
        "chain_length": chain_length,
        "seed": seed,
        "root_restored": root_restored,
        "restored_ids": restored_ids,
        "hop_profiles": hop_profiles,
    }


def run_hop_attenuation_suite(seeds: list[int] = [101, 202, 303]) -> dict[int, list[dict[str, Any]]]:
    chain_lengths = [2, 3, 4, 5, 6]
    results_by_length: dict[int, list[dict[str, Any]]] = {}

    for L in chain_lengths:
        runs = []
        for s in seeds:
            runs.append(run_hop_attenuation_experiment(chain_length=L, seed=s))
        results_by_length[L] = runs

    return results_by_length


if __name__ == "__main__":
    import json
    suite_res = run_hop_attenuation_suite()
    print("Hop attenuation runs completed.")
