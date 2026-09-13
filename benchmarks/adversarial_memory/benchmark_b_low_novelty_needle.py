"""
Adversarial Benchmark B: Low-Novelty Needle Attack.
Attacks the assumption that needles are outlier vectors with high novelty.
Here, critical events reside inside existing background clusters with tiny semantic perturbation:
    critical_event = cluster_center + epsilon
Thus:
    Cosine distance to cluster <= 0.02 -> Novelty N_t <= 0.02.
Novelty can NO LONGER act as an easy heuristic to identify the needle.
Evaluates whether Continuum retains critical events when novelty is stripped away.
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


def run_benchmark_b(
    stream_length: int = 5000,
    capacity: int = 300,
    embedding_dim: int = 32,
    seed: int = 101,
) -> dict[str, Any]:
    torch.manual_seed(seed)

    # 4 distinct background clusters
    n_clusters = 4
    cluster_centers = torch.randn(n_clusters, embedding_dim)
    cluster_centers = cluster_centers / torch.norm(cluster_centers, dim=-1, keepdim=True)

    # Needles are placed strictly INSIDE cluster 0 and cluster 1 with tiny perturbation
    # epsilon = 0.015 * noise -> cosine similarity with cluster center > 0.99!
    n_needles = 10
    needle_schedule = [50, 100, 150, 200, 250, 300, 350, 400, 450, 500]
    needles: dict[int, Tensor] = {}
    for idx, step in enumerate(needle_schedule):
        c_id = idx % 2  # Belongs to cluster 0 or 1
        needle_vec = cluster_centers[c_id] + 0.015 * torch.randn(embedding_dim)
        needle_vec = needle_vec / torch.norm(needle_vec)
        needles[step] = needle_vec

    # Generate stream
    stream: list[tuple[int, Tensor]] = []
    for step in range(stream_length):
        if step in needles:
            stream.append((step, needles[step]))
        else:
            # Ordinary background event from one of the 4 clusters
            c_id = (step // 20) % n_clusters
            bg_vec = cluster_centers[c_id] + 0.02 * torch.randn(embedding_dim)
            bg_vec = bg_vec / torch.norm(bg_vec)
            stream.append((step, bg_vec))

    models = {
        "Continuum": ("min_importance", 0.35, 0.35, 0.1, 0.1, 0.1),
        "B_fifo": ("fifo", 0.2, 0.2, 0.2, 0.2, 0.2),
        "B_random": ("random", 0.2, 0.2, 0.2, 0.2, 0.2),
        "B_lru": ("lru", 0.2, 0.2, 0.2, 0.2, 0.2),
        "A_temporal_state": None,
    }

    results: dict[str, Any] = {}
    needle_novelties: list[float] = []

    for name, spec in models.items():
        temporal_cfg = TemporalStateConfig(input_size=embedding_dim, hidden_size=embedding_dim)
        temporal_model = TemporalState(temporal_cfg)
        h_state = temporal_model.initial_state(1)

        mem: AdaptiveMemory | None = None
        if spec is not None:
            eviction, a, b, c, d, e = spec
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
            if mem is not None:
                rec = mem.observe(event_id=step, timestamp=float(step), embedding=vec, temporal_state=h_state[0])
                if name == "Continuum" and step in needles:
                    needle_novelties.append(rec.novelty)

        # Evaluate Needle Retrieval
        hits = 0
        mrr_sum = 0.0
        retained_count = 0

        for step, n_vec in needles.items():
            query = n_vec + 0.01 * torch.randn(embedding_dim)
            query = query / torch.norm(query)

            if mem is not None:
                if any(r.event_id == step for r in mem.records):
                    retained_count += 1
                retrieved = mem.retrieve(query, top_k=5)
                if retrieved:
                    for rank, (r, sim) in enumerate(retrieved, start=1):
                        if r.event_id == step:
                            mrr_sum += 1.0 / rank
                            if rank == 1:
                                hits += 1
                            break
            else:
                h_norm = h_state[0] / torch.norm(h_state[0])
                sim = float(torch.dot(h_norm, n_vec).item())
                if sim > 0.95:
                    hits += 1
                    mrr_sum += 1.0

        results[name] = {
            "accuracy": hits / n_needles,
            "mrr": mrr_sum / n_needles,
            "survival_rate": retained_count / n_needles if mem else 0.0,
            "mean_needle_novelty": sum(needle_novelties) / len(needle_novelties) if needle_novelties else 0.0,
        }

    return results


if __name__ == "__main__":
    for s in [101, 202, 303]:
        r = run_benchmark_b(seed=s)
        print(f"Seed {s}:")
        for m, d in r.items():
            print(f"  {m:<16} Acc={d['accuracy']*100:>5.1f}%  MRR={d['mrr']:.3f}  Survival={d['survival_rate']*100:>5.1f}%  NeedleNovelty={d['mean_needle_novelty']:.4f}")
