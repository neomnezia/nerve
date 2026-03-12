# TOOLS.md — Local Notes

Skills define *how* tools work. This file is for *your* specifics — the stuff that's unique to your environment and task.

## What Goes Here

Things like:
- API endpoints and base URLs
- Repository paths and branch conventions
- CI/CD system URLs and access patterns
- Database connection details (references, not passwords)
- CLI tool quirks you've discovered
- Host addresses and SSH aliases

## Examples

```markdown
### Repositories
- main-repo → /home/user/workspace/project, branch convention: feature/*
- ci-configs → separate repo, changes need manual deploy

### APIs
- CI database → https://ci.example.com/api, requires auth header
- Monitoring → Grafana at https://grafana.internal, dashboard ID: abc123

### CLI Quirks
- `gh pr list` returns max 30 by default — use --limit for more
- Build command requires NODE_ENV=production or tests fail silently
```

## Why Separate?

Skills are shared across workers. Your environment is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure details.

---

Add whatever helps you do your job. This is your cheat sheet.
