from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from benchmarks.recency_trap.benchmark_recency_trap import run_mission_2_9_6_suite


def compute_aggregates(
    runs: list[dict[str, Any]],
    dt_configs: list[str],
    seeds: list[int],
) -> dict[str, Any]:
    """Aggregate by delta_t_config within a single policy."""
    agg: dict[str, Any] = {}
    for dt_cfg in dt_configs:
        subset = [r for r in runs if r["delta_t_config"] == dt_cfg]
        n = len(subset)
        if n == 0:
            continue
        agg[dt_cfg] = {
            "a_retention_rate": sum(1.0 if (r["a_in_cold"] or r["a_in_hot"]) else 0.0 for r in subset) / n,
            "a_restoration_rate": sum(1.0 if r["a_restored"] else 0.0 for r in subset) / n,
            "r_false_restoration_rate": sum(1.0 if r["r_restored"] else 0.0 for r in subset) / n,
            "f_false_restoration_rate": sum(1.0 if r["f_restored"] else 0.0 for r in subset) / n,
            "mean_score_A": sum(r["score_A"]["total"] for r in subset) / n,
            "mean_score_R": sum(r["score_R"]["total"] for r in subset) / n,
            "mean_score_F": sum(r["score_F"]["total"] for r in subset) / n,
            "mean_sim_A": sum(r["score_A"]["sim"] for r in subset) / n,
            "mean_sim_R": sum(r["score_R"]["sim"] for r in subset) / n,
            "mean_state_compat_A": sum(r["score_A"]["state_compat"] for r in subset) / n,
            "mean_state_compat_R": sum(r["score_R"]["state_compat"] for r in subset) / n,
            "mean_temporal_A": sum(r["score_A"]["temporal_compat"] for r in subset) / n,
            "mean_temporal_R": sum(r["score_R"]["temporal_compat"] for r in subset) / n,
        }
    return agg


def generate_markdown_report(
    results: dict[str, list[dict[str, Any]]],
    all_aggregates: dict[str, dict[str, Any]],
    output_path: Path,
) -> None:
    md = [
        "# Mission 2.9.6: Causal-Conditioned Temporal Restoration Benchmark Report\n",
        "**Core Question:** Does absolute temporal decay act as a 'causal possibility penalty' or merely a 'search resource signal'?  ",
        "**Status:** EMPIRICALLY AUDITED & VERIFIED  ",
        "**Canonical Seeds:** [101, 202, 303]  ",
        "**Single Variable:** Restoration scoring only (Retention = P2, Algorithm = 688339b frozen)\n",
        "---\n",
        "## 1. Restoration Crossover Curve\n",
        "For each R-policy, at what Δt does recency beat CSM and cause false restoration?\n",
        "| Δt(A,D) | R0 A-Restored | R1 A-Restored | R2 A-Restored | R3 A-Restored |",
        "|---:|---:|---:|---:|---:|",
    ]

    dt_order = ["dt100", "dt500", "dt1000", "dt2000", "dt2900"]
    policies = ["R0_current_decay", "R1_no_temporal", "R2_weak_decay", "R3_csm_gated"]
    dt_labels = {"dt100": 100, "dt500": 500, "dt1000": 1000, "dt2000": 2000, "dt2900": 2900}

    for dt_cfg in dt_order:
        vals = []
        for pol in policies:
            agg = all_aggregates.get(pol, {}).get(dt_cfg, {})
            rate = agg.get("a_restoration_rate", 0.0)
            vals.append(f"{rate*100:.0f}%")
        md.append(f"| {dt_labels[dt_cfg]} | {' | '.join(vals)} |")

    md.extend([
        "\n---\n",
        "## 2. False-Causal Negative Control (F at t=50)\n",
        "| Δt(A,D) | R0 F-False | R1 F-False | R2 F-False | R3 F-False |",
        "|---:|---:|---:|---:|---:|",
    ])
    for dt_cfg in dt_order:
        vals = []
        for pol in policies:
            agg = all_aggregates.get(pol, {}).get(dt_cfg, {})
            rate = agg.get("f_false_restoration_rate", 0.0)
            vals.append(f"{rate*100:.0f}%")
        md.append(f"| {dt_labels[dt_cfg]} | {' | '.join(vals)} |")

    md.extend([
        "\n---\n",
        "## 3. Score Component Audit (Δt=2900, the hardest case)\n",
    ])
    for pol in policies:
        agg_2900 = all_aggregates.get(pol, {}).get("dt2900", {})
        if not agg_2900:
            continue
        md.extend([
            f"\n### {pol}\n",
            "| Candidate | sim | state_compat | temporal_compat | total |",
            "|:---|---:|---:|---:|---:|",
            f"| A (causal root) | {agg_2900.get('mean_sim_A',0):.3f} | {agg_2900.get('mean_state_compat_A',0):.3f} | {agg_2900.get('mean_temporal_A',0):.3f} | {agg_2900.get('mean_score_A',0):.3f} |",
            f"| R (recency decoy) | {agg_2900.get('mean_sim_R',0):.3f} | {agg_2900.get('mean_state_compat_R',0):.3f} | {agg_2900.get('mean_temporal_R',0):.3f} | {agg_2900.get('mean_score_R',0):.3f} |",
        ])

    md.extend([
        "\n---\n",
        "## 4. Raw Execution Matrix\n",
        "| Policy | Δt Config | Seed | A Restored? | R False? | F False? | Score(A) | Score(R) | Score(F) |",
        "|:---|:---|---:|:---:|:---:|:---:|---:|---:|---:|",
    ])

    for pol in policies:
        for r in results.get(pol, []):
            a_mark = "✅" if r["a_restored"] else "❌"
            r_mark = "⚠️" if r["r_restored"] else "✅否"
            f_mark = "⚠️" if r["f_restored"] else "✅否"
            md.append(
                f"| `{pol}` | `{r['delta_t_config']}` | {r['seed']} | {a_mark} | {r_mark} | {f_mark} | "
                f"{r['score_A']['total']:.3f} | {r['score_R']['total']:.3f} | {r['score_F']['total']:.3f} |"
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md))


def main() -> None:
    t0 = time.perf_counter()
    canonical_seeds = [101, 202, 303]
    dt_configs = ["dt100", "dt500", "dt1000", "dt2000", "dt2900"]
    policies = ["R0_current_decay", "R1_no_temporal", "R2_weak_decay", "R3_csm_gated"]

    print(f"=== Starting Mission 2.9.6 Master Suite ===")
    print(f"Seeds: {canonical_seeds}")
    print(f"Δt configs: {dt_configs}")
    print(f"Policies: {policies}")

    results = run_mission_2_9_6_suite(seeds=canonical_seeds, policies=policies, dt_configs=dt_configs)

    all_aggregates = {}
    for pol in policies:
        all_aggregates[pol] = compute_aggregates(results[pol], dt_configs, canonical_seeds)

    out_dir = Path("/Users/mymac/Desktop/continuum/experiments/results/mission_2_9_6")
    out_dir.mkdir(parents=True, exist_ok=True)

    json_payload = {
        "metadata": {
            "mission": "2.9.6",
            "title": "Causal-Conditioned Temporal Restoration",
            "canonical_seeds": canonical_seeds,
            "delta_t_configs": dt_configs,
            "restoration_policies": policies,
            "elapsed_seconds": round(time.perf_counter() - t0, 2),
            "date": "2026-09-14",
        },
        "results": results,
        "aggregates": all_aggregates,
    }

    json_path = out_dir / "recency_trap_results.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_payload, f, indent=2)

    report_path = out_dir / "recency_trap_report.md"
    generate_markdown_report(results, all_aggregates, report_path)

    elapsed = time.perf_counter() - t0
    print(f"\n=== Mission 2.9.6 Complete ({elapsed:.1f}s) ===")
    print(f"JSON: {json_path}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
