# S7 stale / cross-task evidence — measured results

## Baseline (before fix)

- **When:** 2026-10-05 23:53:21 CST
- **Commit:** `6764737b8fe3aa2ccd4c86010d14426794777a2d`
- **Binary:** `/workspace/tmp/csp-target/release/contextspindle`
- **Wall clock:** 151 ms
- **Raw JSON:** [s7-stale-evidence-baseline.json](s7-stale-evidence-baseline.json)

| Case | Threat | Done outcome | Verdict (gate) |
| --- | --- | --- | --- |
| S7a | Criteria changed C1→C2 after evidence logged | **accepted** | FAIL — gate missing |
| S7b | Foreign-task evidence text attached to T_b | **accepted** | FAIL — gate missing |

Baseline matches Article 1 field check: done gate ignored evidence binding (only criteria presence, clear blocker, finished deps).

## After fix

- **When:** 2026-10-06 00:04:44 CST
- **Commit (at measurement):** `6764737b8fe3aa2ccd4c86010d14426794777a2d`
- **Binary:** `/workspace/tmp/csp-target/debug/contextspindle` (test profile via `cargo test`)
- **Wall clock:** 31 ms
- **Raw JSON:** [s7-stale-evidence-after.json](s7-stale-evidence-after.json)

| Case | Threat | Done outcome | Error | Verdict (gate) |
| --- | --- | --- | --- | --- |
| S7a | Criteria changed C1→C2 after evidence logged | **rejected** | `Error: Evidence is missing or stale relative to current completion criteria` | PASS — gate works |
| S7b | Foreign bound evidence attached to T_b | **rejected** | `Error: Evidence task id mismatch` | PASS — gate works |

## Before vs after

| Case | Before (baseline) | After (fix) |
| --- | --- | --- |
| S7a | accepted (FAIL — gate missing) | rejected (PASS — gate works) |
| S7b | accepted (FAIL — gate missing) | rejected (PASS — gate works) |

Reproduce:

```bash
CARGO_TARGET_DIR=/workspace/tmp/csp-target cargo test -p continuum-cli s7_stale_evidence -- --nocapture
```
