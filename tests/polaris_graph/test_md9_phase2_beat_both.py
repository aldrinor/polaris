"""M-D9 phase 2 — BEAT-BOTH dimension scoring tests.

Pins:
  - 7 default dimensions named per autoloop_beat_tier1_mandate
  - Each scorer is defensive on missing manifest fields
  - score_run validates the Protocol contract
  - Direction-aware diff (higher_is_better vs lower_is_better)
  - Severity tiers (ok / minor / major) + verdict mapping
  - Per-dimension tolerance env overrides (LAW VI)
  - Custom dimensions plug in cleanly via Protocol
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from src.polaris_graph.audit_ir.beat_both_scoring import (
    BEAT_BOTH_SCORERS,
    BeatBothDimension,
    BeatBothReport,
    BeatBothScoringError,
    BeatBothVerdict,
    DimensionRegression,
    DimensionScore,
    DimensionScorer,
    diff_dimension_scores,
    report_to_exit_code,
    score_run,
    tolerance_for,
)


# ---------------------------------------------------------------------------
# Fixtures: manifests
# ---------------------------------------------------------------------------


_RICH_MANIFEST: dict[str, Any] = {
    "citations": [
        "https://accessdata.fda.gov/drugsatfda_docs/label/2024/tirzepatide.pdf",
        "https://www.fda.gov/drugs/approval/2024",
        "https://www.ema.europa.eu/en/medicines/mounjaro",
        "https://nice.org.uk/guidance/ng28",
        "https://canada.ca/health/some-drug",
        "https://www.nejm.org/doi/full/10.1056/NEJMoa2107519",
        "https://thelancet.com/journals/lancet/article/PIIS0140-6736(21)01443-4",
    ],
    "claims": [
        {"n": 478, "baseline": 7.9, "endpoint": 5.7, "ci": "[5.4, 6.0]"},
        {"n": 1879, "baseline": 8.3, "endpoint": 6.1, "ci": "[5.9, 6.3]"},
        {"n": 1437, "baseline": 8.2, "endpoint": 6.5, "ci": "[6.3, 6.7]"},
        # Incomplete claim — missing CI:
        {"n": 938, "baseline": 8.0, "endpoint": 6.4, "ci": None},
    ],
    "tables": [
        {"id": "trial_summary"},
        {"id": "ae_profile"},
    ],
    "sections": [
        {"id": "surpass_1"},
        {"id": "surpass_2"},
        {"id": "surpass_3"},
        {"id": "ae_overview"},
    ],
    "report": {
        "body": (
            "Tirzepatide showed superior HbA1c reduction. However, "
            "gastrointestinal adverse events were notable. In contrast, "
            "the placebo arm showed minimal change. The dose-dependent "
            "effect was robust whereas the safety profile required "
            "monitoring. Although nausea was common, it generally "
            "resolved. Despite these findings, dose titration was "
            "effective."
        ),
    },
}


_THIN_MANIFEST: dict[str, Any] = {
    "citations": ["https://example.com/paper-1"],
    "report": {"body": "Some words here. Just two sentences."},
}


_EMPTY_MANIFEST: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Dimension taxonomy
# ---------------------------------------------------------------------------


def test_seven_beat_both_dimensions_present() -> None:
    """The locked memory autoloop_beat_tier1_mandate documents
    exactly 7 dimensions. Pin that count + names."""
    expected = {
        "unique_citations",
        "regulatory_coverage",
        "jurisdictional_precision",
        "claim_frames",
        "structural_depth",
        "contradiction_handling_grammar",
        "narrative_length",
    }
    actual = {dim.value for dim in BeatBothDimension}
    assert actual == expected
    assert len(BEAT_BOTH_SCORERS) == 7
    scorer_dims = {s.dimension for s in BEAT_BOTH_SCORERS}
    assert scorer_dims == expected


# ---------------------------------------------------------------------------
# score_run on rich manifest (smoke)
# ---------------------------------------------------------------------------


def test_score_run_rich_manifest_all_dimensions_populated() -> None:
    scores = score_run(_RICH_MANIFEST)
    assert set(scores.keys()) == {dim.value for dim in BeatBothDimension}
    # Sanity: every score has the structure we expect.
    for dim, score in scores.items():
        assert isinstance(score, DimensionScore)
        assert score.dimension == dim
        assert isinstance(score.value, float)
        assert score.higher_is_better is True
        assert score.rationale


def test_unique_citations_counts_dedup_urls() -> None:
    scores = score_run(_RICH_MANIFEST)
    assert scores["unique_citations"].value == 7.0


def test_regulatory_coverage_filters_known_regulatory_hosts() -> None:
    scores = score_run(_RICH_MANIFEST)
    # FDA + EMA + NICE + Canada + accessdata.fda.gov = 5 regulatory
    # (canada.ca + accessdata.fda.gov + fda.gov + ema.europa.eu + nice.org.uk)
    assert scores["regulatory_coverage"].value == 5.0


def test_jurisdictional_precision_distinct_jurisdictions() -> None:
    scores = score_run(_RICH_MANIFEST)
    # US (accessdata.fda.gov + fda.gov) + EU (ema) + UK (nice) + CA = 4
    assert scores["jurisdictional_precision"].value == 4.0


def test_claim_frames_only_complete_claims_count() -> None:
    scores = score_run(_RICH_MANIFEST)
    # 3 of 4 claims have all 4 fields populated; the 4th has ci=None
    assert scores["claim_frames"].value == 3.0


def test_structural_depth_tables_plus_sections() -> None:
    scores = score_run(_RICH_MANIFEST)
    # 2 tables + 4 sections = 6
    assert scores["structural_depth"].value == 6.0


def test_contradiction_handling_counts_all_markers() -> None:
    scores = score_run(_RICH_MANIFEST)
    # markers: however, in contrast, whereas, although, despite = 5
    assert scores["contradiction_handling_grammar"].value == 5.0


def test_narrative_length_word_count() -> None:
    scores = score_run(_RICH_MANIFEST)
    expected = float(len(_RICH_MANIFEST["report"]["body"].split()))
    assert scores["narrative_length"].value == expected


# ---------------------------------------------------------------------------
# Defensive: missing/empty manifest
# ---------------------------------------------------------------------------


def test_empty_manifest_returns_zero_for_every_dimension() -> None:
    scores = score_run(_EMPTY_MANIFEST)
    for dim, score in scores.items():
        assert score.value == 0.0, f"{dim} should be 0 for empty manifest"
        assert score.rationale  # rationale present even at zero


def test_thin_manifest_no_crash() -> None:
    scores = score_run(_THIN_MANIFEST)
    assert scores["unique_citations"].value == 1.0
    assert scores["regulatory_coverage"].value == 0.0
    assert scores["jurisdictional_precision"].value == 0.0
    assert scores["claim_frames"].value == 0.0
    assert scores["structural_depth"].value == 0.0
    assert scores["contradiction_handling_grammar"].value == 0.0


def test_score_run_rejects_non_dict_manifest() -> None:
    with pytest.raises(BeatBothScoringError, match="manifest"):
        score_run("not a dict")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Citation extraction defensiveness
# ---------------------------------------------------------------------------


def test_citation_extraction_handles_dict_entries() -> None:
    manifest = {
        "evidence": [
            {"url": "https://example.com/a"},
            {"source_url": "https://example.com/b"},
            {"doi": "10.1000/foo"},
            {"pmid": "12345"},
            {"some_other_key": "ignored"},
        ],
    }
    scores = score_run(manifest)
    assert scores["unique_citations"].value == 4.0


def test_citation_extraction_dedupes_across_paths() -> None:
    manifest = {
        "citations": ["https://example.com/a"],
        "evidence": ["https://example.com/a", "https://example.com/b"],
        "report": {
            "citations": ["https://example.com/a", "https://example.com/c"],
        },
    }
    scores = score_run(manifest)
    assert scores["unique_citations"].value == 3.0


def test_citation_extraction_ignores_non_string_entries() -> None:
    manifest = {"citations": [None, 42, ["nested"], "https://valid.com"]}
    scores = score_run(manifest)
    assert scores["unique_citations"].value == 1.0


# ---------------------------------------------------------------------------
# Diff: GREEN / YELLOW / RED verdicts
# ---------------------------------------------------------------------------


def _baseline_scores() -> dict[str, DimensionScore]:
    return score_run(_RICH_MANIFEST)


def test_diff_no_change_is_green() -> None:
    scores = _baseline_scores()
    report = diff_dimension_scores(scores, scores)
    assert report.verdict is BeatBothVerdict.GREEN
    assert all(d.severity == "ok" for d in report.dimensions)
    assert all(not d.is_regression for d in report.dimensions)


def test_diff_minor_regression_is_yellow() -> None:
    """Drop unique_citations by 3 (default tolerance 2.0); since 3 > 2
    but 3 <= 2*2 = 4, severity is 'minor' → YELLOW.
    """
    baseline = _baseline_scores()
    current = dict(baseline)
    current["unique_citations"] = DimensionScore(
        dimension="unique_citations",
        value=baseline["unique_citations"].value - 3,
        higher_is_better=True,
        rationale="dropped",
    )
    report = diff_dimension_scores(baseline, current)
    assert report.verdict is BeatBothVerdict.YELLOW
    citation_entry = next(
        d for d in report.dimensions if d.dimension == "unique_citations"
    )
    assert citation_entry.is_regression is True
    assert citation_entry.severity == "minor"


def test_diff_major_regression_is_red() -> None:
    """Drop narrative_length by 250 (default tolerance 100, 2x = 200);
    250 > 200 → severity 'major' → RED.
    """
    baseline = _baseline_scores()
    current = dict(baseline)
    current["narrative_length"] = DimensionScore(
        dimension="narrative_length",
        value=baseline["narrative_length"].value - 250,
        higher_is_better=True,
        rationale="dropped",
    )
    report = diff_dimension_scores(baseline, current)
    assert report.verdict is BeatBothVerdict.RED
    entry = next(
        d for d in report.dimensions if d.dimension == "narrative_length"
    )
    assert entry.severity == "major"


def test_diff_improvement_is_not_regression() -> None:
    """Adding citations should NOT regress."""
    baseline = _baseline_scores()
    current = dict(baseline)
    current["unique_citations"] = DimensionScore(
        dimension="unique_citations",
        value=baseline["unique_citations"].value + 50,
        higher_is_better=True,
        rationale="more citations",
    )
    report = diff_dimension_scores(baseline, current)
    assert report.verdict is BeatBothVerdict.GREEN
    entry = next(
        d for d in report.dimensions if d.dimension == "unique_citations"
    )
    assert entry.is_regression is False
    assert entry.delta == 50.0


def test_diff_within_tolerance_is_green() -> None:
    """Drop unique_citations by 1 (tolerance 2) → not a regression."""
    baseline = _baseline_scores()
    current = dict(baseline)
    current["unique_citations"] = DimensionScore(
        dimension="unique_citations",
        value=baseline["unique_citations"].value - 1,
        higher_is_better=True,
        rationale="slight drop",
    )
    report = diff_dimension_scores(baseline, current)
    assert report.verdict is BeatBothVerdict.GREEN


def test_diff_lower_is_better_dimension_direction_flip() -> None:
    """Custom dimension where lower=better. Increasing value = regression."""
    baseline = {
        "duplicate_claims": DimensionScore(
            dimension="duplicate_claims",
            value=2.0,
            higher_is_better=False,
            rationale="baseline",
        )
    }
    current = {
        "duplicate_claims": DimensionScore(
            dimension="duplicate_claims",
            value=10.0,
            higher_is_better=False,
            rationale="bad",
        )
    }
    report = diff_dimension_scores(
        baseline, current, tolerances={"duplicate_claims": 1.0},
    )
    assert report.verdict is BeatBothVerdict.RED
    entry = report.dimensions[0]
    assert entry.is_regression is True
    assert entry.severity == "major"


def test_diff_only_common_dimensions_compared() -> None:
    """Dimensions present in only baseline OR current are skipped."""
    baseline = _baseline_scores()
    current = dict(baseline)
    current["custom_dim"] = DimensionScore(
        dimension="custom_dim",
        value=5.0,
        higher_is_better=True,
        rationale="new",
    )
    report = diff_dimension_scores(baseline, current)
    dims = [d.dimension for d in report.dimensions]
    assert "custom_dim" not in dims
    assert "unique_citations" in dims


def test_diff_higher_is_better_mismatch_raises() -> None:
    baseline = {
        "x": DimensionScore(
            dimension="x", value=1.0, higher_is_better=True, rationale=""
        )
    }
    current = {
        "x": DimensionScore(
            dimension="x", value=2.0, higher_is_better=False, rationale=""
        )
    }
    with pytest.raises(BeatBothScoringError, match="higher_is_better"):
        diff_dimension_scores(baseline, current)


def test_diff_negative_tolerance_raises() -> None:
    baseline = _baseline_scores()
    with pytest.raises(BeatBothScoringError, match="negative"):
        diff_dimension_scores(
            baseline, baseline, tolerances={"unique_citations": -1.0},
        )


# ---------------------------------------------------------------------------
# Tolerance env overrides
# ---------------------------------------------------------------------------


def test_tolerance_for_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(
        "PG_BEAT_BOTH_UNIQUE_CITATIONS_TOLERANCE", raising=False
    )
    assert tolerance_for("unique_citations") == 2.0


def test_tolerance_for_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "PG_BEAT_BOTH_UNIQUE_CITATIONS_TOLERANCE", "10.5"
    )
    assert tolerance_for("unique_citations") == 10.5


def test_tolerance_for_env_clamps_negative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "PG_BEAT_BOTH_UNIQUE_CITATIONS_TOLERANCE", "-5.0"
    )
    assert tolerance_for("unique_citations") == 0.0


def test_tolerance_for_env_invalid_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "PG_BEAT_BOTH_UNIQUE_CITATIONS_TOLERANCE", "not_a_number"
    )
    assert tolerance_for("unique_citations") == 2.0


def test_tolerance_for_unknown_dimension_zero() -> None:
    assert tolerance_for("custom_dim") == 0.0


def test_tolerances_argument_overrides_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit tolerances= passed to diff_dimension_scores wins
    over env vars + built-in defaults."""
    monkeypatch.setenv(
        "PG_BEAT_BOTH_UNIQUE_CITATIONS_TOLERANCE", "0.5"
    )
    baseline = _baseline_scores()
    current = dict(baseline)
    current["unique_citations"] = DimensionScore(
        dimension="unique_citations",
        value=baseline["unique_citations"].value - 1,
        higher_is_better=True,
        rationale="-1",
    )
    # Env says tolerance=0.5; -1 would regress. Override to 5.0
    # → no regression.
    report = diff_dimension_scores(
        baseline, current, tolerances={"unique_citations": 5.0},
    )
    assert report.verdict is BeatBothVerdict.GREEN


# ---------------------------------------------------------------------------
# Custom scorers via Protocol
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ContractDraftCountScorer:
    """Custom scorer probing manifest['contracts']. Lower=better."""

    dimension: str = "contract_draft_count"
    higher_is_better: bool = False

    def score(self, manifest: dict[str, Any]) -> DimensionScore:
        contracts = manifest.get("contracts") or []
        return DimensionScore(
            dimension=self.dimension,
            value=float(len(contracts)),
            higher_is_better=self.higher_is_better,
            rationale=f"{len(contracts)} contracts",
        )


def test_custom_scorer_via_protocol() -> None:
    manifest = {"contracts": [1, 2, 3]}
    scores = score_run(manifest, scorers=(_ContractDraftCountScorer(),))
    assert "contract_draft_count" in scores
    assert scores["contract_draft_count"].value == 3.0
    assert scores["contract_draft_count"].higher_is_better is False


def test_score_run_rejects_wrong_dimension_name() -> None:
    """A scorer that returns a DimensionScore with mismatched
    dimension name is a Protocol violation — fail loudly."""

    @dataclass(frozen=True)
    class _BrokenScorer:
        dimension: str = "expected_name"
        higher_is_better: bool = True

        def score(self, manifest: dict[str, Any]) -> DimensionScore:
            return DimensionScore(
                dimension="wrong_name",
                value=0.0,
                higher_is_better=True,
                rationale="",
            )

    with pytest.raises(BeatBothScoringError, match="dimension"):
        score_run({}, scorers=(_BrokenScorer(),))


def test_score_run_rejects_wrong_direction() -> None:
    @dataclass(frozen=True)
    class _BrokenScorer:
        dimension: str = "x"
        higher_is_better: bool = True

        def score(self, manifest: dict[str, Any]) -> DimensionScore:
            return DimensionScore(
                dimension="x",
                value=0.0,
                higher_is_better=False,  # mismatched
                rationale="",
            )

    with pytest.raises(BeatBothScoringError, match="higher_is_better"):
        score_run({}, scorers=(_BrokenScorer(),))


def test_score_run_rejects_non_dimension_score_return() -> None:
    @dataclass(frozen=True)
    class _BrokenScorer:
        dimension: str = "x"
        higher_is_better: bool = True

        def score(self, manifest: dict[str, Any]) -> DimensionScore:
            return "not a score"  # type: ignore[return-value]

    with pytest.raises(BeatBothScoringError, match="DimensionScore"):
        score_run({}, scorers=(_BrokenScorer(),))


# ---------------------------------------------------------------------------
# CI exit-code mapping
# ---------------------------------------------------------------------------


def test_report_to_exit_code_red_returns_one() -> None:
    baseline = _baseline_scores()
    current = dict(baseline)
    current["unique_citations"] = DimensionScore(
        dimension="unique_citations",
        value=0.0,
        higher_is_better=True,
        rationale="all dropped",
    )
    report = diff_dimension_scores(baseline, current)
    assert report.verdict is BeatBothVerdict.RED
    assert report_to_exit_code(report) == 1


def test_report_to_exit_code_yellow_returns_zero() -> None:
    baseline = _baseline_scores()
    current = dict(baseline)
    current["unique_citations"] = DimensionScore(
        dimension="unique_citations",
        value=baseline["unique_citations"].value - 3,
        higher_is_better=True,
        rationale="-3",
    )
    report = diff_dimension_scores(baseline, current)
    assert report.verdict is BeatBothVerdict.YELLOW
    assert report_to_exit_code(report) == 0


def test_report_to_exit_code_green_returns_zero() -> None:
    baseline = _baseline_scores()
    report = diff_dimension_scores(baseline, baseline)
    assert report.verdict is BeatBothVerdict.GREEN
    assert report_to_exit_code(report) == 0


# ---------------------------------------------------------------------------
# diff_dimension_scores input contract
# ---------------------------------------------------------------------------


def test_diff_rejects_non_dict_baseline() -> None:
    with pytest.raises(BeatBothScoringError, match="dict"):
        diff_dimension_scores("not a dict", {})  # type: ignore[arg-type]


def test_diff_rejects_non_dict_current() -> None:
    with pytest.raises(BeatBothScoringError, match="dict"):
        diff_dimension_scores({}, "not a dict")  # type: ignore[arg-type]
