# Documentation map

## Current ContextSpindle product

- [Product scope](PRODUCT-SCOPE.md): what the task-continuity product does and does not promise.
- [Agent protocol](AGENT-PROTOCOL.md): task creation, resumption, switching, and handoff.
- [Developer quickstart](DEVELOPER_QUICKSTART.md): local CLI and MCP setup.
- [Operations](OPERATIONS.md): integrity checks, backup, restore, security, and capacity.
- [Task-ledger benchmark](TASK-LEDGER-BENCHMARK.md): reproducible current-product measurements and their limits.
- [Naming decision](NAME-CHANGE.md): the public rename and retained compatibility identifiers.

## Historical bounded-memory research

The `continuum` Python module, `continuum-core` Rust crate, `.continuum/` snapshot format, earlier paper, and research experiments remain for compatibility and provenance. [BENCHMARKS.md](BENCHMARKS.md), [EXPERIMENTS.md](EXPERIMENTS.md), [ARCHITECTURE.md](ARCHITECTURE.md), [CLAIM_AUDIT_REPORT.md](CLAIM_AUDIT_REPORT.md), and the `paper/` and `experiments/results/` trees document that earlier engine. These records should not be read as performance or durability claims about the new task ledger.

Older competitive comparisons, positioning notes, and developer audits describe the previous research scope. They are retained as historical context, not as the current product specification. The obsolete marketing showcase and an invalid quickstart were removed because they contained broken links or unsupported current-product claims.

## Website assets

GitHub Pages serves this repository's `docs/` directory. `index.html`, `license.html`, `llms.txt`, `llms-full.txt`, `robots.txt`, and `sitemap.xml` in this directory are site files. Root-level copies that served no current build or publication path were removed where possible.
