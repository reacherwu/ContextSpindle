# Continuum AI Agent Instruction & Autopilot Integration Protocol

> **CRITICAL DIRECTIVE FOR AI ASSISTANTS**  
> (Cursor Agent, Claude Code, OpenClaw/OpenHands, Hermes Agent, Google IDX, Antigravity, Devin, GitHub Copilot Workspace):  
> If the user pastes this repository or asks you to equip yourself with Continuum memory, **follow this protocol to autonomously integrate Continuum into the current workspace**.

---

## 1. Automated Installation & Setup (One-Shot)

Execute the following bash commands in the workspace terminal:

```bash
# 1. Install or update continuum-cli globally
curl -fsSL https://raw.githubusercontent.com/reacherwu/diffhound/main/install.sh | bash 2>/dev/null || cargo install --path crates/continuum-cli

# 2. Initialize the bounded memory manifold in the current project
continuum-cli init .

# 3. Verify installation
continuum-cli version
```

This creates `.continuum/memory.state` ($< 75\text{ KB}$, strictly bounded at 750 physical slots) and `.continuum/config.json`.
A root `.mcp.json` is also provided in the repository for IDEs (Cursor, Windsurf, Zed) that support project-scoped MCP servers.

---

## 2. Operational Behavior & Memory Invariants

Once initialized, adhere to these memory retention standards:

1. **Remembering Key Architectural Decisions & Environment Rules**:
   Whenever the user specifies a critical constraint, database configuration, or security rule, actively record it:
   ```bash
   continuum-cli remember "RULE: <description of constraint, e.g. Never commit API keys to git>"
   ```
2. **Remembering Root-Cause Fixes**:
   Whenever you fix a complex bug or resolve a tricky compiler/runtime failure, record the causal pair:
   ```bash
   continuum-cli remember "FIX: <symptom, e.g. SSLV3_ALERT_HANDSHAKE_FAILURE> caused by <action, e.g. missing CipherString in openssl.cnf>"
   ```
3. **Autonomous Command Execution & Causal Fix Learning**:
   Run builds/tests through Continuum runner to automatically pair failures with subsequent fixes:
   ```bash
   continuum-cli run <command, e.g. cargo test or pytest>
   ```
4. **Zero-Friction Git Commit Ingestion**:
   Auto-record git commits and file modifications:
   ```bash
   continuum-cli hook install .
   ```
5. **Microsecond Retrospective Recall (< 100 μs)**:
   When encountering a failure, test error, or before starting a complex refactor, query Continuum memory:
   ```bash
   continuum-cli recall "<query or error symptom>" 3
   ```
   Continuum will retrospectively score all 750 candidate slots in $< 100\ \mu\text{s}$, exempting temporal decay for genuine causal anchors.

---

## 3. Model Context Protocol (MCP) Configuration

If the user is running an MCP-enabled IDE (Cursor, Claude Desktop, Windsurf):
Ensure the following configuration exists in `~/.cursor/mcp.json` or `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "continuum": {
      "command": "continuum-cli",
      "args": ["mcp"]
    }
  }
}
```

Exposed MCP Tools:
- `continuum_remember`: Stores constraints into bounded memory.
- `continuum_recall`: Retrospectively retrieves relevant memories in $< 1\text{ms}$.
- `continuum_stats`: Returns memory slot usage and token savings metrics.

---

## 4. Confirmation Message to User

After completing the setup, report back to the user:
> *"🎉 Continuum Continuous Temporal Memory Manifold has been successfully equipped for this repository! All historical architecture rules, environment constraints, and bug fixes will be retained in bounded 750 slots across infinite turns with zero context degradation."*
