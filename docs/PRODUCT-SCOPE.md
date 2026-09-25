# ContextSpindle product definition

ContextSpindle exists to keep an AI agent aligned with its task goals across long context windows, compaction, session restarts, unrelated intervening work, and multi-year gaps. On return, the agent should quickly know what task to do, why, what is already decided, and the next safe action, without reloading the whole conversation.

## Required capabilities

1. **Durable task ledger:** Stable task IDs; goal and completion criteria; status and owner; parent/child and dependency links; decisions, evidence references, blockers, and next action. State changes must be recoverable and attributable. A bounded, evicting cache cannot be the sole copy.
2. **Task-line continuity:** Switching to another task must not overwrite the suspended task. Resuming a task must recover its authoritative latest state, including open obligations and unresolved decisions.
3. **Task-aware context assembly:** Start from the task ledger, then retrieve only relevant constraints, decisions, and evidence. Enforce an explicit token budget and show provenance and omissions; summaries are aids, not authoritative state.
4. **Long-horizon reliability:** Define backups, migration, integrity checks, and recovery tests. A claim that old tasks remain available requires storage durability tests, not only retrieval benchmarks.
5. **Cross-agent interface:** Different agents must be able to read and update the same task model without relying on one model's private chat history.

## Scope boundary and current status

DiffHound, PR regression review, and GitHub Action review are not ContextSpindle product features. Historical research and benchmark artifacts remain as provenance, not as the current roadmap.

The current CLI/MCP implementation offers an append-only, versioned task ledger with compact deltas and periodic checkpoints; optimistic updates; compact inbox/search, history, verification, backup and restore; and budgeted context containing required task state plus selected decisions, evidence, related tasks, notes, and bounded-memory hints. Blockers are explicit; completion requires criteria, a cleared blocker, and finished dependencies; dependency cycles are rejected. Context fields are rendered on one line so stored line breaks cannot impersonate status fields. The retrieval cache remains lossy by design; a damaged cache must not hide a readable task ledger. The context budget is a conservative UTF-8 byte ceiling, not an exact model tokenizer. Off-device backup scheduling, independent security review, and long-duration field validation are still operational responsibilities; multi-year availability cannot be guaranteed by code alone.

Each version records a caller-declared actor (`CONTEXTSPINDLE_ACTOR`, otherwise a local process label). This is provenance for coordination, not authentication or authorization; deployment must protect the workspace and backups from untrusted writers.
