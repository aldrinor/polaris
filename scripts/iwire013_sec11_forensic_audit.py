#!/usr/bin/env python3
"""I-wire-013 (#1327): INDEPENDENT §-1.1 forensic render-audit (the trustworthy short test).

A CLEAN-ROOM render-integrity detector. It imports ZERO production predicates — in particular it
does NOT call ``weighted_enrichment.is_render_chrome_or_unrenderable`` / ``key_findings.
is_truncated_fragment`` / ``evaluate_render_chrome_canary``. Those are the BLIND predicates this
test exists to cross-check: on the banked render the manual §-1.1 audit found ~85 chrome / ~35
truncation / 37 contradiction-noise units, while the production predicate (and so the canary AND
the v1 fast harness ``iwire013_fast_render_audit.py``) report ~0. The blindness has two roots and
this detector fixes both:

  1. UNIT BLINDNESS — the canary only enumerates clean TOP-LEVEL ``- `` bullets, so it never
     sees chrome glued INSIDE the Abstract prose, the section bodies, or the 697-unit
     "Corroborated Weighted Findings" citation blob. This detector enumerates EVERY claim-bearing
     unit (Abstract prose, every ``- **…**`` Key-Findings bullet, every claim-section body, each
     header title line, AND every ``[N]``-split unit of the Corroborated Weighted Findings).

  2. PREDICATE BLINDNESS — the production chrome check is a WHOLE-UNIT junk classifier that
     returns False the moment a unit also contains real prose ("…over the recent past.[1] 1
     Introduction 1.1 Research background 1.2 Resea.[14]" reads as real text). This detector uses
     CONTAINMENT forensic rules: a unit is chrome if it CONTAINS an author/ORCID/affiliation list,
     a license/open-access stub, bibliographic/portal junk, browser/UI junk, a glued markdown
     header / ToC fragment, or a non-Latin scrape block — even when wrapped in otherwise-real
     prose. Truncation is detected at the ``[N]`` boundary (cut word before/after a marker), NOT
     by an ellipsis marker (the production ``is_truncated_fragment`` only matches a trailing
     ``…``/``-`` and so misses every mid-word span cut in this report).

KNOWN-WORD BASIS (the truncation precision key): the "is this boundary token a real word or a
span cut?" decision is grounded in the RUN'S OWN sources — every word that occurs >= floor times
across ``evidence_pool.json`` (``direct_quote`` / ``statement`` / ``title``) is "known". So
"labor", "demand", "Acemoglu", "polarization" land in the known set automatically (this corpus is
ABOUT labor) and never false-flag, while span-cut fragments ("Resea", "publica", "hodology") are
absent and flag. No embedded English dictionary; no network.

FAIL-LOUD: exit non-zero when chrome > --chrome-max OR truncation > --truncation-max OR
contradiction-noise > --contradiction-noise-max. ABSENT INPUT IS A FAILURE, never a pass: a
missing report.md / evidence_pool.json / contradictions.json prints SKIPPED and forces a non-zero
exit (the §-1.1 false-green guard — the OPPOSITE of the v1 harness's "PASS (partial)").

Scaffolding sections are excluded from the claim-unit set deliberately: ``Reliability header``,
``Methods``, ``Capability disclosures``, ``Contradiction disclosures``, ``Bibliography``,
``Source corroboration``, ``Evidence-support disclosure``. These are pipeline scaffolding, not
carried-up source prose — the Bibliography legitimately lists DOIs/URLs, so auditing it for
"bibliographic junk" would false-flag. Audited: the Abstract, the Key-Findings bullets, every
analytical ``###``/``####`` section body, the Corroborated Weighted Findings blob, and the
Conclusion.

LAW VI: every threshold + path is a CLI arg / env read; the known-word floor is a CLI arg.

Usage (LOCAL, offline, instant):
    python scripts/iwire013_sec11_forensic_audit.py
    python scripts/iwire013_sec11_forensic_audit.py --report outputs/<run>/report.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Fail-loud thresholds (LAW VI; overridable). The banked render is EXPECTED to breach all three —
# FAIL on the banked report is the correct result; do not tune toward a pass.
_DEFAULT_CHROME_MAX = 5
_DEFAULT_TRUNCATION_MAX = 3
_DEFAULT_CONTRADICTION_NOISE_MAX = 0
_DEFAULT_KNOWN_WORD_FLOOR = 5

# Section headers that are pipeline SCAFFOLDING, not carried-up source prose (excluded from the
# claim-unit set). Matched case-insensitively against the header title's leading text.
_SCAFFOLDING_TITLES = (
    "reliability header",
    "methods",
    "capability disclosures",
    "contradiction disclosures",
    "bibliography",
    "source corroboration",
    "evidence-support disclosure",
    "research report:",  # the H1 echo of the question prompt — not a claim
)

_MARKER_RE = re.compile(r"\[\d+\]")
# One or more trailing ``[N]`` citation markers (optionally whitespace-separated) at the very end of
# a unit. Stripped from a Key-Findings bullet so the boundary-word check inspects the word BEFORE
# the citation, not the marker itself (Codex P1-2).
_TRAILING_MARKERS_RE = re.compile(r"(?:\s*\[\d+\])+\s*$")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*[A-Za-z]|[A-Za-z]")
# A run of non-Latin script (Arabic / CJK) — the report is supposed to be English-only, so a block
# of these characters is a foreign-page scrape carried up as a "claim".
_NONLATIN_RE = re.compile(r"[؀-ۿݐ-ݿ一-鿿぀-ヿ가-힯]{4,}")
_ORCID_RE = re.compile(r"\b\d{4}-\d{4}-\d{4}-\d{3}[\dxX]\b")
# A numbered ToC / heading token, e.g. "1 Introduction", "1.1 Research background", "5.2 AI and".
_TOC_TOKEN_RE = re.compile(r"(?:^|\s)\d+(?:\.\d+){0,3}\s+[A-Z][a-z]")
# A glued/inline markdown header inside a unit body (not a clean leading header).
_INLINE_HEADER_RE = re.compile(r"(?:^|[^\n#])#{1,6}\s+[A-Za-z]")
# Author-with-superscript-affiliation list: "Kanbach1,2 · Louisa Heiduk1 · …" (middot separators).
_AFFIL_MIDDOT_RE = re.compile(r"[A-Za-z]{2,}\d{1,2}(?:,\d)?\s*[·•]")
# Two-letter boundary tokens that are legitimate short words / abbreviations (never a cut).
_SHORT_OK = {
    "ai", "it", "is", "of", "to", "in", "on", "or", "an", "as", "be", "by", "we", "us", "no",
    "so", "do", "etc", "al", "eg", "ie", "vs", "id", "ml", "ui", "ux", "hr", "ev", "us", "uk",
    "eu", "gn", "io", "pp", "ed", "co", "re", "at", "if", "up", "my", "go", "he", "me", "ok",
}

# ---------------------------------------------------------------------------
# I-deepfix-001 P1_chrome_gate (#1344) — CLEAN-ROOM detector mirror of the SEVEN box1 chrome
# CLASSES. INDEPENDENT by construction: these regexes/heuristics are authored SEPARATELY here and
# import NOTHING from weighted_enrichment (the module's line-4 zero-production-predicate contract).
# The whole point of the I-wire-013 clean-room yardstick is that shared code = shared blind spot;
# the detector must catch the SAME classes by its OWN path, and any divergence from the production
# predicate on a fresh class is a FEATURE (it surfaces production blindness), never a bug to be
# resolved by unifying the two implementations. Each rule targets the same class as the production
# rule but keys on a distinct set of signals.
#   (1) paywall / purchase CTA        (2) multilingual license / repository furniture
#   (3) glued author-stats-table      (4) asterisked-author street + ZIP affiliation
#   (5) exec / promo bio              (6) stitched metadata-recital citation
#   (7) short nav / topic-list stub (four-guarded, own stopword-density precision guard)
_DET_PAYWALL_CTA_RE = re.compile(
    r"add to (?:cart|basket)"
    r"|purchase (?:this |the )?(?:article|full[- ]text|pdf|access)"
    r"|buy (?:this )?(?:article|pdf|now)"
    r"|subscribe (?:for|to get) (?:unlimited|full|instant|immediate)"
    r"|rent (?:this )?article"
    r"|free trial"
    r"|printable version",
    re.IGNORECASE,
)
_DET_REPO_LICENSE_RE = re.compile(
    r"standard-?nutzungsbedingungen|nutzungsbedingungen|econstor|"
    r"leibniz-informationszentrum|die dokumente auf|"
    r"zu eigenen wissenschaftlichen zwecken",
    re.IGNORECASE,
)
_DET_STATS_TABLE_RE = re.compile(
    r"\bobs\.?\s+mean\b|\bmean\s+std\.?\s*dev\b|\bvariable\s+obs\b|\bstd\.?\s*dev\.?\s+min\s+max\b",
    re.IGNORECASE,
)
# Detector-owned surname-digit pair regex (authored separately from the production
# _SURNAME_DIGIT_PAIR_RE; equivalent semantics, own source): a >=3-letter name-like stem welded — or
# joined by ONE space — to a 1-2 digit superscript not part of a decimal / percent / longer number.
_DET_SURNAME_DIGIT_PAIR_RE = re.compile(r"\b([A-Za-z]{3,})[ ]?(\d{1,2})(?![\w.%])")
# Detector-owned author/affiliation co-signal (mirrors production _AUTHOR_COSIGNAL_RE, own regex):
# an affiliation keyword as a WHOLE word ("\bCollege\b" never matches the welded "College2"), an
# "et al." marker, or an email address. The superscript author asterisk is NOT a co-signal at all —
# not even the ">=2 starred pairs" form: two starred CATEGORY labels ("High School1* Low College2*
# earnings differed") are byte-identical to a two-author starred byline, so the iter-1 starred-pair
# heuristic over-stripped that real finding (Codex iter-2 P1 blocker). The exactly-2-pair upgrade now
# requires an INDEPENDENT author signal (affiliation keyword / "et al." / email); a bare-stars-only
# byline is an accepted leak (leaked furniture << deleting a real finding, §-1.3 precision-first).
_DET_AUTHOR_COSIGNAL_RE = re.compile(
    r"\b(?:university|institute|college|department)\b"
    r"|\bet\s+al\b"
    r"|[\w.+-]+@[\w-]+\.[a-z]{2,}",
    re.IGNORECASE,
)
_DET_POSTAL_BLOCK_RE = re.compile(r"\b[A-Z][A-Za-z.\-]+,\s+[A-Z]{2}\s+\d{5}(?:-\d{4})?\b")
_DET_CORRESPONDENCE_RE = re.compile(r"\*\s*correspond|correspond(?:ing|ence)\s+(?:author|to)", re.IGNORECASE)
_DET_STREET_RE = re.compile(
    r"\b\d{1,5}\s+(?:[A-Z][a-z]+\s+){1,4}"
    r"(?:street|st\.|avenue|ave\.?|road|rd\.?|drive|dr\.?|boulevard|blvd\.?|lane|way|square|court)\b",
    re.IGNORECASE,
)
_DET_EXEC_TITLE_RE = re.compile(
    r"chief\s+\w+\s+officer|\bc[efot]o\b|(?:co-)?founder|managing director|"
    r"president and ceo|vice president|executive director|partner at",
    re.IGNORECASE,
)
_DET_PROMO_RE = re.compile(
    r"visionary|thought leader|passionate about|award[- ]winning|world[- ]class|leading expert|"
    r"driving (?:digital )?transformation|renowned|seasoned (?:leader|executive|professional)|"
    r"trusted advisor|proven track record|industry veteran",
    re.IGNORECASE,
)
_DET_METADATA_RECITAL_RE = re.compile(
    r"journal article[^.]{0,80}volume\s+\d+[^.]{0,60}(?:article\s+\d+|authored by)"
    r"|volume\s+\d+[^.]{0,30}issue\s+\d+[^.]{0,30}authored by",
    re.IGNORECASE,
)
_DET_TRAILING_CITE_RE = re.compile(r"(?:\s*\[\d+\])+\s*$")
_DET_TRAILING_NUMBER_RE = re.compile(r"(?:^|\s)\d{1,3}(?:\.\d{1,2})?\s*$")
# Independent (detector-owned) stopword set — authored separately from the production
# _CHROME_STOPWORDS so the two yardsticks never share source.
_DET_STOPWORDS = frozenset(
    "the a an and or of to in on at for with by from as is are was were be been that this it its "
    "they we our you your which who than into over under about between among per not no so if while "
    "during after before up down out all each more most some such also may can will has have had "
    "do does did versus vs both".split()
)


def _det_stopword_density(text: str) -> float:
    """Detector-owned stopword density (fraction of alphabetic tokens that are stopwords)."""
    toks = re.findall(r"[A-Za-z]+", text.lower())
    return (sum(1 for t in toks if t in _DET_STOPWORDS) / len(toks)) if toks else 0.0


def _det_surname_digit_pairs(text: str) -> int:
    """Detector rule 3b: count "Surname<digit>" author-superscript pairs (welded 'Kanbach1' or single-
    space 'Archbold 2') by the detector-owned _DET_SURNAME_DIGIT_PAIR_RE. NO finding-label allowlist —
    the pair COUNT plus an author/affiliation co-signal (see the call site) separates a genuine byline
    from a real two-category finding, so 'High School1 Low College2 earnings differed' (2 pairs, no
    co-signal) is KEPT while a >=3-name (or 2-name + affiliation) byline still fires."""
    return len(_DET_SURNAME_DIGIT_PAIR_RE.findall(text))


def _det_is_titlecase_heading(text: str) -> bool:
    """Detector rule 7 helper: every content word (>=3 letters, not a stopword) starts uppercase — the
    Title-Case shape of a ToC / nav heading. Detector-owned; REPLACES the old finite-verb-absence
    heuristic (a real short claim carries a lowercase verb, so it is not Title-Case and is kept)."""
    content = [w for w in re.findall(r"[A-Za-z]+", text) if len(w) >= 3 and w.lower() not in _DET_STOPWORDS]
    return len(content) >= 2 and all(w[0].isupper() for w in content)


def _det_is_short_nav_item(text: str) -> bool:
    """Detector rule 7: a short ToC/nav/topic stub — <=6 words AND a bare trailing number AND stopword
    density below 0.10 AND Title-Case heading shape. Own precision guard, independent of production."""
    core = _DET_TRAILING_CITE_RE.sub("", text.strip()).strip()
    toks = core.split()
    if not (1 <= len(toks) <= 6):
        return False
    if not _DET_TRAILING_NUMBER_RE.search(core):
        return False
    if _det_stopword_density(core) >= 0.10:
        return False
    return _det_is_titlecase_heading(core)


def _det_box1_chrome_flags(text: str) -> list[str]:
    """Detector-owned flags for the seven box1 chrome classes (clean-room; imports no production
    predicate). Returns the list of class labels that fire."""
    out: list[str] = []
    if _DET_PAYWALL_CTA_RE.search(text):
        out.append("paywall_cta")
    if _DET_REPO_LICENSE_RE.search(text):
        out.append("repo_license")
    _det_pairs = _det_surname_digit_pairs(text)
    # Asterisk is NOT a co-signal (see _DET_AUTHOR_COSIGNAL_RE note): two starred category labels are
    # byte-identical to a starred byline, so the exactly-2-pair upgrade requires an INDEPENDENT author
    # signal only (Codex iter-2 P1 blocker). Precision-first per §-1.3.
    _det_cosignal = bool(_DET_AUTHOR_COSIGNAL_RE.search(text))
    if _DET_STATS_TABLE_RE.search(text) or (
        (_det_pairs >= 3 or (_det_pairs == 2 and _det_cosignal))
        and _det_stopword_density(text) < 0.10
    ):
        out.append("author_stats_table")
    if (
        _DET_POSTAL_BLOCK_RE.search(text)
        and (_DET_STREET_RE.search(text) or _DET_CORRESPONDENCE_RE.search(text))
    ) or (_DET_CORRESPONDENCE_RE.search(text) and _DET_STREET_RE.search(text)):
        out.append("affiliation_address")
    if _DET_EXEC_TITLE_RE.search(text) and _DET_PROMO_RE.search(text):
        out.append("exec_promo_bio")
    if _DET_METADATA_RECITAL_RE.search(text):
        out.append("metadata_recital")
    if _det_is_short_nav_item(text):
        out.append("short_nav_item")
    return out


@dataclass
class _Unit:
    """One claim-bearing unit. ``category`` is its provenance (abstract / key_finding / section /
    corroborated / header). ``ends_before_marker`` / ``starts_after_marker`` mark the [N] boundary
    sides eligible for a span-cut check."""

    category: str
    text: str
    ends_before_marker: bool = False
    starts_after_marker: bool = False
    flags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Known-word basis (the run's OWN corpus) — fully offline, no embedded dictionary.
# ---------------------------------------------------------------------------
def build_known_words(snapshot_dir: Path, floor: int) -> tuple[set[str], int, bool]:
    """Every lowercase token occurring >= ``floor`` times across this run's fetched source text
    (``evidence_pool.json`` direct_quote/statement/title; ``corpus_snapshot.json`` text fields as a
    SUPPLEMENT). Returns (known_set, source_chars, evidence_pool_ok).

    ``evidence_pool.json`` is the REQUIRED known-word basis: ``evidence_pool_ok`` is True iff it is
    present AND parseable. A missing / unreadable evidence_pool.json is FAIL-LOUD — the caller exits
    non-zero (SKIPPED -> FAIL for coverage) and the corpus_snapshot.json supplement is NOT consulted,
    so an absent required basis can never be silently masked into a false green (Codex P1-1). The
    supplement only fills in when the required basis is confirmed present+readable but yielded no
    usable text."""
    freq: Counter[str] = Counter()
    chars = 0
    ev = snapshot_dir / "evidence_pool.json"
    evidence_pool_ok = False
    if ev.is_file():
        try:
            rows = json.loads(ev.read_text(encoding="utf-8")) or []
            evidence_pool_ok = True  # present AND parseable -> the required known-word basis exists
            for r in rows:
                if not isinstance(r, dict):
                    continue
                for fkey in ("direct_quote", "statement", "title"):
                    t = r.get(fkey) or ""
                    if isinstance(t, str) and t:
                        chars += len(t)
                        for w in _WORD_RE.findall(t):
                            freq[w.lower()] += 1
        except Exception:  # noqa: BLE001 - present but malformed -> required basis UNREADABLE -> FAIL
            evidence_pool_ok = False
    # corpus_snapshot.json only SUPPLEMENTS once the required evidence_pool basis is confirmed
    # present+readable. A missing/unreadable evidence_pool MUST NOT be masked by this fallback —
    # that silent fall-through was the §-1.1 false-green hole (Codex P1-1).
    if chars == 0 and evidence_pool_ok:
        cs = snapshot_dir / "corpus_snapshot.json"
        if cs.is_file():
            try:
                blob = cs.read_text(encoding="utf-8")
                chars += len(blob)
                for w in _WORD_RE.findall(blob):
                    freq[w.lower()] += 1
            except Exception:  # noqa: BLE001
                pass
    known = {w for w, c in freq.items() if c >= floor}
    return known, chars, evidence_pool_ok


# ---------------------------------------------------------------------------
# Unit enumeration
# ---------------------------------------------------------------------------
def _is_scaffolding(title: str) -> bool:
    t = title.strip().lower().lstrip("# ").strip()
    return any(t.startswith(s) for s in _SCAFFOLDING_TITLES)


def enumerate_units(report_text: str) -> list[_Unit]:
    """Enumerate every claim-bearing unit in the rendered report:

      * each header TITLE line (so a glued-chrome header — "# A Fourth Industrial Revolution
        Paradigm Shift… ## Dennis Zami Atibuni…" — is audited as its own unit, not silently
        consumed as a section title);
      * the Abstract prose, [N]-split (skipping the italic ``_…_`` disclaimer);
      * every ``- **…**`` Key-Findings bullet (one unit per bullet, continuation lines joined);
      * every claim-section ``###``/``####`` body, [N]-split (this is where the Corroborated
        Weighted Findings 697 units come from).

    Scaffolding sections (Bibliography / Methods / disclosures / Reliability header) contribute
    NO body units, but their clean titles are still title-audited (and never trip a chrome rule)."""
    lines = report_text.split("\n")
    units: list[_Unit] = []

    # Group the report into (title, level, body_lines) sections.
    sections: list[tuple[str, int, list[str]]] = []
    cur_title, cur_level, cur_body = "", 0, []
    header_re = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
    for ln in lines:
        m = header_re.match(ln)
        if m:
            if cur_title or cur_body:
                sections.append((cur_title, cur_level, cur_body))
            cur_title, cur_level, cur_body = m.group(2), len(m.group(1)), []
        else:
            cur_body.append(ln)
    if cur_title or cur_body:
        sections.append((cur_title, cur_level, cur_body))

    for title, _level, body_lines in sections:
        # (1) the header title itself is a unit (catches glued-chrome titles).
        if title:
            units.append(_Unit("header", title))
        if _is_scaffolding(title):
            continue
        body = "\n".join(body_lines)
        low_title = title.strip().lower()

        if low_title.startswith("key findings"):
            units.extend(_enumerate_key_findings_bullets(body))
            continue

        # Abstract + analytical sections + corroborated + conclusion: drop the italic disclaimer
        # paragraph, then [N]-split the remaining prose into citation units.
        prose = _strip_italic_disclaimer(body)
        if not prose.strip():
            continue
        cat = "abstract" if low_title.startswith("abstract") else (
            "corroborated" if "corroborated weighted findings" in low_title else "section"
        )
        units.extend(_split_on_markers(prose, cat))
    return units


def _strip_italic_disclaimer(body: str) -> str:
    """Drop the leading ``_…_`` provenance-disclaimer paragraph (pipeline boilerplate, not a
    claim) so it is neither chrome-flagged nor truncation-flagged."""
    out_lines = []
    for ln in body.split("\n"):
        s = ln.strip()
        if s.startswith("_") and s.endswith("_") and len(s) > 2:
            continue
        out_lines.append(ln)
    return "\n".join(out_lines)


def _enumerate_key_findings_bullets(body: str) -> list[_Unit]:
    """One unit per ``- `` / ``- **…**`` bullet; continuation lines (a wrapped truncation tail)
    join into the same bullet."""
    units: list[_Unit] = []
    cur: list[str] | None = None
    for ln in body.split("\n"):
        s = ln.strip()
        if s.startswith("_") and s.endswith("_"):
            continue
        if s.startswith("- "):
            if cur is not None:
                units.append(_make_kf_unit("\n".join(cur)))
            cur = [s[2:]]
        elif cur is not None:
            cur.append(ln)
    if cur is not None:
        units.append(_make_kf_unit("\n".join(cur)))
    return units


def _make_kf_unit(text: str) -> _Unit:
    # A KF bullet ends right before its trailing [N] and starts a fresh claim -> both boundaries
    # are eligible for a span-cut check. Strip the trailing [N] citation marker(s) FIRST so the
    # end-cut check inspects the word right before the citation ("...restricted to s.[25]" -> "s"),
    # not the marker itself: keeping the [N] made _last_word land on "]" and silently miss every
    # cut-word-before-citation in a KF bullet (Codex P1-2).
    text = _TRAILING_MARKERS_RE.sub("", text)
    return _Unit("key_finding", text, ends_before_marker=True, starts_after_marker=True)


def _split_on_markers(prose: str, category: str) -> list[_Unit]:
    """Split prose on ``[N]`` citation markers into citation units. Every piece EXCEPT the last
    ends right before a marker; every piece EXCEPT the first starts right after one."""
    pieces = _MARKER_RE.split(prose)
    n = len(pieces)
    units: list[_Unit] = []
    for i, piece in enumerate(pieces):
        if not piece.strip():
            continue
        units.append(
            _Unit(
                category,
                piece,
                ends_before_marker=(i < n - 1),
                starts_after_marker=(i > 0),
            )
        )
    return units


# ---------------------------------------------------------------------------
# Chrome detection (containment forensic rules — independent of production)
# ---------------------------------------------------------------------------
def chrome_flags(text: str) -> list[str]:
    """Forensic chrome categories a unit CONTAINS (not whole-unit junk). Returns the list of
    category labels that fire; non-empty => the unit is chrome."""
    s = text
    low = s.lower()
    flags: list[str] = []

    # browser / UI junk
    if (
        "refresh the page or clear your browser cache" in low
        or "clear your browser cache" in low
        or re.search(r"\bclose\s*[-–]\s*share\b", low)
        or "most recent answer" in low
        or "i need some assistance" in low
        or "download associated records" in low
    ):
        flags.append("browser_ui")

    # license / open access
    if (
        "creative commons" in low
        or "creativecommons.org/licenses" in low
        or "open access article distributed under" in low
        or re.search(r"©\s*20\d\d\s*the authors", low)
        or "this is an open access article" in low
    ):
        flags.append("license")

    # author / ORCID / affiliation / submission metadata
    if (
        _ORCID_RE.search(s)
        or "orcid" in low
        or _AFFIL_MIDDOT_RE.search(s)
        or re.search(r"received:\s*\d", low)
        or re.search(r"accepted:\s*\d", low)
        or "published online" in low
        or re.search(r"©\s*the author", low)
    ):
        flags.append("author_meta")

    # bibliographic / portal junk (HARD markers only — a lone URL is NOT chrome)
    if (
        re.search(r"\bdoi:\s*10\.\d", low)
        or re.search(r"\bissn\b\s*:?\s*\d", low)
        or "crossref reports the following articles citing" in low
        or "volume title publisher" in low
        or len(re.findall(r"https?://", low)) >= 3
        or len(re.findall(r"https?://(?:dx\.)?doi\.org/", low)) >= 2
    ):
        flags.append("biblio_junk")

    # glued markdown header / ToC fragment
    toc_hits = len(_TOC_TOKEN_RE.findall(s))
    if _INLINE_HEADER_RE.search(s) or toc_hits >= 2:
        flags.append("glued_header_toc")

    # non-Latin / foreign-page scrape
    if _NONLATIN_RE.search(s):
        flags.append("nonlatin_scrape")

    # I-deepfix-001 P1_chrome_gate (#1344): the seven box1 render-seam chrome classes, caught by the
    # detector's OWN independent path (clean-room mirror of the production predicate).
    flags.extend(_det_box1_chrome_flags(s))

    return flags


# ---------------------------------------------------------------------------
# Truncation detection (span cut at the [N] boundary — no ellipsis marker needed)
# ---------------------------------------------------------------------------
def _last_word(text: str) -> tuple[str, bool]:
    """The trailing alphabetic word and whether it was immediately followed by a single period
    (the artificial '.' a span-truncator appends). Trailing hyphen/quote stripped."""
    s = text.rstrip().rstrip('"”\')')
    had_period = s.endswith(".")
    if had_period:
        s = s[:-1].rstrip()
    m = re.search(r"([A-Za-z][A-Za-z'\-]*)$", s)
    if not m:
        return "", had_period
    return m.group(1).strip("-'"), had_period


def _first_word(text: str) -> str:
    m = re.match(r"\s*([A-Za-z][A-Za-z'\-]*)", text)
    return m.group(1).strip("-'") if m else ""


# Suffixes that make a longer known word a mere INFLECTION of the token (so the token is the real
# base word, not a span cut): 'disadvantage' -> {'disadvantaged','disadvantages'} only -> NOT a cut.
# A real END cut has a non-inflectional completion ('resea' -> 'research' = 'resea'+'rch').
_INFLECTIONS = ("s", "d", "es", "ed", "ing", "ly", "ic")


def _has_longer_known_prefix(w: str, known: set[str]) -> bool:
    """True iff some KNOWN corpus word is ``w`` + a NON-inflectional tail (``w`` is a chopped-END
    prefix: 'resea' -> 'research'). A token whose only longer completions are inflections
    ('disadvantage' -> 'disadvantaged'/'disadvantages') is the real base word and returns False."""
    for k in known:
        if len(k) > len(w) and k.startswith(w) and k[len(w):] not in _INFLECTIONS:
            return True
    return False


def _has_longer_known_suffix(w: str, known: set[str]) -> bool:
    """True iff some KNOWN corpus word ENDS with ``w`` and is longer (``w`` is a chopped-START
    suffix: 'hodology' -> 'methodology', 'usand' -> 'thousand')."""
    return any(len(k) > len(w) and k.endswith(w) for k in known)


def _token_is_cut(token: str, known: set[str], *, mode: str) -> bool:
    """A boundary token is a span cut iff it is NOT a known corpus word AND it is a strict
    prefix (end-cut) / suffix (start-cut) of a LONGER known corpus word. The completion gate is
    what keeps precision high: a legit-but-rare sentence-ender ('classifier', 'computerisation')
    is either known or has no longer known completion, so it does NOT flag; a real span cut
    ('Resea'->'research', 'publica'->'publications') always does. len-1 before a marker is a cut
    by construction; len-2 keeps an abbreviation allowlist."""
    if not token:
        return False
    t = token.lower()
    if t in known:
        return False
    completes = _has_longer_known_prefix(t, known) if mode == "end" else _has_longer_known_suffix(t, known)
    if len(t) == 1:
        return t not in {"a", "i"}
    if len(t) == 2:
        return t not in _SHORT_OK and completes
    return completes  # len>=3 and a chopped fragment of a known corpus word -> a span cut


def truncation_flag(unit: _Unit, known: set[str]) -> str | None:
    """Return a short reason if the unit is a mid-word span cut at a [N] boundary, else None."""
    if unit.ends_before_marker:
        w, _had = _last_word(unit.text)
        if _token_is_cut(w, known, mode="end"):
            return f"end-cut:{w!r}"
    if unit.starts_after_marker:
        w = _first_word(unit.text)
        # only a LOWERCASE leading token is a mid-word continuation cut (an uppercase start is a
        # legitimate new sentence after the citation).
        if w and w[0].islower() and _token_is_cut(w, known, mode="start"):
            return f"start-cut:{w!r}"
    return None


# ---------------------------------------------------------------------------
# Contradiction-noise (deterministic, from contradictions.json)
# ---------------------------------------------------------------------------
def _claim_values(row: dict) -> list[float]:
    vals: list[float] = []
    for c in row.get("claims") or []:
        if isinstance(c, dict) and isinstance(c.get("value"), (int, float)):
            vals.append(float(c["value"]))
    return vals


def contradiction_noise(contradictions_path: Path | None, report_text: str) -> dict[str, Any]:
    """Count possible_metric_mismatch rows from contradictions.json AND confirm they render in the
    report. Each such row is §-1.1 noise: year-numbers / DOI / page / ISSN compared as if they were
    a metric, ``close/share`` non-metric subjects, or an empty-LHS range."""
    rendered = sum(
        1 for ln in report_text.split("\n")
        if ln.lstrip().startswith("- ") and "[possible_metric_mismatch]" in ln
    )
    if contradictions_path is None or not contradictions_path.is_file():
        return {"validated": False, "count": 0, "rendered_lines": rendered, "examples": []}
    try:
        rows = json.loads(contradictions_path.read_text(encoding="utf-8")) or []
    except Exception:  # noqa: BLE001
        return {"validated": False, "count": 0, "rendered_lines": rendered, "examples": []}

    pmm: list[dict] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        pred = str(r.get("predicate") or "")
        action = str(r.get("recommended_action") or "")
        if "possible_metric_mismatch" in pred or "metric mismatch" in action.lower():
            pmm.append(r)

    examples: list[str] = []
    for r in pmm:
        subj = str(r.get("subject") or "").strip()
        pred = str(r.get("predicate") or "").strip()
        vals = _claim_values(r)
        why = []
        if any(abs(v) >= 1900 and abs(v) <= 2100 and float(v).is_integer() for v in vals):
            why.append("year-as-metric")
        if subj.lower() in {"close", "market", "paper"} or "/ share" in f"{subj} / {pred}":
            why.append("non-metric-subject")
        if not vals or any(v == 0 for v in vals):
            why.append("empty/zero-LHS")
        lo = min(vals) if vals else None
        hi = max(vals) if vals else None
        examples.append(f"{subj} / {pred}: range {lo} to {hi}" + (f"  [{','.join(why)}]" if why else ""))
    # noise = rows that actually RENDER in the report (the ship-affecting tally). Do NOT fall back
    # to len(pmm): pmm rows the render gate correctly suppressed are NOT shipped noise, so counting
    # them would false-FAIL a report whose headline block is already clean (Codex P2).
    count = rendered
    return {"validated": True, "count": count, "rendered_lines": rendered,
            "pmm_rows": len(pmm), "examples": examples}


# ---------------------------------------------------------------------------
# Audit + report
# ---------------------------------------------------------------------------
def run_audit(report_text: str, snapshot_dir: Path, known: set[str], known_chars: int,
              contradictions_path: Path | None) -> dict[str, Any]:
    units = enumerate_units(report_text)

    chrome_units: list[_Unit] = []
    for u in units:
        fl = chrome_flags(u.text)
        if fl:
            u.flags = fl
            chrome_units.append(u)

    trunc_units: list[_Unit] = []
    truncation_validated = bool(known)
    if truncation_validated:
        for u in units:
            r = truncation_flag(u, known)
            if r:
                u.flags = (u.flags or []) + [r]
                trunc_units.append(u)

    contra = contradiction_noise(contradictions_path, report_text)

    return {
        "total_units": len(units),
        "chrome": {"count": len(chrome_units), "units": chrome_units, "validated": True},
        "truncation": {
            "count": len(trunc_units), "units": trunc_units,
            "validated": truncation_validated, "known_words": len(known), "known_chars": known_chars,
        },
        "contradiction": contra,
    }


def _examples(units: list[_Unit], n: int = 5) -> list[str]:
    out = []
    for u in units[:n]:
        snippet = " ".join(u.text.split())[:150]
        out.append(f"[{u.category}|{','.join(u.flags)}] {snippet}")
    return out


def print_table(audit: dict[str, Any], thresholds: argparse.Namespace) -> None:
    ch, tr, co = audit["chrome"], audit["truncation"], audit["contradiction"]
    print("\n=== I-wire-013 INDEPENDENT sec-1.1 forensic render-audit ===")
    print(f"  claim-bearing units enumerated: {audit['total_units']}")
    print(f"  known-word basis: {tr['known_words']} corpus words "
          f"({tr['known_chars']} source chars, freq>={thresholds.known_word_floor})")
    print(f"  (a) chrome (page furniture as claim): {ch['count']:>4}  "
          f"-> {'FAIL' if ch['count'] > thresholds.chrome_max else 'PASS'}  (max {thresholds.chrome_max})")
    tr_verd = "SKIPPED->FAIL" if not tr["validated"] else (
        "FAIL" if tr["count"] > thresholds.truncation_max else "PASS")
    print(f"  (b) truncation (mid-word span cut) : {tr['count']:>4}  "
          f"-> {tr_verd}  (max {thresholds.truncation_max})")
    co_verd = "SKIPPED->FAIL" if not co["validated"] else (
        "FAIL" if co["count"] > thresholds.contradiction_noise_max else "PASS")
    print(f"  (c) contradiction-noise (pmm rows) : {co['count']:>4}  "
          f"(rendered_lines={co.get('rendered_lines')}, pmm_rows={co.get('pmm_rows','?')}) "
          f"-> {co_verd}  (max {thresholds.contradiction_noise_max})")
    print("\n  --- chrome examples ---")
    for e in _examples(ch["units"]):
        print("   ", e)
    print("  --- truncation examples ---")
    if tr["validated"]:
        for e in _examples(tr["units"]):
            print("   ", e)
    else:
        print("    SKIPPED (no known-word basis: evidence_pool.json / corpus_snapshot.json absent)")
    print("  --- contradiction-noise examples ---")
    if co["validated"]:
        for e in co["examples"][:5]:
            print("   ", e)
    else:
        print("    SKIPPED (contradictions.json absent)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="I-wire-013 independent §-1.1 forensic render-audit")
    parser.add_argument("--report", type=Path,
                        default=Path("outputs/iwire013_validate_local/report.md"),
                        help="rendered report.md to audit (sidecars resolved from its parent dir)")
    parser.add_argument("--chrome-max", type=int, default=_DEFAULT_CHROME_MAX)
    parser.add_argument("--truncation-max", type=int, default=_DEFAULT_TRUNCATION_MAX)
    parser.add_argument("--contradiction-noise-max", type=int, default=_DEFAULT_CONTRADICTION_NOISE_MAX)
    parser.add_argument("--known-word-floor", type=int, default=_DEFAULT_KNOWN_WORD_FLOOR)
    args = parser.parse_args(argv)

    report_path = args.report.resolve()
    snapshot_dir = report_path.parent
    print(f"[forensic] report={report_path}")

    if not report_path.is_file():
        # NEVER pass on absent input: SKIPPED == FAIL-for-coverage (the §-1.1 false-green guard).
        print(f"[forensic] SKIPPED: report not found at {report_path}")
        print("[forensic] OVERALL: FAIL (input absent -> zero coverage)")
        return 2

    report_text = report_path.read_text(encoding="utf-8")
    known, known_chars, evidence_pool_ok = build_known_words(snapshot_dir, args.known_word_floor)
    if not evidence_pool_ok:
        # NEVER pass when the REQUIRED known-word basis is absent: a missing / unreadable
        # evidence_pool.json is SKIPPED == FAIL-for-coverage, never a silent corpus_snapshot.json
        # fallback to a false green (the §-1.1 false-green guard — Codex P1-1).
        print(f"[forensic] SKIPPED: required evidence_pool.json missing or unreadable in {snapshot_dir}")
        print("[forensic] OVERALL: FAIL (required known-word basis absent -> zero truncation coverage)")
        return 2
    contradictions_path = snapshot_dir / "contradictions.json"
    contradictions_path = contradictions_path if contradictions_path.is_file() else None

    audit = run_audit(report_text, snapshot_dir, known, known_chars, contradictions_path)
    print_table(audit, args)

    failures: list[str] = []
    if audit["chrome"]["count"] > args.chrome_max:
        failures.append(f"chrome={audit['chrome']['count']}>{args.chrome_max}")
    if not audit["truncation"]["validated"]:
        failures.append("truncation=SKIPPED(no known-word basis)")
    elif audit["truncation"]["count"] > args.truncation_max:
        failures.append(f"truncation={audit['truncation']['count']}>{args.truncation_max}")
    if not audit["contradiction"]["validated"]:
        failures.append("contradiction-noise=SKIPPED(contradictions.json absent)")
    elif audit["contradiction"]["count"] > args.contradiction_noise_max:
        failures.append(f"contradiction_noise={audit['contradiction']['count']}>{args.contradiction_noise_max}")

    if failures:
        print(f"\n[forensic] OVERALL: FAIL ({'; '.join(failures)})")
        return 1
    print("\n[forensic] OVERALL: PASS (chrome + truncation + contradiction-noise all within bounds)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
