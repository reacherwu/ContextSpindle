# Continuum: Product Positioning & Value Proposition

> **Product Scope & Physical Architecture**:  
> Continuum is an **embedded streaming engine with bounded active memory ($O(K), K \ll T$) and retrospective causal revision** for autonomous AI agents and streaming systems.  
> **What Continuum IS**: A lightweight decision engine that determines what AI should remember, retrieve, and revise within an unbounded stream of events.  
> **What Continuum IS NOT**: It does not replace the underlying raw data lake, event archive, or cold log store ($O(T)$).

---

## 1. Physical Architecture: Active Memory vs. Raw Archive

```text
                             CONTINUUM
                                 │
                      ┌──────────┴──────────┐
                      ↓                     ↓
             Bounded Intelligence      Raw Archive
                 Memory O(K)             O(T)
                      │
                      ↓
               [What to remember?]
               Online stream evaluation: Surprise, Novelty, Subspace Redundancy Control
                      │
                      ↓
               [What to retrieve?]
               On-demand causal query: Backtracks through noise to find root causes
                      │
                      ↓
               [What to revise?]
               Post-hoc belief update: Overturns stale hypotheses when evidence arrives
```

---

## 2. Core Value Proposition (Design Hypotheses)

### 1. Ingestion without LLM Maintenance Overhead
- **Hypothesis**: Many existing memory frameworks (e.g. Mem0, Zep) invoke an LLM for entity extraction, summarization, or graph construction during ingestion.
- **Continuum Approach**: Ingests streaming vectors via local tensor operations with **zero LLM calls during ingestion**. Downstream LLMs are only queried when an action or explanation is needed.

### 2. Retrospective Causal Revision
- **Hypothesis**: In real-world incident analysis and long agent trajectories, symptoms rarely match root causes directly in keyword space. Naive Vector RAG tends to surface recent symptoms rather than the root cause.
- **Continuum Approach**: The **Revision Engine** combines semantic affinity, temporal dynamics, and state fingerprints to backtrack along the trajectory, dampening recent noise storms.

### 3. Strictly Bounded Active Footprint ($Memory(T) = O(K)$)
- **Design Target**: Constant active memory slots (e.g. $K=750$, RSS $< 50\ \text{MB}$) regardless of whether the stream has run for 1,000 steps or 1,000,000 steps.

---

## 3. Target Customer Segments & Validation Metrics

| Customer Segment | Core Challenge | Continuum Target Solution | Target Validation Metric |
|:---|:---|:---|:---|
| **AIOps & Observability** | Alert fatigue; finding early root causes across 24h of log noise. | Bounded memory streams logs; pinpoints configuration root causes under alert storms. | **Root-Cause Recall@5** under 100+ alert decoys. |
| **Autonomous Coding & DevOps Agents** | Agent trajectories fail due to early unspotted setup errors. | Preserves trajectory in bounded slots; auto-traces test failures back to early setup commands. | **Backtracking Accuracy** across 100+ step agent traces. |
| **Personal AI Digital Assistants** | Critical user constraints (dietary, medical, financial) forgotten after 50 turns. | Hard constraints preserved permanently in active/cold memory across thousands of turns. | **Zero Critical Constraint Loss** after 2,000+ conversational turns. |
