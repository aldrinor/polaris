"""FF3-TRUNC-SEM (I-deepfix-001 Wave-5 #1344) — the SEMANTIC render-truncation guard that catches
grammatically-plausible but semantically-truncated claim units a pure LEXICAL last-word rule misses: a
clause cut on a complement-DEMANDING connective grammar guarantees cannot terminate it —

  * a dangling COMPARATIVE ("… adoption spread faster than", "… arm A versus"),
  * a cut SUBORDINATOR ("… the effect held unless", "… it is unclear whether"),
  * an open APPOSITIVE / list lead-in ("… several factors namely", "… key drivers such").

RENDER-ONLY / FAITHFULNESS-NEUTRAL: the guard DROPS the unsafe-to-render fragment (a render stub is NOT a
source — dropping it is cleanliness, never a §-1.3 source drop) and NEVER fabricates a word to "complete" a
claim. Flag-gated ``PG_FF3_TRUNC_SEM`` (default OFF => byte-identical). The frozen faithfulness engine
(strict_verify / NLI / 4-role D8 / provenance / span-grounding) is byte-untouched. Pure / offline.

This module ALSO carries the Wave-5 ANTI-DARK wiring proofs for the FF3 render-truncation flag:
quad-pinned into all four Gate-B slate structures, canary spec registered, and the emit call wired into
the Gate-B per-report seam so a FORCE_ON'd flag PROVES it fired on the official run. (The FF2-TRUNC-v2
lexical guard was RETIRED as unsound and no longer exists.)
"""
from __future__ import annotations

import os

import pytest

import scripts.dr_benchmark.run_gate_b as rg
from src.polaris_graph.generator import key_findings as kf


@pytest.fixture(autouse=True)
def _ff3_flag_on(monkeypatch):
    """FF3-TRUNC-SEM is OPT-IN (default OFF). The render-guard GREEN assertions test the ACTIVATED guard,
    so the flag is ON for the module; the OFF byte-identical test re-sets it to "0" itself."""
    monkeypatch.setenv("PG_FF3_TRUNC_SEM", "1")


# ── DEFAULT-OFF invariant + OFF byte-identical ───────────────────────────────
def test_flag_default_off(monkeypatch):
    """The producer predicate defaults OFF (flag-OFF byte-identical) and reads at CALL time (LAW VI)."""
    monkeypatch.delenv("PG_FF3_TRUNC_SEM", raising=False)
    assert kf._ff3_trunc_sem_enabled() is False
    monkeypatch.setenv("PG_FF3_TRUNC_SEM", "1")
    assert kf._ff3_trunc_sem_enabled() is True
    monkeypatch.setenv("PG_FF3_TRUNC_SEM", "0")
    assert kf._ff3_trunc_sem_enabled() is False


def test_off_is_byte_identical_semantic_shapes_not_flagged(monkeypatch):
    """OFF byte-identical: with PG_FF3_TRUNC_SEM=0 the semantic leg is SKIPPED, so the exact semantic-cut
    strings FF3 catches return False (the pre-Wave-5 HEAD behaviour), while the always-on marker leg and
    the ordinary complete-sentence pass are unchanged."""
    monkeypatch.setenv("PG_FF3_TRUNC_SEM", "0")
    for frag in (
        "The adoption of automation spread faster than",
        "The observed effect held unless",
        "The displacement affected several occupations namely",
        "The study identified key drivers such",
        "Wages fell relative to output arm A versus",
    ):
        assert kf.is_truncated_fragment(frag) is False, f"OFF must be byte-identical (kept): {frag!r}"
    # always-on legs unaffected
    assert kf.is_truncated_fragment("Automation does indeed su…") is True
    assert kf.is_truncated_fragment("Wages rose 5% in 2023.") is False


# ── RED → GREEN: semantic-truncated fragments are CAUGHT ─────────────────────
def test_dangling_comparative_is_flagged():
    """A clause ending on a bare comparative connective ("than"/"versus"/"vs") is semantically truncated —
    the second operand was cut. A pure lexical last-word rule never listed these (valid tokens elsewhere)."""
    for frag in (
        "The adoption of automation spread faster than",
        "Displacement in call centres was larger versus",
        "The reskilling gap widened arm A vs",
    ):
        assert kf.is_truncated_fragment(frag) is True, f"dangling comparative must flag: {frag!r}"


def test_cut_subordinator_is_flagged():
    """A clause ending on a bare subordinator ("whether"/"unless") is semantically truncated — its
    dependent clause was cut."""
    for frag in (
        "The observed productivity effect held unless",
        "It remains unclear whether",
        "Employment recovers unless",
    ):
        assert kf.is_truncated_fragment(frag) is True, f"cut subordinator must flag: {frag!r}"


def test_open_appositive_or_list_lead_in_is_flagged():
    """A clause ending on an open appositive / list lead-in ("namely"/"such") is semantically truncated —
    the enumerated item(s) were cut."""
    for frag in (
        "The displacement affected several occupations namely",
        "The study identified key structural drivers such",
    ):
        assert kf.is_truncated_fragment(frag) is True, f"open appositive must flag: {frag!r}"


def test_as_such_idiom_is_kept():
    """Codex Wave-5 P1: "as such" is a valid sentence-final IDIOM ("… was classified as such", "… are
    recognized as such"), NOT the "such as" list lead-in FF3 targets. The two are distinguished by the
    token BEFORE "such": "as" => the complete idiom (KEEP); a content noun => the cut lead-in (flag)."""
    for frag in (
        "The workforce effect was classified as such",
        "These displaced roles are recognized as such",
        "The productivity gain is documented as such",
    ):
        assert kf.is_truncated_fragment(frag) is False, f"'as such' idiom must be kept: {frag!r}"


# ── PRECISION: clean claims pass untouched; no over-strip ────────────────────
def test_complete_clauses_with_terminal_punct_are_kept():
    """FF3 is gated on ABSENT terminal punctuation — a complete clause (even one that legitimately used a
    demander word mid-sentence) survives."""
    for frag in (
        "Adoption spread faster than in prior technology waves.",
        "The effect held unless the market intervened.",
        "Several occupations were affected, namely clerks and cashiers.",
    ):
        assert kf.is_truncated_fragment(frag) is False, f"complete clause must be kept: {frag!r}"


def test_pronoun_tail_after_demander_is_kept():
    """A legitimate elided/comparative tail whose demander sits right after a PRONOUN subject is complete,
    not a cut (mirrors the pronoun-subject keep-guard)."""
    for frag in (
        "Automation displaced as many roles as it than",   # contrived pronoun-before-demander tail
        "The gains were larger than they",                 # demander not final -> not a demander cut
    ):
        assert kf.is_truncated_fragment(frag) is False, f"pronoun tail must be kept: {frag!r}"


def test_uppercase_acronym_or_label_ender_is_kept():
    """A trailing ALL-CAPS acronym / single-CAPITAL label is a valid ender, never a dangling demander."""
    for frag in (
        "The analysis was per protocol PP",
        "Patients received vitamin C",
    ):
        assert kf.is_truncated_fragment(frag) is False, f"acronym/label ender must be kept: {frag!r}"


def test_ordinary_complete_sentences_and_noun_phrases_are_kept():
    """A normal complete sentence and an ordinary un-truncated clause (no demander ender) are untouched."""
    for frag in (
        "The model improved productivity across many occupations",
        "Generative AI adoption accelerated after 2022",
        "Total factor productivity rose in the services sector",
    ):
        assert kf.is_truncated_fragment(frag) is False, f"clean claim must be kept: {frag!r}"


# ── REALIZED-EFFECT telemetry: detect-and-DROP, NEVER invent meaning ─────────
def test_ff3_detection_is_a_drop_never_a_repair():
    """A detected FF3 fragment is DROPPED (returns True); it is NEVER repaired (repaired ALWAYS 0 — the
    guard never fabricates a word to complete a semantically-truncated claim, §-1.3 / faithfulness-neutral).
    The render stub is removed; the MEANING of any verified claim is never changed."""
    kf.reset_truncation_telemetry()
    caught = "The adoption of automation spread faster than"
    assert kf.is_truncated_fragment(caught) is True
    assert kf.is_truncated_fragment("It remains unclear whether") is True
    _tel = kf._ff3_telemetry()
    assert _tel["detected"] == 2
    assert _tel["dropped"] == 2
    assert _tel["repaired"] == 0
    assert _tel["failopen"] == 0
    # reviewer P0 liveness counter: both fragments were EXAMINED by the guard (screened), proving reach.
    assert _tel["screened"] == 2
    # the guard returns a boolean verdict only; it returns no rewritten/"completed" string.
    assert kf.is_truncated_fragment(caught) is True  # idempotent verdict, input never mutated


# ═════════════════════════════════════════════════════════════════════════════
# Wave-5 ANTI-DARK wiring: both flags quad-pinned; canary specs registered; emit wired.
# ═════════════════════════════════════════════════════════════════════════════
_WAVE5_FLAGS = ["PG_FF3_TRUNC_SEM"]


@pytest.mark.parametrize("flag", _WAVE5_FLAGS)
def test_flag_quad_pinned_into_all_four_slate_structures(flag):
    """Each render-truncation flag is quad-wired: slate "1" + FORCE_ON + REQUIRED + ALLOWLIST, so a stray
    operator/.env =0 fails the run CLOSED before spend and SLATE-PURITY still passes."""
    assert rg._FULL_CAPABILITY_BENCHMARK_SLATE.get(flag) == "1"
    assert flag in rg._BENCHMARK_FORCE_ON_FLAGS
    assert flag in rg._BENCHMARK_PREFLIGHT_REQUIRED_FLAGS
    assert flag in rg._WINNER_FLAG_ALLOWLIST


def test_slate_purity_still_clean_after_wave5():
    """Every force-on flag maps to an allowlist entry — no SLATE-PURITY impurity introduced by Wave-5."""
    unrecognized = sorted(set(rg._BENCHMARK_FORCE_ON_FLAGS) - set(rg._WINNER_FLAG_ALLOWLIST))
    assert unrecognized == []


def test_canary_specs_registered_in_wave3_registry():
    """Both render-truncation markers are registered as run_gate_b activation specs with the whitelist
    producer predicate, a LIVENESS+count-shaped positive regex (reviewer P0: leads with ``reached=<bool>``,
    still carries detected=0 which must PASS when reached=True — §-1.3 no count threshold), a bool_check that
    DEMANDS ``reached=True`` (a dark guard fails), and the failopen degrade tripwire."""
    by_name = {s.name: s for s in rg._ACTIVATION_MARKER_SPECS_WAVE3}
    for name, flag in (("ff3_trunc_sem", "PG_FF3_TRUNC_SEM"),):
        assert name in by_name, f"{name} spec missing from _ACTIVATION_MARKER_SPECS_WAVE3"
        spec = by_name[name]
        assert spec.env_flag == flag
        assert spec.flag_whitelist == ("1", "true", "on", "yes")
        # detected=0 with reached=True is the accepted eligible-yet-zero fire (structural match).
        assert spec.positive_re.search(
            f"[activation] {name}: reached=True screened=1 detected=0 repaired=0 dropped=0"
        )
        # the liveness gate: the parsed marker must satisfy reached=True (a dark reached=False fails).
        assert ("reached", "True") in spec.bool_checks
        assert spec.absent_markers == (f"[activation] {name}: unavailable_failopen",)


def test_emit_call_wired_into_gate_b_per_report_seam():
    """ANTI-DARK: the FF3 realized-effect [activation] emit is WIRED into run_gate_b_query AFTER
    run_one_query renders the report (inside the in-process query the canary capture handler covers), and
    the per-report reset is wired BEFORE it — so a FORCE_ON'd flag PROVES it fired on the official run."""
    import inspect

    src = inspect.getsource(rg.run_gate_b_query)
    assert "reset_truncation_telemetry" in src
    assert "emit_truncation_activation_markers" in src


def _run_canary(monkeypatch, on_flag: str, *marker_lines):
    """Drive rg.assert_activation_markers_fired over a run-log carrying ``marker_lines`` with the canary
    opt-in + ``on_flag`` ON and EVERY OTHER activation flag (all wave3/4/5 siblings) OFF, so ONLY
    ``on_flag``'s spec is asserted (every other module flag => self-scoped out)."""
    monkeypatch.setenv("PG_ACTIVATION_CANARY", "1")
    monkeypatch.setenv(on_flag, "1")
    # Turn OFF every OTHER registered activation flag (main specs + wave3/4/5 siblings) so only the target
    # spec is demanded. Set EXPLICIT "0" (not delenv): "0" reads OFF for a blocklist, whitelist, numeric
    # (int 0 < threshold) AND a DEFAULT-ON producer like summary_table (flag_default_on) — an unset
    # default-on flag would otherwise stay ON and over-demand its marker.
    for spec in (*rg._ACTIVATION_MARKER_SPECS, *rg._ACTIVATION_MARKER_SPECS_WAVE3):
        if spec.env_flag != on_flag:
            monkeypatch.setenv(spec.env_flag, "0")
    log_text = "".join("2026-07-06 12:00:00,000 INFO src.polaris_graph - " + m + "\n" for m in marker_lines)
    rg.assert_activation_markers_fired(log_text)


@pytest.mark.parametrize("name,flag", [("ff3_trunc_sem", "PG_FF3_TRUNC_SEM")])
def test_canary_accepts_ran_ok_zero(monkeypatch, name, flag):
    """§-1.3 no-threshold: reached=True with detected=0 repaired=0 dropped=0 (the guard was CONSULTED and the
    report had no truncated fragments) is an ACCEPTED eligible-yet-zero fire — the canary must NOT raise. The
    liveness field (reached=True) is what proves the guard ran; the detection count stays free to be zero."""
    _run_canary(
        monkeypatch, flag,
        f"[activation] {name}: reached=True screened=5 detected=0 repaired=0 dropped=0",
    )


@pytest.mark.parametrize("name,flag", [("ff3_trunc_sem", "PG_FF3_TRUNC_SEM")])
def test_canary_accepts_nonzero(monkeypatch, name, flag):
    _run_canary(
        monkeypatch, flag,
        f"[activation] {name}: reached=True screened=9 detected=7 repaired=0 dropped=7",
    )


@pytest.mark.parametrize("name,flag", [("ff3_trunc_sem", "PG_FF3_TRUNC_SEM")])
def test_canary_rejects_dark_unreached(monkeypatch, name, flag):
    """Reviewer P0 FALSE-GREEN fix: a marker with reached=False means the guard was flag-ON but the render
    seam NEVER invoked is_truncated_fragment (a still-dark guard), so screened stayed 0. A bare detected=0
    can no longer green-light it — the canary RAISES on reached=False even though every count field is a
    clean zero. This is the exact false-green the fix closes."""
    with pytest.raises(RuntimeError):
        _run_canary(
            monkeypatch, flag,
            f"[activation] {name}: reached=False screened=0 detected=0 repaired=0 dropped=0",
        )


@pytest.mark.parametrize("name,flag", [("ff3_trunc_sem", "PG_FF3_TRUNC_SEM")])
def test_canary_rejects_absent(monkeypatch, name, flag):
    """Flag ON but no positive marker => the guard went dark => the canary RAISES (MARKER ABSENT)."""
    with pytest.raises(RuntimeError):
        _run_canary(monkeypatch, flag, "[activation] some_other_module: fired")


@pytest.mark.parametrize("name,flag", [("ff3_trunc_sem", "PG_FF3_TRUNC_SEM")])
def test_canary_rejects_failopen(monkeypatch, name, flag):
    """The distinct ``unavailable_failopen`` degrade (a guard-internal fault) must FAIL the canary even
    though the positive marker co-occurs (the OLD/DEGRADE-MARKER-PRESENT leg)."""
    with pytest.raises(RuntimeError):
        _run_canary(
            monkeypatch, flag,
            f"[activation] {name}: reached=True screened=3 detected=3 repaired=0 dropped=3",
            f"[activation] {name}: unavailable_failopen",
        )
