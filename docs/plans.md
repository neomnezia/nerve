# Proactive Task Planning

## Overview

Nerve includes a proactive planner that autonomously picks open tasks, explores the codebase, and proposes implementation plans for human review. Plans are never executed automatically — they go through an approval workflow.

## How It Works

```
Cron (every 4h) → persistent "task-planner" job
  → agent browses tasks, checks memory, picks one worth planning
  → explores codebase with Read, Glob, Grep, Bash, etc.
  → calls plan_propose(task_id, content) to store the proposal
  → plan appears in /plans UI for review

User reviews in /plans UI
  → approve → spawns implementation session (visible in Chat)
  → decline → marks plan declined
  → request revision → sends feedback to same persistent planner session
```

## Agent Tools

| Tool | Description |
|------|-------------|
| `plan_propose` | Propose an implementation plan for a task. Stored for async human review. |
| `plan_list` | List existing plans. Used to check which tasks already have pending plans. |

### `plan_propose(task_id, content)`

- Validates the task exists
- Checks no pending/implementing plan already exists → returns error if duplicate
- Auto-increments version if previous plans exist for the same task
- Supersedes any prior pending plan for the same task
- Returns `{ plan_id, task_id, version }`

### `plan_list(status?)`

- Default: returns pending + implementing plans
- Supports filtering: `pending`, `approved`, `declined`, `implementing`, `superseded`

## Plan Statuses

| Status | Meaning |
|--------|---------|
| `pending` | Awaiting human review |
| `approved` | Approved (briefly, before implementation starts) |
| `implementing` | Implementation session is running |
| `declined` | Rejected by user |
| `superseded` | Replaced by a newer version |

## Cron Job

Defined in `~/.nerve/cron/jobs.yaml` as `task-planner`:

- **Schedule:** Every 4 hours (`0 */4 * * *`)
- **Session mode:** Persistent (keeps context for revisions)
- **Context rotation:** Weekly (168 hours)
- **Model:** claude-opus-4-6

The planner is a standard persistent cron job — no special service or engine code needed.

## Revision Flow

When the user requests a revision:

1. User writes feedback in the plan detail page
2. API sends feedback as a new message to the persistent `cron:task-planner` session
3. The agent sees its prior planning context + the feedback
4. Agent calls `plan_propose` with the revised plan
5. Previous plan is automatically superseded

This works because the planner uses a **persistent session** — the agent retains conversation history across triggers and revision requests.

## Approval → Auto-Implementation

When a plan is approved:

1. Plan status → `implementing`
2. A new chat session is created (`impl-{uuid}`) with full tool access
3. The session receives the task content + approved plan as instructions
4. Session runs in the background, visible in the Chat page
5. Task status → `in_progress`

The user can monitor, stop, or interact with the implementation session from the Chat UI.

### Skill Proposals

Plans from the `skill-extractor` and `skill-reviser` cron jobs follow a different approval path. When approved:

1. Plan content is parsed as a full SKILL.md file (YAML frontmatter + body)
2. If the skill already exists → updated; otherwise → created
3. Plan status → `completed`; task status → `done`
4. No implementation session is spawned — the plan *is* the deliverable

This is handled automatically by the plan approval handler based on the task's `source` field (`skill-extractor` or `skill-reviser`).

## Database

Plans are stored in the `plans` SQLite table (schema v12):

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT PK | Plan ID (`plan-{uuid}`) |
| `task_id` | TEXT | Linked task |
| `session_id` | TEXT | Planner session that created it |
| `impl_session_id` | TEXT | Implementation session (after approval) |
| `status` | TEXT | pending/approved/declined/superseded/implementing |
| `content` | TEXT | Plan markdown |
| `feedback` | TEXT | User revision feedback |
| `version` | INTEGER | Version number (increments on revision) |
| `parent_plan_id` | TEXT | Previous version's ID |
| `model` | TEXT | Model used to generate |

## Web UI

### Plan List (`/plans`)

- Status filter tabs: All, Pending, Approved, Implementing, Declined
- Cards show: task title, plan version, status badge, creation date
- Click → navigate to plan detail

### Plan Detail (`/plans/:planId`)

- Rendered markdown plan content
- Task link + implementation session link (when applicable)
- Action bar for pending plans:
  - **Approve & Implement** — spawns implementation session, redirects to Chat
  - **Decline** — marks plan as declined
  - **Request Revision** — quote-style feedback input, sends to planner session
- Previous feedback shown as blockquote

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/plans` | List plans (query: `status`, `task_id`) |
| GET | `/api/plans/:id` | Get plan detail |
| PATCH | `/api/plans/:id` | Update status/feedback |
| POST | `/api/plans/:id/approve` | Approve + spawn implementation |
| POST | `/api/plans/:id/revise` | Send revision feedback to planner |
| GET | `/api/tasks/:id/plans` | Plans for a specific task |
