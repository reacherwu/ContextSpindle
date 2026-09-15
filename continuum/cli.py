"""Command-line interface for the Continuum Temporal Intelligence Engine."""

from __future__ import annotations

import argparse
import sys
import time

import torch

from continuum import ContinuumEngine, ContinuumConfig, __version__


def cmd_version(args: argparse.Namespace) -> None:
    print(f"Continuum Engine version {__version__}")


def cmd_status(args: argparse.Namespace) -> None:
    engine = ContinuumEngine.create(embedding_dim=32, state_dim=32)
    stats = engine.get_stats()
    print("======================================================")
    print(f"  Continuum Engine Runtime Status (v{__version__})")
    print("======================================================")
    print(f"  Max Capacity:       {stats['max_slots']} slots ({engine.config.hot_capacity} Hot + {engine.config.cold_capacity} Cold)")
    print(f"  Current Usage:      {stats['total_slots']} slots ({stats['slot_utilization_pct']:.1f}%)")
    print(f"  Processed Steps:    {stats['step_count']}")
    print(f"  Device:             {stats['device']}")
    print(f"  Subspace Threshold: {engine.config.sim_threshold}")
    print(f"  Revision Gating:    CSM alpha={engine.config.alpha_csm_gating}")
    print("======================================================")


def cmd_demo(args: argparse.Namespace) -> None:
    print(f"Starting Continuum Live Streaming Demonstration (v{__version__})...")
    engine = ContinuumEngine.create(embedding_dim=16, state_dim=16, hot_capacity=50, cold_capacity=100)

    print("\n1. Streaming 200 operational events with cyclic regime shift...")
    for t in range(200):
        # Inject subtle anomaly at step 50
        if t == 50:
            vec = torch.randn(16) * 2.5
            tag = "CRITICAL_ANOMALY_ANCHOR"
        else:
            vec = torch.randn(16)
            tag = "normal_telemetry"

        res = engine.step(vec, payload_ref=tag)
        if t % 40 == 0 or t == 50:
            print(f"   [Step {t:3d}] Importance={res.importance:.3f} | Slots={res.total_slots_used}/150 | Tag={tag}")

    print("\n2. Simulating Terminal Incident at step 200...")
    symptom_vector = torch.randn(16) * 2.5
    print("   Querying Retrospective Revision Engine for root causes...")
    matches = engine.query(symptom_vector, top_k=3)

    print("\n3. Retrospective Causal Candidates Retrieved:")
    for rank, m in enumerate(matches, 1):
        print(f"   #{rank}: Event ID={m.event_id:3d} | Score={m.revision_score:.4f} | Sim={m.components['sim']:.3f} | Provenance={m.provenance}")
    print("\nDemo completed successfully.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="continuum",
        description="Continuum: Continuous Temporal Intelligence Engine CLI",
    )
    parser.add_argument("--version", action="store_true", help="Show Continuum version and exit")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    p_status = subparsers.add_parser("status", help="Display memory bank configuration and runtime status")
    p_status.set_defaults(func=cmd_status)

    p_demo = subparsers.add_parser("demo", help="Run an interactive live streaming demo")
    p_demo.set_defaults(func=cmd_demo)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.version:
        cmd_version(args)
        sys.exit(0)

    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
