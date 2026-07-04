"""G2 run-sweep blocker tests — fail-open readiness gates in scripts/run_honest_sweep_r3.py.

Forensic: dual Claude+Codex 2026-06-12, .codex/I-bench-veracity-003-forensic/. The drb_72
benchmark run surfaced a cluster of run-sweep gates that FAIL OPEN: a skewed corpus is accepted
as sweep-ready with only a disclosure (#1235), a V30-contract Phase-2 fault silently degrades to
the legacy generator (#1238), a CITED bibliography entry renders a blank URL (#1239), the Methods
tier-mix "11%/12%" disagrees with the Limitations "13%" (#1242), a manifest can read `success`
without the 4-role D8 audit ever running (#1226), and an enabled-but-empty quantified
differentiator passes silently (#1237).

Fix: ONE shared env ``PG_BENCHMARK_STRICT_GATES`` (default "0"/off) turns the four fail-open paths
LOUD (#1235/#1238/#1226/#1237); #1239 and #1242 get their own narrow flags. OFF == byte-identical.

These tests exercise the PURE run-sweep helpers directly (no async pipeline, no network, no spend):
  flag-OFF identity  — every shared-flag helper returns the no-op value when strict is off
  flag-ON loud-abort — each strict helper returns the block/raise/hold signal when strict is on
  #1242 single-src   — the tier-mix helper returns ONE consistent percentage used everywhere
  #1239 bib render   — flag-OFF byte-identical; flag-ON relabels a cited-but-blank entry to a gap

FAITHFULNESS: untouched. None of these helpers touch strict_verify / the NLI judge / the 4-role D8
release decision / provenance — they only forbid mislabeling an un-audited, skewed, or empty run as
ready/success, or relabel a locator-less citation DOWN to a disclosed gap (never fabricating a URL).
Plain assertions, no unittest.mock.
"""
from __future__ import annotations

import os

import scripts.run_honest_sweep_r3 as sweep


# ── env helper: set for the body, restore exactly on exit (no mock) ──────────────
class _env:
    def __init__(self, **kv: "str | None") -> None:
        self._kv = kv
        self._prev: dict[str, "str | None"] = {}

    def __enter__(self) -> "_env":
        for k, v in self._kv.items():
            self._prev[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return self

    def __exit__(self, *exc: object) -> None:
        for k, v in self._prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ── shared strict-gate reader (default OFF) ──────────────────────────────────────
def test_shared_strict_flag_default_off():
    with _env(PG_BENCHMARK_STRICT_GATES=None):
        assert sweep._benchmark_strict_gates_on() is False


def test_shared_strict_flag_on():
    with _env(PG_BENCHMARK_STRICT_GATES="1"):
        assert sweep._benchmark_strict_gates_on() is True


def test_shared_strict_flag_explicit_zero_is_off():
    # An explicit "0" / "false" must NOT enable the gate (off == identical).
    for val in ("0", "false", "False", "no", ""):
        with _env(PG_BENCHMARK_STRICT_GATES=val):
            assert sweep._benchmark_strict_gates_on() is False


# ── #1235 corpus-skew readiness gate ─────────────────────────────────────────────
def test_1235_corpus_skew_off_never_blocks():
    # strict OFF -> the weighted-corpus auto-approve is never bypassed, regardless of deviation.
    assert sweep._corpus_skew_blocks_ready(False, True) is False
    assert sweep._corpus_skew_blocks_ready(False, False) is False


def test_1235_corpus_skew_on_blocks_only_material_deviation():
    # strict ON -> bypass the weighted auto-approve ONLY when there is a material deviation
    # (a clean corpus still auto-approves; off==identical for the no-deviation case).
    assert sweep._corpus_skew_blocks_ready(True, True) is True
    assert sweep._corpus_skew_blocks_ready(True, False) is False


# ── drb_72 weighted-gate proceed-on-skew (PG_WEIGHTED_GATE_PROCEED_ON_SKEW) ──────
# A hard tier-COUNT refusal is itself the §-1.3 filter-by-number anti-pattern. When the
# kill-switch is ON *and* the weighted-corpus gate is ON *and* the corpus is non-empty, a
# MATERIAL tier skew DISCLOSES-and-PROCEEDS instead of aborting. A genuinely EMPTY corpus still
# blocks. Default-OFF => byte-identical. These exercise the PURE helpers directly (no pipeline).
def test_drb72_proceed_on_skew_flag_default_off():
    with _env(PG_WEIGHTED_GATE_PROCEED_ON_SKEW=None):
        assert sweep._weighted_gate_proceed_on_skew_enabled() is False


def test_drb72_proceed_on_skew_flag_on():
    with _env(PG_WEIGHTED_GATE_PROCEED_ON_SKEW="1"):
        assert sweep._weighted_gate_proceed_on_skew_enabled() is True


def test_drb72_proceed_on_skew_flag_explicit_falsy_is_off():
    for val in ("0", "false", "False", "no", ""):
        with _env(PG_WEIGHTED_GATE_PROCEED_ON_SKEW=val):
            assert sweep._weighted_gate_proceed_on_skew_enabled() is False


def test_drb72_corpus_skew_positional_call_byte_identical():
    # The pre-existing #1235 positional signature is byte-identical: the three new keyword
    # params default False, so a positional call still refuses a material deviation under strict.
    assert sweep._corpus_skew_blocks_ready(True, True) is True
    assert sweep._corpus_skew_blocks_ready(True, False) is False
    assert sweep._corpus_skew_blocks_ready(False, True) is False


def test_drb72_corpus_skew_proceeds_when_on_and_nonempty():
    # flag ON + weighted gate ON + material deviation + NON-empty corpus -> DISCLOSE-and-PROCEED
    # (returns False -> the caller's weighted auto-approve stands, no tier-COUNT refusal).
    assert sweep._corpus_skew_blocks_ready(
        True, True, weighted_gate_on=True, proceed_on_skew=True, corpus_nonempty=True,
    ) is False


def test_drb72_corpus_skew_still_blocks_empty_corpus():
    # flag ON + weighted gate ON + material deviation but EMPTY corpus (corpus-ZERO floor) ->
    # STILL blocks (returns True). A genuinely empty corpus is never proceeded-on.
    assert sweep._corpus_skew_blocks_ready(
        True, True, weighted_gate_on=True, proceed_on_skew=True, corpus_nonempty=False,
    ) is True


def test_drb72_corpus_skew_flag_off_still_blocks_material_deviation():
    # kill-switch OFF (proceed_on_skew=False) -> byte-identical to #1235: strict + material
    # deviation still blocks even with the weighted gate on and a non-empty corpus.
    assert sweep._corpus_skew_blocks_ready(
        True, True, weighted_gate_on=True, proceed_on_skew=False, corpus_nonempty=True,
    ) is True


def test_drb72_corpus_skew_needs_weighted_gate_on():
    # proceed-on-skew requires the weighted-corpus gate itself to be ON; with it OFF the strict
    # tier-COUNT refusal stands (returns True) even when the kill-switch is on.
    assert sweep._corpus_skew_blocks_ready(
        True, True, weighted_gate_on=False, proceed_on_skew=True, corpus_nonempty=True,
    ) is True


def test_drb72_corpus_skew_no_material_deviation_never_blocks():
    # No material deviation -> never blocks regardless of the new params (a clean corpus
    # auto-approves).
    assert sweep._corpus_skew_blocks_ready(
        True, False, weighted_gate_on=True, proceed_on_skew=True, corpus_nonempty=True,
    ) is False


def test_drb72_proceed_on_skew_disclosure_fires_and_records_skew():
    # MUST-DISCLOSE: when the proceed-on-skew path fires, the discrete record carries the tier
    # skew (had_material_deviation + the tier counts/fractions), never hides it.
    disc = sweep._weighted_corpus_proceed_on_skew_disclosure(
        strict=True,
        has_material_deviation=True,
        weighted_gate_on=True,
        proceed_on_skew=True,
        corpus_nonempty=True,
        tier_counts={"T1": 4, "T2": 0, "T3": 4, "T4": 35, "T6": 37, "T7": 15},
        tier_fractions={"T4": 0.35, "T6": 0.37},
        total_sources=95,
    )
    assert disc is not None
    assert disc["action"] == "disclose_and_proceed"
    assert disc["gate"] == "PG_WEIGHTED_GATE_PROCEED_ON_SKEW"
    assert disc["had_material_deviation"] is True
    assert disc["corpus_nonempty"] is True
    assert disc["total_sources"] == 95
    # the skew itself is present in the disclosure (not a bare boolean)
    assert disc["tier_counts"]["T3"] == 4
    assert disc["tier_counts"]["T4"] == 35
    assert "§-1.3" in disc["reason"] and "DISCLOSED" in disc["reason"]


def test_drb72_proceed_on_skew_disclosure_none_when_not_fired():
    # None (=> nothing attached => byte-identical OFF) whenever any precondition is missing.
    base = dict(
        strict=True, has_material_deviation=True, weighted_gate_on=True,
        proceed_on_skew=True, corpus_nonempty=True,
    )
    # kill-switch off
    assert sweep._weighted_corpus_proceed_on_skew_disclosure(**{**base, "proceed_on_skew": False}) is None
    # weighted gate off
    assert sweep._weighted_corpus_proceed_on_skew_disclosure(**{**base, "weighted_gate_on": False}) is None
    # empty corpus
    assert sweep._weighted_corpus_proceed_on_skew_disclosure(**{**base, "corpus_nonempty": False}) is None
    # strict gates off
    assert sweep._weighted_corpus_proceed_on_skew_disclosure(**{**base, "strict": False}) is None
    # no material deviation
    assert sweep._weighted_corpus_proceed_on_skew_disclosure(**{**base, "has_material_deviation": False}) is None


# ── #1238 V30 contract broad-except ──────────────────────────────────────────────
def test_1238_v30_off_never_reraises():
    # strict OFF -> the V30 fault falls back to legacy (no re-raise), as today.
    assert sweep._v30_should_reraise(False, False) is False
    assert sweep._v30_should_reraise(False, True) is False


def test_1238_v30_on_reraises_unless_fallback_allowed():
    # strict ON + fallback NOT allowed -> fatal (re-raise). strict ON + fallback allowed -> legacy.
    assert sweep._v30_should_reraise(True, False) is True
    assert sweep._v30_should_reraise(True, True) is False


# ── #1226 no success before D8 ───────────────────────────────────────────────────
def test_1226_d8_off_never_blocks_success():
    # strict OFF -> a `success` manifest without D8 is left alone (legacy single-evaluator path).
    assert sweep._d8_success_without_audit(False, "success", False) is False


def test_1226_d8_on_blocks_success_without_audit():
    # strict ON + would-be success + D8 did NOT run -> must convert to a loud hold.
    assert sweep._d8_success_without_audit(True, "success", False) is True


def test_1226_d8_on_allows_success_when_audit_ran():
    # strict ON + success + D8 DID run -> allowed (the audit produced a binding decision).
    assert sweep._d8_success_without_audit(True, "success", True) is False


def test_1226_d8_on_ignores_non_success_status():
    # A partial/abort status is already a non-success signal; the guard must not touch it.
    assert sweep._d8_success_without_audit(True, "partial_thin_corpus", False) is False
    assert sweep._d8_success_without_audit(True, "abort_no_sources", False) is False


# ── #1237 quantified readiness ───────────────────────────────────────────────────
def test_1237_quantified_off_never_fails():
    # strict OFF -> never fail readiness regardless of the quantified telemetry.
    assert sweep._quantified_readiness_failed(False, True, {"fired": False}) is False
    assert sweep._quantified_readiness_failed(False, True, None) is False


def test_1237_quantified_not_force_enabled_never_fails():
    # strict ON but quantified NOT force-enabled -> the differentiator was optional; never fail.
    assert sweep._quantified_readiness_failed(True, False, {"fired": False}) is False
    assert sweep._quantified_readiness_failed(True, False, None) is False


def test_1237_quantified_force_on_but_empty_fails():
    # strict ON + force-enabled + produced NO verified output (fired=False / no telemetry) -> fail.
    assert sweep._quantified_readiness_failed(True, True, {"fired": False}) is True
    assert sweep._quantified_readiness_failed(True, True, None) is True
    # Robust to the typed-status strings quantified_analysis.py emits: keys on `fired`, so an
    # empty_transport / parse_error / declined telemetry without a true `fired` still fails.
    assert sweep._quantified_readiness_failed(
        True, True, {"quantified_status": "empty_transport", "fired": False}
    ) is True


def test_1237_quantified_force_on_and_fired_passes():
    # strict ON + force-enabled + the differentiator FIRED -> readiness passes.
    assert sweep._quantified_readiness_failed(True, True, {"fired": True}) is False


# ── I-wire-003 B4 (#1317): canary distinguishes ran+honest-empty from silently-broke ──
def test_b4_canary_honest_empty_does_not_fail_readiness():
    # The differentiator RAN and honestly produced nothing: an explicit Writer decline
    # (declined_no_spec / no_spec_returned) or every computed sentence dropped by Regime C
    # (no_verified_sentences). These are legitimate non-fires the run DISCLOSES — they must
    # NOT trip the readiness abort (the #1237 fired-only gate wrongly lumped them with breakage).
    for status_key, status_val in (
        ("quantified_status", "declined_no_spec"),
        ("firing_status", "no_spec_returned"),
        ("firing_status", "no_verified_sentences"),
    ):
        tel = {"fired": False, status_key: status_val}
        assert sweep._quantified_readiness_failed(True, True, tel) is False, status_val


def test_b4_canary_broke_or_skipped_fails_readiness():
    # The differentiator SILENTLY BROKE or was SKIPPED: a transport/parse fault, a malformed
    # spec rejected by build_quantified_spec, a sandbox execution failure, or no telemetry at
    # all (skipped). Each must FAIL readiness loudly (force-on but no clean differentiator).
    for status_key, status_val in (
        ("quantified_status", "parse_error"),
        ("quantified_status", "empty_transport"),
        ("firing_status", "spec_provider_error"),
        ("firing_status", "spec_validation_rejected"),
        ("firing_status", "execution_failed"),
    ):
        tel = {"fired": False, status_key: status_val}
        assert sweep._quantified_readiness_failed(True, True, tel) is True, status_val
    # No telemetry object at all == force-enabled but the block was skipped -> fail.
    assert sweep._quantified_readiness_failed(True, True, None) is True


def test_b4_canary_unclassifiable_no_op_falls_back_to_fail():
    # An older / unrecognized telemetry shape with no typed status AND not fired: the gate must
    # NOT silently pass it — it falls back to the #1237 fired-only semantics (fail loud), so a
    # shape the classifier cannot read can never become a silent green.
    assert sweep._quantified_readiness_failed(
        True, True, {"fired": False, "firing_status": "some_unknown_future_status"}
    ) is True
    assert sweep._quantified_readiness_failed(True, True, {"fired": False}) is True


def test_b4_status_of_prefers_typed_status_then_firing_status():
    # _quantified_status_of prefers the machine-readable quantified_status, falls back to
    # firing_status, and returns '' when neither is present.
    assert sweep._quantified_status_of(
        {"quantified_status": "parse_error", "firing_status": "spec_provider_error"}
    ) == "parse_error"
    assert sweep._quantified_status_of({"firing_status": "no_verified_sentences"}) == \
        "no_verified_sentences"
    assert sweep._quantified_status_of({"fired": False}) == ""


# ── F27 (#1213/h3) required-entity ledger fail-soft -> strict HOLD ────────────────
def test_f27_ledger_off_never_holds():
    # strict OFF -> the force-on ledger's fail-soft is the legacy behavior: a ledger failure
    # is a bare WARN, NEVER a hold (byte-identical), regardless of forced_on / failed.
    assert sweep._required_entity_ledger_failed_under_strict(False, True, True) is False
    assert sweep._required_entity_ledger_failed_under_strict(False, True, False) is False
    assert sweep._required_entity_ledger_failed_under_strict(False, False, True) is False


def test_f27_ledger_on_holds_only_when_forced_on_and_failed():
    # strict ON -> HOLD ONLY when the ledger was FORCE-ON (Gate-B) AND it actually FAILED.
    # The honest "Coverage gaps" disclosure must not be silently dropped on the benchmark run.
    assert sweep._required_entity_ledger_failed_under_strict(True, True, True) is True


def test_f27_ledger_on_not_forced_never_holds():
    # strict ON but the ledger was NOT forced-on (an operator did not enable it) -> nothing to
    # surface; no hold. Guards against holding a run that never ran the ledger.
    assert sweep._required_entity_ledger_failed_under_strict(True, False, True) is False
    assert sweep._required_entity_ledger_failed_under_strict(True, False, False) is False


def test_f27_ledger_on_forced_but_succeeded_never_holds():
    # strict ON + force-on + the ledger SUCCEEDED -> the disclosure was produced; no hold.
    assert sweep._required_entity_ledger_failed_under_strict(True, True, False) is False


def test_f27_new_status_is_registered_and_release_blocking_abort():
    # The F27 status must be a valid unified abort_ value that maps to ITSELF (not error_unexpected)
    # and reads as a release-blocking abort class (a HOLD, never a shippable success/partial).
    assert "abort_required_entity_ledger_failed" in sweep.UNIFIED_STATUS_VALUES
    assert (
        sweep.to_unified_status("abort_required_entity_ledger_failed")
        == "abort_required_entity_ledger_failed"
    )
    assert sweep.to_unified_status("abort_required_entity_ledger_failed").startswith("abort_")


def test_f27_apply_hold_surfaces_the_failure_in_the_manifest():
    # BEHAVIORAL (the F27 ACCEPT: an injected ledger exception is SURFACED, not a silent ok).
    # Pre-fix the manifest stayed status="success" / release_allowed=True (the fail-soft dropped
    # the disclosure silently); this asserts the post-fix HOLD lands in the manifest the run writes.
    # Start from a would-be SUCCESS manifest (what the success path built before this backstop).
    manifest = {"status": "success", "release_allowed": True, "slug": "demo"}
    injected_error = "ValueError: build_ledger blew up on a malformed required_entities row"
    summary_status, unified_status = sweep._apply_required_entity_ledger_hold(
        manifest, injected_error
    )
    # The persisted manifest now SURFACES the failure as a release-blocking HOLD.
    assert manifest["status"] == "abort_required_entity_ledger_failed"
    assert manifest["release_allowed"] is False
    assert manifest["strict_gate_required_entity_ledger_failed"] is True
    assert manifest["required_entity_ledger_error"] == injected_error
    # The returned local status vars (threaded into the re-stamp + summary mirror) agree.
    assert summary_status == "abort_required_entity_ledger_failed"
    assert unified_status == "abort_required_entity_ledger_failed"
    # The unrelated field is preserved (surgical mutation, not a manifest rebuild).
    assert manifest["slug"] == "demo"


def test_f27_inject_ledger_exception_flips_success_to_hold_only_under_strict():
    # BEHAVIORAL end-to-end of the wiring contract WITHOUT the live pipeline: simulate the exact
    # decision the run-sweep block makes when build_ledger RAISES (forced_on True, failed True),
    # and assert the manifest is HELD under strict gates but LEFT a silent success when strict OFF
    # (the legacy fail-soft) — proving the fix is gated, not unconditional.
    for strict, expect_hold in ((True, True), (False, False)):
        manifest = {"status": "success", "release_allowed": True}
        # The ledger raised -> the run-sweep block sets these (forced_on=True, failed=True).
        if (
            sweep._required_entity_ledger_failed_under_strict(strict, True, True)
            and manifest["status"] == "success"
        ):
            sweep._apply_required_entity_ledger_hold(manifest, "RuntimeError: injected")
        if expect_hold:
            assert manifest["status"] == "abort_required_entity_ledger_failed"
            assert manifest["release_allowed"] is False
            assert manifest["required_entity_ledger_error"] == "RuntimeError: injected"
        else:
            # strict OFF -> the legacy fail-soft: the run still reads success (byte-identical).
            assert manifest["status"] == "success"
            assert manifest["release_allowed"] is True
            assert "required_entity_ledger_error" not in manifest


# ── #1242 tier-disclosure single source of truth ─────────────────────────────────
# I-deepfix-001 A5 (#1344): default-ON PG_TIER_MIX_SUM_TO_100 — the integer percents sum to EXACTLY
# 100 (largest-remainder) AND every canonical tier T1..T7 is disclosed (0% when absent), fixing the
# drb_72 "101%"/omitted-tier defect. The flag-OFF path reverts to the prior present-keys-only,
# independent-rounding builder byte-for-byte. LABEL/disclosure only — faithfulness-neutral.
def test_1242_tier_mix_summary_sums_to_100_and_shows_all_canonical_tiers(monkeypatch):
    monkeypatch.delenv("PG_TIER_MIX_SUM_TO_100", raising=False)  # default-ON
    fractions = {"T1": 0.55, "T2": 0.20, "T4": 0.24, "UNKNOWN": 0.01}  # a normalized distribution
    out = sweep._tier_mix_disclosure_summary(fractions)
    segments = out.split(", ")
    keys = [seg.split("=")[0] for seg in segments]
    # every canonical tier is shown, in T1..T7 order, then any extra key (UNKNOWN) appended
    assert keys[:7] == ["T1", "T2", "T3", "T4", "T5", "T6", "T7"]
    assert keys[7:] == ["UNKNOWN"]
    # absent tiers are disclosed at 0% (an omitted tier reads as "not assessed" — the drb_72 bug)
    assert "T3=0%" in out and "T5=0%" in out and "T6=0%" in out and "T7=0%" in out
    # the integer percents sum to EXACTLY 100 — never 101 (independent rounding) or 99
    pcts = [int(seg.split("=")[1].rstrip("%")) for seg in segments]
    assert sum(pcts) == 100


def test_1242_tier_mix_summary_is_single_consistent_value(monkeypatch):
    # The SAME helper called twice yields the SAME string — so two disclosure strings that both
    # reference it can never quote different denominators (the "11% vs 13%" self-contradiction).
    monkeypatch.delenv("PG_TIER_MIX_SUM_TO_100", raising=False)  # default-ON
    fractions = {"T1": 0.60, "T4": 0.40}  # normalized
    a = sweep._tier_mix_disclosure_summary(fractions)
    b = sweep._tier_mix_disclosure_summary(fractions)
    assert a == b
    # T1 / T4 render ONE way only, and the whole line sums to 100.
    assert "T1=60%" in a and "T4=40%" in a
    assert sum(int(seg.split("=")[1].rstrip("%")) for seg in a.split(", ")) == 100


def test_1242_tier_mix_summary_empty_and_none_safe(monkeypatch):
    # Default-ON: empty / None disclose ALL canonical tiers at 0% (no spurious 100 fabricated from an
    # empty distribution) — an omitted tier must never silently vanish.
    monkeypatch.delenv("PG_TIER_MIX_SUM_TO_100", raising=False)
    all_zero = "T1=0%, T2=0%, T3=0%, T4=0%, T5=0%, T6=0%, T7=0%"
    assert sweep._tier_mix_disclosure_summary({}) == all_zero
    assert sweep._tier_mix_disclosure_summary(None) == all_zero


def test_1242_tier_mix_summary_flag_off_reverts_to_legacy_builder(monkeypatch):
    # PG_TIER_MIX_SUM_TO_100=0 reverts byte-for-byte to the prior present-keys-only, independent-
    # rounding builder (the exact escape hatch), including "" for empty / None.
    monkeypatch.setenv("PG_TIER_MIX_SUM_TO_100", "0")
    fractions = {"T1": 0.123, "T2": 0.01, "T3": 0.03, "T4": 0.40, "UNKNOWN": 0.27}
    expected_inline = ", ".join(f"{k}={v * 100:.0f}%" for k, v in sorted(fractions.items()))
    assert sweep._tier_mix_disclosure_summary(fractions) == expected_inline
    assert sweep._tier_mix_disclosure_summary({}) == ""
    assert sweep._tier_mix_disclosure_summary(None) == ""


# ── I-deepfix-001 A5 (#1344): journal DOI-prefix reaches the bibliography genre seam ─────────────
def test_a5_journal_doi_only_row_resolves_to_journal_article():
    # A DOI-only bibliography row (blank url) whose DOI is a known journal prefix must resolve to
    # JOURNAL_ARTICLE through _m2_bib_genre (the bibliography/CWF genre seam) — proving the journal
    # DOI-prefix allowlist actually reaches the render (Science 10.1126, JPE 10.1086, QJE 10.1093/qje).
    # Before the A5 fix _m2_bib_genre did not pass the DOI, so these DOI-only rows rendered "unknown".
    from src.polaris_graph.retrieval.document_type_classifier import DocumentType
    for doi in ("10.1126/science.abc1234", "10.1086/705716", "10.1093/qje/qjab001"):
        row = {"num": 1, "statement": "A finding sentence", "tier": "T1", "url": "", "doi": doi}
        dt, _w = sweep._m2_bib_genre(row, protocol=None, document_type_by_url=None)
        assert dt == DocumentType.JOURNAL_ARTICLE, f"{doi} should classify as JOURNAL_ARTICLE"


def test_a5_journal_doi_fail_open_non_journal_doi_not_forced():
    # Fail-open control: a book-capable bare-registrant DOI (10.1093/oxfordhb, OUP-wide incl. books)
    # and a row with NO doi are NOT force-labeled JOURNAL_ARTICLE just because a DOI/allowlist exists.
    from src.polaris_graph.retrieval.document_type_classifier import DocumentType
    for row in (
        {"num": 2, "statement": "An OUP handbook chapter", "tier": "T2", "url": "",
         "doi": "10.1093/oxfordhb/9780199999999"},
        {"num": 3, "statement": "A blog post about AI", "tier": "T6", "url": "", "doi": ""},
    ):
        dt, _w = sweep._m2_bib_genre(row, protocol=None, document_type_by_url=None)
        assert dt != DocumentType.JOURNAL_ARTICLE


# ── #1239 empty bibliography locator ─────────────────────────────────────────────
def _bib_fixture() -> "list[dict]":
    # Mirrors the drb_72 bibliography.json: entries 4 + 5 are CITED (have a `num`) but carry a
    # blank url and no doi. The bib dict shape carries no `is_cited`/`doi` keys for those rows.
    return [
        {"num": 1, "statement": "Automation and New Tasks", "tier": "T1",
         "url": "https://www.aeaweb.org/articles/pdf/doi/10.1257/jep.33.2.3"},
        {"num": 4, "statement": "Robots and Jobs: Evidence from US Labor Markets",
         "tier": "T1", "url": ""},
        {"num": 5, "statement": "Generative AI at Work", "tier": "T1", "url": ""},
    ]


def test_1239_bib_locator_check():
    assert sweep._bib_entry_has_locator({"url": "https://x", "doi": ""}) is True
    assert sweep._bib_entry_has_locator({"url": "", "doi": "10.1/x"}) is True
    assert sweep._bib_entry_has_locator({"url": "", "doi": ""}) is False
    assert sweep._bib_entry_has_locator({"url": "   ", "doi": None}) is False


def test_1239_bib_render_off_byte_identical():
    # require_locator OFF must reproduce the prior inline loop byte-for-byte (off==identical).
    bib = _bib_fixture()
    out = sweep._render_bibliography_lines(bib, require_locator=False)
    legacy = "\n\n## Bibliography\n"
    for b in bib:
        legacy += f"[{b['num']}] {b['statement'][:200]} — {b['url']} (tier {b['tier']})\n"
    assert out == legacy
    # The blank-URL cited entries STILL render as numbered citations pointing at nothing (the bug).
    assert "[4] Robots and Jobs: Evidence from US Labor Markets —  (tier T1)" in out
    assert "[5] Generative AI at Work —  (tier T1)" in out


def test_1239_bib_render_on_keeps_num_and_discloses_gap_no_orphan():
    # require_locator ON (Codex iter-1 REQUEST_CHANGES): a cited-but-locator-less entry KEEPS its
    # citation number so the report BODY's [N] marker still resolves (no orphan), AND honestly
    # discloses the missing locator. Never fabricates a URL; never drops the entry.
    bib = _bib_fixture()
    out = sweep._render_bibliography_lines(bib, require_locator=True)
    # The good entry keeps its citation number + URL.
    assert "[1] Automation and New Tasks — https://www.aeaweb.org" in out
    # The two blank-URL cited entries KEEP their numbers (body [4]/[5] still resolve) with a
    # disclosed evidence-gap note — NOT a number-less "[gap]" line that would orphan the body.
    assert (
        "[4] Robots and Jobs: Evidence from US Labor Markets — no resolvable URL/DOI locator "
        "(disclosed evidence gap, tier T1)"
    ) in out
    assert (
        "[5] Generative AI at Work — no resolvable URL/DOI locator "
        "(disclosed evidence gap, tier T1)"
    ) in out
    # No number-less orphan-gap line.
    assert "[gap]" not in out
    # The entries are STILL present (awareness preserved) — relabel-down, not drop.
    assert out.count("Robots and Jobs") == 1
    assert out.count("Generative AI at Work") == 1


def test_1239_bib_render_on_renders_doi_only_locator():
    # require_locator ON: an entry with a DOI but blank URL renders the DOI as a doi.org locator
    # (a real DOI the entry already carries — never fabricated) and stays a numbered citation.
    bib = [{"num": 7, "statement": "DOI-only entry", "tier": "T1", "url": "",
            "doi": "10.1257/jep.29.3.3"}]
    out = sweep._render_bibliography_lines(bib, require_locator=True)
    assert "[7] DOI-only entry — https://doi.org/10.1257/jep.29.3.3 (tier T1)" in out
    assert "[gap]" not in out


# ── #1242 tier-disclosure override threads ONE canonical string into the telemetry block ──────────
def test_1242_telemetry_block_override_emits_canonical_string_verbatim():
    # Codex iter-1 REQUEST_CHANGES: when tier_disclosure_override is supplied, _format_telemetry_block
    # emits that EXACT canonical string and does NOT re-derive a per-tier list from the fractions — so
    # the LLM-authored Limitations quotes the SAME tier mix the deterministic Methods disclosure quotes.
    from src.polaris_graph.generator.live_deepseek_generator import _format_telemetry_block

    fractions = {"T1": 0.13, "T4": 0.40}
    canonical = sweep._tier_mix_disclosure_summary(fractions)  # "T1=13%, T4=40%"
    block = _format_telemetry_block(
        fractions, None, None, None, tier_disclosure_override=canonical,
    )
    # The canonical string appears verbatim.
    assert canonical in block
    # And the per-tier re-derived list is NOT separately present (no standalone "  T1: 13%" line).
    assert "  T1: 13%" not in block
    assert "  T4: 40%" not in block


def test_1242_telemetry_block_override_none_is_unchanged():
    # override None => legacy per-tier derivation (byte-identical to today).
    from src.polaris_graph.generator.live_deepseek_generator import _format_telemetry_block

    fractions = {"T1": 0.13, "T4": 0.40}
    legacy = _format_telemetry_block(fractions, None, None, None)
    explicit_none = _format_telemetry_block(
        fractions, None, None, None, tier_disclosure_override=None,
    )
    assert legacy == explicit_none
    # The per-tier derived lines ARE present on the legacy path.
    assert "  T1: 13%" in legacy
    assert "  T4: 40%" in legacy


# ── #1240 per-run token-honesty telemetry reset + snapshot ────────────────────────────────────────
def test_1240_token_honesty_reset_zeroes_counters():
    # Codex iter-1 REQUEST_CHANGES: the per-run reset must zero the module-global counters so counts
    # do not accumulate across queries. Drive the real provenance-generator helpers.
    from src.polaris_graph.generator import provenance_generator as pg

    pg.reset_token_honesty_telemetry()
    snap = pg.get_token_honesty_telemetry()
    # I-deepfix-001 B9(c) (#1353): the token-honesty telemetry grew a third counter
    # `mirror_cites_collapsed` (paired-mirror citations folded to one origin). The
    # reset must still zero ALL counters.
    assert snap == {
        "malformed_canonicalized": 0,
        "malformed_dropped": 0,
        "mirror_cites_collapsed": 0,
    }
    # Simulate accumulation, then reset again -> back to zero (no leak across runs).
    pg._TOKEN_HONESTY_TELEMETRY["malformed_canonicalized"] = 4
    pg._TOKEN_HONESTY_TELEMETRY["malformed_dropped"] = 2
    assert pg.get_token_honesty_telemetry()["malformed_canonicalized"] == 4
    pg.reset_token_honesty_telemetry()
    assert pg.get_token_honesty_telemetry() == {
        "malformed_canonicalized": 0,
        "malformed_dropped": 0,
        "mirror_cites_collapsed": 0,
    }


def test_1240_token_honesty_snapshot_is_a_copy_not_a_live_ref():
    # The snapshot surfaced into the manifest must be a COPY, so a later increment in a sibling run
    # cannot retroactively mutate an already-written manifest's recorded counts.
    from src.polaris_graph.generator import provenance_generator as pg

    pg.reset_token_honesty_telemetry()
    snap = pg.get_token_honesty_telemetry()
    pg._TOKEN_HONESTY_TELEMETRY["malformed_dropped"] = 9
    assert snap["malformed_dropped"] == 0  # the earlier snapshot is unaffected
    pg.reset_token_honesty_telemetry()


# ── I-arch-011 PR-b (#1268) Argus keep-all basket-corroboration render ────────────
def _basket_bib_fixture() -> "list[dict]":
    """A basket-bearing bibliography (mirrors the provenance_generator._basket_for_biblio
    projection attached to each row as row["baskets"]). Cluster c1 has TWO
    ENTAILMENT_VERIFIED supports (verified_support_origin_count=2), ONE DETERMINISTIC_ONLY
    weak member, and ONE UNVERIFIED garbage member; it is CONTESTED. The SAME basket is
    attached to both of its members' rows (the 1-to-many enrichment) so we can prove the
    render dedups by claim_cluster_id."""
    c1 = {
        "claim_cluster_id": "c1",
        "claim_text": "Tirzepatide reduced HbA1c by 2.1% at 40 weeks",
        "verified_support_origin_count": 2,
        "total_clustered_origin_count": 4,
        "basket_verdict": "contested",
        "refuter_cluster_ids": ("c9",),
        "supporting_members": [
            {"evidence_id": "ev_a", "source_url": "https://nejm.org/a", "source_tier": "T1",
             "credibility_weight": 0.95, "authority_score": 0.9, "span_verdict": "SUPPORTS",
             "member_tier": "ENTAILMENT_VERIFIED", "direct_quote": "2.1% reduction"},
            {"evidence_id": "ev_b", "source_url": "https://lancet.com/b", "source_tier": "T1",
             "credibility_weight": 0.88, "authority_score": 0.85, "span_verdict": "SUPPORTS",
             "member_tier": "ENTAILMENT_VERIFIED", "direct_quote": "2.1% HbA1c drop"},
            {"evidence_id": "ev_c", "source_url": "https://preprint.org/c", "source_tier": "T4",
             "credibility_weight": 0.40, "authority_score": 0.3, "span_verdict": "UNSUPPORTED",
             "member_tier": "DETERMINISTIC_ONLY", "direct_quote": "HbA1c improved"},
            {"evidence_id": "ev_d", "source_url": "https://blog.example/d", "source_tier": "T7",
             "credibility_weight": 0.05, "authority_score": 0.05, "span_verdict": "UNSUPPORTED",
             "member_tier": "UNVERIFIED", "direct_quote": "diabetes news"},
        ],
    }
    return [
        {"num": 1, "statement": "NEJM RCT", "tier": "T1", "url": "https://nejm.org/a",
         "baskets": [c1]},
        {"num": 2, "statement": "Lancet RCT", "tier": "T1", "url": "https://lancet.com/b",
         "baskets": [c1]},
    ]


def test_iarch011_prb_off_byte_identical_even_with_baskets():
    # WIRING: flag-OFF (corroboration_render default) must be byte-identical to the legacy
    # render even when the rows carry basket data — the corroboration block never appears.
    bib = _basket_bib_fixture()
    legacy = sweep._render_bibliography_lines(bib, require_locator=False)
    explicit_off = sweep._render_bibliography_lines(
        bib, require_locator=False, corroboration_render=False
    )
    assert legacy == explicit_off
    assert "Source corroboration" not in legacy
    assert "GROUNDED-BUT-WEAK" not in legacy


def test_iarch011_prb_on_renders_count_weights_support_labels():
    # WIRING: flag-ON appends the per-claim corroboration block with the COUNT (the basket's
    # own verified_support_origin_count=2, NOT len(members)=4), per-source WEIGHTS, and the
    # SUPPORT label for each ENTAILMENT_VERIFIED member.
    bib = _basket_bib_fixture()
    out = sweep._render_bibliography_lines(
        bib, require_locator=False, corroboration_render=True
    )
    assert "## Source corroboration (per claim)" in out
    # COUNT = verified_support_origin_count (2), never the 4 raw members.
    assert "2 verified independent source(s)" in out
    # Each ENTAILMENT_VERIFIED member is a SUPPORT line carrying its weight + tier.
    # I-deepfix-001 S6 (#1344): the DISPLAYED weight is now the single authority_score source of
    # truth (ev_a authority_score=0.9, ev_b=0.85) — NOT the divergent credibility_weight — so a tier
    # label can never sit on a mismatched weight and every disclosure surface shows one weight.
    assert "SUPPORT: https://nejm.org/a (tier T1, weight 0.90)" in out
    assert "SUPPORT: https://lancet.com/b (tier T1, weight 0.85)" in out


def test_iarch011_prb_deterministic_only_labeled_weak_never_counted_as_support():
    # FAITHFULNESS: the DETERMINISTIC_ONLY member is surfaced LABELED-weak (disclosed),
    # explicitly NOT counted as support and never as a SUPPORT line.
    bib = _basket_bib_fixture()
    out = sweep._render_bibliography_lines(
        bib, require_locator=False, corroboration_render=True
    )
    # weak member appears under the grounded-but-weak label.
    assert "GROUNDED-BUT-WEAK" in out
    assert "https://preprint.org/c" in out
    # the weak member is NEVER on a SUPPORT line.
    assert "SUPPORT: https://preprint.org/c" not in out
    # the disclosed count stays 2 — the weak member did not inflate it.
    assert "3 verified independent source(s)" not in out
    assert "2 verified independent source(s)" in out
    # UNVERIFIED (deterministic garbage) is NOT surfaced at all.
    assert "https://blog.example/d" not in out


def test_iarch011_prb_renders_contested_label_and_dedups_by_cluster():
    # The contested basket renders the cluster-level CONTRADICT label, and the basket
    # (attached to BOTH rows) is rendered exactly ONCE (dedup by claim_cluster_id).
    bib = _basket_bib_fixture()
    out = sweep._render_bibliography_lines(
        bib, require_locator=False, corroboration_render=True
    )
    assert "CONTRADICTED" in out
    # the claim heading appears once, not once-per-member-row.
    assert out.count("Tirzepatide reduced HbA1c by 2.1% at 40 weeks") == 1


def test_iarch011_prb_no_baskets_appends_nothing():
    # A bibliography with no basket data (the CREDIBILITY_REDESIGN-OFF path) appends nothing
    # even with the flag ON — the block is "" and the render equals the legacy.
    bib = _bib_fixture()
    legacy = sweep._render_bibliography_lines(bib, require_locator=False)
    on = sweep._render_bibliography_lines(
        bib, require_locator=False, corroboration_render=True
    )
    assert on == legacy
    assert "Source corroboration" not in on


def test_iarch011_prb_live_wiring_call_site_reads_env_flag(monkeypatch):
    # WIRING (the "fired in output, not config" trap): prove the LIVE render path reads the
    # env flag, not just that the function accepts the kwarg. _env_flag is the exact helper
    # the call site uses; assert the flag name resolves and toggles.
    monkeypatch.delenv(sweep._BASKET_CORROBORATION_RENDER_ENV, raising=False)
    assert sweep._env_flag(sweep._BASKET_CORROBORATION_RENDER_ENV, default=False) is False
    monkeypatch.setenv(sweep._BASKET_CORROBORATION_RENDER_ENV, "1")
    assert sweep._env_flag(sweep._BASKET_CORROBORATION_RENDER_ENV, default=False) is True


def test_iarch011_prb_live_call_site_passes_corroboration_render_kwarg():
    # WIRING (the "fired in output, not config" trap, §-1.4): a unit test that passes
    # corroboration_render=True proves the FUNCTION works but NOT that the LIVE report.md
    # assembly path passes the flag through. Assert the production call site actually wires
    # the env flag into _render_bibliography_lines(corroboration_render=...). Structural
    # source assertion over the single live call site, so a silent regression that drops the
    # kwarg fails loud here.
    import inspect
    src = inspect.getsource(sweep)
    # the only call to _render_bibliography_lines that feeds report.md.
    assert "biblio_section = _render_bibliography_lines(" in src
    call_start = src.index("biblio_section = _render_bibliography_lines(")
    call_block = src[call_start:call_start + 800]
    assert "corroboration_render=_env_flag(" in call_block
    # the env flag IDENTIFIER (not its string value) is what the call site references.
    assert "_BASKET_CORROBORATION_RENDER_ENV" in call_block


def test_iarch011_prb_end_to_end_real_resolver_attaches_baskets_and_block_fires():
    # BEHAVIORAL PROOF (§-1.4 "effect APPEARS in real output", not a hand-built dict):
    # drive the PRODUCTION resolver (resolve_provenance_to_citations_with_count — the same
    # function multi_section_generator.py:4085 calls) with a REAL ClaimBasket of REAL
    # BasketMembers, so it attaches row["baskets"] exactly as the live report.md path does,
    # THEN feed its REAL output through _basket_corroboration_block and assert the block
    # fires with the correct count/weights/labels. This is the attach->render chain end to
    # end, not a fixture that pre-bakes row["baskets"].
    from src.polaris_graph.generator.provenance_generator import (
        resolve_provenance_to_citations_with_count,
        SentenceVerification,
        parse_provenance_tokens,
    )
    from src.polaris_graph.synthesis.credibility_pass import (
        ClaimBasket,
        BasketMember,
        MEMBER_TIER_ENTAILMENT_VERIFIED,
        MEMBER_TIER_DETERMINISTIC_ONLY,
        MEMBER_TIER_UNVERIFIED,
    )

    evidence_pool = {
        "ev_a": {"source_url": "https://nejm.org/a", "tier": "T1", "statement": "HbA1c cut 2.1%"},
        "ev_b": {"source_url": "https://lancet.com/b", "tier": "T1", "statement": "2.1% drop"},
        "ev_c": {"source_url": "https://preprint.org/c", "tier": "T4", "statement": "improved"},
        "ev_d": {"source_url": "https://blog.example/d", "tier": "T7", "statement": "news"},
    }
    sent = "Tirzepatide reduced HbA1c by 2.1% at 40 weeks [#ev:ev_a:0-13]."
    sv = SentenceVerification(
        sentence=sent, tokens=parse_provenance_tokens(sent),
        is_verified=True, failure_reasons=[], soft_warnings=[],
    )
    members = [
        BasketMember("ev_a", "https://nejm.org/a", "T1", "o1", 0.95, 0.9, (0, 13),
                     "HbA1c cut 2.1%", "SUPPORTS", MEMBER_TIER_ENTAILMENT_VERIFIED),
        BasketMember("ev_b", "https://lancet.com/b", "T1", "o2", 0.88, 0.85, (0, 8),
                     "2.1% drop", "SUPPORTS", MEMBER_TIER_ENTAILMENT_VERIFIED),
        BasketMember("ev_c", "https://preprint.org/c", "T4", "o3", 0.40, 0.3, (0, 8),
                     "improved", "UNSUPPORTED", MEMBER_TIER_DETERMINISTIC_ONLY),
        BasketMember("ev_d", "https://blog.example/d", "T7", "o4", 0.05, 0.05, (0, 4),
                     "news", "UNSUPPORTED", MEMBER_TIER_UNVERIFIED),
    ]
    basket = ClaimBasket(
        "c1", "Tirzepatide reduced HbA1c by 2.1% at 40 weeks", "Tirzepatide", "reduced HbA1c",
        members, ("c9",), 2.7, 4, 2, "contested",
    )
    cluster_id_by_evidence = {"ev_a": ["c1"], "ev_b": ["c1"], "ev_c": ["c1"], "ev_d": ["c1"]}

    _text, biblio, _emitted = resolve_provenance_to_citations_with_count(
        [sv], evidence_pool, baskets=[basket],
        cluster_id_by_evidence=cluster_id_by_evidence,
    )
    # the REAL resolver attached row["baskets"] with the member_tier carried through.
    assert biblio and "baskets" in biblio[0]
    tiers = [m["member_tier"] for m in biblio[0]["baskets"][0]["supporting_members"]]
    assert tiers == ["ENTAILMENT_VERIFIED", "ENTAILMENT_VERIFIED",
                     "DETERMINISTIC_ONLY", "UNVERIFIED"]

    # the LIVE render path over the REAL resolver output.
    blk = sweep._basket_corroboration_block(biblio)
    assert "2 verified independent source(s)" in blk
    assert "SUPPORT: https://nejm.org/a (tier T1, weight 0.95)" in blk
    assert "SUPPORT: https://lancet.com/b (tier T1, weight 0.88)" in blk
    assert "GROUNDED-BUT-WEAK" in blk and "https://preprint.org/c" in blk
    assert "SUPPORT: https://preprint.org/c" not in blk      # weak never a support line
    assert "https://blog.example/d" not in blk               # UNVERIFIED hidden
    assert "CONTRADICTED" in blk
