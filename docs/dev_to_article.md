---
title: I built an open-source Rust memory engine that stops AI coding agents from losing context across 1,000+ turns
published: true
description: How we built a 75KB constant memory manifold in 100% pure Rust std that slashes LLM tokens by 96% with <100µs recall on Apple M4.
tags: rust, ai, opensource, programming
canonical_url: https://reacherwu.github.io/continuum/
cover_image: https://raw.githubusercontent.com/reacherwu/continuum/main/benchmarks/assets/continuum_benchmark_infographic.png
---

If you use autonomous coding agents daily — whether it’s **Cursor, Claude Code, Antigravity, OpenClaw, Hermes Agent, or Codex** — you’ve almost certainly run into the exact same brutal trade-off during long-horizon software engineering sprints:

1. **The "Turn 200" Amnesia**: You set a critical constraint at step 10 (e.g. *"Never use legacy OpenSSL ciphers and keep the database pool capped at 5 in auth-service"*). By turn 250 and 50 file edits later, the agent has completely forgotten your rule, hallucinates a default configuration, and breaks your build.
2. **The "Alert Storm" Doom Loop**: An integration test fails and dumps 100 repetitive lines of compiler errors or 502/SSL connection warnings into the terminal. Because context windows suffer from recency bias, the agent’s context is flooded with symptom chatter, pushing the distant root-cause change out of memory.
3. **The Runaway Token Bill**: In deep multi-file refactoring sessions spanning 500 to 1,000+ turns, naively re-sending the entire accumulated conversation history means paying for 100k+ input tokens *on every single request*. A single sprint can easily burn through dozens of dollars in API credits.

To solve this once and for all, I built and open-sourced [**Continuum**](https://github.com/reacherwu/continuum) — an ultra-lightweight, zero-dependency continuous temporal memory engine written in 100% pure standard library Rust.

---

## What is Continuum?

Instead of stuffing entire 100k+ token histories into prompts or spinning up heavy 2GB vector databases (with Redis clusters), Continuum maintains an active, **strictly bounded physical memory manifold (750 physical slots, occupying < 75 KB RAM)** right on your local machine.

Whenever an error occurs or past context is needed, Continuum uses **Retrospective Causal Revision** to retrieve *only the 3 to 5 critical historical anchors* in **under 100 microseconds**, exempting ancient root causes from temporal decay.

![Continuum Hardware-Verified Benchmarks](https://raw.githubusercontent.com/reacherwu/continuum/main/benchmarks/assets/continuum_benchmark_infographic.png)

---

## Real Bare-Metal Hardware Benchmarks (Apple M4)

We didn't just theoretically model savings. We executed real end-to-end benchmarks using **OpenAI's official `tiktoken` (`cl100k_base`)** on an Apple M4 Mac across coding trajectories and streaming logs:

| Metric | Full Context Appending | Standard Sliding Window (10 turns) | **Continuum (Native Rust Engine)** | Real Impact |
| :--- | :--- | :--- | :--- | :--- |
| **Step 90 Prompt Size** | 2,664 tokens | 305 tokens | **256 tokens** | **📉 90.4% token cut** |
| **100-Turn Cumulative Tokens** | 148,522 tokens | 26,450 tokens | **5,896 tokens** | **📉 96.03% token slash** |
| **1,000+ Turn Projected Tokens** | ~50,000,000+ tokens | Truncated | **~300,000 tokens** | **📉 99.4% token slash** |
| **Did it remember Step 10 root cause?** | Yes | ❌ **0% Accuracy (Forgotten)** | ✅ **100% Accuracy (Rank #1)** | **Zero context amnesia** |
| **100,000-Step Stress Test** | Process OOM / Crash | Memory leaks | **Flat 750 slots (< 75 KB RAM)** | **Zero memory leaks** |
| **Retrieval Latency** | 12 ~ 18 seconds | 1 ~ 2 seconds | **60.46 microseconds** | **⚡ 16,540 queries/sec** |

### The Core Takeaway
A sliding window saves tokens but causes catastrophic forgetting (0% accuracy). Continuum cuts token consumption by **96% to 99%** while **guaranteeing 100% causal retention**.

---

## How It Works Under the Hood

Continuum is built on three core systems principles:

### 1. Physical $O(K)$ Bounded Memory
Memory slots are partitioned into:
- **Hot Working Memory ($K_{\text{hot}} = 250$)**: High-fidelity short-term state retention.
- **Cold Candidate Memory ($K_{\text{cold}} = 500$)**: Diverse long-term hypothesis space.

The memory footprint is permanently capped at 750 slots (< 75 KB of contiguous RAM). No matter if you run 100 turns or 100,000 steps, memory usage is a flat, horizontal line.

### 2. Subspace Diversity Deduplication (Anti-Alert-Storm)
When Cold Memory reaches capacity, Continuum does **not** use naive First-In, First-Out (FIFO) or timestamp eviction. Instead, it prunes records with the highest mutual cosine redundancy ($\text{argmax}(\text{max\_sim}) \ge \theta$). 

Under real-world production outages, 500 repetitive symptom messages (like 504 timeouts) collapse into minimal slots, while rare critical mutations from 1,000 turns ago are retained indefinitely.

### 3. Retrospective Causal Revision & Decay Exemption
When a downstream error manifests, historical candidate memories are retrospectively re-scored. If semantic/causal similarity exceeds the exemption threshold, temporal exponential decay is **completely bypassed** ($\text{TempCompat} = 1.0$), allowing distant root causes to defeat recent background chatter.

### 4. Zero External Dependencies (100% Pure Rust `std`)
The core engine (`crates/continuum-core`) has **zero external crate dependencies**. It compiles into a standalone, ultra-compact static binary with zero GC pauses and microsecond cold starts.

---

## Quickstart: Use It with Cursor, Claude Code, or Any Agent via MCP

Continuum includes a built-in **Model Context Protocol (MCP)** server out of the box.

### Step 1: Install the Standalone CLI (macOS / Linux)
```bash
curl -fsSL https://raw.githubusercontent.com/reacherwu/continuum/main/install.sh | bash
```
*(Or build from source: `cargo install --path crates/continuum-cli`)*

### Step 2: Initialize in Any Workspace
```bash
continuum-cli init .
```
This creates `.continuum/memory.state` (< 75 KB, strictly bounded at 750 physical slots).

### Step 3: Configure MCP in Your IDE

#### For Cursor / Windsurf:
Add to `~/.cursor/mcp.json`:
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

#### For Claude Desktop:
Add to `claude_desktop_config.json`:
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

### Or Simply Use the "One-Prompt" Directive
You can paste this directly to Cursor, Claude Code, or Antigravity:
> *"Please read AGENTS.md at https://github.com/reacherwu/continuum and autonomously equip yourself with Continuum memory for this workspace."*

Your assistant will install the CLI, initialize memory, and begin autonomously recording key architectural decisions and bug fixes!

---

## 100% Free & Open Source

Continuum is fully open-source under the **GNU AGPL-v3** license:
- ⭐️ **GitHub Repository**: [https://github.com/reacherwu/continuum](https://github.com/reacherwu/continuum)
- 📊 **Documentation & Interactive Telemetry**: [https://reacherwu.github.io/continuum/](https://reacherwu.github.io/continuum/)
- 🔬 **CERN Zenodo DOI**: `10.5281/zenodo.22765180`

### Discussion Question
For anyone building autonomous agent workflows or using Cursor/Claude Code on large repositories daily: **How are you currently preventing context degradation and runaway token bills during long multi-file sessions? What is your biggest friction point?**

Let me know in the comments below, and feel free to open issues or feature requests on GitHub!
