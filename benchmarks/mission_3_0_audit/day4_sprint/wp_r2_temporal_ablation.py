"""WP-R2: Temporal Policy Matrix across Delta_t Horizon."""

from __future__ import annotations

import json
import math
import random
from typing import Any

import torch
from torch import Tensor

from continuum.memory.cold_memory import ColdCandidateRecord
from continuum.memory.revision_engine import RevisionConfig, RevisionEngine
from benchmarks.recency_trap.benchmark_recency_trap import DiversifiedDynamicsColdMemory, R3Engine
from benchmarks.mission_3_0_audit.audit_pipeline import R4Engine


def run_wp_r2() -> dict[str, Any]:
    seeds = [101, 202, 303]
    delta_t_list = [100, 500, 1000, 2000, 3000]
    policies = ["R0_current", "R1_no_decay", "R2_weak_decay", "R3_csm_gated", "R4_causal_conditioned"]

    base_cfg = RevisionConfig(theta_trigger=0.45, theta_restore=0.25, max_restorations_per_trigger=5)
    engines = {
        "R0_current": RevisionEngine(base_cfg),
        "R1_no_decay": R3Engine(base_cfg, alpha=0.0),
        "R2_weak_decay": RevisionEngine(RevisionConfig(theta_trigger=0.45, theta_restore=0.25, max_restorations_per_trigger=5, temporal_decay_tau=5000.0)),
        "R3_csm_gated": R3Engine(base_cfg, alpha=3.0),
        "R4_causal_conditioned": R4Engine(base_cfg, alpha=3.0, csm_exempt_thresh=0.40),
    }

    results: dict[str, dict[int, dict[str, float]]] = {
        pol: {dt: {"true_recall": 0.0, "false_recovery_rate": 0.0, "true_mean_rank": 0.0, "decoy_mean_rank": 0.0} for dt in delta_t_list}
        for pol in policies
    }

    emb_dim = 32
    state_dim = 32

    for dt in delta_t_list:
        for s in seeds:
            torch.manual_seed(s)
            random.seed(s)
            stream_length = 3500
            t_D = stream_length
            t_A = t_D - dt
            t_R = t_D - 50  # recent decoy
            t_F = 50        # ancient false cause

            # Build orthogonal basis
            v_x = torch.randn(emb_dim); v_x /= torch.norm(v_x)
            v_y = torch.randn(emb_dim); v_y -= torch.dot(v_y, v_x) * v_x; v_y /= torch.norm(v_y)

            vec_A = 0.85 * v_x + 0.15 * torch.randn(emb_dim); vec_A /= torch.norm(vec_A)
            vec_D = 0.85 * v_x + 0.15 * torch.randn(emb_dim); vec_D /= torch.norm(vec_D)
            vec_R = 0.50 * v_x + 0.45 * v_y + 0.05 * torch.randn(emb_dim); vec_R /= torch.norm(vec_R)
            vec_F = 0.75 * v_x + 0.25 * torch.randn(emb_dim); vec_F /= torch.norm(vec_F)

            # Cold memory with 50 candidates (distractors + background + targets)
            cold = DiversifiedDynamicsColdMemory(capacity=100, embedding_dim=emb_dim, state_dim=state_dim)

            # Target candidates
            cur_h = torch.randn(state_dim); cur_h /= torch.norm(cur_h)
            h_A = 0.70 * cur_h + 0.30 * torch.randn(state_dim); h_A /= torch.norm(h_A)
            h_R = 0.85 * cur_h + 0.15 * torch.randn(state_dim); h_R /= torch.norm(h_R)
            h_F = torch.randn(state_dim); h_F /= torch.norm(h_F)

            cold.archive(t_A, float(t_A), vec_A, h_A, 0.6, "true_cause")
            cold.archive(t_R, float(t_R), vec_R, h_R, 0.6, "recent_decoy")
            cold.archive(t_F, float(t_F), vec_F, h_F, 0.6, "ancient_false")

            # Add 20 distractors spread across time
            for step in range(200, stream_length - 100, 150):
                d_vec = 0.35 * vec_D + 0.65 * torch.randn(emb_dim); d_vec /= torch.norm(d_vec)
                d_h = torch.randn(state_dim); d_h /= torch.norm(d_h)
                cold.archive(step, float(step), d_vec, d_h, 0.3, "distractor")

            # Evaluate each policy
            recs = cold.records
            for p_name, eng in engines.items():
                scored = []
                for r in recs:
                    if p_name == "R1_no_decay":
                        sc, comps = eng._compute_revision_score_with_components(r, vec_D, cur_h, float(t_D))
                        sc = sc - eng.config.w_temporal_compat * comps["temporal_compat"] + eng.config.w_temporal_compat * 1.0
                    else:
                        sc, comps = eng._compute_revision_score_with_components(r, vec_D, cur_h, float(t_D))
                    scored.append((sc, r.event_id))

                scored.sort(key=lambda x: x[0], reverse=True)
                top5_ids = [eid for _, eid in scored[:5]]

                rank_A = next(i + 1 for i, (_, eid) in enumerate(scored) if eid == t_A)
                rank_R = next(i + 1 for i, (_, eid) in enumerate(scored) if eid == t_R)

                hit_true = 1.0 if t_A in top5_ids else 0.0
                false_rec = 1.0 if t_F in top5_ids else 0.0

                results[p_name][dt]["true_recall"] += hit_true / len(seeds)
                results[p_name][dt]["false_recovery_rate"] += false_rec / len(seeds)
                results[p_name][dt]["true_mean_rank"] += rank_A / len(seeds)
                results[p_name][dt]["decoy_mean_rank"] += rank_R / len(seeds)

    return results


if __name__ == "__main__":
    res = run_wp_r2()
    print(json.dumps(res, indent=2))
