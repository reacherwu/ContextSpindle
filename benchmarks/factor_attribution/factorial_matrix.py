"""
Mission 2.6: Factor Attribution Matrix.
Performs full factorial ablation across:
- Experiment 1: Single factors (S, N, C, R, U)
- Experiment 2: Pairwise factor combinations (S+N, S+C, S+R, S+U, N+C, N+R, N+U, C+R, C+U, R+U)
- Experiment 3: Pre-registered primary composite (alpha=beta=gamma=delta=epsilon=0.2)
- Comparative Baselines: FIFO, Random, LRU, TemporalState-only

Evaluates across seeds [101, 202, 303] under fixed memory budget K=200, stream length T=5000.
"""
from __future__ import annotations

import math
import time
from typing import Any

import torch
from torch import Tensor

from continuum.memory.adaptive_memory import (
    AdaptiveMemory,
    AdaptiveMemoryConfig,
)
from continuum.state.temporal_state import TemporalState, TemporalStateConfig


def run_single_factorial_trial(
    config_name: str,
    weights: tuple[float, float, float, float, float] | None,  # (alpha, beta, gamma, delta, epsilon)
    eviction_policy: str,
    seed: int,
    stream_length: int = 5000,
    capacity: int = 200,
    embedding_dim: int = 32,
) -> dict[str, Any]:
    torch.manual_seed(seed)

    # 4 background operational clusters
    n_clusters = 4
    cluster_centers = torch.randn(n_clusters, embedding_dim)
    cluster_centers = cluster_centers / torch.norm(cluster_centers, dim=-1, keepdim=True)

    # 10 critical targets injected early in stream (t <= 500)
    target_steps = [50, 100, 150, 200, 250, 300, 350, 400, 450, 500]
    targets: dict[int, Tensor] = {}
    for s in target_steps:
        # Realistic targets: moderate departure from cluster
        c_id = (s // 50) % n_clusters
        v = cluster_centers[c_id] + 0.15 * torch.randn(embedding_dim)
        targets[s] = v / torch.norm(v)

    # Stream generation: AR(1) cluster flow with periodic mode shifts
    stream: list[tuple[int, Tensor]] = []
    bg_state = torch.randn(embedding_dim)
    bg_state = bg_state / torch.norm(bg_state)

    for step in range(stream_length):
        if step in targets:
            stream.append((step, targets[step]))
        else:
            c_id = (step // 30) % n_clusters
            noise = torch.randn(embedding_dim)
            noise = noise / torch.norm(noise)
            bg_state = 0.8 * bg_state + 0.2 * (cluster_centers[c_id] + 0.1 * noise)
            v = bg_state / torch.norm(bg_state)
            stream.append((step, v))

    # Initialize models
    state_dim = embedding_dim
    temporal_cfg = TemporalStateConfig(input_size=embedding_dim, hidden_size=state_dim)
    temporal_model = TemporalState(temporal_cfg)
    h_state = temporal_model.initial_state(1)

    mem: AdaptiveMemory | None = None
    if weights is not None:
        a, b, c, d, e = weights
        mem_cfg = AdaptiveMemoryConfig(
            embedding_dim=embedding_dim,
            state_dim=state_dim,
            capacity=capacity,
            policy_mode="fixed_budget",
            eviction_policy=eviction_policy,  # type: ignore[arg-type]
            alpha_surprise=a,
            beta_novelty=b,
            gamma_causal=c,
            delta_retrieval=d,
            epsilon_uncertainty=e,
            seed=seed,
        )
        mem = AdaptiveMemory(mem_cfg)

    # Stream execution
    t0 = time.perf_counter()
    for step, vec in stream:
        step_out = temporal_model.step(vec.unsqueeze(0), h_state)
        h_state = step_out.state
        if mem is not None:
            mem.observe(event_id=step, timestamp=float(step), embedding=vec, temporal_state=h_state[0])
    elapsed = time.perf_counter() - t0

    # Query evaluation
    hits = 0
    mrr_sum = 0.0
    targets_retained = 0

    if mem is not None:
        retained_ids = set(r.event_id for r in mem.records)
        targets_retained = sum(1 for s in targets if s in retained_ids)

        for s, t_vec in targets.items():
            query = t_vec + 0.02 * torch.randn(embedding_dim)
            query = query / torch.norm(query)
            retrieved = mem.retrieve(query, top_k=5)
            if retrieved:
                for rank, (r, sim) in enumerate(retrieved, start=1):
                    if r.event_id == s:
                        mrr_sum += 1.0 / rank
                        if rank == 1:
                            hits += 1
                        break
    else:
        # Temporal state alone
        h_norm = h_state[0] / torch.norm(h_state[0])
        for s, t_vec in targets.items():
            sim = float(torch.dot(h_norm, t_vec).item())
            if sim > 0.85:
                hits += 1
                mrr_sum += 1.0

    n_targets = len(targets)
    return {
        "config": config_name,
        "seed": seed,
        "top1_accuracy": hits / n_targets,
        "mrr": mrr_sum / n_targets,
        "targets_retained": targets_retained,
        "survival_rate": targets_retained / n_targets,
        "elapsed_sec": elapsed,
    }


def run_full_factorial_matrix(seeds: list[int] = [101, 202, 303]) -> dict[str, Any]:
    # Factor configurations to test
    configurations: list[tuple[str, tuple[float, float, float, float, float] | None, str]] = [
        # --- Experiment 1: Single Factors ---
        ("Exp1_S_only", (1.0, 0.0, 0.0, 0.0, 0.0), "min_importance"),
        ("Exp1_N_only", (0.0, 1.0, 0.0, 0.0, 0.0), "min_importance"),
        ("Exp1_C_only", (0.0, 0.0, 1.0, 0.0, 0.0), "min_importance"),
        ("Exp1_R_only", (0.0, 0.0, 0.0, 1.0, 0.0), "min_importance"),
        ("Exp1_U_only", (0.0, 0.0, 0.0, 0.0, 1.0), "min_importance"),
        # --- Experiment 2: Pairwise Combinations (Equal 0.5/0.5) ---
        ("Exp2_S+N", (0.5, 0.5, 0.0, 0.0, 0.0), "min_importance"),
        ("Exp2_S+C", (0.5, 0.0, 0.5, 0.0, 0.0), "min_importance"),
        ("Exp2_S+R", (0.5, 0.0, 0.0, 0.5, 0.0), "min_importance"),
        ("Exp2_S+U", (0.5, 0.0, 0.0, 0.0, 0.5), "min_importance"),
        ("Exp2_N+C", (0.0, 0.5, 0.5, 0.0, 0.0), "min_importance"),
        ("Exp2_N+R", (0.0, 0.5, 0.0, 0.5, 0.0), "min_importance"),
        ("Exp2_N+U", (0.0, 0.5, 0.0, 0.0, 0.5), "min_importance"),
        ("Exp2_C+R", (0.0, 0.0, 0.5, 0.5, 0.0), "min_importance"),
        ("Exp2_C+U", (0.0, 0.0, 0.5, 0.0, 0.5), "min_importance"),
        ("Exp2_R+U", (0.0, 0.0, 0.0, 0.5, 0.5), "min_importance"),
        # --- Experiment 3: Pre-Registered Primary Equal-Weight Baseline ---
        ("Exp3_Primary_EqualWeight_0.2", (0.2, 0.2, 0.2, 0.2, 0.2), "min_importance"),
        # --- Baselines ---
        ("Baseline_FIFO", (0.2, 0.2, 0.2, 0.2, 0.2), "fifo"),
        ("Baseline_Random", (0.2, 0.2, 0.2, 0.2, 0.2), "random"),
        ("Baseline_LRU", (0.2, 0.2, 0.2, 0.2, 0.2), "lru"),
        ("Baseline_TemporalState_A", None, "none"),
    ]

    all_results: dict[str, Any] = {}

    for name, weights, eviction in configurations:
        runs = []
        for s in seeds:
            res = run_single_factorial_trial(
                config_name=name,
                weights=weights,
                eviction_policy=eviction,
                seed=s,
            )
            runs.append(res)

        accs = [r["top1_accuracy"] for r in runs]
        mrrs = [r["mrr"] for r in runs]
        survs = [r["survival_rate"] for r in runs]

        mean_acc = sum(accs) / len(accs)
        std_acc = math.sqrt(sum((x - mean_acc) ** 2 for x in accs) / len(accs))
        mean_mrr = sum(mrrs) / len(mrrs)
        mean_surv = sum(survs) / len(survs)

        all_results[name] = {
            "mean_accuracy": mean_acc,
            "std_accuracy": std_acc,
            "mean_mrr": mean_mrr,
            "mean_survival_rate": mean_surv,
            "individual_runs": runs,
        }
        print(f"  {name:<32} Top1 Acc: {mean_acc*100:>5.1f}% ± {std_acc*100:>4.1f}%  MRR: {mean_mrr:.3f}")

    return all_results


if __name__ == "__main__":
    res = run_full_factorial_matrix()
