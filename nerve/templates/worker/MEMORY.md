# MEMORY.md — HOT Memory

## How to Use This File

**This is HOT memory — your L1 cache.** It gets loaded into the system prompt every session, so every byte here costs tokens on every turn. Only store things that are:
- **Frequently accessed** — context you need in most sessions
- **Currently relevant** — active investigations, recent patterns, ongoing blockers
- **Hard to recall** — things `memory_recall` would struggle to find quickly

**What does NOT belong here:**
- Stable historical facts → `memorize` to memU
- Resolved items → remove (already in memU from when they were active)
- Rarely referenced details → memU

**Every entry must have a `[added YYYY-MM-DD]` tag.** This is how maintenance knows what's fresh and what's a candidate for eviction. Entries older than ~2 weeks that haven't been accessed should be moved to memU and removed from here.

---

## Task Context
<!-- Active task state, current blockers, in-progress work -->

## Known Patterns
<!-- Recurring issues, flaky tests, common failure modes you see regularly -->

## Operational Lessons
<!-- Hard-won knowledge that affects how you approach work -->
