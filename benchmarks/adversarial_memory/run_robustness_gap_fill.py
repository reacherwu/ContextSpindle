import json
import math
from typing import Any
from pathlib import Path

import torch
from torch import Tensor

from benchmarks.adversarial_memory.benchmark_c_novelty_inversion import run_benchmark_c
from benchmarks.factor_attribution.contamination_scaling import run_contamination_trial
from benchmarks.adversarial_memory.run_all_adversarial import aggregate_runs

from continuum.memory.adaptive_memory import AdaptiveMemory, AdaptiveMemoryConfig
from continuum.state.temporal_state import TemporalState, TemporalStateConfig


MODELS = {
    "S+N": ("min_importance", 0.5, 0.5, 0.0, 0.0, 0.0),
    "N+C": ("min_importance", 0.0, 0.5, 0.5, 0.0, 0.0),
    "Primary_0.2": ("min_importance", 0.2, 0.2, 0.2, 0.2, 0.2),
    "Novelty_Only": ("min_importance", 0.0, 1.0, 0.0, 0.0, 0.0),
    "Surprise_Only": ("min_importance", 1.0, 0.0, 0.0, 0.0, 0.0),
}


def generate_stream(seed: int, stream_length: int, embedding_dim: int):
    torch.manual_seed(seed)
    n_clusters = 3
    cluster_centers = torch.randn(n_clusters, embedding_dim)
    cluster_centers = cluster_centers / torch.norm(cluster_centers, dim=-1, keepdim=True)

    target_steps = [50, 100, 150, 200, 250, 300, 350, 400, 450, 500]
    critical_targets: dict[int, Tensor] = {}
    for s in target_steps:
        v = cluster_centers[0] + 0.03 * torch.randn(embedding_dim)
        critical_targets[s] = v / torch.norm(v)

    # ~100 outlier traps injected every 44 steps from t=600
    trap_steps = set(range(600, stream_length, 44))
    novelty_traps: dict[int, Tensor] = {}
    for s in trap_steps:
        outlier = torch.randn(embedding_dim)
        for c in cluster_centers:
            outlier = outlier - torch.dot(outlier, c) * c
        novelty_traps[s] = outlier / torch.norm(outlier)

    stream = []
    for step in range(stream_length):
        if step in critical_targets:
            stream.append((step, critical_targets[step]))
        elif step in novelty_traps:
            stream.append((step, novelty_traps[step]))
        else:
            c_id = (step // 30) % n_clusters
            v = cluster_centers[c_id] + 0.05 * torch.randn(embedding_dim)
            stream.append((step, v / torch.norm(v)))
            
    return stream, critical_targets, novelty_traps


def run_benchmark_c_extended(
    stream_length: int = 5000,
    capacity: int = 200,
    embedding_dim: int = 32,
    seed: int = 101,
) -> dict[str, Any]:
    stream, critical_targets, novelty_traps = generate_stream(seed, stream_length, embedding_dim)
    
    results: dict[str, Any] = {}

    for name, (eviction, a, b, c, d, e) in MODELS.items():
        temporal_cfg = TemporalStateConfig(input_size=embedding_dim, hidden_size=embedding_dim)
        temporal_model = TemporalState(temporal_cfg)
        h_state = temporal_model.initial_state(1)

        cfg = AdaptiveMemoryConfig(
            embedding_dim=embedding_dim,
            state_dim=embedding_dim,
            capacity=capacity,
            policy_mode="fixed_budget",
            eviction_policy=eviction, # type: ignore
            alpha_surprise=a,
            beta_novelty=b,
            gamma_causal=c,
            delta_retrieval=d,
            epsilon_uncertainty=e,
            seed=seed,
        )
        mem = AdaptiveMemory(cfg)

        for step, vec in stream:
            step_out = temporal_model.step(vec.unsqueeze(0), h_state)
            h_state = step_out.state
            mem.observe(event_id=step, timestamp=float(step), embedding=vec, temporal_state=h_state[0])

        retained_ids = set(r.event_id for r in mem.records)
        traps_hoarded = sum(1 for tid in novelty_traps if tid in retained_ids)
        targets_retained = sum(1 for cid in critical_targets if cid in retained_ids)

        hits = 0
        mrr_sum = 0.0
        for s, target_vec in critical_targets.items():
            query = target_vec + 0.02 * torch.randn(embedding_dim)
            query = query / torch.norm(query)
            retrieved = mem.retrieve(query, top_k=5)
            if retrieved:
                for rank, (r, sim) in enumerate(retrieved, start=1):
                    if r.event_id == s:
                        mrr_sum += 1.0 / rank
                        if rank == 1:
                            hits += 1
                        break

        n_targets = len(critical_targets)
        results[name] = {
            "target_accuracy": hits / n_targets,
            "target_mrr": mrr_sum / n_targets,
            "targets_retained": targets_retained,
            "traps_hoarded": traps_hoarded,
            "trap_hoarding_ratio": traps_hoarded / capacity,
        }

    return results


def run_contamination_trial_extended(
    model_name: str,
    capacity_k: int,
    seed: int,
    stream_length: int = 5000,
    embedding_dim: int = 32,
) -> dict[str, Any]:
    stream, critical_targets, novelty_traps = generate_stream(seed, stream_length, embedding_dim)
    
    eviction, a, b, c, d, e = MODELS[model_name]
    state_dim = embedding_dim
    temporal_cfg = TemporalStateConfig(input_size=embedding_dim, hidden_size=state_dim)
    temporal_model = TemporalState(temporal_cfg)
    h_state = temporal_model.initial_state(1)

    mem_cfg = AdaptiveMemoryConfig(
        embedding_dim=embedding_dim,
        state_dim=state_dim,
        capacity=capacity_k,
        policy_mode="fixed_budget",
        eviction_policy=eviction, # type: ignore
        alpha_surprise=a,
        beta_novelty=b,
        gamma_causal=c,
        delta_retrieval=d,
        epsilon_uncertainty=e,
        seed=seed,
    )
    mem = AdaptiveMemory(mem_cfg)

    for step, vec in stream:
        step_out = temporal_model.step(vec.unsqueeze(0), h_state)
        h_state = step_out.state
        mem.observe(event_id=step, timestamp=float(step), embedding=vec, temporal_state=h_state[0])

    retained_ids = set(r.event_id for r in mem.records)
    targets_retained = sum(1 for s in critical_targets if s in retained_ids)
    traps_hoarded = sum(1 for s in novelty_traps if s in retained_ids)
    final_size = len(mem.records)

    hits = 0
    mrr_sum = 0.0
    for s, t_vec in critical_targets.items():
        q = t_vec + 0.02 * torch.randn(embedding_dim)
        q = q / torch.norm(q)
        retrieved = mem.retrieve(q, top_k=5)
        if retrieved:
            for rank, (r, sim) in enumerate(retrieved, start=1):
                if r.event_id == s:
                    mrr_sum += 1.0 / rank
                    if rank == 1:
                        hits += 1
                    break

    n_targets = len(critical_targets)
    recall = hits / n_targets
    contamination = traps_hoarded / max(1, capacity_k)
    useful_ratio = targets_retained / max(1, capacity_k)
    utilization = final_size / max(1, capacity_k)

    return {
        "model": model_name,
        "capacity_k": capacity_k,
        "seed": seed,
        "recall": recall,
        "mrr": mrr_sum / n_targets,
        "contamination": contamination,
        "useful_ratio": useful_ratio,
        "utilization": utilization,
        "targets_retained": targets_retained,
        "traps_hoarded": traps_hoarded,
    }


def run_contamination_gap_fill() -> dict[str, Any]:
    capacities = [25, 50, 100, 200, 500, 1000]
    seeds = [101, 202, 303]
    models = list(MODELS.keys())
    
    all_trials = []
    for k in capacities:
        for m in models:
            for s in seeds:
                res = run_contamination_trial_extended(m, k, s)
                all_trials.append(res)
                
    # Aggregate by (model, capacity)
    aggregated: dict[str, dict[int, dict[str, float]]] = {m: {} for m in models}
    for m in models:
        for k in capacities:
            matching = [t for t in all_trials if t["model"] == m and t["capacity_k"] == k]
            recalls = [t["recall"] for t in matching]
            contams = [t["contamination"] for t in matching]
            usefuls = [t["useful_ratio"] for t in matching]
            utils = [t["utilization"] for t in matching]
            traps = [t["traps_hoarded"] for t in matching]

            aggregated[m][k] = {
                "mean_recall": sum(recalls) / len(recalls),
                "mean_contamination": sum(contams) / len(contams),
                "mean_useful_ratio": sum(usefuls) / len(usefuls),
                "mean_utilization": sum(utils) / len(utils),
                "mean_traps_hoarded": sum(traps) / len(traps),
            }

    return {
        "capacities": capacities,
        "models": models,
        "seeds": seeds,
        "aggregated": aggregated,
        "raw_trials": all_trials,
    }


if __name__ == "__main__":
    seeds = [101, 202, 303]
    
    print(">>> Running Benchmark C Extended...")
    raw_c: dict[str, list[dict[str, Any]]] = {}
    for s in seeds:
        res = run_benchmark_c_extended(seed=s)
        for m, d in res.items():
            raw_c.setdefault(m, []).append(d)
    
    bench_c_agg = {m: aggregate_runs(raw_c[m]) for m in raw_c}
    
    print(">>> Running Contamination Gap Fill...")
    contam_results = run_contamination_gap_fill()
    
    final_data = {
        "benchmark_c": bench_c_agg,
        "contamination_sweep": contam_results,
    }
    
    out_dir = Path("experiments/results/adversarial_memory")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    res_path = out_dir / "robustness_gap_fill_results.json"
    with open(res_path, "w") as f:
        json.dump(final_data, f, indent=2)
    print(f"Saved results to {res_path}")
        
    md = [
        "# Adversarial Robustness Gap-Fill Report",
        "",
        "## Comparison Table",
        "| Model | Benchmark C Accuracy | Traps Hoarded | Contamination@K=200 | Contamination@K=1000 |",
        "| :--- | :---: | :---: | :---: | :---: |",
    ]
    
    for m in MODELS:
        c_acc = bench_c_agg[m]["mean_target_accuracy"] * 100
        c_traps = bench_c_agg[m]["mean_traps_hoarded"]
        contam_200 = contam_results["aggregated"][m][200]["mean_contamination"] * 100
        contam_1000 = contam_results["aggregated"][m][1000]["mean_contamination"] * 100
        
        md.append(f"| {m} | {c_acc:.1f}% | {c_traps:.1f} | {contam_200:.1f}% | {contam_1000:.1f}% |")
        
    rep_path = out_dir / "robustness_gap_fill_report.md"
    with open(rep_path, "w") as f:
        f.write("\n".join(md) + "\n")
    print(f"Saved report to {rep_path}")
