# S7 — Stale / cross-task evidence gate

**Threat:** Evidence logged against an older completion criteria, or copied from another task, can still be used to mark a revised (or foreign) task `done`. The done gate historically checked blocker emptiness, non-empty criteria, and finished dependencies — not whether evidence is bound to the **current** task id and criteria text.

**Fix (minimal):** When `--evidence` is logged, store a backwards-compatible bound record that includes `task_id` and `criteria_hash` (SHA-256 of criteria UTF-8 at log time). Marking `status=done` requires at least one evidence record whose `task_id` matches this task and whose `criteria_hash` matches the **current** criteria. Legacy plain-string evidence still loads but does **not** satisfy the done gate.

## Pass / fail criteria (written before coding)

### S7a — criteria changed after evidence logged

1. Create task `T` with criteria `C1`.
2. Log evidence `E` while criteria is still `C1` (bound at log time to `T.id` + `sha256(C1)`).
3. Update criteria to `C2` (different text). Record a decision in the same update (required by existing API: *"Changing goal or completion criteria requires a recorded decision"*).
4. Attempt `--status done` with `E` still attached and blocker clear.

| Outcome | Meaning |
| --- | --- |
| **PASS (gate works)** | Update to done is **rejected** because evidence is bound to C1 hash ≠ current C2 hash. |
| **FAIL (gate missing)** | Done is **accepted**. |

### S7b — foreign-task evidence

1. Create tasks `T_a` and `T_b` with their own criteria.
2. Log evidence on `T_a` (bound to `T_a` id + `T_a` criteria hash).
3. Attach that same bound evidence record (the stored `evidence://v1/...` string that claims `T_a`'s id) onto `T_b`, then attempt to mark `T_b` done (blocker clear, criteria present).

| Outcome | Meaning |
| --- | --- |
| **PASS (gate works)** | `T_b` cannot be marked done using `T_a`'s evidence (task id mismatch and/or hash mismatch). |
| **FAIL (gate missing)** | `T_b` becomes done with foreign evidence. |

**Note:** Re-logging the *same payload text* as a fresh `--evidence` on `T_b` intentionally rebinds to `T_b` + current `T_b` criteria. That is a new attestation, not foreign evidence. S7b targets copying a **pre-bound** record that still claims another task's id.

## Expected vs actual

### Baseline (before fix)

| Case | Expected if gate missing | Actual |
| --- | --- | --- |
| S7a | FAIL — done accepted with stale evidence | **accepted** (FAIL — gate missing); wall 151 ms |
| S7b | FAIL — done accepted with foreign evidence | **accepted** (FAIL — gate missing); see baseline JSON |

### After fix

| Case | Expected if gate works | Actual |
| --- | --- | --- |
| S7a | PASS — done rejected (stale criteria hash) | **rejected** — `Evidence is missing or stale relative to current completion criteria` |
| S7b | PASS — done rejected (task id mismatch) | **rejected** — `Evidence task id mismatch` |

Human summary: `benchmarks/results/s7-stale-evidence.md`.

## Reproduce

```bash
# One-command harness (integration test; prints JSON summary)
cargo test -p continuum-cli s7_stale_evidence -- --nocapture

# Unit coverage of the same scenarios (library Store API)
cargo test -p continuum-cli s7a_stale_criteria -- --nocapture
cargo test -p continuum-cli s7b_foreign_task -- --nocapture
```

Optional: set `S7_RESULTS_PATH=/path/to/out.json` when running the integration test to write the JSON artifact.

## Evidence encoding

Bound records use the prefix `evidence://v1/` followed by a JSON object:

```json
{"task_id":"<id>","criteria_hash":"<sha256 hex of criteria UTF-8>","payload":"<caller text>"}
```

Plain legacy strings remain readable in history/context but never satisfy the done gate.

## Limitations

- Hash covers **criteria text only** (not goal, notes, or external artifact bytes).
- Not cryptographic authentication of external artifacts or actors (actor labels remain provenance).
- Unbound legacy evidence does not satisfy done; callers must re-log evidence after the upgrade (or after criteria changes).
- Copying a bound record via `--evidence` preserves the claimed binding so the done gate can reject foreign ids; fresh unbound payload text is rebound to the target task.
