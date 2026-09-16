---
title: I built an open-source Rust memory engine that stops AI coding agents from losing context across 1,000+ turns
published: true
description: A 75KB constant memory manifold in 100% pure Rust std that slashes LLM tokens by 96% with <100µs recall on Apple M4.
tags: rust, ai, opensource, programming
canonical_url: https://reacherwu.github.io/continuum/
cover_image: https://raw.githubusercontent.com/reacherwu/continuum/main/benchmarks/assets/continuum_benchmark_infographic.png
---

If you use autonomous coding agents (**Cursor, Claude Code, Antigravity, OpenClaw, Hermes, Codex**), you've likely hit these long-sprint pain points:

1. **The "Turn 200" Amnesia**: You set a database or security rule at step 10. By turn 250, the agent has completely forgotten it and breaks production.
2. **The "Alert Storm" Doom Loop**: A test fails and dumps 100 lines of error logs. Recency bias drowns out the real root cause that happened 50 turns ago.
3. **Runaway Token Costs**: Re-sending full conversation history on turn 500+ burns 100k+ input tokens per prompt, quickly draining your wallet.

To solve this, I built and open-sourced [**Continuum**](https://github.com/reacherwu/continuum) — an ultra-lightweight, zero-dependency continuous temporal memory engine written in 100% pure standard library Rust.

---

## Real Hardware Benchmarks (Apple M4)

Instead of stuffing 100k+ histories or spinning up heavy 2GB vector databases, Continuum maintains a **strictly bounded physical memory manifold (750 slots, < 75 KB RAM)**.

We benchmarked Continuum using **OpenAI `tiktoken` (`cl100k_base`)** on an Apple M4 across real coding sessions:

![Continuum Hardware-Verified Benchmarks](https://raw.githubusercontent.com/reacherwu/continuum/main/benchmarks/assets/continuum_benchmark_infographic.png)

| Metric | Full Context Appending | Standard Sliding Window (10 turns) | **Continuum (Native Rust Engine)** |
| :--- | :--- | :--- | :--- |
| **100-Turn Cumulative Tokens** | 148,522 tokens | 26,450 tokens | **5,896 tokens (96.03% slash)** |
| **Multi-Depth Needle Recall** | 5/5 (100%) | 0/5 (0% - Forgotten) | **5/5 (100% at Rank #1)** |
| **Rule Override & Contradiction** | Ambiguous prompt conflict | ❌ 0% (Forgotten) | ✅ **100% (Latest override at Rank #1)** |
| **Task Success / Build Pass** | 100% (High cost) | ❌ 0% (Broken config) | ✅ **100% (Tests pass, 96% token cut)** |
| **Engine Retrieval Overhead** | 1.2 ~ 2.5s (full history scan) | N/A (truncated) | **60.46 µs (< 0.0001s, 16,540 QPS)** |
| **End-to-End Prompt Latency** | 12 ~ 18s (100k token load) | 1.1s (shallow window) | **1.2s (compact 256-token prompt)** |
| **100,000-Step Stress Test** | Process Crash (OOM) | Memory leaks | **Flat 750 slots (< 75 KB RAM, 0 leaks)** |

> **The Takeaway**: Sliding windows save tokens but destroy outcomes (0% task success). Continuum cuts token usage by **96%~99%** while **guaranteeing 100% multi-depth recall and contradiction resolution**.

---

## How It Works in 4 Bullets

- **Physical $O(K)$ Bounded Memory**: Exactly 750 slots (< 75 KB contiguous RAM). Memory usage stays a flat line forever across 100,000 steps.
- **Subspace Diversity Deduplication**: Eliminates alert storms without naive FIFO eviction. 500 repetitive errors collapse into minimal slots, protecting ancient root causes.
- **Retrospective Causal Revision & Supersession**: Bypasses decay for genuine anchors, while actively suppressing stale predecessors when rules are updated/contradicted.
- **Zero External Dependencies**: 100% pure Rust `std` — single standalone binary, zero GC pauses, microsecond startup.

---

## 1-Minute Quickstart (MCP)

Continuum comes with a built-in Model Context Protocol (MCP) server for Cursor, Claude Desktop, and Antigravity:

```bash
# 1. Install standalone CLI
curl -fsSL https://raw.githubusercontent.com/reacherwu/continuum/main/install.sh | bash

# 2. Init in any repo (< 75 KB memory manifold)
continuum-cli init .
```

Add to `~/.cursor/mcp.json` or `claude_desktop_config.json`:
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

Or simply prompt your assistant:  
> *"Read AGENTS.md at https://github.com/reacherwu/continuum and equip yourself with Continuum memory for this workspace."*

---

## Open Source & Discussion

- ⭐️ **GitHub**: [https://github.com/reacherwu/continuum](https://github.com/reacherwu/continuum)
- 📊 **Interactive Telemetry Docs**: [https://reacherwu.github.io/continuum/](https://reacherwu.github.io/continuum/)
- 📜 **License**: GNU AGPL-v3

**Discussion**: How do you currently prevent context amnesia and runaway token bills during long coding sprints in Cursor or Claude Code? Would love to hear your thoughts and feedback!
