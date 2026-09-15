import torch
import random
from continuum.memory.adaptive_memory import AdaptiveMemory, AdaptiveMemoryConfig
from continuum.memory.cold_memory import ColdCandidateMemory
from continuum.memory.adaptive_memory import RetentionDecision
from continuum.state.temporal_state import TemporalState, TemporalStateConfig

def trace_evictions(seed):
    print(f"\n================ Seed {seed} ================")
    torch.manual_seed(seed)
    random.seed(seed)
    emb_dim = 32
    state_dim = 32
    stream_length = 3000
    
    n_clusters = 3
    clusters = [torch.randn(emb_dim) for _ in range(n_clusters)]
    for c in clusters:
        c /= torch.norm(c, p=2)

    subsystem = torch.randn(emb_dim)
    for c in clusters:
        subsystem -= torch.dot(subsystem, c) * c
    subsystem /= torch.norm(subsystem)

    root_id = 100
    vec_root = 0.85 * subsystem + 0.15 * torch.randn(emb_dim)
    vec_root /= torch.norm(vec_root)

    b_id = 1550
    v_b = 0.80 * subsystem + 0.20 * torch.randn(emb_dim)
    v_b /= torch.norm(v_b)

    chain_nodes = {root_id: vec_root, b_id: v_b}

    k_hot = 250
    k_cold = 500
    cold = ColdCandidateMemory(capacity=k_cold, embedding_dim=emb_dim, state_dim=state_dim)
    am = AdaptiveMemory(
        AdaptiveMemoryConfig(
            embedding_dim=emb_dim,
            state_dim=state_dim,
            capacity=k_hot,
            seed=seed,
            alpha_surprise=0.2,
            beta_novelty=0.2,
            gamma_causal=0.2,
            delta_retrieval=0.2,
            epsilon_uncertainty=0.2,
        )
    )
    t_cfg = TemporalStateConfig(input_size=emb_dim, hidden_size=state_dim)
    temporal_model = TemporalState(t_cfg)
    h_state = temporal_model.initial_state(1)

    root_admitted_hot = False
    root_evicted_hot = None
    root_evicted_cold = None

    b_admitted_hot = False
    b_evicted_hot = None
    b_evicted_cold = None

    for t in range(stream_length):
        if t in chain_nodes:
            emb = chain_nodes[t]
        else:
            c_idx = (t // 25) % n_clusters
            emb = clusters[c_idx] + 0.03 * torch.randn(emb_dim)
            emb /= torch.norm(emb, p=2)

        h_state = temporal_model.step(emb.unsqueeze(0), h_state).state
        rec = am.observe(
            event_id=t,
            timestamp=float(t),
            embedding=emb,
            temporal_state=h_state[0],
            cold_memory=cold,
        )

        if t == root_id and rec.decision == RetentionDecision.KEEP:
            root_admitted_hot = True
        if t == b_id and rec.decision == RetentionDecision.KEEP:
            b_admitted_hot = True

        if root_admitted_hot and root_evicted_hot is None:
            if not any(r.event_id == root_id for r in am.records):
                root_evicted_hot = t
        if root_evicted_hot is not None and root_evicted_cold is None:
            if not any(r.event_id == root_id for r in cold.records):
                root_evicted_cold = t

        if b_admitted_hot and b_evicted_hot is None:
            if not any(r.event_id == b_id for r in am.records):
                b_evicted_hot = t
        if b_evicted_hot is not None and b_evicted_cold is None:
            if not any(r.event_id == b_id for r in cold.records):
                b_evicted_cold = t

    print(f"Root (100): admitted_hot={root_admitted_hot}, evicted_from_hot_at={root_evicted_hot}, evicted_from_cold_at={root_evicted_cold}")
    print(f"B (1550): admitted_hot={b_admitted_hot}, evicted_from_hot_at={b_evicted_hot}, evicted_from_cold_at={b_evicted_cold}")
    print(f"Total cold evictions during stream: {len(cold.records)} currently in cold")

for s in [101, 202, 303]:
    trace_evictions(s)
