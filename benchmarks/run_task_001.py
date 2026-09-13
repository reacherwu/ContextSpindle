"""Executable, reproducible trainer/evaluator for the frozen TASK-001 protocol.

It intentionally owns the linear prediction head and metric implementation but
does not implement or mutate ``TemporalState``.  The model is imported only at
run time through its RFC-defined public API.
"""

from __future__ import annotations

import argparse
import platform
import resource
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from benchmarks.records import sha256_file, validate_record, write_json
from benchmarks.task_001 import (
    GENERATOR_REVISION,
    binary_metrics,
    canonical_json_sha256,
    generate_delayed_symbols,
    last_event_logits,
    load_protocol,
    named_stream_seeds,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def git_revision(root: Path) -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


class TemporalStateAdapter(nn.Module):
    """Benchmark-owned head around the stable architecture-owned state API."""

    def __init__(self, *, hidden_size: int, gate_bias_init: float) -> None:
        super().__init__()
        try:
            from continuum.state.temporal_state import TemporalState, TemporalStateConfig
        except ImportError as error:
            raise RuntimeError("TemporalState implementation is required before TASK-001 can run") from error
        self.state = TemporalState(TemporalStateConfig(input_size=1, hidden_size=hidden_size, gate_bias_init=gate_bias_init))
        self.head = nn.Linear(hidden_size, 1)

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        states, _ = self.state.forward_sequence(inputs)
        return self.head(states).squeeze(-1)


def _peak_rss_bytes() -> int:
    # ru_maxrss is bytes on macOS and KiB on Linux; current RSS avoids ambiguity.
    current = psutil.Process().memory_info().rss
    maximum = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if platform.system() != "Darwin":
        maximum *= 1024
    return max(current, maximum)


def _system_record(*, protocol: dict[str, Any], device_used: str) -> dict[str, Any]:
    requested = protocol["execution"]["device_requested"]
    accelerators: list[str] = []
    if torch.cuda.is_available():
        accelerators.extend([f"cuda:{i}:{torch.cuda.get_device_name(i)}" for i in range(torch.cuda.device_count())])
    if torch.backends.mps.is_available():
        accelerators.append("mps")
    return {
        "recorded_at": utc_now(), "os": platform.platform(), "cpu": platform.processor() or platform.machine(),
        "ram_bytes": psutil.virtual_memory().total, "accelerators": accelerators,
        "python_version": sys.version, "torch_version": torch.__version__,
        "device_requested": requested, "device_used": device_used,
        "precision": protocol["execution"]["precision"], "deterministic_mode": protocol["execution"]["deterministic_mode"],
        "rss_profiler": "max(psutil.Process().memory_info().rss, resource.getrusage(RUSAGE_SELF).ru_maxrss) normalized to bytes",
    }


def _evaluate(model: nn.Module, batch, *, batch_size: int, device: torch.device) -> tuple[dict[str, Any], list[float]]:
    model.eval(); data = TensorDataset(batch.inputs, batch.labels)
    loader = DataLoader(data, batch_size=batch_size, shuffle=False)
    logits_parts: list[torch.Tensor] = []; samples: list[float] = []
    with torch.no_grad():
        for inputs, _labels in loader:
            started = time.perf_counter(); logits_parts.append(model(inputs.to(device)).cpu()); samples.append(time.perf_counter() - started)
    return binary_metrics(torch.cat(logits_parts), batch.labels, delay=batch.delay), samples


def run(*, config_path: Path, output: Path, seed: int, requested_device: str | None = None) -> Path:
    protocol = load_protocol(config_path)
    if seed not in protocol["seeds"]["canonical"]:
        raise ValueError("non-canonical seed: create an explicitly exploratory record instead")
    config_hash = canonical_json_sha256(protocol); streams = named_stream_seeds(seed)
    device_name = requested_device or protocol["execution"]["device_requested"]
    if device_name != "cpu":
        raise RuntimeError(f"requested device {device_name!r} is unavailable under frozen CPU v1 protocol")
    device = torch.device("cpu"); torch.use_deterministic_algorithms(True); torch.manual_seed(streams["model_init"])
    generator = protocol["generator"]; splits = protocol["splits"]
    train = generate_delayed_symbols(sequence_count=splits["train_sequences"], sequence_length=generator["sequence_length"], delay=generator["delay"], seed=streams["train_data"])
    validation = generate_delayed_symbols(sequence_count=splits["validation_sequences"], sequence_length=generator["sequence_length"], delay=generator["delay"], seed=streams["validation_data"])
    test = generate_delayed_symbols(sequence_count=splits["test_sequences"], sequence_length=generator["sequence_length"], delay=generator["delay"], seed=streams["test_data"])
    model = TemporalStateAdapter(hidden_size=protocol["model"]["hidden_size"], gate_bias_init=protocol["model"]["gate_bias_init"]).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=protocol["training"]["learning_rate"])
    loader_generator = torch.Generator().manual_seed(streams["dataloader"])
    loader = DataLoader(TensorDataset(train.inputs, train.labels), batch_size=protocol["execution"]["batch_size"], shuffle=True, generator=loader_generator)
    loss_fn = nn.BCEWithLogitsLoss(); best_loss = float("inf"); best_epoch = 0; best_state = None; steps = 0
    train_started = time.perf_counter()
    for epoch in range(1, protocol["training"]["epochs_max"] + 1):
        model.train()
        for inputs, labels in loader:
            optimizer.zero_grad(set_to_none=True); logits = model(inputs.to(device))[:, generator["delay"]:]
            loss = loss_fn(logits, labels[:, generator["delay"]:].to(device)); loss.backward(); optimizer.step(); steps += 1
        validation_metrics, _ = _evaluate(model, validation, batch_size=protocol["execution"]["batch_size"], device=device)
        if validation_metrics["binary_cross_entropy"] < best_loss:
            best_loss = float(validation_metrics["binary_cross_entropy"]); best_epoch = epoch
            best_state = {name: value.detach().cpu().clone() for name, value in model.state_dict().items()}
    training_seconds = time.perf_counter() - train_started
    assert best_state is not None
    model.load_state_dict(best_state)
    warmup = test.inputs[:protocol["execution"]["warmup_sequences"]]
    with torch.no_grad(): model(warmup.to(device))
    quality, raw_timings = _evaluate(model, test, batch_size=protocol["execution"]["batch_size"], device=device)
    inference_seconds = sum(raw_timings); timed_sequences = test.inputs.shape[0]
    reference_quality = binary_metrics(last_event_logits(test.inputs), test.labels, delay=test.delay)
    experiment_id = f"{protocol['benchmark_id']}--temporal-state--seed-{seed}--{utc_now().replace(':', '').replace('-', '')}"
    record_dir = output / experiment_id; record_dir.mkdir(parents=True, exist_ok=False); (record_dir / "artifacts").mkdir()
    root = config_path.resolve().parents[1]
    config = {"benchmark_id": protocol["benchmark_id"], "version": protocol["version"], "config_sha256": config_hash, "protocol": protocol, "seed": seed, "streams": streams, "generator_revision": GENERATOR_REVISION, "code_revision": git_revision(root), "system_id": platform.node() or "unknown", "created_at": utc_now(), "split_sha256": {"train": train.content_sha256, "validation": validation.content_sha256, "test": test.content_sha256}}
    state_path = record_dir / "artifacts" / "selected-model.pt"; torch.save(best_state, state_path)
    parameter_count = sum(parameter.numel() for parameter in model.parameters()); state_elements = protocol["model"]["hidden_size"]
    metrics = {"status": "completed", "comparability": "direct", "benchmark_id": protocol["benchmark_id"], "seed": seed, "recorded_at": utc_now(), "quality": quality, "model": {"trainable_parameters": parameter_count, "total_parameters": parameter_count, "recurrent_state_elements": state_elements, "recurrent_state_bytes": state_elements * 4}, "training": {"training_wall_seconds": training_seconds, "training_peak_rss_bytes": _peak_rss_bytes(), "optimizer_steps": steps, "epochs_completed": protocol["training"]["epochs_max"]}, "inference": {"warmup_sequences": protocol["execution"]["warmup_sequences"], "timed_sequences": timed_sequences, "inference_wall_seconds": inference_seconds, "throughput_events_per_second": (timed_sequences * generator["sequence_length"] / inference_seconds), "inference_peak_rss_bytes": _peak_rss_bytes(), "raw_timing_seconds": raw_timings}, "validation_selection": {"selected_epoch": best_epoch, "selected_validation_binary_cross_entropy": best_loss}, "reference": {"name": "last-event-reference-v1", "quality": reference_quality}}
    system = _system_record(protocol=protocol, device_used=str(device))
    write_json(record_dir / "config.json", config); write_json(record_dir / "metrics.json", metrics); write_json(record_dir / "system.json", system)
    write_json(record_dir / "artifacts" / "manifest.json", [{"path": "artifacts/selected-model.pt", "sha256": sha256_file(state_path), "bytes": state_path.stat().st_size, "role": "validation-selected checkpoint"}])
    (record_dir / "stdout.log").write_text("TASK-001 runner completed; stdout/stderr captured by CLI invocation.\n", encoding="utf-8")
    (record_dir / "report.md").write_text(f"# {experiment_id}\n\nStatus: completed. All canonical runs must be retained; this record alone supports no aggregate conclusion.\n", encoding="utf-8")
    validate_record(record_dir)
    return record_dir


def write_noncompleted_record(*, config_path: Path, output: Path, seed: int, status: str, reason: str) -> Path:
    """Retain a blocked/failed invocation rather than silently discarding it."""
    protocol = load_protocol(config_path)
    streams = named_stream_seeds(seed)
    record_id = f"{protocol['benchmark_id']}--temporal-state--seed-{seed}--{utc_now().replace(':', '').replace('-', '')}"
    record_dir = output / record_id
    record_dir.mkdir(parents=True, exist_ok=False)
    root = config_path.resolve().parents[1]
    config = {"benchmark_id": protocol["benchmark_id"], "version": protocol["version"], "config_sha256": canonical_json_sha256(protocol), "protocol": protocol, "seed": seed, "streams": streams, "generator_revision": GENERATOR_REVISION, "code_revision": git_revision(root), "system_id": platform.node() or "unknown", "created_at": utc_now()}
    metrics = {"status": status, "comparability": "not_applicable", "benchmark_id": protocol["benchmark_id"], "seed": seed, "recorded_at": utc_now(), "reason": reason}
    write_json(record_dir / "config.json", config)
    write_json(record_dir / "metrics.json", metrics)
    write_json(record_dir / "system.json", _system_record(protocol=protocol, device_used="unavailable"))
    (record_dir / "stdout.log").write_text(f"invocation: {' '.join(sys.argv)}\n{status}: {reason}\n", encoding="utf-8")
    (record_dir / "report.md").write_text(f"# {record_id}\n\nStatus: {status}. No quality or performance result was produced.\n\nReason: {reason}\n", encoding="utf-8")
    validate_record(record_dir)
    return record_dir


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--config", type=Path, default=Path("benchmarks/task-001-small.yaml")); parser.add_argument("--output", type=Path, default=Path("experiments/results")); parser.add_argument("--seed", type=int, required=True); parser.add_argument("--device")
    args = parser.parse_args()
    try:
        print(run(config_path=args.config, output=args.output, seed=args.seed, requested_device=args.device))
    except Exception as error:
        status = "blocked" if "TemporalState implementation is required" in str(error) else "failed"
        record = write_noncompleted_record(config_path=args.config, output=args.output, seed=args.seed, status=status, reason=f"{type(error).__name__}: {error}")
        print(record, file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
