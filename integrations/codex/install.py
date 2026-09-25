#!/usr/bin/env python3
"""Install the optional, user-scoped Codex integration from this checkout."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import tomllib


SKILL = "contextspindle-task-continuity"
START = "<!-- contextspindle-task-continuity:start -->"
END = "<!-- contextspindle-task-continuity:end -->"
READ_TOOLS = (
    "contextspindle_task_inbox",
    "contextspindle_task_search",
    "contextspindle_task_show",
    "contextspindle_task_context",
    "contextspindle_task_list",
    "contextspindle_task_history",
    "contextspindle_task_children",
    "contextspindle_task_verify",
)
RULE = f"""{START}
For substantive multi-step coding work, use the `{SKILL}` skill to find or create a matching durable task and verify a budgeted handoff before pausing or finishing. The current user request is authoritative; do not resume unrelated tasks or store secrets. Skip this for quick unrelated Q&A. The ledger is local, not automatic cloud memory.
{END}
"""


def run(*args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, env=env, text=True, capture_output=True, check=False)


def install_file(source: Path, destination: Path, mode: int) -> None:
    data = source.read_bytes()
    if destination.exists() and destination.read_bytes() != data:
        backup = destination.with_name(f"{destination.name}.backup-{time.time_ns()}")
        shutil.copy2(destination, backup)
        print(f"Preserved changed file: {backup}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    destination.chmod(mode)


def install_rule(path: Path) -> None:
    old = path.read_text() if path.exists() else ""
    if START in old or END in old:
        if old.count(START) != 1 or old.count(END) != 1 or old.index(START) > old.index(END):
            raise RuntimeError(f"Ambiguous ContextSpindle section in {path}; edit it manually")
        updated = old[: old.index(START)] + RULE.rstrip() + old[old.index(END) + len(END) :]
    else:
        updated = old.rstrip() + ("\n\n" if old.strip() else "") + RULE
    if updated != old:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(updated)


def register_mcp(codex_home: Path, wrapper: Path) -> None:
    env = dict(os.environ, CODEX_HOME=str(codex_home))
    get = run("codex", "mcp", "get", "contextspindle", env=env)
    if get.returncode == 0:
        if f"command: {wrapper}" not in get.stdout:
            raise RuntimeError("An existing contextspindle MCP points elsewhere; inspect it before changing it")
    else:
        add = run("codex", "mcp", "add", "contextspindle", "--", str(wrapper), "mcp", env=env)
        if add.returncode:
            raise RuntimeError(f"Codex MCP registration failed: {add.stderr.strip()}")

    config_path = codex_home / "config.toml"
    content = config_path.read_text()
    config = tomllib.loads(content)
    server = config.get("mcp_servers", {}).get("contextspindle", {})
    if server.get("command") != str(wrapper):
        raise RuntimeError("MCP registration did not persist the expected wrapper command")
    configured_tools = server.get("tools", {})
    additions = []
    for tool in READ_TOOLS:
        if tool not in configured_tools:
            additions.append(
                f'[mcp_servers.contextspindle.tools.{tool}]\napproval_mode = "approve"'
            )
    if additions:
        config_path.write_text(content.rstrip() + "\n\n" + "\n\n".join(additions) + "\n")
        tomllib.loads(config_path.read_text())


def main() -> int:
    if sys.version_info < (3, 11):
        raise RuntimeError("Python 3.11 or newer is required for TOML-safe installation")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", type=Path, default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")))
    parser.add_argument("--binary", type=Path, help="Use an already-built contextspindle binary instead of cargo install")
    parser.add_argument("--skip-mcp", action="store_true", help="Skip Codex MCP registration (for offline preparation)")
    args = parser.parse_args()

    codex_home = args.codex_home.expanduser().resolve()
    source_root = Path(__file__).resolve().parents[2]
    skill_source = Path(__file__).parent / SKILL
    skill_target = codex_home / "skills" / SKILL
    runtime = codex_home / "contextspindle-runtime"
    workspace = codex_home / "contextspindle-workspace"
    binary = runtime / "bin" / "contextspindle"
    wrapper = skill_target / "scripts" / "contextspindle"

    if not args.skip_mcp and shutil.which("codex") is None:
        raise RuntimeError("Codex CLI is required for automatic MCP registration")
    if not args.binary and shutil.which("cargo") is None:
        raise RuntimeError("Cargo is required to build the ContextSpindle binary")
    if args.binary and not args.binary.expanduser().resolve().is_file():
        raise RuntimeError(f"Binary does not exist: {args.binary}")
    codex_home.mkdir(parents=True, exist_ok=True)
    runtime.mkdir(mode=0o700, exist_ok=True)
    workspace.mkdir(mode=0o700, exist_ok=True)
    runtime.chmod(0o700)
    workspace.chmod(0o700)

    if args.binary:
        binary.parent.mkdir(parents=True, exist_ok=True)
        install_file(args.binary.expanduser().resolve(), binary, 0o700)
    else:
        build = run(
            "cargo", "install", "--path", str(source_root / "crates" / "continuum-cli"),
            "--root", str(runtime), "--locked", "--bin", "contextspindle",
            env=dict(os.environ),
        )
        if build.returncode:
            raise RuntimeError(f"Cargo install failed:\n{build.stderr[-3000:]}")
    initialized = run(str(binary), "init", str(workspace), env=dict(os.environ))
    if initialized.returncode:
        raise RuntimeError(f"Workspace initialization failed: {initialized.stderr.strip()}")

    install_file(skill_source / "SKILL.md", skill_target / "SKILL.md", 0o600)
    install_file(skill_source / "scripts" / "contextspindle", wrapper, 0o700)
    install_rule(codex_home / "AGENTS.md")
    if not args.skip_mcp:
        register_mcp(codex_home, wrapper)

    smoke = run(str(wrapper), "task", "verify", env=dict(os.environ, CODEX_HOME=str(codex_home)))
    if smoke.returncode:
        raise RuntimeError(f"Installed wrapper failed verification: {smoke.stderr.strip()}")
    print(f"Installed ContextSpindle Codex integration in {codex_home}")
    print(smoke.stdout.strip())
    if args.skip_mcp:
        print("MCP registration skipped; new sessions will not have ContextSpindle MCP tools yet")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(f"Installation failed: {error}", file=sys.stderr)
        raise SystemExit(1)
