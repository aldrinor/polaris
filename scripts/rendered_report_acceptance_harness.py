#!/usr/bin/env python3
"""I-deepfix-001 Wave 2e (#1344): rendered-report ACCEPTANCE HARNESS — the false-fired-pipeline reader.

`REAL_PLAN_2026.md` names the biggest risk as the **false-fired pipeline**: the composition +
coverage flags turn ON, the writer-path logs look busy, but the rendered ``report.md`` is still
shallow or degraded (empty sections, disclosure-only bodies, glued chrome, no cross-source analysis).
Internal counters cannot see this — they report that the machinery ran, not that real prose shipped.
This harness is the reader that checks the **actual finished paragraphs**, not the counters.

It is an ACCEPTANCE CHECK / TRIAGE, NOT a faithfulness gate. It reports per-check observations plus
an advisory top-level ``looks_false_fired`` heuristic. It NEVER raises, NEVER aborts, NEVER modifies
anything, and no hardcoded threshold decides anything critical — every threshold is an env-tunable
(LAW VI) used ONLY for the advisory flag. The process always exits 0 on content (argparse handles
``--help`` / bad-arg codes); a missing or malformed report/manifest yields a structured result with
``input_present: false``, never an exception.

INDEPENDENT DETECTOR (I-wire-013 blind-predicate lesson,
``project_iwire013_blind_predicate_independent_detector_2026_06_26``): shared code = shared blind
spot. This harness imports ZERO production predicates — its chrome / truncation / analytical /
disclosure rules are authored independently here (own regexes, own heuristics), and the disclosure
label prefixes it recognizes are re-declared as literal constants (NOT imported) so it stays a
clean-room reader of the rendered text. Any divergence from a production predicate is a FEATURE (it
surfaces production blindness), never a bug to be resolved by unifying the two implementations.

The six checks (each an observation, none a hard gate):
  1. WRITER PROSE SHIPPED per section          4. TWO-SIDED TREATMENT (debate sections)
  2. LABELED-FALLBACK-BLOCK RATE               5. CHROME / JUNK IN BODY (independent §-1.1 rules)
  3. ANALYTICAL-UNITS-IN-BODY                  6. RUBRIC-FACET COVERAGE PRESENCE (manifest, best-effort)

Usage (LOCAL, offline, instant):
    python scripts/rendered_report_acceptance_harness.py --report outputs/<run>/report.md
    python scripts/rendered_report_acceptance_harness.py --report <r> --manifest <m> --json-out out.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# LAW VI — thresholds are env-tunable and used ONLY for the advisory
# ``looks_false_fired`` flag. NONE of them gates / aborts / drops anything.
# ---------------------------------------------------------------------------
_ENV_FALLBACK_RATE_MAX = "PG_ACCEPT_FALLBACK_RATE_MAX"
_ENV_MIN_PROSE_SECTION_FRAC = "PG_ACCEPT_MIN_PROSE_SECTION_FRAC"
_ENV_MIN_ANALYTICAL_UNITS = "PG_ACCEPT_MIN_ANALYTICAL_UNITS"
_ENV_CHROME_MAX = "PG_ACCEPT_CHROME_MAX"
_ENV_KNOWN_WORD_FLOOR = "PG_ACCEPT_KNOWN_WORD_FLOOR"

_DEFAULT_FALLBACK_RATE_MAX = 0.5
_DEFAULT_MIN_PROSE_SECTION_FRAC = 0.5
_DEFAULT_MIN_ANALYTICAL_UNITS = 1
_DEFAULT_CHROME_MAX = 5
_DEFAULT_KNOWN_WORD_FLOOR = 5


@dataclass
class Thresholds:
    """Advisory-only knobs (LAW VI). Passed explicitly to :func:`analyze_report` so the analysis is
    deterministic and env-independent; :func:`main` builds one from env + CLI overrides."""

    fallback_rate_max: float = _DEFAULT_FALLBACK_RATE_MAX
    min_prose_section_frac: float = _DEFAULT_MIN_PROSE_SECTION_FRAC
    min_analytical_units: int = _DEFAULT_MIN_ANALYTICAL_UNITS
    chrome_max: int = _DEFAULT_CHROME_MAX
    known_word_floor: int = _DEFAULT_KNOWN_WORD_FLOOR


# ---------------------------------------------------------------------------
# Disclosure-label prefixes — RE-DECLARED as literals here (NOT imported from
# verified_compose) so the harness is a clean-room reader. These mirror
# verified_compose.py:1142-1151 exactly; if the production labels change, this
# harness intentionally keeps its own copy and any drift is a surfaced signal.
# ---------------------------------------------------------------------------
_DISCLOSURE_PREFIXES = (
    "[uncovered supporting evidence for:",
    "[verification incomplete:",
    "[insufficient verified evidence",
)
# The section-level curator-gap stub (a whole slot that failed strict verification). Matched as a
# containment signal, case-insensitive.
_CURATOR_GAP_RE = re.compile(
    r"did not survive strict verification|curator-actionable gap|this slot is a curator|"
    # N4 (I-deepfix-001 wave-2): plain-English gap disclosure (carries [N]).
    r"insufficient verified evidence",
    re.IGNORECASE,
)

# Section titles that are pipeline SCAFFOLDING, not carried-up source prose (excluded from the
# required-prose set). Matched case-insensitively against the header title's leading text.
_SCAFFOLDING_TITLES = (
    "reliability header",
    "methods",
    "capability disclosures",
    "contradiction disclosures",
    "evidence-support disclosure",
    "source corroboration",
    "bibliography",
    "references",
    "appendix",
    "disclosures",
    "research report:",  # the H1 echo of the question prompt — not a claim body
)

_HEADER_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_MARKER_RE = re.compile(r"\[(\d+)\]")
_RAW_EV_TOKEN_RE = re.compile(r"\[#ev:")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*[A-Za-z]|[A-Za-z]")

# ---- Independent chrome rules (authored here; import NOTHING from production) --------------------
_ORCID_RE = re.compile(r"\b\d{4}-\d{4}-\d{4}-\d{3}[\dxX]\b")
_AFFIL_MIDDOT_RE = re.compile(r"[A-Za-z]{2,}\d{1,2}(?:,\d)?\s*[·•]")
_TOC_TOKEN_RE = re.compile(r"(?:^|\s)\d+(?:\.\d+){1,3}\s+[A-Z][a-z]")
_INLINE_HEADER_RE = re.compile(r"(?:^|[^\n#])#{1,6}\s+[A-Za-z]")
_NONLATIN_RE = re.compile(r"[؀-ۿݐ-ݿ一-鿿぀-ヿ가-힯]{4,}")
_URL_RE = re.compile(r"https?://")

# ---- Analytical connectives (independent lexicon) -----------------------------------------------
_ANALYTICAL_PATTERNS = (
    r"in contrast", r"by contrast", r"whereas", r"compared (?:to|with)", r"by comparison",
    r"however", r"conversely", r"on the other hand", r"relative to", r"more than", r"less than",
    r"higher than", r"lower than", r"greater than", r"as a result", r"because", r"therefore",
    r"thus", r"consequently", r"driven by", r"leads? to", r"gives? rise to", r"results? in",
    r"caused? by", r"counterbalanc", r"offset", r"outweigh", r"correlat", r"associated with",
    r"in line with", r"consistent with", r"at odds with", r"contradict", r"whilst",
)
_ANALYTICAL_RE = re.compile("|".join(_ANALYTICAL_PATTERNS), re.IGNORECASE)

# ---- Two-sided debate detection (independent lexicon) -------------------------------------------
_DEBATE_TITLE_RE = re.compile(
    r"\bdebate\b|\bcontrovers|benefits? and risks?|opportunit\w* and challenge|"
    r"for and against|pros? and cons?|displacement .* creation|creation .* displacement|"
    r"two-sided|counter-?argument|competing",
    re.IGNORECASE,
)
_PRO_POLARITY_RE = re.compile(
    r"\bbenefit|\bimprove|\bincrease\w* (?:productivity|output|wages|employment|demand|jobs)|"
    r"\bcreat\w* (?:new )?jobs|\bgains?\b|\baugment|\bcomplement|\bopportunit|\bpositive|"
    r"\bgrowth\b|\bboost|\benhanc|\bhigher (?:wages|productivity|demand)",
    re.IGNORECASE,
)
_CON_POLARITY_RE = re.compile(
    r"\bdisplac|\bjob loss|\blos[et]\w* jobs|\breduc\w* (?:employment|wages|demand|jobs)|"
    r"\brisk\b|\bthreat|\bharm|\bnegative|\bunemploy|\binequalit|\bprecari|\bdecline\b|"
    r"\beliminat\w* (?:jobs|tasks|labor)|\bdisrupt",
    re.IGNORECASE,
)

# Two-letter boundary tokens that are legitimate short words / abbreviations (never a span cut).
_SHORT_OK = frozenset(
    "ai it is of to in on or an as be by we us no so do al eg ie vs id ml ui ux hr ev uk eu io pp "
    "ed co re at if up my go he me ok".split()
)
# Suffixes that make a longer known word a mere INFLECTION of the token (so the token is the real
# base word, not a span cut): 'disadvantage' -> {'disadvantaged','disadvantages'} only -> NOT a cut.
_INFLECTIONS = ("s", "d", "es", "ed", "ing", "ly", "ic")


# ---------------------------------------------------------------------------
# Section model + enumeration
# ---------------------------------------------------------------------------
@dataclass
class Section:
    title: str
    level: int
    body: str
    is_scaffolding: bool


def _is_scaffolding(title: str) -> bool:
    t = title.strip().lower().lstrip("# ").strip()
    return any(t.startswith(s) for s in _SCAFFOLDING_TITLES)


def split_sections(report_text: str) -> list[Section]:
    """Split the rendered report into ``Section`` records on markdown headers (any level). The
    pre-header preamble (if any) is captured as an untitled section and treated as scaffolding."""
    lines = str(report_text or "").split("\n")
    out: list[Section] = []
    cur_title, cur_level, cur_body = "", 0, []
    for ln in lines:
        m = _HEADER_RE.match(ln)
        if m:
            if cur_title or "".join(cur_body).strip():
                out.append(Section(cur_title, cur_level, "\n".join(cur_body),
                                    _is_scaffolding(cur_title) if cur_title else True))
            cur_title, cur_level, cur_body = m.group(2), len(m.group(1)), []
        else:
            cur_body.append(ln)
    if cur_title or "".join(cur_body).strip():
        out.append(Section(cur_title, cur_level, "\n".join(cur_body),
                            _is_scaffolding(cur_title) if cur_title else True))
    return out


def _strip_italic_disclaimer(body: str) -> str:
    """Drop leading ``_…_`` provenance-disclaimer paragraphs (pipeline boilerplate, not a claim)."""
    keep = []
    for ln in body.split("\n"):
        s = ln.strip()
        if s.startswith("_") and s.endswith("_") and len(s) > 2:
            continue
        keep.append(ln)
    return "\n".join(keep)


# ---------------------------------------------------------------------------
# Disclosure-block classification (Check 2 primitives)
# ---------------------------------------------------------------------------
def is_disclosure_block(text: Any) -> bool:
    """True iff a paragraph / line IS a labeled-fallback disclosure block (one of the re-declared
    prefixes) OR a section-level curator-gap stub. Independent of production (literals re-declared)."""
    s = str(text or "").strip()
    if not s:
        return False
    low = s.lower()
    if any(low.startswith(p) for p in _DISCLOSURE_PREFIXES):
        return True
    # a whole short paragraph that is essentially the curator-gap stub
    if _CURATOR_GAP_RE.search(s) and len(s) <= 400:
        return True
    return False


# ---------------------------------------------------------------------------
# Sentence splitting (Check 1 + Check 3 primitive)
# ---------------------------------------------------------------------------
# A sentence boundary: terminal ``.!?`` then any trailing ``[N]`` citation markers (kept, attached to
# the LEFT sentence via the capture group) then whitespace then an uppercase / ``[`` sentence start.
# The captured citation run is required to follow real terminal punctuation, so ``Acemoglu[2] Restrepo``
# (no preceding ``.!?``) does NOT split. Decimals ('0.2') and lowercase continuations do not split.
_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])((?:\s*\[\d+\])*)\s+(?=[A-Z\[(])")


def _split_sentences(prose: str) -> list[str]:
    """Split body prose into candidate sentences (triage-grade, not linguistic). Trailing ``[N]``
    citation markers stay attached to the sentence they cite so per-sentence citation counts are
    correct."""
    text = " ".join(str(prose or "").split())
    if not text:
        return []
    # re.split with one capture group interleaves the captured citation runs: [s0, c0, s1, c1, ...].
    pieces = _SENTENCE_BOUNDARY_RE.split(text)
    sentences: list[str] = []
    i = 0
    while i < len(pieces):
        sent = pieces[i] or ""
        cites = pieces[i + 1] if i + 1 < len(pieces) else ""
        combined = (sent + (cites or "")).strip()
        if combined:
            sentences.append(combined)
        i += 2
    return sentences


def _distinct_citation_ids(text: str) -> list[str]:
    seen: list[str] = []
    for m in _MARKER_RE.findall(text):
        if m not in seen:
            seen.append(m)
    return seen


def _looks_like_prose_sentence(sent: str) -> bool:
    """A real prose sentence: >= 6 alphabetic words and not itself a disclosure block. Filters the
    bare ``[6][7]`` citation-only fragments and one-word stubs that pad a degraded section."""
    if is_disclosure_block(sent):
        return False
    words = re.findall(r"[A-Za-z]{2,}", sent)
    return len(words) >= 6


# ---------------------------------------------------------------------------
# Check 1 — writer prose shipped per section
# ---------------------------------------------------------------------------
def _iter_bullets(body: str) -> list[str]:
    out: list[str] = []
    cur: list[str] | None = None
    for ln in body.split("\n"):
        s = ln.strip()
        if s.startswith("- "):
            if cur is not None:
                out.append("\n".join(cur))
            cur = [s[2:]]
        elif cur is not None:
            cur.append(ln)
    if cur is not None:
        out.append("\n".join(cur))
    return out


def classify_section(section: Section) -> dict[str, Any]:
    """Classify one content section. Returns per-section observations incl. a ``verdict``:
    empty / disclosure_only / single_sentence / prose_shipped / bullets_present / bullets_degraded."""
    prose = _strip_italic_disclaimer(section.body)
    low_title = section.title.strip().lower()
    is_bulleted = low_title.startswith("key findings") or (
        len(_iter_bullets(prose)) >= 2 and len(_split_sentences(prose)) <= len(_iter_bullets(prose))
    )

    # split body into paragraphs to count disclosure blocks vs real prose paragraphs
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", prose) if p.strip()]
    disclosure_paras = [p for p in paragraphs if is_disclosure_block(p)]

    if is_bulleted:
        bullets = [b for b in _iter_bullets(prose) if b.strip()]
        real_bullets = [b for b in bullets if not is_disclosure_block(b) and re.search(r"[A-Za-z]{2,}", b)]
        verdict = "bullets_present" if real_bullets else ("bullets_degraded" if bullets else "empty")
        return {
            "title": section.title, "level": section.level, "type": "bulleted", "verdict": verdict,
            "n_bullets": len(bullets), "n_real_bullets": len(real_bullets),
            "n_sentences": 0, "n_disclosure_blocks": len(disclosure_paras),
        }

    sentences = _split_sentences(prose)
    real_sentences = [s for s in sentences if _looks_like_prose_sentence(s)]
    n_real = len(real_sentences)
    if not prose.strip():
        verdict = "empty"
    elif n_real == 0 and (disclosure_paras or _CURATOR_GAP_RE.search(prose)):
        verdict = "disclosure_only"
    elif n_real == 0:
        verdict = "empty"
    elif n_real == 1:
        verdict = "single_sentence"
    else:
        verdict = "prose_shipped"
    return {
        "title": section.title, "level": section.level, "type": "prose", "verdict": verdict,
        "n_sentences": n_real, "n_disclosure_blocks": len(disclosure_paras), "n_bullets": 0,
        "n_real_bullets": 0,
    }


# ---------------------------------------------------------------------------
# Check 5 — independent chrome / junk detector (imports NO production predicate)
# ---------------------------------------------------------------------------
def body_chrome_flags(text: str) -> list[str]:
    """Forensic chrome categories a body unit CONTAINS (containment rules, not whole-unit junk).
    Independent of production by construction. Returns the list of category labels that fire."""
    s = str(text or "")
    low = s.lower()
    flags: list[str] = []

    if _RAW_EV_TOKEN_RE.search(s):
        flags.append("raw_ev_token")

    if (
        "refresh the page or clear your browser cache" in low
        or "clear your browser cache" in low
        or "download associated records" in low
        or "most recent answer" in low
    ):
        flags.append("browser_ui")

    if (
        "creative commons" in low
        or "creativecommons.org/licenses" in low
        or "open access article distributed under" in low
        or "this is an open access article" in low
        or re.search(r"©\s*20\d\d\s*the authors?", low)
    ):
        flags.append("license")

    if (
        _ORCID_RE.search(s)
        or "orcid" in low
        or _AFFIL_MIDDOT_RE.search(s)
        or re.search(r"received:\s*\d", low)
        or re.search(r"accepted:\s*\d", low)
        or "published online" in low
    ):
        flags.append("author_meta")

    if (
        re.search(r"\bdoi:\s*10\.\d", low)
        or re.search(r"\bissn\b\s*:?\s*\d", low)
        or "crossref reports the following articles citing" in low
        or "journal issn" in low
        or "volume title" in low
        or len(_URL_RE.findall(low)) >= 3
    ):
        flags.append("biblio_junk")

    if _INLINE_HEADER_RE.search(s) or len(_TOC_TOKEN_RE.findall(s)) >= 2:
        flags.append("glued_header_toc")

    if _NONLATIN_RE.search(s):
        flags.append("nonlatin_scrape")

    return flags


# ---- truncation (own known-word basis; evaluated only when evidence_pool.json present) ----------
def build_known_words(snapshot_dir: Path | None, floor: int) -> tuple[set[str], int, bool]:
    """Every lowercase token occurring >= ``floor`` times across this run's fetched source text
    (``evidence_pool.json`` direct_quote/statement/title). Returns (known_set, source_chars,
    basis_available). A missing/unreadable evidence_pool.json => basis_available False (truncation
    then reported ``not_evaluated`` — never a silent pass, never a false flag)."""
    freq: Counter[str] = Counter()
    chars = 0
    if snapshot_dir is None:
        return set(), 0, False
    ev = Path(snapshot_dir) / "evidence_pool.json"
    if not ev.is_file():
        return set(), 0, False
    try:
        rows = json.loads(ev.read_text(encoding="utf-8")) or []
    except Exception:  # noqa: BLE001 — malformed basis -> unavailable (never a false flag)
        return set(), 0, False
    for r in rows:
        if not isinstance(r, dict):
            continue
        for fkey in ("direct_quote", "statement", "title"):
            t = r.get(fkey) or ""
            if isinstance(t, str) and t:
                chars += len(t)
                for w in _WORD_RE.findall(t):
                    freq[w.lower()] += 1
    known = {w for w, c in freq.items() if c >= floor}
    return known, chars, True


def _has_longer_known_prefix(w: str, known: set[str]) -> bool:
    return any(len(k) > len(w) and k.startswith(w) and k[len(w):] not in _INFLECTIONS for k in known)


def _has_longer_known_suffix(w: str, known: set[str]) -> bool:
    return any(len(k) > len(w) and k.endswith(w) for k in known)


def _token_is_cut(token: str, known: set[str], *, mode: str) -> bool:
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
    return completes


def truncation_flags(body: str, known: set[str]) -> list[str]:
    """Mid-word span cuts at a ``[N]`` boundary in the body: the word immediately before a citation
    marker that is a non-inflectional prefix of a LONGER known corpus word ('Resea' -> 'research')."""
    if not known:
        return []
    out: list[str] = []
    # inspect the token right before each [N] marker
    for m in _MARKER_RE.finditer(str(body or "")):
        pre = body[max(0, m.start() - 40):m.start()]
        wm = re.search(r"([A-Za-z][A-Za-z'\-]*)\.?\s*$", pre.rstrip())
        if not wm:
            continue
        w = wm.group(1).strip("-'")
        if _token_is_cut(w, known, mode="end"):
            out.append(f"end-cut:{w!r}")
    return out


# ---------------------------------------------------------------------------
# Check 3 — analytical cross-source units
# ---------------------------------------------------------------------------
def count_analytical_units(sections: list[Section]) -> dict[str, Any]:
    """Count body sentences that are cross-source analytical units (>=1 analytical connective AND
    >=2 DISTINCT [N] citations) vs plain single-source lookups (exactly 1 distinct citation, no
    analytical connective). Only non-scaffolding content sections are scanned."""
    analytical = 0
    single_source = 0
    examples: list[str] = []
    for sec in sections:
        if sec.is_scaffolding:
            continue
        if sec.title.strip().lower().startswith("key findings"):
            # bullets are handled as their own units
            units = [b for b in _iter_bullets(_strip_italic_disclaimer(sec.body)) if b.strip()]
        else:
            units = _split_sentences(_strip_italic_disclaimer(sec.body))
        for sent in units:
            if is_disclosure_block(sent):
                continue
            cites = _distinct_citation_ids(sent)
            has_analytical = bool(_ANALYTICAL_RE.search(sent))
            if has_analytical and len(cites) >= 2:
                analytical += 1
                if len(examples) < 8:
                    examples.append(" ".join(sent.split())[:200])
            elif len(cites) == 1 and not has_analytical:
                single_source += 1
    return {
        "cross_source_analytical_units": analytical,
        "single_source_lookups": single_source,
        "examples": examples,
    }


# ---------------------------------------------------------------------------
# Check 4 — two-sided treatment (debate sections)
# ---------------------------------------------------------------------------
def two_sided_analysis(sections: list[Section], question: str) -> dict[str, Any]:
    """Detect debate framing (question / any content-section title) and, if present, whether both a
    supported PRO (positive-polarity sentence WITH a citation) and a supported CON exist in the body."""
    titles = " ".join(s.title for s in sections)
    debate = bool(_DEBATE_TITLE_RE.search(f"{question}\n{titles}"))
    pro = 0
    con = 0
    for sec in sections:
        if sec.is_scaffolding:
            continue
        body_units = _split_sentences(_strip_italic_disclaimer(sec.body))
        body_units += [b for b in _iter_bullets(_strip_italic_disclaimer(sec.body)) if b.strip()]
        for sent in body_units:
            if is_disclosure_block(sent):
                continue
            if not _distinct_citation_ids(sent):
                continue
            if _PRO_POLARITY_RE.search(sent):
                pro += 1
            if _CON_POLARITY_RE.search(sent):
                con += 1
    two_sided: bool | None
    missing: str | None
    if not debate:
        two_sided, missing = None, None
    else:
        two_sided = pro > 0 and con > 0
        missing = None if two_sided else ("con" if pro > 0 else ("pro" if con > 0 else "both"))
    return {
        "debate_detected": debate,
        "supported_pro_count": pro,
        "supported_con_count": con,
        "two_sided": two_sided,
        "missing_side": missing,
    }


# ---------------------------------------------------------------------------
# Check 6 — rubric / facet coverage presence (manifest, best-effort)
# ---------------------------------------------------------------------------
_FACET_STOPWORDS = frozenset(
    "the a an and or of to in on at for with by from as is are was were be vs and rct trial study "
    "pivotal id type".split()
)


def _facet_keywords(entity_id: str) -> list[str]:
    toks = [t for t in re.split(r"[_\W]+", str(entity_id or "").lower()) if t]
    return [t for t in toks if len(t) >= 3 and t not in _FACET_STOPWORDS]


def _extract_facets(manifest: dict | None) -> list[dict[str, Any]]:
    """Best-effort facet/rubric list from a few known manifest schemas. Never raises."""
    if not isinstance(manifest, dict):
        return []
    facets: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(fid: str) -> None:
        fid = str(fid or "").strip()
        if fid and fid not in seen:
            seen.add(fid)
            facets.append({"facet_id": fid, "keywords": _facet_keywords(fid)})

    fcr = manifest.get("frame_coverage_report")
    if isinstance(fcr, dict):
        for e in fcr.get("entries") or []:
            if isinstance(e, dict) and e.get("entity_id"):
                _add(e["entity_id"])
    comp = manifest.get("completeness")
    if isinstance(comp, dict):
        for tid in comp.get("uncovered_topic_ids") or []:
            _add(tid)
        for tid in comp.get("covered_topic_ids") or []:
            _add(tid)
    # generic fallbacks
    for key in ("facets", "rubric", "required_facets", "expert_facets"):
        val = manifest.get(key)
        if isinstance(val, list):
            for item in val:
                if isinstance(item, str):
                    _add(item)
                elif isinstance(item, dict):
                    _add(item.get("facet_id") or item.get("id") or item.get("name") or "")
    return facets


def facet_coverage(body_text: str, manifest: dict | None) -> dict[str, Any]:
    facets = _extract_facets(manifest)
    if not facets:
        return {"facet_list_available": False, "facets": [], "present": 0, "absent": 0}
    low_body = str(body_text or "").lower()
    present: list[str] = []
    absent: list[str] = []
    detail: list[dict[str, Any]] = []
    for f in facets:
        fid = f["facet_id"]
        kws = f["keywords"]
        exact = fid.lower() in low_body
        hit = sum(1 for k in kws if k in low_body)
        is_present = exact or (bool(kws) and hit >= max(1, (len(kws) + 1) // 2))
        (present if is_present else absent).append(fid)
        detail.append({"facet_id": fid, "keywords_matched": hit, "keywords_total": len(kws),
                       "exact": exact, "present": is_present})
    return {
        "facet_list_available": True, "present": len(present), "absent": len(absent),
        "present_facets": present, "absent_facets": absent, "detail": detail,
    }


# ---------------------------------------------------------------------------
# Core analysis (pure, deterministic, env-independent)
# ---------------------------------------------------------------------------
def analyze_report(
    report_text: str,
    manifest: dict | None = None,
    snapshot_dir: Path | None = None,
    thresholds: Thresholds | None = None,
) -> dict[str, Any]:
    """Read the ACTUAL rendered report and return per-check observations + advisory
    ``looks_false_fired``. NEVER raises: any internal error degrades to a structured field."""
    th = thresholds or Thresholds()
    result: dict[str, Any] = {
        "input_present": bool(str(report_text or "").strip()),
        "thresholds": asdict(th),
    }
    try:
        question = ""
        if isinstance(manifest, dict):
            question = str(manifest.get("question") or manifest.get("research_question") or "")

        sections = split_sections(report_text)
        content_sections = [s for s in sections if not s.is_scaffolding and s.title]
        if not question:
            for s in sections:
                if s.title.strip().lower().startswith("research report:"):
                    question = s.title.split(":", 1)[1].strip()
                    break

        # ---- Check 1: writer prose shipped per section ----
        per_section = [classify_section(s) for s in content_sections]
        prose_secs = [c for c in per_section if c["type"] == "prose"]
        prose_shipped = [c for c in prose_secs if c["verdict"] == "prose_shipped"]
        prose_frac = (len(prose_shipped) / len(prose_secs)) if prose_secs else 0.0
        degraded = [c for c in per_section if c["verdict"] in ("empty", "disclosure_only", "bullets_degraded")]
        check1 = {
            "content_sections": len(content_sections),
            "prose_sections": len(prose_secs),
            "prose_shipped_sections": len(prose_shipped),
            "prose_shipped_fraction": round(prose_frac, 4),
            "degraded_sections": [c["title"] for c in degraded],
            "per_section": per_section,
        }

        # ---- Check 2: labeled-fallback-block rate ----
        total_paras = 0
        disclosure_paras = 0
        disclosure_chars = 0
        total_chars = 0
        heavy_sections: list[str] = []
        for s in content_sections:
            prose = _strip_italic_disclaimer(s.body)
            paras = [p.strip() for p in re.split(r"\n\s*\n", prose) if p.strip()]
            sec_disc = [p for p in paras if is_disclosure_block(p)]
            total_paras += len(paras)
            disclosure_paras += len(sec_disc)
            for p in paras:
                total_chars += len(p)
            for p in sec_disc:
                disclosure_chars += len(p)
            if paras and len(sec_disc) / len(paras) >= 0.5:
                heavy_sections.append(s.title)
        unit_rate = (disclosure_paras / total_paras) if total_paras else 0.0
        char_rate = (disclosure_chars / total_chars) if total_chars else 0.0
        check2 = {
            "total_body_paragraphs": total_paras,
            "disclosure_paragraphs": disclosure_paras,
            "fallback_block_rate_by_unit": round(unit_rate, 4),
            "fallback_block_rate_by_char": round(char_rate, 4),
            "disclosure_heavy_sections": heavy_sections,
        }

        # ---- Check 3: analytical units in body ----
        check3 = count_analytical_units(content_sections)

        # ---- Check 4: two-sided treatment ----
        check4 = two_sided_analysis(content_sections, question)

        # ---- Check 5: chrome / junk in body ----
        # Scan at the §-1.1 unit granularity: each body paragraph is split on ``[N]`` citation
        # markers into sub-units, so glued chrome inside a large blob (e.g. the Corroborated Weighted
        # Findings paragraph) is counted honestly, not as a single whole-paragraph hit.
        chrome_hits: list[dict[str, Any]] = []
        raw_ev_tokens = 0
        for s in content_sections:
            prose = _strip_italic_disclaimer(s.body)
            for para in [p.strip() for p in re.split(r"\n\s*\n", prose) if p.strip()]:
                if is_disclosure_block(para):
                    continue
                raw_ev_tokens += len(_RAW_EV_TOKEN_RE.findall(para))
                sub_units = [u.strip() for u in _MARKER_RE.split(para) if u.strip()]
                sub_hits = [(u, body_chrome_flags(u)) for u in sub_units]
                sub_hits = [(u, fl) for (u, fl) in sub_hits if fl]
                if sub_hits:
                    # fine-grained: one hit per chrome-flagged [N]-split sub-unit
                    for u, fl in sub_hits:
                        chrome_hits.append({"section": s.title, "flags": fl,
                                            "snippet": " ".join(u.split())[:160]})
                else:
                    # union floor: never undercount below the whole-paragraph signal
                    fl = body_chrome_flags(para)
                    if fl:
                        chrome_hits.append({"section": s.title, "flags": fl,
                                            "snippet": " ".join(para.split())[:160]})
        body_all = "\n".join(_strip_italic_disclaimer(s.body) for s in content_sections)
        known, known_chars, basis_ok = build_known_words(snapshot_dir, th.known_word_floor)
        trunc = truncation_flags(body_all, known) if basis_ok else []
        check5 = {
            "chrome_units": len(chrome_hits),
            "raw_ev_tokens": raw_ev_tokens,
            "chrome_examples": chrome_hits[:8],
            "truncation_evaluated": basis_ok,
            "truncation_count": len(trunc) if basis_ok else None,
            "truncation_examples": trunc[:8] if basis_ok else [],
            "known_word_basis_chars": known_chars,
        }

        # ---- Check 6: rubric/facet coverage presence ----
        check6 = facet_coverage(body_all, manifest)

        # ---- advisory looks_false_fired heuristic (env-tunable ONLY) ----
        reasons: list[str] = []
        if unit_rate > th.fallback_rate_max:
            reasons.append(f"fallback_block_rate {unit_rate:.2f} > {th.fallback_rate_max}")
        if prose_secs and prose_frac < th.min_prose_section_frac:
            reasons.append(f"prose_shipped_fraction {prose_frac:.2f} < {th.min_prose_section_frac}")
        if check3["cross_source_analytical_units"] < th.min_analytical_units:
            reasons.append(
                f"cross_source_analytical_units {check3['cross_source_analytical_units']} "
                f"< {th.min_analytical_units}"
            )
        if (len(chrome_hits) + raw_ev_tokens) > th.chrome_max:
            reasons.append(f"body_chrome {len(chrome_hits) + raw_ev_tokens} > {th.chrome_max}")

        result.update({
            "question": question,
            "check1_writer_prose_shipped": check1,
            "check2_labeled_fallback_rate": check2,
            "check3_analytical_units": check3,
            "check4_two_sided": check4,
            "check5_chrome_junk": check5,
            "check6_facet_coverage": check6,
            "looks_false_fired": bool(reasons),
            "reasons": reasons,
        })
    except Exception as exc:  # noqa: BLE001 — triage NEVER raises; degrade to a structured error field
        result["analysis_error"] = f"{type(exc).__name__}: {exc}"
        result.setdefault("looks_false_fired", None)
        result.setdefault("reasons", [])
    return result


# ---------------------------------------------------------------------------
# Plain-English summary
# ---------------------------------------------------------------------------
def _verdict_word(ok: bool) -> str:
    return "OK" if ok else "FLAG"


def format_summary(result: dict[str, Any], th: Thresholds) -> str:
    lines: list[str] = []
    lines.append("=== rendered-report acceptance harness (I-deepfix-001 Wave 2e) ===")
    if not result.get("input_present"):
        lines.append("  input_present: NO — report is empty or was not found.")
    if result.get("analysis_error"):
        lines.append(f"  analysis_error: {result['analysis_error']}")
        lines.append("  (triage never raises; treat this as a FLAG and inspect the report by hand.)")
        return "\n".join(lines)

    c1 = result["check1_writer_prose_shipped"]
    c2 = result["check2_labeled_fallback_rate"]
    c3 = result["check3_analytical_units"]
    c4 = result["check4_two_sided"]
    c5 = result["check5_chrome_junk"]
    c6 = result["check6_facet_coverage"]

    lines.append(
        f"  (1) writer prose shipped : {c1['prose_shipped_sections']}/{c1['prose_sections']} prose "
        f"sections shipped real multi-sentence prose "
        f"(frac {c1['prose_shipped_fraction']:.2f}) -> "
        f"{_verdict_word(c1['prose_shipped_fraction'] >= th.min_prose_section_frac or not c1['prose_sections'])}"
    )
    if c1["degraded_sections"]:
        lines.append(f"        degraded sections: {', '.join(c1['degraded_sections'][:8])}")
    lines.append(
        f"  (2) labeled-fallback rate: {c2['disclosure_paragraphs']}/{c2['total_body_paragraphs']} "
        f"body paragraphs are disclosure blocks (by-unit {c2['fallback_block_rate_by_unit']:.2f}, "
        f"by-char {c2['fallback_block_rate_by_char']:.2f}) -> "
        f"{_verdict_word(c2['fallback_block_rate_by_unit'] <= th.fallback_rate_max)}"
    )
    if c2["disclosure_heavy_sections"]:
        lines.append(f"        disclosure-heavy: {', '.join(c2['disclosure_heavy_sections'][:8])}")
    lines.append(
        f"  (3) analytical units     : {c3['cross_source_analytical_units']} cross-source analytical "
        f"vs {c3['single_source_lookups']} single-source lookups -> "
        f"{_verdict_word(c3['cross_source_analytical_units'] >= th.min_analytical_units)}"
    )
    if c4["debate_detected"]:
        lines.append(
            f"  (4) two-sided treatment  : debate detected — pro={c4['supported_pro_count']} "
            f"con={c4['supported_con_count']} two_sided={c4['two_sided']}"
            + (f" (missing: {c4['missing_side']})" if c4["missing_side"] else "")
            + f" -> {_verdict_word(bool(c4['two_sided']))}"
        )
    else:
        lines.append("  (4) two-sided treatment  : no debate framing detected -> n/a")
    trunc = c5["truncation_count"]
    trunc_txt = "not_evaluated (no evidence_pool.json)" if not c5["truncation_evaluated"] else str(trunc)
    lines.append(
        f"  (5) chrome / junk in body: {c5['chrome_units']} chrome unit(s), "
        f"{c5['raw_ev_tokens']} raw [#ev tokens, truncation={trunc_txt} -> "
        f"{_verdict_word((c5['chrome_units'] + c5['raw_ev_tokens']) <= th.chrome_max)}"
    )
    if c6["facet_list_available"]:
        lines.append(
            f"  (6) facet coverage       : {c6['present']}/{c6['present'] + c6['absent']} manifest "
            f"facets present in body"
            + (f" (absent: {', '.join(c6['absent_facets'][:6])})" if c6["absent_facets"] else "")
        )
    else:
        lines.append("  (6) facet coverage       : no facet/rubric list in manifest -> n/a")

    lff = result.get("looks_false_fired")
    lines.append("")
    lines.append(f"  looks_false_fired: {lff}")
    for r in result.get("reasons", []):
        lines.append(f"    - {r}")
    lines.append("  (ADVISORY triage only - NOT a faithfulness gate; nothing was dropped or aborted.)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _safe_print(text: str) -> None:
    """Print that can NEVER raise on a Windows cp1252 console when the text carries unicode (a real
    report body does). Falls back to an ascii-backslashreplace encode. Triage never crashes on I/O."""
    try:
        print(text)
    except Exception:  # noqa: BLE001
        try:
            enc = (getattr(sys.stdout, "encoding", None) or "utf-8")
            sys.stdout.write(text.encode(enc, errors="backslashreplace").decode(enc, errors="replace") + "\n")
        except Exception:  # noqa: BLE001 — last resort: swallow, never propagate from a triage tool
            pass


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


def _build_thresholds(args: argparse.Namespace) -> Thresholds:
    return Thresholds(
        fallback_rate_max=args.fallback_rate_max
        if args.fallback_rate_max is not None else _env_float(_ENV_FALLBACK_RATE_MAX, _DEFAULT_FALLBACK_RATE_MAX),
        min_prose_section_frac=args.min_prose_section_frac
        if args.min_prose_section_frac is not None else _env_float(_ENV_MIN_PROSE_SECTION_FRAC, _DEFAULT_MIN_PROSE_SECTION_FRAC),
        min_analytical_units=args.min_analytical_units
        if args.min_analytical_units is not None else _env_int(_ENV_MIN_ANALYTICAL_UNITS, _DEFAULT_MIN_ANALYTICAL_UNITS),
        chrome_max=args.chrome_max
        if args.chrome_max is not None else _env_int(_ENV_CHROME_MAX, _DEFAULT_CHROME_MAX),
        known_word_floor=args.known_word_floor
        if args.known_word_floor is not None else _env_int(_ENV_KNOWN_WORD_FLOOR, _DEFAULT_KNOWN_WORD_FLOOR),
    )


def _load_manifest(path: Path | None, report_dir: Path | None) -> dict | None:
    candidate = path
    if candidate is None and report_dir is not None:
        maybe = report_dir / "manifest.json"
        candidate = maybe if maybe.is_file() else None
    if candidate is None or not Path(candidate).is_file():
        return None
    try:
        data = json.loads(Path(candidate).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001 — malformed manifest => treated as absent, never a raise
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="I-deepfix-001 Wave 2e rendered-report ACCEPTANCE HARNESS (triage, never a gate)."
    )
    parser.add_argument("--report", type=Path, default=None,
                        help="rendered report.md to read (manifest/evidence_pool resolved from its dir)")
    parser.add_argument("--manifest", type=Path, default=None,
                        help="optional manifest.json (defaults to <report_dir>/manifest.json if present)")
    parser.add_argument("--json-out", type=Path, default=None, help="optional path to write the JSON result")
    parser.add_argument("--fallback-rate-max", type=float, default=None)
    parser.add_argument("--min-prose-section-frac", type=float, default=None)
    parser.add_argument("--min-analytical-units", type=int, default=None)
    parser.add_argument("--chrome-max", type=int, default=None)
    parser.add_argument("--known-word-floor", type=int, default=None)
    args = parser.parse_args(argv)

    th = _build_thresholds(args)

    report_text = ""
    report_dir: Path | None = None
    if args.report is not None:
        rp = Path(args.report)
        if rp.is_file():
            try:
                report_text = rp.read_text(encoding="utf-8")
            except Exception as exc:  # noqa: BLE001 — never raise on a bad read
                print(f"[wave2e] WARNING: could not read report {rp}: {exc}", file=sys.stderr)
            report_dir = rp.resolve().parent
        else:
            print(f"[wave2e] WARNING: report not found at {rp} — emitting input_present=false result",
                  file=sys.stderr)
    else:
        print("[wave2e] no --report given — emitting empty-input result", file=sys.stderr)

    manifest = _load_manifest(args.manifest, report_dir)
    result = analyze_report(report_text, manifest=manifest, snapshot_dir=report_dir, thresholds=th)

    _safe_print(json.dumps(result, ensure_ascii=False, indent=2))
    _safe_print("")
    _safe_print(format_summary(result, th))

    if args.json_out is not None:
        try:
            Path(args.json_out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"\n[wave2e] wrote JSON result -> {args.json_out}", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001
            print(f"[wave2e] WARNING: could not write --json-out {args.json_out}: {exc}", file=sys.stderr)

    # ACCEPTANCE CHECK / TRIAGE, never a gate: always exit 0 on content (argparse handles --help).
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
