"""
Adversarial Benchmark A: Query-Blind Evaluation.
Tests whether Continuum retains key events when query generation is completely uncoordinated
with event ingestion. The streaming engine sees only event_t in online sequence.
After stream completion, queries are drawn randomly from domain key spaces without accessing
event importance, retention decisions, record IDs, or needle annotations.
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


def run_benchmark_a(
    stream_length: int = 5000,
    capacity: int = 300,
    embedding_dim: int = 32,
    seed: int = 101,
) -> dict[str, Any]:
    torch.manual_seed(seed)

    # 1. Define a set of 30 independent domain concepts/topics
    n_topics = 30
    topic_centers = torch.randn(n_topics, embedding_dim)
    topic_centers = topic_centers / torch.norm(topic_centers, dim=-1, keepdim=True)

    # 2. Generate stream:
    # 20 topics appear periodically as background activity.
    # 10 designated target facts appear in the first 500 steps.
    stream: list[tuple[int, Tensor]] = []
    ground_truth_targets: dict[int, Tensor] = {}  # topic_id -> embedding (kept outside the model)

    target_topic_ids = list(range(10))
    for step in range(stream_length):
        if step < 500 and step % 50 == 0:
            tid = target_topic_ids[(step // 50) % len(target_topic_ids)]
            # Target event is an instance of this target topic
            vec = topic_centers[tid] + 0.05 * torch.randn(embedding_dim)
            vec = vec / torch.norm(vec)
            stream.append((step, vec))
            ground_truth_targets[tid] = vec
        else:
            # Routine stream events from remaining 20 topics
            tid = 10 + (step % (n_topics - 10))
            vec = topic_centers[tid] + 0.1 * torch.randn(embedding_dim)
            vec = vec / torch.norm(vec)
            stream.append((step, vec))

    # Models to test
    models = {
        "Continuum": ("min_importance", 0.35, 0.35, 0.1, 0.1, 0.1),
        "B_fifo": ("fifo", 0.2, 0.2, 0.2, 0.2, 0.2),
        "B_random": ("random", 0.2, 0.2, 0.2, 0.2, 0.2),
        "B_lru": ("lru", 0.2, 0.2, 0.2, 0.2, 0.2),
        "A_temporal_state": None,
    }

    results: dict[str, Any] = {}

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

        # Execution (Online streaming strictly blind to queries)
        t0 = time.perf_counter()
        for step, vec in stream:
            step_out = temporal_model.step(vec.unsqueeze(0), h_state)
            h_state = step_out.state
            if mem is not None:
                mem.observe(event_id=step, timestamp=float(step), embedding=vec, temporal_state=h_state[0])
        elapsed = time.perf_counter() - t0

        # Blind Evaluation:
        # Generate queries randomly for the 10 target topics using an independent noise draw
        # (NO access to memory records, internal scores, or event IDs)
        hits = 0
        mrr_sum = 0.0
        sim_sum = 0.0

        for tid in target_topic_ids:
            target_vec = ground_truth_targets[tid]
            # Query is drawn from the target topic concept center with noise
            query = topic_centers[tid] + 0.03 * torch.randn(embedding_dim)
            query = query / torch.norm(query)

            if mem is not None:
                retrieved = mem.retrieve(query, top_k=5)
                if retrieved:
                    sim_sum += retrieved[0][1]
                    for rank, (r, sim) in enumerate(retrieved, start=1):
                        # Measure cosine similarity between retrieved embedding and target
                        target_sim = float(torch.dot(r.embedding, target_vec).item())
                        if target_sim > 0.90:  # Matches the target fact closely
                            mrr_sum += 1.0 / rank
                            if rank == 1:
                                hits += 1
                            break
            else:
                # TemporalState alone
                h_norm = h_state[0] / torch.norm(h_state[0])
                sim = float(torch.dot(h_norm, target_vec).item())
                sim_sum += sim
                if sim > 0.90:
                    hits += 1
                    mrr_sum += 1.0

        n_eval = len(target_topic_ids)
        results[name] = {
            "accuracy": hits / n_eval,
            "mrr": mrr_sum / n_eval,
            "mean_sim": sim_sum / n_eval,
            "elapsed_sec": elapsed,
        }

    return results


if __name__ == "__main__":
    for s in [101, 202, 303]:
        r = run_benchmark_a(seed=s)
        print(f"Seed {s}:")
        for m, d in r.items():
            print(f"  {m:<16} Acc={d['accuracy']*100:>5.1f}%  MRR={d['mrr']:.3f}  Sim={d['mean_sim']:.3f}")
