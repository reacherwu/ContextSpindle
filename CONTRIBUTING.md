# Contributing to ContextSpindle

ContextSpindle focuses on durable task continuity and task-aware context assembly. Contributions should maintain these invariants:

## Core Engineering Invariants
1. **Durable task state**: An evicting memory cache must never be the sole copy of active or historical task records.
2. **Bounded retrieval memory**: The existing hot/cold memory representation must respect physical $O(K)$ slots.
3. **Repeatable retrieval**: A fixed snapshot, query, and configuration should produce the same retrieval result.
4. **Evidence-backed claims**: Test task recovery, context budget, and retrieval behavior before claiming reliability or token savings.

## Development Workflow
```bash
# 1. Build from this checkout
cargo build

# 2. Run test suite
cargo test --workspace

```
