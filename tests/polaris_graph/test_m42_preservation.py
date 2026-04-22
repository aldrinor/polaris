"""M-42 preservation regression suite (Codex pass-3 required addition).

These tests validate that a V26 sweep output does not regress any
V25 baseline metric that the M-42 bundle was designed to preserve or
improve. Each test targets a single invariant stated in the approved
fix plan (`outputs/audits/v25/fix_plan.md` §"Preservation regression-
test suite").

Target directory: `outputs/full_scale_v26/clinical/clinical_tirzepatide_t2dm/`.
If that directory doesn't exist yet, every test skips with a clear
reason. Once V26 produces artifacts, the suite runs automatically.

V25 baselines (measured 2026-04-22 from V25 manifest):
- Bibliography size: 40
- T2 count: 10 (min acceptable: 3 per plan)
- Jurisdiction counts: FDA=7, EMA=3, HC=1, NICE=4
- Contradictions count: 15 (min acceptable: 10 per plan)

M-42d target: HC >= 2 (up from V25=1). All other baselines: >=.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import pytest


# ─────────────────────────────────────────────────────────────────────
# V25 baselines (Codex plan pass-3 approved)
# ─────────────────────────────────────────────────────────────────────
V25_BASELINES = {
    "biblio_size": 40,
    "t2_count": 3,                 # conservative floor per plan
    "fda_count": 7,
    "ema_count": 3,
    "nice_count": 4,
    "contradictions": 10,          # conservative floor per plan
    "mechanism_underframed_rate": 0.55,  # V25 ceiling per plan
}


def _v26_sweep_root() -> Path:
    """Resolve the V26 sweep output root. Allow override via env
    `POLARIS_V26_SWEEP_ROOT` for integration tests."""
    override = os.environ.get("POLARIS_V26_SWEEP_ROOT")
    if override:
        return Path(override)
    return (
        Path(__file__).parent.parent.parent
        / "outputs"
        / "full_scale_v26"
        / "clinical"
        / "clinical_tirzepatide_t2dm"
    )


def _require_v26_output() -> Path:
    root = _v26_sweep_root()
    if not root.exists():
        pytest.skip(
            f"V26 sweep output not yet present at {root}. "
            f"Run `python scripts/run_full_scale_v26.py` first."
        )
    return root


def _load_bibliography(root: Path) -> list[dict[str, Any]]:
    p = root / "bibliography.json"
    if not p.exists():
        pytest.skip(f"bibliography.json missing at {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        pytest.fail(f"bibliography.json expected list, got {type(data).__name__}")
    return data


def _load_contradictions(root: Path) -> list[dict[str, Any]]:
    p = root / "contradictions.json"
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def _load_report(root: Path) -> str:
    p = root / "report.md"
    if not p.exists():
        pytest.skip(f"report.md missing at {p}")
    return p.read_text(encoding="utf-8")


def _jurisdiction_count(biblio: list[dict[str, Any]], code: str) -> int:
    from src.polaris_graph.retrieval.evidence_selector import (
        _row_jurisdiction,
    )
    return sum(1 for b in biblio if _row_jurisdiction(b) == code)


def _tier_count(biblio: list[dict[str, Any]], tier: str) -> int:
    return sum(1 for b in biblio if b.get("tier") == tier)


# ─────────────────────────────────────────────────────────────────────
# Biblio-level preservation
# ─────────────────────────────────────────────────────────────────────


class TestBibliographyPreservation:
    def test_biblio_size_at_or_above_v25_baseline(self) -> None:
        root = _require_v26_output()
        biblio = _load_bibliography(root)
        assert len(biblio) >= V25_BASELINES["biblio_size"], (
            f"V26 biblio shrank: {len(biblio)} < "
            f"{V25_BASELINES['biblio_size']}"
        )

    def test_t2_count_at_or_above_v25_baseline(self) -> None:
        root = _require_v26_output()
        biblio = _load_bibliography(root)
        t2 = _tier_count(biblio, "T2")
        assert t2 >= V25_BASELINES["t2_count"], (
            f"V26 T2 dropped: {t2} < {V25_BASELINES['t2_count']}"
        )


# ─────────────────────────────────────────────────────────────────────
# Jurisdiction preservation (M-42d preservation guard validation)
# ─────────────────────────────────────────────────────────────────────


class TestJurisdictionPreservation:
    def test_fda_count_at_or_above_v25_baseline(self) -> None:
        root = _require_v26_output()
        biblio = _load_bibliography(root)
        fda = _jurisdiction_count(biblio, "FDA")
        assert fda >= V25_BASELINES["fda_count"], (
            f"V26 FDA dropped: {fda} < {V25_BASELINES['fda_count']} "
            f"(M-42d preservation guard failure)"
        )

    def test_ema_count_at_or_above_v25_baseline(self) -> None:
        root = _require_v26_output()
        biblio = _load_bibliography(root)
        ema = _jurisdiction_count(biblio, "EMA")
        assert ema >= V25_BASELINES["ema_count"], (
            f"V26 EMA dropped: {ema} < {V25_BASELINES['ema_count']} "
            f"(M-42d preservation guard failure)"
        )

    def test_nice_count_at_or_above_v25_baseline(self) -> None:
        root = _require_v26_output()
        biblio = _load_bibliography(root)
        nice = _jurisdiction_count(biblio, "NICE")
        assert nice >= V25_BASELINES["nice_count"], (
            f"V26 NICE dropped: {nice} < {V25_BASELINES['nice_count']} "
            f"(M-42d preservation guard failure)"
        )

    def test_hc_count_reaches_m42d_target(self) -> None:
        """M-42d success criterion: HC >= 2 (up from V25 baseline of 1)."""
        root = _require_v26_output()
        biblio = _load_bibliography(root)
        hc = _jurisdiction_count(biblio, "HC")
        assert hc >= 2, (
            f"V26 HC did not reach M-42d target: {hc} < 2. "
            f"Either HC pool too thin or quota expansion failed."
        )


# ─────────────────────────────────────────────────────────────────────
# Contradictions preservation
# ─────────────────────────────────────────────────────────────────────


class TestContradictionsPreservation:
    def test_contradictions_disclosed_at_or_above_v25_baseline(self) -> None:
        root = _require_v26_output()
        contradictions = _load_contradictions(root)
        assert len(contradictions) >= V25_BASELINES["contradictions"], (
            f"V26 contradictions count regressed: "
            f"{len(contradictions)} < {V25_BASELINES['contradictions']}"
        )


# ─────────────────────────────────────────────────────────────────────
# Mechanism section depth (M-42c target) + under-framing ceiling
# ─────────────────────────────────────────────────────────────────────


_MECHANISM_CLAIM_TOKENS = (
    "receptor", "half-life", "pharmacokinetic", "bioavailability",
    "signaling", "signalling", "pathway", "agonist", "antagonist",
    "binding", "affinity", "clamp", "metabolism", "kinetic",
    "pharmacodynamic",
)

# Frame elements mirror M-41c / M-42a — if a mechanism sentence
# names ONE of these frame-element tokens, it gets 1 credit. Need
# >= 3 to avoid under-framing.
_FRAME_ELEMENT_TOKENS = (
    # Quantitative / dose
    "mg", "μg", "ng", "ml", "kg", "nmol", "pmol", "%",
    "dose", "weekly", "daily", "once-weekly", "subcutaneous",
    # Species / system
    "human", "humans", "rat", "mouse", "cell", "in vitro", "in vivo",
    # Measurement / timepoint
    "hour", "minute", "day", "week", "c-max", "auc", "t-max", "t1/2",
    # Mechanism specifics
    "gip", "glp-1", "incretin", "glucagon",
)


def _extract_mechanism_section(report_md: str) -> str | None:
    """Find the Mechanism section prose. Return None if absent."""
    # Match a heading whose text begins with "Mechanism" (case-insensitive).
    pattern = r"(?:^|\n)##+\s*Mechanism[^\n]*\n(.+?)(?=\n##+\s|\Z)"
    m = re.search(pattern, report_md, re.IGNORECASE | re.DOTALL)
    return m.group(1) if m else None


def _mechanism_underframed_rate(mech_text: str) -> float:
    """Return fraction of mechanism-claim sentences with < 3 frame
    elements. 0.0 if no mechanism sentences found."""
    # Split into sentences by `. ` (simple heuristic; report prose is
    # LLM-generated with conventional punctuation).
    sentences = re.split(r"(?<=[.!?])\s+", mech_text)
    mech_sentences: list[str] = []
    for s in sentences:
        sl = s.lower()
        if any(tok in sl for tok in _MECHANISM_CLAIM_TOKENS):
            mech_sentences.append(sl)
    if not mech_sentences:
        return 0.0
    underframed = 0
    for sent in mech_sentences:
        frame_count = sum(1 for tok in _FRAME_ELEMENT_TOKENS if tok in sent)
        if frame_count < 3:
            underframed += 1
    return underframed / len(mech_sentences)


class TestMechanismUnderFraming:
    def test_mechanism_underframed_rate_at_or_below_v25_ceiling(self) -> None:
        """V25 ceiling: 6/11 strict-verified Mechanism sentences were
        under-framed ≈ 55%. V26 must not exceed this ratio."""
        root = _require_v26_output()
        report_md = _load_report(root)
        mech_text = _extract_mechanism_section(report_md)
        if mech_text is None:
            pytest.skip(
                "V26 report.md has no Mechanism section. M-40 outline "
                "trigger may not have fired; not a preservation failure."
            )
        rate = _mechanism_underframed_rate(mech_text)
        ceiling = V25_BASELINES["mechanism_underframed_rate"]
        assert rate <= ceiling, (
            f"V26 Mechanism under-framed rate {rate:.2%} > V25 ceiling "
            f"{ceiling:.2%}. M-42c expanded Mechanism section but "
            f"re-introduced under-framed mechanism claims — M-41c "
            f"regression."
        )


# ─────────────────────────────────────────────────────────────────────
# Fixture-loading self-test (runs always, not V26-gated)
# ─────────────────────────────────────────────────────────────────────


class TestSuiteMetadata:
    def test_v25_baselines_stable(self) -> None:
        """Guards against accidental baseline edits that would let
        regressions through silently."""
        assert V25_BASELINES["biblio_size"] == 40
        assert V25_BASELINES["fda_count"] == 7
        assert V25_BASELINES["ema_count"] == 3
        assert V25_BASELINES["nice_count"] == 4
        assert V25_BASELINES["contradictions"] == 10
        assert V25_BASELINES["mechanism_underframed_rate"] == 0.55

    def test_sweep_root_override_works(self, monkeypatch) -> None:
        """Env override must be honored for integration harness use."""
        monkeypatch.setenv("POLARIS_V26_SWEEP_ROOT", "/tmp/does-not-exist")
        # Path normalizes separators per-OS; compare parts.
        assert _v26_sweep_root() == Path("/tmp/does-not-exist")

    def test_mechanism_underframing_detector_flags_under_framed(
        self,
    ) -> None:
        """Detector must correctly identify under-framed mechanism
        sentences (< 3 frame elements)."""
        text = (
            "Tirzepatide is a dual GIP and GLP-1 receptor agonist. "
            "The receptor binding modulates metabolism and half-life."
        )
        # Sentence 1: receptor, gip, glp-1 → 3 frame elements → OK
        # Sentence 2: receptor, (no frame element tokens beyond these) → <3 → under-framed
        rate = _mechanism_underframed_rate(text)
        assert 0.0 < rate <= 1.0

    def test_mechanism_underframing_detector_returns_zero_when_empty(
        self,
    ) -> None:
        """No mechanism-claim sentences → 0.0 rate (not a failure)."""
        text = "This paragraph has no mechanism tokens at all."
        rate = _mechanism_underframed_rate(text)
        assert rate == 0.0
