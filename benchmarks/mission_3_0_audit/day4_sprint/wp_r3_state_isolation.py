"""WP-R3: Recurrent State Auto-correlation Isolation & Component Matrix."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import torch
from torch import Tensor

from benchmarks.mission_3_0_audit.audit_pipeline import generate_evaluation_stream
from benchmarks.mission_3_0.acm_architecture import ACMArchitecture


def run_wp_r3() -> dict[str, Any]:
    seeds = [101, 202, 303]

    # 8 Conditions:
    # (w_sim, w_state, w_temp, w_prov)
    conditions = {
        "1_Sim_only": (1.0, 0.0, 0.0, 0.0),
        "2_Temporal_only": (0.0, 0.0, 1.0, 0.0),
        "3_State_only": (0.0, 1.0, 0.0, 0.0),
        "4_Sim_plus_Temporal": (0.6, 0.0, 0.4, 0.0),
        "5_Sim_plus_State": (0.6, 0.4, 0.0, 0.0),
        "6_Temporal_plus_State": (0.0, 0.5, 0.5, 0.0),
        "7_Sim_plus_Temporal_plus_State": (0.45, 0.30, 0.25, 0.0),
        "8_Full_Standard": (0.40, 0.30, 0.20, 0.10),
    }

    results: dict[str, Any] = {
        cond: {
            "top5_any_recall": 0.0,
            "top5_both_recall": 0.0,
            "mean_frr": 0.0,
            "a_long_mean_rank": 0.0,
            "a_mid_mean_rank": 0.0,
            "seeds": {},
        }
        for cond in conditions
    }

    for s in seeds:
        stream, vec_D, t_A_long, t_A_mid, t_R, t_F = generate_evaluation_stream(s)
        model = ACMArchitecture(emb_dim=32, state_dim=32, k_hot=250, k_cold=500, seed=s)

        for t, emb, _ in stream:
            model.observe(t, float(t), emb)

        cur_h = model.h_state[0]
        recs = model.cold_memory.records
        t_curr = float(len(stream))

        cand_ids = {r.event_id for r in recs}
        a_long_retained = t_A_long in cand_ids
        a_mid_retained = t_A_mid in cand_ids

        for cond_name, (w_sim, w_state, w_temp, w_prov) in conditions.items():
            scored = []
            for r in recs:
                _, comps = model.revision_engine._compute_revision_score_with_components(
                    r, vec_D, cur_h, t_curr
                )
                score = (
                    w_sim * comps["sim"]
                    + w_state * comps["state_compat"]
                    + w_temp * comps["temporal_compat"]
                    + w_prov * comps["provenance_compat"]
                )
                scored.append((score, r.event_id))

            scored.sort(key=lambda x: x[0], reverse=True)
            top5_eids = [eid for _, eid in scored[:5]]

            rank_a_long = next((i + 1 for i, (_, eid) in enumerate(scored) if eid == t_A_long), 999)
            rank_a_mid = next((i + 1 for i, (_, eid) in enumerate(scored) if eid == t_A_mid), 999)

            hit_a_long = 1 if t_A_long in top5_eids else 0
            hit_a_mid = 1 if t_A_mid in top5_eids else 0
            any_hit = 1.0 if (hit_a_long or hit_a_mid) else 0.0
            both_hit = 1.0 if (hit_a_long and hit_a_mid) else 0.0

            # FRR: fraction of top-5 slots that are non-causal
            causal_hits_in_top5 = hit_a_long + hit_a_mid
            frr = (5 - causal_hits_in_top5) / 5.0

            results[cond_name]["top5_any_recall"] += any_hit / len(seeds)
            results[cond_name]["top5_both_recall"] += both_hit / len(seeds)
            results[cond_name]["mean_frr"] += frr / len(seeds)
            results[cond_name]["a_long_mean_rank"] += rank_a_long / len(seeds)
            results[cond_name]["a_mid_mean_rank"] += rank_a_mid / len(seeds)
            results[cond_name]["seeds"][s] = {
                "rank_a_long": rank_a_long,
                "rank_a_mid": rank_a_mid,
                "top5_ids": top5_eids,
                "any_hit": bool(any_hit),
                "both_hit": bool(both_hit),
                "frr": frr,
            }

    return results


if __name__ == "__main__":
    res = run_wp_r3()
    print(json.dumps(res, indent=2))
