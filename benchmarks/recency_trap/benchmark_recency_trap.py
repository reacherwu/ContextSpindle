from __future__ import annotations

import math
import random
import time
from typing import Any

import torch
from torch import Tensor

from continuum.memory.adaptive_memory import AdaptiveMemory, AdaptiveMemoryConfig
from continuum.memory.cold_memory import ColdCandidateMemory, ColdCandidateRecord
from continuum.memory.revision_engine import RevisionConfig, RevisionEngine, RevisionResult
from continuum.state.temporal_state import TemporalState, TemporalStateConfig

# ===========================================================================
# Mission 2.9.5 retention policy (reused as fixed online stage)
# ===========================================================================

class DiversifiedDynamicsColdMemory(ColdCandidateMemory):
    """P2 from Mission 2.9.5: Diversified Dynamical Attractor Cold Memory."""
    def __init__(self, capacity: int, embedding_dim: int, state_dim: int, sim_thresh: float = 0.85):
        super().__init__(capacity=capacity, embedding_dim=embedding_dim, state_dim=state_dim)
        self.sim_thresh = sim_thresh

    def _evict_oldest(self) -> None:
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


# ===========================================================================
# Restoration scoring variants (benchmark-local — DOES NOT modify frozen core)
# ===========================================================================

class R0Engine(RevisionEngine):
    """R0: Current absolute decay (τ=1000). Identical to frozen baseline."""
    pass


class R1Engine(RevisionEngine):
    """R1: No temporal penalty. temporal_compat fixed to 1.0."""
    def _compute_revision_score_with_components(
        self, candidate, trigger_embedding, trigger_state, trigger_timestamp
    ):
        score, components = super()._compute_revision_score_with_components(
            candidate, trigger_embedding, trigger_state, trigger_timestamp
        )
        old_temporal = components["temporal_compat"]
        components["temporal_compat"] = 1.0
        score = score - self.config.w_temporal_compat * old_temporal + self.config.w_temporal_compat * 1.0
        return score, components


class R2Engine(RevisionEngine):
    """R2: Weak temporal penalty (τ=5000)."""
    def _compute_revision_score_with_components(
        self, candidate, trigger_embedding, trigger_state, trigger_timestamp
    ):
        score, components = super()._compute_revision_score_with_components(
            candidate, trigger_embedding, trigger_state, trigger_timestamp
        )
        old_temporal = components["temporal_compat"]
        delta_t = abs(trigger_timestamp - candidate.timestamp)
        new_temporal = math.exp(-delta_t / 5000.0)
        components["temporal_compat"] = new_temporal
        score = score - self.config.w_temporal_compat * old_temporal + self.config.w_temporal_compat * new_temporal
        return score, components


class R3Engine(RevisionEngine):
    """
    R3: CSM-Gated temporal penalty.
    High causal-compatibility candidates get a longer effective τ.
    effective_tau = τ_base * (1 + α * csm_candidate)
    where csm_candidate = w_sim * sim + w_state_compat * state_compat
    """
    def __init__(self, config: RevisionConfig, alpha: float = 3.0):
        super().__init__(config)
        self.alpha = alpha

    def _compute_revision_score_with_components(
        self, candidate, trigger_embedding, trigger_state, trigger_timestamp
    ):
        score, components = super()._compute_revision_score_with_components(
            candidate, trigger_embedding, trigger_state, trigger_timestamp
        )
        old_temporal = components["temporal_compat"]
        csm_candidate = self.config.w_sim * components["sim"] + self.config.w_state_compat * components["state_compat"]
        effective_tau = self.config.temporal_decay_tau * (1.0 + self.alpha * csm_candidate)
        delta_t = abs(trigger_timestamp - candidate.timestamp)
        new_temporal = math.exp(-delta_t / effective_tau)
        components["temporal_compat"] = new_temporal
        score = score - self.config.w_temporal_compat * old_temporal + self.config.w_temporal_compat * new_temporal
        return score, components


ENGINE_REGISTRY: dict[str, type] = {
    "R0_current_decay": R0Engine,
    "R1_no_temporal": R1Engine,
    "R2_weak_decay": R2Engine,
    "R3_csm_gated": R3Engine,
}


# ===========================================================================
# Recency Trap Experiment
# ===========================================================================

def run_recency_trap_experiment(
    restoration_policy: str,
    delta_t_config: str,
    seed: int,
    emb_dim: int = 32,
    state_dim: int = 32,
    stream_length: int = 3000,
    n_distractors: int = 30,
) -> dict[str, Any]:
    """
    Mission 2.9.6 Recency Trap Experiment.

    Fixed Online Retention = P2 (DiversifiedDynamicsColdMemory).
    Variable: Restoration scoring (R0, R1, R2, R3).

    Events:
      A: True causal root at t_A (varies by delta_t_config)
      R: Recency decoy at t=2929 (high sim to D, different subsystem)
      F: False-causal ancient at t=50 (high sim to D, orthogonal state)
      D: Terminal symptom at t=stream_length
    """
    torch.manual_seed(seed)
    random.seed(seed)

    # Parse delta_t_config to determine t_A
    dt_map = {
        "dt100": stream_length - 100,    # t_A = 2900
        "dt500": stream_length - 500,    # t_A = 2500
        "dt1000": stream_length - 1000,  # t_A = 2000
        "dt2000": stream_length - 2000,  # t_A = 1000
        "dt2900": stream_length - 2900,  # t_A = 100
    }
    t_A = dt_map.get(delta_t_config)
    if t_A is None:
        raise ValueError(f"Unknown delta_t_config: {delta_t_config}")

    t_R = stream_length - 71  # 2929
    t_F = 50

    # Build orthogonal basis
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

    # Decoy subsystem Y (orthogonal to X and clusters)
    v_y = torch.randn(emb_dim)
    for b in basis:
        v_y -= torch.dot(v_y, b) * b
    v_y /= torch.norm(v_y, p=2)
    basis.append(v_y)

    # --- Event vectors ---
    # A: causal root (aligned with X)
    vec_A = 0.85 * v_x + 0.15 * torch.randn(emb_dim)
    vec_A /= torch.norm(vec_A, p=2)

    # D: terminal symptom (aligned with X)
    vec_D = 0.85 * v_x + 0.15 * torch.randn(emb_dim)
    vec_D /= torch.norm(vec_D, p=2)

    # R: recency decoy (moderate sim to D via X component, but significant Y component)
    vec_R = 0.50 * v_x + 0.45 * v_y + 0.05 * torch.randn(emb_dim)
    vec_R /= torch.norm(vec_R, p=2)

    # F: false-causal ancient (high sim to D via X component, but orthogonal state dynamics)
    vec_F = 0.75 * v_x + 0.25 * torch.randn(emb_dim)
    vec_F /= torch.norm(vec_F, p=2)

    # Distractors: weak alignment with D
    available_dist_steps = [
        t for t in range(200, stream_length - 100)
        if t not in (t_A, t_R, t_F)
    ]
    dist_steps = set(random.sample(available_dist_steps, min(n_distractors, len(available_dist_steps))))
    dist_vectors: dict[int, Tensor] = {}
    for t in dist_steps:
        v = 0.30 * vec_D + 0.70 * torch.randn(emb_dim)
        dist_vectors[t] = v / torch.norm(v, p=2)

    # Initialize components
    t_cfg = TemporalStateConfig(input_size=emb_dim, hidden_size=state_dim)
    temporal_model = TemporalState(t_cfg)
    h_state = temporal_model.initial_state(1)

    k_hot = 250
    k_cold = 500

    cold = DiversifiedDynamicsColdMemory(capacity=k_cold, embedding_dim=emb_dim, state_dim=state_dim, sim_thresh=0.85)

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

    # Build engine based on restoration_policy
    base_config = RevisionConfig(
        theta_trigger=0.45,
        theta_restore=0.25,
        max_restorations_per_trigger=1,
    )
    engine_cls = ENGINE_REGISTRY.get(restoration_policy)
    if engine_cls is None:
        raise ValueError(f"Unknown restoration_policy: {restoration_policy}")
    if restoration_policy == "R3_csm_gated":
        engine = engine_cls(base_config, alpha=3.0)
    else:
        engine = engine_cls(base_config)

    t0 = time.perf_counter()

    # Track whether causal drift is active
    causal_active = False

    for t in range(stream_length):
        if t == t_A:
            emb = vec_A
            causal_active = True
        elif t == t_R:
            emb = vec_R
        elif t == t_F:
            emb = vec_F
        elif t in dist_steps:
            emb = dist_vectors[t]
        else:
            c_idx = (t // 25) % n_clusters
            base_vec = clusters[c_idx].clone()
            if causal_active:
                drift_factor = min(0.25, 0.03 + 0.00008 * (t - t_A))
                base_vec = base_vec + drift_factor * v_x
            base_vec = base_vec + 0.03 * torch.randn(emb_dim)
            emb = base_vec / torch.norm(base_vec, p=2)

        h_state = temporal_model.step(emb.unsqueeze(0), h_state).state
        am.observe(
            event_id=t,
            timestamp=float(t),
            embedding=emb,
            temporal_state=h_state[0],
            cold_memory=cold,
        )

    # --- Pre-revision audit ---
    a_in_cold = any(r.event_id == t_A for r in cold.records)
    a_in_hot = any(r.event_id == t_A for r in am.records)
    r_in_cold = any(r.event_id == t_R for r in cold.records)
    r_in_hot = any(r.event_id == t_R for r in am.records)
    f_in_cold = any(r.event_id == t_F for r in cold.records)
    f_in_hot = any(r.event_id == t_F for r in am.records)

    # --- Terminal evidence trigger ---
    h_state = temporal_model.step(5.0 * vec_D.unsqueeze(0), h_state).state
    rec_d, revs = am.observe_with_revision(
        event_id=stream_length,
        timestamp=float(stream_length),
        embedding=vec_D,
        temporal_state=h_state[0],
        cold_memory=cold,
        revision_engine=engine,
    )

    elapsed_ms = (time.perf_counter() - t0) * 1000

    restored_ids = [r.candidate.event_id for r in revs if r.decision == "restore"]
    a_restored = t_A in restored_ids
    r_restored = t_R in restored_ids
    f_restored = t_F in restored_ids

    # --- Score component audit: compute scores for A, R, F if they are in cold ---
    def _audit_candidate(event_id: int) -> dict[str, float]:
        """Get full score breakdown for a candidate."""
        for rev in revs:
            if rev.candidate.event_id == event_id:
                return {"total": rev.revision_score, **rev.components}
        # Candidate not in revision results — compute manually if in cold
        for rec in cold.records:
            if rec.event_id == event_id:
                _, comps = engine._compute_revision_score_with_components(
                    rec, vec_D, h_state[0], float(stream_length)
                )
                total = (
                    engine.config.w_sim * comps["sim"]
                    + engine.config.w_state_compat * comps["state_compat"]
                    + engine.config.w_temporal_compat * comps["temporal_compat"]
                    + engine.config.w_provenance_compat * comps["provenance_compat"]
                )
                return {"total": total, **comps}
        return {"total": 0.0, "sim": 0.0, "state_compat": 0.0, "temporal_compat": 0.0, "provenance_compat": 0.0}

    score_A = _audit_candidate(t_A)
    score_R = _audit_candidate(t_R)
    score_F = _audit_candidate(t_F)

    return {
        "restoration_policy": restoration_policy,
        "delta_t_config": delta_t_config,
        "seed": seed,
        "t_A": t_A,
        "t_R": t_R,
        "t_F": t_F,
        "delta_t_A": stream_length - t_A,
        "delta_t_R": stream_length - t_R,
        "delta_t_F": stream_length - t_F,
        "a_in_cold": a_in_cold,
        "a_in_hot": a_in_hot,
        "r_in_cold": r_in_cold,
        "r_in_hot": r_in_hot,
        "f_in_cold": f_in_cold,
        "f_in_hot": f_in_hot,
        "restored_ids": restored_ids,
        "a_restored": a_restored,
        "r_restored": r_restored,
        "f_restored": f_restored,
        "score_A": score_A,
        "score_R": score_R,
        "score_F": score_F,
        "latency_ms": elapsed_ms,
    }


def run_mission_2_9_6_suite(
    seeds: list[int] = [101, 202, 303],
    policies: list[str] | None = None,
    dt_configs: list[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    if policies is None:
        policies = ["R0_current_decay", "R1_no_temporal", "R2_weak_decay", "R3_csm_gated"]
    if dt_configs is None:
        dt_configs = ["dt100", "dt500", "dt1000", "dt2000", "dt2900"]

    results: dict[str, list[dict[str, Any]]] = {}

    for policy in policies:
        key = policy
        results[key] = []
        print(f"\n--> Policy: {policy}")
        for dt_cfg in dt_configs:
            for s in seeds:
                res = run_recency_trap_experiment(policy, dt_cfg, seed=s)
                results[key].append(res)
                a_mark = "✅" if res["a_restored"] else "❌"
                r_mark = "⚠️" if res["r_restored"] else "✅否"
                f_mark = "⚠️" if res["f_restored"] else "✅否"
                print(
                    f"    {dt_cfg}/seed{s}: A_restored={a_mark} R_restored={r_mark} F_restored={f_mark} "
                    f"ScoreA={res['score_A']['total']:.3f} ScoreR={res['score_R']['total']:.3f} ScoreF={res['score_F']['total']:.3f}"
                )

    return results
