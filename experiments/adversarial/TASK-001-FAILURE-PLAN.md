# TASK-001 adversarial failure plan

**Scope:** RFC-0001 minimal gated temporal state only.  This plan neither
changes the model nor supplies a benchmark score.  A passing model must satisfy
these probes without a test-only code path or hidden event history.

## Runnable artifacts

- `tests/adversarial/test_task_001_failure_modes.py` tests only the public
  `TemporalState` contract.
- `experiments/adversarial/task_001_cases.py` is an independent seeded
  delayed-copy fixture and leakage-schema guard.
- `tests/adversarial/test_task_001_benchmark_guards.py` validates that fixture
  and its out-of-distribution (OOD) slices.

After the implementation and package exports land, run:

```bash
python -m pytest tests/adversarial -q
```

Run the same command on CPU for `float32` and `float64`.  MPS results, if
collected, are supplementary: they must identify device, PyTorch version, and
precision and must not replace the CPU gate.

## Contract probes and interpretation

| Risk | Probe | Required observation | Failure interpretation |
| --- | --- | --- | --- |
| event reordering / accidental pooling | apply `[-0.8, 0.45]` and its reverse with fixed asymmetric weights | final states differ | input order was ignored, sorted, pooled, or otherwise erased |
| future leakage | keep a three-event prefix fixed and replace the suffix | every prefix output is bit-identical | reverse/bidirectional lookahead or whole-sequence leakage |
| batch cross-talk | perturb one row's entire stream and initial state | untouched row's all states and final state are bit-identical | reduction, broadcasting, cache, or indexing mixes rows |
| hidden lifecycle state | interleave two caller-owned streams through one module | each equals its independent sequence result | module retains mutable stream state or resets implicitly |
| non-finite boundary | inject NaN, +Inf, and -Inf into input/state/sequence | documented `ValueError` or `RuntimeError` at the call | invalid values propagated silently |
| numerical extremes | use `float32` largest finite values with finite weights | returned states/final state remain finite | accepted finite input poisoned visible state |
| saturated gates | force `b_g=-20` then `b_g=20` | low gate retains prior state; high gate returns candidate (within `1e-6`) | interpolation equation, gate polarity, or diagnostics are wrong |
| boundedness | 1,024 events at high amplitude and finite initial states including `1.75` | `abs(h) <= max(abs(h0), 1) + 2e-6` (`f32`), `+2e-12` (`f64`) | recurrence does not preserve the stated convex bound |

Exact equality is deliberately used for causal-prefix, batch-isolation, and
stream-interleaving comparisons because the compared rows execute identical
operations.  Tolerances are used only where sigmoid saturation and
floating-point endpoint effects are intrinsic.

## Benchmark leakage and distribution-shift gate

The independent fixture has two contemporaneous inputs:

```text
x[t] = [signal_now[t], nuisance_now[t]]
target evaluated at t = signal_now[t-gap]
```

The schema guard rejects a fixture in which either feature at evaluation time
equals the delayed target.  It is a structural guard, not a claim that
correlation has been eliminated in every possible external generator.  The
benchmark adapter must preserve this alignment and log feature names, label
alignment, split seed, and gap for every run.

Report OOD outcomes separately; do not fold them into an IID aggregate:

1. **Longer gap:** train/evaluate IID at gap 3, then evaluate a frozen gap-9
   slice with no retraining or protocol change.
2. **Nuisance magnitude:** multiply the independent nuisance channel by 25 on
   a held-out slice while retaining signal encoding, labels, dimensions, and
   head/model weights.
3. **Seed holdout:** use a seed never selected after inspecting outcomes.  It
   is retained even if the model loses to the registered last-event reference.

For each slice, record accuracy (or the benchmark owner's frozen metric),
model/reference difference, seed, number of examples, gap, nuisance scale,
device, dtype, parameter count, and training checkpoint.  An OOD result is a
robustness diagnostic, not evidence for H-001 unless the Benchmark Agent
preregisters it as such.

## Entry and exit rules

- Do not run these as evidence until the engineering implementation is pinned
  to a commit and the Benchmark Agent freezes its adapter/protocol.
- A contract-probe failure blocks TASK-001 acceptance.  Preserve the failing
  seed, tensors, configuration, framework/device/dtype, traceback, and
  serialized parameter state under `experiments/results/`; do not tune the
  test or discard the run.
- A benchmark leakage failure invalidates the associated benchmark result and
  requires a newly versioned dataset/configuration; it cannot be repaired by
  reporting a favorable subset.
- A saturation or OOD degradation is not by itself an implementation defect.
  It must be reported as a limitation and compared under the same frozen
  protocol.

## Blocking findings for the owners

1. **No frozen benchmark adapter or metric exists yet.** The fixture guards
   data alignment, but cannot prove the benchmark's training/evaluation code
   uses it correctly.  The Benchmark Agent must define the adapter invocation,
   target index, metric, aggregate seed rule, and registered baseline before
   benchmark evidence can be accepted.
2. **The RFC demands finite outputs for finite input/state, but has no stated
   overflow policy for finite extreme affine preactivations.** The supplied
   probe requires finite returned state on an extreme case; Engineering should
   explicitly document whether it validates intermediates or relies on the
   saturating nonlinearities.  Silent non-finite diagnostics would violate the
   public finite-output contract.
3. **The RFC's exact initialization policy remains intentionally undecided.**
   This does not block correctness probes with hand-set weights, but it blocks
   reproducible performance interpretation until framework version, seed, and
   serialized parameters are recorded as required by RFC-0001.
