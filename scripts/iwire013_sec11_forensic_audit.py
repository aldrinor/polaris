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
def build_known_words(snapshot_dir: Path, floor: int) -> tuple[set[str], int]:
    """Every lowercase token occurring >= ``floor`` times across this run's fetched source text
    (``evidence_pool.json`` direct_quote/statement/title; ``corpus_snapshot.json`` text fields as a
    fallback). Returns (known_set, source_chars). An EMPTY set is returned when no source text is
    available — the caller treats that as "truncation check unvalidatable" (SKIPPED -> FAIL for
    coverage), never a silent pass."""
    freq: Counter[str] = Counter()
    chars = 0
    ev = snapshot_dir / "evidence_pool.json"
    if ev.is_file():
        try:
            rows = json.loads(ev.read_text(encoding="utf-8")) or []
            for r in rows:
                if not isinstance(r, dict):
                    continue
                for fkey in ("direct_quote", "statement", "title"):
                    t = r.get(fkey) or ""
                    if isinstance(t, str) and t:
                        chars += len(t)
                        for w in _WORD_RE.findall(t):
                            freq[w.lower()] += 1
        except Exception:  # noqa: BLE001 - malformed -> treat as absent (SKIPPED downstream)
            pass
    if chars == 0:
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
    return known, chars


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
    # are eligible for a span-cut check.
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
    # noise = rows that actually render (use the rendered count as the ship-affecting tally; fall
    # back to the pmm-row count if the rendered scan finds none but rows exist).
    count = rendered if rendered else len(pmm)
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
    known, known_chars = build_known_words(snapshot_dir, args.known_word_floor)
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
