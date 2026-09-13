"""
Adversarial Benchmark C: Novelty Inversion Attack (The Novelty Trap).
Tests whether the memory engine falls into the trap of becoming a pure "novelty collector".
Environment:
- Event Type A (Novelty Traps): Extremely novel, isolated outlier events (N_t -> 1.0)
  that are NEVER queried in the future.
- Event Type B (Critical Targets): Familiar, routine events belonging to common clusters (N_t -> 0.05)
  that ARE the primary query targets at the end of the stream.
Models compared:
- Novelty-only (beta=1.0)
- Surprise-only (alpha=1.0)
- Adaptive Memory (Composite)
- FIFO
- Random
- LRU
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


def run_benchmark_c(
    stream_length: int = 5000,
    capacity: int = 200,
    embedding_dim: int = 32,
    seed: int = 101,
) -> dict[str, Any]:
    torch.manual_seed(seed)

    # 3 standard background clusters
    n_clusters = 3
    cluster_centers = torch.randn(n_clusters, embedding_dim)
    cluster_centers = cluster_centers / torch.norm(cluster_centers, dim=-1, keepdim=True)

    # Event B (Critical Targets): 10 ordinary events within Cluster 0
    target_steps = [50, 100, 150, 200, 250, 300, 350, 400, 450, 500]
    critical_targets: dict[int, Tensor] = {}
    for s in target_steps:
        # Familiar event: drawn from cluster 0
        v = cluster_centers[0] + 0.03 * torch.randn(embedding_dim)
        v = v / torch.norm(v)
        critical_targets[s] = v

    # Event A (Novelty Traps): 100 synthetic extreme outliers
    # Injected periodically at steps 600, 650, 700, ...
    novelty_trap_steps = set(range(600, stream_length, 45))
    novelty_traps: dict[int, Tensor] = {}
    for s in novelty_trap_steps:
        # Outlier vector orthogonal to all cluster centers
        outlier = torch.randn(embedding_dim)
        for c in cluster_centers:
            outlier = outlier - torch.dot(outlier, c) * c
        outlier = outlier / torch.norm(outlier)
        novelty_traps[s] = outlier

    # Generate stream
    stream: list[tuple[int, Tensor]] = []
    for step in range(stream_length):
        if step in critical_targets:
            stream.append((step, critical_targets[step]))
        elif step in novelty_traps:
            stream.append((step, novelty_traps[step]))
        else:
            # Regular background from clusters 0, 1, 2
            c_id = (step // 30) % n_clusters
            v = cluster_centers[c_id] + 0.05 * torch.randn(embedding_dim)
            v = v / torch.norm(v)
            stream.append((step, v))

    # Configurations
    models = {
        "Novelty_Only": ("min_importance", 0.0, 1.0, 0.0, 0.0, 0.0),
        "Surprise_Only": ("min_importance", 1.0, 0.0, 0.0, 0.0, 0.0),
        "Adaptive_Memory": ("min_importance", 0.35, 0.35, 0.1, 0.1, 0.1),
        "FIFO": ("fifo", 0.2, 0.2, 0.2, 0.2, 0.2),
        "Random": ("random", 0.2, 0.2, 0.2, 0.2, 0.2),
        "LRU": ("lru", 0.2, 0.2, 0.2, 0.2, 0.2),
    }

    results: dict[str, Any] = {}

    for name, (eviction, a, b, c, d, e) in models.items():
        temporal_cfg = TemporalStateConfig(input_size=embedding_dim, hidden_size=embedding_dim)
        temporal_model = TemporalState(temporal_cfg)
        h_state = temporal_model.initial_state(1)

        cfg = AdaptiveMemoryConfig(
            embedding_dim=embedding_dim,
            state_dim=embedding_dim,
            capacity=capacity,
            policy_mode="fixed_budget",
            eviction_policy=eviction,
            alpha_surprise=a,
            beta_novelty=b,
            gamma_causal=c,
            delta_retrieval=d,
            epsilon_uncertainty=e,
            seed=seed,
        )
        mem = AdaptiveMemory(cfg)

        for step, vec in stream:
            step_out = temporal_model.step(vec.unsqueeze(0), h_state)
            h_state = step_out.state
            mem.observe(event_id=step, timestamp=float(step), embedding=vec, temporal_state=h_state[0])

        # Evaluate:
        # How many novelty traps were hoarded in memory?
        retained_ids = set(r.event_id for r in mem.records)
        traps_hoarded = sum(1 for tid in novelty_traps if tid in retained_ids)
        targets_retained = sum(1 for cid in critical_targets if cid in retained_ids)

        # Query performance on the CRITICAL TARGETS (never query the traps!)
        hits = 0
        mrr_sum = 0.0
        for s, target_vec in critical_targets.items():
            query = target_vec + 0.02 * torch.randn(embedding_dim)
            query = query / torch.norm(query)
            retrieved = mem.retrieve(query, top_k=5)
            if retrieved:
                for rank, (r, sim) in enumerate(retrieved, start=1):
                    if r.event_id == s:
                        mrr_sum += 1.0 / rank
                        if rank == 1:
                            hits += 1
                        break

        n_targets = len(critical_targets)
        results[name] = {
            "target_accuracy": hits / n_targets,
            "target_mrr": mrr_sum / n_targets,
            "targets_retained": targets_retained,
            "traps_hoarded": traps_hoarded,
            "trap_hoarding_ratio": traps_hoarded / capacity,
        }

    return results


if __name__ == "__main__":
    for s in [101, 202, 303]:
        r = run_benchmark_c(seed=s)
        print(f"Seed {s}:")
        for m, d in r.items():
            print(
                f"  {m:<16} Acc={d['target_accuracy']*100:>5.1f}%  "
                f"TargetsRetained={d['targets_retained']:>2}/10  "
                f"TrapsHoarded={d['traps_hoarded']:>3}/{200} ({d['trap_hoarding_ratio']*100:>4.1f}%)"
            )
