# MEMORY.md — HOT Memory

## How to Use This File

**This is HOT memory — your L1 cache.** It gets loaded into the system prompt every main session, so every byte here costs tokens on every turn. Only store things that are:
- **Frequently accessed** — context you need in most conversations
- **Currently relevant** — active projects, upcoming events, recent decisions
- **Hard to recall** — things `memory_recall` would struggle to find quickly

**What does NOT belong here:**
- Stable historical facts (employment start dates, home purchase details) -> `memorize` to memU
- Resolved items (completed migrations, past events) -> remove, already in memU
- Rarely referenced details (specific PR numbers, one-off fixes) -> memU

**Lifecycle of entries:**
1. New important fact -> add here with `[added YYYY-MM-DD]` date tag
2. Fact stays relevant -> keep it, update if context changes
3. Fact becomes stale or rarely needed -> move to memU via `memorize`, then remove from here
4. During memory maintenance: review dates, evict anything older than ~2 weeks that hasn't been accessed

**Every entry must have a `[added YYYY-MM-DD]` tag** (or `[stable]` for permanent entries like contact info). This is how the memory maintenance cron knows what's fresh and what's a candidate for eviction.

---

## Your Human
- **Name:** *(fill in)* `[stable]`
- **Timezone:** *(fill in)* `[stable]`

## Active Context

*(Add current projects, decisions, and deadlines here as they come up)*

## Operational Lessons

*(Hard-won lessons that affect how you work — document mistakes so future-you doesn't repeat them)*
