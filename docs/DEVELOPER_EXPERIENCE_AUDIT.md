# Agent C: Product UX & Developer Onboarding Audit

**Auditor:** Agent C (Product UX & Developer Experience)  
**Date:** 2026-09-14  
**Target:** Can an external developer integrate Continuum into an agent within 10 minutes?

---

## 1. Ergonomics Assessment

### Strengths
1. **Zero Infrastructure Bootstrap:** `ContinuumEngine.create()` requires zero external databases, zero Redis/Docker setup, and zero cloud API keys. It runs instantly out-of-the-box.
2. **Minimal Surface Area API:**
   - Ingest: `engine.step(vector, payload_ref="...")`
   - Retrieve: `engine.query(query_vector, top_k=5)`
   - Persist: `engine.save(path)` and `ContinuumEngine.load(path)`
3. **LangChain Native Integration:** `ContinuumChatMessageHistory` provides a standard drop-in replacement for LangChain agent memory with 3 lines of code.

### Areas for Improvement (DX Friction Points)
1. **Vector Conversion Requirement:** Currently, the base engine requires `vector: Tensor | list[float]`. While `LangChain` wrapper accepts raw strings, the base engine requires users to pass pre-computed embeddings.
   - *Recommendation for v0.2:* Provide an optional built-in embedder in `ContinuumEngine` (e.g. `engine.step_text(text)`).
2. **Provenance Clarity:** Return rich metadata dictionaries in `CausalMatch` instead of just string payloads.
