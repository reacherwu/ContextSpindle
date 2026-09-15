from __future__ import annotations

import random
import time
from typing import Any

import torch
from torch import Tensor

from continuum.memory.adaptive_memory import AdaptiveMemory, AdaptiveMemoryConfig
from continuum.memory.cold_memory import ColdCandidateMemory, ColdCandidateRecord
from continuum.memory.revision_engine import RevisionConfig, RevisionEngine
from continuum.state.temporal_state import TemporalState, TemporalStateConfig


class UniquenessBiasedColdMemory(ColdCandidateMemory):
    """
    M1: Uniqueness/Novelty-Biased Cold Memory.
    When full, evicts the candidate with the highest pairwise similarity to other cold records
    (strictly keeps what is most orthogonal/unique).
    """
    def __init__(self, capacity: int, embedding_dim: int, state_dim: int):
        super().__init__(capacity=capacity, embedding_dim=embedding_dim, state_dim=state_dim)

    def _evict_oldest(self) -> None:
        if len(self.records) == 0:
            return
        with torch.no_grad():
            sim_mat = torch.matmul(self.embeddings_tensor, self.embeddings_tensor.T)
            sim_mat.fill_diagonal_(-1.0)
            max_sims, _ = torch.max(sim_mat, dim=1)
            evict_idx = torch.argmax(max_sims).item()

        self.records.pop(evict_idx)
        if len(self.records) == 0:
            self.embeddings_tensor = None
        else:
            self.embeddings_tensor = torch.cat(
                [self.embeddings_tensor[:evict_idx], self.embeddings_tensor[evict_idx + 1 :]], dim=0
            )


class RedundancyFIFOColdMemory(ColdCandidateMemory):
    """
    M2: Non-Oracle Redundancy-FIFO Cold Memory (from Mission 2.9.3).
    When full, evicts oldest redundant candidate (sim >= 0.85). If none redundant, FIFO.
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
            evict_idx = 0
        self.records.pop(evict_idx)
        if len(self.records) == 0:
            self.embeddings_tensor = None
        else:
            self.embeddings_tensor = torch.cat(
                [self.embeddings_tensor[:evict_idx], self.embeddings_tensor[evict_idx + 1 :]], dim=0
            )


class DynamicalTrajectoryColdMemory(ColdCandidateMemory):
    """
    M3: Dynamical Latent Trajectory Coherence Cold Memory.
    Uses online observable temporal dynamics:
    Measures dynamical transition footprint:
      Priority(e) = (0.5 * importance_at_eviction + 0.5 * ||h_e||_2) * (1.0 - redundancy_to_cluster)
    Evicts lowest dynamical priority.
    """
    def __init__(self, capacity: int, embedding_dim: int, state_dim: int):
        super().__init__(capacity=capacity, embedding_dim=embedding_dim, state_dim=state_dim)

    def _evict_oldest(self) -> None:
        if len(self.records) == 0:
            return
        with torch.no_grad():
            if self.embeddings_tensor is not None and len(self.records) > 3:
                sim_mat = torch.matmul(self.embeddings_tensor, self.embeddings_tensor.T)
                sim_mat.fill_diagonal_(-1.0)
                top3_sims = torch.topk(sim_mat, k=min(3, len(self.records) - 1), dim=1).values.mean(dim=1)

                scores = []
                for i, rec in enumerate(self.records):
                    uniqueness = max(0.0, 1.0 - float(top3_sims[i].item()))
                    st_norm = float(torch.norm(rec.state_fingerprint, p=2).item())
                    score = (0.4 * rec.importance_at_eviction + 0.6 * min(1.0, st_norm)) * (uniqueness + 0.1)
                    scores.append(score)
                evict_idx = int(torch.tensor(scores).argmin().item())
            else:
                evict_idx = 0

        self.records.pop(evict_idx)
        if len(self.records) == 0:
            self.embeddings_tensor = None
        else:
            self.embeddings_tensor = torch.cat(
                [self.embeddings_tensor[:evict_idx], self.embeddings_tensor[evict_idx + 1 :]], dim=0
            )


def run_mission_2_9_4_experiment(
    condition: str,  # 'M0_fifo', 'M1_uniqueness_biased', 'M2_redundancy_fifo', 'M3_dynamical_trajectory'
    seed: int,
    emb_dim: int = 32,
    state_dim: int = 32,
    stream_length: int = 3000,
    n_traps: int = 50,
    n_distractors: int = 50,
) -> dict[str, Any]:
    """
    Mission 2.9.4 Causal vs Unique Discrimination Experiment.
    Injects:
    - Causal Anchor 1: Subtle/Low-Novelty Anchor (A_subtle at t=100, 0.90 cluster 0 + 0.10 subsystem)
    - Causal Anchor 2: Salient Anchor (A_salient at t=150, 0.85 subsystem + 0.15 noise)
    - Unique Anomaly Traps: 50 orthogonal vectors with high novelty, zero causal link (t in [200, 1500])
    - Superficial Distractors: 50 events superficially aligned with terminal symptom D (t in [200, 2800])
    - Background: Operational cycling across 3 clusters
    - Terminal Evidence: Event D at t=3000 (subsystem aligned)
    """
    torch.manual_seed(seed)
    random.seed(seed)

    n_clusters = 3
    clusters = [torch.randn(emb_dim) for _ in range(n_clusters)]
    for c in clusters:
        c /= torch.norm(c, p=2)

    subsystem = torch.randn(emb_dim)
    for c in clusters:
        subsystem -= torch.dot(subsystem, c) * c
    subsystem /= torch.norm(subsystem)

    # Class 1: Subtle Causal Anchor
    subtle_id = 100
    vec_subtle = 0.90 * clusters[0] + 0.10 * subsystem
    vec_subtle /= torch.norm(vec_subtle)

    # Class 2: Salient Causal Anchor
    salient_id = 150
    vec_salient = 0.85 * subsystem + 0.15 * torch.randn(emb_dim)
    vec_salient /= torch.norm(vec_salient)

    # Terminal Event D
    vec_D = 0.85 * subsystem + 0.15 * torch.randn(emb_dim)
    vec_D /= torch.norm(vec_D)

    # Class 3: Unique Anomaly Traps
    available_trap_steps = [t for t in range(200, 1500, 20) if t not in (subtle_id, salient_id)]
    trap_steps = set(random.sample(available_trap_steps, min(n_traps, len(available_trap_steps))))
    trap_vectors: dict[int, Tensor] = {}
    for t in trap_steps:
        v = torch.randn(emb_dim)
        for c in clusters:
            v -= torch.dot(v, c) * c
        v -= torch.dot(v, subsystem) * subsystem
        trap_vectors[t] = v / torch.norm(v)

    # Class 4: Superficial Distractors
    available_dist_steps = [t for t in range(200, stream_length - 50) if t not in trap_steps and t not in (subtle_id, salient_id)]
    dist_steps = set(random.sample(available_dist_steps, min(n_distractors, len(available_dist_steps))))
    dist_vectors: dict[int, Tensor] = {}
    for t in dist_steps:
        v = 0.35 * vec_D + 0.65 * torch.randn(emb_dim)
        dist_vectors[t] = v / torch.norm(v)

    t_cfg = TemporalStateConfig(input_size=emb_dim, hidden_size=state_dim)
    temporal_model = TemporalState(t_cfg)
    h_state = temporal_model.initial_state(1)

    k_hot = 250
    k_cold = 500

    if condition == "M0_fifo":
        cold = ColdCandidateMemory(capacity=k_cold, embedding_dim=emb_dim, state_dim=state_dim)
    elif condition == "M1_uniqueness_biased":
        cold = UniquenessBiasedColdMemory(capacity=k_cold, embedding_dim=emb_dim, state_dim=state_dim)
    elif condition == "M2_redundancy_fifo":
        cold = RedundancyFIFOColdMemory(capacity=k_cold, embedding_dim=emb_dim, state_dim=state_dim, sim_thresh=0.85)
    elif condition == "M3_dynamical_trajectory":
        cold = DynamicalTrajectoryColdMemory(capacity=k_cold, embedding_dim=emb_dim, state_dim=state_dim)
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

    for t in range(stream_length):
        if t == subtle_id:
            emb = vec_subtle
        elif t == salient_id:
            emb = vec_salient
        elif t in trap_steps:
            emb = trap_vectors[t]
        elif t in dist_steps:
            emb = dist_vectors[t]
        else:
            c_idx = (t // 25) % n_clusters
            emb = clusters[c_idx] + 0.03 * torch.randn(emb_dim)
            emb /= torch.norm(emb, p=2)

        h_state = temporal_model.step(emb.unsqueeze(0), h_state).state
        am.observe(
            event_id=t,
            timestamp=float(t),
            embedding=emb,
            temporal_state=h_state[0],
            cold_memory=cold,
        )

    # Post-stream audit of memory contents before terminal revision
    subtle_in_cold = any(r.event_id == subtle_id for r in cold.records)
    salient_in_cold = any(r.event_id == salient_id for r in cold.records)
    subtle_in_hot = any(r.event_id == subtle_id for r in am.records)
    salient_in_hot = any(r.event_id == salient_id for r in am.records)

    traps_in_cold = sum(1 for r in cold.records if r.event_id in trap_steps)
    distractors_in_cold = sum(1 for r in cold.records if r.event_id in dist_steps)
    total_cold = len(cold.records)
    bg_in_cold = total_cold - traps_in_cold - distractors_in_cold - (1 if subtle_in_cold else 0) - (1 if salient_in_cold else 0)

    # Discrimination Ratio:
    # CDR = Retention(Causal) / Retention(Traps)
    # Retention(Causal) = (subtle_in_cold + salient_in_cold) / 2
    # Retention(Traps) = traps_in_cold / len(trap_steps)
    retention_causal = (1.0 if (subtle_in_cold or subtle_in_hot) else 0.0) + (1.0 if (salient_in_cold or salient_in_hot) else 0.0)
    retention_causal_mean = retention_causal / 2.0
    trap_retention_rate = traps_in_cold / len(trap_steps) if len(trap_steps) > 0 else 0.0
    
    if trap_retention_rate > 0:
        cdr = retention_causal_mean / trap_retention_rate
    else:
        cdr = retention_causal_mean * 10.0  # clean separation bonus

    # Terminal evidence trigger
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
    causal_restored = any(eid in (subtle_id, salient_id) for eid in restored_ids)
    trap_restored = any(eid in trap_steps for eid in restored_ids)
    distractor_restored = any(eid in dist_steps for eid in restored_ids)

    return {
        "condition": condition,
        "seed": seed,
        "subtle_in_cold": subtle_in_cold,
        "salient_in_cold": salient_in_cold,
        "subtle_in_hot": subtle_in_hot,
        "salient_in_hot": salient_in_hot,
        "traps_in_cold": traps_in_cold,
        "trap_retention_rate": trap_retention_rate,
        "distractors_in_cold": distractors_in_cold,
        "bg_in_cold": bg_in_cold,
        "total_cold": total_cold,
        "cdr": cdr,
        "restored_ids": restored_ids,
        "causal_restored": causal_restored,
        "trap_restored": trap_restored,
        "distractor_restored": distractor_restored,
        "latency_ms": elapsed_ms,
    }


def run_mission_2_9_4_suite(
    seeds: list[int] = [101, 202, 303],
    conditions: list[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    if conditions is None:
        conditions = [
            "M0_fifo",
            "M1_uniqueness_biased",
            "M2_redundancy_fifo",
            "M3_dynamical_trajectory",
        ]

    results: dict[str, list[dict[str, Any]]] = {c: [] for c in conditions}
    for c in conditions:
        for s in seeds:
            results[c].append(run_mission_2_9_4_experiment(condition=c, seed=s))
    return results
