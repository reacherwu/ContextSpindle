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
from benchmarks.minimal_fix_isolation.exp_a_retention import ProtectedRootColdMemory


class RedundancyFIFOEvictionColdMemory(ColdCandidateMemory):
    """
    C2: Non-Oracle Online Redundancy-FIFO Eviction.
    When capacity (500) is reached:
    - Computes pairwise cosine similarities among candidates in cold memory.
    - If any candidate has max similarity >= sim_thresh (default 0.85) to another candidate,
      it is marked redundant (background cluster duplicate).
    - Evicts the oldest redundant candidate.
    - If no candidates are redundant (all unique directions), falls back to standard FIFO.
    Uses strictly observable online representations. Zero future knowledge, zero oracle.
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
            evict_idx = 0  # fallback to standard FIFO

        self.records.pop(evict_idx)
        if len(self.records) == 0:
            self.embeddings_tensor = None
        else:
            self.embeddings_tensor = torch.cat(
                [self.embeddings_tensor[:evict_idx], self.embeddings_tensor[evict_idx + 1 :]], dim=0
            )


class OnlineDedupMergeColdMemory(ColdCandidateMemory):
    """
    C3: Non-Oracle Online Dedup-Merge Admission.
    When a candidate arrives:
    - If its cosine similarity to an existing cold candidate >= sim_thresh (0.85),
      it merges/refreshes the existing representative's timestamp and state fingerprint,
      WITHOUT consuming a new slot and without pushing out a distinct historical memory.
    - If distinct, it archives normally. If capacity is reached, standard FIFO applies.
    Uses strictly observable online signals. Zero oracle.
    """
    def __init__(self, capacity: int, embedding_dim: int, state_dim: int, sim_thresh: float = 0.85):
        super().__init__(capacity=capacity, embedding_dim=embedding_dim, state_dim=state_dim)
        self.sim_thresh = sim_thresh

    def archive(
        self, event_id: int, timestamp: float, embedding: Tensor,
        temporal_state: Tensor, importance: float, provenance: str
    ) -> ColdCandidateRecord:
        emb = embedding.detach().float()
        if emb.ndim > 1:
            emb = emb.squeeze()
        norm = torch.norm(emb, p=2)
        if norm > 1e-8:
            emb = emb / norm
        st = temporal_state.detach().float()

        if self.embeddings_tensor is not None and len(self.records) > 0:
            with torch.no_grad():
                sims = torch.mv(self.embeddings_tensor, emb)
                max_sim, max_idx = torch.max(sims).item(), torch.argmax(sims).item()
                if max_sim >= self.sim_thresh:
                    updated = ColdCandidateRecord(
                        event_id=self.records[max_idx].event_id,
                        timestamp=timestamp,
                        compressed_embedding=self.records[max_idx].compressed_embedding,
                        state_fingerprint=st,
                        importance_at_eviction=importance,
                        provenance_summary=f"{self.records[max_idx].provenance_summary}+merged",
                    )
                    self.records[max_idx] = updated
                    return updated

        return super().archive(event_id, timestamp, embedding, temporal_state, importance, provenance)


class DynamicValueColdMemory(ColdCandidateMemory):
    """
    C4: Non-Oracle Online Dynamic Density & Value Eviction.
    Each candidate's retention priority is computed from online observables:
      Priority(e) = (1.0 - mean_top3_similarity(e)) * (0.5 * importance + 0.5 * state_norm)
    When full, evicts the candidate with lowest retention priority.
    Zero future knowledge, zero oracle.
    """
    def __init__(self, capacity: int, embedding_dim: int, state_dim: int):
        super().__init__(capacity=capacity, embedding_dim=embedding_dim, state_dim=state_dim)

    def _evict_oldest(self) -> None:
        if len(self.records) == 0:
            return

        evict_idx = 0
        with torch.no_grad():
            if self.embeddings_tensor is not None and len(self.records) > 3:
                sim_mat = torch.matmul(self.embeddings_tensor, self.embeddings_tensor.T)
                sim_mat.fill_diagonal_(-1.0)
                top_k = min(3, len(self.records) - 1)
                top_sims = torch.topk(sim_mat, k=top_k, dim=1).values.mean(dim=1)  # [N]
                
                scores = []
                for i, rec in enumerate(self.records):
                    uniqueness = max(0.0, 1.0 - float(top_sims[i].item()))
                    imp = rec.importance_at_eviction
                    st_norm = float(torch.norm(rec.state_fingerprint, p=2).item())
                    priority = uniqueness * (0.5 * imp + 0.5 * min(1.0, st_norm))
                    scores.append(priority)
                
                evict_idx = int(torch.tensor(scores).argmin().item())

        self.records.pop(evict_idx)
        if len(self.records) == 0:
            self.embeddings_tensor = None
        else:
            self.embeddings_tensor = torch.cat(
                [self.embeddings_tensor[:evict_idx], self.embeddings_tensor[evict_idx + 1 :]], dim=0
            )


def run_mission_2_9_3_experiment(
    condition: str,
    seed: int,
    emb_dim: int = 32,
    state_dim: int = 32,
    stream_length: int = 3000,
    n_distractors: int = 500,
) -> dict[str, Any]:
    """
    Mission 2.9.3 Single Experiment:
    Compares:
      C0_current_fifo: Baseline FIFO (A0)
      C1_oracle_protected: Upper-bound Oracle (A1)
      C2_online_redundancy_fifo: Non-oracle Redundancy-eviction
      C3_online_dedup_merge: Non-oracle Dedup-merge admission
      C4_dynamic_value: Non-oracle Dynamic value & uniqueness eviction
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

    root_id = 100
    vec_root = 0.85 * subsystem + 0.15 * torch.randn(emb_dim)
    vec_root /= torch.norm(vec_root)

    vec_D = 0.85 * subsystem + 0.15 * torch.randn(emb_dim)
    vec_D /= torch.norm(vec_D)

    available = [t for t in range(200, stream_length - 50) if t != root_id]
    chosen = random.sample(available, min(n_distractors, len(available)))
    distractor_indices = set(chosen)

    t_cfg = TemporalStateConfig(input_size=emb_dim, hidden_size=state_dim)
    temporal_model = TemporalState(t_cfg)
    h_state = temporal_model.initial_state(1)

    k_hot = 250
    k_cold = 500

    if condition == "C0_current_fifo":
        cold = ColdCandidateMemory(capacity=k_cold, embedding_dim=emb_dim, state_dim=state_dim)
    elif condition == "C1_oracle_protected":
        cold = ProtectedRootColdMemory(capacity=k_cold, embedding_dim=emb_dim, state_dim=state_dim, root_id=root_id)
    elif condition == "C2_online_redundancy_fifo":
        cold = RedundancyFIFOEvictionColdMemory(capacity=k_cold, embedding_dim=emb_dim, state_dim=state_dim, sim_thresh=0.85)
    elif condition == "C3_online_dedup_merge":
        cold = OnlineDedupMergeColdMemory(capacity=k_cold, embedding_dim=emb_dim, state_dim=state_dim, sim_thresh=0.85)
    elif condition == "C4_dynamic_value":
        cold = DynamicValueColdMemory(capacity=k_cold, embedding_dim=emb_dim, state_dim=state_dim)
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

    root_admitted_cold = False
    root_eviction_time = None

    for t in range(stream_length):
        if t == root_id:
            emb = vec_root
        elif t in distractor_indices:
            emb = 0.35 * vec_D + 0.65 * torch.randn(emb_dim)
            emb /= torch.norm(emb, p=2)
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

        in_cold = any(r.event_id == root_id for r in cold.records)
        if in_cold and not root_admitted_cold:
            root_admitted_cold = True
        if not in_cold and root_admitted_cold and root_eviction_time is None:
            root_eviction_time = t

    root_in_cold = any(r.event_id == root_id for r in cold.records)

    # Search candidates
    root_search_rank = -1
    searched = cold.search(vec_D, top_k=min(100, len(cold.records)))
    searched_eids = [c.event_id for c, _ in searched]
    if root_id in searched_eids:
        root_search_rank = searched_eids.index(root_id) + 1

    # Trigger terminal event
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
    restoration_count = len(restored_ids)
    true_revision_count = sum(1 for eid in restored_ids if eid == root_id)
    false_revision_count = sum(1 for eid in restored_ids if eid != root_id)

    root_restored = root_id in restored_ids
    restoration_recall = 1.0 if root_restored else 0.0

    if restoration_count > 0:
        revision_precision = true_revision_count / restoration_count
        false_revision_rate = false_revision_count / restoration_count
    else:
        revision_precision = 0.0
        false_revision_rate = 0.0

    total_cold = len(cold.records)
    distractor_occupancy = sum(1 for r in cold.records if r.event_id in distractor_indices)
    background_occupancy = total_cold - distractor_occupancy - (1 if root_in_cold else 0)

    cand_root = next((r for r in cold.records if r.event_id == root_id), None)
    root_revision_score = 0.0
    if cand_root is not None:
        root_revision_score = engine.compute_revision_score(
            cand_root, vec_D, h_state[0], float(stream_length)
        )

    return {
        "condition": condition,
        "seed": seed,
        "root_in_cold": root_in_cold,
        "root_eviction_time": root_eviction_time,
        "root_search_rank": root_search_rank,
        "root_revision_score": root_revision_score,
        "cold_occupancy_total": total_cold,
        "distractor_occupancy": distractor_occupancy,
        "background_occupancy": background_occupancy,
        "restoration_recall": restoration_recall,
        "restoration_count": restoration_count,
        "true_revision_count": true_revision_count,
        "false_revision_count": false_revision_count,
        "revision_precision": revision_precision,
        "false_revision_rate": false_revision_rate,
        "restored_ids": restored_ids,
        "latency_ms": elapsed_ms,
    }


def run_mission_2_9_3_suite(
    seeds: list[int] = [101, 202, 303],
    conditions: list[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    if conditions is None:
        conditions = [
            "C0_current_fifo",
            "C1_oracle_protected",
            "C2_online_redundancy_fifo",
            "C3_online_dedup_merge",
            "C4_dynamic_value",
        ]

    results: dict[str, list[dict[str, Any]]] = {c: [] for c in conditions}
    for c in conditions:
        for s in seeds:
            results[c].append(run_mission_2_9_3_experiment(condition=c, seed=s))
    return results
