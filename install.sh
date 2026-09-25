#!/usr/bin/env bash
# Install ContextSpindle from a checked-out source tree.
set -euo pipefail

source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
package_dir="${source_dir}/crates/continuum-cli"

if [[ ! -f "${package_dir}/Cargo.toml" ]]; then
    echo "ContextSpindle source checkout not found beside install.sh." >&2
    echo "Clone the project, then run its install.sh from that checkout." >&2
    exit 1
fi
if ! command -v cargo >/dev/null 2>&1; then
    echo "Rust Cargo is required: https://rustup.rs" >&2
    exit 1
fi

cargo install --path "${package_dir}" --locked --bin contextspindle
echo "ContextSpindle installed to Cargo's bin directory."
echo "Run 'contextspindle init .' inside each workspace, then 'contextspindle task create <goal>'."
echo "If the command is not found, add Cargo's bin directory to PATH yourself."
