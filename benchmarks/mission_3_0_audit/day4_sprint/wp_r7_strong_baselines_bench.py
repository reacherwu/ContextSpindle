"""WP-R7: Multi-Baseline Comparison Matrix across Canonical Seeds."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import torch
from torch import Tensor

from benchmarks.mission_3_0_audit.audit_pipeline import generate_evaluation_stream
from benchmarks.mission_3_0.acm_architecture import ACMArchitecture
from benchmarks.mission_3_0.baselines import (
    B1_RecurrentStateOnly,
    B2_FixedBudgetLRU,
    B3_SlidingWindowAttention,
    B4_UnboundedArchive,
)
from benchmarks.strong_baselines.strong_baselines import (
    StrongBaseline_DeltaNet,
    StrongBaseline_GatedSSM,
)


def run_wp_r7() -> dict[str, Any]:
    seeds = [101, 202, 303]

    model_names = [
        "B1_Recurrent_Only",
        "B2_Fixed_LRU_750",
        "B3_Sliding_FIFO_750",
        "DeltaNet_Linear_Attn",
        "Gated_SSM_Mamba",
        "ACM_Current_Revision",
        "ACM_Sim_Only_Retrieval",
        "B4_Full_Store_Oracle",
    ]

    results: dict[str, Any] = {
        name: {
            "memory_slots": 0,
            "memory_bounded": True,
            "mean_step_time_us": 0.0,
            "mean_query_time_us": 0.0,
            "top5_any_recall": 0.0,
            "top5_both_recall": 0.0,
            "mean_frr": 0.0,
            "a_long_mean_rank": 0.0,
            "a_mid_mean_rank": 0.0,
        }
        for name in model_names
    }

    for s in seeds:
        stream, vec_D, t_A_long, t_A_mid, t_R, t_F = generate_evaluation_stream(s)
        total_steps = len(stream)

        m_b1 = B1_RecurrentStateOnly(emb_dim=32, state_dim=32)
        m_b2 = B2_FixedBudgetLRU(capacity=750, emb_dim=32)
        m_b3 = B3_SlidingWindowAttention(window_size=750, emb_dim=32)
        m_deltanet = StrongBaseline_DeltaNet(emb_dim=32, key_dim=16, val_dim=16)
        m_mamba = StrongBaseline_GatedSSM(emb_dim=32, d_state=32)
        m_acm = ACMArchitecture(emb_dim=32, state_dim=32, k_hot=250, k_cold=500, seed=s)
        m_b4 = B4_UnboundedArchive(emb_dim=32)

        models_to_run = [
            ("B1_Recurrent_Only", m_b1, lambda m, t, ts, emb: m.step(emb)),
            ("B2_Fixed_LRU_750", m_b2, lambda m, t, ts, emb: m.observe(t, ts, emb)),
            ("B3_Sliding_FIFO_750", m_b3, lambda m, t, ts, emb: m.observe(t, ts, emb)),
            ("DeltaNet_Linear_Attn", m_deltanet, lambda m, t, ts, emb: m.observe(t, ts, emb)),
            ("Gated_SSM_Mamba", m_mamba, lambda m, t, ts, emb: m.observe(t, ts, emb)),
            ("ACM_Current_Revision", m_acm, lambda m, t, ts, emb: m.observe(t, ts, emb)),
            ("B4_Full_Store_Oracle", m_b4, lambda m, t, ts, emb: m.observe(t, ts, emb)),
        ]

        step_times = {}
        for name, m, step_fn in models_to_run:
            t0 = time.perf_counter()
            for t, emb, _ in stream:
                step_fn(m, t, float(t), emb)
            elapsed = time.perf_counter() - t0
            step_times[name] = (elapsed / total_steps) * 1e6

        # Query benchmarking and evaluation
        t0 = time.perf_counter()
        q_b1 = m_b1.query_causal(vec_D, top_k=5)
        q_b1_time = (time.perf_counter() - t0) * 1e6

        t0 = time.perf_counter()
        q_b2 = m_b2.query_causal(vec_D, top_k=5)
        q_b2_time = (time.perf_counter() - t0) * 1e6

        t0 = time.perf_counter()
        q_b3 = m_b3.query_causal(vec_D, top_k=5)
        q_b3_time = (time.perf_counter() - t0) * 1e6

        t0 = time.perf_counter()
        q_deltanet = m_deltanet.query_causal(vec_D, top_k=5)
        q_deltanet_time = (time.perf_counter() - t0) * 1e6

        t0 = time.perf_counter()
        q_mamba = m_mamba.query_causal(vec_D, top_k=5)
        q_mamba_time = (time.perf_counter() - t0) * 1e6

        t0 = time.perf_counter()
        q_acm_rev = m_acm.query_causal(vec_D, top_k=5)
        q_acm_rev_time = (time.perf_counter() - t0) * 1e6

        t0 = time.perf_counter()
        cold_recs = m_acm.cold_memory.records
        sim_scored = [(torch.dot(r.compressed_embedding, vec_D).item(), r.event_id) for r in cold_recs]
        sim_scored.sort(key=lambda x: x[0], reverse=True)
        q_acm_sim = [eid for _, eid in sim_scored[:5]]
        q_acm_sim_time = (time.perf_counter() - t0) * 1e6

        rank_acm_sim_long = next((i + 1 for i, (_, eid) in enumerate(sim_scored) if eid == t_A_long), 999)
        rank_acm_sim_mid = next((i + 1 for i, (_, eid) in enumerate(sim_scored) if eid == t_A_mid), 999)

        t0 = time.perf_counter()
        q_b4 = m_b4.query_causal(vec_D, top_k=5)
        q_b4_time = (time.perf_counter() - t0) * 1e6

        def evaluate_retrieval(retrieved: list[int]):
            hit_long = 1 if t_A_long in retrieved else 0
            hit_mid = 1 if t_A_mid in retrieved else 0
            any_hit = 1.0 if (hit_long or hit_mid) else 0.0
            both_hit = 1.0 if (hit_long and hit_mid) else 0.0
            frr = (len(retrieved) - (hit_long + hit_mid)) / max(len(retrieved), 1) if retrieved else 1.0
            return any_hit, both_hit, frr

        evals = {
            "B1_Recurrent_Only": (q_b1, 0, True, step_times["B1_Recurrent_Only"], q_b1_time, 999, 999),
            "B2_Fixed_LRU_750": (q_b2, m_b2.get_memory_slots(), True, step_times["B2_Fixed_LRU_750"], q_b2_time, 999, 999),
            "B3_Sliding_FIFO_750": (q_b3, m_b3.get_memory_slots(), True, step_times["B3_Sliding_FIFO_750"], q_b3_time, 999, 999),
            "DeltaNet_Linear_Attn": (q_deltanet, m_deltanet.get_memory_slots(), True, step_times["DeltaNet_Linear_Attn"], q_deltanet_time, 999, 999),
            "Gated_SSM_Mamba": (q_mamba, m_mamba.get_memory_slots(), True, step_times["Gated_SSM_Mamba"], q_mamba_time, 999, 999),
            "ACM_Current_Revision": (q_acm_rev, m_acm.get_memory_slots(), True, step_times["ACM_Current_Revision"], q_acm_rev_time, 999, 999),
            "ACM_Sim_Only_Retrieval": (q_acm_sim, m_acm.get_memory_slots(), True, step_times["ACM_Current_Revision"], q_acm_sim_time, rank_acm_sim_long, rank_acm_sim_mid),
            "B4_Full_Store_Oracle": (q_b4, m_b4.get_memory_slots(), False, step_times["B4_Full_Store_Oracle"], q_b4_time, 999, 999),
        }

        n = len(seeds)
        for name, (q_res, slots, bounded, s_time, q_time, r_l, r_m) in evals.items():
            any_h, both_h, frr = evaluate_retrieval(q_res)
            results[name]["memory_slots"] = slots
            results[name]["memory_bounded"] = bounded
            results[name]["mean_step_time_us"] += s_time / n
            results[name]["mean_query_time_us"] += q_time / n
            results[name]["top5_any_recall"] += any_h / n
            results[name]["top5_both_recall"] += both_h / n
            results[name]["mean_frr"] += frr / n
            results[name]["a_long_mean_rank"] += r_l / n
            results[name]["a_mid_mean_rank"] += r_m / n

    return results


if __name__ == "__main__":
    res = run_wp_r7()
    print(json.dumps(res, indent=2))
