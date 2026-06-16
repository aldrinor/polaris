"""iarch007 (drb_90 epic-failure) regression + release-invariant suite — AGENT-NEWFILES (A11-test).

This suite is the STRUCTURAL guard that the iarch007 fix set cannot silently regress, and the
no-unjudged-release INVARIANT that A18 enforces. Each test is labelled as ONE of two classes
(the distinction the advisor flagged as correctness-critical):

  * INVARIANT — a permanent safety property that MUST hold NOW and after every future fix. The
    seam status set-membership ({released_with_disclosed_gaps, released_insufficient_safety,
    abort_*}, NEVER success) is the canonical one: the current fail-closed `abort_*` seam path
    ALREADY satisfies it, and so does the A2 rescue. Encoding it as "seam must be
    released_with_disclosed_gaps" would convert a permanent invariant into a fix-detector that
    breaks the moment anyone refactors — so it is encoded as set-membership exactly as worded.

  * FIX-DETECTOR — exercises a specific landed fix in its real call shape. It PASSES once the
    corresponding code fix is landed and FAILS (with a clear message) if the fix is absent or
    inert (dead-on-arrival). Per the task: "expect it to FAIL where the corresponding code fix
    is not yet landed — report which assertions fail and why."

Covered (per the AGENT-NEWFILES brief):
  - shell-fetch fixtures (Archive.org / 404 / docket / legal-shell)            [FIX-DETECTOR]
  - qwen prompt-window clamp                                                   [FIX-DETECTOR]
  - comparative-empty serialization                                           [FIX-DETECTOR]
  - exact-origin overlap fallback                                             [FIX-DETECTOR]
  - quantified parse-failure raise                                            [FIX-DETECTOR]
  - the no-unjudged-release invariant (status set + release_allowed proof)    [INVARIANT]

No network, no live evidence DB. Real captured-class shell strings + the real drb_90 held
manifest fixture are used where available; small representative strings otherwise (§-1.1 / LAW II).
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------------------------- #
# module loaders (the sweep script + the new release-invariant module live OUTSIDE the package)  #
# --------------------------------------------------------------------------------------------- #
def _load_path_module(rel_path: str, mod_name: str):
    path = _REPO_ROOT / rel_path
    spec = importlib.util.spec_from_file_location(mod_name, str(path))
    assert spec is not None and spec.loader is not None, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def sweep_module():
    return _load_path_module("scripts/run_honest_sweep_r3.py", "rhsr3_test")


@pytest.fixture(scope="module")
def invariant_module():
    return _load_path_module("scripts/iarch007_release_invariant_check.py", "iarch007_inv_test")


# =============================================================================================== #
# A1 — shell-fetch fixtures  [FIX-DETECTOR]                                                        #
# The fetch-layer shell detector must flag page-furniture (Archive.org JS wrapper, soft-404,      #
# CourtListener docket index, bare DOI) as shells and pass a real article — keying on             #
# fetch-integrity, NEVER topicality. Fails if `_is_fetch_shell` is absent/inert.                  #
# =============================================================================================== #
_SHELL_FIXTURES = {
    "archive_org_js_wrapper": (
        "<html><head><title>Wayback Machine</title></head>"
        "<body><script>__wbCsp=true;</script><div id='wm-ipp'></div></body></html>"
    ),
    "soft_404_page_not_found": "Page not found",
    "courtlistener_docket_index": "Filing fee: $402.00",
    "bare_doi_stub": "doi:10.1234/adas.liability.2026",
}

_REAL_ARTICLE = (
    "The court held that the manufacturer was liable for design defects in the automated "
    "lane-keeping system. The verdict awarded $240 million in damages, finding the design "
    "unreasonably dangerous under the consumer-expectation test applied by the jury. "
) * 8


@pytest.mark.parametrize("name,body", sorted(_SHELL_FIXTURES.items()))
def test_fix_a1_shell_fetch_is_flagged(name, body):
    """FIX-DETECTOR: every shell fixture is flagged a fetch-layer shell (page furniture)."""
    from src.polaris_graph.retrieval.frame_fetcher import _is_fetch_shell

    is_shell, reason = _is_fetch_shell(body)
    assert is_shell, (
        f"shell fixture {name!r} was NOT flagged as a shell (reason={reason!r}); the A1 "
        "fetch-layer detector is absent or inert (dead-on-arrival)"
    )
    assert reason, "a flagged shell must carry a non-empty reason"


def test_fix_a1_real_article_is_not_a_shell():
    """FIX-DETECTOR: a real article passes — the detector keys on integrity, not topicality."""
    from src.polaris_graph.retrieval.frame_fetcher import _is_fetch_shell

    is_shell, _ = _is_fetch_shell(_REAL_ARTICLE)
    assert not is_shell, "a real article was mis-flagged as a shell (topicality leak?)"


# =============================================================================================== #
# A2/A3 — qwen prompt-window clamp  [FIX-DETECTOR]                                                 #
# The qwen3.6 judge body (max_tokens 262140 vs a 262144 window) must clamp DOWN so prompt +       #
# completion fits — the exact HTTP-400 RC2 fix. Reasoning effort is untouched.                    #
# =============================================================================================== #
@pytest.fixture
def _resolver_env(monkeypatch):
    monkeypatch.setenv("PG_TOKEN_LIMIT_RESOLVER", "1")
    monkeypatch.setenv("PG_TOKEN_LIMIT_ALLOW_FETCH", "1")
    monkeypatch.setenv("PG_TOKEN_LIMIT_SAFETY_MARGIN", "1000")
    from src.polaris_graph.llm import token_limit_resolver as tlr

    table = [{
        "id": "qwen/qwen3.6-35b-a3b",
        "context_length": 262144,
        "top_provider": {"max_completion_tokens": 262144},
    }]
    monkeypatch.setattr(tlr, "_fetch_models_table", lambda: table)
    tlr.reset_cache()
    yield tlr
    tlr.reset_cache()


def test_fix_a2_qwen_judge_max_tokens_clamps_below_window(_resolver_env):
    """FIX-DETECTOR: the judge's 262140 request clamps below the 262144 window."""
    tlr = _resolver_env
    prompt_tokens = 5000
    allowed = tlr.compute_allowed_max_tokens(
        "qwen/qwen3.6-35b-a3b", prompt_tokens, 262140, apply_completion_cap=True
    )
    assert allowed < 262140, "judge max_tokens did not clamp (the qwen HTTP-400 fix is inert)"
    assert prompt_tokens + allowed < 262144, "clamped budget still overruns the window (would 400)"


def test_fix_a2_finalize_body_chokepoint_clamps(_resolver_env):
    """FIX-DETECTOR: the shared finalize_body chokepoint mutates body['max_tokens'] down."""
    tlr = _resolver_env
    body = {"model": "qwen/qwen3.6-35b-a3b", "max_tokens": 262140, "messages": []}
    tlr.finalize_body(body, "qwen/qwen3.6-35b-a3b", 5000, apply_completion_cap=True)
    assert body["max_tokens"] < 262140, "finalize_body did not clamp (chokepoint bypassed)"


# =============================================================================================== #
# A5 — exact-origin overlap fallback  [FIX-DETECTOR]                                               #
# A drifted REAL origin (no exact sub-query match) is recovered by the content-word overlap        #
# fallback instead of orphaned; an unrelated origin stays orphaned (content-keyed, not blanket).   #
# =============================================================================================== #
class _Sec:
    def __init__(self, idxs):
        self.sub_query_indices = idxs


# A drifted origin: a STORM expansion that string-equals NO planned sub-query (so the exact
# match is empty AND `origin_matches_any` is False), with a real STATEMENT/direct_quote that
# shares >= 2 content words with sub_query 0 -> the row-content overlap fallback credits it.
_DRIFTED_ROW = {
    "query_origin": "storm_expansion_drifted_origin_no_exact_match",
    "statement": "Liability allocation for automated driving crashes assigns fault.",
    "direct_quote": "the manufacturer bears liability for the automated driving system",
}
_SUBQ = ["liability allocation for automated driving system crashes"]


def test_fix_a5_drifted_origin_recovered_by_overlap_fallback(monkeypatch):
    """FIX-DETECTOR: a drifted real origin routes to the right section via row-content overlap."""
    monkeypatch.setenv("PG_PLAN_SUFFICIENCY_ORIGIN_DRIFT_FALLBACK", "1")
    from src.polaris_graph.adequacy.plan_sufficiency_gate import relevant_section_indices

    matched = relevant_section_indices(dict(_DRIFTED_ROW), [_Sec([0])], list(_SUBQ))
    assert 0 in matched, (
        "a drifted real origin was ORPHANED (row-content overlap fallback did not fire) — A5 is "
        "dead-on-arrival; the evidence row would route to no section"
    )


def test_fix_a5_facet_level_drift_fallback(monkeypatch):
    """FIX-DETECTOR: the facet-level fallback (_facets_matched_for_row) also recovers drift."""
    monkeypatch.setenv("PG_PLAN_SUFFICIENCY_ORIGIN_DRIFT_FALLBACK", "1")
    from src.polaris_graph.adequacy.plan_sufficiency_gate import _facets_matched_for_row

    facets = _facets_matched_for_row(dict(_DRIFTED_ROW), _Sec([0]), list(_SUBQ))
    assert 0 in facets, "A5 facet-level drift fallback did not credit the matching facet"


def test_fix_a5_contentless_row_stays_orphaned(monkeypatch):
    """FIX-DETECTOR: the fallback is content-keyed — a row with no usable content is NOT credited."""
    monkeypatch.setenv("PG_PLAN_SUFFICIENCY_ORIGIN_DRIFT_FALLBACK", "1")
    from src.polaris_graph.adequacy.plan_sufficiency_gate import relevant_section_indices

    row = dict(_DRIFTED_ROW, statement="x", direct_quote="")
    assert 0 not in relevant_section_indices(row, [_Sec([0])], list(_SUBQ)), (
        "a content-less row was wrongly credited — the fallback must be content-keyed"
    )


def test_fix_a5_fallback_off_is_byte_identical_legacy(monkeypatch):
    """FIX-DETECTOR: explicit OFF reproduces the legacy strict-exact-only behavior (orphans drift)."""
    monkeypatch.setenv("PG_PLAN_SUFFICIENCY_ORIGIN_DRIFT_FALLBACK", "0")
    from src.polaris_graph.adequacy.plan_sufficiency_gate import relevant_section_indices

    # Legacy: a drifted origin with no EXACT match is orphaned (the pre-A5 bug, preserved on OFF).
    assert relevant_section_indices(dict(_DRIFTED_ROW), [_Sec([0])], list(_SUBQ)) == [], (
        "with the fallback explicitly OFF, a drifted origin must orphan (legacy byte-identical)"
    )


# =============================================================================================== #
# A10 — quantified parse-failure raise  [FIX-DETECTOR]                                             #
# A typed SpecProviderTransportError must exist so a transport/parse fault raises (lands in the    #
# retry lane) instead of laundering as a benign Writer decline (bare None).                        #
# =============================================================================================== #
def test_fix_a10_spec_provider_transport_error_exists(sweep_module):
    """FIX-DETECTOR (symbol-presence): the typed transport error class exists and is raisable.

    HONEST SCOPE: the actual A10 raise (the `_q_spec_provider` empty/no-JSON path RAISING this
    instead of returning None) is INLINE in an async closure (not unit-callable); the behavioral
    raise-path is covered by the A19 live canary. This proxy guards the typed contract exists.
    """
    err = getattr(sweep_module, "SpecProviderTransportError", None)
    assert err is not None, "SpecProviderTransportError missing — A10 fail-loud split not landed"
    assert isinstance(err, type) and issubclass(err, Exception), "not an Exception subclass"
    # It must be raisable/catchable as the typed contract A10 specifies.
    with pytest.raises(err):
        raise err("empty/no-JSON spec body")


def test_fix_a10_reserved_empty_transport_status_present():
    """FIX-DETECTOR (symbol-presence): the reserved QUANTIFIED_STATUS_EMPTY_TRANSPORT status exists."""
    from src.polaris_graph.generator import quantified_analysis as qa

    assert hasattr(qa, "QUANTIFIED_STATUS_EMPTY_TRANSPORT"), (
        "QUANTIFIED_STATUS_EMPTY_TRANSPORT reserved status missing"
    )


# =============================================================================================== #
# A4 - comparative-empty serialization  [BEHAVIORAL]                                               #
# A section ATTEMPTED (evidence rows assigned) but emitting ZERO verified sentences must be        #
# serialized as a non-verdict stub (attempted=True, reason=resolved_emitted==0) instead of        #
# vanishing - exactly drb_90's "Comparative Assessment".                                           #
#                                                                                                  #
# Both load-bearing pieces are now unit-callable and tested for REAL behavior (no source-text     #
# grep - per -1.1 a source-presence check is NOT a quality signal): the pure stub builder         #
# (build_attempted_zero_emit_section_stub) returns the exact non-verdict dict, and the zero-emit  #
# trigger (resolve_provenance_to_citations_with_count) returns emitted_count==0 on an empty       #
# kept-sentence list - which is what drives is_gap_stub = (resolved_emitted == 0). End-to-end     #
# coverage over a finished run dir remains the A19 live canary + the A18 artifact invariant.      #
# =============================================================================================== #
def test_a4_comparative_empty_stub_builder_behavioral(sweep_module):
    """BEHAVIORAL (calls the real pure helper, not a source-text grep — §-1.1): the A4 zero-emit
    stub builder returns the non-verdict serialization dict.

    An ATTEMPTED section that emits zero verified sentences MUST serialize attempted=True +
    reason=resolved_emitted==0 with a present-but-empty `dropped` list (so the downstream
    per-reason tally loop stays byte-identical), instead of vanishing from verification_details.json
    (drb_90's "Comparative Assessment").
    """
    build = getattr(sweep_module, "build_attempted_zero_emit_section_stub", None)
    assert build is not None, "A4 stub builder missing — an attempted-but-zero-emit section vanishes"
    stub = build("Comparative Assessment", False, ["ev1", "ev2"])
    assert stub["attempted"] is True
    assert stub["reason"] == "resolved_emitted==0"
    assert stub["total_kept"] == 0 and stub["kept"] == []
    assert stub["dropped"] == [], (
        "`dropped` must be present-but-empty so the per-reason tally loop stays byte-identical"
    )
    assert stub["ev_ids_assigned"] == ["ev1", "ev2"], "the attempted section's assigned rows are disclosed"


def test_a4_zero_emit_trigger_is_behavioral():
    """BEHAVIORAL (calls the real resolver, not a source-text grep — §-1.1): a zero-surviving
    section resolves to emitted_count==0, which is the gap-stub trigger.

    `is_gap_stub = (resolved_emitted == 0)` is driven by the resolver's emitted count, NOT the
    pre-resolve kept-list length (the F10 honesty fix). Empty kept_sentences MUST resolve to
    emitted_count==0 — proven by calling the real resolver, so a comparative section with rows but
    zero surviving spans is marked a gap stub instead of shipping an empty body as non-stub.
    """
    from src.polaris_graph.generator.provenance_generator import (
        resolve_provenance_to_citations_with_count,
    )

    _rendered, biblio, emitted = resolve_provenance_to_citations_with_count([], {})
    assert emitted == 0, (
        "an empty kept-sentence section must resolve to emitted_count==0 (the is_gap_stub trigger)"
    )
    assert biblio == [], "a zero-emit section yields no citations"


# =============================================================================================== #
# NO-UNJUDGED-RELEASE INVARIANT  [INVARIANT — must hold NOW and after every future fix]            #
# =============================================================================================== #
def test_invariant_seam_status_in_allowed_set_never_success(sweep_module):
    """INVARIANT: a judge seam-error never resolves to `success`; it lands in the allowed set
    {released_with_disclosed_gaps, released_insufficient_safety_evidence, abort_*}.

    This is a PERMANENT property. The legacy fail-closed seam path (abort_four_role_release_held)
    already satisfied it; the A2 rescue (released_with_disclosed_gaps) also satisfies it. Encoded
    as set-membership so it can never become a brittle fix-detector.
    """
    from src.polaris_graph.roles.release_policy import (
        STATUS_RELEASED_INSUFFICIENT_SAFETY,
        STATUS_RELEASED_WITH_DISCLOSED_GAPS,
        STATUS_SUCCESS,
    )

    build = sweep_module.build_seam_release_outcome

    class _Tok:
        def __init__(self, eid):
            self.evidence_id = eid

    class _SV:
        def __init__(self, eids):
            self.tokens = [_Tok(e) for e in eids]

    class _Section:
        def __init__(self, eids):
            self.kept_sentences_pre_resolve = [_SV(eids)]

    evidence_for_gen = [{"evidence_id": "ev_1"}, {"evidence_id": "ev_2"}]
    for is_clinical in (False, True):
        outcome, _withheld, _ = build(
            sections=[_Section(["ev_1", "ev_2"])],
            evidence_for_gen=evidence_for_gen,
            is_clinical=is_clinical,
            seam_held_reason="seam_error:HTTPStatusError:400",
        )
        assert outcome.status != STATUS_SUCCESS, (
            f"seam (clinical={is_clinical}) resolved to SUCCESS — un-judged content marked verified"
        )
        assert (
            outcome.status
            in {STATUS_RELEASED_WITH_DISCLOSED_GAPS, STATUS_RELEASED_INSUFFICIENT_SAFETY}
            or outcome.status.startswith("abort")
        ), f"seam status {outcome.status!r} is outside the allowed no-unjudged-release set"


def test_invariant_seam_disclosed_gaps_non_empty(sweep_module):
    """INVARIANT: a seam outcome ALWAYS carries a non-empty disclosed_gaps list.

    A non-empty disclosed_gaps is precisely what forces release_policy to resolve to
    released_with_disclosed_gaps and never `success` (release_policy.py ships SUCCESS only on an
    EMPTY disclosed_gaps list). Permanent property of any honest seam disposition.
    """
    build = sweep_module.build_seam_release_outcome

    class _Tok:
        def __init__(self, eid):
            self.evidence_id = eid

    class _SV:
        def __init__(self, eids):
            self.tokens = [_Tok(e) for e in eids]

    class _Section:
        def __init__(self, eids):
            self.kept_sentences_pre_resolve = [_SV(eids)]

    outcome, _w, _r = build(
        sections=[_Section(["ev_1"])],
        evidence_for_gen=[{"evidence_id": "ev_1"}],
        is_clinical=False,
        seam_held_reason="seam_error:HTTPStatusError:400",
    )
    assert outcome.disclosed_gaps, "seam outcome had an EMPTY disclosed_gaps -> would ship success"
    assert any(sweep_module.SEAM_GAP_UNADJUDICATED in g for g in outcome.disclosed_gaps), (
        "the seam disclosure must carry the four_role_seam_unadjudicated label"
    )


def test_invariant_seam_fabricated_identity_withholds_body(sweep_module):
    """INVARIANT: a cited identity not in the evidence pool withholds the body (no un-screened
    fabricated citation ships on a seam error). The fabrication latch lives only in the judge
    lane, so the standalone seam screen is the compensating control — permanent safety floor.
    """
    build = sweep_module.build_seam_release_outcome

    class _Tok:
        def __init__(self, eid):
            self.evidence_id = eid

    class _SV:
        def __init__(self, eids):
            self.tokens = [_Tok(e) for e in eids]

    class _Section:
        def __init__(self, eids):
            self.kept_sentences_pre_resolve = [_SV(eids)]

    outcome, withheld, _ = build(
        sections=[_Section(["ev_1", "ev_FAKE_NOT_IN_POOL"])],
        evidence_for_gen=[{"evidence_id": "ev_1"}],
        is_clinical=False,
        seam_held_reason="seam_error:HTTPStatusError:400",
    )
    assert withheld, "a fabricated cited identity did NOT withhold the body (un-screened fab ships)"
    from src.polaris_graph.roles.release_policy import STATUS_SUCCESS

    assert outcome.status != STATUS_SUCCESS, "fabricated-identity seam resolved to SUCCESS"


def test_invariant_release_policy_empty_disclosed_gaps_only_path_to_success():
    """INVARIANT: compute_release_outcome ships `success` ONLY on EMPTY disclosed_gaps; any
    non-empty disclosed_gaps => released_with_disclosed_gaps. This is the structural reason the
    seam rescue's non-empty gap can never become a false SUCCESS. Permanent policy property.
    """
    from src.polaris_graph.roles.release_policy import (
        ReleaseDecision,
        STATUS_RELEASED_WITH_DISCLOSED_GAPS,
        STATUS_SUCCESS,
        compute_release_outcome,
    )

    # A clean decision with always-release ON + NO disclosed gaps -> success.
    clean = ReleaseDecision(
        release_allowed=True, held_reasons=[], gaps=[], needs_rewrite=[],
        fabricated_occurrence_latched=False,
    )
    out_clean = compute_release_outcome(
        clean, zero_verified=False, zero_usable_evidence=False,
        safety_floor_insufficient=False, coverage_fraction=1.0, always_release=True,
    )
    assert out_clean.status == STATUS_SUCCESS

    # A decision carrying a non-hard held reason -> a disclosed gap -> NOT success.
    from src.polaris_graph.roles.release_policy import (
        _REASON_UNSUPPORTED_RESIDUAL_BELOW_COVERAGE,
    )
    gapped = ReleaseDecision(
        release_allowed=False,
        held_reasons=[_REASON_UNSUPPORTED_RESIDUAL_BELOW_COVERAGE],
        gaps=[], needs_rewrite=[], fabricated_occurrence_latched=False,
    )
    out_gapped = compute_release_outcome(
        gapped, zero_verified=False, zero_usable_evidence=False,
        safety_floor_insufficient=False, coverage_fraction=0.5, always_release=True,
    )
    assert out_gapped.status == STATUS_RELEASED_WITH_DISCLOSED_GAPS
    assert out_gapped.status != STATUS_SUCCESS


# --- the A18 artifact invariant (the conformance check the CI gate runs) ----------------------- #
def test_invariant_a18_success_without_d8_is_a_violation(invariant_module):
    """INVARIANT: an artifact stamped success with NO D8 adjudication is a violation (the A2
    catastrophe path). The check must flag it."""
    v = invariant_module.check_manifest({
        "status": "success", "release_allowed": True,
        "four_role_evaluation": {"final_verdicts": {}},
    })
    assert v, "a success manifest with empty final_verdicts must be a release-invariant violation"


def test_invariant_a18_success_with_d8_passes(invariant_module):
    """INVARIANT: a success artifact WITH real D8 verdicts satisfies the invariant."""
    v = invariant_module.check_manifest({
        "status": "success", "release_allowed": True,
        "four_role_evaluation": {"final_verdicts": {"c1": "VERIFIED", "c2": "PARTIAL"}},
    })
    assert v == [], f"a judged success manifest must satisfy the invariant; got {v}"


def test_invariant_a18_seam_disclosed_gaps_passes(invariant_module):
    """INVARIANT: the PROVEN seam rescue (seam gap + a passed compensating screen, no D8) passes."""
    v = invariant_module.check_manifest({
        "status": "released_with_disclosed_gaps", "release_allowed": True,
        "four_role_evaluation": {"final_verdicts": {}},
        "release_disclosure": {
            "disclosed_gaps": ["four_role_seam_unadjudicated: judge unreachable"],
            "adjudicated": False, "body_withheld": False,
            "compensating_screen_passed": True,
        },
    })
    assert v == [], f"the proven seam rescue must satisfy the invariant; got {v}"


def test_invariant_a18_seam_token_without_proof_violates(invariant_module):
    """INVARIANT (iarch007 SWEEP-P0): the seam token WITHOUT a withheld body or a passed
    compensating screen is NOT proof — the seam body would ship un-judged AND un-screened."""
    v = invariant_module.check_manifest({
        "status": "released_with_disclosed_gaps", "release_allowed": True,
        "four_role_evaluation": {"final_verdicts": {}},
        "release_disclosure": {
            "disclosed_gaps": ["four_role_seam_unadjudicated: judge unreachable"],
            "adjudicated": False, "body_withheld": False,
            "compensating_screen_passed": False,
        },
    })
    assert v, "a seam token with no withheld body and no passed screen must be a violation"


def test_invariant_a18_arbitrary_gap_is_not_seam_proof(invariant_module):
    """INVARIANT (iarch007 SWEEP-P0): an arbitrary non-seam disclosed gap is NOT seam proof
    (the pre-fix `any non-empty disclosed_gaps` bypass is closed)."""
    v = invariant_module.check_manifest({
        "status": "released_with_disclosed_gaps", "release_allowed": True,
        "four_role_evaluation": {"final_verdicts": {}},
        "release_disclosure": {
            "disclosed_gaps": ["credibility_unscored: 3 sources at neutral weight"],
            "adjudicated": False, "body_withheld": False,
            "compensating_screen_passed": False,
        },
    })
    assert v, "a non-seam disclosed gap must not satisfy the seam-rescue proof"


def test_invariant_a18_disclosed_gaps_without_disclosure_violates(invariant_module):
    """INVARIANT: released_with_disclosed_gaps with NO disclosure AND no D8 is a silent release."""
    v = invariant_module.check_manifest({
        "status": "released_with_disclosed_gaps", "release_allowed": True,
        "four_role_evaluation": {"final_verdicts": {}},
    })
    assert v, "a disclosed-gaps release with no disclosure and no D8 must be a violation"


def test_invariant_a18_partial_release_without_d8_violates(invariant_module):
    """INVARIANT (iarch007 SWEEP-P0 #2): release_allowed=true on a NON-abort, non-strict,
    non-disclosed status (e.g. partial_saturation) with empty final_verdicts and no proven seam is a
    silent un-judged release — the partial_*/unknown hole the pre-fix checker let through entirely.
    The check must flag it."""
    v = invariant_module.check_manifest({
        "status": "partial_saturation", "release_allowed": True,
        "four_role_evaluation": {"final_verdicts": {}},
    })
    assert v, "release_allowed=true on partial_saturation with no D8/seam proof must be a violation"


def test_invariant_a18_partial_release_with_d8_passes(invariant_module):
    """INVARIANT: a partial_* status that DID adjudicate (non-empty final_verdicts) satisfies the
    invariant — the proof demand is about real judging, not the status label."""
    v = invariant_module.check_manifest({
        "status": "partial_saturation", "release_allowed": True,
        "four_role_evaluation": {"final_verdicts": {"c1": "VERIFIED"}},
    })
    assert v == [], f"a judged partial release must satisfy the invariant; got {v}"


def test_invariant_a18_partial_not_released_passes(invariant_module):
    """INVARIANT: a partial_* status that did NOT release (release_allowed=false) ships nothing and
    satisfies the invariant — the fail-closed disposition is never tripped."""
    v = invariant_module.check_manifest({
        "status": "partial_saturation", "release_allowed": False,
        "four_role_evaluation": {"final_verdicts": {}},
    })
    assert v == [], f"a non-released partial status must satisfy the invariant; got {v}"


def test_release_path_no_disclosure_with_d8_does_not_false_hold(sweep_module):
    """BEHAVIORAL (run-path reconstruction, iarch007 over-strict guard): a release-asserting status
    reached WITHOUT a serialized release_disclosure but WITH real D8 evidence (non-empty
    final_verdicts) must NOT be false-HELD — adjudicated is derived from the judge ACTUALLY running,
    never a blind False. This is the drb_90 empty-report symptom from the over-strict side."""
    from src.polaris_graph.roles.release_policy import assert_release_invariant

    manifest = {
        "status": "success", "release_allowed": True,
        "four_role_evaluation": {"final_verdicts": {"c1": "VERIFIED", "c2": "PARTIAL"}},
        # no release_disclosure (legacy / non-always-release write path)
    }
    outcome = sweep_module.reconstruct_release_outcome_from_manifest(manifest)
    assert outcome.adjudicated is True, "D8 ran (final_verdicts non-empty) -> adjudicated must be True"
    assert_release_invariant(outcome)  # must NOT raise — a genuinely-judged release is never held


def test_release_path_no_disclosure_no_d8_still_fails_closed(sweep_module):
    """BEHAVIORAL (run-path reconstruction): a release-asserting status with NEITHER a serialized
    release_disclosure NOR D8 evidence (empty final_verdicts) is a truly un-judged release and MUST
    still FAIL CLOSED — the over-strict guard does NOT reopen the fail-open Codex closed."""
    from src.polaris_graph.roles.release_policy import (
        ReleaseInvariantError, assert_release_invariant,
    )

    manifest = {
        "status": "success", "release_allowed": True,
        "four_role_evaluation": {"final_verdicts": {}},
    }
    outcome = sweep_module.reconstruct_release_outcome_from_manifest(manifest)
    assert outcome.adjudicated is False, "no disclosure AND no D8 evidence -> adjudicated must be False"
    with pytest.raises(ReleaseInvariantError):
        assert_release_invariant(outcome)


def test_release_path_serialized_seam_adjudicated_false_is_honored(sweep_module):
    """BEHAVIORAL: a serialized release_disclosure recording the seam (adjudicated=False) is read
    HONESTLY (never overridden by the D8-derive branch) — the seam stays un-adjudicated."""
    manifest = {
        "status": "released_with_disclosed_gaps", "release_allowed": True,
        "four_role_evaluation": {"final_verdicts": {}},
        "release_disclosure": {
            "adjudicated": False, "body_withheld": True,
            "disclosed_gaps": ["four_role_seam_unadjudicated: judge unreachable"],
        },
    }
    outcome = sweep_module.reconstruct_release_outcome_from_manifest(manifest)
    assert outcome.adjudicated is False, "a serialized adjudicated=False (seam) must be honored, not derived"
    assert outcome.body_withheld is True


def test_invariant_a18_real_drb90_held_manifest_passes(invariant_module):
    """INVARIANT: the REAL drb_90 held run (abort_four_role_release_held, release_allowed=False,
    final_verdicts empty) satisfies the invariant — nothing shipped, the correct fail-closed
    disposition. This is the negative-control that proves the check does not over-fire on a
    legitimately-held run."""
    fixture = _REPO_ROOT / "tests" / "fixtures" / "drb90_redaction" / "manifest.json"
    # The fixture is git-tracked (tests/fixtures/drb90_redaction/manifest.json); a missing file is a
    # REAL failure (a dropped fixture), NOT a skip-worthy condition (iarch007 A11 P1: the conditional
    # skip masked an absent fixture, letting the negative-control silently not run).
    assert fixture.is_file(), (
        f"the git-tracked real drb_90 fixture is MISSING at {fixture} — a dropped fixture must fail "
        "loudly, not skip the negative-control"
    )
    manifest = json.loads(fixture.read_text(encoding="utf-8"))
    assert manifest.get("status") == "abort_four_role_release_held"
    assert manifest.get("release_allowed") is False
    v = invariant_module.check_manifest(manifest)
    assert v == [], f"the real drb_90 HELD manifest must satisfy the invariant; got {v}"


def test_invariant_a18_self_test_green(invariant_module):
    """INVARIANT: the release-invariant module's own offline self-test is green."""
    assert invariant_module._self_test() == 0, "the A18 release-invariant self-test failed"


def test_invariant_a18_release_allowed_on_abort_violates(invariant_module):
    """INVARIANT: release_allowed=true with an abort_* status is a self-contradiction -> violation."""
    v = invariant_module.check_manifest({
        "status": "abort_no_verified_sections", "release_allowed": True,
    })
    assert v, "release_allowed=true on an abort status must be a violation (binding contradiction)"
