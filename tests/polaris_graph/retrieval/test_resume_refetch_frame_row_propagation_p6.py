"""I-deepfix-001 P6 (#1344) — A15 resume-recovery propagation to the V30 contract slot generator.

RED-before / GREEN-after behavioral test for the P6 resume-checkpoint fix.

THE BUG (traced at scripts/run_honest_sweep_r3.py:11595-11612): on a ``--resume`` the A15
re-fetch (``resume_refetch.refetch_degraded_resume_rows``) re-grounds a degraded reloaded
``evidence_for_gen`` ROW dict's ``direct_quote`` in place, but the V30 contract slot generator
reads its span from the ``FrameRow`` (``frame_row.direct_quote``,
contract_section_runner.py) — a SEPARATE object that ``fetch_compiled_frame`` re-fetches fresh and
that can come back a SHELL again on the resume (same paywall/block). So a recovered anchor still
RENDERS HOLLOW. The fix (``propagate_recovered_spans_to_frame_rows``) copies the recovered span from
the reloaded contract row (matched by ``v30_entity_id``) into any HOLLOW FrameRow.

The assertions hinge on the SAME render-decision predicate the production contract runner uses
(``_frame_row_has_usable_quote`` — the A1 shell/usable gate) and on the evidence-pool anchor span the
slot generator actually cites (``register_frame_rows_into_evidence_pool``) — not on an internal flag,
so a GREEN here means the resumed run renders a FILLED anchor, not a tautology (I-wire-014 lesson).

FAITHFULNESS (§-1.3): the fix copies REAL recovered fetched content onto the frame row's INPUT span;
register + slot-fill still flow through the UNCHANGED strict_verify. It is hollow-only (never clobbers
a good span), resume-scoped, and never fabricates (a hollow row with no recovered span stays disclosed).
"""
from __future__ import annotations

import dataclasses

from src.polaris_graph.generator.contract_section_runner import (
    _MIN_VERIFIABLE_SPAN_CHARS,
    _frame_row_has_usable_quote,
    register_frame_rows_into_evidence_pool,
)
from src.polaris_graph.retrieval.frame_fetcher import FrameRow, ProvenanceClass

# The propagation helper under test (this import is RED before the fix lands).
from src.polaris_graph.retrieval.resume_refetch import (
    propagate_recovered_spans_to_frame_rows,
    recovered_spans_from_reloaded_rows,
)

# A real, > floor recovered span (mirrors what the AccessBypass+Zyte cascade re-grounds on resume).
_RECOVERED_SPAN = (
    "Industrial robots reduced local employment: one more robot per thousand workers "
    "cut the employment-to-population ratio by about 0.2 percentage points across US "
    "commuting zones between 1990 and 2007."
)
assert len(_RECOVERED_SPAN) >= _MIN_VERIFIABLE_SPAN_CHARS


def _hollow_gap_frame_row(entity_id: str) -> FrameRow:
    """A V30 contract anchor that came back an EMPTY SHELL (the reloaded-degraded case)."""
    return FrameRow(
        entity_id=entity_id,
        entity_type="economic_report",
        rendering_slot="empirical_displacement",
        provenance_class=ProvenanceClass.FRAME_GAP_UNRECOVERABLE,
        direct_quote="",  # hollow
        quote_source="none",
        doi="10.1086/705716",
        pmid=None,
        oa_pdf_url=None,
        url="https://www.journals.uchicago.edu/doi/10.1086/705716",
        title="Robots and Jobs: Evidence from US Labor Markets",
        authors=("Acemoglu D", "Restrepo P"),
        journal="Journal of Political Economy",
        year=2020,
        failure_reason="fetch_shell",
    )


def _filled_frame_row(entity_id: str, quote: str) -> FrameRow:
    """A V30 contract anchor whose fresh fetch already yielded a usable span (must NOT be clobbered)."""
    return dataclasses.replace(
        _hollow_gap_frame_row(entity_id),
        provenance_class=ProvenanceClass.OPEN_ACCESS,
        direct_quote=quote,
        quote_source="oa_full_text",
        failure_reason=None,
    )


def _recovered_map_from_reloaded_rows(evidence_for_gen: list[dict]) -> dict[str, str]:
    """Exercise the PRODUCTION guarded builder the run_honest_sweep caller now uses (not a local
    mirror): {v30_entity_id -> recovered direct_quote}, admitting ONLY genuinely-recovered rows."""
    return recovered_spans_from_reloaded_rows(evidence_for_gen)


def test_baseline_hollow_frame_row_renders_hollow_anchor():
    """Guard: without propagation the reloaded hollow anchor renders empty (the shipped bug)."""
    row = _hollow_gap_frame_row("robots_jobs")
    # The production render-decision predicate: NOT a usable quote -> gap disclosure (hollow anchor).
    assert _frame_row_has_usable_quote(row) is False
    pool: dict = {}
    register_frame_rows_into_evidence_pool(pool, (row,))
    # The span the slot generator would cite is empty -> hollow contract anchor.
    assert pool["robots_jobs"]["direct_quote"] == ""


def test_recovered_row_renders_filled_contract_anchor_on_resume():
    """GREEN target: an A15-recovered reloaded row propagates into the hollow FrameRow so the resumed
    contract run renders a FILLED anchor (usable quote + non-empty evidence-pool cite span)."""
    entity_id = "robots_jobs"
    frame_rows = (_hollow_gap_frame_row(entity_id),)

    # The reloaded, A15-re-grounded evidence_for_gen contract row (direct_quote repopulated in place).
    reloaded_evidence_for_gen = [
        {
            "evidence_id": entity_id,
            "v30_entity_id": entity_id,
            "v30_frame_row": True,
            "direct_quote": _RECOVERED_SPAN,
            "source_url": "https://www.journals.uchicago.edu/doi/10.1086/705716",
        }
    ]
    recovered = _recovered_map_from_reloaded_rows(reloaded_evidence_for_gen)
    assert recovered == {entity_id: _RECOVERED_SPAN}

    new_rows, telemetry = propagate_recovered_spans_to_frame_rows(
        frame_rows, recovered_span_by_entity=recovered,
    )

    assert telemetry["propagated"] == [entity_id]
    (patched,) = new_rows
    # Render-decision predicate flips hollow -> usable (the anchor now fills, not discloses a gap).
    assert _frame_row_has_usable_quote(patched) is True
    assert patched.direct_quote == _RECOVERED_SPAN
    assert patched.provenance_class != ProvenanceClass.FRAME_GAP_UNRECOVERABLE
    assert patched.quote_source == "a15_resume_refetch"

    # The span the slot generator cites is now the REAL recovered content -> filled contract anchor.
    pool: dict = {}
    register_frame_rows_into_evidence_pool(pool, new_rows)
    assert pool[entity_id]["direct_quote"] == _RECOVERED_SPAN


def test_non_hollow_frame_row_is_never_clobbered():
    """FAITHFULNESS/no-clobber: a FrameRow that already carries a usable span keeps it, even if a
    (different) recovered span is present for that entity."""
    entity_id = "robots_jobs"
    good_quote = (
        "The paper documents large and robust negative effects of industrial robots on "
        "employment and wages in US commuting zones over the 1990-2007 period."
    )
    frame_rows = (_filled_frame_row(entity_id, good_quote),)
    new_rows, telemetry = propagate_recovered_spans_to_frame_rows(
        frame_rows,
        recovered_span_by_entity={entity_id: _RECOVERED_SPAN},
    )
    assert telemetry["propagated"] == []
    (unchanged,) = new_rows
    assert unchanged.direct_quote == good_quote  # fresh fetch preserved, not overwritten


def test_hollow_row_without_recovery_stays_disclosed_no_fabrication():
    """NO-FABRICATION: a hollow anchor with NO matching recovered span stays a gap (disclosed),
    never invented."""
    entity_id = "eloundou_gpts"
    frame_rows = (_hollow_gap_frame_row(entity_id),)
    new_rows, telemetry = propagate_recovered_spans_to_frame_rows(
        frame_rows,
        recovered_span_by_entity={"some_other_entity": _RECOVERED_SPAN},
    )
    assert telemetry["propagated"] == []
    (still_hollow,) = new_rows
    assert still_hollow.direct_quote == ""
    assert _frame_row_has_usable_quote(still_hollow) is False


import pytest

from src.polaris_graph.retrieval.resume_refetch import (
    _DEGRADED_FLAGS,
    is_row_genuinely_recovered,
)

# A NON-empty shell/error span that clears the 50-char floor but is NOT real recovered content
# (e.g. a paywall / landing-page notice). The A15 refetch leaves a STILL-SHELL row's span in place and
# does NOT clear its degraded flags — so this span must never be harvested as "recovered".
_SHELL_SPAN = (
    "To continue reading this article, please subscribe or sign in to your institutional "
    "account. Access to the full text requires a valid subscription."
)
assert len(_SHELL_SPAN) >= _MIN_VERIFIABLE_SPAN_CHARS


@pytest.mark.parametrize("degraded_flag", list(_DEGRADED_FLAGS))
def test_flagged_shell_row_does_not_propagate(degraded_flag):
    """RED-before / GREEN-after for the Codex P1: a reloaded contract row that is STILL DEGRADED
    (a residual A15 flag set) — even with a non-empty >= floor shell span — must be EXCLUDED from the
    propagation map, so its shell can NOT relabel a hollow FrameRow to OPEN_ACCESS. The A15 refetch
    clears these flags ONLY on real recovery; keeping one means the row is still a shell."""
    entity_id = "robots_jobs"
    frame_rows = (_hollow_gap_frame_row(entity_id),)

    still_shell_evidence_for_gen = [
        {
            "evidence_id": entity_id,
            "v30_entity_id": entity_id,
            "v30_frame_row": True,
            "direct_quote": _SHELL_SPAN,  # non-empty, clears the floor, but still a shell
            degraded_flag: True,          # residual A15 degraded flag => NOT recovered
            "source_url": "https://www.journals.uchicago.edu/doi/10.1086/705716",
        }
    ]

    # The guarded builder must NOT treat a flagged shell as a recovered span.
    assert is_row_genuinely_recovered(still_shell_evidence_for_gen[0]) is False
    recovered = _recovered_map_from_reloaded_rows(still_shell_evidence_for_gen)
    assert recovered == {}

    # End-to-end: nothing propagates, the hollow anchor stays a disclosed gap (NO fabricated anchor).
    new_rows, telemetry = propagate_recovered_spans_to_frame_rows(
        frame_rows, recovered_span_by_entity=recovered,
    )
    assert telemetry["propagated"] == []
    (still_hollow,) = new_rows
    assert still_hollow.direct_quote == ""
    assert _frame_row_has_usable_quote(still_hollow) is False
    assert still_hollow.provenance_class == ProvenanceClass.FRAME_GAP_UNRECOVERABLE


def test_cleared_flags_still_recover_after_a15_refetch():
    """Counterpart: once A15 sets the degraded flags to False (a REAL recovery), the same row DOES
    propagate — the guard gates on live degradation, it does not permanently blacklist a recovered
    anchor (no over-drop / WEIGHT-not-FILTER)."""
    entity_id = "robots_jobs"
    frame_rows = (_hollow_gap_frame_row(entity_id),)
    recovered_evidence_for_gen = [
        {
            "evidence_id": entity_id,
            "v30_entity_id": entity_id,
            "v30_frame_row": True,
            "direct_quote": _RECOVERED_SPAN,
            # A15 re-fetch RECOVERED this row: it re-grounded the span AND cleared every flag.
            **{flag: False for flag in _DEGRADED_FLAGS},
            "source_url": "https://www.journals.uchicago.edu/doi/10.1086/705716",
        }
    ]
    assert is_row_genuinely_recovered(recovered_evidence_for_gen[0]) is True
    recovered = _recovered_map_from_reloaded_rows(recovered_evidence_for_gen)
    assert recovered == {entity_id: _RECOVERED_SPAN}
    new_rows, telemetry = propagate_recovered_spans_to_frame_rows(
        frame_rows, recovered_span_by_entity=recovered,
    )
    assert telemetry["propagated"] == [entity_id]
    (patched,) = new_rows
    assert _frame_row_has_usable_quote(patched) is True
    assert patched.direct_quote == _RECOVERED_SPAN


def test_human_curated_provenance_is_never_overwritten():
    """A HUMAN_CURATED row is a PERMANENT marker; even if hollow it must not be relabelled OA."""
    entity_id = "curator_row"
    curated = dataclasses.replace(
        _hollow_gap_frame_row(entity_id),
        provenance_class=ProvenanceClass.HUMAN_CURATED,
        direct_quote="",
        human_curated_provenance={"source": "operator"},
    )
    new_rows, telemetry = propagate_recovered_spans_to_frame_rows(
        (curated,),
        recovered_span_by_entity={entity_id: _RECOVERED_SPAN},
    )
    assert telemetry["propagated"] == []
    (unchanged,) = new_rows
    assert unchanged.provenance_class == ProvenanceClass.HUMAN_CURATED
    assert unchanged.direct_quote == ""


# ── Codex P6 BLOCKER: an UNFLAGGED, non-starved error-page span must be RE-SCREENED at the ──────────
# propagation-map build point, regardless of flag-state.
#
# The resume degraded-detector (run_honest_sweep_r3.py ~:11559) flags a reloaded row ONLY on
# content_starved / fetch_failed / landing_page / is_content_starved. A doi.org "DOI Not Found"
# registry page is REAL English prose well above the starvation floor and carries NO degraded flags,
# so it is NEVER flagged, NEVER re-fetched, and the error-page screen inside
# ``refetch_degraded_resume_rows`` never runs on it. Such a row then passes ``is_row_genuinely_recovered``
# (non-empty span AND no flags) on flag-state ALONE and would relabel a HOLLOW V30 FrameRow to
# OPEN_ACCESS — a fetch FAILURE rendered as a filled contract anchor. The fix re-screens the candidate
# span CONTENT with the SAME live-path screen (``live_retriever._recovered_content_error_class``, no new
# detector) inside ``recovered_spans_from_reloaded_rows``, rejecting the error page regardless of flags.
# §-1.3: refusing to propagate a fetch FAILURE as grounding is faithfulness-STRENGTHENING, not a source
# DROP — the row stays a disclosed gap in evidence_for_gen and flows through the UNCHANGED strict_verify.

from src.polaris_graph.retrieval.live_retriever import (  # noqa: E402
    _recovered_content_error_class,
    is_content_starved as _live_is_content_starved,
)

# A realistic ~800-char doi.org "DOI Not Found" registry page: real prose (NON-starved), NO degraded
# flags, but a fetch FAILURE. Contains the registry signatures the live-path screen matches.
_UNFLAGGED_DOI_ERROR_PAGE = (
    "DOI Not Found. 10.1086/705716. This DOI cannot be found in the DOI System. Possible reasons "
    "are that the DOI is incorrect in your source, that the DOI was copied incorrectly (check that "
    "the string includes all the characters before and after the slash and no sentence punctuation "
    "marks), or that the DOI has not been activated yet — please try again later and report the "
    "problem if the error continues. DOI name not found. Report errors to the responsible DOI "
    "registration agency. The International DOI Foundation (IDF) is a not-for-profit membership "
    "organization that is the governance and management body for the federation of Registration "
    "Agencies providing Digital Object Identifier services and registration, and is the registration "
    "authority for the ISO standard (ISO 26324) for the DOI system. Home. Handbook. Factsheets. FAQs."
)
assert len(_UNFLAGGED_DOI_ERROR_PAGE) >= _MIN_VERIFIABLE_SPAN_CHARS


def _unflagged_error_page_row(entity_id: str) -> dict:
    """A reloaded V30 contract row carrying an error-page span with NO degraded flags set at all —
    the case the flag-only guard is blind to (never flagged => never re-fetched => never screened)."""
    return {
        "evidence_id": entity_id,
        "v30_entity_id": entity_id,
        "v30_frame_row": True,
        "direct_quote": _UNFLAGGED_DOI_ERROR_PAGE,   # non-empty, non-starved, NO degraded flags
        "source_url": "https://doi.org/10.1086/705716",
    }


def test_error_page_is_nonstarved_and_flag_guard_is_blind_to_it():
    """Precondition + why flags are insufficient: the error page is NON-starved (so the resume
    degraded-detector never flags it) AND ``is_row_genuinely_recovered`` returns True on flag-state
    alone — so ONLY a content re-screen can reject it. The live-path screen classifies it as an
    error page while a real recovered span reads as content."""
    row = _unflagged_error_page_row("robots_jobs")
    assert _live_is_content_starved(_UNFLAGGED_DOI_ERROR_PAGE) is False
    assert is_row_genuinely_recovered(row) is True   # flag-only guard is BLIND to it
    assert _recovered_content_error_class(_UNFLAGGED_DOI_ERROR_PAGE) != ""
    assert _recovered_content_error_class(_RECOVERED_SPAN) == ""


def test_unscreened_builder_would_propagate_error_page_documents_bug():
    """Contrast (documents the exact Codex-flagged bug surface): WITHOUT the screen (legacy None
    default), the flag-only builder ADMITS the unflagged error page and it fills the hollow anchor —
    the behaviour the injected re-screen closes. The production caller always wires the screen."""
    entity_id = "robots_jobs"
    row = _unflagged_error_page_row(entity_id)
    # No screen => the flag-only guard admits the error page (the bug).
    recovered = recovered_spans_from_reloaded_rows([row])
    assert recovered == {entity_id: _UNFLAGGED_DOI_ERROR_PAGE}
    new_rows, telemetry = propagate_recovered_spans_to_frame_rows(
        (_hollow_gap_frame_row(entity_id),), recovered_span_by_entity=recovered,
    )
    # The fetch FAILURE would render as a FILLED contract anchor — this is what the fix prevents.
    assert telemetry["propagated"] == [entity_id]
    (wrongly_filled,) = new_rows
    assert wrongly_filled.direct_quote == _UNFLAGGED_DOI_ERROR_PAGE
    assert wrongly_filled.provenance_class == ProvenanceClass.OPEN_ACCESS


def test_unflagged_error_page_span_is_rescreened_and_rejected():
    """GREEN target (Codex P6 BLOCKER): with the SAME live-path error-page screen wired, the
    unflagged, non-starved DOI-registry error page is RE-SCREENED and EXCLUDED from the propagation
    map regardless of flag-state, so it can NOT relabel the hollow V30 FrameRow to OPEN_ACCESS — the
    anchor stays a disclosed gap (NO fabrication)."""
    entity_id = "robots_jobs"
    row = _unflagged_error_page_row(entity_id)
    frame_rows = (_hollow_gap_frame_row(entity_id),)

    # The guarded builder, wired with the live-path screen, rejects the error page => empty map.
    recovered = recovered_spans_from_reloaded_rows(
        [row], recovered_error_class_fn=_recovered_content_error_class,
    )
    assert recovered == {}

    new_rows, telemetry = propagate_recovered_spans_to_frame_rows(
        frame_rows, recovered_span_by_entity=recovered,
    )
    assert telemetry["propagated"] == []
    (still_hollow,) = new_rows
    assert still_hollow.direct_quote == ""
    assert _frame_row_has_usable_quote(still_hollow) is False
    assert still_hollow.provenance_class == ProvenanceClass.FRAME_GAP_UNRECOVERABLE
    # And the evidence-pool cite span the slot generator would use stays empty (hollow anchor).
    pool: dict = {}
    register_frame_rows_into_evidence_pool(pool, new_rows)
    assert pool[entity_id]["direct_quote"] == ""


def test_genuine_recovered_span_still_propagates_with_screen_on():
    """PRECISION / no over-strip (§-1.3 WEIGHT-not-FILTER): the re-screen must reject ONLY fetch
    FAILURES — a genuine recovered span passes the live-path screen (empty class token) and STILL
    propagates + renders FILLED with the screen wired. Over-stripping a real finding is a lost claim,
    a faithfulness HARM, so this guards the fix from being too aggressive."""
    entity_id = "robots_jobs"
    frame_rows = (_hollow_gap_frame_row(entity_id),)
    reloaded = [
        {
            "evidence_id": entity_id,
            "v30_entity_id": entity_id,
            "v30_frame_row": True,
            "direct_quote": _RECOVERED_SPAN,
            **{flag: False for flag in _DEGRADED_FLAGS},   # A15 cleared every flag => real recovery
            "source_url": "https://www.journals.uchicago.edu/doi/10.1086/705716",
        }
    ]
    recovered = recovered_spans_from_reloaded_rows(
        reloaded, recovered_error_class_fn=_recovered_content_error_class,
    )
    assert recovered == {entity_id: _RECOVERED_SPAN}
    new_rows, telemetry = propagate_recovered_spans_to_frame_rows(
        frame_rows, recovered_span_by_entity=recovered,
    )
    assert telemetry["propagated"] == [entity_id]
    (patched,) = new_rows
    assert _frame_row_has_usable_quote(patched) is True
    assert patched.direct_quote == _RECOVERED_SPAN
    assert patched.provenance_class == ProvenanceClass.OPEN_ACCESS
