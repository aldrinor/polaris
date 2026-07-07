"""Focused offline unit test for the cross-section repetition guard (I-deepfix-001 FIX 5, #1344).

Proves the recycle-not-broaden defect + its fix, AND the diff-gate protections:

  * RED baseline (guard OFF / unset): a finding restated in 3 sections is left in ALL 3 — the exact
    recycle-across-sections defect the audit found (Goldman 2.5% x4, robot-est x4, ...).
  * GREEN (guard ON): the finding is CONSOLIDATED to its richest instance + a back-reference in the
    other sections, with EVERY recycled citation preserved (§-1.3 keep-all); distinct findings kept.
  * P1 #2 (Codex — loose equivalence): near-identical-but-DISTINCT sentences (different figure) are
    NEVER clustered (exact-recycle only) — no faithfulness leak.
  * P1 (Codex iter-2 — bracketed-entity equivalence leak): two sentences identical EXCEPT a
    non-citation bracketed entity ([Alpha] vs [Beta]), each carrying a numeric citation, are DISTINCT
    verified claims and are NEVER clustered. The signature strips ONLY numeric [N] citations, so
    bracketed entity content stays distinguishing.
  * P1 #3 (Codex — markdown layout): a contract-style body with ``### slot`` headings keeps its
    headings + blank lines byte-for-byte (in-place substring swap, never split+rejoin).
  * P1 (Fable — marker-less disclosures): two sections carrying the production gap stub, and
    ``is_gap_stub``-flagged sections, are NEVER rewritten into a false "See ... for this finding".

Faithfulness-neutral by construction: the guard only edits the rendered ``verified_text`` string.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.polaris_graph.generator.cross_section_repetition_guard import (
    consolidate_cross_section_repetition,
    guard_enabled,
)

_ENV_ENABLED = "PG_CROSS_SECTION_REPETITION_GUARD"

# The production marker-less gap stub (multi_section_generator.py), reproduced here so the test pins
# the exact real-world sentence the guard must NEVER treat as a recyclable finding.
_GAP_STUB_SENTENCE = (
    "No claim in this section survived strict verification against the retrieved "
    "source text; this section is a curator-actionable gap. See the verification "
    "details and frame-coverage report for per-claim disposition."
)


@dataclass
class _FakeSection:
    """Minimal stand-in for SectionResult (the guard reads only these attrs via getattr)."""

    title: str
    verified_text: str
    dropped_due_to_failure: bool = False
    is_gap_stub: bool = False


# The recycled finding — identical wording across sections, different corroborating citations. The
# richest instance (most citations) lives in "Economic Impact" ([1][2]); the other two are recycled.
_GOLDMAN = (
    "Goldman Sachs estimates a 2.5 percent boost to global gross domestic "
    "product over roughly ten years"
)


def _build_sections() -> list[_FakeSection]:
    return [
        _FakeSection(
            title="Economic Impact",
            verified_text=(
                f"{_GOLDMAN}. [1][2] "
                "Manufacturing output rose sharply across the coastal provinces last quarter. [3]"
            ),
        ),
        _FakeSection(
            title="Labor Markets",
            verified_text=(
                f"{_GOLDMAN}. [4] "
                "Union membership declined among younger service-sector workers nationwide. [5]"
            ),
        ),
        _FakeSection(
            title="Policy Response",
            verified_text=(
                f"{_GOLDMAN}. [6] "
                "Regulators proposed fresh licensing rules covering autonomous delivery vehicles. [7]"
            ),
        ),
    ]


def _count_goldman(sections: list[_FakeSection]) -> int:
    return sum(1 for s in sections if "Goldman Sachs estimates" in s.verified_text)


def test_guard_default_off_is_no_op(monkeypatch: pytest.MonkeyPatch) -> None:
    """Flag unset => guard disabled => sections untouched (RED baseline: the recycled finding still
    appears in ALL 3 sections, reproducing the defect)."""
    monkeypatch.delenv(_ENV_ENABLED, raising=False)
    assert guard_enabled() is False
    sections = _build_sections()
    before = [s.verified_text for s in sections]

    telemetry = consolidate_cross_section_repetition(sections)

    assert telemetry == {}
    assert [s.verified_text for s in sections] == before  # byte-identical
    assert _count_goldman(sections) == 3  # defect reproduced under OFF


def test_guard_explicit_off_token_is_no_op(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_ENV_ENABLED, "0")
    sections = _build_sections()
    before = [s.verified_text for s in sections]
    assert consolidate_cross_section_repetition(sections) == {}
    assert [s.verified_text for s in sections] == before


def test_finding_in_three_sections_consolidated_citations_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GREEN: guard ON => the finding is kept once (richest) + back-referenced in the other two, with
    ALL recycled citations preserved and every distinct finding untouched."""
    monkeypatch.setenv(_ENV_ENABLED, "1")
    assert guard_enabled() is True
    sections = _build_sections()

    telemetry = consolidate_cross_section_repetition(sections)

    # Exactly one cross-section cluster; two recycled instances consolidated (3 sections -> 1 rich).
    assert telemetry == {"clusters": 1, "consolidated": 2}

    econ, labor, policy = sections

    # Richest instance (most citations) is KEPT verbatim in "Economic Impact".
    assert _GOLDMAN in econ.verified_text
    assert "[1]" in econ.verified_text and "[2]" in econ.verified_text

    # The finding now appears in prose EXACTLY once across the whole report (space freed elsewhere).
    assert _count_goldman(sections) == 1

    # The other two sections carry a back-reference to the richest section — NOT the full restatement.
    for sr in (labor, policy):
        assert 'See "Economic Impact" for this finding.' in sr.verified_text
        assert "Goldman Sachs estimates" not in sr.verified_text

    # EVERY recycled citation is preserved (never dropped) — inline on its section's back-reference.
    assert "[4]" in labor.verified_text
    assert "[6]" in policy.verified_text

    # Distinct findings (and their citations) in each section are UNTOUCHED.
    assert "Manufacturing output rose sharply across the coastal provinces last quarter. [3]" \
        in econ.verified_text
    assert "Union membership declined among younger service-sector workers nationwide. [5]" \
        in labor.verified_text
    assert "Regulators proposed fresh licensing rules covering autonomous delivery vehicles. [7]" \
        in policy.verified_text

    # The full citation universe survives across the report (union preserved, none lost).
    all_text = " ".join(s.verified_text for s in sections)
    for marker in ("[1]", "[2]", "[3]", "[4]", "[5]", "[6]", "[7]"):
        assert marker in all_text, marker


def test_all_distinct_findings_untouched(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guard ON but no finding recurs across sections => nothing is consolidated, prose byte-identical."""
    monkeypatch.setenv(_ENV_ENABLED, "1")
    sections = [
        _FakeSection(
            title="One",
            verified_text="Manufacturing output rose sharply across the coastal provinces. [1]",
        ),
        _FakeSection(
            title="Two",
            verified_text="Union membership declined among younger service-sector workers. [2]",
        ),
        _FakeSection(
            title="Three",
            verified_text="Regulators proposed fresh licensing rules for autonomous vehicles. [3]",
        ),
    ]
    before = [s.verified_text for s in sections]

    telemetry = consolidate_cross_section_repetition(sections)

    assert telemetry == {"clusters": 0, "consolidated": 0}
    assert [s.verified_text for s in sections] == before


def test_same_section_repeat_left_to_fact_dedup(monkeypatch: pytest.MonkeyPatch) -> None:
    """A finding repeated WITHIN one section (not across sections) is NOT consolidated here — that is
    fact_dedup's job; the guard only acts on cross-section recurrence."""
    monkeypatch.setenv(_ENV_ENABLED, "1")
    sections = [
        _FakeSection(
            title="Only Section",
            verified_text=f"{_GOLDMAN}. [1] {_GOLDMAN}. [2]",
        ),
        _FakeSection(
            title="Other",
            verified_text="Union membership declined among younger service-sector workers. [3]",
        ),
    ]
    before = [s.verified_text for s in sections]

    telemetry = consolidate_cross_section_repetition(sections)

    assert telemetry == {"clusters": 0, "consolidated": 0}
    assert [s.verified_text for s in sections] == before


def test_dropped_and_empty_sections_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    """A dropped-due-to-failure section and an empty section are never mutated; a live cross-section
    recurrence between the remaining sections still consolidates."""
    monkeypatch.setenv(_ENV_ENABLED, "1")
    sections = [
        _FakeSection(title="Dropped", verified_text=f"{_GOLDMAN}. [9]",
                     dropped_due_to_failure=True),
        _FakeSection(title="Empty", verified_text="   "),
        _FakeSection(title="Economic Impact", verified_text=f"{_GOLDMAN}. [1][2]"),
        _FakeSection(title="Labor Markets", verified_text=f"{_GOLDMAN}. [4]"),
    ]

    telemetry = consolidate_cross_section_repetition(sections)

    assert telemetry == {"clusters": 1, "consolidated": 1}
    # Dropped + empty untouched.
    assert sections[0].verified_text == f"{_GOLDMAN}. [9]"
    assert sections[1].verified_text == "   "
    # Richest kept, the live twin back-referenced with its citation preserved.
    assert _GOLDMAN in sections[2].verified_text
    assert 'See "Economic Impact" for this finding.' in sections[3].verified_text
    assert "[4]" in sections[3].verified_text


# ── P1 (Codex diff-gate — dropped-section safety): a rendered section must NEVER be collapsed into a
#    back-reference to a NON-rendered (dropped_due_to_failure) section. The guard is passed the RAW
#    section_results but must exclude dropped sections so one is never picked as the richest / back-ref
#    target. Regression: make the DROPPED section the richest-by-citation-count candidate. ──────────────
def test_dropped_richest_section_never_becomes_backref_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The exact Codex diff-gate finding: the recycled finding appears in THREE sections, and the
    instance with the MOST citations ([1][2][3]) lives in a ``dropped_due_to_failure`` section. If the
    guard did not exclude dropped sections it would pick that non-rendered section as the richest and
    replace the finding in BOTH rendered sections with a back-reference to a section that never renders
    — silent final-output content loss. With the exclusion, the dropped section contributes no unit, the
    richest is the richest RENDERED section, and no back-reference ever points to the dropped section."""
    monkeypatch.setenv(_ENV_ENABLED, "1")
    sections = [
        # Dropped/non-rendered, yet carries the MOST citations => would be chosen as richest if the
        # dropped-section exclusion were missing (this is what makes the test catch the regression).
        _FakeSection(title="Dropped Rich", verified_text=f"{_GOLDMAN}. [1][2][3]",
                     dropped_due_to_failure=True),
        _FakeSection(title="Economic Impact", verified_text=f"{_GOLDMAN}. [4][5]"),
        _FakeSection(title="Labor Markets", verified_text=f"{_GOLDMAN}. [6]"),
    ]

    telemetry = consolidate_cross_section_repetition(sections)

    # Only the two RENDERED sections form the cluster; one recycled instance consolidated.
    assert telemetry == {"clusters": 1, "consolidated": 1}

    dropped, econ, labor = sections

    # The dropped/non-rendered section is left byte-for-byte untouched.
    assert dropped.verified_text == f"{_GOLDMAN}. [1][2][3]"

    # NO section anywhere points a back-reference at the non-rendered section — the core safety.
    for sr in sections:
        assert 'See "Dropped Rich"' not in sr.verified_text

    # The finding is kept in the richest RENDERED section (Economic Impact, [4][5]); Labor Markets
    # back-references THAT rendered section, carrying its own citation. No content is lost from render.
    assert _GOLDMAN in econ.verified_text
    assert 'See "Economic Impact" for this finding. [6]' in labor.verified_text
    assert "Goldman Sachs estimates" not in labor.verified_text

    # The finding still survives in rendered prose exactly once (the dropped copy does not render).
    rendered = [s for s in sections if not s.dropped_due_to_failure]
    assert sum(1 for s in rendered if "Goldman Sachs estimates" in s.verified_text) == 1


# ── P1 #2 (Codex): loose-equivalence faithfulness leak — exact-recycle only ─────────────────────
def test_near_restatement_with_different_figure_not_clustered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two near-identical sentences that DIFFER only in the figure (2.5% vs 3.5%) are DISTINCT verified
    content — they must NEVER be clustered / one replaced by a back-reference. Exact-recycle only."""
    monkeypatch.setenv(_ENV_ENABLED, "1")
    sec_a = (
        "Goldman Sachs estimates a 2.5 percent boost to global gross domestic product "
        "over roughly ten years. [1]"
    )
    sec_b = (
        "Goldman Sachs estimates a 3.5 percent boost to global gross domestic product "
        "over roughly ten years. [2]"
    )
    sections = [
        _FakeSection(title="Economic Impact", verified_text=sec_a),
        _FakeSection(title="Labor Markets", verified_text=sec_b),
    ]
    before = [s.verified_text for s in sections]

    telemetry = consolidate_cross_section_repetition(sections)

    # No cluster: the 3.5% figure is DISTINCT content and stays in the report verbatim.
    assert telemetry == {"clusters": 0, "consolidated": 0}
    assert [s.verified_text for s in sections] == before
    assert "3.5 percent" in sections[1].verified_text
    assert "See \"" not in sections[1].verified_text


# ── P1 (Codex iter-2): bracketed-entity equivalence leak — the signature must strip ONLY numeric
#    citations, never a non-citation bracketed label. [Alpha] != [Beta] => distinct, never clustered. ──
def test_bracketed_entity_difference_with_numeric_citations_not_clustered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The exact Codex diff-gate iter-2 regression: two sentences identical EXCEPT a non-citation
    bracketed entity ([Alpha] vs [Beta]), EACH carrying a distinct numeric citation, are genuinely
    DISTINCT verified claims. If the signature stripped all brackets they would collapse and one real
    claim would be replaced by a back-reference (a §-1.3 drop). They must stay untouched."""
    monkeypatch.setenv(_ENV_ENABLED, "1")
    sec_a = "The model [Alpha] reduced error rates by 10 percent in the 2025 trial cohort. [1]"
    sec_b = "The model [Beta] reduced error rates by 10 percent in the 2025 trial cohort. [2]"
    sections = [
        _FakeSection(title="Model A", verified_text=sec_a),
        _FakeSection(title="Model B", verified_text=sec_b),
    ]
    before = [s.verified_text for s in sections]

    telemetry = consolidate_cross_section_repetition(sections)

    # No cluster: the bracketed entity difference makes them distinct.
    assert telemetry == {"clusters": 0, "consolidated": 0}
    assert [s.verified_text for s in sections] == before
    # Both distinct bracketed entities survive verbatim; no false back-reference.
    assert "[Alpha]" in sections[0].verified_text
    assert "[Beta]" in sections[1].verified_text
    assert "See \"" not in sections[1].verified_text


def test_same_bracketed_entity_only_citation_differs_still_clusters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Positive control for the iter-2 fix: two sentences IDENTICAL including the same bracketed entity
    ([Alpha] in both), differing ONLY in the numeric citation, ARE a genuine recycle and STILL cluster
    — proving numeric-only stripping did not break legitimate consolidation. The kept instance retains
    the bracketed entity; the back-reference carries the recycled instance's numeric citation."""
    monkeypatch.setenv(_ENV_ENABLED, "1")
    sec_a = "The system [Alpha] cut latency by 12 percent across all regions in 2025. [1][2]"
    sec_b = "The system [Alpha] cut latency by 12 percent across all regions in 2025. [3]"
    sections = [
        _FakeSection(title="Rich", verified_text=sec_a),
        _FakeSection(title="Other", verified_text=sec_b),
    ]

    telemetry = consolidate_cross_section_repetition(sections)

    assert telemetry == {"clusters": 1, "consolidated": 1}
    # Richest kept verbatim, bracketed entity preserved.
    assert "[Alpha]" in sections[0].verified_text
    assert "cut latency by 12 percent" in sections[0].verified_text
    # Recycled instance replaced by a back-reference carrying ONLY its numeric citation ([3]).
    assert 'See "Rich" for this finding. [3]' in sections[1].verified_text
    assert "cut latency by 12 percent" not in sections[1].verified_text


# ── P1 #3 (Codex): markdown ### heading layout must survive the in-place swap ────────────────────
def test_markdown_slot_headings_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    """A contract-style body carries ``### slot`` sub-headings + blank lines. Consolidating a recycled
    finding inside it must leave every heading + blank line byte-for-byte (no split+rejoin flatten)."""
    monkeypatch.setenv(_ENV_ENABLED, "1")
    # Richest instance sits in a plain narrative section.
    rich = _FakeSection(title="Overview", verified_text=f"{_GOLDMAN}. [1][2]")
    # The contract section: the recycle is a CLEAN middle sentence (not adjacent to a heading — a
    # heading-glued sentence is deliberately skipped, precision-first) inside a slotted body.
    contract_body = (
        "### Economic Slot\n\n"
        "Trade volumes expanded in the second quarter across all regions. [3] "
        f"{_GOLDMAN}. [4] "
        "Consumer prices held steady through the period. [8]\n\n"
        "### Policy Slot\n\n"
        "Regulators opened a consultation on autonomous logistics. [5]"
    )
    contract = _FakeSection(title="Contract", verified_text=contract_body)
    sections = [rich, contract]

    telemetry = consolidate_cross_section_repetition(sections)

    assert telemetry == {"clusters": 1, "consolidated": 1}
    # The richest instance is kept verbatim.
    assert _GOLDMAN in rich.verified_text
    # Both ### headings + their blank lines survive byte-for-byte.
    assert "### Economic Slot\n\n" in contract.verified_text
    assert "\n\n### Policy Slot\n\n" in contract.verified_text
    # The recycled restatement was swapped for a back-reference carrying its own citation.
    assert "Goldman Sachs estimates" not in contract.verified_text
    assert 'See "Overview" for this finding. [4]' in contract.verified_text
    # The distinct neighbouring sentences are untouched.
    assert "Trade volumes expanded in the second quarter across all regions. [3]" \
        in contract.verified_text
    assert "Consumer prices held steady through the period. [8]" in contract.verified_text
    assert "Regulators opened a consultation on autonomous logistics. [5]" \
        in contract.verified_text


# ── P1 (Fable): marker-less gap disclosures must never be rewritten ──────────────────────────────
def test_two_gap_stub_sections_never_backreferenced(monkeypatch: pytest.MonkeyPatch) -> None:
    """RED/GREEN for the Fable defect: two sections carrying the production marker-less gap stub must
    NOT cluster — the honest per-section disclosure stays intact, never a false back-reference."""
    monkeypatch.setenv(_ENV_ENABLED, "1")
    sections = [
        _FakeSection(title="Safety", verified_text=_GAP_STUB_SENTENCE, is_gap_stub=True),
        _FakeSection(title="Mechanism", verified_text=_GAP_STUB_SENTENCE, is_gap_stub=True),
    ]
    before = [s.verified_text for s in sections]

    telemetry = consolidate_cross_section_repetition(sections)

    # Never clustered: gap stubs are marker-less AND is_gap_stub-flagged (belt-and-braces).
    assert telemetry == {"clusters": 0, "consolidated": 0}
    assert [s.verified_text for s in sections] == before
    for sr in sections:
        assert "See \"" not in sr.verified_text  # no false pointer
        assert sr.verified_text == _GAP_STUB_SENTENCE  # honest disclosure intact


def test_marker_less_disclosure_not_flagged_still_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    """Even without the is_gap_stub flag, a marker-less disclosure recurring across sections is NOT a
    finding (no numeric citation) — so it is never consolidated. Real cited findings around it are."""
    monkeypatch.setenv(_ENV_ENABLED, "1")
    sections = [
        _FakeSection(
            title="Safety",
            verified_text=f"{_GAP_STUB_SENTENCE} {_GOLDMAN}. [1][2]",
        ),
        _FakeSection(
            title="Mechanism",
            verified_text=f"{_GAP_STUB_SENTENCE} {_GOLDMAN}. [3]",
        ),
    ]

    telemetry = consolidate_cross_section_repetition(sections)

    # Only the cited Goldman finding clusters; the marker-less stub sentence is ignored in BOTH.
    assert telemetry == {"clusters": 1, "consolidated": 1}
    # The gap stub text still appears (unchanged) in both sections — never turned into a back-ref.
    assert sections[0].verified_text.count(_GAP_STUB_SENTENCE) == 1
    assert sections[1].verified_text.count(_GAP_STUB_SENTENCE) == 1
    assert "See \"" not in sections[0].verified_text
    # The recycled Goldman finding was consolidated in the non-richest section.
    assert 'See "Safety" for this finding. [3]' in sections[1].verified_text
