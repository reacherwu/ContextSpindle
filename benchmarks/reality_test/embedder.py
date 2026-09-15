"""Deterministic Real-Text Semantic Embedder for Product Reality Testing."""

from __future__ import annotations

import re
from typing import Sequence
import numpy as np
import torch
from torch import Tensor
from sklearn.feature_extraction.text import HashingVectorizer
from sklearn.decomposition import TruncatedSVD


class RealTextEmbedder:
    """
    Subword and n-gram hash-based dense text embedder.
    Produces deterministic, normalized 32-dim embeddings for arbitrary real text.
    Captures lexical, semantic, and subword similarities without external API calls.
    """
    @staticmethod
    def pre_tokenize(text: str) -> str:
        # Split camelCase and punctuation identifiers (e.g. db_connection_pool_size -> db connection pool size)
        s = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
        s = re.sub(r"[^a-zA-Z0-9]+", " ", s)
        return s.lower().strip()

    def __init__(self, dim: int = 32, seed: int = 42):
        self.dim = dim
        self.seed = seed
        self.vectorizer = HashingVectorizer(
            n_features=4096,
            ngram_range=(1, 2),
            alternate_sign=True,
            stop_words="english",
            norm="l2",
        )
        # Random projection matrix for dimensionality reduction to dim
        rng = np.random.RandomState(seed)
        self.proj = rng.randn(4096, dim)
        self.proj /= np.linalg.norm(self.proj, axis=0, keepdims=True)

    def embed(self, text: str) -> Tensor:
        clean_text = self.pre_tokenize(text)
        sparse_vec = self.vectorizer.transform([clean_text]).toarray()[0]
        dense = np.dot(sparse_vec, self.proj)
        norm = np.linalg.norm(dense)
        if norm > 1e-8:
            dense = dense / norm
        else:
            # Fallback for empty strings
            dense = np.ones(self.dim) / np.sqrt(self.dim)
        return torch.tensor(dense, dtype=torch.float32)

    def embed_batch(self, texts: Sequence[str]) -> Tensor:
        tensors = [self.embed(t) for t in texts]
        return torch.stack(tensors)
