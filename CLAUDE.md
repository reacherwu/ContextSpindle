# Continuum AI Agent Guidelines & Integration Protocol for Claude

> **CRITICAL CONTEXT FOR CLAUDE (Claude Code, Claude Desktop, Cursor Claude)**:  
> This repository is equipped with **Continuum** — a continuous temporal memory manifold written in pure Rust standard library with zero external crate dependencies.  
> It operates under strictly bounded physical slots (750 slots, < 75KB) and performs retrospective causal recall in < 100µs.

---

## 1. Operating Instructions for Claude

When working in this repository:
1. **Retrospectively Recall Past Decisions & Fixes**:
   - Before executing refactors, diagnosing build/test failures, or checking architectural constraints, use the Continuum MCP tool or CLI:
     - MCP Tool: `continuum_recall(query: "...", top_k: 3)`
     - Shell CLI: `continuum-cli recall "<symptom or query>" 3`
2. **Remember New Critical Rules & Causal Bug Fixes**:
   - When resolving a complex bug or establishing a project constraint:
     - MCP Tool: `continuum_remember(text: "RULE/FIX: ...")`
     - Shell CLI: `continuum-cli remember "RULE/FIX: ..."`

---

## 2. Core Architecture Invariants

1. **Physical O(K) Bounded Memory**:
   - Strictly bounded physical slots ($K_{\text{hot}} = 250, K_{\text{cold}} = 500$, total = 750).
   - NEVER introduce unbounded arrays that grow over time $T$.
2. **Two-Tier Manifold with Subspace Diversity**:
   - Hot Memory for recency. Cold Memory uses subspace diversity deduplication ($\text{argmax}(\text{max\_sim}) \ge \text{sim\_thresh}$), NEVER naive FIFO or timestamp eviction.
3. **Causal Revision & Decay Exemption**:
   - When semantic similarity $\ge \theta_{\text{exempt}}$, temporal decay is exempted ($\text{TempCompat} = 1.0$), ensuring ancient root causes defeat recent noise.
4. **Lightweight Semantic Causal Bridge**:
   - Dual-channel query projection ($q_{\text{bridged}} = (1-\lambda) q_{\text{symptom}} + \lambda q_{\text{hypothesis}}$) in $< 10\ \mu\text{s}$ without cloud LLM roundtrips.

---

## 3. Technology Stack & Language Mandates

1. **Rust Core Priority**:
   - All high-performance streaming, state recurrence, memory indexing, and persistence belong in `crates/continuum-core`.
   - `continuum-core` must maintain **zero external crate dependencies** (pure standard library).
   - The CLI in `crates/continuum-cli` compiles to a standalone, zero-dependency binary.
2. **Python Integration**:
   - Python access is provided via `continuum/native.py` using standard `ctypes` bindings to `target/release/libcontinuum_core.dylib`.

---

## 4. Mandatory Verification Redlines

Before completing any task, you MUST execute and pass:
1. `cargo test --workspace` (Must be 100% PASS, 0 failures).
2. `python3 -m unittest discover tests` (Must be 100% PASS, 0 failures).
3. Check scenarios via `./target/release/continuum-cli demo <aiops|persona|github|persistence>` (All must report `🎉 VERDICT: SUCCESS`).
