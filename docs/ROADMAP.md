# Roadmap

Current priority (2026-09-25): durable task ledger, task resume, task-aware context assembly with explicit token budgets, and long-horizon recovery tests. The bounded memory engine remains a retrieval component, not the task source of truth. See [PRODUCT-SCOPE.md](PRODUCT-SCOPE.md). The table below is the earlier ACM research roadmap and is retained for provenance.

| Phase | Deliverable | Gate |
| --- | --- | --- |
| 0 | Repository, roles, protocols, research scan | Judge review of plan |
| 1 | Skeleton, tests, experiment logging | Reproducibility check |
| 2 | Minimal temporal state | TASK-001 benchmark + adversarial review |
| 3 | Adaptive memory | Ablation B |
| 4 | Sparse retrieval | Ablation C |
| 5 | Router | Retrieval-routing tests |
| 6 | Phase interaction | Ablation D |
| 7 | Causal memory | Multi-hop benchmark |
| 8 | Revision | Revision benchmark |
| 9–14 | Integration, baselines, ablation, scaling | Judge decision at each milestone |

Target scales (1K through 100M) are reporting points, not promises. Any unrun scale is recorded as not runnable on current hardware.
