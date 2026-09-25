# Project-scoped Agent Integration

ContextSpindle is opt-in. An agent must explicitly write and read durable tasks; it cannot infer a complete task ledger from a private chat history. Use this prompt with an agent working in a checkout of this repository:

```text
Read AGENTS.md and docs/AGENT-PROTOCOL.md in this checkout. Do not install global software or edit IDE settings. Build the local ContextSpindle binary with `cargo build --release --bin contextspindle`, then run `target/release/contextspindle init .` if the workspace is not initialized. At the start of each task, inspect `task inbox` or `task search`, or use a task ID supplied by the user. Create a durable task with a goal and completion criteria if none exists. Record the next action, blockers, decisions, and evidence as work progresses. Before switching or stopping, update the task and run `task context <id> <budget>`. Treat `.continuum/` retrieval hints as optional; `.contextspindle/tasks/` is the source of truth. Never mark a task complete without checking its criteria and dependencies.
```

The project-scoped [`.mcp.json`](../.mcp.json) starts the checked-out MCP server through Cargo. An MCP client that supports this configuration can use the `contextspindle_task_*` tools. For other clients, configure an equivalent local command yourself; do not assume any IDE automatically detects or installs the server.

Run `contextspindle task verify` and create off-device backups with `contextspindle task backup <new-directory>`. The ledger is Git-ignored, so Git pushes do not preserve task history. See [the protocol](AGENT-PROTOCOL.md) for recovery, coordination, and budget limits.
