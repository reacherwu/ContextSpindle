from __future__ import annotations

import gc
import os
import random
import time
from typing import Any

import psutil
import torch
from torch import Tensor

from benchmarks.mission_3_0.acm_architecture import ACMArchitecture
from benchmarks.mission_3_0.baselines import (
    B1_RecurrentStateOnly,
    B2_FixedBudgetLRU,
    B3_SlidingWindowAttention,
    B4_UnboundedArchive,
)


def get_process_memory_mb() -> float:
    process = psutil.Process(os.getpid())
    return float(process.memory_info().rss) / (1024.0 * 1024.0)


# ===========================================================================
# Benchmark A: Causal Capability Validation (T = 3000)
# ===========================================================================

def run_causal_capability_experiment(
    model_name: str,
    seed: int,
    emb_dim: int = 32,
    state_dim: int = 32,
    stream_length: int = 3000,
) -> dict[str, Any]:
    torch.manual_seed(seed)
    random.seed(seed)

    t_A_long = 100    # Delta_t = 2900 (far outside W=750 window)
    t_A_mid = 2000    # Delta_t = 1000 (outside W=750 window)
    n_traps = 50
    n_distractors = 50
    n_clusters = 3

    # Orthogonal bases
    basis: list[Tensor] = []
    for _ in range(n_clusters):
        v = torch.randn(emb_dim)
        for b in basis:
            v -= torch.dot(v, b) * b
        v /= torch.norm(v, p=2)
        basis.append(v)
    clusters = basis[:n_clusters]

    # Failure Subsystem X
    v_x = torch.randn(emb_dim)
    for b in basis:
        v_x -= torch.dot(v_x, b) * b
    v_x /= torch.norm(v_x, p=2)
    basis.append(v_x)

    # Event vectors
    vec_A_long = 0.85 * v_x + 0.15 * torch.randn(emb_dim)
    vec_A_long /= torch.norm(vec_A_long, p=2)

    vec_A_mid = 0.85 * v_x + 0.15 * torch.randn(emb_dim)
    vec_A_mid /= torch.norm(vec_A_mid, p=2)

    vec_D = 0.85 * v_x + 0.15 * torch.randn(emb_dim)
    vec_D /= torch.norm(vec_D, p=2)

    # Anomaly traps: orthogonal spatial vectors
    trap_steps = set(range(300, 1800, 30))
    trap_vectors: dict[int, Tensor] = {}
    for t in trap_steps:
        v = torch.randn(emb_dim)
        for b in basis:
            v -= torch.dot(v, b) * b
        trap_vectors[t] = v / torch.norm(v, p=2)

    # Distractors: superficial alignment with D
    dist_steps = set(range(500, stream_length - 50, 45)) - trap_steps - {t_A_long, t_A_mid}
    dist_vectors: dict[int, Tensor] = {}
    for t in dist_steps:
        v = 0.40 * vec_D + 0.60 * torch.randn(emb_dim)
        dist_vectors[t] = v / torch.norm(v, p=2)

    # Instantiate Model
    if model_name == "B1_recurrent_only":
        model: Any = B1_RecurrentStateOnly(emb_dim=emb_dim, state_dim=state_dim)
    elif model_name == "B2_fixed_lru":
        model = B2_FixedBudgetLRU(capacity=750, emb_dim=emb_dim)
    elif model_name == "B3_sliding_window":
        model = B3_SlidingWindowAttention(window_size=750, emb_dim=emb_dim)
    elif model_name == "B4_unbounded_archive":
        model = B4_UnboundedArchive(emb_dim=emb_dim)
    elif model_name == "ACM_architecture":
        model = ACMArchitecture(emb_dim=emb_dim, state_dim=state_dim, k_hot=250, k_cold=500, seed=seed)
    else:
        raise ValueError(f"Unknown model_name: {model_name}")

    t0 = time.perf_counter()
    causal_active = False

    # Stream loop
    for t in range(stream_length):
        if t == t_A_long:
            emb = vec_A_long
            causal_active = True
        elif t == t_A_mid:
            emb = vec_A_mid
            causal_active = True
        elif t in trap_steps:
            emb = trap_vectors[t]
        elif t in dist_steps:
            emb = dist_vectors[t]
        else:
            c_idx = (t // 25) % n_clusters
            base_vec = clusters[c_idx].clone()
            if causal_active:
                drift_factor = min(0.30, 0.04 + 0.0001 * (t - t_A_long))
                base_vec = base_vec + drift_factor * v_x
            base_vec = base_vec + 0.03 * torch.randn(emb_dim)
            emb = base_vec / torch.norm(base_vec, p=2)

        if model_name == "B1_recurrent_only":
            model.step(emb)
        else:
            model.observe(event_id=t, timestamp=float(t), embedding=emb)

    stream_time_ms = (time.perf_counter() - t0) * 1000

    # Query terminal symptom D
    t_query0 = time.perf_counter()
    retrieved_ids = model.query_causal(vec_D, top_k=5)
    query_time_ms = (time.perf_counter() - t_query0) * 1000

    # Audit retrieval
    retrieved_long = t_A_long in retrieved_ids
    retrieved_mid = t_A_mid in retrieved_ids
    causal_retrieved = retrieved_long or retrieved_mid
    traps_retrieved = sum(1 for eid in retrieved_ids if eid in trap_steps)
    distractors_retrieved = sum(1 for eid in retrieved_ids if eid in dist_steps)
    memory_slots_used = model.get_memory_slots()

    # False restoration rate (fraction of non-causal items in retrieved list)
    false_items = len(retrieved_ids) - (1 if retrieved_long else 0) - (1 if retrieved_mid else 0)
    frr = (false_items / len(retrieved_ids)) if len(retrieved_ids) > 0 else 0.0

    return {
        "model_name": model_name,
        "seed": seed,
        "retrieved_long": retrieved_long,
        "retrieved_mid": retrieved_mid,
        "causal_retrieved": causal_retrieved,
        "retrieved_ids": retrieved_ids,
        "traps_retrieved": traps_retrieved,
        "distractors_retrieved": distractors_retrieved,
        "frr": frr,
        "memory_slots_used": memory_slots_used,
        "stream_time_ms": stream_time_ms,
        "query_time_ms": query_time_ms,
    }


# ===========================================================================
# Benchmark B: System Efficiency & Scaling Validation (T = 1K to 10K)
# ===========================================================================

def run_efficiency_scaling_experiment(
    model_name: str,
    stream_length: int,
    seed: int = 101,
    emb_dim: int = 32,
    state_dim: int = 32,
) -> dict[str, Any]:
    gc.collect()
    torch.manual_seed(seed)
    random.seed(seed)

    if model_name == "B1_recurrent_only":
        model: Any = B1_RecurrentStateOnly(emb_dim=emb_dim, state_dim=state_dim)
    elif model_name == "B2_fixed_lru":
        model = B2_FixedBudgetLRU(capacity=750, emb_dim=emb_dim)
    elif model_name == "B3_sliding_window":
        model = B3_SlidingWindowAttention(window_size=750, emb_dim=emb_dim)
    elif model_name == "B4_unbounded_archive":
        model = B4_UnboundedArchive(emb_dim=emb_dim)
    elif model_name == "ACM_architecture":
        model = ACMArchitecture(emb_dim=emb_dim, state_dim=state_dim, k_hot=250, k_cold=500, seed=seed)
    else:
        raise ValueError(f"Unknown model_name: {model_name}")

    query_vec = torch.randn(emb_dim)
    query_vec /= torch.norm(query_vec, p=2)

    # Warmup and initial RSS
    start_rss_mb = get_process_memory_mb()
    t0 = time.perf_counter()

    for t in range(stream_length):
        emb = torch.randn(emb_dim)
        emb /= torch.norm(emb, p=2)
        if model_name == "B1_recurrent_only":
            model.step(emb)
        else:
            model.observe(event_id=t, timestamp=float(t), embedding=emb)

    total_stream_time = time.perf_counter() - t0
    peak_rss_mb = get_process_memory_mb()
    final_slots = model.get_memory_slots()

    # Latency per 1K steps
    per_step_us = (total_stream_time / stream_length) * 1e6

    # Query time
    t_q0 = time.perf_counter()
    _ = model.query_causal(query_vec, top_k=5)
    query_ms = (time.perf_counter() - t_q0) * 1000

    return {
        "model_name": model_name,
        "stream_length": stream_length,
        "slots_used": final_slots,
        "peak_rss_mb": peak_rss_mb,
        "per_step_us": per_step_us,
        "query_ms": query_ms,
    }
