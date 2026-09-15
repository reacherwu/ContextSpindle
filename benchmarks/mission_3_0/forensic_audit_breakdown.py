import os
import random
import math
import torch
from torch import Tensor
from benchmarks.mission_3_0.acm_architecture import ACMArchitecture
from continuum.memory.adaptive_memory import RetentionDecision

def run_forensic_audit():
    seeds = [101, 202, 303]
    emb_dim = 32
    state_dim = 32
    stream_length = 3000
    t_A_long = 100
    t_A_mid = 2000
    n_clusters = 3

    for seed in seeds:
        print("=" * 100)
        print(f"AUDIT FOR SEED: {seed}")
        print("=" * 100)

        torch.manual_seed(seed)
        random.seed(seed)

        # 1. Setup data generation identical to benchmark_e2e_validation.py
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

        tracking = {
            t_A_long: {"admitted_hot": False, "evicted_to_cold": False, "eviction_step_from_hot": None, "admitted_cold": False, "evicted_from_cold": False, "eviction_step_from_cold": None, "reason_cold_evict": None},
            t_A_mid: {"admitted_hot": False, "evicted_to_cold": False, "eviction_step_from_hot": None, "admitted_cold": False, "evicted_from_cold": False, "eviction_step_from_cold": None, "reason_cold_evict": None},
        }

        causal_active = False

        original_evict_oldest = model.cold_memory._evict_oldest
        def hooked_evict_oldest():
            if len(model.cold_memory.records) == 0:
                return
            evict_idx = -1
            with torch.no_grad():
                if model.cold_memory.embeddings_tensor is not None and len(model.cold_memory.records) > 1:
                    sim_mat = torch.matmul(model.cold_memory.embeddings_tensor, model.cold_memory.embeddings_tensor.T)
                    sim_mat.fill_diagonal_(-1.0)
                    max_sims, _ = torch.max(sim_mat, dim=1)
                    redundant_mask = max_sims >= model.cold_memory.sim_thresh
                    if redundant_mask.any():
                        for i in range(len(model.cold_memory.records)):
                            if redundant_mask[i]:
                                evict_idx = i
                                evict_reason = "subspace_redundancy"
                                break
            if evict_idx == -1:
                scores = []
                for r in model.cold_memory.records:
                    st_norm = float(torch.norm(r.state_fingerprint, p=2).item())
                    scores.append(0.4 * r.importance_at_eviction + 0.6 * st_norm)
                evict_idx = int(torch.tensor(scores).argmin().item())
                evict_reason = "dynamical_norm_lru"

            evicted_record = model.cold_memory.records[evict_idx]
            if evicted_record.event_id in tracking:
                tracking[evicted_record.event_id]["evicted_from_cold"] = True
                tracking[evicted_record.event_id]["eviction_step_from_cold"] = model.step_count
                tracking[evicted_record.event_id]["reason_cold_evict"] = evict_reason

            original_evict_oldest()

        model.cold_memory._evict_oldest = hooked_evict_oldest

        # Stream ingestion
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

            if t in tracking:
                if rec.decision == RetentionDecision.KEEP:
                    tracking[t]["admitted_hot"] = True
                elif rec.decision == RetentionDecision.DISCARD:
                    tracking[t]["admitted_cold"] = True

            # Check if target was evicted from hot memory in subsequent steps
            for target_t in [t_A_long, t_A_mid]:
                if target_t < t and tracking[target_t]["admitted_hot"] and not tracking[target_t]["evicted_to_cold"]:
                    in_hot = any(r.event_id == target_t for r in model.hot_memory.records)
                    if not in_hot:
                        tracking[target_t]["evicted_to_cold"] = True
                        tracking[target_t]["eviction_step_from_hot"] = t
                        in_cold = any(r.event_id == target_t for r in model.cold_memory.records)
                        if in_cold:
                            tracking[target_t]["admitted_cold"] = True

        print(f"\n[1] EVENT FATE TRACKING (Hot vs Cold Memory Status at t=3000):")
        for target_t, name in [(t_A_long, "A_long (t=100)"), (t_A_mid, "A_mid (t=2000)")]:
            in_hot = any(r.event_id == target_t for r in model.hot_memory.records)
            in_cold = any(r.event_id == target_t for r in model.cold_memory.records)
            print(f"  * {name}: In Hot={in_hot}, In Cold={in_cold}")
            print(f"    Details: {tracking[target_t]}")

        # Terminal query
        emb_unsq = vec_D.detach().float().unsqueeze(0)
        model.h_state = model.temporal_model.step(emb_unsq, model.h_state).state
        cur_h = model.h_state[0]

        print(f"\n[2] COLD MEMORY RETRIEVAL & COSINE PRE-FILTERING (Capacity = {model.cold_memory.capacity}, Count = {len(model.cold_memory.records)}):")
        all_cold_sims = []
        for idx, r in enumerate(model.cold_memory.records):
            c_emb = r.compressed_embedding
            sim = float(torch.dot(c_emb, vec_D).item())
            all_cold_sims.append((idx, r.event_id, r.timestamp, sim, r.provenance_summary))

        all_cold_sims.sort(key=lambda x: x[3], reverse=True)

        for target_t, name in [(t_A_long, "A_long (t=100)"), (t_A_mid, "A_mid (t=2000)")]:
            found_ranks = [(rank+1, sim) for rank, (idx, eid, ts, sim, prov) in enumerate(all_cold_sims) if eid == target_t]
            if found_ranks:
                print(f"  * {name}: Present in Cold Memory. Cosine Rank: {found_ranks[0][0]} / {len(all_cold_sims)}, Cosine Sim: {found_ranks[0][1]:.4f}")
            else:
                print(f"  * {name}: ABSENT from Cold Memory.")

        # Top 100 candidate retrieval as done in query_causal
        candidates = model.cold_memory.search(vec_D, top_k=min(100, len(model.cold_memory.records)))
        
        scored_candidates = []
        for cand, sim_val in candidates:
            score, comps = model.revision_engine._compute_revision_score_with_components(
                cand, vec_D, cur_h, float(model.step_count)
            )
            cat = "A_long" if cand.event_id == t_A_long else "A_mid" if cand.event_id == t_A_mid else "TRAP" if cand.event_id in trap_steps else "DISTRACTOR" if cand.event_id in dist_steps else "BACKGROUND"
            scored_candidates.append({
                "event_id": cand.event_id,
                "timestamp": cand.timestamp,
                "category": cat,
                "score": score,
                "sim": comps["sim"],
                "w_sim": model.rev_config.w_sim * comps["sim"],
                "state_compat": comps["state_compat"],
                "w_state": model.rev_config.w_state_compat * comps["state_compat"],
                "temporal_compat": comps["temporal_compat"],
                "w_temporal": model.rev_config.w_temporal_compat * comps["temporal_compat"],
                "provenance": comps["provenance_compat"],
                "w_prov": model.rev_config.w_provenance_compat * comps["provenance_compat"],
                "delta_t": abs(float(model.step_count) - cand.timestamp),
                "provenance_summary": cand.provenance_summary,
            })

        scored_candidates.sort(key=lambda x: x["score"], reverse=True)

        print(f"\n[3] TOP-10 RETRIEVED CANDIDATES (Post-R3 Scoring):")
        header = f"{'Rank':4s} | {'ID':4s} | {'Cat':10s} | {'Score':7s} | {'Sim':6s} | {'StCmp':6s} | {'TmpCmp':6s} | {'Prv':5s} | {'w*Sim':6s} | {'w*St':6s} | {'w*Tmp':6s} | {'w*Prv':6s} | {'Δt':5s}"
        print(header)
        print("-" * len(header))
        for rk, item in enumerate(scored_candidates[:10]):
            print(f"{rk+1:4d} | {item['event_id']:4d} | {item['category']:10s} | {item['score']:7.4f} | {item['sim']:6.4f} | {item['state_compat']:6.4f} | {item['temporal_compat']:6.4f} | {item['provenance']:5.2f} | {item['w_sim']:6.4f} | {item['w_state']:6.4f} | {item['w_temporal']:6.4f} | {item['w_prov']:6.4f} | {item['delta_t']:5.0f}")

        print(f"\n[4] TRUE CAUSAL ROOTS DETAILED AUDIT:")
        for target_t, name in [(t_A_long, "A_long (t=100)"), (t_A_mid, "A_mid (t=2000)")]:
            matched = [item for item in scored_candidates if item["event_id"] == target_t]
            if matched:
                item = matched[0]
                rank = scored_candidates.index(item) + 1
                print(f"  * {name} -> R3 Score Rank: {rank} / {len(scored_candidates)}")
                print(f"    Total Score: {item['score']:.4f} (Restore Threshold: {model.rev_config.theta_restore})")
                print(f"    Breakdown: sim={item['sim']:.4f} (w={item['w_sim']:.4f}), state_compat={item['state_compat']:.4f} (w={item['w_state']:.4f}), temporal_compat={item['temporal_compat']:.4f} (w={item['w_temporal']:.4f}), prov={item['provenance']:.2f} (w={item['w_prov']:.4f})")
                print(f"    Temporal dynamics: delta_t={item['delta_t']:.0f}")
            else:
                in_cold_recs = [r for r in model.cold_memory.records if r.event_id == target_t]
                if in_cold_recs:
                    cand = in_cold_recs[0]
                    score, comps = model.revision_engine._compute_revision_score_with_components(
                        cand, vec_D, cur_h, float(model.step_count)
                    )
                    print(f"  * {name} -> EXCLUDED FROM TOP-100 COSINE SEARCH! (In Cold Memory, but sim was outside top 100)")
                    print(f"    Sim: {comps['sim']:.4f}, State: {comps['state_compat']:.4f}, Temporal: {comps['temporal_compat']:.4f}, Theoretical Score: {score:.4f}")
                else:
                    print(f"  * {name} -> COMPLETELY ABSENT (Evicted from Cold Memory prior to query).")

        print("\n")

if __name__ == "__main__":
    run_forensic_audit()
