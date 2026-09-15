import os
import random
import math
import torch
from benchmarks.mission_3_0.acm_architecture import ACMArchitecture
from continuum.memory.adaptive_memory import RetentionDecision

def detailed_diagnostics():
    seeds = [101, 202, 303]
    emb_dim = 32
    state_dim = 32
    stream_length = 3000
    t_A_long = 100
    t_A_mid = 2000
    n_clusters = 3

    for seed in seeds:
        print("=" * 100)
        print(f"DEEP DIVE INVESTIGATION: SEED {seed}")
        print("=" * 100)

        torch.manual_seed(seed)
        random.seed(seed)

        # Basis
        basis = []
        for _ in range(n_clusters):
            v = torch.randn(emb_dim)
            for b in basis:
                v -= torch.dot(v, b) * b
            v /= torch.norm(v, p=2)
            basis.append(v)
        clusters = basis[:n_clusters]

        v_x = torch.randn(emb_dim)
        for b in basis:
            v_x -= torch.dot(v_x, b) * b
        v_x /= torch.norm(v_x, p=2)
        basis.append(v_x)

        vec_A_long = 0.85 * v_x + 0.15 * torch.randn(emb_dim)
        vec_A_long /= torch.norm(vec_A_long, p=2)

        vec_A_mid = 0.85 * v_x + 0.15 * torch.randn(emb_dim)
        vec_A_mid /= torch.norm(vec_A_mid, p=2)

        vec_D = 0.85 * v_x + 0.15 * torch.randn(emb_dim)
        vec_D /= torch.norm(vec_D, p=2)

        print(f"Direct raw cosine similarities with vec_D at creation:")
        print(f"  dot(vec_A_long, vec_D): {torch.dot(vec_A_long, vec_D).item():.4f}")
        print(f"  dot(vec_A_mid,  vec_D): {torch.dot(vec_A_mid,  vec_D).item():.4f}")
        print(f"  dot(v_x,        vec_D): {torch.dot(v_x,        vec_D).item():.4f}")
        for c_i, c_v in enumerate(clusters):
            print(f"  dot(cluster[{c_i}], vec_D): {torch.dot(c_v, vec_D).item():.4f}")

        trap_steps = set(range(300, 1800, 30))
        trap_vectors = {}
        for t in trap_steps:
            v = torch.randn(emb_dim)
            for b in basis:
                v -= torch.dot(v, b) * b
            trap_vectors[t] = v / torch.norm(v, p=2)

        dist_steps = set(range(500, stream_length - 50, 45)) - trap_steps - {t_A_long, t_A_mid}
        dist_vectors = {}
        for t in dist_steps:
            v = 0.40 * vec_D + 0.60 * torch.randn(emb_dim)
            dist_vectors[t] = v / torch.norm(v, p=2)

        model = ACMArchitecture(emb_dim=emb_dim, state_dim=state_dim, k_hot=250, k_cold=500, seed=seed)

        evictions_count = {"subspace": 0, "norm": 0}
        total_archived = 0

        original_archive = model.cold_memory.archive
        def hooked_archive(*args, **kwargs):
            nonlocal total_archived
            total_archived += 1
            return original_archive(*args, **kwargs)
        model.cold_memory.archive = hooked_archive

        original_evict = model.cold_memory._evict_oldest
        def hooked_evict():
            # Check reason
            if len(model.cold_memory.records) > 1 and model.cold_memory.embeddings_tensor is not None:
                sim_mat = torch.matmul(model.cold_memory.embeddings_tensor, model.cold_memory.embeddings_tensor.T)
                sim_mat.fill_diagonal_(-1.0)
                max_sims, _ = torch.max(sim_mat, dim=1)
                if (max_sims >= model.cold_memory.sim_thresh).any():
                    evictions_count["subspace"] += 1
                else:
                    evictions_count["norm"] += 1
            else:
                evictions_count["norm"] += 1
            original_evict()
        model.cold_memory._evict_oldest = hooked_evict

        causal_active = False
        saved_step_states = {}

        for t in range(stream_length):
            if t == t_A_long:
                emb = vec_A_long
                causal_active = True
            elif t == t_A_mid:
                emb = vec_A_mid
                causal_active = True
            elif t in trap_steps:
                emb = trap_vectors[t]
            elif t in dist_steps:
                emb = dist_vectors[t]
            else:
                c_idx = (t // 25) % n_clusters
                base_vec = clusters[c_idx].clone()
                if causal_active:
                    drift_factor = min(0.30, 0.04 + 0.0001 * (t - t_A_long))
                    base_vec = base_vec + drift_factor * v_x
                base_vec = base_vec + 0.03 * torch.randn(emb_dim)
                emb = base_vec / torch.norm(base_vec, p=2)

            rec = model.observe(event_id=t, timestamp=float(t), embedding=emb)
            if t in (t_A_long, t_A_mid, 500, 1000, 2000, 2500, 2900, 2950):
                saved_step_states[t] = model.h_state[0].clone()

        print(f"\nCold Memory Statistics:")
        print(f"  Total events archived to Cold: {total_archived}")
        print(f"  Total evictions: {evictions_count['subspace'] + evictions_count['norm']} (Subspace redundancy: {evictions_count['subspace']}, Norm/LRU: {evictions_count['norm']})")
        print(f"  Final Cold memory records count: {len(model.cold_memory.records)}")

        # Query symptom
        emb_unsq = vec_D.detach().float().unsqueeze(0)
        model.h_state = model.temporal_model.step(emb_unsq, model.h_state).state
        cur_h = model.h_state[0]

        # Check state norm and similarities with cur_h
        print(f"\nRNN Hidden State Dynamics:")
        print(f"  Norm of cur_h at query (t=3000): {torch.norm(cur_h, p=2).item():.4f}")
        for st_t, st_h in saved_step_states.items():
            cos_h = torch.dot(st_h, cur_h) / (torch.norm(st_h, p=2) * torch.norm(cur_h, p=2) + 1e-8)
            print(f"  State at t={st_t:4d}: norm={torch.norm(st_h, p=2).item():.4f}, cos_sim with cur_h={cos_h.item():.4f}")

        # Check cold memory records categories
        cats = {"A_long": 0, "A_mid": 0, "TRAP": 0, "DISTRACTOR": 0, "BACKGROUND": 0}
        for r in model.cold_memory.records:
            if r.event_id == t_A_long:
                cats["A_long"] += 1
            elif r.event_id == t_A_mid:
                cats["A_mid"] += 1
            elif r.event_id in trap_steps:
                cats["TRAP"] += 1
            elif r.event_id in dist_steps:
                cats["DISTRACTOR"] += 1
            else:
                cats["BACKGROUND"] += 1
        print(f"\nCold Memory Breakdown by Event Type (Total {len(model.cold_memory.records)}):")
        for cat, cnt in cats.items():
            print(f"  {cat:12s}: {cnt}")

        # Effective tau calculation demonstration
        print(f"\nEffective Tau and Temporal Penalty Analysis:")
        for target_t, name in [(t_A_long, "A_long (t=100)"), (t_A_mid, "A_mid (t=2000)")]:
            recs = [r for r in model.cold_memory.records if r.event_id == target_t]
            if recs:
                cand = recs[0]
                score, comps = model.revision_engine._compute_revision_score_with_components(
                    cand, vec_D, cur_h, float(model.step_count)
                )
                csm = model.rev_config.w_sim * comps["sim"] + model.rev_config.w_state_compat * comps["state_compat"]
                eff_tau = model.rev_config.temporal_decay_tau * (1.0 + model.revision_engine.alpha * csm)
                delta_t = abs(float(model.step_count) - cand.timestamp)
                print(f"  {name}:")
                print(f"    sim={comps['sim']:.4f}, state_compat={comps['state_compat']:.4f} -> csm={csm:.4f}")
                print(f"    effective_tau = 1000 * (1 + 3 * {csm:.4f}) = {eff_tau:.1f}")
                print(f"    delta_t = {delta_t:.0f}")
                print(f"    temporal_compat = exp(-{delta_t:.0f} / {eff_tau:.1f}) = {comps['temporal_compat']:.4f}")
                print(f"    w_temporal * temporal_compat = {model.rev_config.w_temporal_compat * comps['temporal_compat']:.4f}")

        # Let's do the same for a recent background event and distractor
        # Top ranked candidate in query_causal
        candidates = model.cold_memory.search(vec_D, top_k=min(100, len(model.cold_memory.records)))
        top_cand, _ = candidates[0]
        score, comps = model.revision_engine._compute_revision_score_with_components(
            top_cand, vec_D, cur_h, float(model.step_count)
        )
        csm = model.rev_config.w_sim * comps["sim"] + model.rev_config.w_state_compat * comps["state_compat"]
        eff_tau = model.rev_config.temporal_decay_tau * (1.0 + model.revision_engine.alpha * csm)
        delta_t = abs(float(model.step_count) - top_cand.timestamp)
        print(f"  Top Candidate (ID {top_cand.event_id}, t={top_cand.timestamp}):")
        print(f"    sim={comps['sim']:.4f}, state_compat={comps['state_compat']:.4f} -> csm={csm:.4f}")
        print(f"    effective_tau = 1000 * (1 + 3 * {csm:.4f}) = {eff_tau:.1f}")
        print(f"    delta_t = {delta_t:.0f}")
        print(f"    temporal_compat = exp(-{delta_t:.0f} / {eff_tau:.1f}) = {comps['temporal_compat']:.4f}")
        print(f"    w_temporal * temporal_compat = {model.rev_config.w_temporal_compat * comps['temporal_compat']:.4f}")

if __name__ == "__main__":
    detailed_diagnostics()
