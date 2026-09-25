# ContextSpindle Architecture Specification (formerly Continuum)

The public product is agent context memory. The legacy module, crate, and snapshot names remain in use during migration; see [the naming decision](NAME-CHANGE.md). The architecture below describes the existing research model and Rust engine, not a guarantee that every event survives bounded retention.

## 1. System Overview

**Continuum** is a continuous temporal intelligence engine designed for infinite-horizon streaming data. It operates under strictly bounded physical memory and compute budgets while preserving the ability to retrospectively interpret and revise past event representations when future evidence arrives.

```text
                               Streaming Events x_t
                                        │
                                        ▼
                   ┌──────────────────────────────────────────┐
                   │   Layer 1: Temporal Recurrence Core      │
                   │   (Gated Hidden State h_t, O(1) Memory)  │
                   └────────────────────┬─────────────────────┘
                                        │
                                        ▼
                   ┌──────────────────────────────────────────┐
                   │   Layer 2: Two-Tier Manifold Memory      │
                   │   (Strictly Bounded at K_total = 750)    │
                   │                                          │
                   │   ┌──────────────────────────────────┐   │
                   │   │ Hot Active Memory (K=250)        │   │
                   │   │ (Online 5-Factor Epistemic Gate) │   │
                   │   └───────────────┬──────────────────┘   │
                   │                   │                      │
                   │       [Bypass / Eviction Stream]         │
                   │                   │                      │
                   │   ┌───────────────▼──────────────────┐   │
                   │   │ Cold Candidate Memory (K=500)    │   │
                   │   │ (Subspace Redundancy Control)    │   │
                   │   └───────────────┬──────────────────┘   │
                   └───────────────────┼──────────────────────┘
                                       │
                         [Incident / Query Trigger]
                                       │
                                       ▼
                   ┌──────────────────────────────────────────┐
                   │   Layer 3: Retrospective Revision Engine │
                   │   (Causal Separation Margin CSM-Gated)   │
                   └──────────────────────────────────────────┘
```

---

## 2. Core Architectural Layers

### Layer 1: Temporal Recurrence Core (`TemporalState`)
- **Role:** Maintains a smooth, low-dimensional dynamical latent state $h_t \in \mathbb{R}^{H}$ that tracks local regime transitions and predictability.
- **Complexity:** $O(1)$ constant time and memory per step.

### Layer 2: Two-Tier Manifold Memory (`AdaptiveMemory` + `BypassColdMemory`)
- **Strict Budget Invariant:** $K_{\text{total}} = 750$ slots ($K_{\text{hot}} = 250, K_{\text{cold}} = 500$).
- **Hot Working Set:** Computes 5 online factors without lookahead:
  $$\text{Importance}(x_t) = 0.2 S_t + 0.2 N_t + 0.2 C_t + 0.2 R_t + 0.2 U_t$$
- **Bypass Admission:** Prevents the "Hot-Gate Discard" flaw discovered in Mission 2.9.7. If Hot Memory rejects a subtle event, Cold Memory evaluates it independently against its subspace diversity manifold.
- **Representational Redundancy Control:** In Cold Memory, pairwise cosine similarity $\ge 0.85$ triggers elimination of duplicate background clusters, guaranteeing that slots are reserved for orthogonal dynamical regimes.

### Layer 3: Retrospective Revision Engine (`RevisionEngine`)
- **Role:** When a terminal symptom or anomaly $D$ is observed, evaluates all stored candidate events:
  $$\text{RevisionScore}(A, D) = 0.4 \cdot \text{sim} + 0.3 \cdot \text{state\_compat} + 0.2 \cdot \text{temporal\_compat} + 0.1 \cdot \text{provenance}$$
- **CSM-Gated Decay:** Expands the effective time horizon $\tau$ proportionally to causal compatibility, preventing temporal decay from prematurely crushing distant genuine root causes.
