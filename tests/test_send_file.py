"""Tests for the send_file dispatch path.

Covers:
- ChannelRouter.send_file fan-out: missing context, missing capability,
  successful dispatch.
- TelegramChannel.send_file: missing file, oversized file, success path.
- _send_file_impl in agent.tools: workspace scope, engine-unavailable
  fallback, native-delivered success message, fallback message when
  the channel cannot deliver.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nerve.channels.base import BaseChannel, ChannelCapability
from nerve.channels.router import ChannelRouter
from nerve.channels.telegram import TelegramChannel
from nerve.config import NerveConfig


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _StubChannel(BaseChannel):
    """Minimal channel stub with configurable capabilities + send_file return."""

    def __init__(
        self,
        name: str = "stub",
        caps: ChannelCapability = ChannelCapability.SEND_TEXT,
        send_file_returns: bool = True,
    ):
        self._name = name
        self._caps = caps
        self._send_file_returns = send_file_returns
        self.send_file_calls: list[tuple[str, str]] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def capabilities(self) -> ChannelCapability:
        return self._caps

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def send(self, message) -> None:
        pass

    async def send_file(self, target: str, file_path: str) -> bool:  # type: ignore[override]
        self.send_file_calls.append((target, file_path))
        return self._send_file_returns


# ---------------------------------------------------------------------------
# ChannelRouter.send_file
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRouterSendFile:
    async def test_no_message_context_returns_false(self):
        engine = MagicMock()
        router = ChannelRouter(engine)
        assert await router.send_file("missing-session", "/tmp/x") is False

    async def test_channel_without_capability_returns_false(self, tmp_path):
        engine = MagicMock()
        router = ChannelRouter(engine)
        ch = _StubChannel(caps=ChannelCapability.SEND_TEXT)
        router._channels["stub"] = ch
        router._message_context["sess-1"] = {
            "channel_name": "stub",
            "target": "12345",
            "message_id": 1,
        }
        f = tmp_path / "a.txt"
        f.write_text("hi")
        assert await router.send_file("sess-1", str(f)) is False
        assert ch.send_file_calls == []

    async def test_dispatches_when_capability_present(self, tmp_path):
        engine = MagicMock()
        router = ChannelRouter(engine)
        ch = _StubChannel(
            caps=ChannelCapability.SEND_TEXT | ChannelCapability.SEND_FILES,
            send_file_returns=True,
        )
        router._channels["stub"] = ch
        router._message_context["sess-1"] = {
            "channel_name": "stub",
            "target": "12345",
            "message_id": 1,
        }
        f = tmp_path / "a.txt"
        f.write_text("hi")
        assert await router.send_file("sess-1", str(f)) is True
        assert ch.send_file_calls == [("12345", str(f))]

    async def test_propagates_channel_failure(self, tmp_path):
        engine = MagicMock()
        router = ChannelRouter(engine)
        ch = _StubChannel(
            caps=ChannelCapability.SEND_TEXT | ChannelCapability.SEND_FILES,
            send_file_returns=False,
        )
        router._channels["stub"] = ch
        router._message_context["sess-1"] = {
            "channel_name": "stub",
            "target": "12345",
            "message_id": 1,
        }
        f = tmp_path / "a.txt"
        f.write_text("hi")
        assert await router.send_file("sess-1", str(f)) is False


# ---------------------------------------------------------------------------
# TelegramChannel.send_file
# ---------------------------------------------------------------------------


def _make_telegram_channel() -> TelegramChannel:
    """Build a TelegramChannel with a minimal config and a mocked _app."""
    cfg = NerveConfig()
    cfg.telegram.bot_token = "TEST:TOKEN"
    cfg.telegram.allowed_users = [1]
    ch = TelegramChannel(cfg, router=MagicMock())
    # Bypass real PTB Application — only need send_document to exist.
    mock_app = MagicMock()
    mock_app.bot = MagicMock()
    mock_app.bot.send_document = AsyncMock()
    ch._app = mock_app
    return ch


@pytest.mark.asyncio
class TestTelegramSendFile:
    async def test_missing_file_returns_false(self, tmp_path):
        ch = _make_telegram_channel()
        bogus = tmp_path / "does-not-exist.txt"
        assert await ch.send_file("12345", str(bogus)) is False
        ch._app.bot.send_document.assert_not_awaited()

    async def test_directory_returns_false(self, tmp_path):
        ch = _make_telegram_channel()
        assert await ch.send_file("12345", str(tmp_path)) is False
        ch._app.bot.send_document.assert_not_awaited()

    async def test_oversized_file_returns_false(self, tmp_path, monkeypatch):
        ch = _make_telegram_channel()
        f = tmp_path / "big.bin"
        f.write_bytes(b"x")
        # Pretend the file is >50 MiB without actually writing 50 MiB.
        original_stat = Path.stat

        def fake_stat(self, *args, **kwargs):
            real = original_stat(self, *args, **kwargs)
            if str(self) == str(f.resolve()):
                class _S:
                    st_size = 60 * 1024 * 1024
                    st_mode = real.st_mode
                return _S()
            return real

        monkeypatch.setattr(Path, "stat", fake_stat)
        assert await ch.send_file("12345", str(f)) is False
        ch._app.bot.send_document.assert_not_awaited()

    async def test_success_path_calls_send_document(self, tmp_path):
        ch = _make_telegram_channel()
        f = tmp_path / "note.md"
        f.write_text("hello")
        ok = await ch.send_file("12345", str(f))
        assert ok is True
        ch._app.bot.send_document.assert_awaited_once()
        kwargs = ch._app.bot.send_document.await_args.kwargs
        assert kwargs["chat_id"] == 12345
        assert kwargs["filename"] == "note.md"

    async def test_send_document_failure_returns_false(self, tmp_path):
        ch = _make_telegram_channel()
        ch._app.bot.send_document.side_effect = RuntimeError("boom")
        f = tmp_path / "note.md"
        f.write_text("hello")
        assert await ch.send_file("12345", str(f)) is False

    async def test_no_app_returns_false(self, tmp_path):
        ch = _make_telegram_channel()
        ch._app = None
        f = tmp_path / "note.md"
        f.write_text("hi")
        assert await ch.send_file("12345", str(f)) is False

    async def test_capability_includes_send_files(self):
        ch = _make_telegram_channel()
        assert ChannelCapability.SEND_FILES in ch.capabilities


# ---------------------------------------------------------------------------
# tools._send_file_impl
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSendFileImpl:
    async def test_missing_path_returns_error(self):
        from nerve.agent import tools

        result = await tools._send_file_impl({}, "sess")
        assert "file_path is required" in result["content"][0]["text"]

    async def test_file_not_found_returns_error(self, tmp_path):
        from nerve.agent import tools

        bogus = tmp_path / "missing"
        result = await tools._send_file_impl({"file_path": str(bogus)}, "sess")
        assert "not found" in result["content"][0]["text"]

    async def test_outside_workspace_blocked(self, tmp_path):
        from nerve.agent import tools

        workspace = tmp_path / "ws"
        workspace.mkdir()
        outside = tmp_path / "secret.txt"
        outside.write_text("nope")

        with patch.object(tools, "_workspace", workspace), \
             patch.object(tools, "_engine", MagicMock()):
            result = await tools._send_file_impl(
                {"file_path": str(outside)}, "sess"
            )
        assert "must be within the workspace" in result["content"][0]["text"]

    async def test_engine_unavailable_falls_back(self, tmp_path):
        from nerve.agent import tools

        workspace = tmp_path / "ws"
        workspace.mkdir()
        f = workspace / "a.txt"
        f.write_text("hi")

        with patch.object(tools, "_workspace", workspace), \
             patch.object(tools, "_engine", None):
            result = await tools._send_file_impl(
                {"file_path": str(f)}, "sess"
            )
        text = result["content"][0]["text"]
        assert "File ready: a.txt" in text
        assert "open the web panel" in text

    async def test_native_delivery_success_message(self, tmp_path):
        from nerve.agent import tools

        workspace = tmp_path / "ws"
        workspace.mkdir()
        f = workspace / "a.txt"
        f.write_text("hi")

        engine = MagicMock()
        engine.router = MagicMock()
        engine.router.send_file = AsyncMock(return_value=True)

        with patch.object(tools, "_workspace", workspace), \
             patch.object(tools, "_engine", engine):
            result = await tools._send_file_impl(
                {"file_path": str(f)}, "sess-1"
            )

        engine.router.send_file.assert_awaited_once_with(
            "sess-1", str(f.resolve())
        )
        text = result["content"][0]["text"]
        assert text.startswith("Sent file: a.txt")

    async def test_dispatch_failure_returns_fallback(self, tmp_path):
        from nerve.agent import tools

        workspace = tmp_path / "ws"
        workspace.mkdir()
        f = workspace / "a.txt"
        f.write_text("hi")

        engine = MagicMock()
        engine.router = MagicMock()
        engine.router.send_file = AsyncMock(return_value=False)

        with patch.object(tools, "_workspace", workspace), \
             patch.object(tools, "_engine", engine):
            result = await tools._send_file_impl(
                {"file_path": str(f)}, "sess-1"
            )
        text = result["content"][0]["text"]
        assert "File ready: a.txt" in text
        assert "open the web panel" in text

    async def test_dispatch_exception_is_caught(self, tmp_path):
        from nerve.agent import tools

        workspace = tmp_path / "ws"
        workspace.mkdir()
        f = workspace / "a.txt"
        f.write_text("hi")

        engine = MagicMock()
        engine.router = MagicMock()
        engine.router.send_file = AsyncMock(side_effect=RuntimeError("boom"))

        with patch.object(tools, "_workspace", workspace), \
             patch.object(tools, "_engine", engine):
            result = await tools._send_file_impl(
                {"file_path": str(f)}, "sess-1"
            )
        text = result["content"][0]["text"]
        assert "File ready: a.txt" in text
        assert "open the web panel" in text
