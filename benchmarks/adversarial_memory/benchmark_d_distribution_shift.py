"""
Adversarial Benchmark D: Future Query Distribution Shift.
Tests whether the historical retrieval prior (Demand Prior R_t) acts as a vulnerability
when future query interest shifts unexpectedly.
Stream phase:
- Category X appears with high density and burstiness -> R_t is high.
- Category Y appears sparsely and quietly -> R_t is low.
Evaluation phase:
- No-Shift Regime: Queries match stream distribution (mostly Category X).
- Shift Regime: Queries invert distribution (mostly Category Y).
Compares:
- Adaptive Memory WITH Retrieval Prior (delta=0.3)
- Adaptive Memory WITHOUT Retrieval Prior (delta=0.0)
- FIFO
- Random
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


def run_benchmark_d(
    stream_length: int = 5000,
    capacity: int = 250,
    embedding_dim: int = 32,
    seed: int = 101,
) -> dict[str, Any]:
    torch.manual_seed(seed)

    # Centers for Category X (frequent) and Category Y (rare)
    cat_x_center = torch.randn(embedding_dim)
    cat_x_center = cat_x_center / torch.norm(cat_x_center)

    cat_y_center = torch.randn(embedding_dim)
    cat_y_center = cat_y_center - torch.dot(cat_y_center, cat_x_center) * cat_x_center
    cat_y_center = cat_y_center / torch.norm(cat_y_center)

    # 10 milestone events in Category X and 10 in Category Y (injected in first 1000 steps)
    needles_x: dict[int, Tensor] = {}
    needles_y: dict[int, Tensor] = {}
    for i in range(10):
        step_x = 50 + i * 40
        vx = cat_x_center + 0.05 * torch.randn(embedding_dim)
        needles_x[step_x] = vx / torch.norm(vx)

        step_y = 60 + i * 40
        vy = cat_y_center + 0.05 * torch.randn(embedding_dim)
        needles_y[step_y] = vy / torch.norm(vy)

    # Stream:
    # 85% Category X events (dense, bursty)
    # 15% Category Y events (sparse)
    stream: list[tuple[int, Tensor]] = []
    for step in range(stream_length):
        if step in needles_x:
            stream.append((step, needles_x[step]))
        elif step in needles_y:
            stream.append((step, needles_y[step]))
        else:
            if step % 7 == 0:  # Rare Category Y
                v = cat_y_center + 0.1 * torch.randn(embedding_dim)
            else:  # Frequent Category X
                v = cat_x_center + 0.1 * torch.randn(embedding_dim)
            v = v / torch.norm(v)
            stream.append((step, v))

    models = {
        "Adaptive_With_R": AdaptiveMemoryConfig(
            embedding_dim=embedding_dim,
            state_dim=embedding_dim,
            capacity=capacity,
            policy_mode="fixed_budget",
            eviction_policy="min_importance",
            alpha_surprise=0.25,
            beta_novelty=0.25,
            gamma_causal=0.1,
            delta_retrieval=0.3,  # High reliance on retrieval prior
            epsilon_uncertainty=0.1,
            seed=seed,
        ),
        "Adaptive_Without_R": AdaptiveMemoryConfig(
            embedding_dim=embedding_dim,
            state_dim=embedding_dim,
            capacity=capacity,
            policy_mode="fixed_budget",
            eviction_policy="min_importance",
            alpha_surprise=0.4,
            beta_novelty=0.4,
            gamma_causal=0.1,
            delta_retrieval=0.0,  # Zero reliance on retrieval prior
            epsilon_uncertainty=0.1,
            seed=seed,
        ),
        "FIFO": AdaptiveMemoryConfig(
            embedding_dim=embedding_dim,
            state_dim=embedding_dim,
            capacity=capacity,
            policy_mode="fixed_budget",
            eviction_policy="fifo",
            seed=seed,
        ),
        "Random": AdaptiveMemoryConfig(
            embedding_dim=embedding_dim,
            state_dim=embedding_dim,
            capacity=capacity,
            policy_mode="fixed_budget",
            eviction_policy="random",
            seed=seed,
        ),
    }

    results: dict[str, Any] = {}

    for name, cfg in models.items():
        temporal_cfg = TemporalStateConfig(input_size=embedding_dim, hidden_size=embedding_dim)
        temporal_model = TemporalState(temporal_cfg)
        h_state = temporal_model.initial_state(1)
        mem = AdaptiveMemory(cfg)

        for step, vec in stream:
            step_out = temporal_model.step(vec.unsqueeze(0), h_state)
            h_state = step_out.state
            mem.observe(event_id=step, timestamp=float(step), embedding=vec, temporal_state=h_state[0])

        # Evaluate Category X and Category Y retrieval separately
        def evaluate_set(needle_dict: dict[int, Tensor]) -> float:
            hits = 0
            for s, n_vec in needle_dict.items():
                q = n_vec + 0.02 * torch.randn(embedding_dim)
                q = q / torch.norm(q)
                retrieved = mem.retrieve(q, top_k=5)
                if retrieved and retrieved[0][0].event_id == s:
                    hits += 1
            return hits / len(needle_dict)

        acc_x = evaluate_set(needles_x)
        acc_y = evaluate_set(needles_y)

        # In No-Shift evaluation: 80% weight on X, 20% on Y
        acc_no_shift = 0.8 * acc_x + 0.2 * acc_y
        # In Shifted evaluation: 20% weight on X, 80% on Y (interest shifted to the sparse category)
        acc_shifted = 0.2 * acc_x + 0.8 * acc_y
        delta_acc = acc_shifted - acc_no_shift

        results[name] = {
            "acc_cat_x_dense": acc_x,
            "acc_cat_y_sparse": acc_y,
            "acc_no_shift": acc_no_shift,
            "acc_shifted": acc_shifted,
            "shift_degradation": delta_acc,
        }

    return results


if __name__ == "__main__":
    for s in [101, 202, 303]:
        r = run_benchmark_d(seed=s)
        print(f"Seed {s}:")
        for m, d in r.items():
            print(
                f"  {m:<20} X(Dense)={d['acc_cat_x_dense']*100:>5.1f}%  "
                f"Y(Sparse)={d['acc_cat_y_sparse']*100:>5.1f}%  "
                f"NoShift={d['acc_no_shift']*100:>5.1f}%  "
                f"Shifted={d['acc_shifted']*100:>5.1f}%  "
                f"Delta={d['shift_degradation']*100:>+5.1f}%"
            )
