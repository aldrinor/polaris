"""I-arch-011 LANE COMPOSE — B08 (composition grounding) + B10 (contract funnel).

Behavioral, fail-loud tests for the EVIDENCE-DRIVEN section-selection fix in
``multi_section_generator.py``.

B08 ROOT CAUSE (pre-fix): the M-40 prompt rule force-mandated a "Mechanism"
section whenever >=3 evidence rows carried mechanism vocabulary in their TITLE.
The LLM obeyed and attached ev_ids by title — but many of those rows were
fetched as stubs / never read (no ``direct_quote`` and no read ``statement``),
so strict_verify could resolve no span and the section rendered a 0-sentence
grounding gap. The fix:
  (a) softens the M-40 prompt rule so Mechanism is OPTIONAL / evidence-driven,
      never a "MUST include" mandate keyed on title vocabulary; and
  (b) adds a DETERMINISTIC, ENFORCED groundability guard
      (``_drop_ungroundable_sections``) that removes any planned section whose
      EVERY assigned ev_id resolves to a non-span-groundable (title-only/unread)
      row — applied on the legacy LLM-outline path before fallback selection.

These tests target the enforced mechanism (b) + the de-mandated prompt (a).
They are deterministic (no LLM call). They FAIL on the pre-fix code (where
``_drop_ungroundable_sections`` / ``_ev_is_span_groundable`` do not exist and
the M-40 rule still says "you MUST include 'Mechanism'") and PASS after the fix.

B10 (contract funnel entities=5): the literal entity cap is NOT in either file
assigned to this lane (``multi_section_generator.py`` / ``domain_router.py``);
it lives in the per-query report contract + the contract-construction path
(out of lane). This test fail-loud asserts that NO hard numeric entity cap was
introduced into the in-lane files, so the lane can never become the place that
re-imposes a FILTER-AND-CAP funnel.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.polaris_graph.generator.multi_section_generator import (
    OUTLINE_SYSTEM_PROMPT,
    SectionPlan,
    _drop_ungroundable_sections,
    _ev_is_span_groundable,
)


# ---------------------------------------------------------------------------
# Helpers — build a realistic evidence pool (real-data shape, no mocks).
# ---------------------------------------------------------------------------


def _read_row(evidence_id: str, *, statement: str = "", direct_quote: str = "") -> dict:
    """An evidence row that was actually READ (has quotable span text)."""
    return {
        "evidence_id": evidence_id,
        "title": f"Source {evidence_id}",
        "statement": statement,
        "direct_quote": direct_quote,
        "tier": "T1",
    }


def _title_only_row(evidence_id: str, *, title: str) -> dict:
    """An evidence row known ONLY by title — fetched as a stub / never read.
    No ``statement`` text, no ``direct_quote``: nothing strict_verify can ground
    a sentence against. This is the B08 failure shape (mechanism-titled stubs).
    """
    return {
        "evidence_id": evidence_id,
        "title": title,
        "statement": "",
        "direct_quote": "",
        "tier": "T6",
    }


# ---------------------------------------------------------------------------
# B08 — Mechanism section dropped when no groundable mechanism evidence exists.
# ---------------------------------------------------------------------------


def test_groundability_predicate_distinguishes_read_from_title_only():
    """The predicate is the load-bearing groundability signal: read rows are
    groundable; title-only/unread rows are not."""
    assert _ev_is_span_groundable(_read_row("ev_a", statement="Tirzepatide lowered HbA1c by 2.1%."))
    assert _ev_is_span_groundable(_read_row("ev_b", direct_quote="The agonist bound the GLP-1 receptor."))
    assert not _ev_is_span_groundable(
        _title_only_row("ev_c", title="Pharmacokinetics of a dual agonist (receptor binding)")
    )
    assert not _ev_is_span_groundable(None)
    assert not _ev_is_span_groundable({"evidence_id": "ev_d"})


def test_mechanism_section_dropped_when_all_ev_ids_unread():
    """B08 CORE: a Mechanism section whose EVERY assigned ev_id is a title-only
    (unread) mechanism-vocab stub MUST be dropped — it could only render a
    0-sentence grounding gap. Genuinely-grounded sections survive intact."""
    evidence = [
        # Efficacy: real read rows.
        _read_row("ev_001", statement="In SURPASS-2, tirzepatide reduced HbA1c by 2.46%."),
        _read_row("ev_002", direct_quote="Body weight fell 11.2 kg at week 40 with the 15 mg dose."),
        # Mechanism: ONLY title-only stubs (the M-40 title-vocab trap — never read).
        _title_only_row("ev_900", title="Mechanism of action: GIP/GLP-1 receptor agonism"),
        _title_only_row("ev_901", title="Pharmacokinetics and half-life of the dual agonist"),
        _title_only_row("ev_902", title="Pharmacodynamic signaling pathway and binding kinetics"),
    ]
    plans = [
        SectionPlan(title="Efficacy", focus="Efficacy endpoints.", ev_ids=["ev_001", "ev_002"]),
        # The forced, ungroundable Mechanism section the pre-fix M-40 rule produced.
        SectionPlan(
            title="Mechanism",
            focus="Mechanism of action.",
            ev_ids=["ev_900", "ev_901", "ev_902"],
        ),
    ]

    kept, dropped = _drop_ungroundable_sections(plans, evidence)

    kept_titles = {p.title for p in kept}
    assert "Mechanism" in dropped, (
        "B08: the title-only Mechanism section must be DROPPED — it has zero "
        f"span-groundable rows. dropped={dropped}"
    )
    assert "Mechanism" not in kept_titles, "Ungroundable Mechanism section must not survive."
    assert "Efficacy" in kept_titles, "The grounded Efficacy section must be kept untouched."


def test_mechanism_section_kept_when_any_ev_id_is_read():
    """Faithfulness/breadth guardrail: the guard is groundability-only, NOT a
    cap. A Mechanism section with even ONE actually-read row survives with ALL
    its ev_ids intact — read evidence is never thinned to a number."""
    evidence = [
        _read_row("ev_001", statement="Tirzepatide reduced HbA1c by 2.46%."),
        # Mechanism subset: one READ mechanism row + two title-only stubs.
        _read_row(
            "ev_910",
            direct_quote="Tirzepatide is a dual GIP and GLP-1 receptor agonist; "
            "receptor binding drives insulinotropic signaling.",
        ),
        _title_only_row("ev_911", title="Pharmacokinetics of the dual agonist"),
        _title_only_row("ev_912", title="Half-life and metabolism overview"),
    ]
    plans = [
        SectionPlan(title="Efficacy", focus="Efficacy.", ev_ids=["ev_001"]),
        SectionPlan(
            title="Mechanism",
            focus="Mechanism of action.",
            ev_ids=["ev_910", "ev_911", "ev_912"],
        ),
    ]

    kept, dropped = _drop_ungroundable_sections(plans, evidence)

    kept_by_title = {p.title: p for p in kept}
    assert "Mechanism" in kept_by_title, (
        "A Mechanism section with a real read row must be KEPT — the guard is "
        f"groundability-only, never a breadth cap. dropped={dropped}"
    )
    # All three ev_ids preserved — no thinning of the grounded section.
    assert kept_by_title["Mechanism"].ev_ids == ["ev_910", "ev_911", "ev_912"]
    assert dropped == []


def test_m40_prompt_no_longer_force_mandates_mechanism():
    """B08 (a): the M-40 prompt rule must no longer FORCE Mechanism on title
    vocabulary. The pre-fix rule literally said
    `you MUST include "Mechanism"`; the fix de-mandates it to evidence-driven
    inclusion."""
    prompt = OUTLINE_SYSTEM_PROMPT
    # The forced-mandate phrasing must be gone.
    assert 'MUST include "Mechanism"' not in prompt, (
        "B08: M-40 must no longer hard-mandate a Mechanism section on title "
        "vocabulary — that is the rule that forced ungrounded depth-padding."
    )
    # The de-mandated rule must explicitly tie inclusion to read evidence and
    # explicitly reject title-only inclusion.
    assert "EVIDENCE-DRIVEN" in prompt
    assert "TITLE ALONE" in prompt
    assert "OMIT the section" in prompt


# ---------------------------------------------------------------------------
# B10 — no hard numeric entity cap may be introduced into the in-lane files.
# ---------------------------------------------------------------------------


def test_no_hard_entity_cap_in_lane_files():
    """B10 (lane-scope guardrail): the entities=5 funnel does NOT live in the
    two files this lane owns, and the fix must NOT introduce any hard numeric
    entity/section cap into them (WEIGHT-AND-CONSOLIDATE, never FILTER-AND-CAP).

    Fail-loud: scans the in-lane source for a hard-coded `entities = 5` /
    `entities=5` / `max_entities = 5` style cap. The contract funnel is widened
    out-of-lane (per-query contract + contract construction); the in-lane files
    must never become the place that re-imposes a 5-entity numeric cap.
    """
    repo_root = Path(__file__).resolve().parents[3]
    in_lane = [
        repo_root / "src" / "polaris_graph" / "generator" / "multi_section_generator.py",
        repo_root / "src" / "polaris_graph" / "audit_ir" / "domain_router.py",
    ]
    # Match a hard cap that pins an entity/required-entity count to 5
    # (e.g. `entities = 5`, `max_entities=5`, `n_entities = 5`).
    cap_pat = re.compile(
        r"\b(?:max_|n_|num_|required_)?entit(?:y|ies)\b[^\n=]{0,30}=\s*5\b",
        re.IGNORECASE,
    )
    offenders: list[str] = []
    for path in in_lane:
        assert path.exists(), f"in-lane file missing: {path}"
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), start=1):
            if cap_pat.search(line):
                offenders.append(f"{path.name}:{i}: {line.strip()}")
    assert not offenders, (
        "B10: a hard 5-entity numeric cap must not exist in the in-lane files "
        "(WEIGHT-AND-CONSOLIDATE, never FILTER-AND-CAP). Offenders:\n"
        + "\n".join(offenders)
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-x", "-q", "-p", "no:cacheprovider"]))
