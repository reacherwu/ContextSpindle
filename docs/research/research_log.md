# Initial prior-art research log

**Scan date:** 2026-09-13

**Scope:** initial literature and official-implementation scan for Continuum v0.1.

**Method:** live web search; primary papers (arXiv, conference proceedings, OpenReview) and official repositories were preferred. Links below are source records, not performance endorsements. This log makes no novelty, priority, or superiority claim.

## Bottom line

Continuum's intended component set sits in well-populated research areas:
input-selective recurrent state, fast-weight corrective memory, compressed and
retrieved long context, test-time neural memory, complex/phase-aware attention,
causal graph memory, and temporally qualified revision. The repository should
therefore present ACM as a **testable integration and evaluation hypothesis**.
No component is treated as novel merely because it is combined with the others.
Whether a particular implementation is materially different—or useful—remains
an empirical and legal/attribution question for a future RFC and benchmark.

## Evidence register

### 1. Selective state-space models: Mamba and Mamba-2

- **Source:** Gu & Dao, *Mamba: Linear-Time Sequence Modeling with Selective State Spaces* (2023), [arXiv:2312.00752](https://arxiv.org/abs/2312.00752), with [official code](https://github.com/state-spaces/mamba).
- **What the source establishes:** Mamba makes SSM parameters input-dependent so a sequence model can selectively propagate or forget information; the paper describes linear sequence scaling and a hardware-aware recurrent-mode algorithm.
- **Continuum overlap:** `h_t = (1-g_t)h_{t-1}+g_t candidate_t` and the stated goals of selective propagation/forgetting and bounded streaming state overlap at the design-problem level. A gated local temporal state is conventional recurrent/SSM territory, not a new memory mechanism.
- **Difference currently documented:** TASK-001 is a deliberately small PyTorch probe for local synthetic dependencies; it does not claim Mamba's selective SSM parameterization, scan implementation, scale, or language-model result.
- **Implication:** use neutral language (“gated temporal state”). Do not compare throughput or long-context accuracy with Mamba absent matching model capacity, precision, hardware, training data, and task. Add Mamba-family comparison only when it can be reproduced fairly.

- **Source:** Dao & Gu, *Transformers are SSMs: Generalized Models and Efficient Algorithms Through Structured State Space Duality* (2024), [arXiv:2405.21060](https://arxiv.org/abs/2405.21060), [official code repository](https://github.com/state-spaces/mamba).
- **What the source establishes:** the SSD framework connects structured SSMs and attention variants and introduces Mamba-2 as a refinement of selective SSMs. The authors report a 2–8× core-layer speed figure in their own setting.
- **Continuum overlap:** any proposal that combines state evolution with attention-like retrieval touches an explicitly studied SSM/attention relationship.
- **Implication:** do not call a future SSM-plus-retrieval or router design a new theoretical bridge without a formal derivation and a separate literature review. The paper's reported speed figure is not transferable to this prototype.

### 2. Delta-rule and gated fast-weight memory

- **Source:** Yang et al., *Parallelizing Linear Transformers with the Delta Rule over Sequence Length* (2024), [arXiv:2406.06484](https://arxiv.org/abs/2406.06484), [NeurIPS proceedings PDF](https://papers.neurips.cc/paper_files/paper/2024/file/d13a3eae72366e61dfdc7eea82eeb685-Paper-Conference.pdf).
- **What the source establishes:** it studies DeltaNet, where a fixed-size fast-weight memory receives corrective delta-rule updates, and develops parallel training over sequence length. The delta rule itself is older than this work.
- **Continuum overlap:** bounded adaptive memory with correction/write behavior is strongly overlapping. A future “revise the memory state when evidence arrives” mechanism must distinguish revision of an explicit event record from DeltaNet's differentiable fast-weight update.

- **Source:** Yang, Kautz & Hatamizadeh, *Gated Delta Networks: Improving Mamba2 with Delta Rule* (2024/ICLR 2025), [arXiv:2412.06464](https://arxiv.org/abs/2412.06464), [official NVIDIA implementation](https://github.com/NVlabs/GatedDeltaNet).
- **What the source establishes:** Gated DeltaNet combines delta-rule memory updates with data-dependent gating and evaluates pure and hybrid variants.
- **Continuum overlap:** importance/forget/write gating and fixed active memory are direct competitors in the same functional space.
- **Implication:** for adaptive memory stages, use a Gated DeltaNet-like baseline or state clearly that comparison is not yet feasible. Do not reduce the baseline to “linear attention”: its corrective write rule and gates are material ablations.

### 3. Long-context recurrent, compressed, and retrieved memory

- **Sources:** Rae et al., *Compressive Transformers for Long-Range Sequence Modelling* (2019), [arXiv:1911.05507](https://arxiv.org/abs/1911.05507); Bulatov et al., *Recurrent Memory Transformer* (2022), [arXiv:2207.06881](https://arxiv.org/abs/2207.06881); He et al., *Hierarchical Memory Transformer* (2024), [arXiv:2405.06067](https://arxiv.org/abs/2405.06067), [code](https://github.com/OswaldHe/HMT-pytorch); Rodkin et al., *Associative Recurrent Memory Transformer* (2024), [arXiv:2407.04841](https://arxiv.org/abs/2407.04841).
- **What these sources establish:** established alternatives hold recent states, compress or propagate older information across segments, and in some cases retrieve/organize that history hierarchically or associatively.
- **Continuum overlap:** bounded active memory, event selection, memory compression, and retrieval across a stream are all established research problems with concrete architectures.
- **Difference currently documented:** Continuum proposes explicitly auditable event records and causal-hypothesis status, rather than only latent token/state memories. That is a proposed data/provenance distinction, not an established performance advantage.
- **Implication:** report separate costs for the active latent state, retained event records, and any graph. “Bounded active memory” must not conceal unbounded archival/event storage.

### 4. Test-time learned long-term memory

- **Sources:** Sun et al., *Learning to (Learn at Test Time): RNNs with Expressive Hidden States* (2024), [arXiv:2407.04620](https://arxiv.org/abs/2407.04620); Behrouz, Zhong & Mirrokni, *Titans: Learning to Memorize at Test Time* (2025), [arXiv:2501.00663](https://arxiv.org/abs/2501.00663), [NeurIPS paper](https://proceedings.neurips.cc/paper_files/paper/2025/file/a4ca07aa108036f80cbb5b82285fd4b1-Paper-Conference.pdf); Behrouz et al., *ATLAS: Learning to Optimally Memorize the Context at Test Time* (2025), [arXiv:2505.23735](https://arxiv.org/abs/2505.23735).
- **What these sources establish:** a memory may be a test-time-updated neural object rather than only a hidden vector or external store. Titans explicitly couples local attention with long-term neural memory and uses surprise-sensitive writing/decay; ATLAS addresses capacity and update management.
- **Continuum overlap:** short/local state plus longer-lived memory, surprise/importance signals, write/forget control, and later adaptation overlap materially.
- **Implication:** importance, novelty, and surprise fields in Continuum event records are bookkeeping signals until operationalized and ablated. If they drive writing, compare against uniform, recency, and surprise-disabled policies; do not describe them as a new long-term-memory principle.

### 5. Phase-aware and quantum-inspired attention

- **Sources:** *Quantum-Inspired Complex Transformers: Resolving* (OpenReview, 2025), [paper](https://openreview.net/forum?id=41da03e7743318d4eb8659c44bf66795349377e0); Nahid et al., *Q-Interference: Memory-Efficient Phase-Aware Quantum-Inspired Attention* (2026), [arXiv:2608.17288](https://arxiv.org/abs/2608.17288); Hioki, *Complex-Valued Phase-Coherent Transformer* (2026), [arXiv:2605.10123](https://arxiv.org/abs/2605.10123).
- **What these sources establish:** complex-valued or amplitude/phase parameterizations and phase-dependent interaction/suppression have already been investigated. Q-Interference specifically presents a classical trigonometric factorization for phase-aware attention.
- **Continuum overlap:** the architecture document's proposed learned amplitude/phase score is within this prior-art family.
- **Implication:** retain the constitution's wording: this is a classical, ablatable interaction score, **not quantum computing**. A future RFC needs an exact equation, numerical-stability plan, parameter/FLOP accounting, and real-valued, phase-randomized, and phase-disabled controls. No novelty inference is warranted from the current prose.

### 6. Causal memory and causal graph updates

- **Sources:** Zhang et al., *ActMem: Bridging the Gap Between Memory Retrieval and Reasoning in LLM Agents* (2026), [arXiv:2603.00026](https://arxiv.org/abs/2603.00026); Zhang et al., *Causal Graph Discovery with Retrieval-Augmented Generation based Large Language Models* (2024), [arXiv:2402.15301](https://arxiv.org/abs/2402.15301).
- **What these sources establish:** ActMem organizes history as a causal/semantic graph and uses it for active causal reasoning; the causal-graph-discovery work distinguishes association extraction from a causality-verification mechanism and discusses evidence-sensitive updates.
- **Continuum overlap:** explicit event graph, causal hypotheses, multi-hop queries, counterfactual-like reasoning, and revision in response to later evidence.
- **Difference currently documented:** Continuum explicitly proposes separate hypothesis versus validated-relation labels and append-only provenance. That is a sensible safety/evaluation stance but not a claim that causal validity can be inferred from a stream.
- **Implication:** any edge produced from co-occurrence, temporal order, embedding similarity, or an LLM must start as non-validated. A causal-memory benchmark must provide intervention ground truth (or say it measures only association/path retrieval). Accuracy on multi-hop temporal chains is not causal identification.

### 7. Historical memory revision and provenance

- **Source:** Yin et al., *History Matters: Temporal Knowledge Editing in Large Language Model* (2023/AAAI 2024), [arXiv:2312.05497](https://arxiv.org/abs/2312.05497), [AAAI record](https://doi.org/10.1609/aaai.v38i17.29912).
- **What the source establishes:** the authors formulate temporal knowledge editing and report that conventional edits can retain new facts while catastrophically forgetting historical ones; their AToKe benchmark and METO make historical and new facts time-qualified targets.
- **Continuum overlap:** RQ5 and `revise(event_id, evidence)` directly overlap with the problem of applying later evidence without losing prior, time-relevant interpretation.
- **Implication:** append-only evidence/provenance should support two query modes: “current best-supported interpretation” and “interpretation supported as of time *t*.” Revision benchmarks must score both and include contradictions, reversals, false corrections, and provenance traceability. Append-only storage by itself does not resolve conflicting retrieval.

## Cross-cutting evaluation requirements induced by the scan

1. **Define the resource boundary.** Count resident model state, event archive, graph, indices, and any disk-backed store separately. “Linear” or “bounded” must name the quantity and the sequence/storage assumptions.
2. **Separate functional claims.** Retrieval accuracy, local temporal prediction, causal identification, historical revision, latency, and throughput cannot substitute for one another.
3. **Use controls that isolate each proposed benefit.** At minimum: last-event/recency; conventional gated state; uniform versus importance/surprise writing; no-retrieval versus sparse retrieval; no-graph versus graph; current-only versus historical-time-qualified revision; real-valued versus phase-disabled interaction.
4. **Treat published numbers as non-comparable by default.** This v0.1 prototype's hardware, parameter count, data, seeds, precision, and objectives differ from the cited systems unless a benchmark record proves otherwise.
5. **Preserve negative results.** Compression and learned memory can lose exact recall, create interference, and make provenance/retrieval conflict resolution harder. Record these outcomes rather than relabelling them as evidence of causality or abstraction.

## Gaps / next research check before later phases

- Before adaptive sparse memory: survey/reproduce feasible Mamba, Gated DeltaNet, and a recurrent/compressive-memory comparator for the exact synthetic task.
- Before phase interaction: conduct a dedicated derivation and prior-art pass covering complex-valued attention, then submit an RFC with ablations and stability criteria.
- Before causal graph implementation: specify edge evidence, confidence calibration, verification protocol, intervention-ground-truth generator, and query semantics.
- Before revision implementation: specify immutable event/evidence schema, conflict-resolution rule, temporal query API, and revision benchmark including historical recall.

## Source-selection note

The web scan also surfaced newer preprints and informal implementations. They are intentionally not used as the basis for performance claims here. The cited links above are primary papers, proceedings/OpenReview records, or explicitly official repositories where available. The scan is not exhaustive and should be refreshed for each mechanism-specific RFC.
