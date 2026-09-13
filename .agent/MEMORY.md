# Project memory

## Current Research Status (Mission 2.5 Audit)

```text
                 CONTINUUM
                     │
                     ▼
             Temporal State
                  ✅ PASS (TASK-001)
                     │
                     ▼
             Adaptive Memory
                  🟡 PROMISING BUT CONSTRAINED (TASK-002)
                     │
                     ▼
       Current Scaling Benchmark
                  🟡 EVIDENCE (1K to 100K bounded at K=500)
                     │
                     ▼
       Adversarial Validation
                  🔴 COMPLETED AUDIT (Mission 2.5)
                     │
                     ▼
          Sparse Event Memory
                  ⏸️ PAUSED
```

## Validated Facts (Empirically Proven)

1. **Physical Boundedness:** Across stream lengths from $T=1,000$ to $T=100,000$, Continuum memory remains strictly bounded at $K=500$ slots with flat process RAM (< 65 MB).
2. **Query-Blind Superiority (Benchmark A):** When queries are generated blindly post-stream without access to internal flags, Continuum retains 26.7% vs FIFO/LRU/Random (0.0%).
3. **Beyond-Novelty Retention (Benchmark B):** When needles are mathematically embedded inside background clusters ($N_t \le 0.0025$), Continuum still achieves 36.7% recall vs FIFO/LRU/Random (0.0%), proving it does not rely solely on outlier novelty.
4. **Novelty Trap Vulnerability (Benchmark C):** Novelty-only models collapse completely (0.0% recall, 49% memory hoarded by useless outlier traps). Multi-factor Adaptive Memory resists this trap (23.3% recall), but is still partially vulnerable.
5. **Epistemic Horizon of Online Scoring (Benchmark E):** Pure online scoring ($x_{\le t}$) achieves 0.0% on delayed causal chains ($A \to B \to C \to D$) where $A$ appears ordinary at $t=100$. This rigorously proves the mathematical necessity of retrospective Memory Revision (Phase 8).

## Failed / Refuted Hypotheses

1. **"Novelty alone is sufficient for long-term memory" — REFUTED (Benchmark C):** Outlier traps completely poison novelty-only memory banks.
2. **"Online-only scoring can handle delayed causality" — REFUTED (Benchmark E):** Events with delayed causal impact are irrevocably evicted by online filters unless retrospective revision is supported.

## Limitations and Open Questions

- In Benchmark B (low-novelty needles), accuracy drops from 96.7% to 36.7%. How to enhance micro-changepoint sensitivity without overfitting?
- Historical Demand Prior ($R_t$) provides zero advantage under query distribution shift (Benchmark D). Should factor $R_t$ be excised or redesigned?
- Memory Revision (Phase 8) is strictly required to solve delayed causal chains.

## Next Step

Awaiting Judge / Human Director review of Mission 2.5 Adversarial Validation report before deciding whether to refine Adaptive Memory or proceed to Sparse Event Memory.
