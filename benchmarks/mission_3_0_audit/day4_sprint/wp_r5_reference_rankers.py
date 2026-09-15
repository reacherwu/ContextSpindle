"""WP-R5: Reference Causal Rankers & Stage 1 Pre-Filter Truncation Audit."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import torch
from torch import Tensor

from benchmarks.mission_3_0_audit.audit_pipeline import generate_evaluation_stream
from benchmarks.mission_3_0.acm_architecture import ACMArchitecture


def run_wp_r5() -> dict[str, Any]:
    seeds = [101, 202, 303]

    rankers = {
        "R-A_Sim_only": lambda c: c["sim"],
        "R-B_Sim_plus_State": lambda c: 0.57 * c["sim"] + 0.43 * c["state_compat"],
        "R-C_Sim_plus_Temporal": lambda c: 0.67 * c["sim"] + 0.33 * c["temporal_compat"],
        "R-D_Sim_plus_State_plus_Temporal": lambda c: 0.44 * c["sim"] + 0.33 * c["state_compat"] + 0.22 * c["temporal_compat"],
        "R-E_Sim_plus_CSM_Gated": lambda c: c["sim"] * (1.0 if c["sim"] >= 0.50 else c["temporal_compat"]),
        "R-F_Full_Engine": lambda c: 0.40 * c["sim"] + 0.30 * c["state_compat"] + 0.20 * c["temporal_compat"] + 0.10 * c["provenance_compat"],
    }

    stage1_k_values = [50, 100, 200, 500]

    results: dict[str, Any] = {
        "rankers": {
            name: {
                "top5_any_recall": 0.0,
                "top5_both_recall": 0.0,
                "mean_frr": 0.0,
                "a_long_mean_rank": 0.0,
                "a_mid_mean_rank": 0.0,
                "seed_results": {},
            }
            for name in rankers
        },
        "stage1_truncation_audit": {
            k: {
                "a_long_passed_rate": 0.0,
                "a_mid_passed_rate": 0.0,
                "seed_ranks": {},
            }
            for k in stage1_k_values
        },
    }

    for s in seeds:
        stream, vec_D, t_A_long, t_A_mid, t_R, t_F = generate_evaluation_stream(s)
        model = ACMArchitecture(emb_dim=32, state_dim=32, k_hot=250, k_cold=500, seed=s)

        for t, emb, _ in stream:
            model.observe(t, float(t), emb)

        cur_h = model.h_state[0]
        recs = model.cold_memory.records
        t_curr = float(len(stream))

        # 1. Audit Stage 1 Pre-Filter (raw cosine similarity search)
        raw_sim_ranked = []
        for r in recs:
            raw_sim = torch.dot(r.compressed_embedding, vec_D).item()
            raw_sim_ranked.append((raw_sim, r.event_id))
        raw_sim_ranked.sort(key=lambda x: x[0], reverse=True)

        stage1_rank_long = next(i + 1 for i, (_, eid) in enumerate(raw_sim_ranked) if eid == t_A_long)
        stage1_rank_mid = next(i + 1 for i, (_, eid) in enumerate(raw_sim_ranked) if eid == t_A_mid)

        for k in stage1_k_values:
            top_k_eids = {eid for _, eid in raw_sim_ranked[:k]}
            long_pass = t_A_long in top_k_eids
            mid_pass = t_A_mid in top_k_eids

            results["stage1_truncation_audit"][k]["a_long_passed_rate"] += (1.0 if long_pass else 0.0) / len(seeds)
            results["stage1_truncation_audit"][k]["a_mid_passed_rate"] += (1.0 if mid_pass else 0.0) / len(seeds)
            results["stage1_truncation_audit"][k]["seed_ranks"][s] = {
                "rank_a_long": stage1_rank_long,
                "rank_a_mid": stage1_rank_mid,
                "a_long_passed": long_pass,
                "a_mid_passed": mid_pass,
            }

        # 2. Audit Reference Rankers across all Cold Memory records
        record_components = []
        for r in recs:
            _, comps = model.revision_engine._compute_revision_score_with_components(
                r, vec_D, cur_h, t_curr
            )
            record_components.append((r.event_id, comps))

        for name, fn in rankers.items():
            scored = []
            for eid, comps in record_components:
                sc = fn(comps)
                scored.append((sc, eid))
            scored.sort(key=lambda x: x[0], reverse=True)

            top5_eids = [eid for _, eid in scored[:5]]
            rank_long = next((i + 1 for i, (_, eid) in enumerate(scored) if eid == t_A_long), 999)
            rank_mid = next((i + 1 for i, (_, eid) in enumerate(scored) if eid == t_A_mid), 999)

            hit_long = 1 if t_A_long in top5_eids else 0
            hit_mid = 1 if t_A_mid in top5_eids else 0
            any_hit = 1.0 if (hit_long or hit_mid) else 0.0
            both_hit = 1.0 if (hit_long and hit_mid) else 0.0
            frr = (5 - (hit_long + hit_mid)) / 5.0

            results["rankers"][name]["top5_any_recall"] += any_hit / len(seeds)
            results["rankers"][name]["top5_both_recall"] += both_hit / len(seeds)
            results["rankers"][name]["mean_frr"] += frr / len(seeds)
            results["rankers"][name]["a_long_mean_rank"] += rank_long / len(seeds)
            results["rankers"][name]["a_mid_mean_rank"] += rank_mid / len(seeds)
            results["rankers"][name]["seed_results"][s] = {
                "rank_a_long": rank_long,
                "rank_a_mid": rank_mid,
                "top5_ids": top5_eids,
                "any_hit": bool(any_hit),
                "both_hit": bool(both_hit),
                "frr": frr,
            }

    return results


if __name__ == "__main__":
    res = run_wp_r5()
    print(json.dumps(res, indent=2))
