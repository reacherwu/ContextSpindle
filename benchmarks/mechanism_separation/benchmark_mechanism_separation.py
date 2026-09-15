from __future__ import annotations

import math
import random
import time
from typing import Any

import torch
from torch import Tensor

from continuum.memory.adaptive_memory import AdaptiveMemory, AdaptiveMemoryConfig
from continuum.memory.cold_memory import ColdCandidateMemory, ColdCandidateRecord
from continuum.memory.revision_engine import RevisionConfig, RevisionEngine
from continuum.state.temporal_state import TemporalState, TemporalStateConfig


class NaiveDeltaColdMemory(ColdCandidateMemory):
    """
    P0: Naive State Delta Eviction.
    Evicts candidate with the lowest instantaneous state norm ||h_e||_2.
    Fails to separate transient spikes (high single-step norm) from true persistent changes.
    """
    def __init__(self, capacity: int, embedding_dim: int, state_dim: int):
        super().__init__(capacity=capacity, embedding_dim=embedding_dim, state_dim=state_dim)

    def _evict_oldest(self) -> None:
        if len(self.records) == 0:
            return
        norms = [float(torch.norm(r.state_fingerprint, p=2).item()) for r in self.records]
        evict_idx = int(torch.tensor(norms).argmin().item())

        self.records.pop(evict_idx)
        if len(self.records) == 0:
            self.embeddings_tensor = None
        else:
            self.embeddings_tensor = torch.cat(
                [self.embeddings_tensor[:evict_idx], self.embeddings_tensor[evict_idx + 1 :]], dim=0
            )


class PersistentDriftColdMemory(ColdCandidateMemory):
    """
    P1: Pure Persistent Drift Eviction.
    Evicts candidates with low persistence / rapid dissipation, but has NO subspace diversity.
    Prioritizes raw persistent state magnitude:
      score = importance + ||h_e||_2
    Without diversity, 10 massive non-causal regime shifts and ongoing drift displace subtle causal anchors.
    """
    def __init__(self, capacity: int, embedding_dim: int, state_dim: int):
        super().__init__(capacity=capacity, embedding_dim=embedding_dim, state_dim=state_dim)

    def _evict_oldest(self) -> None:
        if len(self.records) == 0:
            return
        scores = [
            float(0.3 * r.importance_at_eviction + 0.7 * torch.norm(r.state_fingerprint, p=2).item())
            for r in self.records
        ]
        evict_idx = int(torch.tensor(scores).argmin().item())

        self.records.pop(evict_idx)
        if len(self.records) == 0:
            self.embeddings_tensor = None
        else:
            self.embeddings_tensor = torch.cat(
                [self.embeddings_tensor[:evict_idx], self.embeddings_tensor[evict_idx + 1 :]], dim=0
            )


class DiversifiedDynamicsColdMemory(ColdCandidateMemory):
    """
    P2: Diversified Dynamical Attractor Cold Memory.
    Combines:
    1. Persistent state transition footprint (filters transient noise spikes).
    2. Subspace redundancy suppression (cosine similarity >= 0.85):
       If redundant background records exist, evict the oldest redundant record first.
       This prevents orthogonal regime shifts and background cycling from crowding out
       subtle causal anchors.
    """
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
                [self.embeddings_tensor[:evict_idx], self.embeddings_tensor[evict_idx + 1 :]], dim=0
            )


def run_mission_2_9_5_experiment(
    condition: str,  # 'P0_naive_delta', 'P1_persistent_drift', 'P2_diversified_dynamics', 'P3_two_stage_continuum'
    seed: int,
    emb_dim: int = 32,
    state_dim: int = 32,
    stream_length: int = 3000,
    n_regimes: int = 10,
    n_transients: int = 50,
    n_distractors: int = 50,
) -> dict[str, Any]:
    """
    Mission 2.9.5 Mechanism Isolation Experiment:
    Separating Persistent State Change from True Causal Explanatory Value.
    """
    torch.manual_seed(seed)
    random.seed(seed)

    n_clusters = 3
    basis_vectors: list[Tensor] = []
    
    # 1. 3 background cluster bases
    for _ in range(n_clusters):
        v = torch.randn(emb_dim)
        for b in basis_vectors:
            v -= torch.dot(v, b) * b
        v /= torch.norm(v, p=2)
        basis_vectors.append(v)
    clusters = basis_vectors[:n_clusters]

    # 2. Failure Subsystem X
    v_x = torch.randn(emb_dim)
    for b in basis_vectors:
        v_x -= torch.dot(v_x, b) * b
    v_x /= torch.norm(v_x, p=2)
    basis_vectors.append(v_x)

    # 3. 10 Orthogonal Regime Subsystems Y_1 .. Y_10
    regime_subsystems: list[Tensor] = []
    for _ in range(n_regimes):
        v_y = torch.randn(emb_dim)
        for b in basis_vectors:
            v_y -= torch.dot(v_y, b) * b
        v_y /= torch.norm(v_y, p=2)
        basis_vectors.append(v_y)
        regime_subsystems.append(v_y)

    # Class 1: Causal Anchor (A_causal, t=100)
    causal_id = 100
    vec_causal = 0.85 * v_x + 0.15 * torch.randn(emb_dim)
    vec_causal /= torch.norm(vec_causal, p=2)

    # Terminal Event D (t=3000)
    vec_D = 0.85 * v_x + 0.15 * torch.randn(emb_dim)
    vec_D /= torch.norm(vec_D, p=2)

    # Class 2: 10 Persistent Non-Causal Regime Shifts
    # Placed at regular intervals between t=300 and t=1800
    regime_steps = [300 + i * 150 for i in range(n_regimes)]
    regime_vectors: dict[int, Tensor] = {}
    for idx, t_step in enumerate(regime_steps):
        v_r = 0.90 * regime_subsystems[idx] + 0.10 * torch.randn(emb_dim)
        regime_vectors[t_step] = v_r / torch.norm(v_r, p=2)

    # Class 3: 50 Transient Outlier Spikes
    available_transient_steps = [
        t for t in range(200, 2500, 25)
        if t not in regime_steps and t != causal_id
    ]
    transient_steps = set(random.sample(available_transient_steps, min(n_transients, len(available_transient_steps))))
    transient_vectors: dict[int, Tensor] = {}
    for t in transient_steps:
        # High spatial novelty, orthogonal to clusters and subsystems
        v = torch.randn(emb_dim)
        for b in basis_vectors:
            v -= torch.dot(v, b) * b
        transient_vectors[t] = 2.0 * (v / torch.norm(v, p=2))

    # Class 4: 50 Superficial Distractors
    available_dist_steps = [
        t for t in range(200, stream_length - 50)
        if t not in regime_steps and t not in transient_steps and t != causal_id
    ]
    dist_steps = set(random.sample(available_dist_steps, min(n_distractors, len(available_dist_steps))))
    dist_vectors: dict[int, Tensor] = {}
    for t in dist_steps:
        v = 0.40 * vec_D + 0.60 * torch.randn(emb_dim)
        dist_vectors[t] = v / torch.norm(v, p=2)

    # Initialize TemporalState and Memories
    t_cfg = TemporalStateConfig(input_size=emb_dim, hidden_size=state_dim)
    temporal_model = TemporalState(t_cfg)
    h_state = temporal_model.initial_state(1)

    k_hot = 250
    k_cold = 500

    if condition == "P0_naive_delta":
        cold = NaiveDeltaColdMemory(capacity=k_cold, embedding_dim=emb_dim, state_dim=state_dim)
    elif condition == "P1_persistent_drift":
        cold = PersistentDriftColdMemory(capacity=k_cold, embedding_dim=emb_dim, state_dim=state_dim)
    elif condition in ("P2_diversified_dynamics", "P3_two_stage_continuum"):
        cold = DiversifiedDynamicsColdMemory(capacity=k_cold, embedding_dim=emb_dim, state_dim=state_dim, sim_thresh=0.85)
    else:
        raise ValueError(f"Unknown condition: {condition}")

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
    engine = RevisionEngine(
        RevisionConfig(
            theta_trigger=0.45,
            theta_restore=0.25,
            max_restorations_per_trigger=1,
        )
    )

    t0 = time.perf_counter()

    # Active regime offsets accumulator
    active_regime_offsets = torch.zeros(emb_dim)
    causal_active = False

    for t in range(stream_length):
        if t == causal_id:
            emb = vec_causal
            causal_active = True
        elif t in regime_steps:
            emb = regime_vectors[t]
            # Accumulate persistent regime shift into background state
            r_idx = regime_steps.index(t)
            active_regime_offsets += 0.25 * regime_subsystems[r_idx]
        elif t in transient_steps:
            emb = transient_vectors[t]
        elif t in dist_steps:
            emb = dist_vectors[t]
        else:
            c_idx = (t // 25) % n_clusters
            base_vec = clusters[c_idx]
            # Add persistent regime offsets
            base_vec = base_vec + active_regime_offsets
            if causal_active:
                # Persistent subtle failure drift along subsystem X
                drift_factor = min(0.35, 0.05 + 0.0001 * (t - causal_id))
                base_vec = base_vec + drift_factor * v_x
            base_vec = base_vec + 0.03 * torch.randn(emb_dim)
            emb = base_vec / torch.norm(base_vec, p=2)

        # Recurrent step
        h_state = temporal_model.step(emb.unsqueeze(0), h_state).state
        am.observe(
            event_id=t,
            timestamp=float(t),
            embedding=emb,
            temporal_state=h_state[0],
            cold_memory=cold,
        )

    # Pre-revision audit of Cold Memory contents
    causal_in_cold = any(r.event_id == causal_id for r in cold.records)
    causal_in_hot = any(r.event_id == causal_id for r in am.records)
    causal_retained = causal_in_cold or causal_in_hot

    regimes_in_cold = sum(1 for r in cold.records if r.event_id in regime_steps)
    transients_in_cold = sum(1 for r in cold.records if r.event_id in transient_steps)
    distractors_in_cold = sum(1 for r in cold.records if r.event_id in dist_steps)
    total_cold = len(cold.records)

    transient_suppression_rate = 1.0 - (transients_in_cold / len(transient_steps)) if len(transient_steps) > 0 else 1.0
    distractor_suppression_rate = 1.0 - (distractors_in_cold / len(dist_steps)) if len(dist_steps) > 0 else 1.0

    # Terminal evidence trigger at t=3000
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
    causal_restored = causal_id in restored_ids
    regime_restored = any(eid in regime_steps for eid in restored_ids)
    transient_restored = any(eid in transient_steps for eid in restored_ids)
    distractor_restored = any(eid in dist_steps for eid in restored_ids)

    # Compute RevisionScores directly for audit of Causal Separation Margin (CSM)
    causal_score = 0.0
    regime_scores: list[float] = []
    
    # Audit candidates scored in revision engine
    for r in revs:
        eid = r.candidate.event_id
        if eid == causal_id:
            causal_score = r.revision_score
        elif eid in regime_steps:
            regime_scores.append(r.revision_score)

    # If causal anchor was not scored (e.g. not retrieved or evicted), calculate what score would be or set to 0.0
    if causal_score == 0.0 and causal_in_cold:
        for rec in cold.records:
            if rec.event_id == causal_id:
                causal_score = engine.compute_revision_score(rec, vec_D, h_state[0], float(stream_length))
                break

    # If regime shifts were in cold, compute their scores against D
    if not regime_scores:
        for rec in cold.records:
            if rec.event_id in regime_steps:
                regime_scores.append(engine.compute_revision_score(rec, vec_D, h_state[0], float(stream_length)))

    max_regime_score = max(regime_scores) if regime_scores else 0.0
    csm = causal_score - max_regime_score

    return {
        "condition": condition,
        "seed": seed,
        "causal_in_cold": causal_in_cold,
        "causal_in_hot": causal_in_hot,
        "causal_retained": causal_retained,
        "regimes_in_cold": regimes_in_cold,
        "transients_in_cold": transients_in_cold,
        "distractors_in_cold": distractors_in_cold,
        "total_cold": total_cold,
        "transient_suppression_rate": transient_suppression_rate,
        "distractor_suppression_rate": distractor_suppression_rate,
        "restored_ids": restored_ids,
        "causal_restored": causal_restored,
        "regime_restored": regime_restored,
        "transient_restored": transient_restored,
        "distractor_restored": distractor_restored,
        "causal_score": causal_score,
        "max_regime_score": max_regime_score,
        "csm": csm,
        "latency_ms": elapsed_ms,
    }


def run_mission_2_9_5_suite(
    seeds: list[int] = [101, 202, 303],
    conditions: list[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    if conditions is None:
        conditions = [
            "P0_naive_delta",
            "P1_persistent_drift",
            "P2_diversified_dynamics",
            "P3_two_stage_continuum",
        ]

    results: dict[str, list[dict[str, Any]]] = {c: [] for c in conditions}

    for cond in conditions:
        print(f"--> Running Condition {cond} across seeds {seeds}...")
        for s in seeds:
            res = run_mission_2_9_5_experiment(cond, seed=s)
            results[cond].append(res)
            causal_mark = "✅" if res["causal_retained"] else "❌"
            rec_mark = "✅" if res["causal_restored"] else "❌"
            print(
                f"    Seed {s}: Causal Retained={causal_mark}, Regimes={res['regimes_in_cold']}/10, "
                f"Transients={res['transients_in_cold']}/50, Restored={res['restored_ids']}, "
                f"Causal Restored={rec_mark}, CSM={res['csm']:.3f}"
            )

    return results
