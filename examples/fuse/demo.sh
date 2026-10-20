#!/usr/bin/env bash
# 5-minute, offline reproduction of the compact fuse round-trip. No API key needed.
# Feeds the exact hook payloads Claude Code documents for PreCompact and
# SessionStart(source=compact) to the CLI, using the bundled synthetic transcript.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cargo build --quiet --release --manifest-path "$ROOT/Cargo.toml" --bin contextspindle
BIN="$ROOT/target/release/contextspindle"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "== 1. preview the hook config (nothing written)"
"$BIN" fuse setup --settings "$WORK/settings.json" | head -20

echo "== 2. PreCompact fires: save"
printf '{"session_id":"demo","transcript_path":"%s","cwd":"%s","hook_event_name":"PreCompact","trigger":"auto","custom_instructions":null}' \
  "$ROOT/examples/fuse/session.jsonl" "$WORK" | "$BIN" fuse save

echo "== 3. SessionStart(compact) fires: restore -> additionalContext JSON"
printf '{"session_id":"demo","cwd":"%s","hook_event_name":"SessionStart","source":"compact"}' "$WORK" \
  | "$BIN" fuse restore | python3 -c 'import json,sys; c=json.load(sys.stdin)["hookSpecificOutput"]["additionalContext"]; print(c); print(f"[{len(c.encode())} bytes]")'

echo "== 4. probe check"
"$BIN" fuse demo | tail -1
