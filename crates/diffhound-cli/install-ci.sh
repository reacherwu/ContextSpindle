#!/usr/bin/env bash
# DiffHound 1-Shot CI Installer for Open Source Repositories
# Usage: curl -fsSL https://raw.githubusercontent.com/reacherwu/continuum/main/crates/diffhound-cli/install-ci.sh | bash

set -euo pipefail

echo "================================================================="
echo "  🐕 DiffHound: Installing Zero-Noise CI PR Guard"
echo "================================================================="

if [ ! -d ".git" ]; then
    echo "❌ Error: Current directory is not a Git repository root."
    echo "   Please navigate to the root of your project and re-run."
    exit 1
fi

mkdir -p .github/workflows

WORKFLOW_FILE=".github/workflows/diffhound.yml"

cat << 'EOF' > "$WORKFLOW_FILE"
name: DiffHound Anti-Regression Guard

on:
  pull_request:
    branches: [ main, master ]

jobs:
  guard:
    name: DiffHound Zero-Noise PR Guard
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Set up Rust
        uses: dtolnay/rust-toolchain@stable

      - name: Cache Cargo Dependencies
        uses: actions/cache@v4
        with:
          path: |
            ~/.cargo/bin/
            ~/.cargo/registry/index/
            ~/.cargo/registry/cache/
            ~/.cargo/git/db/
            target/
          key: ${{ runner.os }}-cargo-${{ hashFiles('**/Cargo.lock') }}
          restore-keys: |
            ${{ runner.os }}-cargo-

      - name: Run DiffHound Review
        uses: reacherwu/continuum@main
        with:
          base-ref: 'origin/${{ github.base_ref }}'
          fail-on-regression: true
          threshold: '0.45'
EOF

echo "✅ Created $WORKFLOW_FILE successfully!"
echo ""
echo "Next step:"
echo "  git add .github/workflows/diffhound.yml"
echo "  git commit -m \"ci: add DiffHound Zero-Noise PR Guard\""
echo "  git push"
echo ""
echo "🎉 DiffHound is now actively guarding your pull requests against historical regressions!"
