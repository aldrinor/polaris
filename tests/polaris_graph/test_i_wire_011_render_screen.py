"""I-wire-011 (#1325) — offline self-tests for the render/compose/screen + canary + depth fixes.

No live calls: every helper is pure / deterministic. Asserts the faithfulness-STRENGTHENING
invariants: a chrome/truncated fragment is screened out (and the canary trips in enforce mode), a
complete supported sentence still renders, marker runs are capped, a contradiction renders a
CONTRADICTS line, and the depth layer emits >0 grounded key findings.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import pathlib
from types import SimpleNamespace

import pytest


def _load_rhs():
    """Load scripts/run_honest_sweep_r3.py as a module (mirrors the per-test loaders above)."""
    spec = importlib.util.spec_from_file_location(
        "_rhs_wall", pathlib.Path(__file__).resolve().parents[2] / "scripts" / "run_honest_sweep_r3.py"
    )
    rhs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rhs)
    return rhs

from src.polaris_graph.generator import key_findings as kf
from src.polaris_graph.generator import provenance_generator as pg


# ── fix 1: corroboration claim-header chrome/truncation screen ───────────────
def test_claim_header_unrenderable_truncation_and_chrome():
    import importlib.util
    import pathlib

    spec = importlib.util.spec_from_file_location(
        "_rhs", pathlib.Path(__file__).resolve().parents[2] / "scripts" / "run_honest_sweep_r3.py"
    )
    rhs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rhs)

    # mid-word START cut, mid-word END cut, CC-license, numbered-ToC, gap-stub -> unrenderable
    assert rhs._claim_header_is_unrenderable("usand workers reduces the ratio by 0.2 points.")
    assert rhs._claim_header_is_unrenderable("a chatbot launched on Nov 30, 2022 drew comprehensi [...")
    assert rhs._claim_header_is_unrenderable("(article) is licensed under a Creative Commons license")
    assert rhs._claim_header_is_unrenderable("The Digital Transformation, 2023 2.6 Industry 4.0 reshapes")
    assert rhs._claim_header_is_unrenderable(
        "A claim previously stated here did not survive 4-role verification; curator-actionable gap."
    )
    # a complete, capitalized, on-topic claim still renders (NOT unrenderable)
    assert not rhs._claim_header_is_unrenderable(
        "Automation reduced the employment-to-population ratio by 0.2 percentage points."
    )
    # internal hyphen + decimal is a real claim, not truncation/ToC
    assert not rhs._claim_header_is_unrenderable(
        "Treatment-specific effects rose 3.2 percentage points over the period."
    )
    # word-boundary cosmetic trim never manufactures a mid-word "…"
    trimmed = rhs._normalize_claim_summary("Automation does indeed subsume " + "x " * 120, quote_trim=30)
    assert trimmed.endswith("…") and not trimmed.rstrip("…").endswith("subsum")


# ── fix 2/3: truncation skip + marker-run cap ────────────────────────────────
def test_is_truncated_fragment_high_precision():
    assert kf.is_truncated_fragment("the model accounted for treatment-speci [...")
    assert kf.is_truncated_fragment("Automation does indeed su…")
    assert kf.is_truncated_fragment("a partial word ending in hyphen-")
    # complete sentence with internal hyphen + trailing citation is NOT truncated
    assert not kf.is_truncated_fragment("Treatment-specific effects were observed. [12]")
    assert not kf.is_truncated_fragment("Wages rose 5% in 2023.")


def test_cap_citation_marker_runs():
    s = "AI raised productivity [12][13][14][15][16]."
    assert kf.cap_citation_marker_runs(s, 3) == "AI raised productivity [12][13][14]."
    # non-adjacent markers (distinct claims) are not merged/capped
    s2 = "A is true [1] and B is true [2] and C is true [3] and D [4]."
    assert kf.cap_citation_marker_runs(s2, 3) == s2
    # cap<=0 is a no-op (never strips all citations)
    assert kf.cap_citation_marker_runs(s, 0) == s


def test_build_key_findings_caps_markers_and_skips_truncated():
    good = SimpleNamespace(
        title="Efficacy", dropped_due_to_failure=False, is_gap_stub=False,
        sentences_verified=2,
        verified_text="Automation reduced employment by 0.2 points [12][13][14][15][16].",
    )
    out = kf.build_key_findings([good])
    assert "[12][13][14]" in out and "[15]" not in out  # capped to 3


# ── fix 5: chrome/truncation canary on the verified set ──────────────────────
def _sv(sentence, verified=True):
    return pg.SentenceVerification(
        sentence=sentence, tokens=[], is_verified=verified, failure_reasons=[], soft_warnings=[],
    )


def test_chrome_canary_warn_default_no_raise_but_counts(monkeypatch):
    monkeypatch.setenv(pg._CHROME_CANARY_ENV, "warn")
    pg.reset_chrome_canary_telemetry()
    pg._run_chrome_canary([_sv("a real finding ending in a truncated word-")])
    assert pg.get_chrome_canary_telemetry()["chrome_in_kept"] == 1


def test_chrome_canary_enforce_trips(monkeypatch):
    monkeypatch.setenv(pg._CHROME_CANARY_ENV, "enforce")
    pg.reset_chrome_canary_telemetry()
    with pytest.raises(pg.ChromeReachedVerifiedError):
        pg._run_chrome_canary([_sv("comprehensi [...")])


def test_chrome_canary_clean_set_passes(monkeypatch):
    monkeypatch.setenv(pg._CHROME_CANARY_ENV, "enforce")
    pg.reset_chrome_canary_telemetry()
    pg._run_chrome_canary([_sv("Automation reduced employment by 0.2 percentage points.")])
    assert pg.get_chrome_canary_telemetry()["chrome_in_kept"] == 0


# ── fix 4: CONTRADICTS both-sides block ──────────────────────────────────────
def test_render_contradicts_block(tmp_path):
    import importlib.util
    import pathlib

    spec = importlib.util.spec_from_file_location(
        "_rhs2", pathlib.Path(__file__).resolve().parents[2] / "scripts" / "run_honest_sweep_r3.py"
    )
    rhs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rhs)

    sidecar = tmp_path / "contradictions.json"
    sidecar.write_text(json.dumps([
        {
            "subject": "automation", "predicate": "employment effect",
            "relative_difference": 0.5,
            "claims": [
                {"value": 0.2, "unit": "%", "evidence_id": "a1", "source_tier": "T1"},
                {"value": 0.42, "unit": "%", "evidence_id": "b2", "source_tier": "T4"},
            ],
        },
        {"subject": "x", "predicate": "y", "claims": [{"value": 1, "evidence_id": "z"}]},  # 1-sided: skipped
    ]), encoding="utf-8")
    block = rhs._render_contradicts_block(str(sidecar))
    assert "CONTRADICTS: automation / employment effect" in block
    assert "0.2%" in block and "0.42%" in block and "ev=a1" in block
    assert "relative difference" in block
    # no sidecar -> empty, no heading
    assert rhs._render_contradicts_block(str(tmp_path / "missing.json")) == ""


# ── fix 6: grounded depth layer emits >0 key findings ────────────────────────
def test_depth_layer_emits_grounded_key_findings(monkeypatch):
    monkeypatch.setenv(kf._DEPTH_LAYER_ENV, "1")
    sr = SimpleNamespace(
        title="Labor effects", dropped_due_to_failure=False, is_gap_stub=False,
        sentences_verified=2,
        verified_text=(
            "Automation reduced employment by 0.2 percentage points [3]. "
            "A key limitation is that aggregate data obscure local effects [4]."
        ),
    )
    out = kf.build_depth_layer([sr])
    assert "**Key Findings**" in out
    assert "**Challenges**" in out  # real limitation cue present
    assert "[3]" in out
    # default OFF -> byte-identical empty
    monkeypatch.setenv(kf._DEPTH_LAYER_ENV, "0")
    assert kf.build_depth_layer([sr]) == ""


# ── I-wire-010 (#1324): the POST-RELEASE advisory NLI annotation wall ─────────
def test_nli_annotation_wall_skips_on_hang_and_continues():
    """A hung entailment judge that never returns is bounded by the wall: wait_for raises
    TimeoutError, the helper fail-opens to a skip marker, and the caller CONTINUES (the run
    is no longer wedged before the manifest write). Proxy for 'manifest is reached' — the real
    end-to-end manifest write is not feasible offline; this proves the deadlock is broken."""
    rhs = _load_rhs()

    async def _never_returns(_pairs):
        await asyncio.Event().wait()  # parks forever — the provider-hang the deadlock came from

    result, timed_out = asyncio.run(
        rhs._nli_annotation_with_wall([{"sentence": "x"}], 0.05, _never_returns)
    )
    assert timed_out is True
    assert result["nli_status"] == "skipped_wall_timeout"
    assert result["sentences_checked"] == 0
    assert result["advisory"] is True


def test_nli_annotation_wall_passes_through_result_when_fast():
    """When the annotator returns within the wall, its real result is returned unchanged
    (timed_out False) so the normal eligible/sidecar enrichment path runs."""
    rhs = _load_rhs()

    async def _fast(_pairs):
        return {"nli_status": "ok", "sentences_checked": 3, "disputed_count": 1}

    result, timed_out = asyncio.run(rhs._nli_annotation_with_wall([1, 2, 3], 5, _fast))
    assert timed_out is False
    assert result["sentences_checked"] == 3


def test_nli_annotation_wall_propagates_budget_and_unavailable():
    """Core Invariant §9.1.6 + LAW II: a BudgetExceededError (cap breach) and an unavailable
    judge must PROPAGATE out of the wall helper (NOT be swallowed by the timeout except, NOT
    become a skip marker) so the caller's existing `raise` / `unavailable` handlers fire."""
    rhs = _load_rhs()

    async def _budget(_pairs):
        raise rhs.BudgetExceededError("cap breached")

    with pytest.raises(rhs.BudgetExceededError):
        asyncio.run(rhs._nli_annotation_with_wall([1], 5, _budget))

    class _Unavailable(RuntimeError):
        pass

    async def _unavail(_pairs):
        raise _Unavailable("model down")

    with pytest.raises(_Unavailable):
        asyncio.run(rhs._nli_annotation_with_wall([1], 5, _unavail))


# ── I-wire-011 (#1325) gate iter-1 P1: opposing-pair selection (not claims[:2]) ─
def test_contradicts_block_picks_opposing_poles_not_first_two(tmp_path):
    """On a >2-claim basket the renderer must show the GENUINELY OPPOSING endpoints (min vs
    max value), NOT the positional first two. Crafted so claims[:2] would pick non-extreme
    sides (0.30, 0.10) while the true poles are 0.10 vs 0.90."""
    rhs = _load_rhs()
    sidecar = tmp_path / "contradictions.json"
    sidecar.write_text(json.dumps([
        {
            "subject": "drug X", "predicate": "response rate",
            "relative_difference": 8.0,
            "claims": [
                {"value": 0.30, "unit": "%", "evidence_id": "mid", "source_tier": "T3"},
                {"value": 0.10, "unit": "%", "evidence_id": "low", "source_tier": "T1"},
                {"value": 0.90, "unit": "%", "evidence_id": "high", "source_tier": "T5"},
            ],
        },
    ]), encoding="utf-8")
    block = rhs._render_contradicts_block(str(sidecar))
    # the true poles (low + high) are rendered as the two sides ...
    assert "ev=low" in block and "ev=high" in block
    # ... and the mid claim is NOT presented as one of the two opposing sides.
    assert "ev=mid" not in block
    assert "0.1%" in block and "0.9%" in block

    # helper unit-level: exact poles chosen, ties on a >2 same-value basket -> no arbitrary pair
    pair = rhs._select_opposing_pair([
        {"value": 0.30, "evidence_id": "mid"},
        {"value": 0.10, "evidence_id": "low"},
        {"value": 0.90, "evidence_id": "high"},
    ])
    assert {pair[0]["evidence_id"], pair[1]["evidence_id"]} == {"low", "high"}
    assert rhs._select_opposing_pair([
        {"value": 0.5, "evidence_id": "a"},
        {"value": 0.5, "evidence_id": "b"},
        {"value": 0.5, "evidence_id": "c"},
    ]) is None
    # exactly-2-claim semantic pair (both 0.0 sentinel) is a non-arbitrary pair -> returned
    sem = rhs._select_opposing_pair([
        {"value": 0.0, "evidence_id": "s1"}, {"value": 0.0, "evidence_id": "s2"},
    ])
    assert sem is not None and {sem[0]["evidence_id"], sem[1]["evidence_id"]} == {"s1", "s2"}


def test_contradicts_block_a17_incommensurable_not_rendered_as_contradiction(tmp_path):
    """A17 guard: a not_comparable record (the detector declaring a CATEGORY ERROR, not a real
    contradiction — degrees bucketed with metres) must NOT render a 'CONTRADICTS … VS …' pair;
    it is disclosed as INCOMMENSURABLE so a category error is never framed as a contradiction."""
    rhs = _load_rhs()
    sidecar = tmp_path / "contradictions.json"
    sidecar.write_text(json.dumps([
        {
            "subject": "sensor", "predicate": "reading", "not_comparable": True,
            "incommensurable_reason": "degrees vs metres",
            "claims": [
                {"value": 0.5, "unit": "deg", "evidence_id": "ang", "source_tier": "T2"},
                {"value": 100.0, "unit": "m", "evidence_id": "dist", "source_tier": "T2"},
            ],
        },
    ]), encoding="utf-8")
    block = rhs._render_contradicts_block(str(sidecar))
    assert "INCOMMENSURABLE: sensor / reading" in block
    assert "CONTRADICTS" not in block
    assert "0.5deg VS" not in block  # the misleading maximal-spread pair is never asserted


def test_contradicts_block_ambiguous_multiclaim_discloses_without_arbitrary_pair(tmp_path):
    """A >2-claim record with NO value spread cannot yield a genuine opposing pair: the block
    DISCLOSES the contradiction (count + sidecar) rather than fabricating an arbitrary [:2] pair."""
    rhs = _load_rhs()
    sidecar = tmp_path / "contradictions.json"
    sidecar.write_text(json.dumps([
        {
            "subject": "topic", "predicate": "stance",
            "claims": [
                {"value": 0.5, "evidence_id": "a"},
                {"value": 0.5, "evidence_id": "b"},
                {"value": 0.5, "evidence_id": "c"},
            ],
        },
    ]), encoding="utf-8")
    block = rhs._render_contradicts_block(str(sidecar))
    assert "CONTRADICTS: topic / stance — 3 same-subject claims disagree" in block
    assert " VS " not in block  # no arbitrary two-sided pair fabricated
