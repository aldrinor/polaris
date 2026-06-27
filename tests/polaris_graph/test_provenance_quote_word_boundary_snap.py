"""I-wire-014 (#1327) — provenance-quote word-boundary trim (no mid-word truncation).

REGRESSION: the A15 resume re-fetch (``resume_refetch.py``) repopulates a row's cited
``direct_quote`` with the head of the freshly-fetched body via
``_build_provenance_quote``. With a hard ``content[:CAP]`` slice that head — and each
decimal-window chunk — ended MID-WORD (proven: 80/96 spans in the iwire014_replay2
evidence_pool landed at 1495-1505 chars ending alphanumeric, rendering fragments like
"usand workers" from "thousand"). The fix snaps every cut (head end + each window
start/end) to the last word boundary at/before the cap, so the stored span NEVER ends
mid-word while staying a verbatim substring of the de-hyphenated content
(faithfulness-neutral: the numeric / content-word grounding strict_verify reads is
unchanged).

Offline + deterministic: no network, no LLM, no model load. Pure string fixtures.
"""

from src.polaris_graph.retrieval.live_retriever import (
    _PROVENANCE_HEAD_CHARS_CAP,
    _QUOTE_SNAP_MAX_BACKTRACK,
    _build_provenance_quote,
    _is_quote_word_char,
    _snap_end_to_word_boundary,
    _snap_start_to_quote_word_boundary,
)

CAP = _PROVENANCE_HEAD_CHARS_CAP


def _ends_on_word_boundary(quote: str, content: str) -> bool:
    """The quote does not cut a word: it is a prefix and the char in ``content`` right
    after the prefix does not glue onto the prefix's last char to form one word."""
    if not content.startswith(quote):
        return False
    e = len(quote)
    if e >= len(content):
        return True
    return not (_is_quote_word_char(content[e - 1]) and _is_quote_word_char(content[e]))


# ── _snap_end_to_word_boundary unit cases ────────────────────────────────────

def test_snap_end_word_straddle_walks_back_to_boundary():
    text = "alpha beta gamma delta"
    # cut at index 14 lands inside "gamma" (g a m | m a) → snap back to the start of
    # "gamma" (index 11), so the head is "alpha beta " ending after a complete word.
    end = _snap_end_to_word_boundary(text, 14)
    assert end == 11  # index of "gamma" start; text[:11] == "alpha beta "
    assert text[:end] == "alpha beta "
    assert text[end - 1] == " "  # the char before the cut is whitespace (clean)
    assert not (_is_quote_word_char(text[end - 1]) and _is_quote_word_char(text[end]))


def test_snap_end_already_at_boundary_unchanged():
    text = "alpha beta gamma"
    end = len("alpha ")  # 6, sits on 'b' with a space before → already a boundary
    assert _snap_end_to_word_boundary(text, end) == end


def test_snap_end_at_or_past_length_unchanged():
    text = "short"
    assert _snap_end_to_word_boundary(text, len(text)) == len(text)
    assert _snap_end_to_word_boundary(text, len(text) + 50) == len(text)


def test_snap_end_giant_token_keeps_hard_cut():
    # a single token longer than the backtrack window must not be ejected wholesale
    text = "Z" * (_QUOTE_SNAP_MAX_BACKTRACK + 200)
    end = 100  # strictly inside the giant token, > backtrack from any boundary
    assert _snap_end_to_word_boundary(text, end) == end


def test_snap_start_walks_back_to_word_head():
    text = "alpha beta gamma"
    start = 13  # inside "gamma" (gam|ma) → snap back to 'g' at index 11
    snapped = _snap_start_to_quote_word_boundary(text, start)
    assert snapped == 11
    assert text[snapped] == "g"


# ── _build_provenance_quote integration cases (the four mandated + extras) ────

def test_head_word_straddle_never_ends_mid_word():
    # CASE: a word straddles the CAP boundary (the production "thousand" bug)
    content = ("word " * 298) + "thousand workers here"  # > CAP, "thousand" at the cut
    assert len(content) > CAP
    quote = _build_provenance_quote(content, head_chars=CAP)
    assert len(quote) <= CAP
    assert content.startswith(quote), "must be a verbatim prefix"
    assert _ends_on_word_boundary(quote, content), f"ends mid-word: {quote[-15:]!r}"
    # the cut fragment "thou"/"thousan" must NOT be the trailing token
    assert not quote.endswith("thou")
    assert not quote.endswith("thousan")


def test_sentence_boundary_within_reach():
    # CASE: a sentence terminator sits a few chars before the cap → snap lands clean
    content = ("alpha beta " * 135) + "gamma. NEXTWORD " + ("z" * 200)
    assert len(content) > CAP
    quote = _build_provenance_quote(content, head_chars=CAP)
    assert len(quote) <= CAP
    assert content.startswith(quote)
    assert _ends_on_word_boundary(quote, content), f"ends mid-word: {quote[-15:]!r}"


def test_exact_boundary_at_cap_unchanged():
    # CASE: a space sits exactly at index CAP → no snap needed, hard cut is already clean
    content = ("a " * 748) + "word here at end now done"  # space lands on even indices
    assert len(content) > CAP
    quote = _build_provenance_quote(content, head_chars=CAP)
    assert len(quote) <= CAP
    assert content.startswith(quote)
    assert _ends_on_word_boundary(quote, content)
    # char at the cap index was whitespace, so the emitted head is exactly content[:CAP]
    assert content[CAP - 1:CAP + 1][-1] == " "


def test_short_string_returned_unchanged():
    # CASE: content shorter than CAP is returned verbatim and whole
    short = "A short fetched body well under the cap, complete sentence."
    assert _build_provenance_quote(short, head_chars=CAP) == short


def test_multi_chunk_decimal_past_head_joined_quote_clean():
    # CASE: a decimal lives PAST the head → the quote ends on the final window chunk,
    # whose end IS the whole direct_quote's end. It must also end on a word boundary,
    # the centered decimal must survive, and chunk starts must be word-clean.
    tail = " the value 12.5 percent of thousand workers reported gains in 2024"
    content = ("lorem ipsum " * 140) + tail
    assert len(content) > CAP
    quote = _build_provenance_quote(
        content, head_chars=CAP, window_chars=500, max_total_chars=12000
    )
    assert "[...]" in quote, "expected a multi-chunk quote"
    assert "12.5" in quote, "the centered decimal must be preserved (faithfulness)"
    parts = quote.split("\n\n[...]\n\n")
    # every chunk is a verbatim substring of the de-hyphenated content
    for part in parts:
        assert part in content, "each chunk must be a verbatim substring"
    # the last chunk ends on a word boundary relative to the source
    last = parts[-1]
    idx = content.rfind(last)
    assert idx != -1
    end_pos = idx + len(last)
    assert end_pos >= len(content) or not (
        _is_quote_word_char(content[end_pos - 1])
        and _is_quote_word_char(content[end_pos])
    ), f"last chunk ends mid-word: {last[-15:]!r}"
    # the first window chunk (after the head) starts on a word boundary
    win = parts[1]
    widx = content.find(win)
    assert widx == 0 or not (
        _is_quote_word_char(content[widx - 1]) and _is_quote_word_char(content[widx])
    ), f"window starts mid-word: {win[:15]!r}"


def test_multi_chunk_interior_decimal_forces_window_end_snap():
    # CASE (the headline path): a decimal INTERIOR to the document with normal-word
    # filler AFTER it, so the final decimal-window ends mid-document AND mid-word —
    # this is the one case that actually exercises ``_snap_end_to_word_boundary`` on a
    # window chunk inside the joined quote (not the EOF early-return). Normal words are
    # used so the 64-char giant-token guard never trips and the snap genuinely fires.
    content = (
        ("lorem ipsum " * 130)
        + "rate was 12.5 percent "
        + ("alpha beta gamma delta " * 30)
    )
    assert len(content) > CAP
    quote = _build_provenance_quote(
        content, head_chars=CAP, window_chars=500, max_total_chars=12000
    )
    assert "[...]" in quote, "expected a multi-chunk quote"
    assert "12.5" in quote, "the centered decimal must be preserved (faithfulness)"
    last = quote.split("\n\n[...]\n\n")[-1]
    assert last in content, "last chunk must be a verbatim substring"
    idx = content.rfind(last)
    assert idx != -1
    end_pos = idx + len(last)
    # PROVE the window ended INTERIOR (not at EOF) → the END-snap was actually needed
    assert end_pos < len(content), "fixture must end the final window mid-document"
    # and the snapped end lands on a clean word boundary (never mid-word)
    assert not (
        _is_quote_word_char(content[end_pos - 1])
        and _is_quote_word_char(content[end_pos])
    ), f"window end is mid-word: {last[-15:]!r}"


def test_giant_token_at_head_keeps_hard_cut_no_overtrim():
    # CASE: pathological single token > CAP → keep the hard cut rather than drop the
    # whole token (bounded backtrack); still a verbatim prefix and <= CAP.
    content = "Z" * 3000
    quote = _build_provenance_quote(content, head_chars=CAP)
    assert quote == content[:CAP]
    assert len(quote) == CAP
    assert content.startswith(quote)


def test_verbatim_prefix_property_holds_for_head():
    # The repopulated span must be a verbatim PREFIX of the (de-hyphenated) content so
    # strict_verify's offsets/grounding still resolve.
    content = ("Sodium intake of 2.3 grams per day was associated with " * 40)
    quote = _build_provenance_quote(content, head_chars=CAP)
    head_part = quote.split("\n\n[...]\n\n")[0]
    assert content.startswith(head_part), "head segment must be a verbatim prefix"
