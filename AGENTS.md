# ContextSpindle agent instructions

This repository develops ContextSpindle, a local, bounded, persistent context memory engine for AI agents. DiffHound is an optional PR review application built on the engine.

## Working in this repository

- Preserve the bounded hot/cold slot limits and the snapshot format unless a migration is designed and tested.
- Keep memory retrieval deterministic for a fixed snapshot, query, and configuration. Do not describe model-generated responses as deterministic.
- Keep historical benchmark results, paper titles, and failed experiments intact. Claims about latency, accuracy, memory, or token savings require the exact benchmark and conditions.
- Before a complex refactor, inspect current code and optionally recall relevant local constraints with `contextspindle recall "<topic>" 3` if the CLI is installed. The legacy `continuum-cli` command remains supported.
- Run relevant Rust and Python tests after changing implementation behavior. A local `cargo test` or `pytest` run is sufficient; `contextspindle run` is optional when recording a failure/fix pair is useful.
- Do not install a global CLI, change user IDE settings, or install Git hooks unless the task calls for integration setup.

## Local integration

```bash
cargo install --path crates/continuum-cli
contextspindle init .
contextspindle remember "RULE: <durable project constraint>"
contextspindle recall "<query>" 3
contextspindle mcp
```

`contextspindle init` currently writes `.continuum/memory.state` and `.continuum/config.json` so existing snapshots remain readable. A project-scoped MCP example is in [`.mcp.json`](.mcp.json). The advertised tools are `contextspindle_remember`, `contextspindle_recall`, and `contextspindle_stats`; old `continuum_*` tool calls are accepted during migration.

Read [the naming decision](docs/NAME-CHANGE.md) before changing package names, FFI symbols, snapshot paths, or published references.
