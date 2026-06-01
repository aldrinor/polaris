"""I-meta-006 (#1006) — benchmark scorecard run-wiring (cash-free orchestrator).

Ties Extract -> FACT-score -> scorecard for the 5 locked questions across POLARIS
+ the stored competitor reports. The ``span_fetcher`` + ``judge`` (the only billed
work) are INJECTED — the operator-gated paid run supplies the real fetcher + the
Claude+Codex reconciled-audit adapter; this module + its smoke run with fakes, so
the orchestration is spend-free-testable and the paid run is one call away.

Inputs:
  - POLARIS: a completed run dir with ``report.md`` + ``bibliography.json``.
  - ChatGPT / Gemini: stored markdown under
    ``outputs/dr_benchmark/external_outputs/<system>/Q##_*.md``.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable

from src.polaris_graph.benchmark.benchmark_scorecard import build_scorecard
from src.polaris_graph.benchmark.fact_scorer import Judge, SpanFetcher, score_atoms
from src.polaris_graph.benchmark.report_claim_extractor import extract_atoms

# References / Sources / Bibliography header — bare, ## heading, or **bold**
# (Codex diff-gate P2-1: a plain "References" line must also split).
_REFERENCES_HEADER_RE = re.compile(
    r"^\s*(?:#{1,4}\s*)?(?:\*\*)?"
    r"(references|sources|bibliography|works cited|citations)"
    r"(?:\*\*)?\s*:?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
# a numbered reference line "12. Author ... https://url"
_NUMBERED_REF_RE = re.compile(r"^\s*\[?(\d{1,3})[\].]\s+(.*)$")
_URL_RE = re.compile(r"https?://\S+")


def _looks_like_reference_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if _URL_RE.search(s):
        return True
    if re.match(r"^\[?\d{1,3}[\].]\s", s):
        return True
    # "Author, 2015 ..." / "Acemoglu & Restrepo (2018) ..."
    if re.match(r"^[A-Z][A-Za-z.\-]+[,&\s].*\(?(?:19|20)\d{2}", s):
        return True
    return False


def split_body_and_references(report_text: str) -> tuple[str, str]:
    """Split a report into (body, references_section). Claims are extracted from
    the BODY only.

    Codex diff-gate P1: strip ONLY a TERMINAL, reference-list-like section, never a
    mid-report ``## Sources`` or a header followed by answer prose — silently
    dropping prose claims would let a report ESCAPE the denominator. Uses the LAST
    matching header and strips only when the trailing block is mostly reference
    lines; otherwise FAILS SAFE toward inclusion (over-including a few reference
    lines as uncited atoms is a minor lane1 distortion, NOT a denominator bypass).
    """
    matches = list(_REFERENCES_HEADER_RE.finditer(report_text))
    if not matches:
        return report_text, ""
    m = matches[-1]
    after = report_text[m.end():]
    nonempty = [ln for ln in after.splitlines() if ln.strip()]
    if not nonempty:
        return report_text[: m.start()], after
    ref_like = sum(1 for ln in nonempty if _looks_like_reference_line(ln))
    if ref_like / len(nonempty) >= 0.6:
        return report_text[: m.start()], after
    # substantial prose after the (last) header → do NOT strip (fail-safe).
    return report_text, ""


def parse_references(report_text: str) -> dict[str, str]:
    """Best-effort key→source map from a report's References section. Maps both a
    numbered key ("12") and any author-year-ish leading token to the first URL on
    the line (or the line text when no URL). Unresolved citations downstream
    correctly become UNREACHABLE(source_missing) — this parser never fabricates."""
    m = _REFERENCES_HEADER_RE.search(report_text)
    refs: dict[str, str] = {}
    if not m:
        return refs
    for line in report_text[m.end():].splitlines():
        line = line.strip()
        if not line:
            continue
        url_m = _URL_RE.search(line)
        resolved = url_m.group(0) if url_m else line[:300]
        num_m = _NUMBERED_REF_RE.match(line)
        if num_m:
            refs[num_m.group(1)] = resolved
        # also index by a normalized "Author, Year" leading fragment if present
        ay = re.match(r"[\[\d.\s]*([A-Z][A-Za-z]+(?:[^,]*,\s*(?:19|20)\d{2}))", line)
        if ay:
            key = re.sub(r"\s+", " ", ay.group(1).strip().lower())
            refs.setdefault(key, resolved)
    return refs


def _polaris_references(run_dir: Path) -> dict[str, str]:
    biblio_path = run_dir / "bibliography.json"
    if not biblio_path.exists():
        return {}
    try:
        data = json.loads(biblio_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    refs: dict[str, str] = {}
    entries = data if isinstance(data, list) else data.get("entries", [])
    for e in entries:
        if isinstance(e, dict) and e.get("num") is not None:
            refs[str(e["num"])] = e.get("url") or e.get("evidence_id") or ""
    return refs


def run_scorecard(
    *,
    polaris_run_dir: str | Path | None,
    external_root: str | Path,
    span_fetcher: SpanFetcher,
    judge: Judge,
    atomizer: Callable[[str], list[str]] | None = None,
    rubrics=None,
) -> dict:
    """Extract -> FACT-score -> scorecard across all systems for the 5 locked Qs.

    Returns the scorecard dict (lane1 + lane2_pending). The injected ``span_fetcher``
    + ``judge`` are the only billed work."""
    rows_by_system_qid: dict[tuple[str, str], list] = {}

    def _ingest(system: str, report_text: str, references: dict[str, str], qid: str):
        # Extract claims from the BODY only — the References/Bibliography list is
        # not prose claims and must not be scored as uncited atoms.
        body, _ = split_body_and_references(report_text)
        atoms = extract_atoms(body, system, references,
                              atomizer=atomizer, question_id=qid)
        rows = score_atoms(atoms, span_fetcher=span_fetcher, judge=judge)
        rows_by_system_qid[(system, qid)] = rows

    external_root = Path(external_root)
    for system_dir, system in (("gpt_5_5_pro", "chatgpt"), ("gemini_3_1_pro", "gemini")):
        d = external_root / system_dir
        if not d.is_dir():
            continue
        for md in sorted(d.glob("Q*.md")):
            qid = re.match(r"Q(\d+)", md.name)
            if not qid:
                continue
            text = md.read_text(encoding="utf-8", errors="replace")
            _ingest(system, text, parse_references(text), qid.group(1))

    if polaris_run_dir:
        run_dir = Path(polaris_run_dir)
        report = run_dir / "report.md"
        if report.exists():
            text = report.read_text(encoding="utf-8", errors="replace")
            qid_m = re.search(r"Q(\d+)", run_dir.name) or re.search(r"(\d+)", run_dir.name)
            qid = qid_m.group(1) if qid_m else "0"
            _ingest("polaris", text, _polaris_references(run_dir), qid)

    return build_scorecard(rows_by_system_qid, rubrics=rubrics)
