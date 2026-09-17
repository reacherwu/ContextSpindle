# Continuum — AI Team Handover & Anti-Regression Guard

<div align="center">

**English** | [中文说明](README_CN.md)

</div>

[![Rust: 100% Native](https://img.shields.io/badge/Rust-100%25%20Pure%20Native-dea584.svg?logo=rust&logoColor=white)](crates/continuum-core)
[![Zero External Crates](https://img.shields.io/badge/Dependencies-0%20(Pure%20std)-brightgreen.svg?logo=rust&logoColor=white)](#)
[![Tests: 82 Passing](https://img.shields.io/badge/tests-82%20passing-brightgreen)](#)
[![Memory: Flat O(K)](https://img.shields.io/badge/Memory-750%20Slots%20Flat%20O(K)-blue.svg)](#)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22765180.svg)](https://doi.org/10.5281/zenodo.22765180)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-purple.svg)](LICENSE)

> **“Prevent new AI sessions and agents from repeating errors your team has already solved.”**  
> Designed for software development agencies and engineering teams maintaining multiple repositories with AI tools (Cursor, Claude Code, Windsurf, Hermes).

---

## 🎯 3 Concrete Outcomes Delivered

| Outcome | Traditional AI Coding Reality | With Continuum Team Guard |
| :--- | :--- | :--- |
| **1. Zero-Context Handover** | Switching devs, IDEs, or starting a new session causes AI amnesia. Developers waste time re-prompting project constraints. | **Automatic Repository Manifold**: Project rules live in the repo root; any dev or AI picks up the context instantly. |
| **2. Verifiable Audit Trail** | Past fixes get lost in chat histories. AI hallucinates plausible but incorrect solutions from fuzzy memories. | **Causal Pairing with Verification**: Pairs failure symptoms directly with working fix commands (e.g. green test runs) and Git commits. |
| **3. Live Warnings & CI Gatekeeping** | AI quietly re-breaks edge cases resolved last week, re-introducing regressions into main branches. | **Active Warnings + Deterministic Tests**: Turns critical rules into regression tests to physically block errors in CI/CD. |

---

## 💡 Why Software Agencies & Multi-Repo Teams Need It

In fast-paced environments rotating between multiple client codebases, **AI-induced rework directly burns billable hours and client trust**:

1. **Convention Bleeding**: Devs work on Client A's React 18 in the morning, and Client B's legacy Vue 2 in the afternoon. AI habitually bleeds patterns across projects.
2. **Repeating Hidden Traps**: Niche client quirks (e.g. *"payment webhook requires strict HMAC order"*, *"table X requires a distributed lock"*) are learned the hard way once, but newly spawned AI sessions stumble into them again.
3. **Unbillable Rework**: Debugging the same regression twice cannot be billed to the client—it directly eats into the agency's net margin.

---

## 🚀 3-Step Setup (Zero Friction)

### 1. Install Continuum CLI
```bash
curl -fsSL https://raw.githubusercontent.com/reacherwu/continuum/main/install.sh | bash 2>/dev/null || cargo install --path crates/continuum-cli
```

### 2. Initialize in Repository and Mount Git Hook
```bash
# Inside target project repository root
continuum-cli init .
continuum-cli hook install .
```
- Creates an ultra-compact `< 75 KB` state file at `.continuum/memory.state`.
- Automatically captures configuration changes and commits on every `git commit`.

### 3. Connect to Team IDEs (Cursor / Claude / Windsurf)

Continuum includes a **built-in, zero-dependency MCP (Model Context Protocol) stdio server**.

#### Cursor (`~/.cursor/mcp.json`):
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

#### Claude Code / Claude Desktop:
```bash
claude mcp add continuum continuum-cli mcp
```

---

## 🛠️ Daily Workflow: Completely Frictionless

Developers **do not need to change their daily habits**. Continuum operates silently beneath the surface:

```bash
# 1. Record a critical project constraint or architectural guardrail
continuum-cli remember "RULE: Client payment callback must verify HMAC SHA256 signature with 3s timeout"

# 2. Autonomous Causal Pairing: run tests through runner; failure symptoms auto-pair with fixes
continuum-cli run cargo test
# or
continuum-cli run pytest

# 3. Microsecond recall (< 100 μs) before refactoring or when debugging
continuum-cli recall "payment gateway timeout" 2

# Machine mode: structured JSON output for AI Agent integration
continuum-cli recall "payment gateway timeout" 2 --json
```

---

## ⚡ Hardened Production Engineering (100% Native Rust)

Continuum is not a fragile glue script—it is an industrial-grade systems binary:

- **100% Pure Rust Standard Library**: `crates/continuum-core` has **0 external crate dependencies**, single standalone binary, memory strictly bounded at **~75 KB** (zero Python heap bloat or GC pauses);
- **OS Kernel `flock` Mutual Exclusion**: Uses operating system kernel file locks; process crashes automatically release the lock descriptor, eliminating deadlocks and split-brain writes;
- **Power-Loss Durability & Checksums**: Atomic replacement followed by **parent directory `fsync`**, with built-in `CTNMFOOT` signatures and 64-bit FNV-1a checksums;
- **Full Regression Test Guard**: 82 automated unit, regression, and C-ABI integration tests passing 100%.

---

## 📄 Academic Citation & Prior Art

The foundational two-tier manifold and retrospective causal revision architecture were independently derived and archived on **CERN Zenodo**:
- **Paper**: *Continuum: A Deterministic O(K)-Bounded Two-Tier Memory Manifold for Resilient Autonomous Agents under Temporal Alert Storms*
- **Author**: Jun Wu
- **DOI**: [https://doi.org/10.5281/zenodo.22765180](https://doi.org/10.5281/zenodo.22765180)

---

## 📜 License

Released under the **GNU Affero General Public License v3.0 (AGPL-v3)**. Free and open-source for developers and teams locally.
