"""WP-R1: RevisionEngine Mathematical Reconstruction & Component Audit."""

from __future__ import annotations

import json
from pathlib import Path
import torch
from benchmarks.mission_3_0_audit.audit_pipeline import generate_evaluation_stream
from benchmarks.mission_3_0.acm_architecture import ACMArchitecture


def run_wp_r1() -> dict[str, Any]:
    seeds = [101, 202, 303]
    candidate_breakdowns = {s: {} for s in seeds}

    for s in seeds:
        stream, vec_D, t_A_long, t_A_mid, t_R, t_F = generate_evaluation_stream(s)
        model = ACMArchitecture(emb_dim=32, state_dim=32, k_hot=250, k_cold=500, seed=s)

        for t, emb, _ in stream:
            model.observe(t, float(t), emb)

        cur_h = model.h_state[0]
        recs = model.cold_memory.records
        target_ids = {
            "A_long": t_A_long,
            "A_mid": t_A_mid,
            "Recent_Decoy": t_R,
            "Ancient_False": t_F,
            "Regime_Drift_Early": 300,
        }

        # Also find the Top-1 background winner in this seed
        scored_all = []
        for r in recs:
            sc, comps = model.revision_engine._compute_revision_score_with_components(
                r, vec_D, cur_h, float(len(stream))
            )
            scored_all.append((sc, r, comps))
        scored_all.sort(key=lambda x: x[0], reverse=True)
        top1_bg = next((item for item in scored_all if item[1].event_id not in target_ids.values()), scored_all[0])
        target_ids[f"Top1_Distractor_Winner (ID {top1_bg[1].event_id})"] = top1_bg[1].event_id

        for label, eid in target_ids.items():
            cand = next((r for r in recs if r.event_id == eid), None)
            if cand is not None:
                score, comps = model.revision_engine._compute_revision_score_with_components(
                    cand, vec_D, cur_h, float(len(stream))
                )
                rank = next(i + 1 for i, item in enumerate(scored_all) if item[1].event_id == eid)
                candidate_breakdowns[s][label] = {
                    "event_id": eid,
                    "rank": rank,
                    "total_score": score,
                    "sim_raw": comps["sim"],
                    "sim_weighted": 0.4 * comps["sim"],
                    "state_raw": comps["state_compat"],
                    "state_weighted": 0.3 * comps["state_compat"],
                    "temp_raw": comps["temporal_compat"],
                    "temp_weighted": 0.2 * comps["temporal_compat"],
                    "prov_raw": comps["provenance_compat"],
                    "prov_weighted": 0.1 * comps["provenance_compat"],
                    "delta_t": abs(float(len(stream)) - cand.timestamp),
                }

    return candidate_breakdowns


if __name__ == "__main__":
    res = run_wp_r1()
    print(json.dumps(res, indent=2))
