"""
Adversarial Benchmark E: Delayed Causal Importance (The Epistemic Horizon Attack).
Constructs a delayed causal chain:
    A -> B -> C -> D
When root event A occurs at step t=100:
    It appears completely ordinary: low prediction error, low novelty (looks like routine telemetry).
Thousands of events later, terminal event D occurs at step t=5100 (e.g. bearing seizure).
Query at t=5100:
    "Retrieve the antecedent root cause A that led to failure D."
Scientific Question:
    Can an online-only memory retention policy (Conditioned strictly on x_<=t) survive
    delayed causal relevance without retrospective Memory Revision (Phase 8)?
Expected Result:
    Catastrophic eviction of root cause A.
    Provides the foundational empirical justification for Phase 8 (Memory Revision).
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


def run_benchmark_e(
    stream_length: int = 5200,
    capacity: int = 250,
    embedding_dim: int = 32,
    seed: int = 101,
) -> dict[str, Any]:
    torch.manual_seed(seed)

    # 3 operational background clusters
    n_clusters = 3
    cluster_centers = torch.randn(n_clusters, embedding_dim)
    cluster_centers = cluster_centers / torch.norm(cluster_centers, dim=-1, keepdim=True)

    # Event A (Root Cause): Occurs at step 100.
    # CRITICAL DESIGN: It looks completely ordinary (drawn from cluster 0 with small noise)
    step_A = 100
    vec_A = cluster_centers[0] + 0.02 * torch.randn(embedding_dim)
    vec_A = vec_A / torch.norm(vec_A)

    # Intermediate causal chain events
    step_B = 1500
    vec_B = 0.5 * vec_A + 0.5 * cluster_centers[1] + 0.02 * torch.randn(embedding_dim)
    vec_B = vec_B / torch.norm(vec_B)

    step_C = 3000
    vec_C = 0.5 * vec_B + 0.5 * cluster_centers[2] + 0.02 * torch.randn(embedding_dim)
    vec_C = vec_C / torch.norm(vec_C)

    # Terminal Event D: Occurs at step 5100
    step_D = 5100
    vec_D = torch.randn(embedding_dim)
    vec_D = vec_D / torch.norm(vec_D)

    stream: list[tuple[int, Tensor]] = []
    for step in range(stream_length):
        if step == step_A:
            stream.append((step, vec_A))
        elif step == step_B:
            stream.append((step, vec_B))
        elif step == step_C:
            stream.append((step, vec_C))
        elif step == step_D:
            stream.append((step, vec_D))
        else:
            # Routine background
            c_id = (step // 25) % n_clusters
            v = cluster_centers[c_id] + 0.03 * torch.randn(embedding_dim)
            v = v / torch.norm(v)
            stream.append((step, v))

    models = {
        "Continuum_Adaptive": ("min_importance", 0.35, 0.35, 0.1, 0.1, 0.1),
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

        rec_A_importance = 0.0
        rec_A_decision = "none"

        for step, vec in stream:
            step_out = temporal_model.step(vec.unsqueeze(0), h_state)
            h_state = step_out.state
            rec = mem.observe(event_id=step, timestamp=float(step), embedding=vec, temporal_state=h_state[0])
            if step == step_A:
                rec_A_importance = rec.importance
                rec_A_decision = rec.decision.value

        # Post-Stream Causal Query:
        # At t=5100, failure D occurs. The inquiry asks for Root Cause Event A.
        retained_ids = set(r.event_id for r in mem.records)
        event_A_survived = step_A in retained_ids

        # Query for A
        query_A = vec_A + 0.01 * torch.randn(embedding_dim)
        query_A = query_A / torch.norm(query_A)
        retrieved = mem.retrieve(query_A, top_k=5)
        top1_match = 1.0 if (retrieved and retrieved[0][0].event_id == step_A) else 0.0

        results[name] = {
            "root_event_A_importance_at_t100": rec_A_importance,
            "root_event_A_decision_at_t100": rec_A_decision,
            "root_event_A_survived_at_t5100": 1.0 if event_A_survived else 0.0,
            "root_cause_retrieval_accuracy": top1_match,
        }

    return results


if __name__ == "__main__":
    for s in [101, 202, 303]:
        r = run_benchmark_e(seed=s)
        print(f"Seed {s}:")
        for m, d in r.items():
            print(
                f"  {m:<18} "
                f"I(A)_at_t100={d['root_event_A_importance_at_t100']:.3f}  "
                f"A_survived={d['root_event_A_survived_at_t5100']}  "
                f"Accuracy={d['root_cause_retrieval_accuracy']*100:.1f}%"
            )
