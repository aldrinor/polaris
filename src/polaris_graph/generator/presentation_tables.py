"""Deterministic verified-number COMPARISON TABLE renderer (I-deepfix-001 Wave-2c, #1344).

Some research prompts (and the DRB-II "Presentation" rubric explicitly) reward presenting a
like-with-like numeric comparison in TABLE form — the rubric example is "presented the change
in gold prices in table form": the same measure and unit, with values across entities or
time-points. The multi-section generator emits span-verified narrative prose but does not lay
out such a comparison table, so the presentation dimension loses a directly-scored point.

This module renders that table WITHOUT any LLM / network / IO, purely from ALREADY-VERIFIED
numeric claims. It is presentation-only and therefore faithfulness-NEUTRAL (CLAUDE.md §-1.3: a
table is a presentation of already-verified findings, not a new claim). The contract:

* Consumes ONLY already-verified numeric claims supplied by the caller. It performs NO
  verification and NEVER re-verifies — it does not touch strict_verify / NLI / 4-role D8 /
  provenance / span-grounding.
* Numbers are copied VERBATIM from the verified claim (never recomputed, never rounded, never
  reformatted). No arithmetic is performed on any value.
* Each value keeps its citation marker (``[N]`` / ``[#ev:...]``) verbatim, rendered in the
  Citation column of its own row.
* A table is emitted ONLY when >= 2 comparable claims share a (measure, unit) — otherwise the
  module returns empty (no single-row filler, no invented comparison).

Gated behind the default-OFF kill-switch ``PG_PRESENTATION_TABLES`` (LAW VI). OFF => the public
entry returns a no-op (``changed=False``, ``text=""``) so a future caller that only inserts
``result.text`` when ``result.changed`` is byte-identical to today. This build is MODULE ONLY:
no caller is wired to it yet (that is a separate Batch-2 ``2c-wiring`` step).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Iterable

# --- canary / markers -------------------------------------------------------
CANARY_TAG = "[presentation_tables]"
# Distinctive idempotency marker embedded once per rendered table (HTML comment, invisible in a
# markdown viewer). A resume / re-finalize that re-reads a report already carrying this marker is
# a no-op at the public entry.
TABLE_MARKER = "<!-- polaris:presentation_table -->"

# --- env kill-switch (default OFF; LAW VI) ----------------------------------
_ENABLE_FLAG = "PG_PRESENTATION_TABLES"
_OFF_VALUES = frozenset({"0", "false", "off", "no", ""})

# --- comparability gate -----------------------------------------------------
# A table is emitted only when at least this many comparable claims share a (measure, unit).
_MIN_COMPARABLE = 2

# --- disclosed-gap marker ---------------------------------------------------
GAP_CELL = "—"

# --- rendering --------------------------------------------------------------
_ENTITY_HEADER_DEFAULT = "Entity"
_WS_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class VerifiedNumericClaim:
    """One ALREADY-VERIFIED numeric claim for a facet.

    ``value`` is a VERBATIM string (or the caller may pass a list which is joined verbatim by
    :func:`_value_str`); it is never parsed to a number, so no rounding/reformatting can occur.
    ``citation`` is the verbatim citation marker (e.g. ``[3]`` or a ``[#ev:...]`` token).
    """

    entity: str
    measure: str
    value: str
    unit: str = ""
    time_window: str = ""
    citation: str = ""


@dataclass
class PresentationTablesResult:
    """Output of the presentation-tables pass: the (possibly) rewritten text and its counts.

    ``changed`` says whether any table was inserted; ``tables``/``rows`` count
    what was emitted and ``canary`` carries the marker used to assert the pass
    fired in output.
    """

    text: str
    changed: bool
    tables: int = 0
    rows: int = 0
    canary: str = ""


# ---------------------------------------------------------------------------
# Enablement
# ---------------------------------------------------------------------------
def presentation_tables_enabled() -> bool:
    """LAW VI kill-switch (default OFF). OFF => the public entry is a no-op."""
    return os.environ.get(_ENABLE_FLAG, "0").strip().lower() not in _OFF_VALUES


# ---------------------------------------------------------------------------
# Input coercion
# ---------------------------------------------------------------------------
def _get(obj: Any, name: str, default: Any = "") -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _first_nonempty(obj: Any, names: tuple[str, ...]) -> str:
    """First non-empty stripped string among ``names`` on ``obj`` (dict or attr). PURE."""
    for name in names:
        val = _get(obj, name, "")
        if val is None:
            continue
        text = str(val).strip()
        if text:
            return text
    return ""


def _value_str(value: Any) -> str:
    """VERBATIM rendering of a value. A str/scalar is returned stripped and OTHERWISE unchanged
    (no float parse => no rounding/reformatting); a list/tuple is joined with "; " keeping each
    token verbatim. Empty tokens are dropped. PURE."""
    if isinstance(value, (list, tuple)):
        return "; ".join(str(v).strip() for v in value if str(v).strip())
    if value is None:
        return ""
    return str(value).strip()


def _coerce_claim(obj: Any) -> VerifiedNumericClaim | None:
    """Duck-type ``obj`` (a ``VerifiedNumericClaim``, a dict, or an object) into a
    ``VerifiedNumericClaim``. Field fallbacks match the pipeline's ``ExtractedNumericClaim``
    (subject/predicate/value/unit) so a future wiring step can feed real claims unchanged. A
    claim missing entity, measure, or value is dropped (no partial-field row invented). PURE."""
    if obj is None:
        return None
    entity = _first_nonempty(obj, ("entity", "subject"))
    measure = _first_nonempty(obj, ("measure", "predicate", "endpoint_phrase"))
    value = _value_str(_get(obj, "value", ""))
    if not (entity and measure and value):
        return None
    unit = _first_nonempty(obj, ("unit",))
    time_window = _first_nonempty(obj, ("time_window", "window"))
    citation = _first_nonempty(obj, ("citation", "cite", "marker"))
    return VerifiedNumericClaim(
        entity=entity,
        measure=measure,
        value=value,
        unit=unit,
        time_window=time_window,
        citation=citation,
    )


# ---------------------------------------------------------------------------
# Grouping (comparability)
# ---------------------------------------------------------------------------
def _comparability_key(claim: VerifiedNumericClaim) -> tuple[str, str]:
    """(measure, unit) normalized for GROUPING ONLY (lowercased, whitespace-collapsed). The
    rendered labels remain the verbatim surface forms. PURE."""
    measure = _WS_RE.sub(" ", claim.measure.strip().lower())
    unit = _WS_RE.sub(" ", claim.unit.strip().lower())
    return (measure, unit)


def group_comparable_claims(
    claims: Iterable[VerifiedNumericClaim],
) -> dict[tuple[str, str], list[VerifiedNumericClaim]]:
    """Group already-coerced claims by comparability key, keeping ONLY groups with
    ``>= _MIN_COMPARABLE`` members (no single-row filler). Returned dict is ordered
    deterministically by (measure, unit) key so multiple tables emit in a stable order. PURE."""
    buckets: dict[tuple[str, str], list[VerifiedNumericClaim]] = {}
    for claim in claims:
        buckets.setdefault(_comparability_key(claim), []).append(claim)
    qualifying = {k: v for k, v in buckets.items() if len(v) >= _MIN_COMPARABLE}
    return {k: qualifying[k] for k in sorted(qualifying)}


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------
def _escape_cell(text: str) -> str:
    """Newline-flatten + pipe-escape a markdown cell. PURE."""
    return (text or "").replace("\n", " ").replace("|", "\\|").strip()


def _entity_cell(claim: VerifiedNumericClaim) -> str:
    """Row identity cell: the entity, with a verbatim time-window appended when present (both
    strings come from the verified claim). PURE."""
    if claim.time_window:
        return f"{claim.entity} ({claim.time_window})"
    return claim.entity


def render_comparison_table(
    claims: list[VerifiedNumericClaim],
    *,
    facet_label: str = "",
    entity_header: str = _ENTITY_HEADER_DEFAULT,
) -> str:
    """Render one GFM comparison table for a group of comparable verified claims.

    Rows are sorted by (entity, measure, time_window, value) so the ordering is FULLY
    input-order-independent — the flagship same-entity/same-measure case (one entity, several
    time-points) is disambiguated by time_window/value rather than falling back to input order.
    Every value/citation is copied VERBATIM. The measure/unit labels use the first row's surface
    form (all rows in a group share the normalized measure/unit). Returns "" for an empty group
    (documented building block; never IndexErrors). PURE."""
    if not claims:
        return ""
    rows = sorted(
        claims,
        key=lambda c: (
            c.entity.strip().lower(),
            c.measure.strip().lower(),
            c.time_window.strip().lower(),
            c.value.strip().lower(),
        ),
    )
    measure_label = rows[0].measure.strip()
    headers = [entity_header, "Measure", "Value", "Unit", "Citation"]

    title_bits = [b for b in (facet_label.strip() if facet_label else "", measure_label) if b]
    title = " — ".join(title_bits) if title_bits else (measure_label or "Comparison")

    lines: list[str] = []
    lines.append(f"### {title}")
    lines.append("")
    lines.append(TABLE_MARKER)
    lines.append(
        "_Values are quoted verbatim from cited sources; a — marks a field the cited source "
        "did not provide._"
    )
    lines.append("")
    lines.append("| " + " | ".join(_escape_cell(h) for h in headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for claim in rows:
        cells = [
            _escape_cell(_entity_cell(claim)) or GAP_CELL,
            _escape_cell(claim.measure) or GAP_CELL,
            _escape_cell(claim.value) or GAP_CELL,
            _escape_cell(claim.unit) or GAP_CELL,
            _escape_cell(claim.citation) or GAP_CELL,
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public entry (flag-gated)
# ---------------------------------------------------------------------------
def render_presentation_tables(
    *,
    claims: Iterable[Any],
    existing_report_md: str = "",
    facet_label: str = "",
    entity_header: str = _ENTITY_HEADER_DEFAULT,
) -> PresentationTablesResult:
    """Build the verified-number comparison table(s) for a facet's already-verified numeric
    claims, optionally appended to ``existing_report_md``.

    No-op (``changed=False``) when: the kill-switch is OFF, the report already carries the table
    marker (idempotent / resume-safe), or fewer than ``_MIN_COMPARABLE`` claims share any
    (measure, unit). Otherwise returns the concatenated table(s) (one per qualifying comparability
    group). PURE apart from reading the env kill-switch.

    Wiring-time contract a caller MUST respect:

    * Insert ONLY when ``result.changed`` is True; never assume ``result.text`` is the tables.
      The ``text`` semantics differ across the no-op paths: the OFF path returns ``text=""`` while
      the no-comparable / already-present paths return ``existing_report_md`` unchanged. Gating on
      ``changed`` keeps the OFF path byte-identical.
    * ``TABLE_MARKER`` idempotency is REPORT-GLOBAL: once ANY presentation table exists in the
      report, a later call for a DIFFERENT facet is a silent no-op (``already_present``). A
      multi-facet caller must therefore render ALL facets in ONE call (pass all claims together),
      not once per facet against the growing report."""
    if not presentation_tables_enabled():
        return PresentationTablesResult(text="", changed=False, canary="disabled")
    if existing_report_md and TABLE_MARKER in existing_report_md:
        return PresentationTablesResult(
            text=existing_report_md, changed=False, canary="already_present"
        )

    coerced = [c for c in (_coerce_claim(x) for x in (claims or [])) if c is not None]
    groups = group_comparable_claims(coerced)
    if not groups:
        empty = existing_report_md if existing_report_md else ""
        return PresentationTablesResult(text=empty, changed=False, canary="no_comparable_claims")

    blocks: list[str] = []
    total_rows = 0
    for grp in groups.values():
        blocks.append(
            render_comparison_table(grp, facet_label=facet_label, entity_header=entity_header)
        )
        total_rows += len(grp)
    tables_md = "\n\n".join(blocks)

    if existing_report_md:
        new_text = existing_report_md.rstrip() + "\n\n" + tables_md + "\n"
    else:
        new_text = tables_md

    canary = f"{CANARY_TAG} tables={len(groups)} rows={total_rows}"
    return PresentationTablesResult(
        text=new_text, changed=True, tables=len(groups), rows=total_rows, canary=canary
    )
