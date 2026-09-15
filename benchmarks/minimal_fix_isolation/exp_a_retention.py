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


class StratifiedColdCandidateMemory(ColdCandidateMemory):
    """
    Stratified Cold Candidate Memory (A2):
    Splits capacity (K_cold=500) into two sub-pools:
    - Protected/High-Value pool (capacity=100): Evicts lowest importance_at_eviction (or FIFO among lowest).
    - Standard FIFO pool (capacity=400): Routine background events.
    Uses ONLY existing signals (importance_at_eviction derived from S, N, C, R, U).
    No new neural networks.
    """
    def __init__(self, capacity: int, embedding_dim: int, state_dim: int, high_val_cap: int = 100):
        super().__init__(capacity=capacity, embedding_dim=embedding_dim, state_dim=state_dim)
        self.high_val_cap = high_val_cap
        self.standard_cap = capacity - high_val_cap
        self.records_high: list[ColdCandidateRecord] = []
        self.records_std: list[ColdCandidateRecord] = []

    def archive(self, event_id: int, timestamp: float, embedding: Tensor,
                temporal_state: Tensor, importance: float, provenance: str) -> ColdCandidateRecord:
        emb = embedding.detach().float()
        if emb.ndim > 1:
            emb = emb.squeeze()
        norm = torch.norm(emb, p=2)
        if norm > 1e-8:
            emb = emb / norm

        state_fingerprint = temporal_state.detach().float()

        record = ColdCandidateRecord(
            event_id=event_id,
            timestamp=timestamp,
            compressed_embedding=emb,
            state_fingerprint=state_fingerprint,
            importance_at_eviction=importance,
            provenance_summary=provenance
        )

        # Threshold to qualify for high-value pool: importance >= 0.40 (existing signal)
        if importance >= 0.40:
            if len(self.records_high) >= self.high_val_cap:
                # Evict lowest importance from high-value pool
                min_idx = min(range(len(self.records_high)), key=lambda i: self.records_high[i].importance_at_eviction)
                self.records_high.pop(min_idx)
            self.records_high.append(record)
        else:
            if len(self.records_std) >= self.standard_cap:
                self.records_std.pop(0)  # FIFO for standard
            self.records_std.append(record)

        self._sync_all_records()
        return record

    def _sync_all_records(self) -> None:
        self.records = self.records_high + self.records_std
        if len(self.records) > 0:
            embs = [r.compressed_embedding.unsqueeze(0) for r in self.records]
            self.embeddings_tensor = torch.cat(embs, dim=0)
        else:
            self.embeddings_tensor = None


class ProtectedRootColdMemory(ColdCandidateMemory):
    """A1: Protected-root only baseline."""
    def __init__(self, capacity: int, embedding_dim: int, state_dim: int, root_id: int):
        super().__init__(capacity=capacity, embedding_dim=embedding_dim, state_dim=state_dim)
        self.root_id = root_id

    def _evict_oldest(self) -> None:
        if len(self.records) == 0:
            return
        idx = -1
        for i, rec in enumerate(self.records):
            if rec.event_id != self.root_id:
                idx = i
                break
        if idx != -1:
            self.records.pop(idx)
            if len(self.records) == 0:
                self.embeddings_tensor = None
            else:
                embs = [r.compressed_embedding.unsqueeze(0) for r in self.records]
                self.embeddings_tensor = torch.cat(embs, dim=0)


def run_exp_a_experiment(
    condition: str,  # 'A0_current_fifo', 'A1_protected_root', 'A2_stratified'
    seed: int,
    emb_dim: int = 32,
    state_dim: int = 32,
    stream_length: int = 3000,
    n_distractors: int = 500,
) -> dict[str, Any]:
    """
    M2.9.2-A: Stratified Retention Isolation Experiment.
    Compares:
      A0: Current FIFO
      A1: Protected-root only
      A2: Stratified retention (using only existing online signals)
    Under standard 500-distractor stress stream.
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

    if condition == "A0_current_fifo":
        cold = ColdCandidateMemory(capacity=k_cold, embedding_dim=emb_dim, state_dim=state_dim)
    elif condition == "A1_protected_root":
        cold = ProtectedRootColdMemory(capacity=k_cold, embedding_dim=emb_dim, state_dim=state_dim, root_id=root_id)
    elif condition == "A2_stratified":
        cold = StratifiedColdCandidateMemory(capacity=k_cold, embedding_dim=emb_dim, state_dim=state_dim, high_val_cap=100)
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

    root_admitted_cold_step = None
    root_evicted_cold_step = None

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
        rec = am.observe(
            event_id=t,
            timestamp=float(t),
            embedding=emb,
            temporal_state=h_state[0],
            cold_memory=cold,
        )

        in_cold = any(r.event_id == root_id for r in cold.records)
        if in_cold and root_admitted_cold_step is None:
            root_admitted_cold_step = t
        if not in_cold and root_admitted_cold_step is not None and root_evicted_cold_step is None:
            root_evicted_cold_step = t

    # Audit presence and ranking BEFORE revision execution
    root_in_cold_before_rev = any(r.event_id == root_id for r in cold.records)
    root_rank = -1
    if root_in_cold_before_rev and cold.embeddings_tensor is not None:
        q = vec_D / torch.norm(vec_D, p=2)
        sims = torch.mv(cold.embeddings_tensor, q)
        all_sims = [(cold.records[i].event_id, float(sims[i].item())) for i in range(len(cold.records))]
        all_sims.sort(key=lambda x: x[1], reverse=True)
        ranks = {item[0]: r + 1 for r, item in enumerate(all_sims)}
        root_rank = ranks.get(root_id, -1)

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

    # Calculate cold occupancy breakdown
    total_cold = len(cold.records)
    distractor_in_cold_count = sum(1 for r in cold.records if r.event_id in distractor_indices)
    background_in_cold_count = total_cold - distractor_in_cold_count

    root_in_cold = root_in_cold_before_rev

    # Metric calculations strictly adhering to directive 6
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

    return {
        "condition": condition,
        "seed": seed,
        "root_in_cold": root_in_cold,
        "root_eviction_time": root_evicted_cold_step,
        "cold_occupancy_total": total_cold,
        "distractor_occupancy": distractor_in_cold_count,
        "background_occupancy": background_in_cold_count,
        "root_rank": root_rank,
        "restoration_recall": restoration_recall,
        "restoration_count": restoration_count,
        "true_revision_count": true_revision_count,
        "false_revision_count": false_revision_count,
        "revision_precision": revision_precision,
        "false_revision_rate": false_revision_rate,
        "latency_ms": elapsed_ms,
    }


def run_exp_a_suite(seeds: list[int] = [101, 202, 303]) -> dict[str, list[dict[str, Any]]]:
    conditions = ["A0_current_fifo", "A1_protected_root", "A2_stratified"]
    results: dict[str, list[dict[str, Any]]] = {c: [] for c in conditions}
    for c in conditions:
        for s in seeds:
            results[c].append(run_exp_a_experiment(condition=c, seed=s))
    return results


if __name__ == "__main__":
    res = run_exp_a_suite([999])
    print("Exp A smoke run passed.")
