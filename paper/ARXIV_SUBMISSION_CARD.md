# arXiv.org Submission Metadata Card

Use this metadata card to fill in the submission fields on [arXiv.org Submit](https://arxiv.org/user/create?preflight=1).

---

## 1. File Upload (Source Files)
- **File to Upload**: [`/Users/mymac/Desktop/continuum/paper/arxiv_submission.tar.gz`](file:///Users/mymac/Desktop/continuum/paper/arxiv_submission.tar.gz)  
  *(Or drag and drop `main.tex` and `references.bib` from `paper/arxiv_package/`)*

---

## 2. Category Selection
- **Primary Classification**: `Computer Science - Artificial Intelligence (cs.AI)`
- **Cross Lists (Recommended)**:
  - `Computer Science - Software Engineering (cs.SE)`
  - `Computer Science - Distributed, Systems, and Cluster Computing (cs.DC)`

---

## 3. Metadata Fields (Copy & Paste)

### Title
```text
Continuum: A Deterministic O(K)-Bounded Two-Tier Memory Manifold for Resilient Autonomous Agents under Temporal Alert Storms
```

### Authors
```text
Jun Wu
```

### Abstract (Plain Text for arXiv Web Interface)
```text
Autonomous software engineering agents, conversational assistants, and automated site reliability engineering (AIOps) systems must operate over long-running sequential trajectories spanning thousands of discrete steps. Existing state management paradigms suffer from a foundational physical trade-off: (i) appending uncompressed interaction logs to the context window incurs O(T) cumulative token transmission costs, high latency, and severe attentional degradation (Lost-in-the-Middle), while (ii) naive First-In, First-Out (FIFO) sliding windows permanently evict ancient, safety-critical causal anchors when saturated by bursty alert storms. We present Continuum, a continuous temporal intelligence engine governed by a deterministic, physically bounded O(K) two-tier memory manifold. Continuum bifurcates working memory into an active Hot working memory (K_hot = 250) and a candidate Cold manifold (K_cold = 500). To prevent repetitive alert storms from exhausting physical capacity, Continuum enforces Subspace Diversity Deduplication, evicting records with maximal mutual redundancy rather than temporal age. When terminal symptoms occur, Continuum employs Retrospective Causal Revision with Temporal Decay Exemption: candidate events exhibiting high causal/semantic affinity (>= theta_exempt) bypass recency penalties entirely (TempCompat = 1.0), ensuring ancient root causes defeat recent noise. Furthermore, for cross-domain discrepancies lacking shared vocabulary, Continuum introduces a deterministic Dual-Channel Semantic Causal Bridge projecting diagnostic hypotheses in < 10 microseconds. Continuum is implemented as a standalone, zero-external-dependency library in pure Rust with flat, cache-coherent memory layouts and sub-millisecond, bit-exact disk serialization. On enterprise AIOps benchmarks under 3,000-step alert storms, Continuum retrieves ancient root-cause configurations at Rank #1 with 100% recall, whereas standard vector stores and FIFO fail. In an in-the-wild, self-referential evaluation on its own 3,203-step development trajectory (4.61 MB raw JSONL), Continuum compresses history into 750 bounded slots, runs retrospective causal queries in 755.8 microseconds, and reduces cloud token transmission by 96.8%, fully eliminating 5-minute prompt cache TTL invalidation penalties.
```

### Comments (Optional)
```text
8 pages, 2 tables, 2 algorithms. Open-source implementation in pure Rust: https://github.com/continuum-ai/continuum
```

### License
- Select: **`arXiv.org perpetual, non-exclusive license to distribute this article`** (Standard & recommended)
