# Continuum Memory Reliability & Audit Specification

> **Mission**:  
> Memory without verifiability is a liability. In high-stakes enterprise applications, AI memory must never hallucinate connections, leak downstream data, or present unverifiable claims.  
> Continuum enforces **strict provenance, zero lookahead, and component score transparency** at every layer of the architecture.

---

## 1. The 5 Pillars of Memory Reliability

### 1. Zero Data Leakage (No Lookahead / Strict Causality)
- **Principle**: An event at time $t$ can only be observed, scored, and admitted into memory based on information available at $t' \le t$.
- **Enforcement**:
  - In `AdaptiveMemory`, surprise and novelty are computed strictly against existing buffer state $M_{t-1}$.
  - In `TemporalState`, the recurrent hidden state $h_t$ is updated sequentially via causal autoregression.
  - Future trigger symptoms or downstream queries are strictly prohibited from leaking into the observation phase.

### 2. Resistance to False Causality (Decoy & Recency Bias Defense)
- **Principle**: Pure temporal correlation or recency must never be confused with genuine causal explanation.
- **Enforcement**:
  - The Causal-Semantic Gating mechanism in `RevisionEngine` requires candidates to demonstrate genuine semantic affinity before granting recency exemptions.
  - Distant random events and recent irrelevant chit-chat cannot bypass the gating threshold.

### 3. Traceable Provenance (Auditability)
- **Principle**: Every memory retrieved by the system must carry an unforgeable trace back to its origin.
- **Enforcement**:
  - Every `CausalMatch` returned by `engine.query()` contains:
    - `event_id`: Immutable integer sequence ID.
    - `timestamp`: Physical or logical event arrival time.
    - `provenance`: Trace string recorded at observation (e.g. log line, commit hash, or chat turn).

### 4. Transparent Score Decomposition
- **Principle**: No black-box similarity numbers. Downstream agents and human operators must be able to inspect why an event was retrieved.
- **Enforcement**:
  - Every match includes a detailed `components` dictionary:
    ```python
    match.components = {
        "sim": 0.985,              # Direct semantic cosine similarity
        "state_compat": 1.000,     # Dynamical state trajectory alignment
        "temporal_compat": 1.000,  # Causal-gated temporal factor
        "provenance_compat": 0.500 # Source confidence weight
    }
    ```

### 5. Deterministic Reproducibility
- **Principle**: Given identical seeds and identical event streams, Continuum produces identical memory states and identical retrieval rankings.
- **Enforcement**: Fully verified by `tests/test_integration_v01.py` (`test_reproducibility_across_instances`).
