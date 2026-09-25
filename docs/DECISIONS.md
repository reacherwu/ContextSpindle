# Decisions

## D-0003 — ContextSpindle name and product focus

**Status:** accepted locally (2026-09-25)

The project name is ContextSpindle. Its main function is persistent, deterministic retrieval of selected context for AI agents. DiffHound remains an application of the engine. Public CLI and MCP names gain ContextSpindle aliases; legacy identifiers, snapshots, historical experiment records, and the published paper title remain compatible. The collision check and exact scope are recorded in [NAME-CHANGE.md](NAME-CHANGE.md).

## D-0001 — Research-first v0.1

**Status:** accepted (2026-09-13)

Continuum v0.1 is a modular Python/PyTorch research prototype. It will not introduce product SDKs, CUDA/Metal optimization, external vector databases, or commercial claims during the initial validation loop.

## D-0002 — Independent evidence lanes

**Status:** accepted (2026-09-13)

Model implementation, benchmark standards, adversarial tests, and technical judgment have separate repository roles. Repository isolation is provided by Git worktrees when agents make edits.
