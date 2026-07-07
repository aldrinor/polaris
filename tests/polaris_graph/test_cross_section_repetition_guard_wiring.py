"""Cross-section repetition guard WIRING (I-deepfix-001 FIX 5, GH #1344).

The guard module ``cross_section_repetition_guard`` is sound + diff-gated; these tests prove the
WIRING half:

  * OFF byte-identical — flag unset => the render-assembly-seam caller
    (``_apply_cross_section_repetition_guard``) is a no-op: it returns ``{}``, emits NO marker, and
    mutates NO ``verified_text`` (so the assembled report equals the legacy assembly).
  * ON consolidates a VERBATIM cross-section duplicate to a citation-preserving back-reference while
    KEEPING every citation and every DISTINCT sentence (§-1.3 consolidate-keep-all, never a drop).
  * FAIL-CONSERVATIVE — a guard error RESTORES each section's pre-guard ``verified_text`` (never a
    dropped or partially-swapped section) and emits the DISTINCT ``unavailable_failopen`` degrade
    marker the activation canary REJECTS.
  * The honest-liveness marker reports the REALIZED consolidated count (``consolidated=0`` is an
    accepted ran-ok-zero fire — NEVER gated on a >0 count per §-1.3).
  * The run_gate_b activation canary registers a matching ``_ActivationMarkerSpec`` so a DARK guard
    (never wired / never reached) CRASHES the paid run instead of silently shipping.

Pure / offline. The frozen faithfulness engine is untouched (the guard is RENDER-ONLY and runs AFTER
strict_verify / NLI / 4-role D8 / provenance / span-grounding).
"""
from __future__ import annotations

import logging

import pytest

import scripts.dr_benchmark.run_gate_b as rg
import src.polaris_graph.generator.multi_section_generator as msg
from src.polaris_graph.generator.cross_section_repetition_guard import (
    consolidate_cross_section_repetition,
)
from src.polaris_graph.generator.multi_section_generator import (
    SectionResult,
    _apply_cross_section_repetition_guard,
)

_FLAG = "PG_CROSS_SECTION_REPETITION_GUARD"
_LOGGER = "polaris_graph.multi_section"
_MARKER_PREFIX = "[activation] cross_section_repetition_guard:"
_FAILOPEN = "[activation] cross_section_repetition_guard: unavailable_failopen"

# A finding sentence that will recur VERBATIM (numeric-citation-stripped) across two sections.
_FINDING = "Goldman Sachs estimated a 2.5% lift in global GDP over ten years"


def _mk(title: str, verified_text: str, *, dropped: bool = False, gap_stub: bool = False) -> SectionResult:
    """A real SectionResult carrying only the fields the guard reads; the rest are inert defaults."""
    return SectionResult(
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
        dropped_due_to_failure=dropped,
        is_gap_stub=gap_stub,
    )


def _two_recycled_sections() -> tuple[SectionResult, SectionResult]:
    """Section A (richest: 2 citations) + Section B (1 citation), each carrying the SAME verbatim finding
    plus its OWN distinct sentence."""
    a = _mk("Economic Impact", f"{_FINDING} [1][2]. Robots will number 20 million by 2030 [4].")
    b = _mk("Labor Effects", f"{_FINDING} [3]. Unemployment may rise to 8% in affected regions [5].")
    return a, b


# ── (1) OFF byte-identical ─────────────────────────────────────────────────────────────────────
def test_module_off_returns_empty_and_no_mutation(monkeypatch):
    """The GUARD MODULE itself: flag unset => returns {} and mutates no verified_text."""
    monkeypatch.delenv(_FLAG, raising=False)
    a, b = _two_recycled_sections()
    before = (a.verified_text, b.verified_text)
    tel = consolidate_cross_section_repetition([a, b])
    assert tel == {}
    assert (a.verified_text, b.verified_text) == before


def test_caller_off_is_noop_no_marker_byte_identical(monkeypatch, caplog):
    """The WIRED CALLER: flag unset => returns {}, emits NO [activation] marker, and leaves every
    section byte-identical (=> the assembled report equals the legacy assembly)."""
    monkeypatch.delenv(_FLAG, raising=False)
    a, b = _two_recycled_sections()
    before = (a.verified_text, b.verified_text)
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        out = _apply_cross_section_repetition_guard([a, b])
    assert out == {}
    assert (a.verified_text, b.verified_text) == before
    assert _MARKER_PREFIX not in caplog.text


# ── (2) ON consolidates a verbatim cross-section duplicate to a back-reference (keep-all) ────────
def test_caller_on_consolidates_to_backref_keeps_citations_and_distinct(monkeypatch, caplog):
    monkeypatch.setenv(_FLAG, "1")
    a, b = _two_recycled_sections()
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        out = _apply_cross_section_repetition_guard([a, b])
    # telemetry: exactly one recycled instance consolidated into one cross-section cluster.
    assert out == {"clusters": 1, "consolidated": 1}
    # Richest section (A) keeps the full finding verbatim + BOTH its citations + its distinct sentence.
    assert _FINDING in a.verified_text
    assert "[1][2]" in a.verified_text
    assert "Robots will number 20 million by 2030 [4]." in a.verified_text
    # Recycled section (B): the finding is REPLACED by a back-reference to A...
    assert _FINDING not in b.verified_text
    assert 'See "Economic Impact" for this finding.' in b.verified_text
    # ...its OWN citation [3] is PRESERVED (§-1.3 keep-all — no citation dropped)...
    assert "[3]" in b.verified_text
    # ...and B's DISTINCT sentence is UNTOUCHED (distinct content is never clustered / dropped).
    assert "Unemployment may rise to 8% in affected regions [5]." in b.verified_text


def test_distinct_findings_never_clustered(monkeypatch):
    """§-1.3 no-drop: two sections whose findings differ by a single figure have DIFFERENT signatures
    and are NEVER consolidated (nothing replaced, telemetry consolidated=0)."""
    monkeypatch.setenv(_FLAG, "1")
    a = _mk("A", "Robots will number 20 million by 2030 [1]. Extra distinct sentence one here [2].")
    b = _mk("B", "Robots will number 30 million by 2030 [3]. Extra distinct sentence two here [4].")
    before = (a.verified_text, b.verified_text)
    tel = consolidate_cross_section_repetition([a, b])
    assert tel.get("consolidated", 0) == 0
    assert (a.verified_text, b.verified_text) == before


# ── (3) FAIL-CONSERVATIVE: a guard error keeps the ORIGINAL sections + emits the degrade marker ──
def test_caller_guard_error_restores_sections_and_emits_degrade_marker(monkeypatch, caplog):
    monkeypatch.setenv(_FLAG, "1")
    a, b = _two_recycled_sections()
    before = (a.verified_text, b.verified_text)

    def _raiser(section_results):
        # Simulate a PARTIAL in-place mutation before failing, to prove the caller restores it.
        if section_results:
            section_results[0].verified_text = "CORRUPTED PARTIAL SWAP"
        raise RuntimeError("boom")

    monkeypatch.setattr(msg, "consolidate_cross_section_repetition", _raiser)
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        out = _apply_cross_section_repetition_guard([a, b])
    # returns {} and the ORIGINAL sections are restored byte-for-byte (never dropped / partially-swapped).
    assert out == {}
    assert (a.verified_text, b.verified_text) == before
    # the DISTINCT degrade marker is emitted (the canary REJECTS it)...
    assert _FAILOPEN in caplog.text
    # ...and the positive consolidated= marker is NOT emitted on the error path.
    assert "consolidated=" not in caplog.text


# ── (4) the honest-liveness marker reports the REALIZED consolidated count (0 is an accepted fire) ─
def test_caller_marker_reports_realized_count_nonzero(monkeypatch, caplog):
    monkeypatch.setenv(_FLAG, "1")
    a, b = _two_recycled_sections()
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        _apply_cross_section_repetition_guard([a, b])
    assert "[activation] cross_section_repetition_guard: consolidated=1" in caplog.text
    assert _FAILOPEN not in caplog.text


def test_caller_marker_ran_ok_zero_is_honest_fire(monkeypatch, caplog):
    """§-1.3 no-threshold: a guard that RAN and found nothing to consolidate emits an HONEST
    ``consolidated=0`` (never suppressed, never a >0 gate) and NO degrade marker."""
    monkeypatch.setenv(_FLAG, "1")
    only = _mk("Solo", "A single lonely finding with no cross-section twin at all [1].")
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        _apply_cross_section_repetition_guard([only])
    assert "[activation] cross_section_repetition_guard: consolidated=0" in caplog.text
    assert _FAILOPEN not in caplog.text


# ── (5) run_gate_b activation-canary spec contract (mirrors summary_table / landmark / stance) ───
def _spec():
    by_name = {s.name: s for s in rg._ACTIVATION_MARKER_SPECS_WAVE3}
    assert "cross_section_repetition_guard" in by_name, (
        "cross_section_repetition_guard spec missing from _ACTIVATION_MARKER_SPECS_WAVE3"
    )
    return by_name["cross_section_repetition_guard"]


def test_spec_registered_with_flag_and_liveness_regex():
    spec = _spec()
    assert spec.env_flag == _FLAG
    # positive_re matches a realized fire (nonzero AND the accepted ran-ok-zero) ...
    assert spec.positive_re.search("[activation] cross_section_repetition_guard: consolidated=7")
    assert spec.positive_re.search("[activation] cross_section_repetition_guard: consolidated=0")
    # ...but NEVER an empty string (a dark guard leaves no marker at all).
    assert not spec.positive_re.search("")


def test_spec_failopen_is_absent_marker_and_blocklist_shape():
    spec = _spec()
    assert spec.absent_markers == (_FAILOPEN,)
    # default-OFF blocklist producer parity: NO count threshold, NO default-ON, whitelist=truthy set.
    assert spec.bool_checks == ()
    assert spec.exact_fields == ()
    assert spec.flag_default_on is False
    assert spec.flag_whitelist == ("1", "true", "on", "yes")


def _run_canary(monkeypatch, *marker_lines):
    """Drive rg.assert_activation_markers_fired with the canary opt-in + this flag ON and EVERY OTHER
    activation flag OFF, so ONLY the cross_section_repetition_guard spec is asserted."""
    monkeypatch.setenv("PG_ACTIVATION_CANARY", "1")
    monkeypatch.setenv(_FLAG, "1")
    for spec in (*rg._ACTIVATION_MARKER_SPECS, *rg._ACTIVATION_MARKER_SPECS_WAVE3):
        if spec.env_flag != _FLAG:
            monkeypatch.delenv(spec.env_flag, raising=False)
    # summary_table is DEFAULT-ON (flag_default_on): an UNSET flag stays ON and would over-demand its
    # marker on these no-table logs; pin it explicit "0" (delenv leaves the default-on path ON).
    monkeypatch.setenv("PG_RENDER_SUMMARY_TABLE", "0")
    log_text = "".join(
        "2026-07-06 12:00:00,000 INFO src.polaris_graph - " + m + "\n" for m in marker_lines
    )
    rg.assert_activation_markers_fired(log_text)


def test_canary_accepts_realized_marker(monkeypatch):
    _run_canary(monkeypatch, "[activation] cross_section_repetition_guard: consolidated=3")


def test_canary_accepts_ran_ok_zero(monkeypatch):
    _run_canary(monkeypatch, "[activation] cross_section_repetition_guard: consolidated=0")


def test_canary_rejects_dark_absent_marker(monkeypatch):
    with pytest.raises(RuntimeError):
        _run_canary(monkeypatch, "[activation] some_other_module: fired")


def test_canary_rejects_failopen(monkeypatch):
    with pytest.raises(RuntimeError):
        _run_canary(
            monkeypatch,
            "[activation] cross_section_repetition_guard: consolidated=3",
            _FAILOPEN,
        )
