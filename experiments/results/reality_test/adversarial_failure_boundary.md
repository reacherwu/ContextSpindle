# Agent B: Continuum Adversarial Failure Boundary Report
**Audit Goal:** Identify exactly when, why, and how Continuum fails under realistic adversarial conditions.

## 1. Vulnerability 1: Surface Decoy Storm (Symptom-Cause Vocabulary Gap)
- **Query-to-Root Cosine Sim:** 0.269
- **Query-to-Alert Cosine Sim:** 0.295
- **Decoy Advantage:** +0.026
- **The Breakdown:** In real incident queries, queries describe **symptoms** ('504 timeout'), while the root cause describes **actions** ('pool_size changed'). Consequently, all 100 alerts in the storm have higher direct cosine similarity than the root cause.
- **Failure Condition:** If Stage 1 cosine pre-filter size $K_{\text{search}} \le N_{\text{alerts}}$ (e.g. $k=100$ vs 100 alerts), the root cause is **silently truncated** before RevisionEngine can evaluate causal compatibility.

## 2. Vulnerability 2: Causal Exemption Threshold in Low-Overlap Domains
- If `causal_exempt_threshold` is hardcoded at $0.50$, real-text root causes with similarity in $[0.25, 0.45]$ are **not exempted** from exponential temporal decay.
- Across $\Delta t = 2900$, an unexempted event suffers an exponential penalty $\exp(-2.9) = 0.055$, dropping its score from 0.70 down to 0.15.

## 3. Vulnerability 3: Fact Reversal & Invalidation
- **Did Overturned Fact (Step 50) Beat Stale Fact (Step 10)?** ❌ NO
- When facts are updated, recency and state compatibility work together to favor the most recent amendment over the stale initial state.

## 4. Engineering Recommendations for Product Hardening
1. **Adaptive Stage 1 Pre-Filter:** In Cold Memory search, do not limit Stage 1 to a rigid top-100 cosine cutoff when the buffer has 500 slots. Evaluate all 500 cold candidates with vectorized PyTorch batch scoring (WP-R6 proved 500 candidates take only 18.5 μs!).
2. **Dynamic Causal Thresholding:** Use relative ranking (e.g. Top 10% similarity or $z$-score above mean) instead of rigid absolute scalar threshold ($0.50$) to handle real-world vocabulary gaps.
