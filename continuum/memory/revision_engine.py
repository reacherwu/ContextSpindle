import math
from dataclasses import dataclass
from typing import Any

import torch
from torch import Tensor

from continuum.memory.cold_memory import ColdCandidateRecord, ColdCandidateMemory


@dataclass(frozen=True)
class RevisionConfig:
    w_sim: float = 0.4
    w_state_compat: float = 0.3  
    w_temporal_compat: float = 0.2
    w_provenance_compat: float = 0.1
    theta_trigger: float = 0.7      # Only trigger when I(D) > this
    theta_restore: float = 0.5      # Only restore when R(A,D) > this
    temporal_decay_tau: float = 1000.0  # Decay constant for temporal compatibility
    max_restorations_per_trigger: int = 5  # Allow restoring top antecedent candidates per trigger event
    causal_exempt_threshold: float | None = None  # When set and sim >= this, exempt from temporal decay


@dataclass(frozen=True)
class RevisionResult:
    candidate: ColdCandidateRecord
    revision_score: float
    components: dict[str, float]  # sim, state_compat, temporal_compat, provenance_compat
    decision: str  # 'restore' or 'ignore'


class RevisionEngine:
    def __init__(self, config: RevisionConfig):
        self.config = config
    
    def compute_revision_score(
        self, candidate: ColdCandidateRecord, trigger_embedding: Tensor,
        trigger_state: Tensor, trigger_timestamp: float
    ) -> float:
        score, _ = self._compute_revision_score_with_components(
            candidate, trigger_embedding, trigger_state, trigger_timestamp
        )
        return score

    def _compute_revision_score_with_components(
        self, candidate: ColdCandidateRecord, trigger_embedding: Tensor,
        trigger_state: Tensor, trigger_timestamp: float
    ) -> tuple[float, dict[str, float]]:
        
        # Sim: cosine similarity between embeddings
        c_emb = candidate.compressed_embedding
        t_emb = trigger_embedding.detach().float()
        if t_emb.ndim > 1:
            t_emb = t_emb.squeeze()
        norm_t = torch.norm(t_emb, p=2)
        if norm_t > 1e-8:
            t_emb = t_emb / norm_t
            
        with torch.no_grad():
            sim = float(torch.dot(c_emb, t_emb).item())
            sim = max(0.0, min(1.0, sim))  # Clamp between 0 and 1
        
        # StateCompat: cosine similarity between state fingerprints
        c_state = candidate.state_fingerprint.clone()
        t_state = trigger_state.detach().float()
        
        norm_c = torch.norm(c_state, p=2)
        if norm_c > 1e-8:
            c_state = c_state / norm_c
        norm_ts = torch.norm(t_state, p=2)
        if norm_ts > 1e-8:
            t_state = t_state / norm_ts
            
        with torch.no_grad():
            state_compat = float(torch.dot(c_state, t_state).item())
            state_compat = max(0.0, min(1.0, state_compat))
            
        # TemporalCompat: exp(-|t_trigger - t_candidate| / tau)
        delta_t = abs(trigger_timestamp - candidate.timestamp)
        if self.config.causal_exempt_threshold is not None and sim >= self.config.causal_exempt_threshold:
            temporal_compat = 1.0
        else:
            temporal_compat = math.exp(-delta_t / self.config.temporal_decay_tau)
        
        # ProvenanceCompat: v1 constant 0.5 (Phase 7 hook)
        provenance_compat = 0.5
        
        score = (
            self.config.w_sim * sim +
            self.config.w_state_compat * state_compat +
            self.config.w_temporal_compat * temporal_compat +
            self.config.w_provenance_compat * provenance_compat
        )
        
        components = {
            "sim": sim,
            "state_compat": state_compat,
            "temporal_compat": temporal_compat,
            "provenance_compat": provenance_compat
        }
        
        return score, components
    
    def try_revision(
        self, trigger_event_id: int, trigger_embedding: Tensor,
        trigger_state: Tensor, trigger_timestamp: float,
        trigger_importance: float, cold_memory: ColdCandidateMemory
    ) -> list[RevisionResult]:
        
        # 1. Check if trigger_importance > theta_trigger
        if trigger_importance <= self.config.theta_trigger:
            return []
            
        # 2. Search cold memory for candidates
        candidates = cold_memory.search(trigger_embedding, top_k=min(100, len(cold_memory.records)))
        
        # 3. Score each candidate
        scored_candidates = []
        for candidate, _ in candidates:
            score, components = self._compute_revision_score_with_components(
                candidate, trigger_embedding, trigger_state, trigger_timestamp
            )
            scored_candidates.append((score, candidate, components))
            
        # 4. Return candidates exceeding theta_restore, sorted by score
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        
        results = []
        restorations = 0
        for score, candidate, components in scored_candidates:
            if score > self.config.theta_restore and restorations < self.config.max_restorations_per_trigger:
                decision = 'restore'
                restorations += 1
            else:
                decision = 'ignore'
                
            # As per requirements, we could return all or just restored. 
            # We return all candidates exceeding theta_restore (or all scored? instruction says:
            # "Return candidates exceeding theta_restore, sorted by score". Wait, the RevisionResult has 'decision'. 
            # If we only return those exceeding theta_restore, decision is always 'restore' (unless max_restorations hit).
            # I will just return those that exceed theta_restore, or just all that were searched.
            # I will return all searched candidates as RevisionResult. 
            results.append(RevisionResult(
                candidate=candidate,
                revision_score=score,
                components=components,
                decision=decision
            ))
            
        # Filter to only return those with restore decision if we strictly want that, 
        # but returning all gives more info. Let's return only those exceeding theta_restore.
        return [r for r in results if r.revision_score > self.config.theta_restore]
