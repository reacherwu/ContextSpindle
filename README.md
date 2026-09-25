# ContextSpindle

Persistent, deterministic context memory for AI agents.

ContextSpindle stores selected decisions, constraints, and root-cause fixes across agent sessions. Its bounded Rust memory engine supports local ingestion, snapshot persistence, and repeatable retrieval. The memory store is a source of context for an agent; it does not make the agent's language-model output deterministic.

**DiffHound** is an application built on the memory engine. It checks a code change against retained fixes and architecture constraints. The memory engine is the primary project; PR review is one use case.

## Quick start

Build the memory CLI from this checkout:

```bash
cargo install --path crates/continuum-cli
contextspindle init .
contextspindle remember "RULE: Never commit API keys"
contextspindle recall "API key policy" 3
contextspindle stats
```

For an MCP client, use the project configuration in [`.mcp.json`](.mcp.json) or run `contextspindle mcp`. The CLI writes local state in `.continuum/` for snapshot compatibility with earlier releases. The `continuum-cli` command remains available during migration.

For the optional PR guard:

```bash
cargo install --path crates/diffhound-cli
diffhound review --base origin/main --fail-on-regression
```

## What is preserved

- A bounded active memory with configurable hot and cold capacity.
- Local snapshots that survive process restarts.
- Explicit `remember`, `recall`, `run`, `hook`, and MCP interfaces.
- A deterministic retrieval algorithm for a fixed state, query, and configuration.

The memory is selective. Evicted information may be unavailable, and retrieval quality depends on the stream and query. See [research and benchmark documents](docs/BENCHMARKS.md) for measured behavior and limitations; historical experimental records are retained under their original names.

## Naming and compatibility

The former name **Continuum** appears in the Python import path, Rust crate names, snapshot directory, older MCP tool names, published paper title, and historical experiment records. Those identifiers remain readable during the transition. New integrations should use the ContextSpindle command and MCP server key. See [the naming decision](docs/NAME-CHANGE.md) for the checked names and migration boundary.

[中文说明](README_CN.md) · [License](LICENSE) · [DiffHound GitHub Action](action.yml)
