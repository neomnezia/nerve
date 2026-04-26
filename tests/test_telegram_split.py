"""Unit tests for nerve.channels.telegram._smart_split."""

from nerve.channels.telegram import _smart_split, MAX_MSG_LEN


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
