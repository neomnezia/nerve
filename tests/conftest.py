"""Shared test fixtures for Nerve tests."""

import asyncio
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

from nerve.db import Database


@pytest.fixture(scope="session")
def event_loop():
    """Use a single event loop for all tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db(tmp_path):
    """Create a fresh in-memory-like database for each test."""
    db_path = tmp_path / "test.db"
    database = Database(db_path)
    await database.connect()
    yield database
    await database.close()
