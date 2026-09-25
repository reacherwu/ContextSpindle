#!/usr/bin/env bash
# Install ContextSpindle from a checked-out source tree.
# Usage: ./install.sh [install-root]
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

install_args=(--path "${package_dir}" --locked --bin contextspindle)
if [[ $# -gt 1 ]]; then
    echo "Usage: ./install.sh [install-root]" >&2
    exit 1
fi
if [[ $# -eq 1 ]]; then
    install_args+=(--root "$1")
fi
cargo install "${install_args[@]}"
echo "ContextSpindle installed."
echo "Run 'contextspindle init .' inside each workspace, then 'contextspindle task create <goal>'."
echo "If the command is not found, add the selected install root's bin directory to PATH yourself."
