"""Tests for TelegramChannel.send length policy.

Covers the inline / preview-plus-document split for outbound responses:
- Short text → single inline message, no document.
- Boundary text (= MAX_MSG_LEN) → single inline message, no document.
- Long text (> MAX_MSG_LEN) → inline preview + document attachment.
- Filename construction (with and without session_id).
- Document upload failure tolerated; preview still delivered.
- format_response is identity (length policy lives in send()).
"""

from __future__ import annotations

import re
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock

import pytest

from nerve.channels.base import OutboundMessage
from nerve.channels.telegram import (
    FLOODWAIT_GAP_S,
    MAX_MSG_LEN,
    PREVIEW_FOOTER,
    TelegramChannel,
)
from nerve.config import NerveConfig


@pytest.fixture(autouse=True)
def _patch_floodwait_sleep(monkeypatch):
    """Replace the floodwait gap sleep with a no-op so tests don't actually wait."""
    import nerve.channels.telegram as tg_mod

    async def _fast_sleep(_secs):  # noqa: D401
        return None

    monkeypatch.setattr(tg_mod.asyncio, "sleep", _fast_sleep)
    yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_telegram_channel() -> TelegramChannel:
    """Build a TelegramChannel with a mocked PTB Application."""
    cfg = NerveConfig()
    cfg.telegram.bot_token = "TEST:TOKEN"
    cfg.telegram.allowed_users = [1]
    ch = TelegramChannel(cfg, router=MagicMock())
    mock_app = MagicMock()
    mock_app.bot = MagicMock()
    sent_msg = MagicMock()
    sent_msg.message_id = 42
    mock_app.bot.send_message = AsyncMock(return_value=sent_msg)
    mock_app.bot.send_document = AsyncMock()
    ch._app = mock_app
    return ch


def _outbound(text: str, target: str = "12345", session_id: str = "abc123de") -> OutboundMessage:
    return OutboundMessage(target=target, text=text, session_id=session_id)


# ---------------------------------------------------------------------------
# Length policy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTelegramSendLengthPolicy:
    async def test_send_short_text_single_message(self):
        """Short text: 1 send_message call, 0 send_document calls."""
        ch = _make_telegram_channel()
        await ch.send(_outbound("x" * 100))
        ch._app.bot.send_message.assert_awaited_once()
        ch._app.bot.send_document.assert_not_awaited()

    async def test_send_at_boundary_4096(self):
        """Boundary text (= MAX_MSG_LEN): inline only, no document."""
        ch = _make_telegram_channel()
        await ch.send(_outbound("x" * MAX_MSG_LEN))
        ch._app.bot.send_message.assert_awaited_once()
        ch._app.bot.send_document.assert_not_awaited()

    async def test_send_one_over_4097_preview_plus_file(self):
        """1 char over boundary: preview + file attachment."""
        ch = _make_telegram_channel()
        text = "y" * (MAX_MSG_LEN + 1)
        await ch.send(_outbound(text))

        # Inline preview was sent
        ch._app.bot.send_message.assert_awaited_once()
        sent_text = ch._app.bot.send_message.await_args.kwargs["text"]
        assert sent_text.endswith(PREVIEW_FOOTER)
        assert len(sent_text) <= MAX_MSG_LEN

        # Document was sent with the full original text
        ch._app.bot.send_document.assert_awaited_once()
        doc_arg = ch._app.bot.send_document.await_args.kwargs["document"]
        assert isinstance(doc_arg, BytesIO)
        assert doc_arg.getvalue() == text.encode("utf-8")
        assert len(doc_arg.getvalue()) == MAX_MSG_LEN + 1

    async def test_send_long_8000_full_in_file(self):
        """8000-char response: file holds full original; preview ≤ MAX_MSG_LEN."""
        ch = _make_telegram_channel()
        text = "z" * 8000
        await ch.send(_outbound(text))

        # Preview is bounded by MAX_MSG_LEN
        sent_text = ch._app.bot.send_message.await_args.kwargs["text"]
        assert len(sent_text) <= MAX_MSG_LEN

        # Document holds the full unmodified original
        doc_arg = ch._app.bot.send_document.await_args.kwargs["document"]
        assert doc_arg.getvalue() == text.encode("utf-8")
        assert len(doc_arg.getvalue()) == 8000


# ---------------------------------------------------------------------------
# Filename construction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTelegramFilename:
    async def test_filename_includes_session_id(self):
        """Filename matches response-<session_id>-<YYYYmmdd-HHMMSS>.md."""
        ch = _make_telegram_channel()
        await ch.send(_outbound("a" * (MAX_MSG_LEN + 100), session_id="abc123de"))
        kwargs = ch._app.bot.send_document.await_args.kwargs
        assert re.fullmatch(r"response-abc123de-\d{8}-\d{6}\.md", kwargs["filename"])

    async def test_filename_falls_back_when_session_empty(self):
        """Empty session_id → filename starts with response-unknown-."""
        ch = _make_telegram_channel()
        await ch.send(_outbound("b" * (MAX_MSG_LEN + 100), session_id=""))
        kwargs = ch._app.bot.send_document.await_args.kwargs
        assert kwargs["filename"].startswith("response-unknown-")
        assert kwargs["filename"].endswith(".md")

    async def test_filename_sanitizes_unsafe_chars(self):
        """Path separators / spaces / control chars in session_id are stripped."""
        ch = _make_telegram_channel()
        await ch.send(_outbound(
            "e" * (MAX_MSG_LEN + 50), session_id="ab/cd\\ef gh\n12",
        ))
        kwargs = ch._app.bot.send_document.await_args.kwargs
        # Result keeps only [A-Za-z0-9_-]; "abcdefgh12" survives.
        assert re.fullmatch(
            r"response-abcdefgh12-\d{8}-\d{6}\.md", kwargs["filename"],
        )

    async def test_filename_truncates_long_session_id(self):
        """Very long session_id is capped at 16 chars in the slug."""
        ch = _make_telegram_channel()
        long_sid = "a" * 100
        await ch.send(_outbound("f" * (MAX_MSG_LEN + 50), session_id=long_sid))
        kwargs = ch._app.bot.send_document.await_args.kwargs
        # Slug is exactly 16 'a's.
        assert re.fullmatch(
            r"response-a{16}-\d{8}-\d{6}\.md", kwargs["filename"],
        )

    async def test_filename_only_invalid_chars_falls_back(self):
        """All-invalid session_id ('///\\\\') sanitizes to empty → 'unknown'."""
        ch = _make_telegram_channel()
        await ch.send(_outbound("g" * (MAX_MSG_LEN + 50), session_id="///\\\\"))
        kwargs = ch._app.bot.send_document.await_args.kwargs
        assert kwargs["filename"].startswith("response-unknown-")


# ---------------------------------------------------------------------------
# Failure modes & format_response identity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTelegramSendFailureModes:
    async def test_document_failure_preserves_preview(self, caplog):
        """If send_document raises, preview was already delivered; no exception escapes."""
        import logging

        ch = _make_telegram_channel()
        ch._app.bot.send_document.side_effect = RuntimeError("network exploded")
        text = "c" * (MAX_MSG_LEN + 50)

        with caplog.at_level(logging.WARNING, logger="nerve.channels.telegram"):
            await ch.send(_outbound(text))  # must not raise

        # Preview was sent successfully
        ch._app.bot.send_message.assert_awaited_once()
        # Document attempt was made and failed
        ch._app.bot.send_document.assert_awaited_once()
        # Warning was logged
        assert any(
            "response document upload failed" in rec.message
            for rec in caplog.records
        )

    async def test_preview_footer_is_paperclip_only(self):
        """Preview ends with exactly PREVIEW_FOOTER ('\\n\\n📎'), nothing more."""
        ch = _make_telegram_channel()
        await ch.send(_outbound("d" * (MAX_MSG_LEN + 200)))
        sent_text = ch._app.bot.send_message.await_args.kwargs["text"]
        assert sent_text.endswith("\n\n📎")
        # No trailing content past the footer
        assert sent_text.count("📎") == 1


@pytest.mark.asyncio
class TestTelegramFloodwaitGap:
    async def test_floodwait_gap_at_least_one_second(self):
        """Gap between preview and document must clear Telegram's 1 msg/sec/chat limit."""
        assert FLOODWAIT_GAP_S >= 1.0

    async def test_floodwait_gap_is_awaited_between_sends(self, monkeypatch):
        """send() awaits asyncio.sleep(FLOODWAIT_GAP_S) before send_document."""
        import nerve.channels.telegram as tg_mod

        observed: list[float] = []

        async def _spy_sleep(secs):
            observed.append(secs)

        monkeypatch.setattr(tg_mod.asyncio, "sleep", _spy_sleep)

        ch = _make_telegram_channel()
        await ch.send(_outbound("h" * (MAX_MSG_LEN + 100)))

        assert FLOODWAIT_GAP_S in observed


def test_format_response_identity():
    """format_response no longer truncates — length policy lives in send()."""
    cfg = NerveConfig()
    cfg.telegram.bot_token = "TEST:TOKEN"
    cfg.telegram.allowed_users = [1]
    ch = TelegramChannel(cfg, router=MagicMock())
    long_text = "x" * 10000
    assert ch.format_response(long_text) == long_text
    assert ch.format_response("short") == "short"
