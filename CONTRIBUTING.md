# Contributing to DiffHound

Thank you for your interest in contributing to DiffHound! We welcome contributions that maintain our core invariants:

## Core Engineering Invariants
1. **100% Native Rust & Zero External Dependencies**: `continuum-core` and `diffhound-cli` must rely strictly on standard library Rust. Do not add external crates without architectural review.
2. **Zero Noise**: Clean PRs must generate 0 comments and produce exit code 0.
3. **Bounded Physical Memory**: State representation must strictly respect physical $O(K)$ slots.
4. **Deterministic Testing**: Every fix must be validated with automated tests passing 100% (`cargo test --workspace`).

## Development Workflow
```bash
# 1. Clone & build
git clone https://github.com/reacherwu/diffhound.git
cd diffhound
cargo build

# 2. Run test suite
cargo test --workspace

# 3. Verify DiffHound against your own branch
./target/debug/diffhound review --base origin/main --fail-on-regression
```
