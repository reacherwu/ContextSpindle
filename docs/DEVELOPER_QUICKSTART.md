# ContextSpindle developer quickstart

ContextSpindle provides local, persistent context memory for AI agents. The Rust engine holds a bounded active set; the CLI stores its snapshot on disk.

## Build and initialize

```bash
git clone https://github.com/reacherwu/diffhound.git
cd diffhound
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
      "command": "contextspindle",
      "args": ["mcp"]
    }
  }
}
```

The MCP tools are `contextspindle_remember`, `contextspindle_recall`, and `contextspindle_stats`. Older `continuum_*` calls still work.

## Optional PR review

```bash
cargo install --path crates/diffhound-cli
diffhound review --base origin/main --fail-on-regression
```

See [the naming decision](NAME-CHANGE.md) for compatibility boundaries and [benchmark policy](BENCHMARKS.md) for evidence standards.
