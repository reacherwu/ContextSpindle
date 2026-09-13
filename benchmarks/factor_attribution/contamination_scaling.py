"""
Mission 2.6: Capacity Contamination Curve & Pareto Frontier Analysis.
Sweeps memory budget K across [25, 50, 100, 200, 500, 1000] under an adversarial outlier stream:
- 10 Critical Targets (occur early at t <= 500)
- 100 Outlier Novelty Traps (injected periodically across t=600..5000; never queried)
- Routine background operational flow
Measures for each (K, Model):
- Recall(K): Top-1 accuracy on Critical Targets
- Contamination(K): Fraction of memory slots hoarded by outlier traps
- Useful-Memory Ratio(K): Fraction of slots holding true critical targets
- Memory Utilization(K): Slots used / K
Identifies the Pareto Frontier between Recall and Contamination.
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


def run_contamination_trial(
    model_name: str,
    capacity_k: int,
    seed: int,
    stream_length: int = 5000,
    embedding_dim: int = 32,
) -> dict[str, Any]:
    torch.manual_seed(seed)

    # Background clusters
    n_clusters = 3
    cluster_centers = torch.randn(n_clusters, embedding_dim)
    cluster_centers = cluster_centers / torch.norm(cluster_centers, dim=-1, keepdim=True)

    # 10 Critical Targets (ordinary events within cluster 0, injected t <= 500)
    target_steps = [50, 100, 150, 200, 250, 300, 350, 400, 450, 500]
    critical_targets: dict[int, Tensor] = {}
    for s in target_steps:
        v = cluster_centers[0] + 0.03 * torch.randn(embedding_dim)
        critical_targets[s] = v / torch.norm(v)

    # 100 Outlier Novelty Traps (isolated orthogonal outliers across t=600..5000)
    trap_steps = set(range(600, stream_length, 44))
    novelty_traps: dict[int, Tensor] = {}
    for s in trap_steps:
        outlier = torch.randn(embedding_dim)
        for c in cluster_centers:
            outlier = outlier - torch.dot(outlier, c) * c
        novelty_traps[s] = outlier / torch.norm(outlier)

    # Generate stream
    stream: list[tuple[int, Tensor]] = []
    for step in range(stream_length):
        if step in critical_targets:
            stream.append((step, critical_targets[step]))
        elif step in novelty_traps:
            stream.append((step, novelty_traps[step]))
        else:
            c_id = (step // 30) % n_clusters
            v = cluster_centers[c_id] + 0.05 * torch.randn(embedding_dim)
            stream.append((step, v / torch.norm(v)))

    # Configure models
    state_dim = embedding_dim
    temporal_cfg = TemporalStateConfig(input_size=embedding_dim, hidden_size=state_dim)
    temporal_model = TemporalState(temporal_cfg)
    h_state = temporal_model.initial_state(1)

    eviction = "min_importance"
    weights = (0.2, 0.2, 0.2, 0.2, 0.2)

    if model_name == "Continuum_Primary_0.2":
        eviction = "min_importance"
        weights = (0.2, 0.2, 0.2, 0.2, 0.2)
    elif model_name == "Surprise_Only":
        eviction = "min_importance"
        weights = (1.0, 0.0, 0.0, 0.0, 0.0)
    elif model_name == "Novelty_Only":
        eviction = "min_importance"
        weights = (0.0, 1.0, 0.0, 0.0, 0.0)
    elif model_name == "FIFO":
        eviction = "fifo"
        weights = (0.2, 0.2, 0.2, 0.2, 0.2)
    elif model_name == "Random":
        eviction = "random"
        weights = (0.2, 0.2, 0.2, 0.2, 0.2)

    a, b, c, d, e = weights
    mem_cfg = AdaptiveMemoryConfig(
        embedding_dim=embedding_dim,
        state_dim=state_dim,
        capacity=capacity_k,
        policy_mode="fixed_budget",
        eviction_policy=eviction,  # type: ignore[arg-type]
        alpha_surprise=a,
        beta_novelty=b,
        gamma_causal=c,
        delta_retrieval=d,
        epsilon_uncertainty=e,
        seed=seed,
    )
    mem = AdaptiveMemory(mem_cfg)

    # Stream processing
    for step, vec in stream:
        step_out = temporal_model.step(vec.unsqueeze(0), h_state)
        h_state = step_out.state
        mem.observe(event_id=step, timestamp=float(step), embedding=vec, temporal_state=h_state[0])

    # Analysis of memory slots
    retained_ids = set(r.event_id for r in mem.records)
    targets_retained = sum(1 for s in critical_targets if s in retained_ids)
    traps_hoarded = sum(1 for s in novelty_traps if s in retained_ids)
    final_size = len(mem.records)

    # Retrieval performance on Critical Targets
    hits = 0
    mrr_sum = 0.0
    for s, t_vec in critical_targets.items():
        q = t_vec + 0.02 * torch.randn(embedding_dim)
        q = q / torch.norm(q)
        retrieved = mem.retrieve(q, top_k=5)
        if retrieved:
            for rank, (r, sim) in enumerate(retrieved, start=1):
                if r.event_id == s:
                    mrr_sum += 1.0 / rank
                    if rank == 1:
                        hits += 1
                    break

    n_targets = len(critical_targets)
    recall = hits / n_targets
    contamination = traps_hoarded / max(1, capacity_k)
    useful_ratio = targets_retained / max(1, capacity_k)
    utilization = final_size / max(1, capacity_k)

    return {
        "model": model_name,
        "capacity_k": capacity_k,
        "seed": seed,
        "recall": recall,
        "mrr": mrr_sum / n_targets,
        "contamination": contamination,
        "useful_ratio": useful_ratio,
        "utilization": utilization,
        "targets_retained": targets_retained,
        "traps_hoarded": traps_hoarded,
    }


def run_contamination_sweep(
    capacities: list[int] = [25, 50, 100, 200, 500, 1000],
    models: list[str] = [
        "Continuum_Primary_0.2",
        "Surprise_Only",
        "Novelty_Only",
        "FIFO",
        "Random",
    ],
    seeds: list[int] = [101, 202, 303],
) -> dict[str, Any]:
    print(f"Sweeping capacities: {capacities} across models: {models}")
    all_trials = []

    for k in capacities:
        print(f"\n--- Capacity K = {k} ---")
        for m in models:
            runs = []
            for s in seeds:
                res = run_contamination_trial(m, k, s)
                runs.append(res)
                all_trials.append(res)

            mean_rec = sum(r["recall"] for r in runs) / len(runs)
            mean_contam = sum(r["contamination"] for r in runs) / len(runs)
            mean_useful = sum(r["useful_ratio"] for r in runs) / len(runs)
            print(f"  [{m:<22}] K={k:>4}: Recall={mean_rec*100:>5.1f}%  Contamination={mean_contam*100:>5.1f}%  UsefulRatio={mean_useful*100:>5.2f}%")

    # Aggregate by (model, capacity)
    aggregated: dict[str, dict[int, dict[str, float]]] = {m: {} for m in models}
    for m in models:
        for k in capacities:
            matching = [t for t in all_trials if t["model"] == m and t["capacity_k"] == k]
            recalls = [t["recall"] for t in matching]
            contams = [t["contamination"] for t in matching]
            usefuls = [t["useful_ratio"] for t in matching]
            utils = [t["utilization"] for t in matching]

            aggregated[m][k] = {
                "mean_recall": sum(recalls) / len(recalls),
                "mean_contamination": sum(contams) / len(contams),
                "mean_useful_ratio": sum(usefuls) / len(usefuls),
                "mean_utilization": sum(utils) / len(utils),
            }

    return {
        "capacities": capacities,
        "models": models,
        "seeds": seeds,
        "aggregated": aggregated,
        "raw_trials": all_trials,
    }


if __name__ == "__main__":
    res = run_contamination_sweep()
