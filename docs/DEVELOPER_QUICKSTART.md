# ContextSpindle developer quickstart

ContextSpindle provides local, persistent context memory for AI agents. The Rust engine holds a bounded active set; the CLI stores its snapshot on disk.

Durable tasks are stored separately in `.contextspindle/tasks/`. Use `contextspindle task create <goal> --criteria <criteria>`, `task update <id> --next <action>`, and `task context <id> 2048` to resume work with bounded context. Run `task verify` and `task backup <new-directory>` regularly; restore from a verified backup with `task restore <backup-directory>` in a new workspace.

## Build and initialize

```bash
cargo install --path crates/continuum-cli
contextspindle version
contextspindle init .
```

The snapshot is currently `.continuum/memory.state`. The old path is retained to read earlier data.

## Use memory

```bash
contextspindle remember "RULE: Never commit API keys"
contextspindle recall "API key policy" 3
contextspindle stats
```

Retrieval is deterministic for a fixed snapshot, query, and configuration. A bounded memory cannot guarantee that every historical event is still present. Inspect current project files and user instructions before acting on recalled context.

## Connect an MCP client

The repository's [`.mcp.json`](../.mcp.json) shows the project-scoped configuration:

```json
{
  "mcpServers": {
    "contextspindle": {
      "command": "cargo",
      "args": ["run", "--release", "--quiet", "--bin", "contextspindle", "--", "mcp"]
    }
  }
}
```

The MCP tools include `contextspindle_task_create`, `contextspindle_task_update`, `contextspindle_task_context`, `contextspindle_task_inbox`, `contextspindle_task_search`, `contextspindle_task_verify`, `contextspindle_task_backup`, and `contextspindle_task_restore`, plus the bounded-cache tools `contextspindle_remember`, `contextspindle_recall`, and `contextspindle_stats`. Older `continuum_*` calls still work.

See [the naming decision](NAME-CHANGE.md) for compatibility boundaries and [benchmark policy](BENCHMARKS.md) for evidence standards.
