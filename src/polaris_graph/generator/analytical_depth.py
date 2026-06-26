"""Analytical-depth heuristic — single source of truth for Pipeline A + Pipeline B.

The depth heuristic (regex counts of comparison / aggregation / challenge markers, markdown tables, and
``**Key Findings**`` subsections, plus a per-section "deficient" flag and a ``passed`` threshold) was
historically inlined in ``synthesizer._evaluate_analytical_depth`` and drove the Pipeline-B RC-8 gate.
It is extracted here, byte-for-byte, so:

1. The benchmark (Pipeline A, ``run_honest_sweep_r3.run_one_query``) can import the heuristic **without**
   importing ``synthesizer`` (which pulls ``OpenRouterClient`` + tracer + schemas + state — heavy, with
   construction side-effects). This module is stdlib-only (``re`` + typing); zero new dependency, zero
   network, zero cost.
2. The two pipelines share one implementation and cannot drift. ``synthesizer._evaluate_analytical_depth``
   now delegates here, so RC-8 behavior is unchanged.

The benchmark uses ``evaluate_analytical_depth`` as an **ADVISORY, non-gating** annotation only (see
``run_honest_sweep_r3``). The ``passed`` boolean and ``deficient_sections`` list are computed over a
``split_report_into_sections`` view of the assembled report (split on ATX headers), which differs from
Pipeline B's semantic ``report_sections``: Bibliography / Methods / sub-headers each become their own
"section", so the benchmark ``passed`` / ``deficient_sections`` are an **advisory split read, NOT the
RC-8 gate verdict**. The benchmark NEVER gates on this signal.
"""

from __future__ import annotations

import os
import re
from typing import Any

# ATX markdown header: 1-6 '#' then whitespace then a title (e.g. "## Key Findings", "### Limitations").
_ATX_HEADER_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")

# I-wire-012 (#1326) depth fix — count the AGGREGATED ``## Key Findings`` ATX block + ``### <title>``
# synthesis headers, not only the per-section ``**Key Findings**`` bold form. Default-ON kill-switch
# ``PG_DEPTH_COUNT_ATX_KEY_FINDINGS``. A report that ships a ``## Key Findings`` block (or the
# ``## Analytical synthesis`` per-section headings) previously scored key_findings=0 here because the
# regex matched ONLY the bold form — the depth=0 the I-wire-012 acceptance flags. Broadening can ONLY
# RAISE the count, which makes the Pipeline-B RC-8 depth heuristic EASIER to pass (never a faithfulness
# relaxation — RC-8 is an advisory depth heuristic, not the faithfulness engine); =0 restores the exact
# pre-I-wire-012 count for byte-identical RC-8 parity.
_COUNT_ATX_KEY_FINDINGS_ENV = "PG_DEPTH_COUNT_ATX_KEY_FINDINGS"
_DEPTH_OFF_VALUES = frozenset({"0", "false", "no", "off", ""})


def _count_atx_key_findings_enabled() -> bool:
    """Default ON. ``PG_DEPTH_COUNT_ATX_KEY_FINDINGS=0`` restores the bold-only count (RC-8 parity)."""
    return os.getenv(_COUNT_ATX_KEY_FINDINGS_ENV, "1").strip().lower() not in _DEPTH_OFF_VALUES


def evaluate_analytical_depth(report_sections: list[dict]) -> dict:
    """RC-8: Evaluate analytical depth using regex-based heuristics.

    Checks for the 5 analytical operations across all sections.
    Returns: {"passed": bool, "scores": {...}, "deficient_sections": [...]}

    Body MOVED VERBATIM from ``synthesizer._evaluate_analytical_depth`` (same regex strings, same
    per-section ``ops_present`` logic, same thresholds, same return keys) — Pipeline-B RC-8 parity.

    NOTE (benchmark form): the ``key_findings`` regex matches the **bold** ``**Key Findings**``
    subsection form (the per-section form emitted by the synthesis prompt). The benchmark's *front*
    aggregated Key Findings block is emitted as an **ATX** header (``## Key Findings`` —
    ``generator/key_findings.py``), which this regex deliberately does NOT count. Per-section bold
    ``**Key Findings**`` subsections ARE counted. Kept verbatim rather than broadened so Pipeline-B
    RC-8 counts cannot shift; the benchmark consumes this advisory-only, so a conservative
    (undercounting, never inflating) key-findings tally is the safe direction.
    """
    comparison_markers = re.compile(
        r'\b(compared to|in contrast|whereas|however|unlike|alternatively|'
        r'on the other hand|differs from|outperformed|underperformed)\b', re.I
    )
    aggregation_markers = re.compile(
        r'\b(across \d+ studies|multiple sources|ranged from|median of|'
        r'average of|converging|majority of evidence|consistently)\b', re.I
    )
    challenge_markers = re.compile(
        r'\b(limitation|however contradictory|conflicting|gap in|'
        r'insufficient evidence|notable absence|remains unclear|'
        r'further research needed|caveat)\b', re.I
    )
    table_pattern = re.compile(r'\|[^|]+\|[^|]+\|')
    # I-wire-012 (#1326): when enabled (default), ALSO count the aggregated ``## Key Findings`` ATX
    # block and the ``## Analytical synthesis`` synthesis header (which ``split_report_into_sections``
    # turns into a section TITLE, not body content) — not only the per-section ``**Key Findings**``
    # bold form — so a report that ships a Key-Findings block scores key_findings>0 instead of 0.
    count_atx_kf = _count_atx_key_findings_enabled()
    # I-wire-013 (#1327): ALSO match an ATX ``## Key Findings`` header that appears INSIDE a section's
    # CONTENT - not only the bold ``**Key Findings**`` form, and not only when ``split_report_into_
    # sections`` lifts it to a TITLE. Pipeline B scores whole-report ``content`` blobs whose depth /
    # analytical-synthesis block carries an ATX ``## Key Findings`` / ``### <title>`` header inline; the
    # bold-only regex scored those 0. Broadening can ONLY RAISE the advisory count (RC-8 is a heuristic,
    # never the faithfulness engine), so it makes the depth heuristic EASIER to pass; ``=0`` (the
    # ``PG_DEPTH_COUNT_ATX_KEY_FINDINGS`` kill-switch) restores the exact bold-only count for RC-8 parity.
    if count_atx_kf:
        key_findings_pattern = re.compile(
            r'\*\*Key Findings?\*\*|^#{1,6}\s+Key Findings?\b', re.I | re.M
        )
    else:
        key_findings_pattern = re.compile(r'\*\*Key Findings?\*\*', re.I)
    atx_kf_title_pattern = re.compile(r'^(?:Key Findings?|Analytical synthesis)$', re.I)

    total_comparison = 0
    total_aggregation = 0
    total_challenge = 0
    total_tables = 0
    total_key_findings = 0
    deficient = []

    for section in report_sections:
        content = section.get("content", "")
        comp = len(comparison_markers.findall(content))
        agg = len(aggregation_markers.findall(content))
        chal = len(challenge_markers.findall(content))
        tables = len(table_pattern.findall(content))
        kf = len(key_findings_pattern.findall(content))
        # I-wire-012 (#1326): count a section whose TITLE is the aggregated "Key Findings" / the
        # "Analytical synthesis" header (the ATX block split_report_into_sections lifts to the title).
        if count_atx_kf and atx_kf_title_pattern.match((section.get("title", "") or "").strip()):
            kf += 1

        total_comparison += comp
        total_aggregation += agg
        total_challenge += chal
        total_tables += tables
        total_key_findings += kf

        ops_present = sum([comp > 0, agg > 0, chal > 0, tables > 0, kf > 0])
        if ops_present < 2:
            deficient.append(section.get("title", "?"))

    passed = (
        total_comparison >= 10 and
        total_tables >= 2 and
        total_key_findings >= 3 and
        total_challenge >= 3 and
        len(deficient) <= 2
    )

    return {
        "passed": passed,
        "comparison_markers": total_comparison,
        "aggregation_patterns": total_aggregation,
        "challenge_markers": total_challenge,
        "tables": total_tables,
        "key_findings": total_key_findings,
        "deficient_sections": deficient,
    }


def split_report_into_sections(report_md: str) -> list[dict]:
    """Split an assembled markdown report into ``[{"title", "content"}]`` on ATX headers.

    Used by the benchmark advisory annotation so the depth metric covers the **full delivered report**
    (front Key Findings block, body sections, Trial Summary tables, Per-Trial subsections, Limitations,
    and the V30 Methods disclosure if present) — not just the body ``verified_text``.

    Rules:
    - Each line matching ``^#{1,6}\\s+<title>`` starts a new section; ``<title>`` is the header text.
    - Text BEFORE the first header becomes a single ``{"title": "Preamble", "content": ...}`` section
      (so a leading block with no header is still scored).
    - The header line itself is excluded from the section ``content`` (only the body text is scored),
      matching Pipeline B, which scores ``section["content"]`` (body), not the heading.
    - Empty / whitespace-only input → ``[]``. A report with no headers → one ``Preamble`` section.
    """
    if not report_md or not report_md.strip():
        return []

    sections: list[dict] = []
    current_title = "Preamble"
    current_lines: list[str] = []

    def _flush() -> None:
        content = "\n".join(current_lines).strip()
        # Drop a leading empty Preamble (report that opens directly with a header), but keep any
        # later empty section so the deficient-section accounting stays faithful to the structure.
        if content or current_title != "Preamble" or sections:
            sections.append({"title": current_title, "content": content})

    for line in report_md.splitlines():
        match = _ATX_HEADER_RE.match(line)
        if match:
            _flush()
            current_title = match.group(2).strip() or "?"
            current_lines = []
        else:
            current_lines.append(line)
    _flush()

    return sections
