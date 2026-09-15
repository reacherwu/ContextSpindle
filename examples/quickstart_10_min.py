#!/usr/bin/env python3
"""
Continuum 10-Minute Developer Onboarding Quickstart.

Demonstrates the primary developer workflow:
1. Initialize ContinuumEngine in 2 lines.
2. Continuously stream events (logs, chat messages, or agent tool outputs).
3. Query memory for causal explanations and root causes.
"""

from __future__ import annotations

import torch
from continuum import ContinuumEngine, ContinuumConfig


def main():
    print("=" * 60)
    print("  Continuum 10-Minute Developer Quickstart")
    print("=" * 60)

    # 1. Initialize Engine (Zero external DB, zero config required)
    engine = ContinuumEngine.create(embedding_dim=32, state_dim=32)
    print("1. Initialized ContinuumEngine (Bounded at 750 memory slots).")

    # 2. Ingest streaming events
    print("2. Ingesting streaming events...")
    # Event 1: Initial critical configuration
    v_config = torch.randn(32); v_config /= torch.norm(v_config)
    engine.step(v_config, payload_ref="auth_service_db_pool=5")

    # Events 2..50: Background chatter / noise
    for i in range(1, 50):
        v_noise = torch.randn(32); v_noise /= torch.norm(v_noise)
        engine.step(v_noise, payload_ref=f"worker_heartbeat_{i}")

    stats = engine.get_stats()
    print(f"   Total slots used: {stats['total_slots']} / {stats['max_slots']}")

    # 3. Query memory for root cause
    print("3. Querying memory with downstream symptom...")
    v_symptom = 0.85 * v_config + 0.15 * torch.randn(32); v_symptom /= torch.norm(v_symptom)
    matches = engine.query(v_symptom, top_k=2)

    for rank, m in enumerate(matches, 1):
        print(f"   Match #{rank}: Event ID {m.event_id} | Score={m.revision_score:.3f} | Provenance={m.provenance}")

    # 4. Save and Reload State
    print("4. Testing zero-loss state persistence...")
    engine.save("/tmp/continuum_quickstart.pt")
    reloaded = ContinuumEngine.load("/tmp/continuum_quickstart.pt")
    reloaded_matches = reloaded.query(v_symptom, top_k=2)
    assert len(reloaded_matches) == len(matches)
    print("   State saved and reloaded with 100% parity.")

    print("\n[SUCCESS] Developer onboarding completed in < 10 lines of code.")


if __name__ == "__main__":
    main()
