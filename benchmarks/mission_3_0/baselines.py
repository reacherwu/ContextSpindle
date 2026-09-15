from __future__ import annotations

import math
from typing import Any

import torch
from torch import Tensor, nn

from continuum.state.temporal_state import TemporalState, TemporalStateConfig


class B1_RecurrentStateOnly:
    """
    Baseline 1: Recurrent State Only (GRU / Minimal Mamba style).
    Maintains constant O(1) latent state vector, but has ZERO episodic memory slots.
    Cannot store or retrieve past episodic events.
    """
    def __init__(self, emb_dim: int = 32, state_dim: int = 32):
        self.config = TemporalStateConfig(input_size=emb_dim, hidden_size=state_dim)
        self.temporal_model = TemporalState(self.config)
        self.h_state = self.temporal_model.initial_state(1)
        self.step_count = 0

    def step(self, embedding: Tensor) -> Tensor:
        emb = embedding.detach().float()
        if emb.ndim == 1:
            emb = emb.unsqueeze(0)
        self.h_state = self.temporal_model.step(emb, self.h_state).state
        self.step_count += 1
        return self.h_state[0]

    def query_causal(self, query_embedding: Tensor, top_k: int = 5) -> list[int]:
        # Pure recurrent state cannot return past event IDs
        return []

    def get_memory_slots(self) -> int:
        return 0


class B2_FixedBudgetLRU:
    """
    Baseline 2: Standard Fixed-Budget LRU Memory.
    Capacity strictly bounded at K = 750 slots.
    Evicts the least recently accessed / observed item when full.
    Standard cosine similarity retrieval.
    """
    def __init__(self, capacity: int = 750, emb_dim: int = 32):
        self.capacity = capacity
        self.emb_dim = emb_dim
        self.records: list[dict[str, Any]] = []
        self.embeddings_tensor: Tensor | None = None
        self.last_access: list[float] = []

    def observe(self, event_id: int, timestamp: float, embedding: Tensor) -> None:
        emb = embedding.detach().float()
        if emb.ndim > 1:
            emb = emb.squeeze()
        norm = torch.norm(emb, p=2)
        if norm > 1e-8:
            emb = emb / norm

        if len(self.records) >= self.capacity:
            # Evict least recently used
            oldest_idx = int(torch.tensor(self.last_access).argmin().item())
            self.records.pop(oldest_idx)
            self.last_access.pop(oldest_idx)
            self.embeddings_tensor = torch.cat(
                [self.embeddings_tensor[:oldest_idx], self.embeddings_tensor[oldest_idx + 1:]], dim=0
            )

        self.records.append({"event_id": event_id, "timestamp": timestamp})
        self.last_access.append(timestamp)
        new_emb = emb.unsqueeze(0)
        if self.embeddings_tensor is None:
            self.embeddings_tensor = new_emb
        else:
            self.embeddings_tensor = torch.cat([self.embeddings_tensor, new_emb], dim=0)

    def query_causal(self, query_embedding: Tensor, top_k: int = 5) -> list[int]:
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
            _, top_indices = torch.topk(sims, k=k)

        results = []
        for idx in top_indices.tolist():
            results.append(self.records[idx]["event_id"])
            self.last_access[idx] = self.last_access[idx] + 1.0
        return results

    def get_memory_slots(self) -> int:
        return len(self.records)


class B3_SlidingWindowAttention:
    """
    Baseline 3: Sliding-Window Attention (Transformer KV-Cache window).
    Window size strictly bounded at W = 750 tokens/events.
    Maintains exact FIFO window over the most recent 750 events.
    Completely blind to events occurring before (t_current - W).
    """
    def __init__(self, window_size: int = 750, emb_dim: int = 32):
        self.window_size = window_size
        self.emb_dim = emb_dim
        self.records: list[dict[str, Any]] = []
        self.embeddings_tensor: Tensor | None = None

    def observe(self, event_id: int, timestamp: float, embedding: Tensor) -> None:
        emb = embedding.detach().float()
        if emb.ndim > 1:
            emb = emb.squeeze()
        norm = torch.norm(emb, p=2)
        if norm > 1e-8:
            emb = emb / norm

        if len(self.records) >= self.window_size:
            # FIFO pop oldest
            self.records.pop(0)
            self.embeddings_tensor = self.embeddings_tensor[1:]

        self.records.append({"event_id": event_id, "timestamp": timestamp})
        new_emb = emb.unsqueeze(0)
        if self.embeddings_tensor is None:
            self.embeddings_tensor = new_emb
        else:
            self.embeddings_tensor = torch.cat([self.embeddings_tensor, new_emb], dim=0)

    def query_causal(self, query_embedding: Tensor, top_k: int = 5) -> list[int]:
        if len(self.records) == 0 or self.embeddings_tensor is None:
            return []
        q = query_embedding.detach().float()
        if q.ndim > 1:
            q = q.squeeze()
        norm_q = torch.norm(q, p=2)
        if norm_q > 1e-8:
            q = q / norm_q

        # Scaled dot-product attention over the sliding window
        d_k = math.sqrt(float(self.emb_dim))
        k = min(top_k, len(self.records))
        with torch.no_grad():
            attn_scores = torch.mv(self.embeddings_tensor, q) / d_k
            _, top_indices = torch.topk(attn_scores, k=k)

        return [self.records[idx]["event_id"] for idx in top_indices.tolist()]

    def get_memory_slots(self) -> int:
        return len(self.records)


class B4_UnboundedArchive:
    """
    Baseline 4: Full Unbounded Linear Archive (Vector DB / Full Store).
    Capacity unbounded (K = T). Stores EVERY historical event.
    Represents theoretical retrieval upper bound, but memory is O(T) and search is O(T).
    """
    def __init__(self, emb_dim: int = 32):
        self.emb_dim = emb_dim
        self.records: list[dict[str, Any]] = []
        self.embeddings_tensor: Tensor | None = None

    def observe(self, event_id: int, timestamp: float, embedding: Tensor) -> None:
        emb = embedding.detach().float()
        if emb.ndim > 1:
            emb = emb.squeeze()
        norm = torch.norm(emb, p=2)
        if norm > 1e-8:
            emb = emb / norm

        self.records.append({"event_id": event_id, "timestamp": timestamp})
        new_emb = emb.unsqueeze(0)
        if self.embeddings_tensor is None:
            self.embeddings_tensor = new_emb
        else:
            self.embeddings_tensor = torch.cat([self.embeddings_tensor, new_emb], dim=0)

    def query_causal(self, query_embedding: Tensor, top_k: int = 5) -> list[int]:
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
            _, top_indices = torch.topk(sims, k=k)

        return [self.records[idx]["event_id"] for idx in top_indices.tolist()]

    def get_memory_slots(self) -> int:
        return len(self.records)
