"""
Realistic Dataset for Empirical Baseline Comparison Benchmark.

Contains:
1. Four realistic software engineering tasks with historical traps and latent regressions.
2. Background rule sets simulating repository AGENTS.md growth (5, 25, 50 rules).
3. Production incident logs and historical commits for provenance testing.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class Scenario:
    id: str
    name: str
    category: str
    prompt: str
    historical_incident: str
    causal_anchor: str
    commit_sha: str
    ground_truth_constraint: str
    trap_description: str
    has_ci_test: bool  # Can CI unit test catch this deterministically?


# 4 Real-World Developer Tasks with concrete file paths and commit provenance
SCENARIOS: List[Scenario] = [
    Scenario(
        id="task_net_tls",
        name="TLS Legacy Handshake & Fallback Trap",
        category="networking",
        prompt=(
            "Please refactor `crates/net/src/client.rs` to modernize the connection pool builder. "
            "Clean up redundant configuration flags, remove deprecated legacy methods, and standardize on TLS 1.3 defaults."
        ),
        historical_incident=(
            "INCIDENT #412: Production outage on v1.4 client connections. "
            "Error: SSLV3_ALERT_HANDSHAKE_FAILURE on banking gateway endpoints. "
            "Root cause: Gateway uses legacy TLS 1.2 with custom RSA-AES cipher. "
            "Fix: Enforced fallback cipher suite `DEFAULT:@SECLEVEL=1:!aNULL` when connecting to legacy endpoints."
        ),
        causal_anchor=(
            "FIX: [4b8e21a] crates/net/src/client.rs: preserve legacy cipher fallback handler to prevent SSLV3_ALERT_HANDSHAKE_FAILURE"
        ),
        commit_sha="4b8e21a",
        ground_truth_constraint="crates/net/src/client.rs: preserve legacy cipher fallback",
        trap_description="Agent naively purges legacy cipher fallback to enforce 'pure TLS 1.3', breaking banking gateway traffic in production.",
        has_ci_test=True,
    ),
    Scenario(
        id="task_db_lock",
        name="SQLite Concurrency & WAL Busy Contention",
        category="database",
        prompt=(
            "Refactor `crates/storage/src/db.rs` to optimize SQLite connection initialization for fast cold starts. "
            "Streamline pragma statements and minimize disk I/O during startup."
        ),
        historical_incident=(
            "INCIDENT #529: High-concurrency write requests threw `database is locked (SQLITE_BUSY)`. "
            "Root cause: SQLite default busy handler immediately returns error under write contention. "
            "Fix: Set `PRAGMA busy_timeout = 5000;` and enable WAL journal mode in connection init."
        ),
        causal_anchor=(
            "FIX: [7e3f19c] crates/storage/src/db.rs: set PRAGMA busy_timeout = 5000 and WAL mode to prevent SQLITE_BUSY crashes"
        ),
        commit_sha="7e3f19c",
        ground_truth_constraint="crates/storage/src/db.rs: set PRAGMA busy_timeout = 5000 and WAL mode",
        trap_description="Agent removes busy_timeout to make connection setup faster, causing immediate database lockouts under multi-agent load.",
        has_ci_test=True,
    ),
    Scenario(
        id="task_simd_align",
        name="ARM64 AVX2 Unaligned SIMD Memory Trap",
        category="systems",
        prompt=(
            "Refactor `crates/core/src/ring_buffer.rs` to eliminate struct padding and pack fields "
            "for minimal memory footprint in embedded environments."
        ),
        historical_incident=(
            "INCIDENT #604: Process crashed with `SIGBUS: 10 (alignment fault)` on Apple Silicon (ARM64) and Graviton. "
            "Root cause: Vectorized ring buffer operations require strict 64-byte cache-line alignment. "
            "Fix: Add `#[repr(align(64))]` to RingBuffer struct and verify pointer alignment before SIMD loads."
        ),
        causal_anchor=(
            "FIX: [9102ef8] crates/core/src/ring_buffer.rs: enforce #[repr(align(64))] to prevent SIGBUS alignment faults on ARM64"
        ),
        commit_sha="9102ef8",
        ground_truth_constraint="crates/core/src/ring_buffer.rs: enforce #[repr(align(64))]",
        trap_description="Agent removes align(64) attribute to 'pack' memory tighter, causing catastrophic SIGBUS crashes on ARM servers.",
        has_ci_test=True,
    ),
    Scenario(
        id="task_kqueue_darwin",
        name="BSD/Darwin kqueue File Descriptor Trap",
        category="os_runtime",
        prompt=(
            "Diagnose and fix the file watcher in `crates/watcher/src/sys.rs` which fails on macOS with error: "
            "`kqueue error: EVFILT_READ returned EPERM on fd`."
        ),
        historical_incident=(
            "INCIDENT #781: File watcher failed on macOS build agents. "
            "Root cause: BSD kqueue does not support regular vnode file descriptors for EVFILT_READ; returns EPERM. "
            "Fix: Use `EVFILT_VNODE` with `NOTE_WRITE | NOTE_EXTEND` instead of `EVFILT_READ` for regular files on Darwin."
        ),
        causal_anchor=(
            "FIX: [a3d8901] crates/watcher/src/sys.rs: use EVFILT_VNODE instead of EVFILT_READ for regular files on Darwin/macOS"
        ),
        commit_sha="a3d8901",
        ground_truth_constraint="crates/watcher/src/sys.rs: use EVFILT_VNODE instead of EVFILT_READ",
        trap_description="Agent assumes file descriptor is closed or permissions are wrong and suggests chmod or reopening file, missing the OS kernel limitation.",
        has_ci_test=False,  # Environmental OS-specific issue: fails on macOS but passes on Linux CI runner!
    ),
]


CORE_RULES_5: List[str] = [
    "1. Code Quality: Use standard Rust 2024 edition idioms, zero unsafe code unless strictly audited.",
    "2. Error Handling: Return `Result<T, CustomError>` instead of `.unwrap()` or `.expect()` in library paths.",
    "3. Concurrency: Never hold locks across `.await` suspension points; prefer channel-based messaging.",
    "4. Clean Diff: Keep changes scoped strictly to the requested task; avoid unrequested formatting or dependency churn.",
    "5. CI Compliance: Ensure all unit tests pass before proposing final modifications.",
]

ACCUMULATED_RULES_25: List[str] = CORE_RULES_5 + [
    "6. Git Commits: Follow Conventional Commits format (`feat:`, `fix:`, `refactor:`, `docs:`).",
    "7. Logging: Use `tracing::debug!` for verbose diagnostic logs; never use raw `println!` in library crates.",
    "8. Networking: Set 15-second default connect timeouts on all outgoing HTTP client requests.",
    "9. TLS Compatibility: In `crates/net/src/client.rs`, preserve legacy cipher fallback handler `DEFAULT:@SECLEVEL=1:!aNULL` for banking endpoints (Incident #412).",
    "10. Serialization: All public structs must implement `serde::Serialize` and `serde::Deserialize`.",
    "11. JSON API: Use camelCase for external API JSON fields and snake_case for internal Rust fields.",
    "12. Allocations: Avoid allocating memory inside hot-path event loops; preallocate vectors with `Vec::with_capacity`.",
    "13. Database: Always configure `PRAGMA busy_timeout = 5000` and WAL mode in `crates/storage/src/db.rs` to prevent SQLITE_BUSY (Incident #529).",
    "14. Migrations: Database schema migrations must be backwards-compatible for at least one release cycle.",
    "15. Struct Alignment: Preserve `#[repr(align(64))]` on RingBuffer in `crates/core/src/ring_buffer.rs` to prevent ARM64 SIGBUS crashes (Incident #604).",
    "16. File Watching: On macOS/Darwin, register `EVFILT_VNODE` rather than `EVFILT_READ` with kqueue in `crates/watcher/src/sys.rs` (Incident #781).",
    "17. Shell Commands: Never execute shell commands with user-supplied input without strict path and character validation.",
    "18. Dependencies: Do not add external crates to `crates/continuum-core`; maintain zero-dependency pure stdlib architecture.",
    "19. Documentation: Every public function must contain a rustdoc comment explaining arguments and failure conditions.",
    "20. Deprecation: Mark deprecated functions with `#[deprecated(since = '...', note = '...')]` rather than deleting them immediately.",
    "21. Benchmarks: Run criterion benchmarks on any PR touching the core ingestion pipeline.",
    "22. Platform Support: Support x86_64, aarch64 (Linux/macOS), and wasm32-unknown-unknown targets.",
    "23. Sensitive Data: Never log API tokens, auth headers, or user passwords even at `trace` level.",
    "24. File Locks: Hold OS-level transactional `flock` across read-modify-write sequences on state files.",
    "25. Signal Handling: Clean up background lockfiles on SIGINT/SIGTERM before process exit.",
]

BLOATED_RULES_50: List[str] = ACCUMULATED_RULES_25 + [
    "26. Regex: Precompile regular expressions in `lazy_static!` or `std::sync::OnceLock` instead of recreating them per request.",
    "27. Timeouts: Wrap all upstream RPC calls with exponential backoff and maximum 3 retry attempts.",
    "28. Time Zones: Store all database timestamps as UTC ISO-8601 strings or UNIX epoch milliseconds.",
    "29. Float Math: Use `f64::total_cmp` when sorting floats to handle NaN and infinity deterministically.",
    "30. Hash Maps: Use `ahash` or `FxHashMap` for internal performance-critical hash sets, standard `SipHash` for public untrusted inputs.",
    "31. File Permissions: Ensure newly created state directories have POSIX permissions `0700`.",
    "32. Atomic Renames: State files must be written to `.tmp.<pid>` and atomically renamed to prevent tearing.",
    "33. Fsync: Call `fsync()` on parent directory after atomic rename to ensure directory entry durability.",
    "34. Metrics: Export Prometheus metrics on port 9090 when running in daemon mode.",
    "35. Tracing: Set span names to `<module>::<function_name>` for OpenTelemetry compatibility.",
    "36. Env Vars: Use prefix `CONTINUUM_` for all environment variable configurations.",
    "37. Memory Bounds: Maximum memory manifold allocation is strictly bounded at 750 physical slots.",
    "38. Cold Eviction: Cold memory eviction must use pairwise cosine diversity pruning, never FIFO.",
    "39. Causal Exemption: Exempt memories from temporal decay when causal similarity exceeds threshold 0.25.",
    "40. JSON Parser: Use the zero-dependency recursive-descent parser for MCP communication.",
    "41. MCP Protocol: Return `isError: true` on failed tool executions instead of returning successful empty responses.",
    "42. Exit Codes: All CLI error conditions must terminate with exit code 1.",
    "43. Git Hooks: Post-commit hook must safely chain to pre-existing hooks if present.",
    "44. Terminal ID: Persistent terminals must share environment variables across invocations.",
    "45. File Watching Events: Batch file system change events with a 50ms debounce window.",
    "46. Test Coverage: Minimum test coverage for core module is 85% line coverage.",
    "47. Release Builds: Always strip debug symbols in release profile with `strip = true` in Cargo.toml.",
    "48. LTO: Enable ThinLTO for release builds to optimize cross-crate inlining.",
    "49. Panics: Set `panic = 'abort'` in production release profile to minimize binary footprint.",
    "50. Checksums: Append 64-bit FNV-1a checksum and `CTNMFOOT` footer to all persistent snapshot files.",
]


def format_agents_md(rules: List[str]) -> str:
    header = "# Repository Agent Guidelines & Architecture Rules\n\n"
    header += "> Follow these rules carefully when making any modifications to this repository.\n\n"
    return header + "\n".join(rules) + "\n"
