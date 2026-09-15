# Mission 2.9.6: Causal-Conditioned Temporal Restoration Benchmark Report

**Core Question:** Does absolute temporal decay act as a 'causal possibility penalty' or merely a 'search resource signal'?  
**Status:** EMPIRICALLY AUDITED & VERIFIED  
**Canonical Seeds:** [101, 202, 303]  
**Single Variable:** Restoration scoring only (Retention = P2, Algorithm = 688339b frozen)

---

## 1. Restoration Crossover Curve

For each R-policy, at what Δt does recency beat CSM and cause false restoration?

| Δt(A,D) | R0 A-Restored | R1 A-Restored | R2 A-Restored | R3 A-Restored |
|---:|---:|---:|---:|---:|
| 100 | 0% | 0% | 0% | 0% |
| 500 | 0% | 0% | 0% | 0% |
| 1000 | 0% | 0% | 0% | 0% |
| 2000 | 0% | 0% | 0% | 0% |
| 2900 | 33% | 33% | 33% | 33% |

---

## 2. False-Causal Negative Control (F at t=50)

| Δt(A,D) | R0 F-False | R1 F-False | R2 F-False | R3 F-False |
|---:|---:|---:|---:|---:|
| 100 | 0% | 33% | 33% | 0% |
| 500 | 0% | 0% | 0% | 0% |
| 1000 | 0% | 0% | 0% | 0% |
| 2000 | 0% | 0% | 0% | 0% |
| 2900 | 0% | 0% | 0% | 0% |

---

## 3. Score Component Audit (Δt=2900, the hardest case)


### R0_current_decay

| Candidate | sim | state_compat | temporal_compat | total |
|:---|---:|---:|---:|---:|
| A (causal root) | 0.596 | 0.492 | 0.055 | 0.447 |
| R (recency decoy) | 0.000 | 0.000 | 0.000 | 0.000 |

### R1_no_temporal

| Candidate | sim | state_compat | temporal_compat | total |
|:---|---:|---:|---:|---:|
| A (causal root) | 0.596 | 0.492 | 1.000 | 0.636 |
| R (recency decoy) | 0.000 | 0.000 | 0.000 | 0.000 |

### R2_weak_decay

| Candidate | sim | state_compat | temporal_compat | total |
|:---|---:|---:|---:|---:|
| A (causal root) | 0.596 | 0.492 | 0.560 | 0.548 |
| R (recency decoy) | 0.000 | 0.000 | 0.000 | 0.000 |

### R3_csm_gated

| Candidate | sim | state_compat | temporal_compat | total |
|:---|---:|---:|---:|---:|
| A (causal root) | 0.596 | 0.492 | 0.260 | 0.488 |
| R (recency decoy) | 0.000 | 0.000 | 0.000 | 0.000 |

---

## 4. Raw Execution Matrix

| Policy | Δt Config | Seed | A Restored? | R False? | F False? | Score(A) | Score(R) | Score(F) |
|:---|:---|---:|:---:|:---:|:---:|---:|---:|---:|
| `R0_current_decay` | `dt100` | 101 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.000 |
| `R0_current_decay` | `dt100` | 202 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.411 |
| `R0_current_decay` | `dt100` | 303 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.000 |
| `R0_current_decay` | `dt500` | 101 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.000 |
| `R0_current_decay` | `dt500` | 202 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.412 |
| `R0_current_decay` | `dt500` | 303 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.000 |
| `R0_current_decay` | `dt1000` | 101 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.000 |
| `R0_current_decay` | `dt1000` | 202 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.413 |
| `R0_current_decay` | `dt1000` | 303 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.000 |
| `R0_current_decay` | `dt2000` | 101 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.000 |
| `R0_current_decay` | `dt2000` | 202 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.416 |
| `R0_current_decay` | `dt2000` | 303 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.000 |
| `R0_current_decay` | `dt2900` | 101 | ❌ | ✅否 | ✅否 | 0.392 | 0.000 | 0.000 |
| `R0_current_decay` | `dt2900` | 202 | ❌ | ✅否 | ✅否 | 0.397 | 0.000 | 0.418 |
| `R0_current_decay` | `dt2900` | 303 | ✅ | ✅否 | ✅否 | 0.551 | 0.000 | 0.000 |
| `R1_no_temporal` | `dt100` | 101 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.000 |
| `R1_no_temporal` | `dt100` | 202 | ❌ | ✅否 | ⚠️ | 0.000 | 0.000 | 0.600 |
| `R1_no_temporal` | `dt100` | 303 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.000 |
| `R1_no_temporal` | `dt500` | 101 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.000 |
| `R1_no_temporal` | `dt500` | 202 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.601 |
| `R1_no_temporal` | `dt500` | 303 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.000 |
| `R1_no_temporal` | `dt1000` | 101 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.000 |
| `R1_no_temporal` | `dt1000` | 202 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.603 |
| `R1_no_temporal` | `dt1000` | 303 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.000 |
| `R1_no_temporal` | `dt2000` | 101 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.000 |
| `R1_no_temporal` | `dt2000` | 202 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.605 |
| `R1_no_temporal` | `dt2000` | 303 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.000 |
| `R1_no_temporal` | `dt2900` | 101 | ❌ | ✅否 | ✅否 | 0.581 | 0.000 | 0.000 |
| `R1_no_temporal` | `dt2900` | 202 | ❌ | ✅否 | ✅否 | 0.586 | 0.000 | 0.607 |
| `R1_no_temporal` | `dt2900` | 303 | ✅ | ✅否 | ✅否 | 0.740 | 0.000 | 0.000 |
| `R2_weak_decay` | `dt100` | 101 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.000 |
| `R2_weak_decay` | `dt100` | 202 | ❌ | ✅否 | ⚠️ | 0.000 | 0.000 | 0.511 |
| `R2_weak_decay` | `dt100` | 303 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.000 |
| `R2_weak_decay` | `dt500` | 101 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.000 |
| `R2_weak_decay` | `dt500` | 202 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.512 |
| `R2_weak_decay` | `dt500` | 303 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.000 |
| `R2_weak_decay` | `dt1000` | 101 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.000 |
| `R2_weak_decay` | `dt1000` | 202 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.514 |
| `R2_weak_decay` | `dt1000` | 303 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.000 |
| `R2_weak_decay` | `dt2000` | 101 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.000 |
| `R2_weak_decay` | `dt2000` | 202 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.516 |
| `R2_weak_decay` | `dt2000` | 303 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.000 |
| `R2_weak_decay` | `dt2900` | 101 | ❌ | ✅否 | ✅否 | 0.493 | 0.000 | 0.000 |
| `R2_weak_decay` | `dt2900` | 202 | ❌ | ✅否 | ✅否 | 0.498 | 0.000 | 0.518 |
| `R2_weak_decay` | `dt2900` | 303 | ✅ | ✅否 | ✅否 | 0.652 | 0.000 | 0.000 |
| `R3_csm_gated` | `dt100` | 101 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.000 |
| `R3_csm_gated` | `dt100` | 202 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.448 |
| `R3_csm_gated` | `dt100` | 303 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.000 |
| `R3_csm_gated` | `dt500` | 101 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.000 |
| `R3_csm_gated` | `dt500` | 202 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.449 |
| `R3_csm_gated` | `dt500` | 303 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.000 |
| `R3_csm_gated` | `dt1000` | 101 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.000 |
| `R3_csm_gated` | `dt1000` | 202 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.450 |
| `R3_csm_gated` | `dt1000` | 303 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.000 |
| `R3_csm_gated` | `dt2000` | 101 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.000 |
| `R3_csm_gated` | `dt2000` | 202 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.453 |
| `R3_csm_gated` | `dt2000` | 303 | ❌ | ✅否 | ✅否 | 0.000 | 0.000 | 0.000 |
| `R3_csm_gated` | `dt2900` | 101 | ❌ | ✅否 | ✅否 | 0.428 | 0.000 | 0.000 |
| `R3_csm_gated` | `dt2900` | 202 | ❌ | ✅否 | ✅否 | 0.433 | 0.000 | 0.455 |
| `R3_csm_gated` | `dt2900` | 303 | ✅ | ✅否 | ✅否 | 0.602 | 0.000 | 0.000 |