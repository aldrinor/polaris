"""feat/intake-contract (2026-07-15) — POST-WRITE structure/format CHECKER (Part 3).

NON-BLOCKING, observe+log ONLY. It compares the FINISHED report to a contract and
returns an adherence summary. It changes NOTHING in the report and touches NOTHING
in the faithfulness engine.

  * ``check_report_against_contract`` is a PURE function — no env reads, no network,
    no LLM, no import of any strict_verify / provenance / span engine. It only READS
    the report text, the bibliography, and a plain contract dict, and returns a dict.
  * ``build_floor_contract`` builds the checker's contract view from the PURE regex
    floor extractors (the *_regex variants are network-free and require NO flag), so
    the checker has a real contract to compare against without enabling any extractor.
  * ``postwrite_check_enabled`` gates the DRIVER hook. DEFAULT OFF. With the flag off
    the driver never calls the checker, adds no summary key, writes no sidecar, logs
    no line => byte-identical to today.

SAFETY (hard rules 1-3): the checker performs NO verification and adds NO 'verify
faithfulness' line. Source-rule and date-window adherence are HARD-CODED to status
'NOTED_NOT_ENFORCED' — they are observation only and must never become PASS/FAIL,
never feed enforcement, never touch the exit code. ``enforced`` is ALWAYS False.
"""
from __future__ import annotations

import os
import re
from typing import Any

CHECKER_VERSION = "s3-postwrite-1"

# Mirror intake_constraint_extractor._OFF_VALUES (the repo flag-parsing idiom).
_OFF_VALUES = frozenset({"0", "false", "no", "off", "disabled", ""})
_ENV_FLAG = "PG_POSTWRITE_STRUCTURE_CHECK"

# Level-2 headings only ('## Foo'); the title uses '# ' and the intro is unheaded
# prose, so parsing level-2 avoids polluting present_headings with the title/intro.
_H2_RE = re.compile(r"^##\s+(?!#)(.+?)\s*$", re.M)
# Own numeric-marker regex — deliberately SEPARATE from the faithfulness _CITE_RE so
# this checker never touches the faithfulness tripwire.
_MARKER_RE = re.compile(r"\[(\d+)\]")


def postwrite_check_enabled() -> bool:
    """DRIVER gate. DEFAULT OFF. Set PG_POSTWRITE_STRUCTURE_CHECK=1 to activate."""
    return os.getenv(_ENV_FLAG, "0").strip().lower() not in _OFF_VALUES


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _required_items(contract: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect required section/topic items from the contract's instruction slots +
    any explicit required_sections. Each item -> {label, entities}."""
    items: list[dict[str, Any]] = []
    for slot in (contract.get("instruction_slots") or contract.get("required_sections") or []):
        if not isinstance(slot, dict):
            continue
        ents = [str(e) for e in (slot.get("entities") or []) if str(e).strip()]
        label = (slot.get("text") or (ents[0] if ents else "")).strip()
        if ents or label:
            items.append({"label": label, "entities": ents})
    return items


def _length_band(contract: dict[str, Any]) -> tuple[int | None, int | None] | None:
    """Return an (min, max) word band from the contract length directive, or None."""
    band = contract.get("length")
    if isinstance(band, dict):
        lo = band.get("min")
        hi = band.get("max")
        if lo is None and hi is None:
            return None
        return (int(lo) if lo is not None else None, int(hi) if hi is not None else None)
    return None


def check_report_against_contract(
    report_text: str,
    contract: dict[str, Any],
    biblio: list[dict[str, Any]] | None,
    actual_words: int,
) -> dict[str, Any]:
    """Compare a finished report against a contract. PURE + observe-only.

    Returns the adherence summary dict (see module docstring / the scout OUTPUT
    SHAPE). ``enforced`` is ALWAYS False — the machine-readable proof this is
    observe-only. This function mutates none of its inputs.
    """
    report_text = report_text or ""
    biblio = list(biblio or [])
    contract_source = str(contract.get("contract_source") or "floor_regex")

    # --- 1) required sections ---
    present_headings = [h.strip() for h in _H2_RE.findall(report_text)]
    present_norm = [_norm(h) for h in present_headings]
    required = _required_items(contract)
    satisfied: list[str] = []
    missing: list[str] = []
    for item in required:
        terms = [item["label"]] + item["entities"] if item["label"] else item["entities"]
        terms_norm = [_norm(t) for t in terms if _norm(t)]
        # Covered if ANY required term appears within ANY level-2 heading (substring).
        covered = any(any(tn and tn in hn for hn in present_norm) for tn in terms_norm)
        label = item["label"] or ", ".join(item["entities"])
        (satisfied if covered else missing).append(label)
    if not required:
        sections_status = "N/A"
    elif not missing:
        sections_status = "PASS"
    elif satisfied:
        sections_status = "PARTIAL"
    else:
        sections_status = "MISSING"

    # --- 2) length ---
    band = _length_band(contract)
    if band is None:
        length_status = "UNSPECIFIED"
    else:
        lo, hi = band
        if lo is not None and actual_words < lo:
            length_status = "UNDER"
        elif hi is not None and actual_words > hi:
            length_status = "OVER"
        else:
            length_status = "PASS"

    # --- 3) citation style ---
    body = report_text.split("\n\n## References\n", 1)[0]
    observed_markers = len(set(int(m) for m in _MARKER_RE.findall(body)))
    has_references = "## References" in report_text
    required_citation = contract.get("citation_style")
    if not required_citation:
        citation_status = "UNSPECIFIED"
    elif observed_markers > 0 or has_references:
        citation_status = "PASS"
    else:
        citation_status = "MISMATCH"

    # --- 4) source-rule adherence: NOTED, NEVER enforced ---
    cited_total = len(biblio)
    journal_only = bool(contract.get("journal_only"))
    source_rule = "journal_only" if journal_only else (
        "scope_facets" if contract.get("source_rules") else None)
    apparent_matching = 0
    apparent_non_matching = 0
    if journal_only:
        for b in biblio:
            tier = str(b.get("tier") or "").upper()
            # Heuristic ONLY (never enforced): tiers commonly used for scholarly work.
            if tier in ("A", "T1", "TIER1", "1"):
                apparent_matching += 1
            else:
                apparent_non_matching += 1

    # --- date window: NOTED, NEVER enforced ---
    date_window = contract.get("date_window")

    items_checked = 0
    n_pass = n_partial = n_missing = n_noted = 0
    for status in (sections_status, length_status, citation_status):
        if status in ("N/A", "UNSPECIFIED"):
            continue
        items_checked += 1
        if status == "PASS":
            n_pass += 1
        elif status == "PARTIAL":
            n_partial += 1
        elif status in ("MISSING", "UNDER", "OVER", "MISMATCH"):
            n_missing += 1
    if source_rule:
        n_noted += 1
    if date_window:
        n_noted += 1

    return {
        "checker_version": CHECKER_VERSION,
        "enforced": False,  # ALWAYS — machine-readable proof this is observe-only.
        "contract_source": contract_source,
        "sections": {
            "required": [i["label"] or ", ".join(i["entities"]) for i in required],
            "present_headings": present_headings,
            "satisfied": satisfied,
            "missing": missing,
            "status": sections_status,
        },
        "length": {
            "required_band": list(band) if band else None,
            "actual_words": int(actual_words),
            "status": length_status,
        },
        "citation_style": {
            "required": required_citation,
            "observed_markers": observed_markers,
            "has_references_section": has_references,
            "status": citation_status,
        },
        "source_rules": {
            "rule": source_rule,
            "cited_total": cited_total,
            "apparent_matching": apparent_matching,
            "apparent_non_matching": apparent_non_matching,
            "status": "NOTED_NOT_ENFORCED",
        },
        "date_window": {
            "required": date_window,
            "status": "NOTED_NOT_ENFORCED",
        },
        "summary": {
            "items_checked": items_checked,
            "pass": n_pass,
            "partial": n_partial,
            "missing": n_missing,
            "noted": n_noted,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# contract view from the pure regex floor (network-free, cost-free, unflagged).
# ─────────────────────────────────────────────────────────────────────────────

_LEN_ABOUT_RE = re.compile(r"\b(?:about|approximately|around|roughly)\s+(\d{2,6})\s+words?\b", re.I)
_LEN_ATLEAST_RE = re.compile(r"\b(?:at\s+least|no\s+fewer\s+than|minimum\s+of)\s+(\d{2,6})\s+words?\b", re.I)
_LEN_ATMOST_RE = re.compile(r"\b(?:at\s+most|no\s+more\s+than|under|maximum\s+of|up\s+to)\s+(\d{2,6})\s+words?\b", re.I)


def _length_directive(rq: str) -> dict[str, int] | None:
    """A tolerant word band from an explicit length directive, else None.
    'about N' => +-15%; 'at least N' / 'no more than N' => one-sided."""
    m = _LEN_ABOUT_RE.search(rq or "")
    if m:
        n = int(m.group(1))
        return {"min": int(n * 0.85), "max": int(n * 1.15)}
    lo = _LEN_ATLEAST_RE.search(rq or "")
    hi = _LEN_ATMOST_RE.search(rq or "")
    band: dict[str, int] = {}
    if lo:
        band["min"] = int(lo.group(1))
    if hi:
        band["max"] = int(hi.group(1))
    return band or None


def build_floor_contract(rq: str) -> dict[str, Any]:
    """Build the checker's contract view from the PURE regex floor extractors.

    Calls the *_regex extractor variants directly (they are pure, network-free, and
    require NO flag), so the checker gets a real contract without enabling any
    extractor behavior. Returns a plain dict the pure checker consumes.
    """
    contract: dict[str, Any] = {"contract_source": "floor_regex"}
    try:
        from src.polaris_graph.retrieval.intake_constraint_extractor import (  # noqa: PLC0415
            extract_constraints_regex,
            extract_instruction_slots_regex,
            extract_scope_constraints_regex,
        )
    except Exception:  # noqa: BLE001 — fail-open: an empty contract => everything N/A
        return contract

    try:
        slots = extract_instruction_slots_regex(rq)
        contract["instruction_slots"] = [s.to_dict() for s in slots]
    except Exception:  # noqa: BLE001
        contract["instruction_slots"] = []

    try:
        uc = extract_constraints_regex(rq)
        contract["journal_only"] = bool(uc.journal_only)
        if uc.date_start_year is not None or uc.date_end_year is not None:
            contract["date_window"] = {
                "start_year": uc.date_start_year, "end_year": uc.date_end_year}
        if uc.language:
            contract["source_language"] = uc.language
    except Exception:  # noqa: BLE001
        pass

    try:
        sc = extract_scope_constraints_regex(rq)
        if not sc.is_empty():
            contract["source_rules"] = [f.to_dict() for f in sc.facets]
    except Exception:  # noqa: BLE001
        pass

    length = _length_directive(rq)
    if length:
        contract["length"] = length
    # The champion always emits [N] markers + a References section, so a numeric
    # citation style is the report's native contract.
    contract["citation_style"] = "numeric"
    return contract
