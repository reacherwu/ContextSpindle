# The "One-Prompt" Universal AI IDE Autopilot Integration

> **The Zero-Friction Experience**:  
> You don't need to configure terminal environments or manually edit JSON files. Simply copy and paste the prompt below directly into the chat window of **Cursor, Claude Code, Windsurf, Google Project IDX, OpenClaw, Hermes Agent, or Codex**.

---

## 📋 Copy & Paste Prompt for Any AI IDE

```text
Please read the integration protocol from https://github.com/reacherwu/diffhound (specifically AGENTS.md) and autonomously equip yourself with the Continuum Bounded Memory Engine for this project:

1. `curl -fsSL https://raw.githubusercontent.com/reacherwu/diffhound/main/install.sh | bash 2>/dev/null || cargo install --path crates/continuum-cli`
2. `continuum-cli init .`

Once installed, actively use `continuum remember` to store our architectural constraints and bug resolutions, and use `continuum recall` to retrieve past context in < 100 microseconds. Confirm when ready.
```

---

## 🤖 Platform-Specific Autonomous Actions

When your AI assistant receives the prompt above, it autonomously performs the following steps depending on the environment:

### 1. ⚡ Cursor IDE (Composer / Chat / Agent)
- **Auto-Rule Detection**: Cursor automatically discovers `.cursorrules` in the repository root.
- **Workspace MCP Server**: Cursor 0.40+ automatically detects the root `.mcp.json` file configuring `continuum-cli mcp`.
- **Command Integration**: The Cursor Agent runs terminal commands directly to execute `continuum-cli init .` and retain lifetime memory.

### 2. 🤖 Claude Code (Anthropic CLI Agent)
- Runs `curl -fsSL https://.../install.sh | bash` inside Claude Code's terminal bash tool.
- Registers the Continuum MCP server via:
  ```bash
  claude mcp add continuum continuum-cli mcp
  ```
- Continuously invokes `continuum_remember` and `continuum_recall` during long multi-file refactoring runs.

### 3. 🌐 Google Project IDX / Cloud Web IDEs
- Automatically installs in the cloud virtual machine terminal.
- Persists state in `<workspace>/.continuum/memory.state` across browser refreshes and cloud container reboots.

### 4. 🌪️ Windsurf (Cascade Agent)
- Automatically recognizes the root `.mcp.json` file.
- Cascade accesses `continuum_remember`, `continuum_recall`, and `continuum_stats` as native tools.

### 5. 🦾 Hermes Agent / OpenClaw / OpenHands
- Uses native shell tool calling to run:
  ```bash
  continuum remember "RULE: ..."
  continuum recall "<symptom or constraint>" 3
  ```
- Memory is strictly bounded at 750 slots (< 75 KB), ensuring agent trajectory logs never cause context window exhaustion.

### 6. 💻 OpenAI Codex / GitHub Copilot Workspace
- Pre-loads architectural memories into repo context prompts on every run using `continuum recall`.

---

## 🔒 Memory Guarantees

1. **Strictly Physical $O(K)$ Boundedness**: 250 Hot working slots + 500 Cold candidate slots = 750 slots (< 75 KB). Zero RAM leaks, zero heap bloat over infinite turns.
2. **Subspace Diversity Deduplication**: Redundant alert storms collapse into single slots; rare, life-critical constraints are protected forever.
3. **Decay Exemption for Causal Anchors**: Retrospective causal scoring exempts temporal decay for true root causes, defeating recent distracting chatter.
4. **100% Pure Native Rust**: Zero external crate dependencies, sub-100 microsecond retrieval latency.
