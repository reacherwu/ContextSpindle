# P1 regression checkpoint

No further code edits or broad lint/workspace runs at this checkpoint.

Exact independent-review findings:
- [x] P1-1: init uses the transactional writer lock and preserves existing memory. Test: init_preserves_existing_memory_and_configuration. Repeated init is tested; simultaneous init specifically is not separately tested.
- [x] P1-2: output-option parsing preserves literal text/path arguments. Test: json_options_preserve_literal_text_and_paths.
- [x] P1-3: JSON decodes valid UTF-16 surrogate pairs. Test: unicode_surrogates_follow_json_semantics.

Dependent reliability regressions:
- [x] CLI/MCP storage failures never claim success: storage_errors_are_nonzero_and_never_claim_success, mcp_storage_failures_are_tool_errors_without_empty_fallback.
- [x] Recovery CLI: recovery_check_backup_and_confirmed_restore.
- [x] Storage integration suite: stable OS lock, long holder/process exit, process/thread RMW, invalid-state preservation, atomic publication and backup/restore.

Raw execution evidence: P1_REGRESSION.log. Each invocation must exit zero before committing.
Scope: CLI memory/MCP/error handling, JSON compatibility, core lock/persistence/recovery, minimum Rust version, and related tests. Runner changes are excluded from this checkpoint commit and remain uncommitted. No installation, Hermes configuration changes, or live-memory access.
This checkpoint is not a production-readiness certification or a performance benchmark. CTNM0001 has no checksum; old and new lock protocols must not run concurrently.
