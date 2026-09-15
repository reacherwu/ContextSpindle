import torch
import random
from continuum.memory.adaptive_memory import AdaptiveMemory, AdaptiveMemoryConfig
from continuum.memory.cold_memory import ColdCandidateMemory
from continuum.memory.revision_engine import RevisionConfig, RevisionEngine
from continuum.state.temporal_state import TemporalState, TemporalStateConfig

def check_seed(seed):
    print(f"\n--- Checking Seed {seed} ---")
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

    # In chain_length_scaling.py:
    # num_intermediates = chain_length - 2 = 1 (for L=3)
    # step_gap = (3000 - 100) // (1 + 1) = 1450
    # hop_t = 100 + 1 * 1450 = 1550
    b_id = 1550
    decay = 0.80
    v_b = decay * subsystem + (1.0 - decay) * torch.randn(emb_dim)
    v_b /= torch.norm(v_b)

    chain_nodes = {root_id: vec_root, b_id: v_b}

    vec_terminal = 0.85 * subsystem + 0.15 * torch.randn(emb_dim)
    vec_terminal /= torch.norm(vec_terminal)

    t_cfg = TemporalStateConfig(input_size=emb_dim, hidden_size=state_dim)
    temporal_model = TemporalState(t_cfg)
    h_state = temporal_model.initial_state(1)

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

    evicted_times = {}
    for t in range(stream_length):
        if t in chain_nodes:
            emb = chain_nodes[t]
        else:
            c_idx = (t // 25) % n_clusters
            emb = clusters[c_idx] + 0.03 * torch.randn(emb_dim)
            emb /= torch.norm(emb, p=2)

        h_state = temporal_model.step(emb.unsqueeze(0), h_state).state
        am.observe(
            event_id=t,
            timestamp=float(t),
            embedding=emb,
            temporal_state=h_state[0],
            cold_memory=cold,
        )

    print(f"Cold memory size at t={stream_length}: {len(cold.records)}")
    oldest_in_cold = cold.records[0].event_id if cold.records else None
    newest_in_cold = cold.records[-1].event_id if cold.records else None
    print(f"Oldest in cold: {oldest_in_cold}, Newest in cold: {newest_in_cold}")
    print(f"Is root (100) in hot? {any(r.event_id == 100 for r in am.records)}")
    print(f"Is root (100) in cold? {any(r.event_id == 100 for r in cold.records)}")
    print(f"Is B (1550) in hot? {any(r.event_id == 1550 for r in am.records)}")
    print(f"Is B (1550) in cold? {any(r.event_id == 1550 for r in cold.records)}")

for s in [101, 202, 303]:
    check_seed(s)
