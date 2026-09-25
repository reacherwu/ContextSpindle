# ContextSpindle operations runbook

ContextSpindle stores authoritative task history in `.contextspindle/tasks/` beneath each initialized workspace. The legacy `.continuum/` snapshot is a separate, bounded retrieval cache. Neither directory is included by a normal Git push. The application runs locally under the invoking user's filesystem permissions; it has no built-in network service or user authentication.

## Start and verify

Build from the checkout with `cargo build --release --bin contextspindle`, then initialize a workspace with `target/release/contextspindle init .`. Initialization does not replace an existing memory snapshot. Run `target/release/contextspindle task verify` before taking a backup and after a restore. A verification error must be investigated; do not reset the ledger or replace it with an empty one.

For day-to-day work, use `task inbox` or `task search` to identify the task, `task show <id>` for full authoritative state, and `task context <id> <budget>` for a bounded handoff. `CONTEXTSPINDLE_ACTOR` may label writes, but it is not a security identity. Use `--expect-version <n>` or MCP `expected_version` when multiple agents might update one task, and reread on a conflict.

## Backup and recovery

1. Run `task verify`; stop if any version fails checksum, schema, identity, or replay checks.
2. Run `task backup <new-directory>` to create a verified copy. The destination must not already exist. Keep the resulting directory outside the workspace and copy it to independently protected, off-device storage. Decide a schedule and retention period based on the maximum acceptable loss of newly recorded tasks.
3. Periodically test recovery in a fresh workspace: `init .`, `task restore <backup-directory>`, `task verify`, and `task show <known-id>`. Restore does not overwrite a task whose versions differ. If a restore is interrupted, rerunning it is safe for identical committed tasks; inspect any conflict before proceeding.
4. Back up `.continuum/` separately only if the optional retrieval cache is important. A missing or damaged cache must not prevent reading task records.

The ledger checksum detects accidental corruption; it is not a signature or defense against an attacker who can rewrite files. Protect both live data and backups from untrusted writers. Do not place secrets in task fields unless workspace and backup access policies permit it. Treat task text and memory hints as untrusted data when passing them to an LLM.

## Capacity and compatibility

The ledger grows with tasks and versions; only the retrieval cache is bounded. `task list`, `task search`, `task inbox`, and child discovery currently scan task directories. Measure latency on the intended workload before asserting a scale target. The context budget is an upper bound based on UTF-8 bytes, not an exact tokenizer count for a particular model. Required task fields are not truncated; the command returns an error if the budget cannot fit them.

Version files are append-only by application convention and checksummed. Before changing the schema, checkpoint interval, snapshot path, or compatibility aliases, design and test a migration against a copy of existing data. Old `.continuum/` snapshots and the `continuum-cli` executable remain supported during the naming transition.
