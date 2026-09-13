"""Benchmark-owned guards for the frozen TASK-001 contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import torch

from benchmarks.records import validate_json, validate_record, write_json
from benchmarks.task_001 import (
    binary_metrics,
    canonical_json_sha256,
    generate_delayed_symbols,
    last_event_logits,
    load_protocol,
    named_stream_seeds,
)
from benchmarks.run_task_001 import TemporalStateAdapter, clone_checkpoint_state


ROOT = Path(__file__).parents[2]
PROTOCOL_PATH = ROOT / "benchmarks" / "task-001-small.yaml"


def test_frozen_protocol_has_documented_v1_values() -> None:
    protocol = load_protocol(PROTOCOL_PATH)
    assert protocol["benchmark_id"] == "task-001-small-v1"
    assert protocol["splits"] == {"train_sequences": 2048, "validation_sequences": 512, "test_sequences": 512}
    assert protocol["generator"]["sequence_length"] == 64
    assert protocol["generator"]["delay"] == 8
    assert protocol["seeds"]["canonical"] == [101, 202, 303]
    assert protocol["training"]["epochs_max"] == 20
    assert protocol["execution"]["device_requested"] == "cpu"


def test_named_streams_and_generator_are_reproducible_and_split_distinct() -> None:
    streams = named_stream_seeds(101)
    assert streams == named_stream_seeds(101)
    assert len(set(streams.values())) == len(streams)
    first = generate_delayed_symbols(sequence_count=4, sequence_length=16, delay=3, seed=streams["train_data"])
    rerun = generate_delayed_symbols(sequence_count=4, sequence_length=16, delay=3, seed=streams["train_data"])
    held_out = generate_delayed_symbols(sequence_count=4, sequence_length=16, delay=3, seed=streams["test_data"])
    torch.testing.assert_close(first.inputs, rerun.inputs, rtol=0, atol=0)
    torch.testing.assert_close(first.labels, rerun.labels, rtol=0, atol=0)
    assert first.content_sha256 != held_out.content_sha256
    assert torch.equal(first.labels[:, 3:], (first.inputs[:, :-3, 0] > 0).float())
    assert not torch.equal(first.labels[:, 3:], (first.inputs[:, 3:, 0] > 0).float())


def test_last_event_reference_is_registered_and_not_a_delayed_oracle() -> None:
    batch = generate_delayed_symbols(sequence_count=512, sequence_length=64, delay=8, seed=17)
    metrics = binary_metrics(last_event_logits(batch.inputs), batch.labels, delay=batch.delay)
    assert metrics["evaluated_tokens"] == 512 * 56
    # IID symbols make a one-event shortcut near chance, while a delayed oracle
    # would be exactly one.  Wide bounds avoid turning a random test into a score gate.
    assert 0.42 < metrics["accuracy"] < 0.58
    assert 0.42 < metrics["balanced_accuracy"] < 0.58


def test_schema_validator_accepts_completed_record_and_rejects_missing_quality(tmp_path: Path) -> None:
    protocol = load_protocol(PROTOCOL_PATH); configuration_hash = canonical_json_sha256(protocol)
    config = {"benchmark_id": "task-001-small-v1", "version": 1, "config_sha256": configuration_hash, "protocol": protocol, "seed": 101, "streams": named_stream_seeds(101), "generator_revision": "task-001-delayed-symbol-v1", "code_revision": "abc", "system_id": "test", "created_at": "2026-09-13T00:00:00Z"}
    system = {"recorded_at": "2026-09-13T00:00:00Z", "os": "test", "cpu": "test", "ram_bytes": 1, "accelerators": [], "python_version": "test", "torch_version": "test", "device_requested": "cpu", "device_used": "cpu", "precision": "float32", "deterministic_mode": True}
    metrics = {"status": "completed", "comparability": "direct", "benchmark_id": "task-001-small-v1", "seed": 101, "recorded_at": "2026-09-13T00:00:00Z", "quality": {"accuracy": .5, "balanced_accuracy": .5, "binary_cross_entropy": .7, "evaluated_tokens": 56}, "model": {"trainable_parameters": 1, "total_parameters": 1, "recurrent_state_elements": 1, "recurrent_state_bytes": 4}, "training": {"training_wall_seconds": 1., "training_peak_rss_bytes": 1, "optimizer_steps": 1, "epochs_completed": 1}, "inference": {"warmup_sequences": 1, "timed_sequences": 1, "inference_wall_seconds": 1., "throughput_events_per_second": 1., "inference_peak_rss_bytes": 1, "raw_timing_seconds": [1.]}, "validation_selection": {"selected_epoch": 1, "selected_validation_binary_cross_entropy": .7}, "reference": {"name": "last-event-reference-v1", "quality": {}}}
    for name, payload in (("config", config), ("system", system), ("metrics", metrics)):
        validate_json(name, payload); write_json(tmp_path / f"{name}.json", payload)
    (tmp_path / "stdout.log").write_text("test\n")
    validate_record(tmp_path)
    incomplete = dict(metrics); incomplete.pop("quality")
    with pytest.raises(Exception):
        validate_json("metrics", incomplete)


def test_checkpoint_clone_round_trips_actual_temporal_state_extra_state() -> None:
    """Regression: TemporalState serializes config as a non-tensor extra state."""
    torch.manual_seed(23)
    model = TemporalStateAdapter(hidden_size=3, gate_bias_init=0.25)
    inputs = torch.tensor([[[1.0], [-1.0], [1.0]]])
    expected = model(inputs).detach().clone()
    checkpoint = clone_checkpoint_state(model.state_dict())

    assert checkpoint["state._extra_state"] == model.state.get_extra_state()
    assert checkpoint["state._extra_state"] is not model.state_dict()["state._extra_state"]
    with torch.no_grad():
        for parameter in model.parameters():
            parameter.add_(1.0)
    model.load_state_dict(checkpoint)
    torch.testing.assert_close(model(inputs), expected)
