# Agent A: Competitor Benchmark Report (Real-Text Corpora)
**Benchmark Date:** 2026-09-14  **Protocol:** Strictly identical real-text stream inputs and identical subword dense embeddings across all baselines.

| Corpus / Scenario | Model Architecture | Active Memory Slots | Bounded O(1)? | Query Latency (μs) | Root Rank | Recall@1 | Recall@5 |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| **AIOps_Log_Incident** | Continuum_Engine | 750 | Yes | 10507.2 | #10 | 0% | 0% |
| **AIOps_Log_Incident** | Vector_RAG_FullStore | 3000 | No (O(T)) | 348.5 | #999 | 0% | 0% |
| **AIOps_Log_Incident** | Sliding_FIFO | 750 | Yes | 56.1 | #999 | 0% | 0% |
| **AIOps_Log_Incident** | Fixed_LRU | 750 | Yes | 61.5 | #999 | 0% | 0% |
| **GitHub_Agent_Trajectory** | Continuum_Engine | 49 | Yes | 706.5 | #999 | 0% | 0% |
| **GitHub_Agent_Trajectory** | Vector_RAG_FullStore | 100 | No (O(T)) | 19.2 | #999 | 0% | 0% |
| **GitHub_Agent_Trajectory** | Sliding_FIFO | 50 | Yes | 8.5 | #999 | 0% | 0% |
| **GitHub_Agent_Trajectory** | Fixed_LRU | 50 | Yes | 6.2 | #999 | 0% | 0% |
| **Persona_Lifelong_Dialogue** | Continuum_Engine | 499 | Yes | 6737.2 | #1 | ✅ 100% | ✅ 100% |
| **Persona_Lifelong_Dialogue** | Vector_RAG_FullStore | 2000 | No (O(T)) | 205.1 | #1 | ✅ 100% | ✅ 100% |
| **Persona_Lifelong_Dialogue** | Sliding_FIFO | 500 | Yes | 42.8 | #999 | 0% | 0% |
| **Persona_Lifelong_Dialogue** | Fixed_LRU | 500 | Yes | 46.5 | #999 | 0% | 0% |
