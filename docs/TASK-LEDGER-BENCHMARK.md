# Task ledger smoke benchmark

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
