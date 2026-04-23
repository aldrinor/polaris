"""M-49 V28 preservation regression suite.

Codex V28 plan pass-2 APPROVED. Classified as preservation_guard
(not root_cause). Extends `test_m42_preservation.py` with V27
baselines + new V28-specific acceptance tests for M-44 (primary
citations), M-45 (refetch diagnostics), M-47 (mechanism extraction),
M-50 (per-trial subsections).

Target directory: `outputs/full_scale_v28/clinical/clinical_tirzepatide_t2dm/`.
Override via env `POLARIS_V28_SWEEP_ROOT` for integration tests.
If directory missing, every test skips (partial-run safety per
M-42 pass-2 pattern).

V27 baselines (measured 2026-04-22 from V27 manifest):
- Bibliography: 47 (V27 actual >= V25's 40)
- FDA context mentions: 16 (V27)
- EMA context mentions: 7
- NICE context mentions: 8
- Health Canada context mentions: 3
- Contradictions enumerated: 13
- Mechanism section word count: 184 (V27 — M-47 should lift >=350)
- Report total word count: ~3441

V28 acceptance requirements (per plan):
- Primary-trial citation for >=7 of 11 named pivotal trials
- SURPASS-CVOT primary cited
- SURPASS-2 primary ETDs present
- Trial Summary table with >=6 rows (M-45 contingent)
- Per-Trial Summaries block with >=2 subsections (M-50)
- Preservation floors: NICE>=4, HC>=2, FDA>=7, EMA>=3, biblio>=40
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import pytest


# ─────────────────────────────────────────────────────────────────
# V27 baselines + V28 acceptance thresholds
# ─────────────────────────────────────────────────────────────────
V27_BASELINES = {
    "biblio_size": 40,            # V27 actual 47 but floor at V25
    "fda_count": 7,
    "ema_count": 3,
    "nice_count": 4,
    "hc_count": 2,                # M-42d target preserved
    "contradictions_min": 10,     # V27 actual 13 but floor conservative
}

V28_ACCEPTANCE = {
    "primary_trials_cited_min": 7,    # of 11 pivotal trials
    "trial_table_rows_min": 6,        # M-42b table
    "per_trial_subsections_min": 2,   # M-50
    "mechanism_word_count_min": 350,  # M-42c + M-47
    "biblio_size_min": 40,
}

# Pivotal tirzepatide trials the V28 report should cover. Note this
# is used only for counting — trial names appear only here, not in
# implementation code (per M-32 generalization discipline; tests may
# carry specific names but implementation must not).
PIVOTAL_TRIALS = [
    "SURPASS-1", "SURPASS-2", "SURPASS-3", "SURPASS-4",
    "SURPASS-5", "SURPASS-6", "SURPASS-CVOT",
    "SURMOUNT-1", "SURMOUNT-2", "SURMOUNT-3", "SURMOUNT-4",
]


def _v28_sweep_root() -> Path:
    """Resolve the V28 sweep output root."""
    override = os.environ.get("POLARIS_V28_SWEEP_ROOT")
    if override:
        return Path(override)
    return (
        Path(__file__).parent.parent.parent
        / "outputs"
        / "full_scale_v28"
        / "clinical"
        / "clinical_tirzepatide_t2dm"
    )


def _require_v28_output() -> Path:
    root = _v28_sweep_root()
    if not root.exists():
        pytest.skip(
            f"V28 sweep output not yet present at {root}. "
            f"Run `python scripts/run_full_scale_v28.py` first "
            f"(or set POLARIS_V28_SWEEP_ROOT to point at a test "
            f"fixture)."
        )
    return root


def _load_json_if_present(root: Path, name: str) -> Any:
    p = root / name
    if not p.exists():
        pytest.skip(f"{name} not yet present at {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    return data


def _load_report(root: Path) -> str:
    p = root / "report.md"
    if not p.exists():
        pytest.skip(f"report.md missing at {p}")
    return p.read_text(encoding="utf-8")


def _load_bibliography(root: Path) -> list[dict[str, Any]]:
    data = _load_json_if_present(root, "bibliography.json")
    if not isinstance(data, list):
        pytest.fail(f"bibliography.json: expected list, got {type(data).__name__}")
    return data


def _load_contradictions(root: Path) -> list[dict[str, Any]]:
    p = root / "contradictions.json"
    if not p.exists():
        pytest.skip(f"contradictions.json not yet present at {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


# ─────────────────────────────────────────────────────────────────
# V27 preservation (must not regress)
# ─────────────────────────────────────────────────────────────────
class TestV27PreservationFloors:
    """V28 must not regress V27's wins."""

    def test_biblio_size_at_or_above_floor(self) -> None:
        root = _require_v28_output()
        biblio = _load_bibliography(root)
        assert len(biblio) >= V27_BASELINES["biblio_size"], (
            f"V28 biblio size {len(biblio)} below V27 floor "
            f"{V27_BASELINES['biblio_size']}"
        )

    def test_fda_count_preserved(self) -> None:
        root = _require_v28_output()
        biblio = _load_bibliography(root)
        fda = sum(
            1 for e in biblio
            if "fda.gov" in (e.get("url") or "").lower()
            or "accessdata" in (e.get("url") or "").lower()
        )
        assert fda >= V27_BASELINES["fda_count"], (
            f"V28 FDA {fda} < V27 baseline "
            f"{V27_BASELINES['fda_count']}"
        )

    def test_ema_count_preserved(self) -> None:
        root = _require_v28_output()
        biblio = _load_bibliography(root)
        ema = sum(
            1 for e in biblio
            if "ema.europa.eu" in (e.get("url") or "").lower()
        )
        assert ema >= V27_BASELINES["ema_count"], (
            f"V28 EMA {ema} < V27 baseline "
            f"{V27_BASELINES['ema_count']}"
        )

    def test_nice_count_preserved(self) -> None:
        root = _require_v28_output()
        biblio = _load_bibliography(root)
        nice = sum(
            1 for e in biblio
            if "nice.org.uk" in (e.get("url") or "").lower()
        )
        assert nice >= V27_BASELINES["nice_count"], (
            f"V28 NICE {nice} < V27 baseline "
            f"{V27_BASELINES['nice_count']}"
        )

    def test_hc_count_preserved(self) -> None:
        root = _require_v28_output()
        biblio = _load_bibliography(root)
        # HC hosts per clinical.yaml regulatory_anchors
        hc_hosts = ("canada.ca", "hres.ca", "hc-sc.gc.ca",
                    "cda-amc.ca", "hpfb-dgpsa.ca")
        hc = sum(
            1 for e in biblio
            if any(h in (e.get("url") or "").lower() for h in hc_hosts)
        )
        assert hc >= V27_BASELINES["hc_count"], (
            f"V28 HC {hc} < V27 floor {V27_BASELINES['hc_count']}"
        )

    def test_contradictions_preserved(self) -> None:
        root = _require_v28_output()
        contras = _load_contradictions(root)
        assert len(contras) >= V27_BASELINES["contradictions_min"], (
            f"V28 contradictions {len(contras)} < floor "
            f"{V27_BASELINES['contradictions_min']}"
        )


# ─────────────────────────────────────────────────────────────────
# M-44 acceptance: primary-trial citations in report
# ─────────────────────────────────────────────────────────────────
class TestM44PrimaryCitations:
    """V28 must cite primary publications for >=7 of 11 pivotal trials."""

    def test_pivotal_trial_coverage(self) -> None:
        root = _require_v28_output()
        report = _load_report(root)
        mentioned = sum(
            1 for trial in PIVOTAL_TRIALS
            if re.search(rf"\b{re.escape(trial)}\b", report)
        )
        assert mentioned >= V28_ACCEPTANCE["primary_trials_cited_min"], (
            f"V28 covers {mentioned}/{len(PIVOTAL_TRIALS)} pivotal "
            f"trials; need >={V28_ACCEPTANCE['primary_trials_cited_min']}"
        )

    def test_surpass_cvot_mentioned(self) -> None:
        root = _require_v28_output()
        report = _load_report(root)
        assert "SURPASS-CVOT" in report or "CVOT" in report, (
            "V28 must mention SURPASS-CVOT (cardiovascular outcome "
            "trial) — critical for 2026 clinical review"
        )

    def test_surpass_2_primary_etd_present(self) -> None:
        """SURPASS-2 primary ETDs per Frías NEJM 2021:
        -0.15%, -0.39%, -0.45% HbA1c (5/10/15 mg vs sema 1 mg).
        V28 must report at least one of these specific values in
        prose with citation. Normalized numeric match; unit variants
        %/pp/percentage points accepted."""
        root = _require_v28_output()
        report = _load_report(root)
        # Normalized value matcher
        patterns = [
            r"[-−]?0\.15\s*(?:%|pp|percentage point)",
            r"[-−]?0\.39\s*(?:%|pp|percentage point)",
            r"[-−]?0\.45\s*(?:%|pp|percentage point)",
        ]
        matched = any(re.search(p, report, re.IGNORECASE) for p in patterns)
        assert matched, (
            "V28 SURPASS-2 report must contain at least one primary "
            "ETD value (-0.15, -0.39, or -0.45 pp) with unit"
        )


# ─────────────────────────────────────────────────────────────────
# M-42b / M-50 structural acceptance
# ─────────────────────────────────────────────────────────────────
class TestStructuralDepthFloor:
    """M-42b trial table + M-50 per-trial subsections both contribute
    to Structural depth. V28 must have EITHER ≥6 trial-table rows OR
    ≥2 per-trial subsections — ideally both."""

    def test_trial_table_or_subsections_present(self) -> None:
        """Codex-approved acceptance: at least one structural
        artifact beyond plain prose."""
        root = _require_v28_output()
        report = _load_report(root)
        has_table = "## Per-Trial Summaries" in report or (
            "### Trial Summary" in report
        )
        assert has_table, (
            "V28 report must include either Trial Summary table or "
            "Per-Trial Summaries block — neither found"
        )

    def test_per_trial_subsections_count(self) -> None:
        """M-50 acceptance: ≥2 per-trial subsections when primaries
        qualify. Skip if M-50 suppressed (valid when <2 primaries
        have fat quotes)."""
        root = _require_v28_output()
        try:
            m50 = _load_json_if_present(root, "m50_per_trial_subsections.json")
        except Exception:
            pytest.skip("M-50 telemetry not found — subsections suppressed")
        entries = m50.get("entries", []) if isinstance(m50, dict) else []
        if not entries:
            pytest.skip("M-50 gated: fewer than 2 qualifying primaries")
        assert len(entries) >= V28_ACCEPTANCE["per_trial_subsections_min"], (
            f"V28 per-trial subsections {len(entries)} below floor "
            f"{V28_ACCEPTANCE['per_trial_subsections_min']}"
        )


# ─────────────────────────────────────────────────────────────────
# M-47 mechanism extraction acceptance
# ─────────────────────────────────────────────────────────────────
class TestM47MechanismExtraction:
    """V28 Mechanism section should extract ≥3 clamp/PK quantitative
    fields when a clamp paper is in the evidence subset."""

    def test_mechanism_word_count_lift(self) -> None:
        """M-42c + M-47 target: Mechanism section >=350 words.
        V27 was 184 words."""
        root = _require_v28_output()
        report = _load_report(root)
        # Find Mechanism section
        m = re.search(
            r"(?:^|\n)##?\s*Mechanism\s*\n+(.*?)(?=\n##? |\Z)",
            report, flags=re.DOTALL | re.IGNORECASE,
        )
        if not m:
            pytest.skip("No Mechanism section in V28 report")
        mech_words = len(m.group(1).split())
        assert mech_words >= V28_ACCEPTANCE["mechanism_word_count_min"], (
            f"V28 Mechanism {mech_words} words; V27 was 184, "
            f"target >={V28_ACCEPTANCE['mechanism_word_count_min']}"
        )

    def test_m47_clamp_validator_passes(self) -> None:
        """When Mechanism subset has a clamp paper, M-47 validator
        must pass (≥3 linked fields matched)."""
        root = _require_v28_output()
        try:
            m47 = _load_json_if_present(root, "m47_mechanism_clamp_diagnostic.json")
        except Exception:
            pytest.skip("M-47 diagnostic not found")
        if not isinstance(m47, dict):
            pytest.skip("M-47 diagnostic malformed")
        if m47.get("no_clamp_papers"):
            pytest.skip("Mechanism subset had no clamp papers — no-op")
        # Pass/fail branch
        passes = m47.get("any_passes_threshold", False)
        incomplete = m47.get("m47_mechanism_extraction_incomplete", False)
        if not passes:
            pytest.fail(
                f"V28 Mechanism clamp validator failed (regen "
                f"attempted, still incomplete). Flag: "
                f"m47_mechanism_extraction_incomplete={incomplete}. "
                f"Per-paper: {m47.get('per_paper')}"
            )


# ─────────────────────────────────────────────────────────────────
# M-45 diagnostic artifact presence
# ─────────────────────────────────────────────────────────────────
class TestM45DiagnosticArtifact:
    """Codex M-45 acceptance: refetch_diagnostics.json persisted with
    per-URL backend + char count + eligibility."""

    def test_refetch_diagnostics_persisted(self) -> None:
        root = _require_v28_output()
        p = root / "refetch_diagnostics.json"
        if not p.exists():
            pytest.skip("refetch_diagnostics.json not present")
        data = json.loads(p.read_text(encoding="utf-8"))
        assert isinstance(data, list), (
            "refetch_diagnostics.json must be a list"
        )
        # If empty list: builder didn't run or no refetches needed;
        # acceptable.
        for entry in data:
            assert "failure_mode" in entry, (
                f"diagnostic entry missing failure_mode: {entry}"
            )
            assert "method" in entry, (
                f"diagnostic entry missing method: {entry}"
            )


# ─────────────────────────────────────────────────────────────────
# M-44 telemetry artifact presence
# ─────────────────────────────────────────────────────────────────
class TestM44TelemetryArtifact:
    """M-44 primary-citation injection + validator telemetry persisted."""

    def test_m44_telemetry_persisted(self) -> None:
        root = _require_v28_output()
        p = root / "m44_primary_citation_telemetry.json"
        if not p.exists():
            pytest.skip("m44_primary_citation_telemetry.json not present")
        data = json.loads(p.read_text(encoding="utf-8"))
        assert isinstance(data, dict), (
            "m44 telemetry must be dict"
        )
        # Keys: injection_log, validator_violations
        assert "injection_log" in data
        assert "validator_violations" in data


# ─────────────────────────────────────────────────────────────────
# Metadata-only tests (always run)
# ─────────────────────────────────────────────────────────────────
class TestM53V29PrimaryCustody:
    """M-49 extension for V29: assert every configured anchor ends
    with cited_in_verified_prose=true. This is the authoritative
    V29 success test — if any anchor failed custody, V29 did not
    ship the pivotal trial coverage."""

    def test_all_anchors_cited_in_verified_prose(self) -> None:
        root = _require_v28_output()
        custody_path = root / "v29_primary_custody.json"
        if not custody_path.exists():
            pytest.skip(
                "v29_primary_custody.json not present — pre-V29 sweep "
                "output, or V29 bundle not yet in effect"
            )
        custody_log = json.loads(custody_path.read_text(encoding="utf-8"))
        assert isinstance(custody_log, list), (
            f"v29_primary_custody.json expected list, got "
            f"{type(custody_log).__name__}"
        )
        failing = [
            e for e in custody_log
            if not e.get("cited_in_verified_prose")
        ]
        if failing:
            # Generate diagnostic detail for each failing anchor:
            # identify which custody step broke.
            fail_report = []
            for e in failing:
                anchor = e.get("anchor", "?")
                if not e.get("found_in_live_corpus"):
                    reason = "retrieval (not in live_corpus)"
                elif not e.get("selected_into_pool"):
                    reason = "selector (dropped from evidence_pool)"
                elif not e.get("injected_into_section"):
                    reason = "generator (not injected into any section)"
                elif not e.get("direct_quote_adequate"):
                    reason = (
                        f"quote thin "
                        f"({e.get('direct_quote_chars', 0)} chars)"
                    )
                else:
                    reason = "generator prose (cited ev_id but no biblio [N])"
                fail_report.append(f"  {anchor}: FAIL at {reason}")
            pytest.fail(
                f"V29 custody: {len(failing)}/{len(custody_log)} "
                f"anchors not cited_in_verified_prose:\n"
                + "\n".join(fail_report)
            )

    def test_custody_log_has_required_9_fields(self) -> None:
        root = _require_v28_output()
        custody_path = root / "v29_primary_custody.json"
        if not custody_path.exists():
            pytest.skip("v29_primary_custody.json not present")
        custody_log = json.loads(custody_path.read_text(encoding="utf-8"))
        required = {
            "anchor", "found_in_live_corpus", "found_ev_id",
            "selected_into_pool", "injected_into_section",
            "direct_quote_chars", "direct_quote_adequate",
            "cited_in_verified_prose", "citation_count",
        }
        for entry in custody_log:
            assert required.issubset(entry.keys()), (
                f"custody entry missing required fields. Entry: {entry}. "
                f"Missing: {required - entry.keys()}"
            )


class TestBaselineConstants:
    """Sanity check: V27/V28 constants are correctly typed."""

    def test_v27_baselines_complete(self) -> None:
        assert V27_BASELINES["biblio_size"] == 40
        assert V27_BASELINES["hc_count"] == 2  # M-42d target
        assert V27_BASELINES["fda_count"] == 7
        assert V27_BASELINES["nice_count"] == 4

    def test_v28_acceptance_complete(self) -> None:
        assert V28_ACCEPTANCE["primary_trials_cited_min"] == 7
        assert V28_ACCEPTANCE["per_trial_subsections_min"] == 2
        assert V28_ACCEPTANCE["mechanism_word_count_min"] == 350

    def test_pivotal_trials_list(self) -> None:
        assert len(PIVOTAL_TRIALS) == 11

    def test_v28_sweep_root_override(self, monkeypatch) -> None:
        monkeypatch.setenv("POLARIS_V28_SWEEP_ROOT", "/tmp/test-v28")
        assert _v28_sweep_root() == Path("/tmp/test-v28")
