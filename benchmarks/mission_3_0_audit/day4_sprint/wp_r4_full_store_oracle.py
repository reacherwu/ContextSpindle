"""WP-R4: Full-Store Reference (B4) Benchmark & Capacity vs. Scoring Isolation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import torch
from torch import Tensor

from continuum.memory.cold_memory import ColdCandidateRecord
from continuum.memory.revision_engine import RevisionConfig, RevisionEngine
from benchmarks.mission_3_0_audit.audit_pipeline import generate_evaluation_stream


def run_wp_r4() -> dict[str, Any]:
    seeds = [101, 202, 303]
    rev_config = RevisionConfig(
        theta_trigger=0.45,
        theta_restore=0.25,
        max_restorations_per_trigger=5,
    )
    engine = RevisionEngine(rev_config)

    results: dict[str, Any] = {
        "seeds": {},
        "summary": {
            "b4_revision_any_recall_top5": 0.0,
            "b4_revision_both_recall_top5": 0.0,
            "b4_revision_mean_frr": 0.0,
            "b4_revision_a_long_mean_rank": 0.0,
            "b4_revision_a_mid_mean_rank": 0.0,
            "b4_sim_only_any_recall_top5": 0.0,
            "b4_sim_only_both_recall_top5": 0.0,
            "b4_sim_only_mean_frr": 0.0,
            "b4_sim_only_a_long_mean_rank": 0.0,
            "b4_sim_only_a_mid_mean_rank": 0.0,
        },
    }

    for s in seeds:
        stream, vec_D, t_A_long, t_A_mid, t_R, t_F = generate_evaluation_stream(s)
        total_steps = len(stream)
        t_curr = float(total_steps)

        # Recurrent state progression
        decay = 0.95
        cur_h = torch.zeros(32)
        states = []
        for t, emb, _ in stream:
            cur_h = decay * cur_h + (1 - decay) * emb
            norm = torch.norm(cur_h, p=2).item()
            if norm > 1e-8:
                cur_h = cur_h / norm
            states.append(cur_h.clone())

        records: list[ColdCandidateRecord] = []
        for idx, (t, emb, tag) in enumerate(stream):
            records.append(
                ColdCandidateRecord(
                    event_id=t,
                    timestamp=float(t),
                    compressed_embedding=emb,
                    state_fingerprint=states[idx],
                    importance_at_eviction=0.5,
                    provenance_summary=f"b4_step_{t}",
                )
            )

        terminal_state = states[-1]

        # 1. Standard RevisionEngine scoring on full 3000 records
        scored_rev = []
        for r in records:
            sc, comps = engine._compute_revision_score_with_components(
                r, vec_D, terminal_state, t_curr
            )
            scored_rev.append((sc, r.event_id, comps))

        scored_rev.sort(key=lambda x: x[0], reverse=True)
        top5_rev = [eid for _, eid, _ in scored_rev[:5]]
        top10_rev = [eid for _, eid, _ in scored_rev[:10]]

        rank_rev_long = next(i + 1 for i, (_, eid, _) in enumerate(scored_rev) if eid == t_A_long)
        rank_rev_mid = next(i + 1 for i, (_, eid, _) in enumerate(scored_rev) if eid == t_A_mid)
        rank_rev_decoy = next(i + 1 for i, (_, eid, _) in enumerate(scored_rev) if eid == t_R)

        score_rev_long = next(sc for sc, eid, _ in scored_rev if eid == t_A_long)
        score_rev_mid = next(sc for sc, eid, _ in scored_rev if eid == t_A_mid)
        score_rev_top1 = scored_rev[0][0]

        hit_rev_any = (t_A_long in top5_rev) or (t_A_mid in top5_rev)
        hit_rev_both = (t_A_long in top5_rev) and (t_A_mid in top5_rev)
        causal_hits_rev = (1 if t_A_long in top5_rev else 0) + (1 if t_A_mid in top5_rev else 0)
        frr_rev = (5 - causal_hits_rev) / 5.0

        # 2. Pure Cosine Similarity scoring on full 3000 records
        scored_sim = []
        for r in records:
            sim = torch.dot(r.compressed_embedding, vec_D).item()
            scored_sim.append((sim, r.event_id))

        scored_sim.sort(key=lambda x: x[0], reverse=True)
        top5_sim = [eid for _, eid in scored_sim[:5]]
        top10_sim = [eid for _, eid in scored_sim[:10]]

        rank_sim_long = next(i + 1 for i, (_, eid) in enumerate(scored_sim) if eid == t_A_long)
        rank_sim_mid = next(i + 1 for i, (_, eid) in enumerate(scored_sim) if eid == t_A_mid)
        rank_sim_decoy = next(i + 1 for i, (_, eid) in enumerate(scored_sim) if eid == t_R)

        hit_sim_any = (t_A_long in top5_sim) or (t_A_mid in top5_sim)
        hit_sim_both = (t_A_long in top5_sim) and (t_A_mid in top5_sim)
        causal_hits_sim = (1 if t_A_long in top5_sim else 0) + (1 if t_A_mid in top5_sim else 0)
        frr_sim = (5 - causal_hits_sim) / 5.0

        results["seeds"][s] = {
            "b4_revision": {
                "top5_ids": top5_rev,
                "rank_a_long": rank_rev_long,
                "rank_a_mid": rank_rev_mid,
                "rank_recent_decoy": rank_rev_decoy,
                "score_a_long": score_rev_long,
                "score_a_mid": score_rev_mid,
                "score_top1": score_rev_top1,
                "gap_to_top1_long": score_rev_top1 - score_rev_long,
                "any_hit_top5": hit_rev_any,
                "both_hit_top5": hit_rev_both,
                "frr_top5": frr_rev,
            },
            "b4_sim_only": {
                "top5_ids": top5_sim,
                "rank_a_long": rank_sim_long,
                "rank_a_mid": rank_sim_mid,
                "rank_recent_decoy": rank_sim_decoy,
                "any_hit_top5": hit_sim_any,
                "both_hit_top5": hit_sim_both,
                "frr_top5": frr_sim,
            },
        }

        n = len(seeds)
        results["summary"]["b4_revision_any_recall_top5"] += (1.0 if hit_rev_any else 0.0) / n
        results["summary"]["b4_revision_both_recall_top5"] += (1.0 if hit_rev_both else 0.0) / n
        results["summary"]["b4_revision_mean_frr"] += frr_rev / n
        results["summary"]["b4_revision_a_long_mean_rank"] += rank_rev_long / n
        results["summary"]["b4_revision_a_mid_mean_rank"] += rank_rev_mid / n

        results["summary"]["b4_sim_only_any_recall_top5"] += (1.0 if hit_sim_any else 0.0) / n
        results["summary"]["b4_sim_only_both_recall_top5"] += (1.0 if hit_sim_both else 0.0) / n
        results["summary"]["b4_sim_only_mean_frr"] += frr_sim / n
        results["summary"]["b4_sim_only_a_long_mean_rank"] += rank_sim_long / n
        results["summary"]["b4_sim_only_a_mid_mean_rank"] += rank_sim_mid / n

    return results


if __name__ == "__main__":
    res = run_wp_r4()
    print(json.dumps(res, indent=2))
