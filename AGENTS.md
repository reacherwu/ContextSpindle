# ContextSpindle agent instructions

This repository develops ContextSpindle, an agent task-continuity system. Its purpose is to preserve goals, task state, decisions, and resumable next actions across long conversations, interruptions, sessions, and years, while assembling relevant context within a token budget. PR review is not a product feature.

## Working in this repository

- Preserve the bounded hot/cold slot limits and the snapshot format unless a migration is designed and tested.
- Do not treat the bounded memory snapshot as the authoritative task record: eviction is allowed there. Durable task records need stable IDs, explicit lifecycle state, provenance, and recoverable storage.
- Before resuming an existing task, use `contextspindle task show <id>` or `contextspindle task context <id> 2048`; if the ID is unknown, search the task ledger. Record goal/next-action changes with `task update` rather than relying only on chat history.
- Follow [the agent task-continuity protocol](docs/AGENT-PROTOCOL.md) when using the task ledger. Refresh a task after a version conflict and record a resumable next action before switching away.
- Keep memory retrieval deterministic for a fixed snapshot, query, and configuration. Do not describe model-generated responses as deterministic.
- Keep historical benchmark results, paper titles, and failed experiments intact. Claims about latency, accuracy, memory, or token savings require the exact benchmark and conditions.
- Before a complex refactor, inspect current code and optionally recall relevant local constraints with `contextspindle recall "<topic>" 3` if the CLI is installed. The legacy `continuum-cli` command remains supported.
- Run relevant Rust and Python tests after changing implementation behavior. A local `cargo test` or `pytest` run is sufficient; `contextspindle run` is optional when recording a failure/fix pair is useful.
- Do not install a global CLI, change user IDE settings, or install Git hooks unless the task calls for integration setup.

## Local integration

```bash
cargo build --release --bin contextspindle
target/release/contextspindle init .
target/release/contextspindle task inbox 10
target/release/contextspindle task context <task-id> 2048
target/release/contextspindle mcp
```

`contextspindle init` writes `.contextspindle/tasks/` plus the compatible `.continuum/memory.state` and `.continuum/config.json`. A project-scoped MCP example is in [`.mcp.json`](.mcp.json). The advertised task tools cover create, update, show, list, inbox, search, context, history, children, verify, backup, and restore; bounded-cache tools `contextspindle_remember`, `contextspindle_recall`, and `contextspindle_stats` remain available. Old `continuum_*` tool calls are accepted during migration.

Read [the naming decision](docs/NAME-CHANGE.md) before changing package names, FFI symbols, snapshot paths, or published references.
