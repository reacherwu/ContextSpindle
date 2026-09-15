"""WP-R6: Vectorized Revision Engine Optimization & Latency Benchmark."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import torch
from torch import Tensor

from continuum.memory.cold_memory import ColdCandidateRecord
from continuum.memory.revision_engine import RevisionConfig, RevisionEngine


class VectorizedRevisionEngine:
    """
    Vectorized PyTorch implementation of RevisionEngine scoring.
    Computes exact scores for N candidates in a single batch tensor pass.
    Zero loop overhead, exact numerical parity with RevisionEngine.
    """
    def __init__(self, config: RevisionConfig):
        self.config = config

    def score_batch(
        self,
        embeddings: Tensor,       # [N, D] normalized
        states: Tensor,           # [N, H] normalized
        timestamps: Tensor,       # [N]
        provenances: Tensor,      # [N]
        query_embedding: Tensor,  # [D] normalized
        query_state: Tensor,      # [H] normalized
        current_time: float,
    ) -> tuple[Tensor, dict[str, Tensor]]:
        # 1. Semantic similarity: [N]
        sim = torch.mv(embeddings, query_embedding)
        sim_clamped = torch.clamp(sim, 0.0, 1.0)

        # 2. State compatibility: [N]
        state_sim = torch.mv(states, query_state)
        state_clamped = torch.clamp(state_sim, 0.0, 1.0)

        # 3. Temporal compatibility: [N]
        delta_t = torch.abs(current_time - timestamps)
        temporal_compat = torch.exp(-delta_t / self.config.temporal_decay_tau)

        # 4. Provenance: [N]
        prov_compat = provenances

        # Weighted combination: [N]
        total_score = (
            self.config.w_sim * sim_clamped
            + self.config.w_state_compat * state_clamped
            + self.config.w_temporal_compat * temporal_compat
            + self.config.w_provenance_compat * prov_compat
        )

        components = {
            "sim": sim_clamped,
            "state_compat": state_clamped,
            "temporal_compat": temporal_compat,
            "provenance_compat": prov_compat,
        }
        return total_score, components


def run_wp_r6() -> dict[str, Any]:
    torch.manual_seed(42)
    n_candidates = 500
    emb_dim = 32
    state_dim = 32

    cfg = RevisionConfig()
    loop_engine = RevisionEngine(cfg)
    vec_engine = VectorizedRevisionEngine(cfg)

    records: list[ColdCandidateRecord] = []
    emb_list = []
    state_list = []
    ts_list = []
    prov_num_list = []

    for i in range(n_candidates):
        emb = torch.randn(emb_dim)
        emb /= torch.norm(emb, p=2)
        st = torch.randn(state_dim)
        st /= torch.norm(st, p=2)
        ts = float(i * 5)
        prov = "cold_admission"

        rec = ColdCandidateRecord(
            event_id=i,
            timestamp=ts,
            compressed_embedding=emb,
            state_fingerprint=st,
            importance_at_eviction=0.5,
            provenance_summary=prov,
        )
        records.append(rec)
        emb_list.append(emb)
        state_list.append(st)
        ts_list.append(ts)
        prov_num_list.append(0.5)

    # Batch tensors
    E = torch.stack(emb_list)
    H = torch.stack(state_list)
    T = torch.tensor(ts_list, dtype=torch.float32)
    P = torch.tensor(prov_num_list, dtype=torch.float32)

    q_emb = torch.randn(emb_dim)
    q_emb /= torch.norm(q_emb, p=2)
    q_st = torch.randn(state_dim)
    q_st /= torch.norm(q_st, p=2)
    curr_t = 3000.0

    # 1. Numerical Parity Check
    loop_scores = []
    for r in records:
        sc, _ = loop_engine._compute_revision_score_with_components(r, q_emb, q_st, curr_t)
        loop_scores.append(sc)
    loop_tensor = torch.tensor(loop_scores, dtype=torch.float32)

    vec_scores, _ = vec_engine.score_batch(E, H, T, P, q_emb, q_st, curr_t)
    max_diff = torch.max(torch.abs(loop_tensor - vec_scores)).item()

    # 2. Timing Benchmark (Warmup + 200 iterations)
    n_iters = 200

    # Loop benchmark
    for _ in range(10):
        for r in records:
            _ = loop_engine._compute_revision_score_with_components(r, q_emb, q_st, curr_t)

    t0 = time.perf_counter()
    for _ in range(n_iters):
        for r in records:
            _ = loop_engine._compute_revision_score_with_components(r, q_emb, q_st, curr_t)
    loop_time_per_query = (time.perf_counter() - t0) / n_iters

    # Vectorized benchmark
    for _ in range(10):
        _ = vec_engine.score_batch(E, H, T, P, q_emb, q_st, curr_t)

    t0 = time.perf_counter()
    for _ in range(n_iters):
        _ = vec_engine.score_batch(E, H, T, P, q_emb, q_st, curr_t)
    vec_time_per_query = (time.perf_counter() - t0) / n_iters

    speedup = loop_time_per_query / max(vec_time_per_query, 1e-9)

    return {
        "n_candidates": n_candidates,
        "emb_dim": emb_dim,
        "max_numerical_difference": max_diff,
        "numerical_parity_passed": bool(max_diff < 1e-5),
        "loop_query_latency_us": loop_time_per_query * 1e6,
        "vectorized_query_latency_us": vec_time_per_query * 1e6,
        "speedup_factor": speedup,
        "sub_100us_target_met": bool(vec_time_per_query * 1e6 < 100.0),
    }


if __name__ == "__main__":
    res = run_wp_r6()
    print(json.dumps(res, indent=2))
