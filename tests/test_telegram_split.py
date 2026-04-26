"""Unit tests for nerve.channels.telegram._smart_split."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from nerve.channels.base import OutboundMessage
from nerve.channels.telegram import (
    FILE_ATTACH_THRESHOLD,
    MAX_MSG_LEN,
    TelegramChannel,
    _smart_split,
)


def test_short_text_returns_single_chunk_unchanged():
    text = "hello world"
    assert _smart_split(text, limit=4096) == ["hello world"]


def test_text_at_exact_limit_is_single_chunk():
    text = "x" * 4096
    chunks = _smart_split(text, limit=4096)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_text_one_over_limit_splits_into_two():
    text = "x" * 4097
    chunks = _smart_split(text, limit=4096)
    assert len(chunks) == 2
    # No data lost
    assert sum(len(c) - len(_continuation_prefix(c)) for c in chunks) == 4097


def test_paragraph_boundary_used_when_possible():
    para_a = "a" * 2000
    para_b = "b" * 2000
    para_c = "c" * 2000
    text = f"{para_a}\n\n{para_b}\n\n{para_c}"
    chunks = _smart_split(text, limit=4096)
    # Two of three paragraphs fit in first chunk; third in second
    assert len(chunks) == 2
    # Each chunk respects the limit
    assert all(len(c) <= 4096 for c in chunks)
    # Joined data round-trips (modulo continuation markers and spacing)
    rebuilt = "\n\n".join(_strip_continuation_prefix(c) for c in chunks)
    assert para_a in rebuilt
    assert para_b in rebuilt
    assert para_c in rebuilt


def _continuation_prefix(chunk: str) -> str:
    """Helper for tests — extract `(N/M)\\n` prefix if present."""
    import re
    m = re.match(r"^\(\d+/\d+\)\n", chunk)
    return m.group(0) if m else ""


def _strip_continuation_prefix(chunk: str) -> str:
    return chunk[len(_continuation_prefix(chunk)):]


def test_oversized_paragraph_splits_on_lines():
    line = "x" * 1000
    para = "\n".join([line] * 6)  # 6 * 1000 + 5 = 6005 chars
    chunks = _smart_split(para, limit=4096)
    # First chunk: ~4 lines (4 * 1000 + 3 = 4003) fits under 4088 inner_limit
    assert len(chunks) >= 2
    assert all(len(c) <= 4096 for c in chunks)
    # No line is split mid-line
    for chunk in chunks:
        body = _strip_continuation_prefix(chunk)
        for produced_line in body.split("\n"):
            assert len(produced_line) == 1000 or produced_line == ""


def test_oversized_line_splits_on_sentences():
    sentence = "Lorem ipsum dolor sit amet. " * 200  # ~5600 chars, single line
    chunks = _smart_split(sentence, limit=4096)
    assert len(chunks) >= 2
    assert all(len(c) <= 4096 for c in chunks)
    # Each chunk body ends on a sentence terminator (or is the last chunk)
    for chunk in chunks[:-1]:
        body = _strip_continuation_prefix(chunk).rstrip()
        assert body.endswith((".", "!", "?"))


def test_single_word_longer_than_limit_hard_splits_with_warning(caplog):
    import logging
    monster = "x" * 10000
    with caplog.at_level(logging.WARNING, logger="nerve.channels.telegram"):
        chunks = _smart_split(monster, limit=4096)
    assert len(chunks) >= 3
    assert all(len(c) <= 4096 for c in chunks)
    assert any("hard split" in rec.message.lower() for rec in caplog.records)


def test_code_fence_split_closes_and_reopens():
    code_body = "line\n" * 1500  # ~7500 chars inside fence
    text = f"intro paragraph\n\n```python\n{code_body}```"
    chunks = _smart_split(text, limit=4096)
    assert len(chunks) >= 2
    # First chunk that opens a fence must close it before the boundary.
    for chunk in chunks:
        body = _strip_continuation_prefix(chunk)
        # Count of ``` markers must be even — fences balanced per chunk.
        assert body.count("```") % 2 == 0, f"unbalanced fence in chunk: {body[:80]!r}"


def test_code_fence_with_language_tag_reopens_with_same_tag():
    code_body = "x = 1\n" * 1000
    text = f"```python\n{code_body}```"
    chunks = _smart_split(text, limit=4096)
    if len(chunks) >= 2:
        second_body = _strip_continuation_prefix(chunks[1])
        # Continuation chunk must reopen the fence with the original language tag.
        assert second_body.startswith("```python\n"), (
            f"expected reopened ```python fence, got: {second_body[:80]!r}"
        )


def test_format_response_no_longer_truncates():
    """Regression: format_response must not silently drop the tail."""
    from nerve.channels.telegram import TelegramChannel
    from nerve.config import NerveConfig

    cfg = NerveConfig.__new__(NerveConfig)  # bypass __init__; we only need format_response
    channel = TelegramChannel.__new__(TelegramChannel)
    channel._config = cfg

    long_text = "a" * 10000
    out = channel.format_response(long_text)
    # No "(truncated)" suffix; full payload preserved.
    assert "(truncated)" not in out
    assert out == long_text


# --------------------------------------------------------------------------- #
#  V6 regression tests (PR #3 review fixes + file-attach routing)             #
# --------------------------------------------------------------------------- #


def test_chunks_under_limit_after_fence_balance_grows_them():
    """P1 (Codex): _balance_code_fences may prepend ```python and append ```,
    pushing a chunk over MAX_MSG_LEN. _enforce_chunk_limit must hard-cut the
    overflow before continuation markers are added.
    """
    # Construct a fenced block right at the boundary so fence prefix/suffix
    # additions force a re-split.
    code_body = "x" * 4000  # leaves <100 chars for fence + marker overhead
    text = f"```python\n{code_body}\n```\n\nmore text here that triggers split"
    chunks = _smart_split(text, limit=MAX_MSG_LEN)
    # Every produced chunk MUST fit Telegram's hard cap, even after fences
    # were rebalanced and continuation markers prepended.
    assert all(len(c) <= MAX_MSG_LEN for c in chunks), [len(c) for c in chunks]


def test_continuation_marker_overhead_handles_three_digit_counts():
    """P2 (Codex): the original code reserved 8 chars for "(99/99)\\n" but
    never enforced that ceiling. Build a payload that produces ≥100 chunks
    and verify every chunk still fits MAX_MSG_LEN once "(NNN/MMM)\\n" is
    prepended.
    """
    # Each line is ~3900 chars, packed via paragraph splitter into one chunk
    # apiece. 105 lines → 105 chunks → markers like "(105/105)\n" (10 chars).
    big_para = "z" * 3900
    text = "\n\n".join([big_para] * 105)
    chunks = _smart_split(text, limit=MAX_MSG_LEN)
    assert len(chunks) >= 100, f"expected ≥100 chunks, got {len(chunks)}"
    over = [(i, len(c)) for i, c in enumerate(chunks) if len(c) > MAX_MSG_LEN]
    assert not over, f"chunks exceeding MAX_MSG_LEN: {over[:5]}"


def test_file_attach_threshold_constant_is_sane():
    """V6: threshold must be above MAX_MSG_LEN (otherwise short messages
    would trigger file-attach) and well below Telegram's 50 MiB document cap.
    """
    assert FILE_ATTACH_THRESHOLD > MAX_MSG_LEN
    assert FILE_ATTACH_THRESHOLD < 50 * 1024 * 1024


def _make_channel_with_mock_bot():
    """Build a TelegramChannel whose ._app.bot is an AsyncMock."""
    channel = TelegramChannel.__new__(TelegramChannel)
    channel._app = MagicMock()
    channel._app.bot = MagicMock()
    channel._app.bot.send_message = AsyncMock(
        return_value=MagicMock(message_id=42),
    )
    channel._app.bot.send_document = AsyncMock(
        return_value=MagicMock(message_id=43),
    )
    # Bypass cache machinery used by send().
    channel._cache_message = MagicMock()
    return channel


def test_send_below_threshold_uses_inline_path():
    """V6: a 5 KB response (above MAX_MSG_LEN, below FILE_ATTACH_THRESHOLD)
    should be smart-split inline — no document attachment.
    """
    channel = _make_channel_with_mock_bot()
    text = "a" * 5000  # 5 KB, between MAX_MSG_LEN (4 KB) and FILE_ATTACH_THRESHOLD (20 KB)
    msg = OutboundMessage(target="123", text=text)
    asyncio.run(channel.send(msg))
    assert channel._app.bot.send_message.await_count >= 2  # at least 2 chunks
    assert channel._app.bot.send_document.await_count == 0


def test_send_above_threshold_uses_file_attach_path():
    """V6: above FILE_ATTACH_THRESHOLD, send must deliver a summary message
    plus exactly one document attachment — never spam-chunk the chat.
    """
    channel = _make_channel_with_mock_bot()
    text = "a" * (FILE_ATTACH_THRESHOLD + 1)
    msg = OutboundMessage(target="123", text=text)
    asyncio.run(channel.send(msg))
    # Exactly one summary message and exactly one document.
    assert channel._app.bot.send_message.await_count == 1
    assert channel._app.bot.send_document.await_count == 1
    # Document payload contains the full text (round-trip via BytesIO).
    doc_call = channel._app.bot.send_document.await_args
    bio = doc_call.kwargs["document"]
    bio.seek(0)
    assert bio.read().decode("utf-8") == text
    assert doc_call.kwargs["filename"] == "response.md"


def test_send_above_threshold_summary_includes_size():
    """V6: summary message should communicate the size so the user knows
    why they got a file instead of inline text.
    """
    channel = _make_channel_with_mock_bot()
    text = "first line for context\n" + "x" * (FILE_ATTACH_THRESHOLD)
    msg = OutboundMessage(target="123", text=text)
    asyncio.run(channel.send(msg))
    summary_call = channel._app.bot.send_message.await_args
    summary_text = summary_call.kwargs["text"]
    assert "KB" in summary_text
    # First-line snippet should be present so the user has context.
    assert "first line for context" in summary_text


def test_send_at_or_below_max_msg_len_sends_one_message():
    """V6: ≤ MAX_MSG_LEN → single message, no smart-split, no file."""
    channel = _make_channel_with_mock_bot()
    text = "x" * MAX_MSG_LEN
    msg = OutboundMessage(target="123", text=text)
    asyncio.run(channel.send(msg))
    assert channel._app.bot.send_message.await_count == 1
    assert channel._app.bot.send_document.await_count == 0


# --------------------------------------------------------------------------- #
#  Codex round-2 regression tests                                             #
# --------------------------------------------------------------------------- #


def test_send_document_failure_falls_back_to_inline_smart_split():
    """Codex P1 (round 2): if `send_document` raises, the response must still
    reach the user via inline smart-split. Otherwise users would only see a
    misleading "delivered as file" summary with no actual content.
    """
    channel = _make_channel_with_mock_bot()
    # Make send_document fail; send_message keeps working.
    channel._app.bot.send_document = AsyncMock(side_effect=RuntimeError("boom"))
    text = "a" * (FILE_ATTACH_THRESHOLD + 100)
    msg = OutboundMessage(target="123", text=text)
    asyncio.run(channel.send(msg))
    # send_document was attempted exactly once.
    assert channel._app.bot.send_document.await_count == 1
    # Fallback: inline smart-split delivered the content as multiple messages.
    # No misleading summary message — the chunks themselves are the delivery.
    assert channel._app.bot.send_message.await_count >= 2
    # Reassemble payload from the chunks (stripping continuation markers)
    # and verify the body content survived.
    import re
    sent_texts = [
        call.kwargs.get("text", "")
        for call in channel._app.bot.send_message.await_args_list
    ]
    bodies = [re.sub(r"^\(\d+/\d+\)\n", "", t) for t in sent_texts]
    rebuilt = "".join(bodies)
    # The reconstruction may have minor join-character differences (e.g.
    # paragraph boundaries are split-points), but every original char
    # of the homogeneous payload must be present.
    assert rebuilt.count("a") == text.count("a"), (
        "fallback inline delivery lost content"
    )


def test_send_above_threshold_summary_arrives_after_document():
    """Codex P1 (round 2) ordering: the document upload happens *before* the
    summary, so a successful summary always reflects the file having
    actually landed in chat (not a promise that the upload then breaks).
    """
    channel = _make_channel_with_mock_bot()
    call_order: list[str] = []

    async def track_doc(*args, **kwargs):
        call_order.append("document")
        return MagicMock(message_id=43)

    async def track_msg(*args, **kwargs):
        call_order.append("message")
        return MagicMock(message_id=42)

    channel._app.bot.send_document = AsyncMock(side_effect=track_doc)
    channel._app.bot.send_message = AsyncMock(side_effect=track_msg)

    text = "a" * (FILE_ATTACH_THRESHOLD + 1)
    msg = OutboundMessage(target="123", text=text)
    asyncio.run(channel.send(msg))
    # Document goes first; summary message follows.
    assert call_order == ["document", "message"], call_order


def test_balanced_fences_after_hard_cut_when_overflow_forces_split():
    """Codex P2 (round 2): when ``_enforce_chunk_limit`` hard-cuts a chunk
    that contains a ``` fence marker, the slice can split the marker
    across chunks, leaving an odd fence count. The smart-split loop
    must re-run ``_balance_code_fences`` after each enforce pass so the
    final chunks always have an even fence count and Telegram renders
    code blocks correctly.
    """
    # Build content where the fenced block sits very close to the limit so
    # the post-balance chunk overshoots and triggers _enforce_chunk_limit.
    code_body = "x" * 4070
    text = f"```python\n{code_body}\n```\n\nfollow-up paragraph that triggers split"
    chunks = _smart_split(text, limit=MAX_MSG_LEN)
    for i, chunk in enumerate(chunks):
        body = _strip_continuation_prefix(chunk)
        assert body.count("```") % 2 == 0, (
            f"chunk {i} has odd fence count: {body[:80]!r}…{body[-40:]!r}"
        )
        assert len(chunk) <= MAX_MSG_LEN, f"chunk {i} oversized: {len(chunk)}"


# --------------------------------------------------------------------------- #
#  Codex round-3 regression tests                                             #
# --------------------------------------------------------------------------- #


def test_fenced_run_with_no_whitespace_anchor_stays_under_limit():
    """Codex P1 (round 3): a fenced block containing a single very long run
    with no whitespace anchors used to produce an over-cap chunk because
    every enforce↔rebalance cycle re-added the fence wrapping. The fix
    reserves fence overhead at planning time so the convergence loop
    doesn't even need to run for fenced inputs.

    Repro from Codex: ``"```python\\n" + "x"*8000 + "\\n```"`` — used to
    yield a chunk of length 4100.
    """
    text = "```python\n" + "x" * 8000 + "\n```"
    chunks = _smart_split(text, limit=MAX_MSG_LEN)
    over = [(i, len(c)) for i, c in enumerate(chunks) if len(c) > MAX_MSG_LEN]
    assert not over, f"chunks exceeding MAX_MSG_LEN: {over}"


def test_whitespace_only_payload_is_not_silently_dropped():
    """Codex P2 (round 3): an input made only of paragraph separators
    used to return ``[]`` from ``_smart_split`` because the planning loop
    appended chunks via ``if current:`` (truthiness skips empty strings),
    so ``_send_inline_chunks`` then sent nothing at all and the user lost
    the message. The fix falls back to a hard char-cut when planning
    produces no chunks.

    Repro from Codex: ``"\\n" * 5000``.
    """
    text = "\n" * 5000
    chunks = _smart_split(text, limit=MAX_MSG_LEN)
    assert chunks, "whitespace-only input must produce at least one chunk"
    # All payload bytes must be present after stripping continuation markers.
    rebuilt = "".join(_strip_continuation_prefix(c) for c in chunks)
    assert rebuilt.count("\n") == text.count("\n"), (
        f"newline content lost: in={text.count(chr(10))}, out={rebuilt.count(chr(10))}"
    )
    # Each chunk fits the cap.
    assert all(len(c) <= MAX_MSG_LEN for c in chunks)
