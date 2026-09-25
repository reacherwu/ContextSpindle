# ContextSpindle Technical Constitution (formerly Continuum)

The current implementation delivers bounded, persistent context memory for AI agents. It aims for repeatable retrieval from a fixed snapshot and query; it does not claim deterministic language-model responses or perfect retention. The current ContextSpindle product goal is task continuity as defined in [PRODUCT-SCOPE.md](PRODUCT-SCOPE.md). The research questions below are preserved from the earlier Continuum research phase and remain evidence requirements for any broader ACM claims.

Continuum is a continuous temporal intelligence engine built around **Adaptive Causal Memory (ACM)**. It aims to process arbitrary-duration event streams with bounded active memory and support selective retrieval, causal reasoning, and historical memory revision.

## Research objective

Test, rather than assume, whether ACM can provide competitive long-range memory at lower memory cost than selected baselines. v0.1 is a Python/PyTorch research prototype, not a product SDK, a quantum system, or a claim of unlimited storage.

## Rules

1. Any superiority claim must be benchmark verified.
2. Development agents cannot modify benchmark standards.
3. Benchmark agents cannot modify the ContextSpindle algorithm.
4. Failed experiments must be retained.
5. Unfavorable results must never be deleted.
6. No cherry-picking.
7. No baseline-free performance claims.
8. Core conclusions require repeated experiments.
9. Quantum-inspired mechanisms must not be described as quantum computing.
10. Streaming with bounded memory is not infinite physical storage.
11. Correlation must not be described as causation.
12. Benchmark configurations must be version controlled.

## Research questions

- RQ1: Does early-event retrieval remain accurate over long event streams?
- RQ2: What memory, latency, and throughput trade-offs emerge against fair baselines?
- RQ3: Can sparse selection retrieve relevant events without retaining all activations?
- RQ4: Can explicit causal hypotheses support multi-hop event-chain queries?
- RQ5: Can later evidence revise historical interpretation without erasing provenance?
