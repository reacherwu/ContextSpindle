# Contributing to ContextSpindle

Thanks for helping improve durable task continuity for AI agents. Before a large design change, open an issue to describe the problem, expected behavior, compatibility impact, and how it can be tested. Small bug fixes and documentation improvements can go directly to a pull request.

## Product boundaries

- The `.contextspindle/tasks/` ledger is the authoritative task record. The bounded `.continuum/` retrieval cache must never be its only copy.
- Preserve the bounded hot/cold slot limits and deterministic retrieval for a fixed snapshot, query, and configuration. Model-generated responses are not deterministic.
- Treat snapshot paths, schemas, and legacy CLI/API aliases as compatibility surfaces. Schema changes need a migration and tests against existing records.
- DiffHound PR review is historical, not an active ContextSpindle feature. Preserve historical papers, benchmark data, and failed experiments rather than rewriting them as new-product evidence.

## Development setup

Use a current stable Rust toolchain and Python 3 with the repository's test dependencies. Build from this checkout; a global install, IDE change, or Git hook is not required.

```sh
cargo build --release --locked --workspace
cargo test --workspace
python3 -m pytest -q
```

The release build makes the native library available to Python integration tests. If those tests report that the native library is unavailable, build the workspace before rerunning them. If a Python dependency is missing, consult the repository's Python packaging files and report the environment in your PR; do not silently skip failing tests.

## Issues and pull requests

1. Search existing issues and describe the observable problem or user benefit. For a bug, include the ContextSpindle version, operating system, minimal reproduction, expected behavior, and actual behavior.
2. Keep changes focused. Add or update Rust/Python tests for behavior changes; include a migration test for persisted formats.
3. Explain how the change affects task durability, context budgets, retrieval determinism, compatibility, and recovery where relevant. Use the [pull request template](.github/pull_request_template.md).
4. For performance, token, or reliability claims, provide the exact workload, command, hardware, build profile, repetitions, raw results, and limitations. Do not present historical memory-engine benchmarks as task-ledger results.

Never post real task ledgers, private prompts, access tokens, or customer data in issues, PRs, logs, or benchmark fixtures. Use synthetic examples. For a suspected security vulnerability, follow [SECURITY.md](SECURITY.md) instead of opening a public issue. Community interactions are covered by the [Code of Conduct](CODE_OF_CONDUCT.md).
