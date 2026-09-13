# Continuum

**Continuum — Continuous Temporal Intelligence Engine** is a research prototype for testing Adaptive Causal Memory (ACM): bounded-memory processing of continuous event streams with selective retrieval, causal hypotheses, and auditable memory revision.

This repository intentionally makes no superiority, novelty, or "unlimited context" claims. Those require repeatable, fair experiments against recorded baselines.

## Status

Mission 0 (orchestration setup) is in progress. The first implementation task is a minimal temporal state plus a reproducible small benchmark.

## Principles

- Streaming capability does not mean infinite physical storage.
- Correlation, temporal order, causal hypothesis, and validated causal relation are distinct.
- Failed experiments and unfavorable results are retained.
- Benchmark standards are owned separately from model code.

## Planned quick start

After TASK-001 is approved and implemented:

```bash
python -m pytest
make benchmark-small
```

See [the specification](docs/CONTINUUM-SPEC.md), [architecture](docs/ARCHITECTURE.md), and [agent protocol](.agent/README.md).
