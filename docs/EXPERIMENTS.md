# Experiment logging contract

Each experiment is an append-only directory at
`experiments/results/<experiment_id>/`. Once completed, failed, blocked, or
not-run, it is immutable. Corrections create a new directory, record
`supersedes_experiment_id`, and give a reason. Raw artifacts may be Git-ignored
for size, but their manifest, hashes, summaries, and status remain archived.

## Required files

| Path | Required for | Contract |
| --- | --- | --- |
| `config.json` | all records | Fully resolved config, SHA-256, benchmark ID/version, generator revision, seed derivation, system ID, and code revision. |
| `metrics.json` | all records | Status, comparability, outcomes or non-run reason, resources, raw timing, validation selection. Validate against metrics schema. |
| `system.json` | all records | OS, CPU, RAM, accelerators, versions, requested/observed device, precision, deterministic settings, unavailable-hardware block. Validate against system schema. |
| `stdout.log` | executed records | Unedited stdout/stderr including command and warnings. |
| `report.md` | all records | Factual status, conditions, limitations, hashes, and statement that no runs were excluded. |
| `artifacts/manifest.json` | executed records with artifacts | Relative path, SHA-256, bytes, and role for each checkpoint, prediction, trace, or retained artifact. |

Use RFC 3339 UTC timestamps and byte counts. An ID identifies one system and
one seed; recommended form is
`task-001-small-v1--<system-id>--seed-<seed>--<utc-timestamp>`. Aggregates are
separate records listing source experiment IDs and performing no hidden re-runs.

## Status and comparability

| Status | Meaning |
| --- | --- |
| `completed` | Execution and schema validation succeeded; quality/resource values exist. |
| `failed` | Execution began but produced no valid result; preserve error and partial evidence. |
| `blocked` | A prerequisite/resource prevents a meaningful run. |
| `not_run` | An intentional non-execution, such as unsupported hardware or absent baseline. |
| `exploratory` | Non-canonical development result; cannot contribute to v1 conclusion. |

Comparability is `direct`, `not_direct`, or `not_applicable`. `direct` requires
identical config hash, generator revision, split hashes, canonical seed policy,
device-used fingerprint, precision, batch size, training budget, and measurement
protocol. `not_direct` includes factual mismatch reasons. `not_applicable` is
for no-result records.

For unavailable hardware, use `not_run`/`blocked`, `not_applicable`, a
structured hardware block in `system.json`, and no fabricated zeroes/null quality
metrics. For an unimplemented baseline, name the unavailable registry entry and
version in that record.

## Integrity and reporting rules

- Record every attempted canonical seed; no outcome-based deletion.
- Keep original values in JSON; round only Markdown presentation.
- Do not overwrite an evaluated checkpoint; manifest hash, selected epoch, and
  validation score are part of the result.
- Include split content hashes and code revision to expose leakage or generator
  changes.
- Include invocation but redact credentials and secret environment variables.
- “Not directly comparable” is never a ranking, winner, or superiority claim.

Schemas in `benchmarks/schemas/` define the machine-readable contract.
`benchmarks/task-001-small.yaml` is the human-editable source; the fully
resolved per-run `config.json` is authoritative.
