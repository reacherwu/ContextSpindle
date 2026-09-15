import os
import random
import math
import torch
from benchmarks.mission_3_0.acm_architecture import ACMArchitecture
from continuum.memory.adaptive_memory import RetentionDecision

def generate_report_tables():
    seeds = [101, 202, 303]
    emb_dim = 32
    state_dim = 32
    stream_length = 3000
    t_A_long = 100
    t_A_mid = 2000
    n_clusters = 3

    results = {}

    for seed in seeds:
        torch.manual_seed(seed)
        random.seed(seed)

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

        causal_active = False
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

            model.observe(event_id=t, timestamp=float(t), embedding=emb)

        emb_unsq = vec_D.detach().float().unsqueeze(0)
        model.h_state = model.temporal_model.step(emb_unsq, model.h_state).state
        cur_h = model.h_state[0]

        # All cold memory cosine ranking
        all_cold_sims = []
        for idx, r in enumerate(model.cold_memory.records):
            sim = float(torch.dot(r.compressed_embedding, vec_D).item())
            all_cold_sims.append((idx, r, sim))
        all_cold_sims.sort(key=lambda x: x[2], reverse=True)

        # Candidates scored in top 100
        candidates = model.cold_memory.search(vec_D, top_k=min(100, len(model.cold_memory.records)))
        scored = []
        for cand, sim_val in candidates:
            score, comps = model.revision_engine._compute_revision_score_with_components(
                cand, vec_D, cur_h, float(model.step_count)
            )
            cat = "A_long" if cand.event_id == t_A_long else "A_mid" if cand.event_id == t_A_mid else "TRAP" if cand.event_id in trap_steps else "DISTRACTOR" if cand.event_id in dist_steps else "BACKGROUND"
            scored.append((cand.event_id, cand.timestamp, cat, score, comps))
        scored.sort(key=lambda x: x[3], reverse=True)

        results[seed] = {
            "all_cold_sims": all_cold_sims,
            "scored": scored,
            "cur_h": cur_h,
            "model": model,
        }

    for seed in seeds:
        print(f"\n=================== SUMMARY FOR SEED {seed} ===================")
        scored = results[seed]["scored"]
        all_cold_sims = results[seed]["all_cold_sims"]
        cur_h = results[seed]["cur_h"]
        model = results[seed]["model"]

        # Print Top-10
        print(f"Top 10 Retrieved for Seed {seed}:")
        for rank, (eid, ts, cat, score, comps) in enumerate(scored[:10]):
            dt = 3000 - ts
            print(f"Rank {rank+1:2d} | ID: {eid:4d} | Cat: {cat:10s} | Score: {score:.4f} | Sim: {comps['sim']:.4f} (w={0.4*comps['sim']:.4f}) | St: {comps['state_compat']:.4f} (w={0.3*comps['state_compat']:.4f}) | Tmp: {comps['temporal_compat']:.4f} (w={0.2*comps['temporal_compat']:.4f}) | dt: {dt:4.0f}")

        # Check A_long and A_mid
        for target_id, target_name in [(100, "A_long (t=100)"), (2000, "A_mid (t=2000)")]:
            # find in all_cold_sims
            cold_rk = [i+1 for i, item in enumerate(all_cold_sims) if item[1].event_id == target_id]
            cold_sim = [item[2] for item in all_cold_sims if item[1].event_id == target_id]
            
            # find in scored
            scored_rk = [i+1 for i, item in enumerate(scored) if item[0] == target_id]
            if scored_rk:
                rk = scored_rk[0]
                item = scored[rk-1]
                comps = item[4]
                dt = 3000 - target_id
                print(f"{target_name}: Stage 1 Cosine Rank={cold_rk[0]}/500 (sim={cold_sim[0]:.4f}) | Stage 2 R3 Rank={rk}/100 | Score={item[3]:.4f} | Sim={comps['sim']:.4f} | St={comps['state_compat']:.4f} | Tmp={comps['temporal_compat']:.4f} | dt={dt}")
            else:
                # compute theoretical
                rec = [item[1] for item in all_cold_sims if item[1].event_id == target_id][0]
                score, comps = model.revision_engine._compute_revision_score_with_components(
                    rec, vec_D, cur_h, 3000.0
                )
                dt = 3000 - target_id
                print(f"{target_name}: Stage 1 Cosine Rank={cold_rk[0]}/500 (sim={cold_sim[0]:.4f}) -> ELIMINATED AT STAGE 1! | Theoretical Stage 2 Score={score:.4f} | Sim={comps['sim']:.4f} | St={comps['state_compat']:.4f} | Tmp={comps['temporal_compat']:.4f} | dt={dt}")

if __name__ == "__main__":
    generate_report_tables()
