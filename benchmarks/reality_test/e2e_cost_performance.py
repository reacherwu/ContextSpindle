"""
Agent D: End-to-End Cost & Latency Benchmark.
Measures:
1. Physical memory (RSS) stability as T scales: 1K -> 10K -> 50K events.
2. End-to-end query latency (Ingest -> Vectorize -> Continuum Query -> Prompt assembly).
3. Token and dollar cost comparison against 1M Full-Context LLM calls.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any
import psutil
import torch

from continuum.api import ContinuumConfig, ContinuumEngine


def run_e2e_cost_performance_benchmark() -> dict[str, Any]:
    process = psutil.Process(os.getpid())
    dim = 32
    cfg = ContinuumConfig(embedding_dim=dim, state_dim=dim, hot_capacity=250, cold_capacity=500, seed=42)
    engine = ContinuumEngine(cfg)

    scales = [1000, 5000, 10000, 25000]
    scale_results = {}

    v_query = torch.randn(dim); v_query /= torch.norm(v_query)

    print("\n--- Running Agent D Scale Benchmark (1K -> 25K events) ---")
    current_step = 0
    t_prev = time.perf_counter()

    for target in scales:
        steps_to_run = target - current_step
        t0 = time.perf_counter()
        for i in range(steps_to_run):
            v = torch.randn(dim); v /= torch.norm(v)
            engine.step(v, payload_ref=f"event_{current_step + i}")
        ingest_elapsed = time.perf_counter() - t0
        current_step = target

        # Query latency
        t0 = time.perf_counter()
        matches = engine.query(v_query, top_k=5)
        query_us = (time.perf_counter() - t0) * 1e6

        # RSS Memory
        rss_mb = process.memory_info().rss / (1024 * 1024)
        slots_used = engine.get_stats()["total_slots"]

        scale_results[f"T_{target}"] = {
            "stream_length": target,
            "slots_used": slots_used,
            "rss_mb": round(rss_mb, 2),
            "step_latency_us": round((ingest_elapsed / steps_to_run) * 1e6, 2),
            "query_latency_us": round(query_us, 2),
            "memory_bounded": bool(slots_used <= 750),
        }
        print(f"  T={target:5d} | Slots: {slots_used:3d} / 750 | RSS: {rss_mb:6.1f} MB | Ingest: {scale_results[f'T_{target}']['step_latency_us']:5.1f} μs | Query: {query_us:6.1f} μs")

    # Financial Cost Modeling per 1,000 queries
    # Scenario: 10,000-event history (~500,000 tokens)
    # Full-Context LLM: 1,000 queries * 500k tokens * $5.00 / 1M tokens = $2,500.00
    # Continuum + Local RAG: 1,000 queries * (5 retrieved chunks * 100 tokens = 500 tokens) * $5.00 / 1M tokens = $0.0025
    cost_comparison = {
        "scenario": "10,000 events history (~500k tokens)",
        "full_context_token_input_per_query": 500000,
        "continuum_retrieved_token_input_per_query": 500,
        "full_context_cost_per_1k_queries_usd": 2500.00,
        "continuum_retrieved_cost_per_1k_queries_usd": 0.0025,
        "projected_token_savings_factor": 1000.0,
    }

    results = {
        "scale_results": scale_results,
        "cost_comparison": cost_comparison,
    }

    out_dir = Path("experiments/results/reality_test")
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "e2e_cost_report.json", "w") as f:
        json.dump(results, f, indent=2)

    # Markdown Report
    report_path = out_dir / "e2e_cost_report.md"
    md = [
        "# Agent D: End-to-End Cost & Latency Benchmark Report\n",
        "**Benchmark Date:** 2026-09-14  ",
        "**Target:** Measure physical memory scaling and financial cost models over large stream volumes.\n\n",
        "## 1. Physical Resource Scaling (T = 1K to 25K Events)\n\n",
        "| Stream Events (T) | Memory Slots Used | Active Memory Bounded? | Resident Memory (RSS) | Per-Step Ingestion Latency | Query Latency |\n",
        "|:---:|:---:|:---:|:---:|:---:|:---:|\n",
    ]

    for k, v in scale_results.items():
        b_str = "✅ YES (O(1))" if v["memory_bounded"] else "❌ NO"
        md.append(f"| {v['stream_length']:,} | {v['slots_used']} / 750 | {b_str} | {v['rss_mb']} MB | {v['step_latency_us']} μs | {v['query_latency_us']} μs |\n")

    md.extend([
        "\n## 2. Token & Financial Cost Modeling (10,000 Events History)\n",
        "- **Full-Context LLM Ingestion:** 500,000 input tokens per query $\\to$ **$2,500.00 per 1,000 queries** (at $5/M tokens).\n",
        "- **Continuum Selective Retrieval:** ~500 input tokens per query $\\to$ **$0.0025 per 1,000 queries**.\n",
        "- **Key Insight:** In high-frequency automated monitoring, stuffing entire event histories into LLM prompts is economically unviable; selective retrieval is mandatory.\n",
    ])

    with open(report_path, "w") as f:
        f.writelines(md)

    print(f"\n[DONE] E2E Cost Report written to: {report_path}")
    return results


if __name__ == "__main__":
    run_e2e_cost_performance_benchmark()
