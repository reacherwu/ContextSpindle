import torch
import random
from continuum.memory.adaptive_memory import AdaptiveMemory, AdaptiveMemoryConfig
from continuum.memory.cold_memory import ColdCandidateMemory
from continuum.memory.revision_engine import RevisionConfig, RevisionEngine
from continuum.state.temporal_state import TemporalState, TemporalStateConfig

def diagnose(seed):
    torch.manual_seed(seed)
    random.seed(seed)
    emb_dim = 32
    state_dim = 32
    stream_length = 3000
    n_distractors = 500

    n_clusters = 3
    clusters = [torch.randn(emb_dim) for _ in range(n_clusters)]
    for c in clusters: c /= torch.norm(c, p=2)
    subsystem = torch.randn(emb_dim)
    for c in clusters: subsystem -= torch.dot(subsystem, c) * c
    subsystem /= torch.norm(subsystem)

    root_id = 100
    vec_root = 0.85 * subsystem + 0.15 * torch.randn(emb_dim)
    vec_root /= torch.norm(vec_root)
    vec_D = 0.85 * subsystem + 0.15 * torch.randn(emb_dim)
    vec_D /= torch.norm(vec_D)

    available = [t for t in range(200, stream_length - 50) if t != root_id]
    chosen = random.sample(available, min(n_distractors, len(available)))
    distractor_indices = set(chosen)

    t_cfg = TemporalStateConfig(input_size=emb_dim, hidden_size=state_dim)
    temporal_model = TemporalState(t_cfg)
    h_state = temporal_model.initial_state(1)
    cold = ColdCandidateMemory(capacity=500, embedding_dim=emb_dim, state_dim=state_dim)
    am = AdaptiveMemory(AdaptiveMemoryConfig(capacity=250, embedding_dim=emb_dim, state_dim=state_dim, seed=seed))
    engine = RevisionEngine(RevisionConfig(theta_trigger=0.45, theta_restore=0.25, max_restorations_per_trigger=1))

    for t in range(stream_length):
        if t == root_id: emb = vec_root
        elif t in distractor_indices:
            emb = 0.35 * vec_D + 0.65 * torch.randn(emb_dim)
            emb /= torch.norm(emb, p=2)
        else:
            c_idx = (t // 25) % n_clusters
            emb = clusters[c_idx] + 0.03 * torch.randn(emb_dim)
            emb /= torch.norm(emb, p=2)
        h_state = temporal_model.step(emb.unsqueeze(0), h_state).state
        am.observe(t, float(t), emb, h_state[0], cold_memory=cold)

    print(f"Seed {seed}:")
    print(f"  Root (100) in hot: {any(r.event_id == root_id for r in am.records)}")
    print(f"  Root (100) in cold: {any(r.event_id == root_id for r in cold.records)}")
    if len(cold.records) > 0:
        print(f"  Oldest in cold: {cold.records[0].event_id}, Newest in cold: {cold.records[-1].event_id}")

for s in [101, 202, 303]:
    diagnose(s)
