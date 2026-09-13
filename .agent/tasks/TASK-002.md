---
task_id: TASK-002
owner: Continuum Engineering Agent
objective: Implement Adaptive Memory with online multi-factor retention policy and execute Ablation B (A vs B, B0-B6) across 3 canonical seeds.
dependencies:
  - RFC-0002 Architecture Gate Approval
  - Research Prior-Art Scan on Stream Retention
  - Benchmark Memory & Ablation Harness Specification
  - Adversarial Failure Probe Specification
status: IN_PROGRESS
files:
  - continuum/memory/adaptive_memory.py
  - tests/test_adaptive_memory.py
  - tests/adversarial/test_adaptive_memory_probes.py
  - benchmarks/memory/test_online_retention.py
  - experiments/ablation/run_ablation_b.py
tests: Unit, online streaming constraint, anti-leakage audit, capacity saturation
benchmark: Ablation B (A, B0-Random, B0-FIFO, B0-LRU vs B1..B6), 6 memory test suites
review: Architecture (APPROVED), Benchmark, Adversarial, Judge, Human Director
decision: in_progress
---

## Hypothesis

Given bounded memory capacity $K \ll T$, an online adaptive retention policy based on predictive surprise, structural novelty, and uncertainty will achieve statistically significant higher retrieval accuracy on distant critical events than fair memory baselines (Random, FIFO, LRU), while maintaining strictly bounded space $O(K \cdot D)$ and per-step processing time $O(K \cdot D)$.

## Engineering Gate Status

**UNBLOCKED (Architecture Gate Conditional Pass incorporated):**
1. Documented $O(KD)$ as Phase 3 baseline implementation complexity (Phase 4 Sparse Memory addresses sub-linear scaling).
2. Test 2 evaluates Redundancy Ratio & Unique Information Coverage against baselines (no arbitrary 1% mandate).
3. Test 4 evaluates against fair baselines: Random, FIFO, and LRU under identical budget $K$ and stream.
4. R0 designated as `Retrieval Prior / Demand Prior` (burstiness is not retrieval probability).
5. Mandatory correlation audit $\text{Corr}(S, C)$ and $\text{Corr}(N, C)$ enforced for Proxy Causal score.
6. Uncertainty formally defined as `Normalized Online Prediction Uncertainty` (recent residual variance via EMA).
7. Pre-registered canonical configuration locked: $\alpha=\beta=\gamma=\delta=\epsilon=0.2$. No post-hoc weight tuning allowed.
