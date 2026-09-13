# Agent protocol

The repository implements orchestration through Git branches/worktrees plus auditable artifacts. Native agents may be used for bounded work; each editing role works in an isolated worktree.

Required task fields: `task_id`, `owner`, `objective`, `dependencies`, `status`, `files`, `tests`, `benchmark`, `review`, `decision`.

Allowed statuses: `BACKLOG`, `READY`, `IN_PROGRESS`, `REVIEW`, `BENCHMARK`, `ADVERSARIAL`, `JUDGE`, `APPROVED`, `REJECTED`, `BLOCKED`.

Major architectural changes must use `.agent/proposals/RFC-XXXX.md` and include problem, proposal, mathematical formulation, impact, hypothesis, failure mode, benchmark plan, ablation plan, adversarial tests, and decision.
