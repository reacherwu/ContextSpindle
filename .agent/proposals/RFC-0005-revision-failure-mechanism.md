# RFC-0005: Mission 2.9 — Revision Failure Mechanism Investigation

**Status:** PRE-REGISTERED  
**Date:** 2026-09-13  
**Authors:** Continuum Core Team & Autonomous Agent  
**Mandate:** CTO / Chief Science Officer Directives (Problem-Driven Research)  
**Target Modules:** `benchmarks/failure_mechanism/`  

---

## 1. Context & Motivation

Continuum Mission 2.8 and Mission 2.8.1 established the 3D Operating Envelope of Retrospective Memory Revision, identifying two major structural failure boundaries:
1. **Multi-hop causal chains break:** $A \to D$ achieves 100.0% recall, while $A \to B \to D$ collapses to 0.0% ($L \ge 4$ collapses to 33.3%).
2. **Candidate crowding breaks:** Flooding cold memory with 500 distractors destroys precision and recall (0.0%). Crucially, physical RAM is negligible (< 0.1 MB for 500 candidates), demonstrating that the bottleneck is **causal identifiability / discrimination**, not physical capacity.

Rather than prematurely introducing external components (Vector DB, GNN, Phase Attention, Mamba) or advancing to Phase 4 (Sparse Event Memory remains PAUSED), Mission 2.9 investigates the **exact failure mechanics** of the existing Continuum Revision prototype.

---

## 2. Core Research Questions & Hypotheses

### Question A: Candidate Attribution (Exp A)
- **Question:** When the true root cause fails to be restored, did it fail to enter the searched Top-$K$ candidate list (`cold_memory.search`), or did it enter Top-$K$ but receive an inferior score (`revision_engine.try_revision`) compared to a decoy, or did it get disqualified by `theta_restore`?
- **Hypothesis A1 (Top-K Filter Bottleneck):** In dense streams or intermediate chains, initial cosine similarity filtering against terminal evidence $e_{\text{terminal}}$ ranks intermediate/decoy events higher than root $e_{\text{root}}$, preventing $e_{\text{root}}$ from being scored by `RevisionEngine`.
- **Hypothesis A2 (Scoring Inversion Bottleneck):** $e_{\text{root}}$ is present in Top-$K$ candidates, but decay or decoys yield $Score(e_{\text{decoy}}) > Score(e_{\text{root}})$.
- **Hypothesis A3 (Gating Bottleneck):** $e_{\text{root}}$ is Top-1, but $Score(e_{\text{root}}) \le \theta_{\text{restore}}$.

### Question B: Hop Attenuation (Exp B)
- **Question:** How does causal evidence degrade across intermediate hops in a multi-hop causal chain ($A \to B \to \dots \to D$)?
- **Hypothesis B1 (Distance Attenuation):** Similarity, state compatibility, and temporal proximity each attenuate monotonically with hop distance from the terminal trigger:
  $$\text{Hop } 0 \to \text{Hop } 1 \to \dots \to \text{Hop } k$$
- **Hypothesis B2 (Intermediate Shadowing):** In $A \to B \to D$, node $B$ has higher similarity and temporal proximity to $D$ than $A$. If $B$ is in cold memory, does $B$ shadow $A$? If $B$ is in hot memory, why does $A$ fail?

### Question C: Crowding Decomposition (Exp C)
- **Question:** Exactly which component of the Revision Judge is fooled by distractors when $|D| = 500$?
- **Hypothesis C1 (Similarity Decoy):** Distractors with high cosine similarity alone to $D$ dominate the cold top-$K$ search and achieve higher scores than the distant root.
- **Hypothesis C2 (State Decoy):** Distractors with state fingerprints close to trigger state fool the dynamical compatibility term.
- **Hypothesis C3 (Temporal Decoy):** Distractors temporally close to terminal trigger ($t \approx T$) receive high temporal compatibility $e^{-\Delta t / \tau}$.
- **Hypothesis C4 (Synergistic Decoy):** Simultaneous high similarity + high state compatibility creates an insurmountable decoy barrier.

---

## 3. Experimental Protocols

### Experiment A: Candidate Attribution Protocol
- **Topology:** $A \to D$ (baseline), $A \to B \to D$ ($L=3$), and $A \to \dots \to D$ ($L=4, 5$).
- **Measurements per run:**
  1. `root_in_cold`: Boolean indicating whether true root is physically present in cold buffer.
  2. `root_raw_sim_rank`: Rank of true root among all records in cold memory sorted by $\cos(e_{\text{cand}}, e_D)$.
  3. `root_in_top_k`: Boolean indicating whether root passed into Top-$K=100$ cold candidate search.
  4. `root_revision_score`: $Score(e_{\text{root}})$.
  5. `root_score_rank`: Rank of true root after full Revision scoring among all scored candidates.
  6. `top1_candidate_id`: ID of the top-scoring candidate.
  7. `top1_candidate_type`: Category of winner (`true_root`, `intermediate_hop`, `distractor`, `background_decoy`).
  8. `margin_to_top1`: $Score(e_{\text{winner}}) - Score(e_{\text{root}})$.

### Experiment B: Hop Attenuation Protocol
- **Chains:** $L \in [2, 3, 4, 5, 6]$.
- For each hop $h \in [0, \dots, L-2]$ (where $h=0$ is immediate predecessor to terminal $D$, up to root):
  1. $\text{CosineSim}(e_h, e_D)$
  2. $\text{StateCompat}(h_h, h_D)$
  3. $\text{TemporalCompat}(t_h, t_D)$
  4. $\text{RevisionScore}(e_h, D)$
  5. Candidate rank in cold memory
  6. Cold retention status and restoration outcome

### Experiment C: Crowding Decomposition Protocol
- Total distractor budget: $N \in [0, 10, 50, 100, 500]$.
- Factorial distractor types:
  - **Type 1 (Sim-Only):** High cosine similarity to $D$ ($0.85$), independent random state, uniform timestamps.
  - **Type 2 (State-Only):** Orthogonal embedding to $D$, state snapshot aligned with terminal state $h_D$.
  - **Type 3 (Temporal-Only):** Random background embedding and state, but timestamps concentrated near trigger ($t \in [T-100, T-1]$).
  - **Type 4 (Random Noise):** Independent random vectors across embedding, state, and timestamps.
  - **Type 5 (Sim + State Dual Decoys):** High similarity to $D$ AND high state compatibility to $h_D$.
- Measure for each distractor type across levels $N$: Root Recall, Precision, False Revision Rate, Top-1 Winner Identity.

---

## 4. Evaluation Standards & Seeds
- Canonical Seeds: `[101, 202, 303]`
- Development Seed: `999`
- Memory Budgets: $K_{\text{hot}} = 250, K_{\text{cold}} = 500$ ($K_{\text{total}} = 750$).
- All experiments strictly frozen at commit `688339b` baseline weights.
- Phase 4 remains **PAUSED**.
