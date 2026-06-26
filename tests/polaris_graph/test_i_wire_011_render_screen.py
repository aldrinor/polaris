"""I-wire-011 (#1325) — offline self-tests for the render/compose/screen + canary + depth fixes.

No live calls: every helper is pure / deterministic. Asserts the faithfulness-STRENGTHENING
invariants: a chrome/truncated fragment is screened out (and the canary trips in enforce mode), a
complete supported sentence still renders, marker runs are capped, a contradiction renders a
CONTRADICTS line, and the depth layer emits >0 grounded key findings.
"""
from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest

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
