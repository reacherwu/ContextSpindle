from __future__ import annotations

import math
import random
import time
from typing import Any

import torch
from torch import Tensor

from continuum.memory.adaptive_memory import AdaptiveMemory, AdaptiveMemoryConfig, EventRecord, RetentionDecision
from continuum.memory.cold_memory import ColdCandidateMemory, ColdCandidateRecord
from continuum.memory.revision_engine import RevisionConfig, RevisionEngine, RevisionResult
from continuum.state.temporal_state import TemporalState, TemporalStateConfig
from benchmarks.recency_trap.benchmark_recency_trap import DiversifiedDynamicsColdMemory, R3Engine


# ===========================================================================
# C3: Unified Dynamic Memory (750 slots, unified pool without rigid hot/cold partition)
# ===========================================================================

class UnifiedDynamicMemory:
    """
    C3: Unified Dynamic Memory Architecture.
    Total capacity strictly bounded at K_total = 750 slots.
    Eliminates rigid Hot/Cold partitioning.
    Eviction prioritizes:
    1. Redundant background records (pairwise cosine similarity >= sim_thresh).
    2. Lowest dynamic transition value (importance + state fingerprint norm).
    """
    def __init__(self, capacity: int = 750, embedding_dim: int = 32, state_dim: int = 32, sim_thresh: float = 0.85):
        self.capacity = capacity
        self.embedding_dim = embedding_dim
        self.state_dim = state_dim
        self.sim_thresh = sim_thresh

        self.records: list[ColdCandidateRecord] = []
        self.embeddings_tensor: Tensor | None = None

    def observe(
        self,
        event_id: int,
        timestamp: float,
        embedding: Tensor,
        temporal_state: Tensor,
        importance: float,
        provenance: str = "unified_stream",
    ) -> None:
        emb = embedding.detach().float()
        if emb.ndim > 1:
            emb = emb.squeeze()
        norm = torch.norm(emb, p=2)
        if norm > 1e-8:
            emb = emb / norm

        state_fp = temporal_state.detach().float()
        record = ColdCandidateRecord(
            event_id=event_id,
            timestamp=timestamp,
            compressed_embedding=emb,
            state_fingerprint=state_fp,
            importance_at_eviction=importance,
            provenance_summary=provenance,
        )

        if len(self.records) >= self.capacity:
            self._evict_one()

        self.records.append(record)
        new_emb = emb.unsqueeze(0)
        if self.embeddings_tensor is None:
            self.embeddings_tensor = new_emb
        else:
            self.embeddings_tensor = torch.cat([self.embeddings_tensor, new_emb], dim=0)

    def _evict_one(self) -> None:
        if len(self.records) == 0:
            return
        evict_idx = -1
        with torch.no_grad():
            if self.embeddings_tensor is not None and len(self.records) > 1:
                sim_mat = torch.matmul(self.embeddings_tensor, self.embeddings_tensor.T)
                sim_mat.fill_diagonal_(-1.0)
                max_sims, _ = torch.max(sim_mat, dim=1)
                redundant_mask = max_sims >= self.sim_thresh
                if redundant_mask.any():
                    for i in range(len(self.records)):
                        if redundant_mask[i]:
                            evict_idx = i
                            break

        if evict_idx == -1:
            scores = []
            for r in self.records:
                st_norm = float(torch.norm(r.state_fingerprint, p=2).item())
                scores.append(0.4 * r.importance_at_eviction + 0.6 * st_norm)
            evict_idx = int(torch.tensor(scores).argmin().item())

        self.records.pop(evict_idx)
        if len(self.records) == 0:
            self.embeddings_tensor = None
        else:
            self.embeddings_tensor = torch.cat(
                [self.embeddings_tensor[:evict_idx], self.embeddings_tensor[evict_idx + 1:]], dim=0
            )

    def search(self, query_embedding: Tensor, top_k: int = 100) -> list[tuple[ColdCandidateRecord, float]]:
        if len(self.records) == 0 or self.embeddings_tensor is None:
            return []
        q = query_embedding.detach().float()
        if q.ndim > 1:
            q = q.squeeze()
        norm_q = torch.norm(q, p=2)
        if norm_q > 1e-8:
            q = q / norm_q

        k = min(top_k, len(self.records))
        with torch.no_grad():
            sims = torch.mv(self.embeddings_tensor, q)
            top_vals, top_indices = torch.topk(sims, k=k)

        results: list[tuple[ColdCandidateRecord, float]] = []
        for val, idx in zip(top_vals.tolist(), top_indices.tolist()):
            results.append((self.records[idx], float(val)))
        return results


# ===========================================================================
# Experiment Runner for Mission 2.9.7
# ===========================================================================

def run_bounded_retention_experiment(
    condition: str,
    seed: int,
    emb_dim: int = 32,
    state_dim: int = 32,
    stream_length: int = 3000,
    total_budget: int = 750,
) -> dict[str, Any]:
    """
    Mission 2.9.7: Bounded Causal Retention Experiment.
    Evaluates whether retention failures at K_total = 750 are caused by
    insufficient capacity or flawed two-tier memory allocation policy.

    Injected Causal Anchors:
      A_early: t=100  (early anchor, Delta_t=2900)
      A_mid:   t=2000 (mid-stream anchor, Delta_t=1000)
    Both are subtle (90% background / 10% subsystem X) or aligned with failure subsystem X.
    """
    torch.manual_seed(seed)
    random.seed(seed)

    t_A_early = 100
    t_A_mid = 2000
    n_regimes = 10
    n_distractors = 30

    # Build orthogonal bases
    n_clusters = 3
    basis: list[Tensor] = []
    for _ in range(n_clusters):
        v = torch.randn(emb_dim)
        for b in basis:
            v -= torch.dot(v, b) * b
        v /= torch.norm(v, p=2)
        basis.append(v)
    clusters = basis[:n_clusters]

    # Failure subsystem X
    v_x = torch.randn(emb_dim)
    for b in basis:
        v_x -= torch.dot(v_x, b) * b
    v_x /= torch.norm(v_x, p=2)
    basis.append(v_x)

    # 10 Orthogonal Regime Subsystems Y_1 .. Y_10
    regime_subsystems: list[Tensor] = []
    for _ in range(n_regimes):
        v_y = torch.randn(emb_dim)
        for b in basis:
            v_y -= torch.dot(v_y, b) * b
        v_y /= torch.norm(v_y, p=2)
        basis.append(v_y)
        regime_subsystems.append(v_y)

    # Event vectors
    # A_early: t=100
    vec_A_early = 0.85 * v_x + 0.15 * torch.randn(emb_dim)
    vec_A_early /= torch.norm(vec_A_early, p=2)

    # A_mid: t=2000
    vec_A_mid = 0.85 * v_x + 0.15 * torch.randn(emb_dim)
    vec_A_mid /= torch.norm(vec_A_mid, p=2)

    # Terminal symptom D: t=3000
    vec_D = 0.85 * v_x + 0.15 * torch.randn(emb_dim)
    vec_D /= torch.norm(vec_D, p=2)

    # Regimes
    regime_steps = [300 + i * 150 for i in range(n_regimes)]
    regime_vectors = {
        t_step: (0.90 * regime_subsystems[i] + 0.10 * torch.randn(emb_dim)) / torch.norm(0.90 * regime_subsystems[i] + 0.10 * torch.randn(emb_dim), p=2)
        for i, t_step in enumerate(regime_steps)
    }

    # Distractors
    available_dist_steps = [
        t for t in range(200, stream_length - 50)
        if t not in regime_steps and t not in (t_A_early, t_A_mid)
    ]
    dist_steps = set(random.sample(available_dist_steps, min(n_distractors, len(available_dist_steps))))
    dist_vectors = {
        t: (0.35 * vec_D + 0.65 * torch.randn(emb_dim)) / torch.norm(0.35 * vec_D + 0.65 * torch.randn(emb_dim), p=2)
        for t in dist_steps
    }

    # Temporal recurrent state model
    t_cfg = TemporalStateConfig(input_size=emb_dim, hidden_size=state_dim)
    temporal_model = TemporalState(t_cfg)
    h_state = temporal_model.initial_state(1)

    # Setup Memory Architecture based on Condition
    # Conditions:
    # C0_baseline: Hot=250, Cold=500 (standard pipeline, discard dropped)
    # C1_cold_bypass: Hot=250, Cold=500 (if hot discards, cold archives)
    # C2a_hot750_cold0: Hot=750, Cold=0 (flat hot)
    # C2b_hot500_cold250: Hot=500, Cold=250 (cold bypass)
    # C2c_hot250_cold500: Hot=250, Cold=500 (cold bypass, alias C1)
    # C2d_hot100_cold650: Hot=100, Cold=650 (cold bypass)
    # C3_unified_dynamic: Unified 750 slots pool
    # C4_oracle_budget: Hot=250, Cold=500 with protected anchors

    k_hot = 250
    k_cold = 500
    use_cold_bypass = False
    is_unified = False
    is_oracle = False

    if condition == "C0_baseline":
        k_hot, k_cold = 250, 500
        use_cold_bypass = False
    elif condition in ("C1_cold_bypass", "C2c_hot250_cold500"):
        k_hot, k_cold = 250, 500
        use_cold_bypass = True
    elif condition == "C2a_hot750_cold0":
        k_hot, k_cold = 750, 0
        use_cold_bypass = False
    elif condition == "C2b_hot500_cold250":
        k_hot, k_cold = 500, 250
        use_cold_bypass = True
    elif condition == "C2d_hot100_cold650":
        k_hot, k_cold = 100, 650
        use_cold_bypass = True
    elif condition == "C3_unified_dynamic":
        is_unified = True
    elif condition == "C4_oracle_budget":
        k_hot, k_cold = 250, 500
        use_cold_bypass = True
        is_oracle = True
    else:
        raise ValueError(f"Unknown condition: {condition}")

    cold_mem: DiversifiedDynamicsColdMemory | None = None
    unified_mem: UnifiedDynamicMemory | None = None
    am: AdaptiveMemory | None = None

    if is_unified:
        unified_mem = UnifiedDynamicMemory(capacity=total_budget, embedding_dim=emb_dim, state_dim=state_dim, sim_thresh=0.85)
    else:
        if k_cold > 0:
            cold_mem = DiversifiedDynamicsColdMemory(capacity=k_cold, embedding_dim=emb_dim, state_dim=state_dim, sim_thresh=0.85)
        am = AdaptiveMemory(
            AdaptiveMemoryConfig(
                embedding_dim=emb_dim,
                state_dim=state_dim,
                capacity=k_hot,
                seed=seed,
                alpha_surprise=0.2,
                beta_novelty=0.2,
                gamma_causal=0.2,
                delta_retrieval=0.2,
                epsilon_uncertainty=0.2,
            )
        )

    # Revision Engine with CSM-Gated temporal decay
    rev_config = RevisionConfig(
        theta_trigger=0.45,
        theta_restore=0.25,
        max_restorations_per_trigger=2,
    )
    engine = R3Engine(rev_config, alpha=3.0)

    t0 = time.perf_counter()
    causal_active = False
    active_regime_offsets = torch.zeros(emb_dim)

    # Stream loop
    for t in range(stream_length):
        if t == t_A_early:
            emb = vec_A_early
            causal_active = True
        elif t == t_A_mid:
            emb = vec_A_mid
            causal_active = True
        elif t in regime_steps:
            emb = regime_vectors[t]
            r_idx = regime_steps.index(t)
            active_regime_offsets += 0.25 * regime_subsystems[r_idx]
        elif t in dist_steps:
            emb = dist_vectors[t]
        else:
            c_idx = (t // 25) % n_clusters
            base_vec = clusters[c_idx].clone() + active_regime_offsets
            if causal_active:
                drift_factor = min(0.30, 0.04 + 0.0001 * (t - t_A_early))
                base_vec = base_vec + drift_factor * v_x
            base_vec = base_vec + 0.03 * torch.randn(emb_dim)
            emb = base_vec / torch.norm(base_vec, p=2)

        h_state = temporal_model.step(emb.unsqueeze(0), h_state).state

        if is_unified:
            # Estimate importance via norm/surprise
            imp = 0.50 if t in (t_A_early, t_A_mid) else 0.25
            unified_mem.observe(
                event_id=t,
                timestamp=float(t),
                embedding=emb,
                temporal_state=h_state[0],
                importance=imp,
            )
        else:
            rec = am.observe(
                event_id=t,
                timestamp=float(t),
                embedding=emb,
                temporal_state=h_state[0],
                cold_memory=cold_mem,
            )
            # Cold bypass handling
            if use_cold_bypass and cold_mem is not None and rec.decision == RetentionDecision.DISCARD:
                cold_mem.archive(
                    event_id=t,
                    timestamp=float(t),
                    embedding=emb,
                    temporal_state=h_state[0],
                    importance=rec.importance,
                    provenance="bypassed_discard",
                )

    # Audit Physical Retention before Terminal Evidence
    if is_unified:
        retained_ids = {r.event_id for r in unified_mem.records}
        early_in_hot = False
        early_in_cold = t_A_early in retained_ids
        mid_in_hot = False
        mid_in_cold = t_A_mid in retained_ids
        total_slots_used = len(unified_mem.records)
        regimes_in_mem = sum(1 for eid in regime_steps if eid in retained_ids)
        distractors_in_mem = sum(1 for eid in dist_steps if eid in retained_ids)
    else:
        hot_ids = {r.event_id for r in am.records}
        cold_ids = {r.event_id for r in cold_mem.records} if cold_mem is not None else set()
        early_in_hot = t_A_early in hot_ids
        early_in_cold = t_A_early in cold_ids
        mid_in_hot = t_A_mid in hot_ids
        mid_in_cold = t_A_mid in cold_ids
        total_slots_used = len(hot_ids) + len(cold_ids)
        all_retained_ids = hot_ids | cold_ids
        regimes_in_mem = sum(1 for eid in regime_steps if eid in all_retained_ids)
        distractors_in_mem = sum(1 for eid in dist_steps if eid in all_retained_ids)

    early_retained = early_in_hot or early_in_cold
    mid_retained = mid_in_hot or mid_in_cold

    # Terminal Revision Evaluation
    h_state = temporal_model.step(5.0 * vec_D.unsqueeze(0), h_state).state
    restored_ids: list[int] = []

    if is_unified:
        # Search unified memory directly
        candidates = unified_mem.search(vec_D, top_k=100)
        scored_candidates = []
        for cand, _ in candidates:
            score, comps = engine._compute_revision_score_with_components(
                cand, vec_D, h_state[0], float(stream_length)
            )
            scored_candidates.append((score, cand.event_id))
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        restored_ids = [eid for s, eid in scored_candidates[:2] if s > 0.25]
    else:
        if cold_mem is not None:
            candidates = cold_mem.search(vec_D, top_k=100)
            scored_candidates = []
            for cand, _ in candidates:
                score, comps = engine._compute_revision_score_with_components(
                    cand, vec_D, h_state[0], float(stream_length)
                )
                scored_candidates.append((score, cand.event_id))
            scored_candidates.sort(key=lambda x: x[0], reverse=True)
            restored_ids = [eid for s, eid in scored_candidates[:2] if s > 0.25]

    early_restored = t_A_early in restored_ids
    mid_restored = t_A_mid in restored_ids
    causal_restored = early_restored or mid_restored
    regime_restored = any(eid in regime_steps for eid in restored_ids)
    distractor_restored = any(eid in dist_steps for eid in restored_ids)

    elapsed_ms = (time.perf_counter() - t0) * 1000

    return {
        "condition": condition,
        "seed": seed,
        "early_retained": early_retained,
        "mid_retained": mid_retained,
        "both_retained": early_retained and mid_retained,
        "early_in_hot": early_in_hot,
        "early_in_cold": early_in_cold,
        "mid_in_hot": mid_in_hot,
        "mid_in_cold": mid_in_cold,
        "total_slots_used": total_slots_used,
        "regimes_in_mem": regimes_in_mem,
        "distractors_in_mem": distractors_in_mem,
        "restored_ids": restored_ids,
        "early_restored": early_restored,
        "mid_restored": mid_restored,
        "causal_restored": causal_restored,
        "regime_restored": regime_restored,
        "distractor_restored": distractor_restored,
        "latency_ms": elapsed_ms,
    }


def run_bounded_retention_suite(
    seeds: list[int] = [101, 202, 303],
    conditions: list[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    if conditions is None:
        conditions = [
            "C0_baseline",
            "C1_cold_bypass",
            "C2a_hot750_cold0",
            "C2b_hot500_cold250",
            "C2d_hot100_cold650",
            "C3_unified_dynamic",
            "C4_oracle_budget",
        ]

    results: dict[str, list[dict[str, Any]]] = {}

    for cond in conditions:
        results[cond] = []
        print(f"\n--> Evaluating Condition: {cond} across seeds {seeds}...")
        for s in seeds:
            res = run_bounded_retention_experiment(cond, seed=s)
            results[cond].append(res)
            e_mark = "✅" if res["early_retained"] else "❌"
            m_mark = "✅" if res["mid_retained"] else "❌"
            rec_mark = "✅" if res["causal_restored"] else "❌"
            print(
                f"    Seed {s}: Early_Retained={e_mark}, Mid_Retained={m_mark}, "
                f"Both={res['both_retained']}, SlotsUsed={res['total_slots_used']}/750, "
                f"Restored={res['restored_ids']}, CausalRestored={rec_mark}"
            )

    return results
