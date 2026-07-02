"""Render-only cosmetic repetition dedup for the final assembled ``report.md``.

This pass runs at the VERY END of the sweep, on the on-disk ``report.md``
markdown TEXT, AFTER ``strict_verify`` / NLI / 4-role D8 / provenance /
span-grounding and ALL faithfulness accounting are complete. It operates on the
output markdown STRING only. It NEVER touches any faithfulness-engine input or
carrier — not ``SectionResult``, not ``kept_sentences_pre_resolve``, not
``verification.tokens``, not the evidence pool. Because it runs strictly
downstream of the faithfulness engine and reads/writes only the rendered bytes,
it CANNOT change any verdict, count, or verified flag.

Per CLAUDE.md §-1.3, repetition is a QUALITY concern, NOT a faithfulness
concern. The good machinery (basket consolidation, strict_verify, D8) is left
untouched; this is a purely presentational last-mile clean-up of the rendered
artifact.

Behaviour (high-precision, fail-open):
  * A prose sentence in an ordinary body section that is a VERBATIM
    (citation-stripped, emphasis-stripped, whitespace/case-normalized)
    duplicate of an EARLIER-rendered body sentence is dropped at its later
    occurrence. Any ``[N]`` citation markers the dropped copy carried that the
    kept copy lacks are MERGED into the kept copy's visible text, so NO source
    is ever lost (§-1.3 CONSOLIDATE, never a hard drop).
  * FRONT summary sections (Abstract, Key Findings, Executive Summary, ...) are
    EXEMPT: their sentences are never registered and never dropped. The front
    "## Key Findings" block extracts body sentences verbatim, so a keep-first
    dedup that registered them would gut the body — exemption prevents that.
  * A section is NEVER emptied: if every eligible prose sentence in a section
    was dropped as a duplicate, its first such sentence is restored (fail-open).
  * Section headings (``#``..``######``), tables, code fences, block quotes,
    horizontal rules, blank lines and the References/Bibliography section are
    passed through byte-identical.
  * Short / near-empty sentences are never deduped (fail-open precision guard).

When the report contains no eligible duplicate, the input is returned
byte-for-byte unchanged (round-trip invariant). Pure function.
"""
from __future__ import annotations

import re

# Numeric citation markers as they appear in a FINAL rendered report.md:
# ``[12]``, ``[12, 13]``, ``[12-14]``. Used both to strip citations before
# comparing sentence text AND to merge citations across duplicate copies.
_RENDER_CITATION_RE = re.compile(r"\[\d+(?:\s*[,;–-]\s*\d+)*\]")

# Broader marker set used ONLY for the normalization key, so a residual
# provenance token (``[#ev:...]`` / ``[CITE]``) never blocks a genuine
# text-duplicate match. Mirrors the assemble-stage _CITATION_MARKER_RE.
_ANY_MARKER_RE = re.compile(
    r"\[#?ev:[^\]]*\]|\[\d+(?:\s*[,;–-]\s*\d+)*\]|\[CITE\]",
    re.IGNORECASE,
)

_WHITESPACE_RUN_RE = re.compile(r"\s+")
_EMPHASIS_RE = re.compile(r"[*_`]+")
_HEADER_RE = re.compile(r"^\s*#{1,6}\s")
_HORIZONTAL_RULE_RE = re.compile(r"^\s*([-*_])(?:\s*\1){2,}\s*$")
_LEADING_BULLET_RE = re.compile(r"^(?:[-*+]\s+|\d+[.)]\s+)")

# Headings whose bodies are INTENTIONAL verbatim re-presentations of body
# sentences (a summary repeats the body — that is the point). Matched liberally
# by prefix because OVER-exempting is fail-open (just less dedup), while
# UNDER-exempting risks gutting the body from a front summary.
_EXEMPT_TITLE_PREFIXES = (
    "abstract",
    "key finding",
    "executive summary",
    "summary",
    "key takeaway",
    "highlights",
    "tl;dr",
    "tldr",
)

_REFERENCES_HEADER_RE = re.compile(
    r"^\s*#{1,6}\s+.*\b(references|bibliography|sources|works cited|citations)\b",
    re.IGNORECASE,
)

# Fail-open precision guard: never dedup a sentence with fewer than this many
# alphanumeric content words. A genuine repeated claim sentence is long.
MIN_CONTENT_WORDS = 5

# Trailing sentence-terminal punctuation (with optional closing quotes/brackets),
# used to insert merged citation markers BEFORE the period rather than after it.
_TRAILING_TERMINAL_RE = re.compile(r"[.!?]+[\"'\]\)]*\s*$")


def _normalize_sentence(sentence: str) -> str:
    """Citation/emphasis/whitespace/case-normalized key for duplicate matching."""
    text = _ANY_MARKER_RE.sub("", sentence or "")
    text = _EMPHASIS_RE.sub("", text)
    text = _WHITESPACE_RUN_RE.sub(" ", text).strip().lower()
    text = _LEADING_BULLET_RE.sub("", text)
    return text.strip(" \t.-–—:;,")


def _normalize_heading_title(line: str) -> str:
    """Lower-cased heading text with the leading ``#`` run and markers removed."""
    text = line.strip().lstrip("#").strip()
    text = _ANY_MARKER_RE.sub("", text)
    text = _EMPHASIS_RE.sub("", text)
    return _WHITESPACE_RUN_RE.sub(" ", text).strip().lower()


def _is_exempt_title(title: str) -> bool:
    return any(title.startswith(prefix) for prefix in _EXEMPT_TITLE_PREFIXES)


def _dedup_eligible(normalized_key: str) -> bool:
    if not normalized_key:
        return False
    words = [w for w in normalized_key.split() if any(c.isalnum() for c in w)]
    return len(words) >= MIN_CONTENT_WORDS


def _cite_numbers(text: str) -> list:
    """Individual numeric citation ids present in ``text`` (order-preserving)."""
    numbers = []
    for marker in _RENDER_CITATION_RE.finditer(text or ""):
        for digits in re.findall(r"\d+", marker.group()):
            numbers.append(int(digits))
    return numbers


def _merge_citations(kept_slot: dict, dropped_sentence: str) -> bool:
    """Append to the kept copy any citation ids the dropped copy carried but the
    kept copy lacks. Guarantees NO source is lost when a duplicate is removed.
    Returns True iff at least one new citation id was merged in."""
    kept_numbers = set(_cite_numbers(kept_slot["text"]))
    missing = [n for n in _cite_numbers(dropped_sentence) if n not in kept_numbers]
    if not missing:
        return False
    added = "".join(f"[{n}]" for n in missing)
    # I-deepfix-001 i-fix: insert the merged citation markers BEFORE any trailing
    # terminal punctuation so the kept copy reads "...guidelines [3][7]." — never a
    # malformed "...guidelines [3].[7]" with a marker stranded after the period.
    text = kept_slot["text"]
    stripped = text.rstrip()
    trailing = text[len(stripped):]
    match = _TRAILING_TERMINAL_RE.search(stripped)
    if match:
        kept_slot["text"] = stripped[: match.start()] + added + stripped[match.start():] + trailing
    else:
        kept_slot["text"] = stripped + added + trailing
    return True


def _split_sentences(line: str) -> list:
    """Split a prose line into ``(sentence, trailing_separator)`` pairs whose
    concatenation reproduces ``line`` byte-for-byte.

    A boundary is a terminal ``.``/``!``/``?`` — optionally followed by closing
    quotes/brackets and inline citation markers that belong to the sentence —
    then a run of horizontal whitespace (assigned to the separator). This keeps
    trailing ``[N]`` citations attached to their sentence and lets a no-drop
    line round-trip exactly."""
    results = []
    length = len(line)
    index = 0
    start = 0
    while index < length:
        if line[index] in ".!?":
            cursor = index + 1
            # Consume closing quotes/brackets + citation markers glued to the
            # terminal punctuation ("claim.[12]" / 'claim."').
            while cursor < length:
                char = line[cursor]
                if char in ')"\'’”':
                    cursor += 1
                    continue
                if char == "[":
                    close = line.find("]", cursor)
                    if close != -1:
                        cursor = close + 1
                        continue
                break
            whitespace_end = cursor
            while whitespace_end < length and line[whitespace_end] in " \t":
                whitespace_end += 1
            if whitespace_end > cursor:  # whitespace follows -> real boundary
                results.append((line[start:cursor], line[cursor:whitespace_end]))
                start = whitespace_end
                index = whitespace_end
                continue
        index += 1
    if start < length:
        results.append((line[start:], ""))
    if not results:  # empty line
        results.append((line, ""))
    return results


def dedup_rendered_report_markdown(report_md: str) -> str:
    """Return ``report_md`` with later verbatim-duplicate body sentences dropped
    (citations merged into the kept copy). Pure; see module docstring."""
    if not report_md or not isinstance(report_md, str):
        return report_md

    lines = report_md.split("\n")
    items = []  # {"kind": "raw", "text"} | {"kind": "prose", "slots": [...]}
    seen = {}  # normalized_key -> kept sentence slot
    section_prose_slots = {}  # section_id -> [non-exempt eligible slots]

    in_code_fence = False
    references_mode = False
    exempt_section = False
    section_id = 0

    for line in lines:
        stripped = line.strip()

        # Code fences: toggle and pass everything inside through untouched.
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_code_fence = not in_code_fence
            items.append({"kind": "raw", "text": line})
            continue
        if in_code_fence:
            items.append({"kind": "raw", "text": line})
            continue

        # Headings define sections and set the exemption state.
        if _HEADER_RE.match(line):
            section_id += 1
            if _REFERENCES_HEADER_RE.match(line):
                references_mode = True
            exempt_section = references_mode or _is_exempt_title(
                _normalize_heading_title(line)
            )
            items.append({"kind": "raw", "text": line})
            continue

        # Everything from the References/Bibliography heading onward is verbatim.
        if references_mode:
            items.append({"kind": "raw", "text": line})
            continue

        # Structural / non-prose lines pass through byte-identical.
        if (
            not stripped
            or stripped.startswith("|")
            or stripped.startswith(">")
            or _HORIZONTAL_RULE_RE.match(line)
        ):
            items.append({"kind": "raw", "text": line})
            continue

        # Prose line: dedup at sentence granularity, rebuild THIS line only.
        slots = []
        for sentence, separator in _split_sentences(line):
            slot = {"text": sentence, "sep": separator, "kept": True}
            key = _normalize_sentence(sentence)
            if _dedup_eligible(key) and not exempt_section:
                if key in seen:
                    slot["contributed_merge"] = _merge_citations(seen[key], sentence)
                    slot["kept"] = False
                else:
                    seen[key] = slot
            # I-deepfix-001 i-fix: register EVERY prose sentence for the fail-open
            # guard, not only dedup-eligible ones. A short/ineligible sentence
            # (never dropped, always kept) keeps its section non-empty, so a
            # dropped duplicate that was the section's only LONG sentence is NOT
            # wrongly restored when real content still survives beside it.
            section_prose_slots.setdefault(section_id, []).append(slot)
            slots.append(slot)
        items.append({"kind": "prose", "slots": slots})

    # Fail-open guard against a bare heading: if EVERY prose slot in a section was
    # dropped, restore its first slot so the section is not left as an empty heading.
    # But a slot whose drop MERGED a new citation into the kept copy elsewhere is NOT
    # restored — its unique information is already preserved, and restoring it would
    # re-introduce a near-duplicate that differs only by a citation already merged.
    # So we restore only a PURE-identical duplicate (contributed no new citation).
    for slots in section_prose_slots.values():
        if not slots or any(slot["kept"] for slot in slots):
            continue
        for slot in slots:
            if not slot.get("contributed_merge"):
                slot["kept"] = True
                break

    out_lines = []
    for item in items:
        if item["kind"] == "raw":
            out_lines.append(item["text"])
        else:
            out_lines.append(
                "".join(
                    slot["text"] + slot["sep"] for slot in item["slots"] if slot["kept"]
                )
            )
    return "\n".join(out_lines)
