"""I-perm-024 (#1216) — beat-both scorer metric extension (claim-by-claim only).

Five extended metrics for the DR head-to-head, computed STRICTLY from the
already-audited per-claim ledger (``ClaimRow``s — each a reconciled VERIFIED/
PARTIAL/UNSUPPORTED/FABRICATED/UNREACHABLE verdict against the FETCHED cited span)
and the FROZEN gold rubric (``RubricElement``s whose ``covered`` /
``citation_supported`` flags were set by the SAME dual §-1.1 audit).

§-1.1 STRUCTURAL GUARANTEE (the load-bearing safety property): every function here
accepts ONLY ``ClaimRow`` / ``RubricElement`` typed inputs. None of them receives or
opens raw report text. So they CANNOT do string-presence / pattern-presence matching
("does the report mention 'tirzepatide'?") — that is structurally impossible, not a
convention. Each metric is a roll-up over the per-claim audit LEDGER, never over raw
text. This is what keeps ``required_entity_recall`` / ``diversity_score`` off the
§-1.1 BANNED list (word/citation/source COUNTS as quality, pattern-presence,
string-presence PASS/FAIL — "lethal in clinical").

The metrics:
  1. ``faithfulness_precision`` = VERIFIED / material(S0-S2).
  2. ``citation_support_rate`` = VERIFIED-with-a-RESOLVED-citation / material.
  3. ``required_entity_recall`` = covered+citation_supported frozen rubric elements
     / total (the existing ``lane2_coverage`` semantics, surfaced as recall).
  4. ``safety_floor_recall`` = #3 restricted to the PRE-REGISTERED safety element
     subset (``safety_floor_elements_v3.json``, pinned to the rubric sha).
  5. ``diversity_score`` = distinct resolved sources among VERIFIED claims / VERIFIED
     count — DIAGNOSTIC ONLY (support-concentration), NOT a superiority signal.

Claimify-style dedup (``claim_dedup``) collapses near-duplicate claim atoms BEFORE
#1/#2/#5 so a verbose report cannot inflate by restating one easy fact. Applied
identically to every system.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src.polaris_graph.benchmark.claim_audit_scorer import ClaimRow, RubricElement
from src.polaris_graph.benchmark.claim_dedup import dedup_claims

_MATERIAL_SEVERITIES = ("S0", "S1", "S2")

# Default location of the pre-registered safety-floor element registry. Lives under
# tracked config/ (NOT runtime outputs/, which is gitignored) — it is hand-authored
# pre-registration, committed, not a regenerated artifact.
_SAFETY_FLOOR_REGISTRY = (
    Path(__file__).resolve().parents[3]
    / "config" / "dr_benchmark" / "safety_floor_elements_v3.json"
)

_DIVERSITY_NOTE = (
    "diversity_score is a support-concentration DIAGNOSTIC (distinct sources among "
    "VERIFIED claims / VERIFIED count), NOT a superiority signal; a higher value is "
    "NOT a §-1.1 'win' (unique-source counts are banned as quality signals)."
)


@dataclass(frozen=True)
class ScoredClaim:
    """One audited claim paired with its prose text (text is used ONLY for dedup —
    never for verdict assignment, which already happened upstream)."""
    text: str
    row: ClaimRow


def _is_material(row: ClaimRow) -> bool:
    return row.severity in _MATERIAL_SEVERITIES


def _has_resolved_citation(row: ClaimRow) -> bool:
    """A claim is citation-supported only if it carries a non-empty resolved
    citation id (an unresolved / None citation does NOT count — traceability floor)."""
    return bool(row.citation_id)


def faithfulness_precision(rows: list[ClaimRow]) -> dict:
    material = [r for r in rows if _is_material(r)]
    denom = len(material)
    verified = sum(1 for r in material if r.verdict == "VERIFIED")
    return {
        "material_atoms": denom,
        "verified": verified,
        "value": (verified / denom) if denom else None,
    }


def citation_support_rate(rows: list[ClaimRow]) -> dict:
    material = [r for r in rows if _is_material(r)]
    denom = len(material)
    supported = sum(
        1 for r in material if r.verdict == "VERIFIED" and _has_resolved_citation(r)
    )
    return {
        "material_atoms": denom,
        "verified_and_cited": supported,
        "value": (supported / denom) if denom else None,
    }


def diversity_score(rows: list[ClaimRow]) -> dict:
    verified = [r for r in rows if r.verdict == "VERIFIED"]
    denom = len(verified)
    distinct_sources = {r.citation_id for r in verified if r.citation_id}
    return {
        "verified_claims": denom,
        "distinct_sources": len(distinct_sources),
        "value": (len(distinct_sources) / denom) if denom else None,
        "note": _DIVERSITY_NOTE,
    }


def required_entity_recall(rubric: list[RubricElement] | None) -> dict:
    if not rubric:
        return {"total_required": 0, "covered_supported": 0, "value": None,
                "pending": True}
    total = len(rubric)
    covered_supported = sum(1 for e in rubric if e.covered and e.citation_supported)
    return {
        "total_required": total,
        "covered_supported": covered_supported,
        "value": (covered_supported / total) if total else None,
        "missing": [e.element_id for e in rubric
                    if not (e.covered and e.citation_supported)],
        "pending": False,
    }


def safety_floor_recall(
    rubric: list[RubricElement] | None, safety_element_ids: set[str] | None,
) -> dict:
    if not rubric or not safety_element_ids:
        return {"total_safety_required": 0, "covered_supported": 0, "value": None,
                "pending": True}
    # Denominator = the PRE-REGISTERED tagged count, NOT the count present in the
    # supplied rubric (Codex diff-gate iter-1 P2): a tagged id missing from the rubric
    # must SURFACE + count AGAINST recall (fail-safe), never silently shrink the
    # denominator into a falsely-high recall.
    rubric_by_id = {e.element_id: e for e in rubric}
    total = len(safety_element_ids)
    covered_supported = 0
    missing: list[str] = []
    missing_from_rubric: list[str] = []
    for eid in sorted(safety_element_ids):
        e = rubric_by_id.get(eid)
        if e is None:
            missing_from_rubric.append(eid)
            missing.append(eid)
            continue
        if e.covered and e.citation_supported:
            covered_supported += 1
        else:
            missing.append(eid)
    return {
        "total_safety_required": total,
        "covered_supported": covered_supported,
        "value": (covered_supported / total) if total else None,
        "missing": missing,
        "missing_from_rubric": missing_from_rubric,
        "pending": False,
    }


def load_safety_floor_element_ids(
    question_id: str, *, registry_path: Path | None = None,
) -> set[str]:
    """Read the pre-registered safety-floor element ids for one question from
    ``safety_floor_elements_v3.json`` (transparent tagging of the frozen rubric;
    NOT invented claims). Missing file / question → empty set (safety_floor_recall
    then reports pending, never a false 0)."""
    path = registry_path or _SAFETY_FLOOR_REGISTRY
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    qmap = data.get("questions", {})
    entry = qmap.get(str(question_id)) or qmap.get(f"Q{question_id}")
    if not entry:
        return set()
    return {str(eid) for eid in entry.get("safety_floor_element_ids", [])}


def _verdict_aware_keep(
    scored_claims: list[ScoredClaim], groups: list[list[int]],
) -> tuple[list[ClaimRow], int]:
    """Collapse ONLY repeated VERIFIED claims; keep EVERY non-VERIFIED claim
    (Codex brief-gate iter-1 P2: a dedup must never hide a bad verdict — if a
    cluster mixes a VERIFIED restatement with an UNSUPPORTED/FABRICATED/PARTIAL/
    UNREACHABLE near-duplicate, the bad verdict survives uncollapsed).

    Within each text cluster: keep the FIRST VERIFIED row (collapsing the rest of
    the VERIFIED restatements to one verified unit) PLUS every non-VERIFIED row
    untouched. Returns (kept_rows, n_verified_collapsed)."""
    kept: list[ClaimRow] = []
    n_verified_collapsed = 0
    for cluster in groups:
        rows_in = [scored_claims[i].row for i in cluster]
        verified = [r for r in rows_in if r.verdict == "VERIFIED"]
        non_verified = [r for r in rows_in if r.verdict != "VERIFIED"]
        if verified:
            # Deterministic, disclosed representative choice (Codex brief-gate iter-2
            # P2): when VERIFIED duplicates have mixed citation resolution, keep the
            # FIRST one carrying a RESOLVED citation so citation_support_rate reflects
            # the best-supported instance; else keep the first VERIFIED. Stable by
            # original cluster order.
            rep = next((r for r in verified if r.citation_id), verified[0])
            kept.append(rep)
            n_verified_collapsed += len(verified) - 1
        kept.extend(non_verified)
    return kept, n_verified_collapsed


def compute_extended_metrics(
    scored_claims: list[ScoredClaim],
    *,
    rubric: list[RubricElement] | None = None,
    safety_element_ids: set[str] | None = None,
    min_jaccard: float = 0.80,
) -> dict:
    """The 5 metrics for ONE (system × question). Dedups REPEATED VERIFIED claim
    atoms first (anti-inflation, never hiding a bad verdict), then rolls up over the
    kept ClaimRows + the audited frozen rubric. Pure aggregation — assigns no
    verdicts, touches no gate.

    ``scored_claims`` is a list of ``ScoredClaim(text, row)`` — a typed AUDITED
    carrier (the claim's prose text paired with its already-reconciled ``ClaimRow``).
    The text is used ONLY for the Claimify dedup; every metric value is derived from
    the ``ClaimRow`` verdicts + the rubric, never from the text (the §-1.1 guard)."""
    texts = [sc.text for sc in scored_claims]
    dedup = dedup_claims(texts, min_jaccard=min_jaccard)
    kept_rows, n_verified_collapsed = _verdict_aware_keep(scored_claims, dedup.groups)

    return {
        "n_raw_claims": len(scored_claims),
        "n_kept_claims": len(kept_rows),
        "dedup": {
            "n_text_clusters_collapsed": dedup.n_collapsed,
            "n_verified_collapsed": n_verified_collapsed,
            "collapsed_groups": dedup.collapsed_groups(),
            "min_jaccard": min_jaccard,
            "policy": "collapse repeated VERIFIED only; every non-VERIFIED claim kept "
                      "(a bad verdict is never hidden by a VERIFIED near-duplicate).",
        },
        "faithfulness_precision": faithfulness_precision(kept_rows),
        "citation_support_rate": citation_support_rate(kept_rows),
        "diversity_score": diversity_score(kept_rows),
        "required_entity_recall": required_entity_recall(rubric),
        "safety_floor_recall": safety_floor_recall(rubric, safety_element_ids),
        "methodology_note": (
            "all metrics derived from the per-claim audit ledger (VERIFIED verdicts "
            "vs FETCHED cited spans) + the frozen gold rubric; NEVER from raw report "
            "text; dedup applied identically to every system; NOT a superiority claim."
        ),
    }
