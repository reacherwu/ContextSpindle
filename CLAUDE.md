# ContextSpindle instructions for Claude

Follow [`AGENTS.md`](AGENTS.md) and [`docs/AGENT-PROTOCOL.md`](docs/AGENT-PROTOCOL.md). ContextSpindle's purpose is to preserve task goals and next actions across long contexts, interruptions, unrelated tasks, and sessions. `.contextspindle/tasks/` is the durable source of truth. `.continuum/` is a bounded retrieval cache and may lose old hints.

On resumption, call `contextspindle_task_context` with the task ID if available; otherwise use `contextspindle_task_inbox` and `contextspindle_task_search`. Create a new task only when none matches. Record changed next actions, decisions, blockers, and evidence through `contextspindle_task_update`; use `expected_version` for coordination. Before stopping or switching tasks, write a resumable next action. A task can be marked done only after criteria and dependencies are satisfied and its blocker is clear.

Use the checked-out CLI or project-scoped `.mcp.json`; do not install a global binary, Git hook, or IDE configuration unless explicitly requested. Run `cargo test --workspace` and relevant Python tests after implementation changes. Preserve historical benchmark records and the legacy crate/snapshot names until a tested migration is designed.
