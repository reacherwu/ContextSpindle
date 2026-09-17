# Reliability hardening plan
Baseline: upstream 4c9df39. Work only in this branch; do not install, modify Hermes configuration or touch user memory.
Keep Rust core + local CLI/MCP. No service, cloud, Docker or new AI provider is required for this native library repair.
Priority 1: propagate storage errors through CLI nonzero exit and MCP isError; never synthesize empty state on corruption.
Priority 2: OS advisory lock held throughout mutation, stable lock inode, no elapsed-age stealing; internal unlocked helpers. Rust std file locking preferred if toolchain supports it; declare MSRV.
Priority 3: durable atomic save, parent sync, temporary-file cleanup, bounded decoding/validation, explicit backup/check/restore with overwrite confirmation. Preserve legacy readable snapshots and document integrity limits.
Priority 4: runner stores observations rather than causal facts, correlates only identical command/project, avoids raw log/argument retention and does not auto-ingest fixes.
Priority 5: machine-readable memory CLI and verified native MCP, strict inputs and complete text output.
Priority 6: honest limitations and reproducible isolated load/recall measurements, no universal recall or memory-size claims.
Acceptance: real files and subprocesses, failure propagation, restart, lock contention/long holder/process exit, multi-process RMW, recover/invalid-backup, legacy roundtrip, Unicode/full text. No offensive reproduction or live-data tests. Independent defensive review, fix/re-review, measured stress evidence, branch PR (not direct main push).
