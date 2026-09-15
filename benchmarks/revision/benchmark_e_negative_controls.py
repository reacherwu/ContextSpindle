from __future__ import annotations

import random
from typing import Any

import torch
from torch import Tensor

from continuum.memory.adaptive_memory import AdaptiveMemory, AdaptiveMemoryConfig
from continuum.memory.cold_memory import ColdCandidateMemory
from continuum.memory.revision_engine import RevisionConfig, RevisionEngine
from continuum.state.temporal_state import TemporalState, TemporalStateConfig


def run_nc_condition(scenario_id: str, seed: int) -> dict[str, Any]:
    """
    Executes one of the 4 negative control scenarios for Memory Revision:
    - NC1: Positive control (True delayed causal chain A -> D)
    - NC2: False causal (accidental similarity without causal connection)
    - NC3: Correlated distractor (Distractor A at 100 vs True Root B at 150)
    - NC4: Random historical candidates (50 candidate events at 100..150)
    """
    emb_dim = 32
    state_dim = 32
    stream_length = 3000

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

    vec_root = 0.85 * subsystem + 0.15 * torch.randn(emb_dim)
    vec_root /= torch.norm(vec_root)
    vec_D = 0.85 * subsystem + 0.15 * torch.randn(emb_dim)
    vec_D /= torch.norm(vec_D)

    t_cfg = TemporalStateConfig(input_size=emb_dim, hidden_size=state_dim)
    temporal_model = TemporalState(t_cfg)
    h_state = temporal_model.initial_state(1)

    cold = ColdCandidateMemory(capacity=500, embedding_dim=emb_dim, state_dim=state_dim)
    am = AdaptiveMemory(
        AdaptiveMemoryConfig(
            embedding_dim=emb_dim,
            state_dim=state_dim,
            capacity=250,
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

    true_root_id = -1
    false_revisions = 0
    true_revisions = 0

    if scenario_id == "NC1":  # True causal (Positive Control)
        true_root_id = 100
    elif scenario_id == "NC2":  # False causal (accidental similarity but orthogonal state/subsystem)
        true_root_id = -1
        vec_root = 0.35 * vec_D + 0.65 * torch.randn(emb_dim)
        vec_root /= torch.norm(vec_root)
    elif scenario_id == "NC3":  # Correlated distractor: A is distractor at 100, B at 150 is true root
        true_root_id = 150
        vec_A = 0.40 * subsystem + 0.60 * torch.randn(emb_dim)
        vec_A /= torch.norm(vec_A)
    elif scenario_id == "NC4":  # Random historical candidates
        true_root_id = -1

    for t in range(stream_length):
        if scenario_id == "NC1" and t == 100:
            emb = vec_root
        elif scenario_id == "NC2" and t == 100:
            emb = vec_root
        elif scenario_id == "NC3" and t == 100:
            emb = vec_A
        elif scenario_id == "NC3" and t == 150:
            emb = vec_root
        elif scenario_id == "NC4" and 100 <= t < 150:
            emb = 0.25 * vec_D + 0.75 * torch.randn(emb_dim)
            emb /= torch.norm(emb)
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

    h_3000 = temporal_model.step(5.0 * vec_D.unsqueeze(0), h_state).state[0]
    rec, revs = am.observe_with_revision(
        event_id=stream_length,
        timestamp=float(stream_length),
        embedding=vec_D,
        temporal_state=h_3000,
        cold_memory=cold,
        revision_engine=engine,
    )

    for r in revs:
        if r.decision == "restore":
            if true_root_id != -1 and r.candidate.event_id == true_root_id:
                true_revisions += 1
            else:
                false_revisions += 1

    root_recalled = any(r.event_id == true_root_id for r in am.records) if true_root_id != -1 else False
    precision = (
        true_revisions / (true_revisions + false_revisions)
        if (true_revisions + false_revisions) > 0
        else (1.0 if true_root_id == -1 else 0.0)
    )

    return {
        "Recall_root": 1.0 if root_recalled else 0.0,
        "FalseRevisionRate": float(false_revisions),
        "RevisionPrecision": float(precision),
        "ColdMemory_slots_used": len(cold.records),
    }

