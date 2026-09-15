"""Strong streaming sequence model baselines: DeltaNet and Gated Linear SSM (Minimal Mamba)."""

from __future__ import annotations

import math
from typing import Any

import torch
from torch import Tensor, nn
from torch.nn import functional as F


class StrongBaseline_DeltaNet(nn.Module):
    """
    Strong Baseline: DeltaNet (Linear Attention with Associative Delta Rule).
    Reference: Schlag et al. (2021) / Sun et al. (2024).
    
    Maintains a bounded key-value memory matrix S_t in R^{d_v x d_k}.
    Update rule: S_t = S_{t-1} + beta_t * (v_t - S_{t-1} k_t) k_t^T
    Strictly O(1) memory and O(1) per-step time complexity.
    """
    def __init__(self, emb_dim: int = 32, key_dim: int = 16, val_dim: int = 16):
        super().__init__()
        self.emb_dim = emb_dim
        self.key_dim = key_dim
        self.val_dim = val_dim

        self.W_k = nn.Linear(emb_dim, key_dim, bias=False)
        self.W_v = nn.Linear(emb_dim, val_dim, bias=False)
        self.W_beta = nn.Linear(emb_dim, 1, bias=True)
        self.W_out = nn.Linear(val_dim, emb_dim, bias=False)

        # Associative state S: [val_dim, key_dim]
        self.register_buffer("S", torch.zeros(val_dim, key_dim))
        self.step_count = 0

    def reset_state(self) -> None:
        self.S.zero_()
        self.step_count = 0

    def observe(self, event_id: int, timestamp: float, embedding: Tensor) -> None:
        emb = embedding.detach().float()
        if emb.ndim > 1:
            emb = emb.squeeze()
        norm = torch.norm(emb, p=2)
        if norm > 1e-8:
            emb = emb / norm

        with torch.no_grad():
            k = F.normalize(self.W_k(emb), p=2, dim=-1)  # [key_dim]
            v = self.W_v(emb)                          # [val_dim]
            beta = torch.sigmoid(self.W_beta(emb))      # scalar in (0, 1)

            # Delta rule error: e = v - S * k
            e = v - torch.mv(self.S, k)                 # [val_dim]
            # Outer product update: S = S + beta * (e (x) k)
            self.S.add_(beta * torch.outer(e, k))

        self.step_count += 1

    def query_causal(self, query_embedding: Tensor, top_k: int = 5) -> list[int]:
        # DeltaNet stores knowledge implicitly in weight matrix S
        # Like standard recurrent models without episodic slots, it cannot return past discrete event IDs
        return []

    def read_associative(self, query_embedding: Tensor) -> Tensor:
        q = query_embedding.detach().float()
        if q.ndim > 1:
            q = q.squeeze()
        q_norm = F.normalize(self.W_k(q), p=2, dim=-1)
        v_out = torch.mv(self.S, q_norm)
        return self.W_out(v_out)

    def get_memory_slots(self) -> int:
        return 0  # Parametric associative matrix; zero explicit episodic slots


class StrongBaseline_GatedSSM(nn.Module):
    """
    Strong Baseline: Gated Linear Selective State Space Model (Minimal Mamba).
    Reference: Gu & Dao (2023), "Mamba: Linear-Time Sequence Modeling with Selective State Spaces".
    
    Continuous state h_t = exp(A * Delta_t) * h_{t-1} + Delta_t * B_t * x_t
    With input-dependent selective discretization Delta_t = softplus(W_Delta * x_t).
    Strictly O(1) memory and O(1) per-step time complexity.
    """
    def __init__(self, emb_dim: int = 32, d_state: int = 32):
        super().__init__()
        self.emb_dim = emb_dim
        self.d_state = d_state

        # Log A parameter (diagonal decay)
        self.A_log = nn.Parameter(torch.log(torch.arange(1, d_state + 1, dtype=torch.float32)))
        self.W_B = nn.Linear(emb_dim, d_state, bias=False)
        self.W_C = nn.Linear(d_state, emb_dim, bias=False)
        self.W_delta = nn.Linear(emb_dim, d_state, bias=True)

        self.register_buffer("h", torch.zeros(d_state))
        self.step_count = 0

    def reset_state(self) -> None:
        self.h.zero_()
        self.step_count = 0

    def observe(self, event_id: int, timestamp: float, embedding: Tensor) -> None:
        emb = embedding.detach().float()
        if emb.ndim > 1:
            emb = emb.squeeze()
        norm = torch.norm(emb, p=2)
        if norm > 1e-8:
            emb = emb / norm

        with torch.no_grad():
            delta = F.softplus(self.W_delta(emb))      # [d_state]
            A = -torch.exp(self.A_log)                 # [d_state]
            A_bar = torch.exp(A * delta)               # [d_state]
            B = self.W_B(emb)                          # [d_state]
            B_bar = delta * B                          # [d_state]

            # Selective recurrent update: h = A_bar * h + B_bar
            self.h.mul_(A_bar).add_(B_bar)

        self.step_count += 1

    def query_causal(self, query_embedding: Tensor, top_k: int = 5) -> list[int]:
        # Pure SSM without episodic memory buffer cannot return past discrete event IDs
        return []

    def get_memory_slots(self) -> int:
        return 0  # Continuous state vector; zero explicit episodic slots
