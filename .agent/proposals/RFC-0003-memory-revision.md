# RFC-0003: Memory Revision Implementation

**Status:** DRAFT
**Decision Owner:** Architecture Agent
**Target Phase:** Phase C (Mission 2.7)

## 1. Problem Statement

Online-only scoring ($x_{\le t}$) achieves 0.0% on delayed causal chains (Benchmark E). Root cause A at $t=100$ is evicted before terminal D at $t=5100$.

## 2. Architecture

Hot Memory + Cold Candidate Memory + Revision Engine

```
STREAM → Online Judge (frozen 0.2) → HOT (K events)
                                     ↓ (eviction)
                                    COLD (K_cold compressed candidates)
                                     ↓ (high-significance trigger)
                                 Revision Engine
                                     ↓
                                Restore / Ignore
```

## 3. ColdCandidateRecord Spec

```python
from dataclasses import dataclass
from torch import Tensor

@dataclass(frozen=True)
class ColdCandidateRecord:
    event_id: int
    timestamp: float
    compressed_embedding: Tensor  # Shape: [D], float32, normalized
    state_fingerprint: Tensor     # Shape: [H], state snapshot at eviction
    importance_at_eviction: float  # I_t when evicted
    provenance_summary: str       # Brief trace of why it was initially kept/evicted
```

## 4. Pre-Registered RevisionScore (FROZEN)

$$R(A,D) = w_1 \cdot \text{Sim}(A_{emb}, D_{emb}) + w_2 \cdot \text{StateCompat}(A, D) + w_3 \cdot \text{TemporalCompat}(A, D) + w_4 \cdot \text{ProvenanceCompat}(A, D)$$

- $w_1 = 0.4$ (embedding cosine similarity)
- $w_2 = 0.3$ (state fingerprint cosine similarity)
- $w_3 = 0.2$ (temporal decay: $\exp(-\Delta t/\tau)$, $\tau=1000$)
- $w_4 = 0.1$ (provenance compatibility, v1 constant 0.5)
- $\theta_{trigger} = 0.7$ (only trigger revision when $I(D) > 0.7$)
- $\theta_{restore} = 0.5$ (only restore when $R(A,D) > 0.5$)
- $K_{cold} = 2K$ (cold capacity is 2x hot capacity, FIFO eviction when full)

## 5. Experimental Protocol

6 conditions (E0-E5) + 4 negative controls.

## 6. Metrics

Recall_root, FalseRevisionRate, RevisionPrecision, ColdCost, Latency_revision, TotalMemory
