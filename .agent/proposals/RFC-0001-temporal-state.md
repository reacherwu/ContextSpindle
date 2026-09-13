# RFC-0001: Minimal Gated Temporal State for TASK-001

**Status:** proposed — requires Architecture, Benchmark, Adversarial, and
Judge review before implementation is accepted.

**Decision owner:** Architecture review

## Problem

Continuum needs a small, falsifiable first component for processing an ordered
event stream. The first component must test local temporal retention without
quietly introducing event storage, retrieval, a causal graph, or an
unbounded-history claim. TASK-001 asks for this component and a reproducible
small benchmark, while reserving benchmark standards for their independent
owner.

## Current limitation

The repository specifies only the scalar recurrence. It does not define the
shape contract, event ordering, initialization, diagnostics, configuration
surface, invalid-input behavior, or equivalence between one-step and sequence
execution. Those omissions would permit materially different implementations
and make a result hard to reproduce or diagnose.

## Proposed solution

Implement a `TemporalState` PyTorch module with exactly one recurrent state
and the following public contract. Names are normative for the initial
implementation; the module may expose ordinary PyTorch parameter inspection in
addition to this contract.

```python
@dataclass(frozen=True)
class TemporalStateConfig:
    input_size: int
    hidden_size: int
    candidate_activation: Literal["tanh"] = "tanh"
    initial_state: Literal["zeros"] = "zeros"
    gate_bias_init: float = 0.0

@dataclass
class TemporalStateStep:
    state: Tensor      # [B, H]
    gate: Tensor       # [B, H]
    candidate: Tensor  # [B, H]

class TemporalState(nn.Module):
    def __init__(self, config: TemporalStateConfig) -> None: ...
    def initial_state(self, batch_size: int, *, device=None, dtype=None) -> Tensor: ...
    def step(self, x_t: Tensor, state: Tensor) -> TemporalStateStep: ...
    def forward_sequence(
        self, x: Tensor, initial_state: Tensor | None = None
    ) -> tuple[Tensor, Tensor]: ...
```

### Configuration and parameterization

`input_size = D` and `hidden_size = H` are positive Python integers. The
initial implementation accepts only `candidate_activation="tanh"` and
`initial_state="zeros"`; unsupported values must fail at construction rather
than silently selecting another behavior. `gate_bias_init` is a finite real
number used only to initialize `b_g`; it must be captured in the serialized
module configuration for reproducibility. There is no dropout, normalization,
learned initial state, masking, timestamp feature, memory capacity, retrieval
policy, or implicit truncation configuration in this RFC.

The module has precisely these trainable tensors:

| parameter | shape |
| --- | --- |
| `W_g`, `W_c` | `[H, D]` |
| `U_g`, `U_c` | `[H, H]` |
| `b_g`, `b_c` | `[H]` |

Initialization for weights and `b_c` must use the repository's documented
PyTorch initialization policy when one is adopted. Until then, a run must log
the framework version, global seed, and exact serialized parameter state; no
claim may depend on an unstated initializer. `b_g` is initialized to the
configured `gate_bias_init` exactly.

### Input, state, and output semantics

`step(x_t, state)` requires finite, floating-point, rank-2 tensors on the same
device and with the same dtype as each other **and** as the module parameters:

- `x_t` has shape `[B, D]`.
- `state` has shape `[B, H]`.
- `B` is positive. `D` and `H` must match the configuration.

It returns a `TemporalStateStep` with finite tensors `state`, `gate`, and
`candidate`, all shape `[B, H]`, preserving device and dtype. Shape mismatch,
non-floating input, device/dtype mismatch, non-positive batch size, or a
non-finite input/state is a `ValueError` (or a documented equivalent
`RuntimeError`) and must never be coerced, padded, detached, or repaired.

`initial_state(B, device, dtype)` returns zeros `[B, H]` with the requested
device/dtype after validating a positive `B` and a floating dtype. If either
keyword is omitted, that property defaults to the first module parameter's
device/dtype. It is the only reset operation. The module owns weights but never
a mutable stream state: two callers can safely carry independent state tensors
through the same module.

`forward_sequence(x, initial_state=None)` requires a finite floating rank-3
tensor `[B, T, D]`, on the module parameter device/dtype, with `B > 0` and
`T >= 0`. If omitted, `initial_state` is the zero state on `x`'s device and
dtype. If supplied, it follows the `step` state contract. It returns `(states,
final_state)`, where `states` is `[B,T,H]` and `final_state` is `[B,H]`. For
`T=0`, `states` is empty along its temporal dimension and `final_state` equals
the supplied/zero initial state. It need not return per-step diagnostics;
callers requiring them use `step`.

Events are processed in the supplied order only. The component treats an event
as its encoded `x_t`; event identifiers, timestamps, and metadata belong to
the caller/encoder. There is no sorting, deduplication, clock interpretation,
or automatic reset. Reordering nonidentical events is expected to change the
result. Autograd connectivity is preserved: the module never calls `detach`;
truncated backpropagation is a caller training-loop decision.

## Mathematical formulation

For a batch row, let `x_t ∈ R^D`, `h_(t-1) ∈ R^H`, and use the configured
parameters above. At every accepted event:

\[
g_t = \sigma(W_g x_t + U_g h_{t-1} + b_g),
\]
\[
c_t = \tanh(W_c x_t + U_c h_{t-1} + b_c),
\]
\[
h_t = (1-g_t) \odot h_{t-1} + g_t \odot c_t.
\]

All operations are element-wise across the `H` coordinates after affine
projections, and batch rows have no interaction. `TemporalStateStep.gate` is
`g_t`; `candidate` is `c_t`; `state` is `h_t`.

The gate lies in `(0,1)` and the candidate lies in `(-1,1)` in real arithmetic.
Thus each coordinate of `h_t` is a convex combination of its previous value
and a value in `[-1,1]`. Consequently:

\[
\lVert h_t \rVert_\infty \leq \max(\lVert h_0 \rVert_\infty, 1).
\]

With required zero initialization, `||h_t||∞ ≤ 1`. Floating-point roundoff may
produce a negligible endpoint deviation; tests should use a documented dtype-
appropriate tolerance rather than demand exact endpoint equality.

## Invariants

1. **Bounded active state:** each live stream retains exactly `H` state scalars
   per batch row, independent of elapsed sequence length `T`; parameters are
   independent of `T`.
2. **No hidden history:** neither the module nor a returned state contains an
   event list, IDs, timestamps, retrieval index, causal relation, or mutable
   internal stream cache.
3. **Causal stream processing:** `h_t` depends only on `(x_0, …, x_t, h_0)`.
   It cannot depend on later inputs during a left-to-right call.
4. **Batch independence:** changing row `j` cannot change the output for row
   `i != j`, given identical row `i` input and initial state.
5. **Step/sequence equivalence:** for identical parameters, input, and initial
   state, `forward_sequence` produces exactly the same operation ordering and
   tensor results as repeated `step` calls, subject only to the chosen dtype's
   normal equality/tolerance policy.
6. **Explicit lifecycle:** initialization/reset happens only through
   `initial_state`; every transition requires caller-provided prior state.
7. **Finite-value boundary:** invalid numerical inputs fail at the public API
   boundary rather than allowing a silent non-finite state to propagate.

These are state semantics, not claims that the component has useful long-range
memory, causal knowledge, or a particular benchmark advantage.

## Implementation impact

The implementation scope is limited to `continuum/state/temporal_state.py`,
its package exports as necessary, and tests owned by engineering/adversarial
roles. The caller must supply the encoder and any prediction head. The module
must use ordinary PyTorch tensor operations so it works on the project's
available CPU and MPS environments; device-specific optimization is out of
scope. This RFC authorizes no memory router, stored event record, benchmark
harness, baseline, dataset, metric, or result change.

## Expected benefit and falsifiable hypothesis

**Hypothesis H-001:** On the independently specified, seeded small
temporal-gap/local-dependency task, a trained compact gated state with a fixed
`H` can retain enough local synthetic signal to outperform the registered
trivial last-event reference under the benchmark's declared aggregate metric
and protocol.

**Falsifier:** H-001 fails if the preregistered aggregate comparison does not
exceed that reference, if the confidence/seed rule in the benchmark protocol is
not satisfied, or if a correctness/reproducibility gate below fails. A failure
requires diagnosis or redesign; it does not authorize adding memory modules or
changing the benchmark standard to recover a favorable result.

## Potential failure

The state may simply forget signal beyond a short gap, overfit one generator,
or gain apparent performance from an accidental feature leak. Gate saturation
can stall adaptation or erase useful state. Poor initialization or unstable
optimization can obscure the capacity question. Fixed-width state may be less
useful than a last-event reference on the declared task. Numerical divergence,
device-specific differences, malformed shapes, and caller lifecycle mistakes
are separate implementation failures, not evidence for or against H-001.

## Acceptance criteria

Architecture review may recommend implementation only when the following are
testable in the engineering change:

1. Construction rejects invalid dimensions, unsupported enum values, and a
   non-finite `gate_bias_init`; parameter shapes and the trainable parameter
   count `2HD + 2H² + 2H` match the configuration.
2. `initial_state` is zero, `[B,H]`, caller-requested device/dtype, and does
   not share mutable stream state with another call.
3. A hand-set small parameter/input example matches the three equations above
   and returns the corresponding `gate` and `candidate`.
4. `forward_sequence` matches repeated `step`, including the `T=0` case, for a
   supplied nonzero initial state and for default zero initialization.
5. Batch independence, output shapes, device/dtype preservation, and autograd
   gradients to input and all six parameters are verified.
6. Invalid rank, shape, dtype, device, and non-finite input/state cases fail
   loudly and deterministically according to the published exception contract.
7. A boundedness check on finite synthetic sequences confirms the stated
   `L∞` bound within a declared floating-point tolerance.
8. The benchmark owner can invoke the model through a stable, documented
   adapter without changing benchmark definitions, and a fixed seed rerun
   records identical configuration and a reproducibility outcome.

## Benchmark plan

This section is a handoff request, not a benchmark standard. The Benchmark
Agent independently owns the dataset generator, train/evaluation split,
baseline implementation, metric, aggregation, seed count, statistical rule,
hardware reporting, and frozen configuration. The architecture-side plan is:

1. Evaluate only the stated local temporal-gap/local-dependency question using
   a fixed-width state and a registered trivial last-event reference.
2. Record the exact `TemporalStateConfig`, model/head parameter counts,
   optimizer and training budget, seeds, framework/device/precision, wall-clock
   latency/throughput method, and peak-memory measurement method.
3. Run all preregistered seeds and retain every run, including failed or
   unfavorable ones. Label comparisons with mismatched budgets or conditions
   **NOT DIRECTLY COMPARABLE** as required by repository policy.
4. Publish no superiority claim from a single seed, an unregistered reference,
   or a benchmark altered after seeing model outcomes.

The requested evidence is an aggregate result versus the benchmark-owned
last-event reference plus a diagnostic by temporal gap. It can support H-001
only; it cannot support a long-context, causal, or ACM-wide claim.

## Ablation plan

The initial ablation set must isolate the recurrence's contribution without
adding modules:

| ID | variant | purpose |
| --- | --- | --- |
| A0 | registered last-event reference | task floor/reference |
| A1 | no recurrent carry (`h_(t-1)=0` at each step) | separates current-event signal from temporal carry |
| A2 | fixed interpolation gate (non-learned, declared value) | tests whether learned gating matters |
| A3 | proposed learned gate and candidate | proposed component |

The Benchmark Agent may reject or refine these variants before freezing the
protocol. All variants must use the same declared encoder/head capacity and
training/evaluation budget where applicable; deviations are reported rather
than normalized away.

## Adversarial tests

The Adversarial Agent independently owns failure tests. Requested probes are:

1. **Order probe:** swap two nonidentical events and verify that a carefully
   selected parameter/input case changes the state; detect accidental pooling
   or sorting.
2. **Future-leak probe:** alter suffix events while holding the prefix fixed;
   prefix states must be unchanged.
3. **Batch-isolation probe:** perturb one batch row; every other row's outputs
   must remain unchanged.
4. **Lifecycle probe:** interleave two streams through one module with
   caller-owned states; neither stream may contaminate the other. Verify that
   reset is explicit rather than implicit at a timestamp or sequence boundary.
5. **Numerical-boundary probe:** NaN/Inf, wrong rank/shape, incompatible
   device/dtype, empty batch, and extreme finite values must either meet the
   published finite output contract or fail at the stated boundary; none may
   silently create a persistent invalid state.
6. **Saturation/retention probe:** construct gates near zero and near one to
   verify the stated interpolation behavior and expose vanishing-update or
   overwrite regimes.
7. **Leakage probe for the harness:** ensure target information is not present
   in contemporaneous input features when the declared task requires temporal
   retention. This is evaluated by the independent benchmark/adversarial roles.

An adversarial failure is retained as evidence. Engineering may fix a contract
violation but may not weaken the probe or alter its benchmark conditions.

## Decision

**Recommendation: CONDITIONAL GO.** The minimal component is sufficiently
specified to implement, but TASK-001 is not approved and H-001 is unvalidated.
Proceed only to an implementation review gate after the Benchmark Agent freezes
the small-task protocol and the Adversarial Agent accepts (or records) the
contract probes. The Judge should return `PASS` only with reproducible,
independently reviewed evidence; otherwise return `FAIL`, `REDESIGN`, or
`INSUFFICIENT EVIDENCE` under the repository decision rules.
