"""Deterministic delayed-symbol data and reference for TASK-001.

This module deliberately does not import Continuum model code.  Its generator,
target alignment, reference, and metrics remain independently testable.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
import yaml


GENERATOR_REVISION = "task-001-delayed-symbol-v1"
STREAM_NAMES = ("model_init", "train_data", "validation_data", "test_data", "dataloader")


@dataclass(frozen=True)
class DelayedSymbolBatch:
    """One complete split; labels are evaluated only at indices ``delay:``."""

    inputs: torch.Tensor  # [N, T, 1], elements in {-1, +1}
    labels: torch.Tensor  # [N, T], labels before delay are intentionally unused
    delay: int
    content_sha256: str

    @property
    def eligible_labels(self) -> torch.Tensor:
        return self.labels[:, self.delay :]


def load_protocol(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        protocol = yaml.safe_load(handle)
    if not isinstance(protocol, dict):
        raise ValueError("benchmark protocol must be a mapping")
    return protocol


def canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def derive_stream_seed(root_seed: int, stream: str) -> int:
    """Implement the derivation algorithm pinned in task-001-small.yaml."""
    if stream not in STREAM_NAMES:
        raise ValueError(f"unknown TASK-001 stream: {stream}")
    digest = hashlib.sha256(f"{root_seed}:{stream}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=False)


def named_stream_seeds(root_seed: int) -> dict[str, int]:
    return {name: derive_stream_seed(root_seed, name) for name in STREAM_NAMES}


def _tensor_sha256(tensor: torch.Tensor) -> str:
    return hashlib.sha256(tensor.detach().cpu().contiguous().numpy().tobytes()).hexdigest()


def generate_delayed_symbols(*, sequence_count: int, sequence_length: int, delay: int, seed: int) -> DelayedSymbolBatch:
    """Generate IID bipolar inputs and an explicitly delayed binary target."""
    if sequence_count <= 0 or sequence_length <= delay or delay <= 0:
        raise ValueError("require sequence_count > 0, delay > 0, and sequence_length > delay")
    generator = torch.Generator(device="cpu").manual_seed(seed)
    symbols = torch.randint(0, 2, (sequence_count, sequence_length), generator=generator, dtype=torch.int64)
    inputs = (symbols.to(torch.float32) * 2.0 - 1.0).unsqueeze(-1)
    labels = torch.zeros((sequence_count, sequence_length), dtype=torch.float32)
    labels[:, delay:] = (inputs[:, :-delay, 0] > 0).to(torch.float32)
    return DelayedSymbolBatch(inputs=inputs, labels=labels, delay=delay, content_sha256=_tensor_sha256(torch.cat((inputs[..., 0], labels), dim=1)))


def last_event_logits(inputs: torch.Tensor) -> torch.Tensor:
    """Parameter-free registered reference: predict the immediately prior symbol."""
    if inputs.ndim != 3 or inputs.shape[-1] != 1:
        raise ValueError("inputs must have shape [N, T, 1]")
    logits = torch.zeros(inputs.shape[:2], dtype=inputs.dtype, device=inputs.device)
    logits[:, 1:] = inputs[:, :-1, 0]
    return logits


def binary_metrics(logits: torch.Tensor, labels: torch.Tensor, *, delay: int) -> dict[str, float | int]:
    """Compute all preregistered quality metrics on eligible held-out tokens."""
    if logits.shape != labels.shape or logits.ndim != 2:
        raise ValueError("logits and labels must be equally shaped [N, T] tensors")
    if not 0 < delay < logits.shape[1]:
        raise ValueError("delay must select a nonempty suffix")
    selected_logits, selected_labels = logits[:, delay:], labels[:, delay:]
    probabilities = torch.sigmoid(selected_logits).clamp(min=1e-7, max=1.0 - 1e-7)
    prediction = probabilities >= 0.5
    truth = selected_labels >= 0.5
    accuracy = (prediction == truth).to(torch.float32).mean().item()
    positives, negatives = truth.sum().item(), (~truth).sum().item()
    recall_positive = ((prediction & truth).sum().item() / positives) if positives else 0.0
    recall_negative = (((~prediction) & (~truth)).sum().item() / negatives) if negatives else 0.0
    bce = torch.nn.functional.binary_cross_entropy(probabilities, selected_labels).item()
    return {
        "accuracy": accuracy,
        "balanced_accuracy": (recall_positive + recall_negative) / 2.0,
        "binary_cross_entropy": bce,
        "evaluated_tokens": int(selected_labels.numel()),
        "probability_clipping": "[1e-7, 1-1e-7] after sigmoid",
    }


def assert_no_contemporaneous_target_leak(batch: DelayedSymbolBatch) -> None:
    """Guard the contract: task input at t cannot equal the label evaluated at t."""
    if torch.equal((batch.inputs[:, batch.delay :, 0] > 0).to(torch.float32), batch.eligible_labels):
        raise AssertionError("target leaked into contemporaneous input feature")
