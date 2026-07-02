"""I-deepfix-001 U17 (#1335) — near-duplicate section collapse (OFFLINE, no model/GPU/network).

THE DUPLICATE: the "Corroborated Weighted Findings" section (weighted_enrichment.
``build_verified_span_draft``, joined-prose) and the numbered "Evidence base" section
(``build_evidence_base_section``) are BUILT FROM THE SAME uncapped unbound-SUPPORTS ev_id surface
with the same same-work consolidation, the same ``spans_per_source()`` budget and the same verbatim
``_emit_unit`` — so both render the SAME verified spans (measured 83-94% identical). Rendering BOTH
is pure repetition (#1335).

THE FIX: ``_append_evidence_base_section`` now skips its append when the Evidence base body is
>= ``PG_SECTION_DEDUP_SIMILARITY`` (default 0.80) similar to an already-assembled non-dropped
section — keep ONE. This is a DISPLAY de-duplication: the surviving Corroborated Weighted Findings
section carries the SAME verified spans + SAME [N] citations (same sources => breadth preserved),
and every entry already passed the FROZEN faithfulness engine independently. Kill-switch
``PG_SECTION_DEDUP_ENABLED`` (default ON) OFF => both sections render => byte-identical legacy.

Entailment is forced OFF (``PG_STRICT_VERIFY_ENTAILMENT=off``) so the Evidence base body is built by
``strict_verify``'s deterministic mechanical checks only (verbatim self-quotes pass) with zero spend.
"""

from __future__ import annotations

import pytest

from src.polaris_graph.generator import multi_section_generator as msg
from src.polaris_graph.generator import weighted_enrichment as we


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures: 8 DISTINCT works (no DOI/title => each is its own work, none consolidate).
# ─────────────────────────────────────────────────────────────────────────────
def _eight_distinct_works():
    pool: dict = {}
    ev_ids: list[str] = []
    for i in range(1, 9):
        eid = f"ev{i:02d}"
        ev_ids.append(eid)
        pool[eid] = {
            "direct_quote": (
                f"Finding number {i}: the measured outcome improved substantially in "
                f"cohort {i} across the observed follow-up window."
            ),
            "source_url": f"https://source{i:02d}.example/paper",
            "source_tier": "T3",
        }
    return ev_ids, pool


def _section_result(title: str, verified_text: str) -> "msg.SectionResult":
    """A minimal non-dropped SectionResult carrying a rendered body."""
    return msg.SectionResult(
        title=title,
        focus="",
        ev_ids_assigned=[],
        raw_draft="",
        rewritten_draft="",
        verified_text=verified_text,
        biblio_slice=[],
        sentences_verified=1,
        sentences_dropped=0,
        regen_attempted=False,
        dropped_due_to_failure=False,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. Normalization: a numbered list and its joined-prose twin normalize equal.
# ─────────────────────────────────────────────────────────────────────────────
def test_normalize_strips_header_enumeration_and_citations():
    numbered = (
        "## Evidence base\n\n"
        "1. Insulin resistance raised fasting glucose in the cohort [3].\n"
        "2. Body weight fell across the study window [7]."
    )
    prose = (
        "Insulin resistance raised fasting glucose in the cohort [ev01]. "
        "Body weight fell across the study window [ev02]."
    )
    n1 = msg._normalize_section_body_for_dedup(numbered)
    n2 = msg._normalize_section_body_for_dedup(prose)
    assert n1 == n2, f"header/enum/citation stripping must make the twins equal:\n{n1!r}\n{n2!r}"
    assert "##" not in n1 and "[" not in n1 and n1[:2] != "1.", "scaffolding must be gone"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Similarity detector: numbered-vs-prose twin flagged; a distinct body is not.
# ─────────────────────────────────────────────────────────────────────────────
def test_detector_flags_numbered_prose_twin_and_ignores_distinct(monkeypatch):
    monkeypatch.delenv("PG_SECTION_DEDUP_ENABLED", raising=False)
    monkeypatch.delenv("PG_SECTION_DEDUP_SIMILARITY", raising=False)
    ev_ids, pool = _eight_distinct_works()
    prose_body = we.build_verified_span_draft(ev_ids, pool)          # CWF-style joined prose
    numbered_block = we.build_evidence_base_section(ev_ids, pool)    # Evidence base numbered list
    assert prose_body and numbered_block

    existing = [
        _section_result("Introduction", "An unrelated introduction about quantum chromodynamics."),
        _section_result("Corroborated Weighted Findings", prose_body),
    ]
    # The numbered Evidence base body is a near-duplicate of the Corroborated Weighted Findings body.
    hit = msg._section_body_is_near_duplicate(numbered_block, existing)
    assert hit == "Corroborated Weighted Findings", f"expected the CWF twin to be flagged; got {hit!r}"

    # A genuinely distinct body is NOT flagged (no over-collapse).
    distinct = "Photosynthesis converts sunlight into chemical energy inside plant chloroplasts."
    assert msg._section_body_is_near_duplicate(distinct, existing) is None


def test_detector_off_when_killswitch_disabled(monkeypatch):
    monkeypatch.setenv("PG_SECTION_DEDUP_ENABLED", "0")
    ev_ids, pool = _eight_distinct_works()
    prose_body = we.build_verified_span_draft(ev_ids, pool)
    numbered_block = we.build_evidence_base_section(ev_ids, pool)
    existing = [_section_result("Corroborated Weighted Findings", prose_body)]
    assert msg._section_body_is_near_duplicate(numbered_block, existing) is None


# ─────────────────────────────────────────────────────────────────────────────
# 3. BEHAVIOR (RED before / GREEN after): the near-identical Evidence base does NOT
#    get appended a second time when the CWF twin already exists.
# ─────────────────────────────────────────────────────────────────────────────
def test_evidence_base_collapses_against_existing_cwf_twin(monkeypatch):
    monkeypatch.setenv("PG_BREADTH_EVIDENCE_BASE_SECTION", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    monkeypatch.delenv("PG_SECTION_DEDUP_ENABLED", raising=False)      # default ON
    ev_ids, pool = _eight_distinct_works()

    # The already-assembled Corroborated Weighted Findings section: the SAME uncapped SUPPORTS
    # surface rendered as joined prose (production build_verified_span_draft).
    cwf_body = we.build_verified_span_draft(ev_ids, pool)
    assert cwf_body, "fixture precondition: the CWF prose body must be non-empty"
    section_results = [_section_result("Corroborated Weighted Findings", cwf_body)]
    global_biblio: list = []

    appended = msg._append_evidence_base_section(section_results, global_biblio, ev_ids, pool)

    assert appended is False, "the near-identical Evidence base must be collapsed (not re-rendered)"
    titles = [s.title for s in section_results]
    assert titles == ["Corroborated Weighted Findings"], (
        f"only ONE section must survive the collapse; got {titles!r}"
    )
    assert not any(s.title == "Evidence base" for s in section_results), (
        "the duplicate Evidence base section must NOT be appended"
    )


def test_evidence_base_still_appends_when_no_twin_exists(monkeypatch):
    """No near-duplicate present => the Evidence base is appended normally (fix does not over-fire)."""
    monkeypatch.setenv("PG_BREADTH_EVIDENCE_BASE_SECTION", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    monkeypatch.delenv("PG_SECTION_DEDUP_ENABLED", raising=False)
    ev_ids, pool = _eight_distinct_works()

    section_results = [
        _section_result("Introduction", "A wholly unrelated overview of marine biology and coral reefs.")
    ]
    global_biblio: list = []
    appended = msg._append_evidence_base_section(section_results, global_biblio, ev_ids, pool)

    assert appended is True, "with no near-duplicate present the Evidence base must still render"
    assert any(s.title == "Evidence base" for s in section_results)


def test_evidence_base_killswitch_off_renders_both(monkeypatch):
    """PG_SECTION_DEDUP_ENABLED=0 => byte-identical legacy: BOTH sections render even when identical."""
    monkeypatch.setenv("PG_BREADTH_EVIDENCE_BASE_SECTION", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    monkeypatch.setenv("PG_SECTION_DEDUP_ENABLED", "0")
    ev_ids, pool = _eight_distinct_works()

    cwf_body = we.build_verified_span_draft(ev_ids, pool)
    section_results = [_section_result("Corroborated Weighted Findings", cwf_body)]
    global_biblio: list = []
    appended = msg._append_evidence_base_section(section_results, global_biblio, ev_ids, pool)

    assert appended is True, "kill-switch OFF must restore the legacy both-sections render"
    assert any(s.title == "Evidence base" for s in section_results)
    assert len(section_results) == 2


# ─────────────────────────────────────────────────────────────────────────────
# 4. Threshold parsing is fail-safe (bad value falls back to the default).
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("bad", ["", "abc", "0", "-0.5", "1.5", "2"])
def test_similarity_threshold_falls_back_on_bad_env(monkeypatch, bad):
    monkeypatch.setenv("PG_SECTION_DEDUP_SIMILARITY", bad)
    assert msg._section_dedup_similarity_threshold() == pytest.approx(
        msg._SECTION_DEDUP_SIMILARITY_DEFAULT
    )


def test_similarity_threshold_honors_valid_env(monkeypatch):
    monkeypatch.setenv("PG_SECTION_DEDUP_SIMILARITY", "0.9")
    assert msg._section_dedup_similarity_threshold() == pytest.approx(0.9)
