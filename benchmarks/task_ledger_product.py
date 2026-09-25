"""Reproducible CLI-process task-continuity smoke benchmark.

Requires the release binary and tiktoken for reporting one encoding's token
counts. All ledger writes happen in a temporary workspace. Prints JSON only.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
import platform
import statistics
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import tiktoken


ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "target" / "release" / "contextspindle"


def call(workspace: Path, *args: str) -> tuple[str, float]:
    start = time.perf_counter()
    result = subprocess.run(
        [str(BIN), *args],
        cwd=workspace,
        text=True,
        capture_output=True,
        check=False,
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    if result.returncode:
        raise RuntimeError(f"{args}: {result.stderr.strip()}")
    return result.stdout, elapsed_ms


def timings(workspace: Path, *args: str, repeats: int) -> dict[str, float]:
    values = [call(workspace, *args)[1] for _ in range(repeats)]
    ordered = sorted(values)
    return {
        "median_ms": round(statistics.median(values), 2),
        "p95_ms": round(ordered[math.ceil(0.95 * len(ordered)) - 1], 2),
        "runs": repeats,
    }


def run(task_count: int, repeats: int) -> dict:
    if task_count < 2 or repeats < 3:
        raise ValueError("task_count must be >= 2 and repeats must be >= 3")
    if not BIN.is_file():
        raise RuntimeError(f"Build the release binary first: {BIN}")
    encoding = tiktoken.get_encoding("cl100k_base")
    with tempfile.TemporaryDirectory(prefix="contextspindle-product-bench-") as temp:
        base = Path(temp)
        live = base / "live"
        live.mkdir()
        call(live, "init", ".")
        goal = "Publish ContextSpindle without losing the original task across interruptions"
        criteria = "Repository is renamed, tests pass, and recovery instructions are documented"
        anchor, _ = call(live, "task", "create", goal, "--criteria", criteria)
        anchor_id = json.loads(anchor)["id"]
        updates = [
            "task", "update", anchor_id, "--status", "active",
            "--next", "Verify benchmark evidence and publish the README",
            "--decision", "The durable task ledger is authoritative; cache hints are optional",
            "--evidence", "docs/TASK-LEDGER-BENCHMARK.md",
        ]
        for index in range(24):
            updates += [
                "--note",
                f"Checkpoint {index + 1}: validated a release, documentation, or recovery detail; "
                "keep the next action explicit so another agent can resume without rereading the transcript.",
            ]
        call(live, *updates)

        create_start = time.perf_counter()
        for index in range(1, task_count):
            call(
                live, "task", "create",
                f"Unrelated task {index:04d}: investigate a separate service, issue, or review request",
            )
        create_seconds = time.perf_counter() - create_start

        pages = []
        for offset in range(0, task_count, 100):
            page, _ = call(live, "task", "list", str(offset), "100")
            pages.append(page.rstrip("\n"))
        naive_all_summaries = "\n".join(pages)

        contexts = {}
        for budget in (512, 1024, 2048, 4096):
            context, _ = call(live, "task", "context", anchor_id, str(budget))
            contexts[str(budget)] = {
                "utf8_bytes": len(context.encode("utf-8")),
                "cl100k_base_tokens": len(encoding.encode(context)),
                "omitted_optional_items": int(
                    context.rsplit("Omitted optional items: ", 1)[1].strip()
                ),
                "contains_goal": goal in context,
                "contains_next": "Verify benchmark evidence" in context,
            }

        performance = {
            "inbox_10": timings(live, "task", "inbox", "10", repeats=repeats),
            "search_anchor_10": timings(
                live, "task", "search", "Publish ContextSpindle", "10", repeats=repeats
            ),
            "context_anchor_2048": timings(
                live, "task", "context", anchor_id, "2048", repeats=repeats
            ),
            "verify_all": timings(live, "task", "verify", repeats=repeats),
        }

        # The cache is deliberately broken after the measured queries. The
        # ledger must still recover the task from another CLI process.
        (live / ".continuum" / "memory.state").write_bytes(b"corrupt cache")
        recovered, _ = call(live, "task", "context", anchor_id, "2048")
        cache_corruption_survived = goal in recovered

        backup = base / "backup"
        call(live, "task", "backup", str(backup))
        fresh = base / "fresh"
        fresh.mkdir()
        call(fresh, "init", ".")
        call(fresh, "task", "restore", str(backup))
        shown, _ = call(fresh, "task", "show", anchor_id)
        restore_survived = json.loads(shown)["goal"] == goal

    return {
        "date_utc": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "task_count": task_count,
        "unrelated_task_count": task_count - 1,
        "anchor_update_count": 1,
        "anchor_note_count": 24,
        "create_unrelated_seconds": round(create_seconds, 2),
        "timing_method": "separate release CLI process; warm filesystem cache; repeated sequentially",
        "performance": performance,
        "naive_all_paginated_task_summaries": {
            "utf8_bytes": len(naive_all_summaries.encode("utf-8")),
            "cl100k_base_tokens": len(encoding.encode(naive_all_summaries)),
        },
        "context_by_budget": contexts,
        "cache_corruption_survived": cache_corruption_survived,
        "backup_restore_survived": restore_survived,
        "tokenizer": {
            "encoding": "cl100k_base",
            "tiktoken_version": importlib.metadata.version("tiktoken"),
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", type=int, default=1000)
    parser.add_argument("--repeats", type=int, default=11)
    args = parser.parse_args()
    print(json.dumps(run(args.tasks, args.repeats), ensure_ascii=False, indent=2))
