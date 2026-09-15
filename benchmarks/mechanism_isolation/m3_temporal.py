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


class CustomDecayRevisionEngine(RevisionEngine):
    """
    RevisionEngine variant allowing isolated evaluation of temporal decay:
    - variant='M3-A_current': standard exp(-delta_t / tau)
    - variant='M3-B_no_decay': temporal_compat = 1.0 (decay disabled)
    """
    def __init__(self, config: RevisionConfig, variant: str = "M3-A_current"):
        super().__init__(config=config)
        self.variant = variant

    def _compute_revision_score_with_components(
        self, candidate: ColdCandidateRecord, trigger_embedding: Tensor,
        trigger_state: Tensor, trigger_timestamp: float
    ) -> tuple[float, dict[str, float]]:
        # Cosine similarity
        with torch.no_grad():
            sim = float(torch.dot(candidate.compressed_embedding, trigger_embedding).item())
            sim = max(0.0, min(1.0, sim))

        # State compatibility
        c_state = candidate.state_fingerprint.clone()
        t_state = trigger_state.detach().float()
        norm_c = torch.norm(c_state, p=2)
        if norm_c > 1e-8:
            c_state = c_state / norm_c
        norm_ts = torch.norm(t_state, p=2)
        if norm_ts > 1e-8:
            t_state = t_state / norm_ts

        with torch.no_grad():
            state_compat = float(torch.dot(c_state, t_state).item())
            state_compat = max(0.0, min(1.0, state_compat))

        # Temporal compatibility under isolation
        delta_t = abs(trigger_timestamp - candidate.timestamp)
        if self.variant == "M3-B_no_decay":
            temporal_compat = 1.0
        else:  # M3-A_current
            temporal_compat = math.exp(-delta_t / self.config.temporal_decay_tau)

        provenance_compat = 0.5

        score = (
            self.config.w_sim * sim +
            self.config.w_state_compat * state_compat +
            self.config.w_temporal_compat * temporal_compat +
            self.config.w_provenance_compat * provenance_compat
        )

        components = {
            "sim": sim,
            "state_compat": state_compat,
            "temporal_compat": temporal_compat,
            "provenance_compat": provenance_compat,
            "delta_t": delta_t,
        }
        return score, components


def run_m3_experiment(
    variant: str,  # 'M3-A_current' or 'M3-B_no_decay'
    chain_length: int,  # L in [2, 3, 4, 5, 6]
    seed: int,
    emb_dim: int = 32,
    state_dim: int = 32,
    stream_length: int = 3000,
) -> dict[str, Any]:
    """
    M3 — Temporal Causality Isolation Experiment
    Identical candidate pool across causal chains of length L.
    Compares:
      M3-A Current Temporal Decay: exp(-delta_t / 1000)
      M3-B No Temporal Decay: temporal_compat = 1.0
    Measures:
      candidate_id, causal_role, hop_distance, cosine_sim, state_score, temporal_score, final_score, rank, restored
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

    chain_nodes: dict[int, dict[str, Any]] = {}
    num_intermediates = chain_length - 2
    step_gap = (stream_length - 100) // (num_intermediates + 1) if num_intermediates > 0 else 0

    for i in range(num_intermediates):
        hop_t = 100 + (i + 1) * step_gap
        decay = 0.85 - 0.05 * (i + 1)
        v_hop = decay * subsystem + (1.0 - decay) * torch.randn(emb_dim)
        v_hop /= torch.norm(v_hop)
        node_letter = chr(ord('B') + i)
        chain_nodes[hop_t] = {
            "event_id": hop_t,
            "embedding": v_hop,
            "role": f"Intermediate_{node_letter}",
            "hop_from_terminal": (num_intermediates - i),
        }

    chain_nodes[root_id] = {
        "event_id": root_id,
        "embedding": vec_root,
        "role": "Root_A",
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
    engine = CustomDecayRevisionEngine(
        RevisionConfig(
            theta_trigger=0.45,
            theta_restore=0.25,
            max_restorations_per_trigger=1,
        ),
        variant=variant,
    )

    t0 = time.perf_counter()
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

    # Score all candidates in cold memory
    cold_records_by_id = {r.event_id: r for r in cold.records}
    all_scored = []
    for r in cold.records:
        sc, comp = engine._compute_revision_score_with_components(
            r, terminal_emb, terminal_state, terminal_ts
        )
        c_role = "Distractor_Background"
        c_hop = -1
        if r.event_id in chain_nodes:
            c_role = chain_nodes[r.event_id]["role"]
            c_hop = chain_nodes[r.event_id]["hop_from_terminal"]

        all_scored.append({
            "candidate_id": r.event_id,
            "causal_role": c_role,
            "hop_distance": c_hop,
            "cosine_similarity": comp["sim"],
            "state_score": comp["state_compat"],
            "temporal_score": comp["temporal_compat"],
            "delta_t": comp["delta_t"],
            "final_score": sc,
            "record": r,
        })

    all_scored.sort(key=lambda x: x["final_score"], reverse=True)
    ranks_by_eid = {item["candidate_id"]: rank_idx + 1 for rank_idx, item in enumerate(all_scored)}
    for rank_idx, item in enumerate(all_scored):
        item["rank"] = rank_idx + 1

    # Execute actual observe_with_revision
    rec_d, revs = am.observe_with_revision(
        event_id=terminal_id,
        timestamp=terminal_ts,
        embedding=terminal_emb,
        temporal_state=terminal_state,
        cold_memory=cold,
        revision_engine=engine,
    )

    restored_ids = {r.candidate.event_id for r in revs if r.decision == "restore"}
    for item in all_scored:
        item["restored"] = item["candidate_id"] in restored_ids
        del item["record"]  # remove non-serializable object

    root_restored = root_id in restored_ids
    root_item = next((item for item in all_scored if item["candidate_id"] == root_id), None)
    root_rank = root_item["rank"] if root_item else -1
    root_score = root_item["final_score"] if root_item else 0.0

    # Build consistent chain_nodes_audit for all defined chain nodes (even if not in cold)
    # Sorted from closest to terminal (hop_distance=1) to root
    sorted_node_metas = sorted(chain_nodes.values(), key=lambda x: x["hop_from_terminal"])
    chain_nodes_audit = []
    for n_meta in sorted_node_metas:
        eid = n_meta["event_id"]
        role = n_meta["role"]
        h_dist = n_meta["hop_from_terminal"]

        if eid in cold_records_by_id:
            c_item = next((it for it in all_scored if it["candidate_id"] == eid), None)
            chain_nodes_audit.append({
                "candidate_id": eid,
                "causal_role": role,
                "hop_distance": h_dist,
                "in_cold": True,
                "cosine_similarity": c_item["cosine_similarity"],
                "state_score": c_item["state_score"],
                "temporal_score": c_item["temporal_score"],
                "delta_t": c_item["delta_t"],
                "final_score": c_item["final_score"],
                "rank": c_item["rank"],
                "restored": c_item["restored"],
            })
        else:
            # Theoretical score against terminal
            emb = n_meta["embedding"]
            st = node_states.get(eid, torch.zeros(state_dim))
            ts = float(eid)
            sim = float(torch.dot(emb, terminal_emb).item())
            norm_st = torch.norm(st, p=2)
            norm_tst = torch.norm(terminal_state, p=2)
            state_compat = float(torch.dot(st / norm_st, terminal_state / norm_tst).item()) if (norm_st > 1e-8 and norm_tst > 1e-8) else 0.0
            dt = abs(terminal_ts - ts)
            temp_sc = 1.0 if variant == "M3-B_no_decay" else math.exp(-dt / engine.config.temporal_decay_tau)
            sc = 0.4 * max(0.0, sim) + 0.3 * max(0.0, state_compat) + 0.2 * temp_sc + 0.1 * 0.5
            chain_nodes_audit.append({
                "candidate_id": eid,
                "causal_role": role,
                "hop_distance": h_dist,
                "in_cold": False,
                "cosine_similarity": max(0.0, sim),
                "state_score": max(0.0, state_compat),
                "temporal_score": temp_sc,
                "delta_t": dt,
                "final_score": sc,
                "rank": -1,
                "restored": False,
            })

    elapsed_ms = (time.perf_counter() - t0) * 1000

    return {
        "variant": variant,
        "chain_length": chain_length,
        "seed": seed,
        "root_restored": root_restored,
        "root_rank": root_rank,
        "root_score": root_score,
        "restored_ids": list(restored_ids),
        "candidates_audit": all_scored[:15],
        "chain_nodes_audit": chain_nodes_audit,
        "latency_ms": elapsed_ms,
    }


def run_m3_suite(seeds: list[int] = [101, 202, 303]) -> dict[str, dict[int, list[dict[str, Any]]]]:
    variants = ["M3-A_current", "M3-B_no_decay"]
    chain_lengths = [2, 3, 4, 5, 6]
    results: dict[str, dict[int, list[dict[str, Any]]]] = {v: {} for v in variants}

    for v in variants:
        for L in chain_lengths:
            runs = []
            for s in seeds:
                runs.append(run_m3_experiment(variant=v, chain_length=L, seed=s))
            results[v][L] = runs
    return results


if __name__ == "__main__":
    res = run_m3_suite([999])
    print("M3 smoke test passed.")
