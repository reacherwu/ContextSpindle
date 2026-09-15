# Continuum: Developer Rapid Onboarding & Quickstart Guide (60 Seconds)

> **What is Continuum?**  
> Continuum is an ultra-fast, deterministic $O(K)$ bounded memory engine for autonomous coding agents, developers, and AIOps systems. Implemented in 100% pure native Rust, it slashes cloud token bills by **96.8%**, runs retrospective causal queries in **< 100 microseconds**, and permanently remembers critical architecture constraints across thousands of steps.
>
> 📄 **Official CERN Zenodo Academic Paper**: [https://doi.org/10.5281/zenodo.22765180](https://doi.org/10.5281/zenodo.22765180)

---

## 1. 10-Second Instant Installation

Run the one-line installer in your terminal:

```bash
curl -fsSL https://get.continuum-core.org/install.sh | bash
```

*(Or build locally from source: `cargo install --path crates/continuum-cli`)*

Verify installation:
```bash
continuum-cli version
# Output: continuum 0.1.0 (native rust core)
```

---

## 2. Interactive Quickstart in Any Project (30 Seconds)

### Step 1: Initialize Bounded Memory in Your Repository
Inside any Git repository or code project:
```bash
cd my-project
continuum-cli init
```
This creates a local `.continuum/` directory storing your bounded 750-slot state snapshot (`memory.state`) and configuration (`config.json`). Total disk footprint is $< 75\text{ KB}$.

### Step 2: Store Critical Rules & Architectural Decisions
Whenever you set up an environment rule, database setting, or security policy:
```bash
continuum-cli remember "PostgreSQL connection pool max_connections=50 idle_timeout=10s. Do not change without DBA review."
continuum-cli remember "Strict compliance rule: never commit plaintext API keys or .env files to Git."
```

### Step 3: Retrieve Past Causal Memories in Microseconds
Whenever a test fails or you need historical context:
```bash
continuum-cli recall "database connection timeout" 2
```
*Output in < 50 μs:*
```text
Retrieved 1 causal memories (< 100 μs native Rust):
#1: [Score: 0.8540] PostgreSQL connection pool max_connections=50 idle_timeout=10s...
```

---

## 3. One-Click IDE Integration via Model Context Protocol (MCP)

Continuum features a **native, zero-dependency Model Context Protocol (MCP) server** built directly into the Rust binary. Any modern AI editor (Cursor, Claude Desktop, Claude Code, Windsurf) can connect in 10 seconds.

### For Cursor IDE:
Open `Cursor Settings` -> `Features` -> `MCP Servers` -> `Add New MCP Server`, or edit `~/.cursor/mcp.json`:
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

### For Claude Desktop:
Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%/Claude/claude_desktop_config.json` (Windows):
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

### For Claude Code CLI:
```bash
claude mcp add continuum continuum-cli mcp
```

### What Happens Once Connected?
Your AI coding assistant automatically gains three native tools:
1. **`continuum_remember`**: Passively or actively commits key architectural rules and debugging findings into your local 750-slot bounded manifold.
2. **`continuum_recall`**: When errors or edge-cases occur, the AI retrospectively queries your history in $< 100\ \mu\text{s}$ to find the true root cause.
3. **`continuum_stats`**: Monitors active memory slots and verifies 96.8% token savings.

---

## 4. Why Developers Love Continuum (The Token Economics)

| Feature | Raw Context Appending | With Continuum Native Engine |
| :--- | :--- | :--- |
| **Token Payload per Query** | Up to 150,000 tokens | **~2,500 tokens (96.8% reduction)** |
| **5-Minute Cache Invalidation** | Flushed every 5 mins of pause | **Immune (Local state persistent)** |
| **Query Latency** | 12 ~ 18 seconds | **< 100 microseconds (0.0001s)** |
| **Attention Quality** | Degrades (*Lost-in-the-Middle*) | **100% Causal Recall (Rank #1)** |
| **Monthly Developer Bill** | ~$150 USD (¥1,080 RMB) | **~$4.50 USD (¥32 RMB)** |

---

## 5. Pricing & Continuum Pro Upgrade ($15/mo)

Check your real-time savings directly from the CLI:
```bash
continuum-cli upgrade
```

### Free Community Tier (100% Free / Open Core)
- Full native Rust $O(K)$ bounded memory engine (750 physical slots).
- Microsecond retrospective causal recall.
- Single repository local state.

### Pro Tier ($15.00 USD / Month)
- **Cross-Device Cloud Sync**: Seamlessly share memory manifolds across your MacBook, desktop, and cloud devboxes.
- **Multi-Repo Workspaces**: Manage unlimited project states simultaneously.
- **Automated Git Hook**: Auto-ingests git commits, pull requests, and failed test logs.
- **Team Memory Sharing**: Share organizational architecture constraints across all team members' AI assistants.

To subscribe: [https://continuum-core.org/pro](https://continuum-core.org/pro) or activate via `continuum-cli auth activate <LICENSE_KEY>`.
