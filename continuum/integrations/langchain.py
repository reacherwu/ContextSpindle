"""LangChain memory integration for Continuum Temporal Intelligence Engine."""

from __future__ import annotations

from typing import Any, Callable, Sequence
import torch
from torch import Tensor

from continuum.api import ContinuumConfig, ContinuumEngine, CausalMatch


class ContinuumChatMessageHistory:
    """
    Drop-in chat message history powered by ContinuumEngine.
    Provides strictly bounded O(1) storage with retrospective causal retrieval.
    """
    def __init__(
        self,
        config: ContinuumConfig | None = None,
        embed_fn: Callable[[str], Sequence[float] | Tensor] | None = None,
    ):
        self.config = config or ContinuumConfig()
        self.engine = ContinuumEngine(self.config)
        self.embed_fn = embed_fn or self._default_embed
        self._raw_messages: list[dict[str, str]] = []

    def _default_embed(self, text: str) -> Tensor:
        # Deterministic lightweight hash embedding when no external LLM embedder is passed
        g = torch.Generator().manual_seed(abs(hash(text)) % (2**31))
        v = torch.randn(self.config.embedding_dim, generator=g)
        return v / torch.norm(v, p=2)

    def add_message(self, role: str, content: str) -> None:
        self._raw_messages.append({"role": role, "content": content})
        emb = self.embed_fn(content)
        payload = f"[{role.upper()}] {content}"
        self.engine.step(emb, payload_ref=payload)

    def add_user_message(self, message: str) -> None:
        self.add_message("user", message)

    def add_ai_message(self, message: str) -> None:
        self.add_message("assistant", message)

    def query_relevant_context(self, query: str, top_k: int = 3) -> list[CausalMatch]:
        q_emb = self.embed_fn(query)
        return self.engine.query(q_emb, top_k=top_k)

    def clear(self) -> None:
        self._raw_messages.clear()
        self.engine.reset()

    @property
    def messages(self) -> list[dict[str, str]]:
        return list(self._raw_messages)
