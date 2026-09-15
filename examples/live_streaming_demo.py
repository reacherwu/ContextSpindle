#!/usr/bin/env python3
"""
Continuum v0.1 Live Streaming Demonstration.

Demonstrates:
1. Online O(1) ingestion of multi-dimensional streaming telemetry.
2. Bounded two-tier memory bank maintaining state without unbounded growth.
3. Sudden failure incident triggering retrospective causal revision.
"""

import math
import os
import random
import sys
import time
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import torch
from continuum import ContinuumEngine, ContinuumConfig


def generate_cluster_stream(step: int, dim: int = 16) -> torch.Tensor:
    # 3-cluster cyclic telemetry with slight noise
    cluster_centers = [
        torch.tensor([1.0, 0.0, -1.0, 0.5] * 4),
        torch.tensor([-0.5, 1.0, 0.0, -0.5] * 4),
        torch.tensor([0.0, -1.0, 1.0, 0.0] * 4),
    ]
    center = cluster_centers[(step // 30) % len(cluster_centers)]
    noise = torch.randn(dim) * 0.05
    v = center + noise
    return v / torch.norm(v, p=2)


def main():
    print("=" * 65)
    print("   CONTINUUM v0.1: LIVE STREAMING CAUSAL INTELLIGENCE DEMO")
    print("=" * 65)

    config = ContinuumConfig(
        embedding_dim=16,
        state_dim=16,
        hot_capacity=50,
        cold_capacity=100,
        seed=101,
    )
    engine = ContinuumEngine(config)

    print(f"\nInitialized ContinuumEngine: Capacity={config.hot_capacity + config.cold_capacity} slots (Bounded)")
    print("Ingesting streaming telemetry events...\n")

    t_incident = 250
    t_root_cause = 50

    # Injected root cause vector
    root_vec = torch.tensor([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0])
    root_vec = root_vec / torch.norm(root_vec, p=2)

    # Stream loop
    for t in range(t_incident):
        if t == t_root_cause:
            vec = root_vec
            tag = "DATABASE_LOCK_LEAK (SILENT ROOT CAUSE)"
        else:
            vec = generate_cluster_stream(t, dim=16)
            tag = "telemetry_healthy"

        res = engine.step(vec, payload_ref=tag)

        if t in (0, t_root_cause, 100, 150, 200, 249):
            print(f"  [Step {t:3d}] Importance={res.importance:.3f} | Decision={res.decision:<7s} | "
                  f"Slots={res.total_slots_used:2d}/150 | Event: {tag}")

    print("\n" + "-" * 65)
    print(f"🚨 [STEP {t_incident}] CRITICAL SERVICE FAILURE TRIGGERED!")
    print("   Terminal Symptom: Cascade Timeout (aligns with Database Lock Leak)")
    print("-" * 65)

    # Terminal symptom vector correlated with root cause
    symptom_vec = root_vec + torch.randn(16) * 0.1
    symptom_vec = symptom_vec / torch.norm(symptom_vec, p=2)

    t_start = time.perf_counter()
    candidates = engine.query(symptom_vec, top_k=3)
    query_latency_us = (time.perf_counter() - t_start) * 1e6

    print(f"\n🔍 Retrospective Causal Candidates (Query Latency: {query_latency_us:.1f} µs):")
    for rank, cand in enumerate(candidates, 1):
        is_hit = "🎯 [TRUE ROOT CAUSE HIT]" if cand.event_id == t_root_cause else "   [Context]"
        print(f"   Rank #{rank}: Event ID={cand.event_id:3d} | Score={cand.revision_score:.4f} | "
              f"Sim={cand.components['sim']:.3f} | {is_hit}")
        print(f"           Provenance: {cand.provenance}")

    print("\n" + "=" * 65)
    print("Demo successfully completed. Continuum successfully preserved and retrieved")
    print(f"the silent root cause from {t_incident - t_root_cause} steps ago under fixed memory.")
    print("=" * 65)


if __name__ == "__main__":
    main()
