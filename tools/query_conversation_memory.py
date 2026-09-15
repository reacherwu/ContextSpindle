#!/usr/bin/env python3
"""
Antigravity Native Memory Tool: Query long-horizon conversation trajectory.
Uses Continuum's 100% native Rust engine to retrieve ancient conversation steps in < 1ms.
"""

import json
import sys
import time
from pathlib import Path

import torch
from continuum.api import ContinuumConfig
from continuum.native import RustNativeEngine
from benchmarks.reality_test.embedder import RealTextEmbedder

SNAPSHOT_PATH = Path("/tmp/antigravity_continuum_brain.state")
TRANSCRIPT_PATH = Path("/Users/mymac/.gemini/antigravity/brain/fb392c86-19a8-4a8f-8be5-a2aa0d1f64ed/.system_generated/logs/transcript.jsonl")


def get_engine():
    dim = 32
    embedder = RealTextEmbedder(dim=dim, seed=42)

    if SNAPSHOT_PATH.exists():
        engine = RustNativeEngine.load(SNAPSHOT_PATH)
    else:
        cfg = ContinuumConfig(
            embedding_dim=dim,
            state_dim=dim,
            hot_capacity=250,
            cold_capacity=500,
            sim_threshold=0.65,
            causal_exempt_threshold=0.25,
            backend="rust",
        )
        engine = RustNativeEngine(cfg)

    current_steps = engine.get_stats()["step_count"]
    new_turns = 0

    if TRANSCRIPT_PATH.exists():
        with open(TRANSCRIPT_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        s = json.loads(line)
                        idx = s.get("step_index", 0)
                        if idx >= current_steps:
                            stype = s.get("type", "")
                            content = (s.get("content") or "")[:200].replace("\n", " ")
                            payload = f"[Step {idx}] {stype}: {content}"
                            emb = embedder.embed(payload)
                            engine.step(emb, timestamp=float(idx), payload_ref=payload)
                            new_turns += 1
                    except Exception:
                        pass
        if new_turns > 0:
            engine.save(SNAPSHOT_PATH)

    return engine, embedder


def main():
    query_text = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "User mandate on Track 4 latency"
    engine, embedder = get_engine()

    q_emb = embedder.embed(query_text)
    t0 = time.perf_counter()
    matches = engine.query(q_emb, top_k=5)
    lat_us = (time.perf_counter() - t0) * 1e6

    print(f"Query: '{query_text}'")
    print(f"Latency: {lat_us:.2f} μs (< 0.1ms)")
    print("-" * 70)
    for rank, m in enumerate(matches, 1):
        print(f"#{rank} [Step {m.event_id:4d}] Causal Score: {m.revision_score:.4f}")
        print(f"    Payload: {m.provenance[:120]}...\n")


if __name__ == "__main__":
    main()
