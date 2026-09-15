# RFC-0004: Memory Revision Generalization, Scaling, & Robustness Protocol (Mission 2.8)

**Status:** APPROVED FOR EXPERIMENTAL EXECUTION  
**Decision Owner:** Architecture Agent & Chief Science Officer  
**Target Phase:** Mission 2.8 (Phase C Extension)  
**Parent RFC:** RFC-0003 (Memory Revision Prototype)  
**Invariant Baseline:** Commit `688339b` 5-Factor Equal Weight `(0.2, 0.2, 0.2, 0.2, 0.2)`

---

## 1. Context & Motivation

Mission 2.7 established the foundational proof-of-concept for retrospective memory revision:
$$E5 (100.0\%) > E4 (0.0\%) \ge E3 (0.0\%) = \text{Baselines} (0.0\%)$$
However, the Project Director and CTO noted that this victory was observed on a single fixed benchmark configuration ($T=3000, \Delta t=2900, K_{\text{hot}}=250, K_{\text{cold}}=500$).

To prove that Temporal Memory Revision is an enduring AI architectural capability rather than a fragile benchmark artifact, Mission 2.8 tests the generalization limits across four challenging axes:
1. Temporal delay scaling
2. Multi-hop causal chain depth
3. Scaled adversarial and correlated distractors
4. Constrained physical memory budgets and capacity ratios

---

## 2. Formal Metric Protocol

To eliminate the methodological loophole where high recall could be bought by unrestricted triggering and false alarms, Mission 2.8 mandates four decoupled metrics:

### 2.1 Restoration Recall (RR)
$$\text{RR} = \frac{\text{Correctly Restored Roots}}{\text{True Antecedent Roots}}$$

### 2.2 Revision Precision (RP)
$$\text{RP} = \frac{\text{True Revisions}}{\text{Total Revisions Triggered}}$$
If zero revisions are triggered and no root existed, $\text{RP} = 1.0$; if a root existed but zero revisions triggered, $\text{RP} = 0.0$.

### 2.3 False Revision Rate (FRR)
$$\text{FRR} = \frac{\text{Incorrect Revisions Restored}}{\text{Trigger Opportunities}}$$

### 2.4 Trigger Rate (TR)
$$\text{TR} = \frac{\text{Actual Revision Invocations}}{\text{Total High-Significance Events}}$$

### 2.5 Revision Efficiency Metric
$$\text{Efficiency} = \frac{\text{Restoration Recall} \times \text{Revision Precision}}{K_{\text{total}} / 1000}$$

---

## 3. Four Scaling Dimensions (Pre-Registered Grids)

### Dimension 1: Temporal Delay Scaling ($\Delta t$)
Measures whether temporal decay $\exp(-\Delta t / \tau)$ maintains sensitivity across vast timescales:
- $\Delta t \in [100, 500, 1000, 3000, 10000, 30000]$
- Fixed $K_{\text{hot}}=250, K_{\text{cold}}=500$.

### Dimension 2: Causal Chain Depth ($L$)
Evaluates state compatibility degradation across intermediate causal intermediate hops:
- 2-hop: $A \to D$
- 3-hop: $A \to B \to D$
- 4-hop: $A \to B \to C \to D$
- 5-hop: $A \to B \to C \to D \to E$
- 6-hop: $A \to B \to C \to D \to E \to F$
Intermediate events receive partial subsystem alignment, testing whether dynamical fingerprints remain coherent.

### Dimension 3: Distractor Scaling ($|D_{\text{dist}}|$)
Stresses Revision Precision under massive candidate pools:
- $|D_{\text{dist}}| \in [0, 10, 50, 100, 500, 1000, 5000]$
Distractors are sampled with moderate similarity ($[0.25, 0.50]$) to trigger events, measuring false recovery resistance.

### Dimension 4: Memory Budget & Ratio Sweeps ($K_{\text{hot}}, K_{\text{cold}} / K_{\text{hot}}$)
Evaluates physical storage bounds:
- $K_{\text{hot}} \in [25, 50, 100, 250, 500, 1000]$
- Ratio $r = K_{\text{cold}} / K_{\text{hot}} \in [0.5, 1.0, 2.0, 3.0]$
Total budget $K_{\text{total}} = K_{\text{hot}} \times (1 + r)$ is strictly enforced.

---

## 4. Revision Ablation Protocol

To confirm factor necessity without overfitting:
- **Factor Ablation:**
  - Full: $w=[0.4, 0.3, 0.2, 0.1]$
  - Sim Only: $w=[1.0, 0, 0, 0]$
  - State Only: $w=[0, 1.0, 0, 0]$
  - Temporal Only: $w=[0, 0, 1.0, 0]$
  - Sim + State: $w=[0.55, 0.45, 0, 0]$
- **Threshold Sensitivity:**
  - $\theta_{\text{trigger}} \in [0.2, 0.35, 0.45, 0.60]$
  - $\theta_{\text{restore}} \in [0.15, 0.25, 0.35, 0.50]$

**Two-Phase Split Protocol:**
1. Hyperparameter and sensitivity exploration performed exclusively on Development Seed `999`.
2. Final evaluation frozen and executed one-shot across Canonical Seeds `[101, 202, 303]`.

---

## 5. Architectural Guardrails

- **Zero Graph/DB Invariant:** No vector databases, Neo4j, GNNs, or Graph Attention.
- **Sparse Event Memory Status:** Remains strictly PAUSED.
