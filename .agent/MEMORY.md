# Project memory

## Current Research Status (Mission 2.9 Completed)

```text
                 CONTINUUM
                     │
                     ▼
             Temporal State
                  ✅ PASS (TASK-001)
                     │
                     ▼
             Adaptive Memory
                  ✅ PASS WITH CONDITIONS (Mission 2.6)
                     │
                     ▼
       Current Scaling Benchmark
                  ✅ EVIDENCE (1K to 100K bounded at K=500)
                     │
                     ▼
       Adversarial Validation
                  ✅ COMPLETED AUDIT (Mission 2.5)
                     │
                     ▼
       Factor Attribution & Robustness
                  ✅ PASS (Mission 2.6 + Phase B Gap-Fill)
                     │
                     ▼
       Memory Revision (Prototype)
                  ✅ PASS (Mission 2.7: E5 > E4 >= E3 = Baselines)
                     │
                     ▼
       Revision Scaling & Generalization
                  ✅ PASS (Mission 2.8: 4 Dimensions + Ablation)
                     │
                     ▼
       Scientific Integrity & Failure Boundaries
                  ✅ PASS (Mission 2.8.1: Operating Envelope & Failure Map)
                     │
                     ▼
       Revision Failure Mechanism Investigation
                  ✅ PASS (Mission 2.9: Exp A, B, C Forensic Dissection)
                     │
                     ▼
       Mechanism Isolation (M1 / M2 / M3)
                  ✅ PASS (Mission 2.9.1: Single-Variable Verified)
                     │
                     ▼
        Minimal Fix Isolation & Scientific Validation
                   ✅ PASS (Mission 2.9.2: H1-H5 Audited)
                      │
                      ▼
        Non-Oracle Online Causal Identification
                   ✅ PASS (Mission 2.9.3: Experimental Completion Signed)
                      │
                      ▼
         Causal-vs-Unique Discrimination
                    ✅ PASS WITH SCIENTIFIC CLARIFICATION (Mission 2.9.4: Causal Anchor vs Unique Anomaly)
                       │
         Mission 2.9 Series: Mechanism Discovery & Failure Boundary
                    📁 CLOSED (Missions 2.9.1 - 2.9.7 Forensic Investigations Complete)
                       │
                       ▼
         Mission 3.0: ACM End-to-End Scientific Validation
                    ❌ FAIL: NOT CERTIFIED (Pre-Registered Failure Criteria Triggered)
                       - Criterion 1 (Causal Recall & Precision): FAILED (Recall +33.3% over B1-B3, but FRR 93.3% > 10% threshold)
                       - Criterion 2 (Memory/Latency Efficiency): PASSED (Bounded K<=750, 92.5% savings vs B4 at T=10K)
                       │
                       ▼
            Sparse Event Memory
                    ⏸️ PAUSED (Frozen until architectural clearance)
```

## Validated Facts (Empirically Proven)

1. **Physical Boundedness:** Across stream lengths from $T=1,000$ to $T=100,000$, Continuum memory remains strictly bounded at $K=500$ slots with flat process RAM (< 65 MB).
2. **Single-Factor Ranking (Clean Stream):** Under clean-stream evaluation distribution, ablation recall is $N(100\%) > C(93.3\%) \gg R(40\%) > U(23.3\%) > S(16.7\%)$. Surprise contributes complementary information, while clean factor attribution was dominated by Novelty and Causal compatibility.
3. **Adversarial Double-Edged Sword ($S+N$ Collapse):** While $S+N$ achieves 100.0% on clean streams, it catastrophically collapses to 0.0% accuracy with 50.0% contamination (hoarding 100/100 outlier traps) under Benchmark C (Novelty Inversion). Continuum Primary (0.2 equal-weight) remains resilient (0.0% contamination).
4. **Epistemic Horizon of Online Scoring Solved by Memory Revision (Mission 2.7):**
   - Online-only scoring ($x_{\le t}$) achieves 0.0% accuracy on delayed causal chains (Benchmark E) because root causes with initially routine importance are evicted under fixed budgets.
   - Retrospective Memory Revision ($K_{\text{hot}}=250, K_{\text{cold}}=500, K_{\text{total}}=750$, Revision Engine with $w=[0.4, 0.3, 0.2, 0.1]$) achieves **100.0% accuracy** across all canonical seeds [101, 202, 303].
   - Strict inequality is verified: **$E5 (100.0\%) > E4 (0.0\%) \ge E3 (0.0\%) = \text{Baselines} (0.0\%)$**.
5. **Negative Control Verification (NC1-NC4):**
   - NC1 (Positive Control, True Causal Chain): 100.0% recall, 0.0 false revisions, 100.0% precision.
   - NC2 (False Causal, accidental similarity): 0.0% recall (refuses to identify accidental similarity as true root).
   - NC3 (Correlated Distractor): Distractor A is suppressed; True Root B is preferred and restored.
   - NC4 (Random Historical Candidates): 0.0% false root recall.
6. **Revision Operating Envelope & Three Failure Boundaries (Mission 2.8.1):**
   - **Three-Tier Horizon Defined:** 1) $\Delta t < K_{\text{hot}}$: Hot memory direct coverage; 2) $K_{\text{hot}} < \Delta t < K_{\text{hot}} + K_{\text{cold}}$: Cold candidate revision active; 3) $\Delta t > K_{\text{total}}$: Cold buffer physical truncation horizon.
   - **Algorithmic Pareto Frontier:** 5 non-dominated points; $K_{\text{hot}}=250, K_{\text{cold}}=500$ ($K_{\text{total}}=750$) is the **best observed operating point** reaching 100% Recall/Precision.
7. **Minimal Fix Isolation Empirical Results (Mission 2.9.2):**
   - **H1 (Cold FIFO Storage Eviction is primary cause under 500 distractors):** **CONFIRMED**. A0 evicts root at $t \approx 2611$ (0% recall), while A1 (protected root) achieves 100% recall.
   - **H2 (Absolute temporal decay suppresses distant causal antecedents):** **CONFIRMED**. Absolute decay suppresses root by $0.189$ points.
   - **H3 (Simple threshold stratified retention resolves cold eviction):** **NOT CONFIRMED**. A2 evicts root at $t \approx 400$ because background cluster transitions saturate the high-value pool.
   - **H4 (Hop-conditioned decay suppresses irrelevant background better than No-decay):** **CONFIRMED**. Background noise score is $0.0816$ under hop decay vs $0.2546$ under No-decay.
   - **H5 (Intermediate admission alone solves multi-hop chain failure):** **NOT CONFIRMED**. C1 restores intermediate $B$ ($66.7\%$), but Chain Recall remains $0.0\%$ due to root storage eviction and single-slot policy.
8. **Non-Oracle Online Causal Identification (Mission 2.9.3 — Experimental Completion Signed):**
   - **H1 (Online Redundancy Eviction avoids saturation & preserves root without oracle):** **CONFIRMED**. Under 500 distractors across all canonical seeds [101, 202, 303], strictly online pairwise representational redundancy control preserved the true root in Cold Memory (100% retention, bounded capacity $\le 500$).
   - **H2 (Root is identifiable from online observable representations):** **CONFIRMED**. In 100% of seeds, the root cause ranked **Rank 1 in Top-100 cosine similarity search** without any oracle or future query knowledge.
   - **H3 (Single-slot terminal revision reliably distinguishes root from early distractors):** **NOT CONFIRMED**. While the root is top in semantic similarity, exponential temporal decay and state drift slightly favored early distractors ($t \approx 252$) over the distant root ($t=100$) for the single winner slot.
9. **Causal-vs-Unique Discrimination & Mechanism Demarcation (Mission 2.9.4 Empirical Verdict):**
   - **Static Geometric Novelty is Anomaly Memory, NOT Causal Memory:** Under `M1` (Uniqueness-Biased), retention of the subtle causal anchor ($A_{\text{subtle}}$, $90\%$ background cluster $+ 10\%$ subsystem) collapses to **33.3%** because high similarity to normal background ($> 0.90$) causes it to be discarded as redundant, even while uninformative anomaly traps ($U$) and salient outliers ($A_{\text{salient}}$) are preserved (100%).
   - **Online Redundancy-FIFO (`M2`) Mitigates but Risks Threshold Sensitivity:** Retains 66.7% subtle anchors and 100% salient anchors, but loses subtle anchors when background cluster variations breach the static redundancy threshold ($0.85$).
   - **Online Dynamical Trajectory Coherence (`M3`) Solves Discrimination:** By factoring internal temporal hidden-state trajectory norm ($\Delta h$) and dynamic state transition footprint into online eviction, `M3` achieves **100.0% Subtle Causal Anchor Retention** and **100.0% Salient Causal Anchor Retention** across all canonical seeds [101, 202, 303], with high Causal-to-Anomaly Discrimination Ratio ($\text{CDR} = 12.50$), 100% causal restoration, and 0.0% false restoration of anomaly traps or distractors.
10. **Separation of Persistent State Change from Causal Explanatory Value (Mission 2.9.5 Empirical Verdict):**
    - **Persistent State Change $\neq$ Causal Value:** An online agent observing $t < T_{\text{terminal}}$ cannot and mathematically should not attempt to single out *which* subsystem's persistent regime shift is the sole future cause of an unknown failure $D$. Persistent non-causal regime shifts ($P_{\text{regime}, 1..10}$) exhibit equal or larger $\|\Delta h\|$ than subtle causal anchors ($A_{\text{causal}}$).
    - **Single-Stage State Magnitude Failure (P0/P1):** Naively prioritizing state magnitude or raw persistent drift evicts the causal anchor on Seed 202 (causal retention drops to 66.7%).
    - **Two-Stage Decoupling Theorem Empirically Validated (P2/P3):**
      - *Stage 1 (Online Cold Retention):* Preserves persistent dynamical shifts across orthogonal subspaces via subspace diversity/redundancy suppression (P2), retaining $A_{\text{causal}}$ in **100% of canonical seeds** alongside orthogonal regime shifts.
      - *Stage 2 (Retrospective Revision):* Conditioned on terminal symptom $D$, the Revision Engine cleanly separates $A_{\text{causal}}$ from all non-causal regime shifts, achieving a Causal Separation Margin of $\text{CSM} = \mathbf{+0.333}$ and **0.0% false restoration of non-causal regime shifts** across all seeds.
11. **Causal-Conditioned Temporal Restoration — Deeper Failure Exposed (Mission 2.9.6 Empirical Verdict):**
    - **Original Hypothesis was WRONG:** Mission 2.9.5 attributed Seed 202's restoration failure to absolute temporal decay (Recency Bias). Mission 2.9.6 tested R0-R3 across 5 Δt configs × 3 seeds (60 experiments), and the results show **the primary failure mode is NOT temporal decay — it is cold storage eviction**.
    - **Critical Finding — Score(A) = 0.0 for Δt $\le$ 2000:** For $\Delta t \in \{100, 500, 1000, 2000\}$, the causal root $A$ scores **exactly 0.0** across ALL policies (R0, R1, R2, R3) and ALL seeds. This means $A$ is not even present in cold memory when terminal evidence $D$ arrives — it was physically evicted before the revision could reach it.
    - **Only Δt=2900 ($t_A=100$) produces nonzero A scores:** At the extreme where $A$ is injected very early ($t=100$), P2 retention manages to preserve it in 2/3 seeds (Score(A) $\approx 0.39\text{-}0.60$). But even there, only Seed 303 restores $A$ (33% restoration rate, identical across R0-R3).
    - **R1 Negative Control CONFIRMED:** R1 (no temporal penalty) produces false restoration of $F$ (false-causal ancient) in Seed 202 at dt100 ($F$ score $=0.600$), confirming that some temporal structure is indeed necessary. R2 (τ=5000) also triggers $F$ false restoration. R3 (CSM-gated) successfully suppresses $F$.
    - **Recency Decoy $R$ is a non-issue:** $R$ at $t=2929$ consistently scores 0.0 — it stays in hot memory and never enters cold, so it was never the actual competitor. The Mission 2.9.5 "Seed 202 recency decoy" was a different event (a distractor, not the constructed $R$).
12. **Capacity vs. Policy Isolation (Mission 2.9.7 Empirical Verdict):**
    - **Verdict: Policy Failure, NOT Capacity Bound:** Under strictly fixed $K_{\text{total}} = 750$ slots ($T=3000$), Continuum's memory retention failure is 100% caused by two-tier admission routing, not physical capacity.
    - **Hot-Gate Discard Bug Identified:** In the legacy architecture (C0), Cold Memory was treated merely as an eviction overflow for Hot Memory. When Hot Memory was full ($t > 250$), incoming subtle causal anchors ($t_A=2000$) were rejected at the Hot gate (`DISCARD`) and dropped into the void—never reaching Cold Memory (0% retention).
    - **750 Slots Physical Sufficiency Proven:** Introducing Cold Memory Direct Bypass (C1) or Unified Dynamic Memory (C3) within the exact same 750 slots achieved **100.0% retention of both Early ($t=100$) and Mid ($t=2000$) anchors simultaneously** across all canonical seeds [101, 202, 303].
13. **ACM End-to-End Scientific Validation (Mission 3.0 Empirical Verdict):**
    - **Official Verdict: NOT CERTIFIED (Pre-Registered Criteria Triggered):** Under strictly fair benchmark conditions against competitive baselines (B1 Recurrent Only, B2 Fixed LRU, B3 Sliding Window Transformer, B4 Full Unbounded Store), ACM achieved an undeniable efficiency advantage (+92.5% slot savings vs B4 at $T=10,000$ with flat $O(1)$ memory), and demonstrated a +33.3% causal recall advantage over B1, B2, and B3.
    - **Failure Reason:** Under the pre-registered failure criteria, ACM was required to achieve False Restoration Rate (FRR) $< 10\%$. In practice, when evaluated against terminal symptom $D$, ACM's Top-5 retrieval retrieved non-causal distractors alongside causal anchors (FRR = 93.3%), and only successfully retrieved the true causal root in 1 out of 3 seeds (Seed 303).
    - **Scientific Implication:** In accordance with the immutable pre-registration rule, ACM is **NOT CERTIFIED as a validated new architecture**. While its memory footprint and long-range reach are physically sound, its retrospective selectivity under dense distractors remains insufficient to guarantee high-precision root cause isolation without further precision-oriented revision mechanics.

## Architectural Invariants (FROZEN)

1. **Core Scoring Invariant:** 5-factor scoring in `adaptive_memory.py` is frozen at commit `688339b` with equal weights `(0.2, 0.2, 0.2, 0.2, 0.2)`.
2. **RevisionScore Weights Invariant:** $w_1 = 0.4, w_2 = 0.3, w_3 = 0.2, w_4 = 0.1, \tau = 1000$.
3. **No Bloat Principle:** No Vector DBs, full Causal Graphs, GNNs, or Phase Attention permitted. Sparse Event Memory remains strictly PAUSED.

## Next Step

Mission 3.0 Concluded with Pre-Registered Verdict: FAILED_NOT_CERTIFIED. The empirical boundary is firmly mapped: ACM's memory efficiency is validated, but causal restoration precision under dense distractors failed the pre-registered certification bar. Await Director's architectural guidance.

