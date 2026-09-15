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


class ProtectedColdCandidateMemory(ColdCandidateMemory):
    """
    ColdCandidateMemory with protected slots that cannot be evicted by FIFO.
    Ensures storage failure is strictly isolated from retrieval failure.
    """
    def __init__(self, capacity: int, embedding_dim: int, state_dim: int, protected_eids: set[int]):
        super().__init__(capacity=capacity, embedding_dim=embedding_dim, state_dim=state_dim)
        self.protected_eids = protected_eids

    def _evict_oldest(self) -> None:
        if len(self.records) == 0:
            return
        # Evict oldest NON-PROTECTED candidate
        idx_to_evict = -1
        for i, rec in enumerate(self.records):
            if rec.event_id not in self.protected_eids:
                idx_to_evict = i
                break

        if idx_to_evict != -1:
            self.records.pop(idx_to_evict)
            if self.embeddings_tensor is not None:
                if len(self.records) == 0:
                    self.embeddings_tensor = None
                else:
                    self.embeddings_tensor = torch.cat(
                        [self.embeddings_tensor[:idx_to_evict], self.embeddings_tensor[idx_to_evict + 1:]], dim=0
                    )


def run_m2_experiment(
    top_k_val: int | str,  # 10, 25, 50, 100, 250, 500, 'ALL'
    distractor_count: int,  # 500 by default (from crowding protocol)
    seed: int,
    emb_dim: int = 32,
    state_dim: int = 32,
    stream_length: int = 3000,
) -> dict[str, Any]:
    """
    M2 — Retrieval Isolation Experiment
    Forces true root to ALWAYS remain in Cold Memory (protecting from FIFO eviction).
    Then sweeps Top-K across [10, 25, 50, 100, 250, 500, 'ALL'].
    Measures whether Top-K candidate truncation is the root bottleneck of crowding failure.
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

    vec_terminal = 0.85 * subsystem + 0.15 * torch.randn(emb_dim)
    vec_terminal /= torch.norm(vec_terminal)

    # 500 distractors distributed across stream
    distractor_indices = set()
    if distractor_count > 0:
        available = [t for t in range(200, stream_length - 50) if t != root_id]
        chosen = random.sample(available, min(distractor_count, len(available)))
        distractor_indices = set(chosen)

    t_cfg = TemporalStateConfig(input_size=emb_dim, hidden_size=state_dim)
    temporal_model = TemporalState(t_cfg)
    h_state = temporal_model.initial_state(1)

    k_hot = 250
    k_cold = 500
    # Use Protected Cold Memory to isolate storage eviction
    cold = ProtectedColdCandidateMemory(
        capacity=k_cold, embedding_dim=emb_dim, state_dim=state_dim, protected_eids={root_id}
    )
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
        if t == root_id:
            emb = vec_root
        elif t in distractor_indices:
            # Distractor has partial alignment with D (standard distractor protocol)
            emb = 0.35 * vec_terminal + 0.65 * torch.randn(emb_dim)
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

    # In case root was still in hot memory or never evicted to cold, ensure root is present in cold
    root_in_cold = any(r.event_id == root_id for r in cold.records)
    if not root_in_cold:
        # Check if in hot
        root_rec_in_hot = next((r for r in am.records if r.event_id == root_id), None)
        if root_rec_in_hot is not None:
            # Hot memory held it, evict it to cold to ensure it's in cold candidate pool
            st = am._record_states.get(root_id, h_state[0])
            cold.archive(root_id, float(root_id), vec_root, st, root_rec_in_hot.importance, "protected_isolation")
        else:
            # Force archive into cold
            cold.archive(root_id, float(root_id), vec_root, h_state[0], 0.5, "protected_isolation")
        root_in_cold = True

    terminal_id = stream_length
    terminal_ts = float(terminal_id)
    terminal_emb = vec_terminal
    h_state = temporal_model.step(5.0 * vec_terminal.unsqueeze(0), h_state).state
    terminal_state = h_state[0]

    # Calculate actual Top-K integer
    actual_top_k = len(cold.records) if top_k_val == "ALL" else int(top_k_val)

    # Search candidates with specified Top-K
    searched_candidates = cold.search(terminal_emb, top_k=min(actual_top_k, len(cold.records)))
    searched_eids = [cand.event_id for cand, _ in searched_candidates]
    root_in_top_k = root_id in searched_eids

    # Raw cosine ranks across all cold records
    q = terminal_emb / torch.norm(terminal_emb, p=2)
    sims = torch.mv(cold.embeddings_tensor, q)
    all_sims = [(cold.records[i].event_id, float(sims[i].item()), cold.records[i]) for i in range(len(cold.records))]
    all_sims.sort(key=lambda x: x[1], reverse=True)
    raw_ranks = {item[0]: r + 1 for r, item in enumerate(all_sims)}
    root_rank = raw_ranks.get(root_id, -1)

    # Score candidates using RevisionEngine
    scored_candidates = []
    for cand, _ in searched_candidates:
        sc, comp = engine._compute_revision_score_with_components(
            cand, terminal_emb, terminal_state, terminal_ts
        )
        scored_candidates.append((sc, cand, comp))
    scored_candidates.sort(key=lambda x: x[0], reverse=True)

    root_scored_item = next((item for item in scored_candidates if item[1].event_id == root_id), None)
    root_score = root_scored_item[0] if root_scored_item else 0.0

    # Decoy stats among scored
    decoy_scored = [item for item in scored_candidates if item[1].event_id != root_id]
    best_decoy_score = decoy_scored[0][0] if decoy_scored else 0.0
    best_decoy_rank = 1 if decoy_scored and (not root_scored_item or best_decoy_score > root_score) else (2 if decoy_scored else -1)

    # Restoration decision
    restored_ids = []
    if len(scored_candidates) > 0 and scored_candidates[0][0] > engine.config.theta_restore:
        winner = scored_candidates[0][1]
        restored_ids.append(winner.event_id)

    root_restored = root_id in restored_ids
    false_revisions = len([eid for eid in restored_ids if eid != root_id])
    precision = 1.0 if root_restored else (0.0 if len(restored_ids) > 0 else 0.0)

    elapsed_ms = (time.perf_counter() - t0) * 1000

    return {
        "distractor_count": distractor_count,
        "top_k": str(top_k_val),
        "actual_top_k": actual_top_k,
        "seed": seed,
        "root_in_cold": root_in_cold,
        "root_rank": root_rank,
        "root_score": root_score,
        "best_decoy_rank": best_decoy_rank,
        "best_decoy_score": best_decoy_score,
        "root_in_top_k": root_in_top_k,
        "restoration_recall": 1.0 if root_restored else 0.0,
        "revision_precision": precision,
        "false_revision_rate": float(false_revisions),
        "cold_size": len(cold.records),
        "latency_ms": elapsed_ms,
    }


def run_m2_suite(seeds: list[int] = [101, 202, 303]) -> dict[str, list[dict[str, Any]]]:
    top_k_levels = [10, 25, 50, 100, 250, 500, "ALL"]
    results: dict[str, list[dict[str, Any]]] = {}
    for k_val in top_k_levels:
        runs = []
        for s in seeds:
            runs.append(run_m2_experiment(top_k_val=k_val, distractor_count=500, seed=s))
        results[str(k_val)] = runs
    return results


if __name__ == "__main__":
    res = run_m2_suite([999])
    print("M2 smoke test passed.")
