# ContextSpindle

Durable task continuity and token-efficient context for AI agents.

ContextSpindle's product goal is to let an agent resume the right task quickly even after long conversations, unrelated intervening tasks, or years away. It must preserve each task's goal, completion criteria, state, decisions, dependencies, and next action in durable records, then assemble only relevant context within a token budget. Its existing bounded Rust memory engine provides selective, repeatable retrieval, but is not itself a lossless task ledger. Retrieval determinism does not imply deterministic language-model output.

The CLI and MCP server now expose a durable, append-only task ledger and task-aware context assembly. The older `remember`/`recall` interface remains a bounded retrieval cache, not the source of truth for tasks. See [the product definition](docs/PRODUCT-SCOPE.md).

Agents should follow [the task-continuity protocol](docs/AGENT-PROTOCOL.md) at the start and end of work. No integration can preserve a task that was never entered into the ledger.

For backup, restore, access control, and capacity planning, use the [operations runbook](docs/OPERATIONS.md).

## Quick start

Build the product CLI from this checkout:

```bash
cargo install --path crates/continuum-cli
contextspindle init .
contextspindle remember "RULE: Never commit API keys"
contextspindle recall "API key policy" 3
contextspindle stats
```

Create and resume a task:

```bash
contextspindle task create "Ship the release" --criteria "Tests pass and release is published"
contextspindle task update <task-id> --status active --next "Run final tests" --expect-version 1
contextspindle task inbox 10
contextspindle task context <task-id> 2048
contextspindle task search "release" 10
contextspindle task verify
contextspindle task backup /path/to/new-backup-directory
```

Task records live in `.contextspindle/tasks/` as checksummed, append-only version files. This directory is Git-ignored; pushing the repository does not back up your tasks. `task restore <backup-directory>` imports a verified backup into a new workspace without overwriting divergent tasks. Back up that directory off-device for long-term survival. Context budgets use a conservative UTF-8 byte ceiling as a token upper-bound proxy; this is not a model-specific tokenizer count. Required goal/state/next-action fields are never silently truncated: a too-small budget returns an error. Optional information is explicitly counted when omitted.

`task list [offset] [limit]` and `task history <id> [from-version] [limit]` are paginated. Inbox and search return bounded summaries; use `task show` or `task context` for the full selected task.

For retry-safe creation, pass a stable `--idempotency-key` (or MCP `idempotency_key`). Repeating the same request returns the existing task; reusing the key with different goals or criteria fails.

For a blocked task, set `--status blocked --blocker "what is missing"`. Add durable evidence references with `--evidence <path-or-URL>`. Clear the blocker before marking a task done.

For an MCP client, use the project configuration in [`.mcp.json`](.mcp.json) (which runs the checked-out Rust project) or run `contextspindle mcp` after installation. The CLI writes bounded memory state in `.continuum/` for snapshot compatibility with earlier releases. The `continuum-cli` command remains available during migration.

## What is preserved

- A bounded active memory with configurable hot and cold capacity.
- Local snapshots that survive process restarts.
- Explicit `remember`, `recall`, `run`, `hook`, and MCP interfaces.
- A deterministic retrieval algorithm for a fixed state, query, and configuration.

The memory is selective. Evicted information may be unavailable, and retrieval quality depends on the stream and query. See [research and benchmark documents](docs/BENCHMARKS.md) for measured behavior and limitations; historical experimental records are retained under their original names.

## Naming and compatibility

The former name **Continuum** appears in the Python import path, Rust crate names, snapshot directory, older MCP tool names, published paper title, and historical experiment records. Those identifiers remain readable during the transition. New integrations should use the ContextSpindle command and MCP server key. See [the naming decision](docs/NAME-CHANGE.md) for the checked names and migration boundary.

[中文说明](README_CN.md) · [License](LICENSE)
