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
    EXEMPT from the cross-section dedup: their sentences are never registered as
    the global kept first occurrence and are never dropped for matching a body
    sentence. The front "## Key Findings" block extracts body sentences verbatim,
    so a keep-first dedup that registered them would gut the body — exemption
    prevents that.
  * BACK-TO-BACK collapse (I-deepfix-001 A3): a prose sentence that is a verbatim
    duplicate of the IMMEDIATELY-PRECEDING eligible sentence in the SAME section
    is dropped at its later occurrence — and this fires in EVERY section,
    INCLUDING the exempt front summaries. This catches the same placeholder /
    claim sentence emitted 2-3x in a row (e.g. a redaction-gap notice repeated
    back-to-back inside "## Key Findings"), which the cross-section dedup cannot
    touch there. Only an adjacent identical sentence collapses, so a summary's
    single re-presentation of a body sentence is left intact. Citations are
    merged into the kept copy exactly as in the cross-section path.
  * A section is NEVER emptied: if every eligible prose sentence in a section
    was dropped as a duplicate, its first such sentence is restored (fail-open).
  * Section headings (``#``..``######``), tables, code fences, block quotes,
    horizontal rules, blank lines and the References/Bibliography section are
    passed through byte-identical. ``references_mode`` is PER-SECTION (I-deepfix-001
    A3 P1): a References/Bibliography/Sources heading byte-preserves ONLY its own
    section (so numbered ``[N]`` entries never collapse and orphan a body marker),
    and the NEXT non-references heading — e.g. the appended "## Source corroboration
    (per claim)" prose block — EXITS byte-preserve so the back-to-back collapse can
    reach it. A ``back_matter`` latch (True from the first references heading onward)
    keeps every back-matter section EXEMPT from the CROSS-SECTION dedup, exactly like
    the front summaries: back matter intentionally re-presents body claim sentences
    (the per-claim corroboration headers), so it must never be gutted — but the A3
    back-to-back collapse still fires there.
  * Short / near-empty sentences are never deduped (fail-open precision guard).

When the report contains no eligible duplicate, the input is returned
byte-for-byte unchanged (round-trip invariant). Pure function.
"""
from __future__ import annotations

import os
import re
from src.polaris_graph.settings import resolve

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

# I-deepfix-001 wave-2 (PG_DEDUP_REFHEADER_STRICT, default OFF): a STANDALONE
# references-section heading whose text is EXACTLY a references keyword (optionally
# surrounded by whitespace) — e.g. "## References", "## Bibliography", "### Sources".
# Anchored ``^...$`` so a heading that merely CONTAINS a keyword does NOT match. The
# loose _REFERENCES_HEADER_RE above matches ANY heading containing the keyword,
# INCLUDING a long level-1 document TITLE that says "...specific literature sources...";
# that false-positive latches back_matter=True at heading 1 and globally exempts the
# WHOLE report from cross-section dedup. This anchored pattern gates ONLY the
# back_matter latch when the flag is ON, so a long title no longer disables body dedup.
_REFERENCES_SECTION_STANDALONE_RE = re.compile(
    r"^\s*#{1,6}\s*(?:references|bibliography|sources|works cited|citations)\s*$",
    re.IGNORECASE,
)


def _refheader_strict_enabled() -> bool:
    """True iff PG_DEDUP_REFHEADER_STRICT is set to an explicit truthy value.
    Default (unset / empty / 0 / false / no / off) is OFF => byte-identical: the
    back_matter latch keeps its legacy loose-regex behaviour when this is OFF."""
    return resolve("PG_DEDUP_REFHEADER_STRICT").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _refheader_max_heading_len() -> int:
    """Max heading-text length (chars) that may latch back_matter under strict mode.
    A real references-section heading is a few words ("References", "References and
    Notes", "7. References", "Cited Sources"); the false-positive is a 1104-char level-1
    TITLE that merely CONTAINS "...literature sources...". Default 80 comfortably admits
    every real variant while rejecting the long title. Env PG_DEDUP_REFHEADER_MAX_LEN."""
    try:
        n = int(resolve("PG_DEDUP_REFHEADER_MAX_LEN"))
    except (TypeError, ValueError):
        return 80
    return n if n > 0 else 80


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
    seen = {}  # normalized_key -> kept sentence slot (cross-section, non-exempt)
    section_prose_slots = {}  # section_id -> [all prose slots]
    # I-deepfix-001 A3: normalized_key of the most recent KEPT eligible sentence
    # in the current section, plus its kept slot. Used for the back-to-back
    # collapse that fires in EVERY section, incl. exempt front summaries.
    section_last_eligible = {}  # section_id -> (normalized_key, kept_slot)

    in_code_fence = False
    references_mode = False
    # I-deepfix-001 A3 P1: latched True from the FIRST references/bibliography/sources
    # heading onward. Back matter (the numbered bibliography, the per-claim "Source
    # corroboration" block, the disclosed-source lists) is EXEMPT from the cross-section
    # dedup — it re-presents body claim sentences on purpose and must never be gutted —
    # while STILL getting the A3 back-to-back collapse in its prose sub-blocks.
    back_matter = False
    exempt_section = False
    section_id = 0
    refheader_strict = _refheader_strict_enabled()

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
            # I-deepfix-001 A3 P1: references_mode is now re-evaluated PER heading (not
            # latched forever). A references/bibliography/sources heading byte-preserves
            # its OWN section — protecting the numbered ``[N]`` entries — but the next
            # non-references heading (e.g. "## Source corroboration (per claim)") exits
            # byte-preserve so the A3 back-to-back collapse can reach that prose block.
            is_references_heading = bool(_REFERENCES_HEADER_RE.match(line))
            # I-deepfix-001 wave-2 (PG_DEDUP_REFHEADER_STRICT, default OFF): the back_matter
            # latch is the dominant blocker — under the OFF (legacy) path a long level-1 TITLE
            # merely CONTAINING "...literature sources..." loose-matches _REFERENCES_HEADER_RE and
            # latches back_matter=True at heading 1, globally exempting the entire report from the
            # cross-section dedup. When the flag is ON, the latch additionally requires a STANDALONE
            # short references-section heading (heading text IS the keyword, e.g. "## Bibliography"),
            # so the document title no longer disables body dedup while a real references heading still
            # latches. ``references_mode`` (the per-section byte-preserve protecting numbered ``[N]``
            # entries) is deliberately left on the loose regex, so OFF stays byte-identical and no
            # genuine references list ever loses its verbatim byte-preserve.
            if is_references_heading:
                # Latch under strict mode iff the heading is a real (short) references
                # heading — an exact standalone keyword OR any references-keyword heading
                # whose text is short. This admits every real variant ("## References and
                # Notes", "## 7. References", "## Cited Sources") while rejecting the long
                # level-1 title (Codex+Fable P2: length guard > exact-keyword anchor).
                heading_text = line.lstrip("#").strip()
                if (
                    not refheader_strict
                    or bool(_REFERENCES_SECTION_STANDALONE_RE.match(line))
                    or len(heading_text) <= _refheader_max_heading_len()
                ):
                    back_matter = True
            references_mode = is_references_heading
            # A back-matter section (corroboration / disclosure lists) is EXEMPT from the
            # cross-section dedup for the SAME reason a front summary is: it re-presents
            # body claim sentences by design. references_mode is subsumed by back_matter
            # here (a references section is always back matter); it is left in the OR only
            # for clarity — a references line never reaches the prose path below anyway.
            exempt_section = (
                references_mode
                or back_matter
                or _is_exempt_title(_normalize_heading_title(line))
            )
            items.append({"kind": "raw", "text": line})
            continue

        # A References/Bibliography/Sources section is byte-preserved verbatim (protects
        # the numbered ``[N]`` entries). Non-references back-matter prose (the per-claim
        # corroboration block) falls through to the dedup path below — exempt from the
        # cross-section pass but still eligible for the A3 back-to-back collapse.
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
            if _dedup_eligible(key):
                dropped = False
                # (1) Cross-section verbatim dedup — non-exempt sections only. A
                # later body sentence that repeats an EARLIER-rendered body
                # sentence is dropped; front summaries are exempt so they may
                # legitimately re-present a body sentence.
                if not exempt_section and key in seen:
                    slot["contributed_merge"] = _merge_citations(seen[key], sentence)
                    slot["kept"] = False
                    dropped = True
                # (2) I-deepfix-001 A3: back-to-back collapse WITHIN a section —
                # fires in EVERY section, INCLUDING exempt front summaries. An
                # eligible sentence identical to the immediately-preceding kept
                # eligible sentence in the same section is dropped (its citations
                # merged into that kept copy). Only an ADJACENT identical sentence
                # collapses, so distinct sentences and a summary's single
                # re-presentation of a body sentence are untouched.
                elif section_id in section_last_eligible:
                    prev_key, prev_slot = section_last_eligible[section_id]
                    if prev_key == key:
                        slot["contributed_merge"] = _merge_citations(prev_slot, sentence)
                        slot["kept"] = False
                        dropped = True
                if not dropped:
                    if not exempt_section:
                        seen[key] = slot
                    section_last_eligible[section_id] = (key, slot)
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
