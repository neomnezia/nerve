"""V21: Enrich session_usage with model, SDK cost, durations, num_turns, and server tool use."""

from __future__ import annotations

import logging

import aiosqlite

logger = logging.getLogger(__name__)


async def up(db: aiosqlite.Connection) -> None:
    await db.executescript("""
        ALTER TABLE session_usage ADD COLUMN model TEXT;
        ALTER TABLE session_usage ADD COLUMN cost_usd REAL;
        ALTER TABLE session_usage ADD COLUMN duration_ms INTEGER;
        ALTER TABLE session_usage ADD COLUMN duration_api_ms INTEGER;
        ALTER TABLE session_usage ADD COLUMN num_turns INTEGER DEFAULT 1;
        ALTER TABLE session_usage ADD COLUMN web_search_requests INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE session_usage ADD COLUMN web_fetch_requests INTEGER NOT NULL DEFAULT 0;
    """)
    logger.info("v021: enriched session_usage with model, cost, durations, num_turns, server_tool_use")
