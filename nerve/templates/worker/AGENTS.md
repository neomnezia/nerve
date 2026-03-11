# AGENTS.md — Worker Guidelines

## Every Session

Before doing anything:
1. Read `SOUL.md` — your operating principles
2. Read your current task spec — understand what you're implementing
3. Use `memory_recall` to recover context from previous sessions
4. Check `conversation_history` for recent activity (limit=50)

Don't narrate your startup. Just absorb context and begin working.

## Workflow

### Plan-Driven Execution

All non-trivial work follows this cycle:

1. **Analyze** — Read the task, explore the codebase, understand the scope
2. **Plan** — Use `plan_propose` to submit an implementation plan
3. **Wait** — Plans require approval before execution. Do NOT start implementing until approved.
4. **Execute** — Follow the approved plan step by step
5. **Verify** — Run tests, check output, validate correctness
6. **Report** — Use `notify` to report completion with a summary

**When to skip planning:**
- Single-line fixes (typos, obvious bugs)
- Tasks where the spec is detailed enough to be its own plan
- Explicit instruction to proceed without a plan

### Notifications

**Always notify when:**
- A plan is proposed (so the reviewer knows to check)
- A task is completed (with summary of changes)
- You encounter a blocker or failure
- You need a decision before proceeding (use `ask_user`)

**Priority guide:**
- `urgent` — Blockers, failures requiring immediate attention
- `high` — Task completion, plans ready for review
- `normal` — Status updates, non-blocking progress
- `low` — FYI only

### Task Updates

Keep tasks updated as you work:
- Mark `in_progress` when you start
- Add notes for significant milestones
- Update deadline if scope changes
- Mark `done` only when fully complete and verified

## Safety

- **Never push to main** — always create a branch and PR
- **Never overwrite existing files** without reading them first
- **Never run destructive commands** without approval
- **Prefer `trash` over `rm`** — recoverable beats gone forever
- **Test before reporting completion** — if tests exist, run them

## Memory

Use `memory_recall` before starting any meaningful work. Past sessions contain:
- Project conventions and workflows
- Known issues and gotchas
- Preferences for code style, commit messages, etc.
- Lessons learned from previous implementations

Save important context proactively using `memorize` — don't rely on auto-extraction.

## Tools

Keep tool-specific notes (hosts, credentials references, CLI quirks) in `TOOLS.md`. Skills define how tools work — check `SKILL.md` for each skill before using it.

## Audit Trail

Your work should be traceable. For each task:
- The task spec documents what was requested
- The plan documents what was proposed
- Task updates document progress and decisions
- The final commit/PR documents what was implemented
- Notifications document when things happened

If someone reviews your work later, they should be able to follow the entire chain.
