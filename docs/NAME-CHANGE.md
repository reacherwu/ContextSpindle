# Naming decision — ContextSpindle

Date: 2026-09-25. The project formerly called Continuum is now **ContextSpindle**. This document records the original rename boundary. The later task-continuity product definition in [PRODUCT-SCOPE.md](PRODUCT-SCOPE.md) supersedes its initial memory-only framing; DiffHound is no longer in the active product scope.

## Collision check

An exact-name public web search and package lookups were performed on 2026-09-25. `contextspindle` returned no exact public project match in the searches performed; PyPI, npm, and crates.io package endpoints returned 404. This is a practical collision check, not a legal trademark clearance or a guarantee of future registry availability.

Rejected candidates:

- **Aevum**: already used by a Rust/MCP causal-memory project for AI agents, and by other AI agent products: <https://github.com/kwailapt/aevum> and <https://github.com/aevum-labs/aevum>.
- **Memstead**: existing agent-memory project: <https://github.com/memstead/memstead>.
- **Tracehold**: existing AI agent security product: <https://tracehold.ai/>.
- **RootKeep**: existing software brands: <https://rootkeep.family/>.

## Migration boundary

The new public project name, user-facing documentation, CLI alias, and MCP server key are ContextSpindle. The existing `continuum-cli` executable, `continuum` Python module, `continuum-core` Rust crate, `.continuum/` snapshots, older MCP tool names, historical experiments, and published paper title retain their identifiers for compatibility and provenance. A future breaking release may migrate these identifiers with explicit snapshot conversion and tests.

The local desktop directory is now `ContextSpindle`. The Git remote `reacherwu/diffhound`, external website URLs, published DOI, and package registry ownership have not been changed; changing those external identities requires a separate migration.
