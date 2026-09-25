# Decisions

## D-0004 — Task continuity is the sole product scope

**Status:** accepted locally (2026-09-25)

ContextSpindle exists to preserve agent task goals and progress across context compaction, interruptions, unrelated tasks, and long time spans. The authoritative task ledger must be durable and distinct from the bounded, evicting retrieval memory. Context assembly must be task-aware and token-budgeted. PR review and DiffHound are removed from the active product scope and build. Historical research records remain for provenance. See [PRODUCT-SCOPE.md](PRODUCT-SCOPE.md).

## D-0003 — ContextSpindle name and product focus

**Status:** accepted locally (2026-09-25)

The project name is ContextSpindle. At the time of this decision, its main function was persistent, deterministic retrieval of selected context for AI agents; D-0004 supersedes that product framing. Public CLI and MCP names gain ContextSpindle aliases; legacy identifiers, snapshots, historical experiment records, and the published paper title remain compatible. The collision check and exact scope are recorded in [NAME-CHANGE.md](NAME-CHANGE.md).

## D-0001 — Research-first v0.1

**Status:** accepted (2026-09-13)

Continuum v0.1 is a modular Python/PyTorch research prototype. It will not introduce product SDKs, CUDA/Metal optimization, external vector databases, or commercial claims during the initial validation loop.

## D-0002 — Independent evidence lanes

**Status:** accepted (2026-09-13)

Model implementation, benchmark standards, adversarial tests, and technical judgment have separate repository roles. Repository isolation is provided by Git worktrees when agents make edits.
