# Use ContextSpindle across local Codex conversations

The repository-scoped `.mcp.json` only applies where that project configuration is loaded. For task continuity across **new local Codex conversations and different repositories on one machine**, install the optional personal integration:

```bash
python3 integrations/codex/install.py
```

Run this from a ContextSpindle source checkout. Requirements: Python 3.11+, Rust/Cargo, and the `codex` CLI. The installer builds `contextspindle` into an isolated directory beneath `${CODEX_HOME:-~/.codex}`, initializes a private workspace there, installs the bundled personal skill, appends one marked section to the existing global `AGENTS.md`, and registers a user-level MCP server. It preserves other `AGENTS.md` instructions and, if replacing a changed skill file, writes a dated backup beside it. Rerunning the installer is supported. To test with an already-built binary, pass `--binary /absolute/path/to/contextspindle`; `--skip-mcp` prepares the files without registering MCP.

The personal rule asks Codex to use the skill for substantive multi-step development, not every unrelated question. On a matching task, the skill searches the shared task ledger, creates or resumes the appropriate task, and checks a 2048 **UTF-8 byte** handoff before pausing. A new conversation must still *invoke* the tools; installing them does not silently capture all chats or make model outputs deterministic. The current user request takes priority over old ledger content.

Check the installation:

```bash
codex mcp get contextspindle
${CODEX_HOME:-$HOME/.codex}/skills/contextspindle-task-continuity/scripts/contextspindle task verify
${CODEX_HOME:-$HOME/.codex}/skills/contextspindle-task-continuity/scripts/contextspindle task inbox 10
```

The installer pre-approves only the task ledger's **read** MCP tools. Task writes retain normal Codex approval behavior. A read-only sandbox can recover existing tasks, but must not be used to create or update them. In workspace-write sessions, a shell invocation of the CLI wrapper may be blocked from writing the private ledger directory; use the MCP write tool with its approval flow, or explicitly grant that dedicated directory as a writable root if your policy permits. Do not broadly disable the sandbox.

The ledger lives in `${CODEX_HOME:-~/.codex}/contextspindle-workspace/.contextspindle/tasks/`. The optional retrieval snapshot lives separately in the same workspace under `.continuum/`. Missing or damaged retrieval data cannot erase tasks or cause task context to read another workspace's cache. The ledger does not sync to cloud storage: schedule protected off-device backups and practice restore using [the operations runbook](OPERATIONS.md) if multi-year recovery matters. Protect both the live workspace and backups; avoid storing secrets in tasks.
