"""UTF-8 safe span truncation for audit bundle embedding (I-f15-002)."""

from __future__ import annotations

import unicodedata

MAX_SPAN_CHARS = 500
ELLIPSIS = "…"
ZWJ = "‍"


def truncate_span(text: str, max_chars: int = MAX_SPAN_CHARS) -> str:
    """Truncate ``text`` to at most ``max_chars`` codepoints total.

    Output never exceeds ``max_chars`` codepoints (including any appended
    ellipsis). Walks back to avoid splitting a base+combining sequence or
    landing immediately before/after a ZWJ join.
    """
    if max_chars < 1:
        return ""
    if len(text) <= max_chars:
        return text
    cut = max_chars - 1
    while cut > 0:
        prev_ch = text[cut - 1]
        next_ch = text[cut] if cut < len(text) else ""
        cut_in_combining = bool(next_ch) and unicodedata.combining(next_ch) != 0
        cut_at_zwj_join = prev_ch == ZWJ or next_ch == ZWJ
        if cut_in_combining or cut_at_zwj_join:
            cut -= 1
            continue
        break
    return text[:cut] + ELLIPSIS
