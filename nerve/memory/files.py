"""Watch and serve memory files for web UI editing.

Uses watchfiles for file change detection and notifies connected clients.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from nerve.agent.streaming import broadcaster

logger = logging.getLogger(__name__)


class FileWatcher:
    """Watches workspace files for changes and notifies web clients."""

    def __init__(self, workspace: Path, on_change: Any = None):
        self.workspace = workspace
        self._running = False
        self._task: asyncio.Task | None = None
        self._on_change = on_change  # async callable(path: str) for .md file changes

    async def start(self) -> None:
        """Start watching for file changes."""
        self._running = True
        self._task = asyncio.create_task(self._watch_loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()

    async def _watch_loop(self) -> None:
        """Watch for file changes using watchfiles."""
        try:
            from watchfiles import awatch

            async for changes in awatch(str(self.workspace)):
                if not self._running:
                    break

                for change_type, path in changes:
                    rel_path = Path(path).relative_to(self.workspace)
                    await broadcaster.broadcast("_file_changes", {
                        "type": "file_changed",
                        "path": str(rel_path),
                        "change": str(change_type),
                    })
                    # Trigger re-indexing for .md files
                    if self._on_change and path.endswith(".md"):
                        asyncio.create_task(self._on_change(path))
        except ImportError:
            logger.info("watchfiles not installed — file watching disabled")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("File watcher error: %s", e)
