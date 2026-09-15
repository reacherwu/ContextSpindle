# Continuum AI Agent Engineering Guidelines & Project Rules

> **CRITICAL CONTEXT FOR AI AGENTS**:  
> This file establishes the mandatory architecture principles, coding standards, and operational guidelines discovered through extensive empirical validation of the Continuum project.  
> Whenever working in this repository, you MUST adhere strictly to these rules.

---

## 1. Core Architecture Invariants

1. **Physical O(K) Bounded Memory**:
   - The engine operates under strictly bounded physical slots (default: $K_{\text{hot}} = 250, K_{\text{cold}} = 500$, total = 750).
   - NEVER introduce unbounded lists, sliding arrays that grow with stream length $T$, or memory leaks. Memory allocation must remain constant over infinite time.
2. **Two-Tier Manifold with Subspace Diversity**:
   - Hot Memory handles short-term multi-factor retention.
   - Cold Memory handles candidate diversity. Eviction from cold memory MUST use mutual redundancy pruning ($\text{argmax}(\text{max\_sim}) \ge \text{sim\_thresh}$), NEVER naive FIFO or timestamp eviction. This protects against alert storms.
3. **Causal Revision & Decay Exemption**:
   - The Retrospective Causal Revision engine breaks the forward recall barrier.
   - When semantic similarity $\ge \theta_{\text{exempt}}$, temporal decay is exempted ($\text{TempCompat} = 1.0$), ensuring ancient root causes defeat recent background chatter.
4. **Lightweight Semantic Causal Bridge**:
   - For domain discrepancies (e.g. error symptom vs. historical configuration action), use dual-channel query projection ($q_{\text{bridged}} = (1-\lambda) q_{\text{symptom}} + \lambda q_{\text{hypothesis}}$). Keep projection deterministic and $< 10\ \mu\text{s}$ without cloud LLM roundtrips.

---

## 2. Technology Stack & Language Mandates

1. **Rust Core Priority**:
   - All high-performance streaming, state recurrence, memory indexing, and persistence logic belongs in `crates/continuum-core`.
   - `continuum-core` must maintain **zero external crate dependencies** (pure standard library).
   - The CLI in `crates/continuum-cli` compiles to a standalone, zero-dependency binary.
2. **Python Integration**:
   - Python access is provided via `continuum/native.py` using standard `ctypes` bindings to the compiled cdylib (`target/release/libcontinuum_core.dylib`).
   - Do NOT introduce heavyweight Python dependencies into the core engine path.

---

## 3. Anti-Patterns to Avoid

- ❌ **The Toy Benchmark Trap**: NEVER use synthetic randomly generated vectors (e.g., $v_{\text{query}} = 0.85 v_{\text{root}} + ...$) as primary proof of capability. Always evaluate using real text corpora (AIOps logs, conversational turns, Git trajectories).
- ❌ **Alert Storm Truncation**: NEVER apply a pre-filter top-k cutoff before causal revision scoring. The true root cause may have low initial raw similarity during an alert storm.
- ❌ **Python Heap Bloat**: NEVER store unbounded string representations in Python heap for long streams; Python allocator causes up to 724MB heap fragmentation. Keep memory flat in native Rust.

---

## 4. Mandatory Verification Redlines

Before completing any task or claiming success, you MUST execute and pass:
1. `cargo test --workspace` (Must be 100% PASS, 0 failures).
2. `python3 -m unittest discover tests` (Must be 100% PASS, 0 failures).
3. Check scenarios via `./target/release/continuum-cli demo <aiops|persona|github|persistence>` (All must report `🎉 VERDICT: SUCCESS`).

---

## 5. Canonical Reference Documents
- Canonical Engineering Playbook: `docs/ENGINEERING_PLAYBOOK.md`
- Architecture Specification: `docs/ARCHITECTURE.md`
- Reality Test Ablation Reports: `experiments/results/reality_test/`
