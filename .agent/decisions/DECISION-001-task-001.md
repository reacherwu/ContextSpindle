# DECISION-001 — TASK-001 implementation entry gate

- **Task:** TASK-001 — minimal gated Temporal State and first reproducible benchmark
- **Judge:** independent judge review
- **Date:** 2026-09-13
- **Decision:** **PASS — strictly scoped implementation may start**
- **Confidence:** High (0.86)
- **Decision boundary:** This is an entry decision for the RFC-defined module only.  It is not acceptance of the implementation, validation of H-001, or permission to claim a benchmark, memory, causal, scaling, novelty, or performance result.

## Evidence

1. [RFC-0001](../proposals/RFC-0001-temporal-state.md) supplies a concrete public API, exact six-tensor recurrence, parameter shapes/count, input/state validation boundary, finite-value rules, lifecycle semantics, invariants, and implementation acceptance criteria.  The permitted code scope is explicitly limited to `continuum/state/temporal_state.py`, necessary exports, and engineering-owned tests; it expressly excludes routers, event storage, causal features, and changes to benchmark definitions.
2. [TASK-001](../tasks/TASK-001.md) gives a bounded objective and a falsifiable local-delay hypothesis against a trivial last-event reference.  It does not treat the task as an ACM-wide evaluation.
3. [Benchmark policy](../../docs/BENCHMARKS.md) independently fixes the intended v1 task conditions, primary metric, reference, canonical seed matrix, resource measurements, comparability conditions, and negative-result policy.  Its scope statement correctly limits any eventual pass to the controlled local-delay task.
4. [Adversarial failure plan](../../experiments/adversarial/TASK-001-FAILURE-PLAN.md) probes ordering, causal-prefix isolation, batch isolation, caller-owned lifecycle, invalid numerical inputs, extreme finite values, gate saturation, boundedness, leakage, and OOD reporting.  The independently runnable fixture guard passed on this worktree: `python3 -m pytest tests/adversarial/test_task_001_benchmark_guards.py -q` → **3 passed**.
5. [Research log](../../docs/research/research_log.md) identifies material prior art and prevents unsupported novelty or transferred-performance claims.  The project constitution and decision rules also require retained negative results and independently owned evidence lanes.

## Strengths

- The implementation target is unusually well-bounded: caller-owned state prevents hidden stream history, the recurrence is directly testable with hand-set parameters, and no retrieval/causal functionality can enter by implication.
- The benchmark design recognizes the correct trivial shortcut control, reserves the standard to an independent owner, uses three named canonical seeds, and requires held-out evaluation, provenance, and resource reporting.
- The adversarial plan exercises the most important ways a small recurrent implementation could look successful while violating its contract, including temporal leakage and cross-stream contamination.
- The evidence documents the distinction between a conventional gated local state and claimed new long-context/ACM behavior.

## Weaknesses and blockers

1. **No implementation exists yet.** No public-contract, autograd, CPU/MPS, or reproducibility test can currently establish correctness.  The full adversarial contract suite is consequently not runnable until the module and exports land.
2. **The benchmark is specified but not yet executable/frozen as repository artifacts.** `docs/BENCHMARKS.md` names `benchmarks/task-001-small.yaml` and `benchmarks/schemas/`, but neither exists in this worktree.  There is no frozen adapter, registered executable last-event implementation, training/evaluation harness, metric/schema validator, or experiment record.  This blocks all benchmark evidence and any result-bearing acceptance decision, but does not require model engineering to modify benchmark standards.
3. **Initialization reproducibility remains incomplete.** RFC-0001 permits a documented PyTorch initialization policy to be adopted later, while requiring framework version, seed, and serialized parameters.  Engineering must make the resulting implementation/configuration serializable and loggable; performance interpretation is blocked until the benchmark record captures those fields.
4. **Finite extreme-input behavior needs an explicit implementation choice.** Finite inputs may overflow affine intermediates even where output nonlinearities are normally saturating.  The RFC and adversarial probe require finite returned diagnostics/state or a documented boundary failure; engineering must not let non-finite diagnostics silently escape.
5. **A size-matched conventional recurrent control is identified by the research/competitor material but is not part of the frozen small-v1 required systems.** This does not block the limited last-event sanity comparison, but it prevents framing a favorable result as evidence of an improved recurrent mechanism.

## Failure cases that must stop acceptance

- Any violation of the RFC API: invalid configuration/input/state acceptance, incorrect recurrence/diagnostics, implicit reset or retained history, batch interaction, prefix dependence on suffixes, broken gradients, or a state outside the stated bound.
- Failure of a CPU `float32` or `float64` adversarial contract probe; MPS evidence is supplementary and cannot replace the CPU gate.
- A benchmark adapter whose target alignment differs from the delayed-copy schema, whose inputs contain contemporaneous target leakage, or whose splits/seeds/configuration cannot be identified and reproduced.
- Missing canonical seed runs, test-set reuse, post-result protocol change, unavailable/mismatched reference conditions, missing provenance, or status/comparability conditions that prevent a direct comparison.
- Aggregate accuracy at or below the registered last-event reference, or failure of the benchmark's still-to-be-materialized confidence/seed rule.  Such an outcome falsifies or leaves H-001 inconclusive; it is not authorization to add memory modules or weaken the benchmark.

## Recommended action

Authorize Engineering to start **only** the RFC-0001 `TemporalState` implementation and its direct contract tests.  Engineering must not create or alter the benchmark generator, adapter, metric, baseline standard, thresholds, seed policy, experiment records, or broader ACM modules.

In parallel or after the implementation lands, the Benchmark owner must commit the referenced versioned configuration, schemas, executable adapter/reference, and a reproducible runner without changing the documented v1 policy; the Adversarial owner must run and preserve the full CPU contract results against the pinned implementation.  Return TASK-001 to Judge only with a pinned code revision, all acceptance/adversarial evidence, and complete canonical benchmark records.  Until then, report **no performance claim and no H-001 outcome**.
