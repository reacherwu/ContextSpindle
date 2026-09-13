# Benchmark policy and TASK-001 harness specification

This document owns the benchmark standard, not model implementation. Changing a
threshold, task generator, metric, split, or measurement procedure requires a
benchmark review and a new versioned configuration; never change one after
inspecting a candidate result to make it look better.

## TASK-001: bounded temporal-state sanity benchmark

**Purpose.** Test whether a compact gated temporal state learns a local,
synthetic delayed dependency while retaining a bounded recurrent state. This is
not a test of long-term memory, retrieval, causality, revision, scaling, or
real-world usefulness.

The generator emits scalar symbols `x_t` in `{-1, +1}`. Its binary target at
time `t` is whether the symbol exactly `delay` events earlier was `+1`:
`y_t = 1[x_(t-delay) = +1]` for `t >= delay`. Earlier positions are excluded
from loss and metrics. Symbols are IID with equal probability, so a current
event-only or fixed-majority approach has expected accuracy and balanced
accuracy of 0.5. The generator uses only its named stream seed, never global or
model RNG state.

The v1 small-scale protocol is `benchmarks/task-001-small.yaml`:

| Item | Fixed v1 value |
| --- | --- |
| train / validation / test sequences | 2,048 / 512 / 512 |
| events per sequence | 64 |
| delayed dependency | 8 events |
| input / target | bipolar scalar event / delayed-symbol binary label |
| training | 20 epochs maximum; validation selects checkpoint |
| evaluation | one complete, held-out test pass; no test-time training |
| execution | CPU by default, batch size 64, float32 |

An implementation may expose the parameters, but a result named
`task-001-small-v1` must use these values. Different values require a distinct
`benchmark_id` and are **NOT DIRECTLY COMPARABLE** to v1.

### Required systems

Every direct comparison uses the same generator version, splits, train/
validation selection rule, seed matrix, precision, batch-size policy, sequence
handling, and measurement process. The candidate is the minimal gated temporal
state in `docs/ARCHITECTURE.md`. Its required reference is a parameter-free
**last-event reference** that predicts `x_(t-1)` as the delayed symbol. With
delay 8 on IID inputs, its expected accuracy is 0.5; it detects accidental
one-event shortcuts.

`benchmarks/baselines.yaml` lists future baseline families. All are currently
`not_yet_implemented`; report them as unavailable, never as invented numbers. A
candidate-only run is an implementation observation, not an advantage claim.
Before a baseline can be called directly comparable, its registry entry records
source URL, immutable revision, license, parameter count, training budget, and
protocol deviations.

### Seeds, selection, and repetitions

The canonical seed matrix is `[101, 202, 303]`. For each seed, deterministically
derive and log the named streams `model_init`, `train_data`, `validation_data`,
`test_data`, and `dataloader`; record the exact derivation algorithm in
`config.json`. Do not rely on a framework default.

Arbitrary exploratory seeds are allowed but labelled `exploratory` and cannot
support a conclusion. A v1 report includes all three canonical seed runs,
including failures. Hyperparameters are selected only using validation data. If
more than one configuration is tried, list all candidates and selection rule;
test each selected configuration once and retain every run.

### Fair resource and quality metrics

Record these per seed; aggregate only comparable completed canonical runs.

| Class | Required fields | Definition |
| --- | --- | --- |
| task quality | accuracy, balanced_accuracy, binary_cross_entropy, evaluated_tokens | Held-out eligible (`t >= delay`) tokens only. |
| model size | trainable_parameters, total_parameters, recurrent_state_elements, recurrent_state_bytes | State bytes are declared active footprint for one stream at recorded dtype, excluding weights and allocator cache. |
| training cost | training_wall_seconds, training_peak_rss_bytes, optimizer_steps, epochs_completed | Wall time brackets training loop only; RSS uses the stated profiler. |
| inference cost | warmup_sequences, timed_sequences, inference_wall_seconds, throughput_events_per_second, inference_peak_rss_bytes | Full sequences include state reset and forward passes, exclude generation and file I/O. |
| environment | device_requested, device_used, precision, batch_size, deterministic_mode | `device_used` is runtime-observed. |

Accuracy is primary. Balanced accuracy makes a changed label distribution
visible. Binary cross-entropy uses probabilities and must state its clipping
rule. Aggregates report `n`, mean, sample standard deviation (`n-1`), min, and
max. Do not aggregate across device types, precisions, batch sizes, generator
versions, or statuses. Timing is directly comparable only with an identical
machine fingerprint and measurement protocol; otherwise label it **NOT DIRECTLY
COMPARABLE** and present raw data.

### Measurement procedure

1. Resolve the versioned configuration and capture its SHA-256.
2. Capture code revision and package/runtime versions before execution.
3. Seed Python, NumPy, PyTorch CPU, and accelerator generators; enable and log
   deterministic mode and exceptions.
4. Generate splits from named streams and assert distinct sequence IDs/content
   hashes between splits.
5. Train under fixed budget and select a checkpoint using validation loss.
6. Evaluate held-out test data exactly once; execute the reference on identical
   test data.
7. Warm up, then measure with a monotonic clock; retain raw timing samples.
8. Validate `metrics.json` and `system.json` against schemas in
   `benchmarks/schemas/` before writing the immutable record.

Fail closed if a requested device is unavailable unless the configuration permits
fallback. A fallback can be an environment observation, not a direct comparison
with the requested-device result.

### Scope and interpretation

Passing establishes only that the component beats the stated shortcut on this
controlled local-delay task. It does not validate memory beyond the recurrent
state, causal reasoning, revision, scaling, or superiority over unimplemented
baseline families. Results at/below reference, unstable seeds, incomplete seed
matrices, missing provenance, or condition mismatches are negative or
inconclusive and must be retained.

## Unavailable hardware or non-runnable scale

Never silently substitute devices or omit a requested scale. Create a normal
record with `status: not_run` or `blocked`, `not_applicable` comparability, and
`unavailable_hardware` in `system.json`. Log requested device/scale, detected
hardware, detection command/API, timestamp, reason, CPU-fallback attempt, and
config hash. The report explicitly says no quality or performance result was
produced. This is feasibility evidence, not a failed model score.

See `docs/EXPERIMENTS.md` for the on-disk contract.
