#!/usr/bin/env bash
# ContextSpindle CLI installer
# Usage: curl -fsSL https://raw.githubusercontent.com/reacherwu/diffhound/main/install.sh | bash
set -e

BOLD="\033[1m"
GREEN="\033[0;32m"
BLUE="\033[0;34m"
YELLOW="\033[0;33m"
RESET="\033[0m"

echo -e "${BOLD}${BLUE}========================================================================${RESET}"
echo -e "${BOLD}${BLUE}  ContextSpindle: Persistent Context Memory for AI Agents                ${RESET}"
echo -e "${BOLD}${BLUE}========================================================================${RESET}"

OS="$(uname -s)"
ARCH="$(uname -m)"

echo -e "-> Detected Platform: ${GREEN}${OS} (${ARCH})${RESET}"

INSTALL_DIR="${HOME}/.cargo/bin"
mkdir -p "${INSTALL_DIR}"

if command -v cargo >/dev/null 2>&1; then
    echo -e "-> Cargo detected. Building standalone native binary from source..."
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [ -d "${SCRIPT_DIR}/crates/continuum-cli" ]; then
        cargo install --path "${SCRIPT_DIR}/crates/continuum-cli" --force --quiet
    else
        echo -e "-> Building from local repository..."
        cargo install --git https://github.com/reacherwu/diffhound continuum-cli --force --quiet
    fi
else
    echo -e "${YELLOW}-> Cargo not found. Checking local pre-compiled binaries...${RESET}"
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [ -f "${SCRIPT_DIR}/target/release/contextspindle" ]; then
        cp "${SCRIPT_DIR}/target/release/contextspindle" "${INSTALL_DIR}/contextspindle"
        chmod +x "${INSTALL_DIR}/contextspindle"
    else
        echo -e "Please install Rust/Cargo (https://rustup.rs) to compile ContextSpindle on ${OS} ${ARCH}."
        exit 1
    fi
fi

# Ensure ~/.cargo/bin is in PATH
if [[ ":$PATH:" != *":${INSTALL_DIR}:"* ]]; then
    echo -e "-> Adding ${INSTALL_DIR} to your shell PATH..."
    SHELL_PROFILE="${HOME}/.bashrc"
    if [ -n "${ZSH_VERSION}" ] || [ -f "${HOME}/.zshrc" ]; then
        SHELL_PROFILE="${HOME}/.zshrc"
    fi
    echo 'export PATH="${HOME}/.cargo/bin:${PATH}"' >> "${SHELL_PROFILE}"
    export PATH="${HOME}/.cargo/bin:${PATH}"
fi

echo -e "\n${BOLD}${GREEN}ContextSpindle successfully installed!${RESET}"
"${INSTALL_DIR}/contextspindle" version

echo -e "\n${BOLD}Quick Start in 60 Seconds:${RESET}"
echo -e "  1. Initialize in your code repository:"
echo -e "     ${BLUE}cd my-project && contextspindle init${RESET}"
echo -e "  2. Remember an architecture rule or constraint:"
echo -e "     ${BLUE}contextspindle remember \"Database max_connections=50 idle_timeout=10s\"${RESET}"
echo -e "  3. Retrieve relevant constraints:"
echo -e "     ${BLUE}contextspindle recall \"database connection timeout\"${RESET}"
echo -e "  4. Connect Cursor / Claude Code IDE via Model Context Protocol (MCP):"
echo -e "     Add to your IDE MCP settings: ${GREEN}{\"command\": \"contextspindle\", \"args\": [\"mcp\"]}${RESET}"
echo -e "  5. Inspect the local memory state:"
echo -e "     ${BLUE}contextspindle stats${RESET}"
echo -e "\n${BOLD}Official Documentation:${RESET} docs/DEVELOPER_QUICKSTART.md"
echo -e "${BOLD}${BLUE}========================================================================${RESET}"
