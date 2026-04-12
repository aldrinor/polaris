"""
Mesh artifact directives — FIX S7 validation + rendering.

Post-processes composed answer text to find artifact directive blocks
and render them. Every block is VALIDATED before rendering: claim_ids
must exist, data must be extractable. Invalid blocks are stripped with
an inline stub message and a warning logged.

v1 design (CP-A lock):

  - TABLE: inline markdown table from claims with numeric data.
    No external dependencies.
  - CHART, FLOW, DECK, FLASHCARDS: stub entries that return a
    "deferred" message. FIX S7 validation still runs (claim_id
    existence check) but rendering is a no-op.

Directive syntax (from design doc §9):
  [TABLE:col1,col2,col3]{claim_ids=clm_a,clm_b,clm_c}
  [CHART:line]{claim_ids=clm_a,clm_b;x_label=Year;y_label=Removal %}
  [FLOW:process]{claim_ids=clm_a,clm_b}
  [DECK:title]{claim_ids=clm_a,clm_b,clm_c}
  [FLASHCARDS:topic]{claim_ids=clm_a,clm_b}
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

ARTIFACT_PATTERN = re.compile(
    r"\[(TABLE|CHART|FLOW|DECK|FLASHCARDS):([^\]]+)\]\{([^}]*)\}",
    re.DOTALL,
)

MIN_TABLE_ROWS = 2


def render_artifacts(
    answer_text: str,
    claims_by_id: dict[str, dict],
) -> tuple[str, list[str]]:
    """
    Find artifact directives in the answer text, validate them (FIX S7),
    and render or strip them.

    Returns (final_text, artifact_file_paths).
    """
    artifacts: list[str] = []

    def _replace(match: re.Match) -> str:
        kind = match.group(1)
        spec = match.group(2)
        raw_payload = match.group(3)

        payload = _parse_payload(raw_payload)
        cids = payload.get("claim_ids", [])

        # ── FIX S7: validate claim_ids exist ──
        missing = [c for c in cids if c not in claims_by_id]
        if missing:
            logger.warning(
                "Stripped [%s] block: missing claims %s", kind, missing,
            )
            return f"_(artifact stripped: {kind} — missing claim references)_"

        if kind == "TABLE":
            return _render_table(spec, cids, claims_by_id)
        if kind in ("CHART", "FLOW", "DECK", "FLASHCARDS"):
            return f"_(artifact deferred: {kind})_"

        return f"_(unknown artifact: {kind})_"

    final_text = ARTIFACT_PATTERN.sub(_replace, answer_text)
    return final_text, artifacts


def _parse_payload(raw: str) -> dict:
    """Parse 'claim_ids=a,b,c;x_label=Year' → dict."""
    result: dict = {}
    for part in raw.split(";"):
        part = part.strip()
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key == "claim_ids":
            result[key] = [v.strip() for v in value.split(",") if v.strip()]
        else:
            result[key] = value
    return result


def _render_table(
    spec: str,
    cids: list[str],
    claims_by_id: dict[str, dict],
) -> str:
    """
    Render a markdown table from claims.

    Spec format: "col1,col2,col3" — column headers.
    Each claim contributes one row. Data is extracted from the claim's
    statement + direct_quote.
    """
    columns = [c.strip() for c in spec.split(",") if c.strip()]
    if not columns:
        logger.warning("Stripped [TABLE]: no columns specified")
        return "_(table stripped: no columns)_"

    rows: list[list[str]] = []
    for cid in cids:
        claim = claims_by_id.get(cid)
        if claim is None:
            continue
        row = _extract_row(claim, columns)
        if row:
            rows.append(row)

    if len(rows) < MIN_TABLE_ROWS:
        logger.warning(
            "Stripped [TABLE]: only %d valid rows (need %d)",
            len(rows), MIN_TABLE_ROWS,
        )
        return f"_(table stripped: insufficient data — {len(rows)} rows)_"

    # Build markdown table
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    body_lines = [
        "| " + " | ".join(row) + " |"
        for row in rows
    ]
    ref_note = "Sources: " + ", ".join(
        f"[{claims_by_id[cid].get('ref_num', '?')}]" for cid in cids
        if cid in claims_by_id
    )
    return "\n".join([header, separator] + body_lines + ["", ref_note])


def _extract_row(claim: dict, columns: list[str]) -> list[str] | None:
    """
    Extract a table row from a claim. Each column value is pulled from
    the claim's statement or direct_quote by looking for the column
    keyword. If any column can't be extracted, returns None.

    This is a best-effort heuristic — the LLM structured the directive
    so the claims should contain the data. If they don't, FIX S7 strips
    the row.
    """
    text = (claim.get("statement", "") + " " + claim.get("direct_quote", "")).lower()
    row: list[str] = []
    for col in columns:
        col_lower = col.lower()
        if col_lower in text:
            row.append(claim.get("statement", "")[:80])
        else:
            return None
    return row
