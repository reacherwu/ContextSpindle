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


class ExperimentalTemporalRevisionEngine(RevisionEngine):
    """
    Evaluates 3 isolated temporal weighting modes:
    1. 'absolute_dt': Current default: exp(-|t_trigger - t_candidate| / tau), tau=1000
    2. 'no_decay': Temporal compatibility = 1.0 (decay completely removed)
    3. 'hop_conditioned': Decay conditioned on causal topology hop distance from terminal:
         hop = node's hop from terminal (1 for immediate predecessor, 2 for next, etc.)
         For non-chain background events: hop = stream_length // step_gap (penalized as max hops)
         decay = exp(-hop / tau_hop), where tau_hop = 2.0 (pre-registered on dev seed 999)
    """
    def __init__(self, config: RevisionConfig, mode: str = "absolute_dt", tau_hop: float = 2.0):
        super().__init__(config=config)
        self.mode = mode
        self.tau_hop = tau_hop

    def _compute_revision_score_with_components(
        self, candidate: ColdCandidateRecord, trigger_embedding: Tensor,
        trigger_state: Tensor, trigger_timestamp: float,
        hop_distance_map: dict[int, int] | None = None,
        max_hops: int = 5,
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

        delta_t = abs(trigger_timestamp - candidate.timestamp)

        # Isolated temporal mode
        if self.mode == "no_decay":
            temporal_compat = 1.0
            hop_val = 0
        elif self.mode == "hop_conditioned":
            if hop_distance_map is not None and candidate.event_id in hop_distance_map:
                hop_val = hop_distance_map[candidate.event_id]
            else:
                # Irrelevant background event treated as max_hops + 1
                hop_val = max_hops + 1
            temporal_compat = math.exp(-hop_val / self.tau_hop)
        else:  # absolute_dt (current default)
            temporal_compat = math.exp(-delta_t / self.config.temporal_decay_tau)
            hop_val = hop_distance_map.get(candidate.event_id, -1) if hop_distance_map else -1

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
            "hop": hop_val,
        }
        return score, components


def run_exp_b_experiment(
    mode: str,  # 'absolute_dt', 'no_decay', 'hop_conditioned'
    chain_length: int,  # L in [2, 3, 4, 5, 6]
    seed: int,
    emb_dim: int = 32,
    state_dim: int = 32,
    stream_length: int = 3000,
    tau_hop: float = 2.0,  # pre-registered on dev seed 999
) -> dict[str, Any]:
    """
    M2.9.2-B: Temporal Decay Mechanism Isolation.
    Compares absolute_dt vs no_decay vs hop_conditioned decay.
    Evaluates:
      Root score, Intermediate score, Decoy score, Root rank, Intermediate rank, Recall, Precision, False revision rate.
    Special query: Does hop-conditioned decay suppress old irrelevant background better than no-decay?
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

    hop_distance_map = {eid: meta["hop_from_terminal"] for eid, meta in chain_nodes.items()}
    max_hops = max(hop_distance_map.values())

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
    engine = ExperimentalTemporalRevisionEngine(
        RevisionConfig(
            theta_trigger=0.45,
            theta_restore=0.25,
            max_restorations_per_trigger=1,
        ),
        mode=mode,
        tau_hop=tau_hop,
    )

    t0 = time.perf_counter()

    for t in range(stream_length):
        if t in chain_nodes:
            emb = chain_nodes[t]["embedding"]
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

    # Terminal evidence trigger
    h_state = temporal_model.step(5.0 * vec_terminal.unsqueeze(0), h_state).state
    terminal_id = stream_length
    terminal_ts = float(terminal_id)
    terminal_emb = vec_terminal
    terminal_state = h_state[0]

    # Score all candidates in cold memory
    all_scored = []
    for r in cold.records:
        sc, comp = engine._compute_revision_score_with_components(
            r, terminal_emb, terminal_state, terminal_ts,
            hop_distance_map=hop_distance_map,
            max_hops=max_hops,
        )
        c_role = "Background_Decoy"
        c_hop = comp["hop"]
        if r.event_id in chain_nodes:
            c_role = chain_nodes[r.event_id]["role"]

        all_scored.append({
            "candidate_id": r.event_id,
            "causal_role": c_role,
            "hop": c_hop,
            "cosine_similarity": comp["sim"],
            "state_score": comp["state_compat"],
            "temporal_score": comp["temporal_compat"],
            "delta_t": comp["delta_t"],
            "final_score": sc,
            "timestamp": r.timestamp,
        })

    all_scored.sort(key=lambda x: x["final_score"], reverse=True)
    for rank_idx, item in enumerate(all_scored):
        item["rank"] = rank_idx + 1

    # Extract Key Candidates
    root_item = next((item for item in all_scored if item["candidate_id"] == root_id), None)
    root_rank = root_item["rank"] if root_item else -1
    root_score = root_item["final_score"] if root_item else 0.0

    # Best intermediate candidate
    intermediate_items = [item for item in all_scored if "Intermediate" in item["causal_role"]]
    best_intermediate = intermediate_items[0] if intermediate_items else None
    inter_rank = best_intermediate["rank"] if best_intermediate else -1
    inter_score = best_intermediate["final_score"] if best_intermediate else 0.0

    # Decoys
    decoys = [item for item in all_scored if item["causal_role"] == "Background_Decoy"]
    best_decoy = decoys[0] if decoys else None
    best_decoy_score = best_decoy["final_score"] if best_decoy else 0.0
    best_decoy_rank = best_decoy["rank"] if best_decoy else -1

    # Old irrelevant background (defined as t < 1000)
    old_decoys = [item for item in decoys if item["timestamp"] < 1000]
    mean_old_decoy_score = float(torch.tensor([d["final_score"] for d in old_decoys]).mean().item()) if old_decoys else 0.0

    # Restoration decision (Top-1 if > theta_restore)
    restored_ids = []
    if len(all_scored) > 0 and all_scored[0]["final_score"] > engine.config.theta_restore:
        restored_ids.append(all_scored[0]["candidate_id"])

    restoration_count = len(restored_ids)
    true_revision_count = sum(1 for eid in restored_ids if eid == root_id)
    false_revision_count = sum(1 for eid in restored_ids if eid != root_id)

    root_restored = root_id in restored_ids
    restoration_recall = 1.0 if root_restored else 0.0

    if restoration_count > 0:
        revision_precision = true_revision_count / restoration_count
        false_revision_rate = false_revision_count / restoration_count
    else:
        revision_precision = 0.0
        false_revision_rate = 0.0

    elapsed_ms = (time.perf_counter() - t0) * 1000

    return {
        "mode": mode,
        "chain_length": chain_length,
        "seed": seed,
        "root_score": root_score,
        "root_rank": root_rank,
        "intermediate_score": inter_score,
        "intermediate_rank": inter_rank,
        "best_decoy_score": best_decoy_score,
        "best_decoy_rank": best_decoy_rank,
        "mean_old_decoy_score": mean_old_decoy_score,
        "restoration_recall": restoration_recall,
        "restoration_count": restoration_count,
        "true_revision_count": true_revision_count,
        "false_revision_count": false_revision_count,
        "revision_precision": revision_precision,
        "false_revision_rate": false_revision_rate,
        "latency_ms": elapsed_ms,
    }


def run_exp_b_suite(seeds: list[int] = [101, 202, 303]) -> dict[str, dict[int, list[dict[str, Any]]]]:
    modes = ["absolute_dt", "no_decay", "hop_conditioned"]
    chain_lengths = [2, 3, 4, 5, 6]
    results: dict[str, dict[int, list[dict[str, Any]]]] = {m: {} for m in modes}
    for m in modes:
        for L in chain_lengths:
            runs = []
            for s in seeds:
                runs.append(run_exp_b_experiment(mode=m, chain_length=L, seed=s))
            results[m][L] = runs
    return results


if __name__ == "__main__":
    res = run_exp_b_suite([999])
    print("Exp B smoke run passed.")
