"""Unit tests for nerve.channels.telegram._smart_split."""

import asyncio
import re
from unittest.mock import AsyncMock, MagicMock

from nerve.channels.base import OutboundMessage
from nerve.channels.telegram import (
    FILE_ATTACH_THRESHOLD,
    MAX_MSG_LEN,
    TelegramChannel,
    _smart_split,
)


_CONTINUATION_RE = re.compile(r"^\(\d+/\d+\)\n")


def _continuation_prefix(chunk: str) -> str:
    """Extract the ``(N/M)\\n`` continuation marker prefix, if present."""
    m = _CONTINUATION_RE.match(chunk)
    return m.group(0) if m else ""


def _strip_continuation_prefix(chunk: str) -> str:
    return chunk[len(_continuation_prefix(chunk)):]


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
#  Send-path tier routing and chunk-cap invariants                            #
# --------------------------------------------------------------------------- #


def test_chunks_under_limit_after_fence_balance_grows_them():
    """Every chunk must fit MAX_MSG_LEN even after fence rebalance grows it."""
    # Construct a fenced block right at the boundary so fence prefix/suffix
    # additions force a re-split.
    code_body = "x" * 4000  # leaves <100 chars for fence + marker overhead
    text = f"```python\n{code_body}\n```\n\nmore text here that triggers split"
    chunks = _smart_split(text, limit=MAX_MSG_LEN)
    assert all(len(c) <= MAX_MSG_LEN for c in chunks), [len(c) for c in chunks]


def test_continuation_marker_overhead_handles_three_digit_counts():
    """Three-digit ``(NNN/MMM)\\n`` markers must not push any chunk over MAX_MSG_LEN."""
    # Each line is ~3900 chars, packed via paragraph splitter into one chunk
    # apiece. 105 lines → 105 chunks → markers like "(105/105)\n" (10 chars).
    big_para = "z" * 3900
    text = "\n\n".join([big_para] * 105)
    chunks = _smart_split(text, limit=MAX_MSG_LEN)
    assert len(chunks) >= 100, f"expected ≥100 chunks, got {len(chunks)}"
    over = [(i, len(c)) for i, c in enumerate(chunks) if len(c) > MAX_MSG_LEN]
    assert not over, f"chunks exceeding MAX_MSG_LEN: {over[:5]}"


def test_file_attach_threshold_constant_is_sane():
    """Threshold sits above MAX_MSG_LEN and below Telegram's 50 MiB document cap."""
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
    """4 KB < text ≤ 20 KB → smart-split inline, no document attachment."""
    channel = _make_channel_with_mock_bot()
    text = "a" * 5000  # 5 KB, between MAX_MSG_LEN (4 KB) and FILE_ATTACH_THRESHOLD (20 KB)
    msg = OutboundMessage(target="123", text=text)
    asyncio.run(channel.send(msg))
    assert channel._app.bot.send_message.await_count >= 2  # at least 2 chunks
    assert channel._app.bot.send_document.await_count == 0


def test_send_above_threshold_uses_file_attach_path():
    """text > 20 KB → exactly one document + one summary message; no chunk spam."""
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
    """Summary message includes the size (so the user knows why a file was sent)."""
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
    """text ≤ MAX_MSG_LEN → single message, no smart-split, no file."""
    channel = _make_channel_with_mock_bot()
    text = "x" * MAX_MSG_LEN
    msg = OutboundMessage(target="123", text=text)
    asyncio.run(channel.send(msg))
    assert channel._app.bot.send_message.await_count == 1
    assert channel._app.bot.send_document.await_count == 0


def test_send_document_failure_falls_back_to_inline_smart_split():
    """``send_document`` failure → inline smart-split delivers full content (no misleading summary)."""
    channel = _make_channel_with_mock_bot()
    channel._app.bot.send_document = AsyncMock(side_effect=RuntimeError("boom"))
    text = "a" * (FILE_ATTACH_THRESHOLD + 100)
    msg = OutboundMessage(target="123", text=text)
    asyncio.run(channel.send(msg))
    assert channel._app.bot.send_document.await_count == 1
    # Inline smart-split delivered content as multiple chunks (no summary).
    assert channel._app.bot.send_message.await_count >= 2
    sent_texts = [
        call.kwargs.get("text", "")
        for call in channel._app.bot.send_message.await_args_list
    ]
    bodies = [_CONTINUATION_RE.sub("", t) for t in sent_texts]
    rebuilt = "".join(bodies)
    assert rebuilt.count("a") == text.count("a"), (
        "fallback inline delivery lost content"
    )


def test_send_above_threshold_summary_arrives_after_document():
    """Document upload precedes summary so a successful summary reflects an actual landed file."""
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
    """Hard-cuts that split a ``` marker must be re-balanced before emit."""
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


def test_fenced_run_with_no_whitespace_anchor_stays_under_limit():
    """A fenced block of unbroken chars must yield chunks ≤ MAX_MSG_LEN."""
    text = "```python\n" + "x" * 8000 + "\n```"
    chunks = _smart_split(text, limit=MAX_MSG_LEN)
    over = [(i, len(c)) for i, c in enumerate(chunks) if len(c) > MAX_MSG_LEN]
    assert not over, f"chunks exceeding MAX_MSG_LEN: {over}"


def test_paragraph_boundary_preserved_after_oversized_paragraph():
    """``\\n\\n`` boundaries adjacent to oversized paragraphs survive reassembly."""
    def reassemble(chunks_):
        return "".join(_CONTINUATION_RE.sub("", c) for c in chunks_)

    # Case 1: oversized followed by short.
    long_para = "L" * 5000
    text1 = long_para + "\n\nthis is the next paragraph"
    chunks1 = _smart_split(text1, limit=MAX_MSG_LEN)
    assert reassemble(chunks1) == text1, "case 1: oversized → short lost boundary"

    # Case 2: short → oversized → short.
    text2 = "small_a\n\n" + ("B" * 5000) + "\n\nsmall_c"
    chunks2 = _smart_split(text2, limit=MAX_MSG_LEN)
    assert reassemble(chunks2) == text2, "case 2: short → oversized → short lost boundary"

    # Case 3: multiple oversized paragraphs interleaved.
    text3 = "a\n\n" + ("B" * 5000) + "\n\nc\n\n" + ("D" * 5000) + "\n\ne"
    chunks3 = _smart_split(text3, limit=MAX_MSG_LEN)
    assert reassemble(chunks3) == text3, "case 3: multi-oversized lost boundary"


def test_inline_throttle_respects_per_chat_rate_limit():
    """Inline chunk throttle ≥ 1 s between sends to stay under 1 msg/sec/chat."""
    import time

    channel = _make_channel_with_mock_bot()
    text = "a" * 5000  # produces ≥ 2 chunks (5KB > MAX_MSG_LEN)
    msg = OutboundMessage(target="123", text=text)
    start = time.monotonic()
    asyncio.run(channel.send(msg))
    elapsed = time.monotonic() - start
    chunk_count = channel._app.bot.send_message.await_count
    # Throttle is sleep(1.0) per chunk after the first → expect ≥ 1.0s elapsed.
    expected_min = 1.0 * (chunk_count - 1)
    assert elapsed >= expected_min - 0.1, (
        f"throttle too fast: {elapsed:.2f}s elapsed for {chunk_count} chunks "
        f"(expected ≥ {expected_min:.2f}s)"
    )


def test_inline_chunk_send_retries_on_retry_after_exception():
    """Transient ``RetryAfter`` is honored: sleep + retry, no chunk lost."""
    from telegram.error import RetryAfter

    channel = _make_channel_with_mock_bot()
    # First call raises RetryAfter(0), second succeeds.
    call_count = {"n": 0}

    async def maybe_flood(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RetryAfter(0)  # zero-second wait keeps test fast
        return MagicMock(message_id=42)

    channel._app.bot.send_message = AsyncMock(side_effect=maybe_flood)
    text = "small payload that fits in one chunk"
    msg = OutboundMessage(target="123", text=text)
    asyncio.run(channel.send(msg))
    # Two attempts: the first hit RetryAfter, the second succeeded.
    assert call_count["n"] == 2, f"expected retry, got {call_count['n']} attempts"


def test_adversarial_fence_tag_does_not_crash_or_drop_content():
    """Pathological fence info strings (≥ 4076 chars) must not crash or drop content."""
    # Tag length 4076 -> inner_limit = 4096 - 12 - (8 + 4076) = 0 without clamp.
    tag = "x" * 4076
    text = f"```{tag}\n" + "y" * 8000 + "\n```"
    # Must not raise.
    chunks = _smart_split(text, limit=MAX_MSG_LEN)
    assert chunks, "adversarial input dropped entirely"
    assert all(len(c) <= MAX_MSG_LEN for c in chunks)

    # Even more extreme: 10 000-char tag (negative inner_limit without clamp).
    huge_tag = "x" * 10000
    text2 = f"```{huge_tag}\n" + "y" * 8000 + "\n```"
    chunks2 = _smart_split(text2, limit=MAX_MSG_LEN)
    assert chunks2, "10k-tag input dropped entirely"
    assert all(len(c) <= MAX_MSG_LEN for c in chunks2)


def test_long_language_tag_does_not_overflow_chunks():
    """Long fence info strings (e.g. 100-char language tags) keep chunks ≤ MAX_MSG_LEN."""
    # 100-char info string — well past "typescript" (10 chars).
    long_tag = "x" * 100
    text = f"```{long_tag}\n" + "y" * 8000 + "\n```"
    chunks = _smart_split(text, limit=MAX_MSG_LEN)
    over = [(i, len(c)) for i, c in enumerate(chunks) if len(c) > MAX_MSG_LEN]
    assert not over, f"chunks exceeding MAX_MSG_LEN: {over}"

    # Sanity: a degenerate 500-char tag still doesn't overflow.
    huge_tag = "a" * 500
    text2 = f"```{huge_tag}\n" + "y" * 8000 + "\n```"
    chunks2 = _smart_split(text2, limit=MAX_MSG_LEN)
    over2 = [(i, len(c)) for i, c in enumerate(chunks2) if len(c) > MAX_MSG_LEN]
    assert not over2, f"chunks exceeding MAX_MSG_LEN with 500-char tag: {over2}"


def test_blank_paragraph_runs_preserved_across_split():
    """Multi-blank runs and leading/trailing blank paragraphs round-trip exactly."""
    def reassemble(chunks_):
        return "".join(_CONTINUATION_RE.sub("", c) for c in chunks_)

    # Case 1: 6-newline run between two normal paragraphs.
    text1 = ("a" * 2000) + "\n\n\n\n\n\n" + ("b" * 2000) + "\n\n" + ("c" * 2000)
    chunks1 = _smart_split(text1, limit=MAX_MSG_LEN)
    assert reassemble(chunks1) == text1, (
        f"6-newline run lost: in had {text1.count(chr(10))} \\n, "
        f"out has {reassemble(chunks1).count(chr(10))} \\n"
    )

    # Case 2: leading blank paragraphs.
    text2 = "\n\n\n\n" + ("x" * 5000)
    chunks2 = _smart_split(text2, limit=MAX_MSG_LEN)
    assert reassemble(chunks2) == text2, "leading blank paragraphs dropped"

    # Case 3: trailing blank paragraphs.
    text3 = ("y" * 5000) + "\n\n\n\n"
    chunks3 = _smart_split(text3, limit=MAX_MSG_LEN)
    assert reassemble(chunks3) == text3, "trailing blank paragraphs dropped"

    # Case 4: blank paragraphs adjacent to oversized paragraph.
    text4 = "head\n\n\n\n" + ("Z" * 5000) + "\n\n\n\ntail"
    chunks4 = _smart_split(text4, limit=MAX_MSG_LEN)
    assert reassemble(chunks4) == text4, (
        "blank paragraphs around oversized lost"
    )


def test_retry_after_exhaustion_raises_to_abort_remaining_chunks():
    """Exhausted ``RetryAfter`` re-raised so caller aborts and preserves the placeholder."""
    from telegram.error import RetryAfter

    channel = _make_channel_with_mock_bot()
    call_count = {"n": 0}

    async def always_flood(*args, **kwargs):
        call_count["n"] += 1
        raise RetryAfter(0)

    channel._app.bot.send_message = AsyncMock(side_effect=always_flood)
    text = "a" * 5000  # produces ≥ 2 chunks
    msg = OutboundMessage(target="123", text=text)

    raised: BaseException | None = None
    try:
        asyncio.run(channel.send(msg))
    except RetryAfter as exc:
        raised = exc

    assert raised is not None, (
        "send() must propagate exhausted RetryAfter so callers know delivery "
        "failed and can preserve streaming placeholders"
    )
    # Exactly 3 retries on the FIRST chunk, then abort — second chunk never tried.
    assert call_count["n"] == 3, (
        f"expected 3 attempts on first chunk only (then abort), got {call_count['n']}"
    )


def test_whitespace_only_payload_is_not_silently_dropped():
    """Whitespace-only input produces ≥1 chunk and preserves all newlines."""
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


def test_long_line_preserves_inter_sentence_whitespace():
    """Sentence-anchor split preserves inter-sentence whitespace verbatim (no normalization)."""
    # 4 sentences × ~1500 chars each = ~6000 chars on one line, well over
    # MAX_MSG_LEN, forcing ``_split_long_line`` to pick sentence anchors.
    sentences = [
        "Alpha." + ("a" * 1500),
        "Bravo!" + ("b" * 1500),
        "Charlie?" + ("c" * 1500),
        "Delta." + ("d" * 1500),
    ]
    # Distinct separators between each pair to detect normalization.
    seps = ["   ", "\t\t", " \t "]
    line = sentences[0] + seps[0] + sentences[1] + seps[1] + sentences[2] + seps[2] + sentences[3]

    chunks = _smart_split(line, limit=MAX_MSG_LEN)
    assert len(chunks) > 1, "test input must exceed MAX_MSG_LEN to exercise splitter"

    rebuilt = "".join(_strip_continuation_prefix(c) for c in chunks)
    assert rebuilt == line, (
        "splitter mutated whitespace: inter-sentence spacing must round-trip "
        "verbatim, not be normalized to a single space"
    )
    assert all(len(c) <= MAX_MSG_LEN for c in chunks)


def test_oversized_paragraph_preserves_leading_blank_lines():
    """Oversized paragraphs starting with blank-line runs round-trip those leading newlines."""
    short = "short paragraph"
    long_body = "L" * 5000  # well over MAX_MSG_LEN
    # ``\n\n\n`` between them: text.split("\n\n") yields
    # ["short paragraph", "\n" + long_body] — the oversized branch then
    # calls _split_paragraph("\n" + long_body, ...) whose lines list is
    # ["", long_body], exercising the empty-leading-line case.
    text = f"{short}\n\n\n{long_body}"

    chunks = _smart_split(text, limit=MAX_MSG_LEN)
    rebuilt = "".join(_strip_continuation_prefix(c) for c in chunks)
    assert rebuilt == text, (
        f"leading blank line lost: in[:30]={text[:30]!r}, "
        f"out[:30]={rebuilt[:30]!r}, len_diff={len(rebuilt) - len(text)}"
    )
    assert all(len(c) <= MAX_MSG_LEN for c in chunks)


def test_balance_code_fences_does_not_strip_trailing_whitespace():
    """Closing-fence injection must not strip trailing spaces or blank lines from body."""
    from nerve.channels.telegram import _balance_code_fences

    # Case 1: body has trailing spaces *and* a trailing blank line.
    body_with_trailing_blanks = "```python\nx = 1   \n  \n"
    chunks = [body_with_trailing_blanks, "more\n```"]
    out = _balance_code_fences(chunks)
    assert out[0].startswith(body_with_trailing_blanks), (
        f"body whitespace lost before fence close: {out[0]!r}"
    )
    assert out[0].endswith("```"), "chunk must end with closing fence"

    # Case 2: body ends with content (no trailing newline) — fence
    # balancer must add ``\n```` so the closing fence is on its own
    # line, but must not strip any of the body's trailing characters.
    body_no_trailing_nl = "```python\ndef foo():    "
    chunks = [body_no_trailing_nl, "    return 1\n```"]
    out = _balance_code_fences(chunks)
    assert out[0].startswith(body_no_trailing_nl), (
        f"body trailing spaces stripped: {out[0]!r}"
    )
    assert out[0].endswith("\n```"), "fence must be opened on a new line"


def test_send_as_file_summary_retries_on_flood_wait():
    """Summary HTML path honors ``RetryAfter`` (sleep + retry) without switching to plain text."""
    from telegram.error import RetryAfter

    channel = _make_channel_with_mock_bot()
    text = "a" * (FILE_ATTACH_THRESHOLD + 1)

    call_count = {"n": 0}
    success_msg = MagicMock(message_id=44)

    async def flood_then_succeed(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise RetryAfter(0)  # zero-second wait keeps test fast
        return success_msg

    channel._app.bot.send_message = AsyncMock(side_effect=flood_then_succeed)
    msg = OutboundMessage(target="123", text=text)
    asyncio.run(channel.send(msg))

    # Document delivered exactly once.
    assert channel._app.bot.send_document.await_count == 1
    # Summary attempted 3 times (2 floods + 1 success).
    assert call_count["n"] == 3, (
        f"expected 3 summary attempts (2 RetryAfter + 1 success), got {call_count['n']}"
    )
    # All attempts used the HTML path — plain-text fallback only fires on
    # non-retryable exceptions, not on RetryAfter exhaustion or success.
    for call in channel._app.bot.send_message.await_args_list:
        assert call.kwargs.get("parse_mode") is not None, (
            "RetryAfter retries must stay on HTML path, not switch to plain text"
        )


def test_send_as_file_summary_swallows_retry_exhaustion_after_doc_delivered():
    """Summary retry exhaustion is swallowed (document already delivered → cosmetic-only)."""
    from telegram.error import RetryAfter

    channel = _make_channel_with_mock_bot()
    text = "a" * (FILE_ATTACH_THRESHOLD + 1)

    call_count = {"n": 0}

    async def always_flood(*args, **kwargs):
        call_count["n"] += 1
        raise RetryAfter(0)

    channel._app.bot.send_message = AsyncMock(side_effect=always_flood)
    msg = OutboundMessage(target="123", text=text)

    raised: BaseException | None = None
    try:
        asyncio.run(channel.send(msg))
    except BaseException as exc:  # noqa: BLE001 — test asserts no raise
        raised = exc

    assert raised is None, (
        f"send() must not raise when summary fails after doc upload, got {raised!r}"
    )
    # Document delivered.
    assert channel._app.bot.send_document.await_count == 1
    # HTML retries (3) exhaust → plain fallback retries (3) → swallow.
    assert call_count["n"] == 6, (
        f"expected 3 HTML + 3 plain attempts under sustained flood, got {call_count['n']}"
    )
