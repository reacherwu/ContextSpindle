# Task ledger smoke benchmark

## Repeatable product-path measurement, 2026-09-25

The [benchmark runner](../benchmarks/task_ledger_product.py) and [raw JSON result](../benchmarks/results/task-ledger-2026-09-25.json) are the primary evidence for the current task-ledger product. The runner built a fresh temporary workspace, created one anchor task with a goal, completion criteria, next action, decision, evidence, and 24 notes, then created 999 unrelated tasks through separate release CLI processes. It queried the ledger from new processes 11 times per operation on a warm filesystem cache, corrupted the optional retrieval snapshot, and verified that task context remained readable. It also backed up and restored the ledger into a fresh workspace.

On macOS 26.6.2 arm64, Apple M4, the 1,000-task workload yielded these measured values:

| Operation | Median | p95 | Samples |
| --- | ---: | ---: | ---: |
| Inbox, 10 tasks | 32.80 ms | 33.92 ms | 11 |
| Search anchor, 10 results | 32.49 ms | 32.89 ms | 11 |
| Anchor context, 2,048-byte budget | 34.23 ms | 35.73 ms | 11 |
| Verify all tasks | 62.73 ms | 63.44 ms | 11 |

For a deliberately naive comparison, concatenating all 10 paginated task-summary responses would send 322,607 UTF-8 bytes, or 94,701 `cl100k_base` tokens, to a model. The selected anchor's 2,048-byte-budget context contained 1,908 bytes, or 420 tokens under the same encoding. That is 99.56% fewer tokens **for this comparison only**; it is not a general product token-savings guarantee, and the two inputs are not semantically identical. The anchor goal and next action survived at every tested budget. At 512, 1,024, 2,048, and 4,096 byte ceilings, the context used 118, 204, 420, and 852 `cl100k_base` tokens respectively, while explicitly reporting 25, 22, 16, and 4 omitted optional items. `tiktoken` 0.12.0 was used for those measurements; the product itself enforces a conservative UTF-8 byte ceiling, not that tokenizer's exact token count.

The optional cache-corruption and backup/restore checks both passed in this temporary workload. The tasks and notes are synthetic, though the timings, outputs, and token counts are actual execution results. No results here establish multi-year durability, cold-cache latency, very long per-task histories, Linux performance, or model answer quality.

Reproduce with:

```bash
cargo build --release --bin contextspindle
python3 -m benchmarks.task_ledger_product --tasks 1000 --repeats 11
```

The runner requires `tiktoken` to report `cl100k_base` counts. It prints JSON and removes its temporary workspace after the run.
Task IDs and caller labels include process/time information, so a rerun can produce slightly different summary-token counts even with the same task text. Filesystem and process-startup timing will also vary.

## Earlier single-run smoke observation

This is a single local smoke measurement, not a latency service-level objective or a multi-year durability claim. It covers the durable task ledger, not the earlier bounded-memory retrieval benchmarks.

On 2026-09-25, a release build of ContextSpindle 0.2.0 ran on macOS Darwin 25.6.0 arm64, Apple M4. A fresh temporary workspace was initialized. One anchor task with a completion criterion and 999 unrelated tasks were created through separate CLI processes, each using the normal fsynced ledger write path. The complete shell run, including initialization, task creation, and the four queries below, took 21.1 seconds of wall time; most of that run was the 1,000-process creation loop. The ledger was queried from new CLI processes with warm filesystem caches using `/usr/bin/time -p`:

| Operation | Wall time, one run |
| --- | ---: |
| `task inbox 10` | 0.06 s |
| `task search 'Old anchor' 10` | 0.03 s |
| `task context <anchor-id> 2048` | 0.03 s |
| `task verify` | 0.05 s |

The context command recovered the first task after 999 unrelated tasks; verification succeeded for all 1,000 tasks. This test did not measure cold-cache behavior, concurrent writers, very long individual task histories, other filesystems, Docker, or Linux. `list`, `search`, `inbox`, and child discovery scan task directories, so latency grows with the number of tasks. Operators should measure their own workload and storage device before setting a performance target.

To reproduce from the repository root on a Unix-like system with `jq` and `/usr/bin/time` available, use a new temporary workspace:

```bash
bin="$PWD/target/release/contextspindle"
bench_root="$(mktemp -d)"
"$bin" init "$bench_root" >/dev/null
anchor_id="$(cd "$bench_root" && "$bin" task create 'Old anchor task' --criteria 'Recovered' | jq -r .id)"
for n in {1..999}; do
  (cd "$bench_root" && "$bin" task create "Unrelated task $n" >/dev/null)
done
(cd "$bench_root" && /usr/bin/time -p "$bin" task inbox 10 >/dev/null)
(cd "$bench_root" && /usr/bin/time -p "$bin" task search 'Old anchor' 10 >/dev/null)
(cd "$bench_root" && /usr/bin/time -p "$bin" task context "$anchor_id" 2048 >/dev/null)
(cd "$bench_root" && /usr/bin/time -p "$bin" task verify >/dev/null)
```
