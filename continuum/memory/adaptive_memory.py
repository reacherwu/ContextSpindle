from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

import torch
from torch import Tensor, nn


class RetentionDecision(str, Enum):
    KEEP = "keep"
    DISCARD = "discard"
    COMPRESS = "compress"


@dataclass(frozen=True)
class EventRecord:
    """
    Immutable representation of an event and its epistemic evaluation.
    Fields are strictly partitioned into Observed, Derived, and Predicted categories.
    Evaluation-only data (e.g. downstream queries, benchmark answers) are strictly prohibited.
    """
    # 1. Observed fields
    event_id: int
    timestamp: float
    embedding: Tensor  # Shape: [D], float32, normalized
    payload_ref: str | None = None

    # 2. Derived online metrics (computed at time t without lookahead)
    surprise: float = 0.0
    novelty: float = 0.0
    uncertainty: float = 0.0
    importance: float = 0.0
    decision: RetentionDecision = RetentionDecision.DISCARD
    provenance: dict[str, Any] = field(default_factory=dict)

    # 3. Predicted relevance (strictly backward conditioned)
    proxy_causal_score: float = 0.0
    retrieval_probability: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.embedding, Tensor):
            raise TypeError(f"embedding must be a torch.Tensor, got {type(self.embedding)}")
        if self.embedding.ndim != 1:
            raise ValueError(f"embedding must be 1D [D], got shape {self.embedding.shape}")
        if not torch.isfinite(self.embedding).all():
            raise ValueError(f"embedding for event {self.event_id} contains non-finite values")

        for name, val in [
            ("surprise", self.surprise),
            ("novelty", self.novelty),
            ("uncertainty", self.uncertainty),
            ("importance", self.importance),
            ("proxy_causal_score", self.proxy_causal_score),
            ("retrieval_probability", self.retrieval_probability),
        ]:
            if not isinstance(val, (int, float)) or not (0.0 <= float(val) <= 1.00001):
                raise ValueError(f"Metric {name} must be in [0.0, 1.0], got {val}")


@dataclass(frozen=True)
class AdaptiveMemoryConfig:
    embedding_dim: int
    state_dim: int = 64
    capacity: int = 1000
    policy_mode: Literal["fixed_budget", "threshold"] = "fixed_budget"
    eviction_policy: Literal["min_importance", "fifo", "random", "lru"] = "min_importance"
    threshold: float = 0.5

    # Five-factor weights (locked pre-registered equal-weight configuration)
    alpha_surprise: float = 0.2
    beta_novelty: float = 0.2
    gamma_causal: float = 0.2
    delta_retrieval: float = 0.2
    epsilon_uncertainty: float = 0.2

    # Streaming statistics and dynamics
    ema_lambda: float = 0.05
    min_sigma: float = 1e-4
    device: str = "cpu"
    seed: int | None = None

    def __post_init__(self) -> None:
        if self.embedding_dim <= 0:
            raise ValueError(f"embedding_dim must be positive, got {self.embedding_dim}")
        if self.capacity <= 0:
            raise ValueError(f"capacity must be positive, got {self.capacity}")
        total_weight = (
            self.alpha_surprise
            + self.beta_novelty
            + self.gamma_causal
            + self.delta_retrieval
            + self.epsilon_uncertainty
        )
        if total_weight < 1e-6:
            raise ValueError("Sum of factor weights must be positive.")


class AdaptiveMemory(nn.Module):
    """
    Adaptive Memory Module for Phase 3.
    Implements online multi-factor scoring, bounded-capacity memory bank,
    and multiple comparative eviction policies (min_importance, fifo, random, lru).
    """

    def __init__(self, config: AdaptiveMemoryConfig) -> None:
        super().__init__()
        self.config = config
        self.rng = random.Random(config.seed)

        # Lightweight online predictor: predicts expected x_t from temporal state h_{t-1}
        self.pred_head = nn.Linear(config.state_dim, config.embedding_dim, bias=True)
        # Initialize predictor deterministically
        nn.init.orthogonal_(self.pred_head.weight)
        nn.init.zeros_(self.pred_head.bias)

        # Memory storage (lists maintained under bounded capacity K)
        self.records: list[EventRecord] = []
        self.embeddings_tensor: Tensor | None = None  # Shape: [N, D]
        self.last_access_time: list[float] = []      # For LRU tracking

        # Online running statistics
        self.register_buffer("running_mean_error", torch.tensor(0.5, dtype=torch.float32))
        self.register_buffer("running_var_error", torch.tensor(0.25, dtype=torch.float32))
        self.last_state: Tensor | None = None

        # Telemetry and audit logs
        self.total_observed: int = 0
        self.total_retained: int = 0
        self.total_evicted: int = 0

        # Rolling factor history for correlation audits (capped at 5000 to bound RAM)
        self._history_surprise: list[float] = []
        self._history_novelty: list[float] = []
        self._history_causal: list[float] = []
        self._history_retrieval: list[float] = []
        self._history_uncertainty: list[float] = []

    def observe(
        self,
        event_id: int,
        timestamp: float,
        embedding: Tensor,
        temporal_state: Tensor | None = None,
        payload_ref: str | None = None,
    ) -> EventRecord:
        """
        Processes an incoming streaming event at time t strictly conditioned on x_{<=t}.
        Computes the 5 factors, decides retention, and updates memory bank.
        """
        self.total_observed += 1

        # Format and normalize input embedding
        x_t = embedding.detach().float()
        if x_t.ndim > 1:
            x_t = x_t.squeeze()
        if x_t.shape[0] != self.config.embedding_dim:
            raise ValueError(
                f"Embedding dimension mismatch: expected {self.config.embedding_dim}, got {x_t.shape[0]}"
            )
        norm = torch.norm(x_t, p=2)
        if norm < 1e-8:
            x_norm = x_t
        else:
            x_norm = x_t / norm

        # 1. Compute Surprise S_t: Prediction error relative to temporal state
        if temporal_state is not None:
            h_prev = temporal_state.detach().float()
            if h_prev.ndim > 1:
                h_prev = h_prev.squeeze()
            with torch.no_grad():
                x_pred = self.pred_head(h_prev)
                x_pred_norm = torch.norm(x_pred, p=2)
                if x_pred_norm > 1e-8:
                    x_pred = x_pred / x_pred_norm
                pred_error = float(torch.norm(x_norm - x_pred, p=2).item() ** 2)
        else:
            pred_error = 0.5

        # Update EMA of prediction error
        lam = self.config.ema_lambda
        var_e = float(self.running_var_error.item())
        mean_e = float(self.running_mean_error.item())
        new_mean = (1.0 - lam) * mean_e + lam * pred_error
        new_var = (1.0 - lam) * var_e + lam * ((pred_error - new_mean) ** 2)
        self.running_mean_error.fill_(new_mean)
        self.running_var_error.fill_(max(new_var, self.config.min_sigma))

        sigma_s = max(math.sqrt(float(self.running_var_error.item())), self.config.min_sigma)
        surprise = float(min(1.0, max(0.0, 1.0 - math.exp(-pred_error / (2.0 * (sigma_s ** 2))))))

        # 2. Compute Novelty N_t: Spatial orthogonality relative to active memory bank
        if len(self.records) == 0 or self.embeddings_tensor is None:
            novelty = 1.0
        else:
            with torch.no_grad():
                sims = torch.mv(self.embeddings_tensor, x_norm)
                max_sim = float(torch.max(sims).item())
                # Clamp to [-1, 1] and map to [0, 1] distance
                max_sim = max(-1.0, min(1.0, max_sim))
                novelty = float(min(1.0, max(0.0, (1.0 - max_sim) / 2.0)))

        # 3. Compute Proxy Causal Relevance C_t: State dynamical displacement proxy
        if temporal_state is not None and self.last_state is not None:
            delta_h = float(torch.norm(temporal_state.detach().float() - self.last_state, p=2).item())
            causal_score = float(min(1.0, max(0.0, math.tanh(delta_h / 2.0))))
        else:
            causal_score = 0.0

        if temporal_state is not None:
            self.last_state = temporal_state.detach().float().clone()

        # 4. Compute Retrieval Prior / Demand Prior R_t: R0 burstiness / recency heuristic
        if len(self.records) > 0 and self.embeddings_tensor is not None:
            with torch.no_grad():
                # Count recent local cluster matches within similarity threshold 0.7
                cluster_matches = int((sims > 0.7).sum().item())
                # Moderate burstiness indicates active recurrent topic
                retrieval_prior = float(min(1.0, 0.2 + 0.15 * min(cluster_matches, 5)))
        else:
            retrieval_prior = 0.5

        # 5. Compute Normalized Online Prediction Uncertainty U_t: Recent residual variance
        uncertainty = float(min(1.0, max(0.0, new_var / (new_var + 0.1))))

        # Composite Importance Score
        w_sum = (
            self.config.alpha_surprise
            + self.config.beta_novelty
            + self.config.gamma_causal
            + self.config.delta_retrieval
            + self.config.epsilon_uncertainty
        )
        raw_importance = (
            self.config.alpha_surprise * surprise
            + self.config.beta_novelty * novelty
            + self.config.gamma_causal * causal_score
            + self.config.delta_retrieval * retrieval_prior
            + self.config.epsilon_uncertainty * uncertainty
        ) / w_sum
        importance = float(min(1.0, max(0.0, raw_importance)))

        # Archive for correlation audit (capped buffer)
        if len(self._history_surprise) < 5000:
            self._history_surprise.append(surprise)
            self._history_novelty.append(novelty)
            self._history_causal.append(causal_score)
            self._history_retrieval.append(retrieval_prior)
            self._history_uncertainty.append(uncertainty)

        # Retention Policy Evaluation
        decision = RetentionDecision.DISCARD
        if self.config.policy_mode == "threshold":
            if importance >= self.config.threshold:
                decision = RetentionDecision.KEEP
        elif self.config.policy_mode == "fixed_budget":
            if len(self.records) < self.config.capacity:
                decision = RetentionDecision.KEEP
            else:
                # Capacity is reached, decide eviction based on policy
                decision = self._evaluate_fixed_budget_retention(importance)

        # Formulate record
        record = EventRecord(
            event_id=event_id,
            timestamp=timestamp,
            embedding=x_norm,
            payload_ref=payload_ref,
            surprise=surprise,
            novelty=novelty,
            uncertainty=uncertainty,
            importance=importance,
            decision=decision,
            provenance={
                "step": self.total_observed,
                "eviction_policy": self.config.eviction_policy,
            },
            proxy_causal_score=causal_score,
            retrieval_probability=retrieval_prior,
        )

        if decision == RetentionDecision.KEEP:
            self._insert_record(record, x_norm, timestamp)
            self.total_retained += 1

        return record

    def _evaluate_fixed_budget_retention(self, incoming_importance: float) -> RetentionDecision:
        """Determines if an incoming event should evict an existing event."""
        if self.config.eviction_policy == "fifo":
            self._evict_index(0)
            return RetentionDecision.KEEP
        elif self.config.eviction_policy == "random":
            evict_idx = self.rng.randrange(len(self.records))
            self._evict_index(evict_idx)
            return RetentionDecision.KEEP
        elif self.config.eviction_policy == "lru":
            oldest_idx = int(torch.tensor(self.last_access_time).argmin().item())
            self._evict_index(oldest_idx)
            return RetentionDecision.KEEP
        elif self.config.eviction_policy == "min_importance":
            # Find record with minimal importance
            min_imp = float("inf")
            min_idx = -1
            for idx, rec in enumerate(self.records):
                if rec.importance < min_imp:
                    min_imp = rec.importance
                    min_idx = idx

            if incoming_importance > min_imp:
                self._evict_index(min_idx)
                return RetentionDecision.KEEP
            else:
                return RetentionDecision.DISCARD
        else:
            return RetentionDecision.DISCARD

    def _evict_index(self, index: int) -> None:
        """Evicts a record at the specified index."""
        self.records.pop(index)
        self.last_access_time.pop(index)
        if self.embeddings_tensor is not None:
            if len(self.records) == 0:
                self.embeddings_tensor = None
            else:
                self.embeddings_tensor = torch.cat(
                    [self.embeddings_tensor[:index], self.embeddings_tensor[index + 1 :]], dim=0
                )
        self.total_evicted += 1

    def _insert_record(self, record: EventRecord, x_norm: Tensor, timestamp: float) -> None:
        """Appends a record to the active memory bank."""
        self.records.append(record)
        self.last_access_time.append(timestamp)
        new_emb = x_norm.unsqueeze(0)
        if self.embeddings_tensor is None:
            self.embeddings_tensor = new_emb
        else:
            self.embeddings_tensor = torch.cat([self.embeddings_tensor, new_emb], dim=0)

    def retrieve(self, query_embedding: Tensor, top_k: int = 5) -> list[tuple[EventRecord, float]]:
        """
        Retrieves top_k records by cosine similarity to query_embedding.
        Returns list of (EventRecord, similarity_score).
        Updates last_access_time for LRU tracking.
        """
        if len(self.records) == 0 or self.embeddings_tensor is None:
            return []

        q = query_embedding.detach().float()
        if q.ndim > 1:
            q = q.squeeze()
        q_norm = torch.norm(q, p=2)
        if q_norm > 1e-8:
            q = q / q_norm

        k = min(top_k, len(self.records))
        with torch.no_grad():
            sims = torch.mv(self.embeddings_tensor, q)
            top_vals, top_indices = torch.topk(sims, k=k)

        results: list[tuple[EventRecord, float]] = []
        for sim_val, idx in zip(top_vals.tolist(), top_indices.tolist()):
            results.append((self.records[idx], float(sim_val)))
            # Update access timestamp for LRU
            self.last_access_time[idx] = self.last_access_time[idx] + 1.0

        return results

    def compute_factor_correlations(self) -> dict[str, float]:
        """
        Audits Pearson correlations between factors S, N, C, R, U.
        Mandated by Gate Condition 5.
        """
        n = len(self._history_surprise)
        if n < 10:
            return {
                "corr_surprise_causal": 0.0,
                "corr_novelty_causal": 0.0,
                "corr_surprise_novelty": 0.0,
                "sample_size": float(n),
            }

        def _calc_pearson(a: list[float], b: list[float]) -> float:
            mean_a = sum(a) / n
            mean_b = sum(b) / n
            num = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b))
            den_a = math.sqrt(sum((x - mean_a) ** 2 for x in a))
            den_b = math.sqrt(sum((y - mean_b) ** 2 for y in b))
            if den_a < 1e-8 or den_b < 1e-8:
                return 0.0
            return float(num / (den_a * den_b))

        return {
            "corr_surprise_causal": _calc_pearson(self._history_surprise, self._history_causal),
            "corr_novelty_causal": _calc_pearson(self._history_novelty, self._history_causal),
            "corr_surprise_novelty": _calc_pearson(self._history_surprise, self._history_novelty),
            "corr_surprise_uncertainty": _calc_pearson(self._history_surprise, self._history_uncertainty),
            "sample_size": float(n),
        }

    def clear(self) -> None:
        """Resets active memory bank to empty state."""
        self.records.clear()
        self.embeddings_tensor = None
        self.last_access_time.clear()
        self.last_state = None

    def get_stats(self) -> dict[str, Any]:
        """Returns runtime diagnostic metrics."""
        mean_importance = (
            sum(r.importance for r in self.records) / len(self.records) if self.records else 0.0
        )
        return {
            "capacity": self.config.capacity,
            "current_size": len(self.records),
            "total_observed": self.total_observed,
            "total_retained": self.total_retained,
            "total_evicted": self.total_evicted,
            "mean_importance": mean_importance,
            "policy_mode": self.config.policy_mode,
            "eviction_policy": self.config.eviction_policy,
        }
