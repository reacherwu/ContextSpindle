# Decisions

## D-0001 — Research-first v0.1

**Status:** accepted (2026-09-13)

Continuum v0.1 is a modular Python/PyTorch research prototype. It will not introduce product SDKs, CUDA/Metal optimization, external vector databases, or commercial claims during the initial validation loop.

## D-0002 — Independent evidence lanes

**Status:** accepted (2026-09-13)

Model implementation, benchmark standards, adversarial tests, and technical judgment have separate repository roles. Repository isolation is provided by Git worktrees when agents make edits.
