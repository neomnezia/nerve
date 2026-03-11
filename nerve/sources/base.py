"""Abstract base class for all data sources."""

from __future__ import annotations

import abc

from nerve.sources.models import FetchResult, SourceRecord


class Source(abc.ABC):
    """Abstract base for all data sources.

    Each source implements fetch() which returns records since a cursor.
    The cursor is an opaque string — each source defines its own semantics
    (message ID, timestamp, page token, etc.).
    """

    source_name: str = ""

    @abc.abstractmethod
    async def fetch(self, cursor: str | None, limit: int = 100) -> FetchResult:
        """Fetch new records since cursor.

        Args:
            cursor: Opaque cursor from the previous fetch. None on first run.
            limit: Maximum number of records to return.

        Returns:
            FetchResult with records, next_cursor, and has_more flag.
        """
        ...

    async def preprocess(self, records: list[SourceRecord]) -> list[SourceRecord]:
        """Source-specific preprocessing of fetched records.

        Called by SourceRunner after fetch() and before processing.
        Override to add source-specific content cleanup (e.g., stripping
        email boilerplate, normalizing markdown, etc.).

        Default: no-op (returns records unchanged).
        """
        return records

    async def close(self) -> None:
        """Optional cleanup — e.g. disconnect clients."""
        pass
