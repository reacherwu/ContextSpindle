# Competitor and prior-art log

This document is a living evidence log, not a novelty claim. The Research role must record highly similar work, its source, overlap, differences, and implications before new mechanisms advance to implementation.

## Initial scan — 2026-09-13

The following is an initial, deliberately non-exhaustive scan of primary papers
and official implementations. It establishes comparison families and risks; it
does **not** establish that Continuum is novel or better than any of them. Full
notes and source links are in [the research log](research/research_log.md).

| Work / family | Primary source / official implementation | Material overlap with Continuum | Implication |
| --- | --- | --- | --- |
| Mamba selective SSM | [Gu & Dao, 2023](https://arxiv.org/abs/2312.00752); [official repo](https://github.com/state-spaces/mamba) | Input-dependent select/forget dynamics and bounded recurrent state | Mandatory local-state / streaming comparator; a learned gate alone is not novel. |
| Mamba-2 / state-space duality | [Dao & Gu, 2024](https://arxiv.org/abs/2405.21060); [official repo](https://github.com/state-spaces/mamba) | Selective SSM refinement; formal bridge between structured SSMs and attention | Do not frame SSM-plus-retrieval ideas as a new attention/SSM principle without a precise distinction and fair implementation. |
| DeltaNet / Gated DeltaNet | [Yang et al., 2024](https://arxiv.org/abs/2406.06484); [Gated DeltaNet paper](https://arxiv.org/abs/2412.06464); [official repo](https://github.com/NVlabs/GatedDeltaNet) | Fixed-size fast-weight state, corrective delta writes, forgetting and input gates | Required comparator once adaptive sparse memory is proposed; the delta rule predates Continuum. |
| Recurrent, compressive, and hierarchical memory Transformers | [Compressive Transformer](https://arxiv.org/abs/1911.05507); [RMT](https://arxiv.org/abs/2207.06881); [HMT](https://arxiv.org/abs/2405.06067); [ARMT](https://arxiv.org/abs/2407.04841) | Bounded segment memory, compression, recurrence, selective/hierarchical recall | “Arbitrary-duration with bounded active memory” is an evaluation goal shared with established work, not a novelty claim. |
| Test-time neural memory | [TTT](https://arxiv.org/abs/2407.04620); [Titans](https://arxiv.org/abs/2501.00663); [ATLAS](https://arxiv.org/abs/2505.23735) | Persistent learned memory, surprise-sensitive writing, local short-term plus long-term memory | Surprise/importance-driven memory and memory-as-parameters require direct ablations against these families if adopted. |
| Complex / phase-aware attention | [Quantum-Inspired Complex Transformers](https://openreview.net/forum?id=41da03e7743318d4eb8659c44bf66795349377e0); [Q-Interference](https://arxiv.org/abs/2608.17288); [Phase-Coherent Transformer](https://arxiv.org/abs/2605.10123) | Amplitude/phase or complex interactions that can reinforce/suppress signals | The planned phase interaction is not quantum computing and is not prima facie new; benchmark against real-valued and phase-disabled controls. |
| Causal graph memory / causal retrieval | [ActMem](https://arxiv.org/abs/2603.00026); [causal graph discovery with RAG](https://arxiv.org/abs/2402.15301) | Structured causal/semantic graph, counterfactual reasoning, evidence-sensitive graph updates | Storing a graph does not validate causality. Separate temporal association, hypotheses, verification status, and interventions in data and evaluation. |
| Temporal revision / knowledge editing | [History Matters / AToKe / METO](https://arxiv.org/abs/2312.05497) | Updating knowledge while retaining time-qualified historical knowledge | Append-only provenance is a sensible design choice, but historical recall and conflict handling must be evaluated—not asserted. |

## Minimum overlap controls

- TASK-001 should be described as a gated temporal-state probe, not as an ACM novelty test. A last-event reference and a size-matched conventional recurrent baseline remain the minimum; Mamba-like / DeltaNet-like comparisons belong in later, feasible benchmark plans.
- Any future sparse event store must be compared separately from compressed/recurrent state. Memory bytes, latency, and retained-event count must be reported alongside task accuracy.
- Any causal claim requires a ground-truth intervention or a clearly labelled synthetic causal generator. Predictive or temporal association alone is insufficient.
- Any revision feature must retain prior evidence and expose time/provenance in queries; test both current-fact and historical-fact answers under conflicting evidence.
