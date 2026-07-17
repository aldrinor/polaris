"""FIX 2 (KEYSTONE artifact hand-off) + FIX 5 (tame mask + journal leak) unit tests.

All OFFLINE — no network, no LLM, no live retrieval. Each test exercises a single
faithfulness-safe, upstream-of-the-verifier behavior the consolidated plan mandates:

  (i)   FIX 2(b): the pinned-contract IDENTITY GUARD — matching sha passes, a swapped
        sha (the recompiled-at-seam bug) trips it (returns an error string).
  (ii)  FIX 5(b): build_quality_eligibility emits per-source receipts, and a DOI/journal
        row PASSes the deterministic SECOND-CHANCE before the UNKNOWN fail-closed while a
        FAIL row (retracted / predatory / low-tier / is_peer_reviewed=False) still fails.
  (iii) FIX 5(c): two-tier topicality splits the below-floor rows into a HARD-quarantined
        junk band (< hard_floor) and a SOFT-demoted on-topic-adjacent band (>= hard_floor).
  (iv)  FIX 5(d): a journal/DOI row PASSes quality BEFORE UNKNOWN; a FAIL row still fails
        (evidence-positive only — no FAIL re-admitted).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.run_gate_e2e as rge  # noqa: E402
from src.polaris_graph.retrieval.quality_eligibility import (  # noqa: E402
    FAIL,
    PASS,
    UNKNOWN,
    build_quality_eligibility,
    build_topicality_eligibility,
    score_source_quality,
)


# ---------------------------------------------------------------------------
# (i) FIX 2(b): the pinned-contract identity guard
# ---------------------------------------------------------------------------

def _write_pin(sweep_dir: Path, sha: str) -> None:
    import json
    sweep_dir.mkdir(parents=True, exist_ok=True)
    (sweep_dir / "planning_gate_artifact.json").write_text(
        json.dumps({"contract_sha256": sha, "contract": {}}, ensure_ascii=False),
        encoding="utf-8")


def test_fix2_guard_passes_on_matching_sha(tmp_path: Path) -> None:
    sweep = tmp_path / "workforce" / "drb_72"
    _write_pin(sweep, "04c81bd7e68f_full_pinned_sha")
    assert rge._assert_pinned_contract_identity(sweep, "04c81bd7e68f_full_pinned_sha") == ""


def test_fix2_guard_trips_on_swapped_sha(tmp_path: Path) -> None:
    # The keystone bug: the seam recompiled a DIFFERENT contract than the gate pinned.
    sweep = tmp_path / "workforce" / "drb_72"
    _write_pin(sweep, "ad7638434434_recompiled_at_seam")  # what the seam wrote
    err = rge._assert_pinned_contract_identity(sweep, "04c81bd7e68f_gate_pinned")
    assert err  # non-empty -> caller sets d["error"], run never scored
    assert "IDENTITY GUARD" in err


def test_fix2_guard_trips_on_missing_pin(tmp_path: Path) -> None:
    sweep = tmp_path / "workforce" / "drb_72"
    sweep.mkdir(parents=True, exist_ok=True)  # no planning_gate_artifact.json
    err = rge._assert_pinned_contract_identity(sweep, "04c81bd7e68f_gate_pinned")
    assert err and "IDENTITY GUARD" in err


def test_fix2_guard_trips_on_empty_expected_sha(tmp_path: Path) -> None:
    sweep = tmp_path / "workforce" / "drb_72"
    _write_pin(sweep, "")
    err = rge._assert_pinned_contract_identity(sweep, "")
    assert err  # an empty pinned sha is not a steerable contract


# ---------------------------------------------------------------------------
# helpers for the eligibility tests
# ---------------------------------------------------------------------------

class _Policy:
    """Minimal duck-typed RetrievalPolicy for build_quality_eligibility."""

    def __init__(self, hard: bool = True) -> None:
        self.quality_profile = "high"
        self.predicate_force = {"quality_profile": "hard" if hard else "soft"}
        self.contract_hash = "TESTHASH"


def _verdict(row: dict) -> str:
    return score_source_quality(row)[0]


# ---------------------------------------------------------------------------
# (ii)/(iv) FIX 5(b): second-chance PASS before UNKNOWN; receipts; FAIL untouched
# ---------------------------------------------------------------------------

def test_fix5b_doi_row_passes_before_unknown() -> None:
    # No tier, no peer-review flag -> would be UNKNOWN(fail-closed); a DOI rescues it.
    row = {"source_url": "https://example.org/x", "doi": "10.1234/abcd"}
    assert _verdict(row) == PASS


def test_fix5b_journal_genre_row_passes_before_unknown() -> None:
    # OpenAlex GOLD peer-reviewed journal article -> PASS via the genre second-chance.
    row = {
        "source_url": "https://academic.example/x",
        "openalex_source_type": "journal",
        "openalex_is_peer_reviewed": True,
        "openalex_publication_type": "article",
    }
    assert _verdict(row) == PASS


def test_fix5b_bare_row_still_unknown() -> None:
    # No DOI, no journal genre, no tier -> the second-chance does NOT rescue -> UNKNOWN.
    row = {"source_url": "https://randomblog.example/post"}
    assert _verdict(row) == UNKNOWN


def test_fix5b_retracted_row_still_fails() -> None:
    # A FAIL verdict is UNTOUCHED even if it also carries a DOI (evidence-positive only).
    row = {"source_url": "https://x.example/a", "doi": "10.1/z", "is_retracted": True}
    assert _verdict(row) == FAIL


def test_fix5b_predatory_row_still_fails() -> None:
    row = {"source_url": "https://www.abacademies.org/articles/x.pdf", "doi": "10.9/q"}
    assert _verdict(row) == FAIL  # abacademies.org now in the predatory host patterns


def test_fix5b_low_tier_row_still_fails() -> None:
    row = {"source_url": "https://news.example/x", "tier": "T6", "doi": "10.5/n"}
    assert _verdict(row) == FAIL  # low tier FAILs before the DOI second-chance is consulted


def test_fix5b_not_peer_reviewed_row_still_fails() -> None:
    row = {"source_url": "https://shell.example/x", "is_peer_reviewed": False, "doi": "10.7/p"}
    assert _verdict(row) == FAIL


def test_fix5b_quality_plan_emits_receipts() -> None:
    # build_quality_eligibility must author one receipt per candidate + honor the second-chance.
    rows = [
        {"source_url": "https://a.example", "doi": "10.1/a"},        # PASS (DOI)
        {"source_url": "https://b.example", "is_retracted": True},   # FAIL (retracted)
        {"source_url": "https://c.example"},                          # UNKNOWN (bare)
    ]
    plan = build_quality_eligibility(_Policy(hard=True), rows)
    verdicts = {r.source_id: r.verdict for r in plan.receipts}
    assert verdicts["https://a.example"] == PASS
    assert verdicts["https://b.example"] == FAIL
    assert verdicts["https://c.example"] == UNKNOWN
    # HARD mode: FAIL + UNKNOWN are masked; the DOI-rescued PASS row is NOT.
    assert "https://a.example" not in plan.eligibility_excluded_ids
    assert "https://b.example" in plan.eligibility_excluded_ids
    assert "https://c.example" in plan.eligibility_excluded_ids


# ---------------------------------------------------------------------------
# (iii) FIX 5(c): two-tier topicality split
# ---------------------------------------------------------------------------

def test_fix5c_two_tier_topicality_split() -> None:
    rows = [
        {"source_url": "https://junk.example", "statement": "off topic"},   # score 0.05 -> HARD
        {"source_url": "https://band.example", "statement": "adjacent"},    # score 0.20 -> SOFT
        {"source_url": "https://good.example", "statement": "on topic"},    # score 0.80 -> PASS
    ]
    scores = {0: 0.05, 1: 0.20, 2: 0.80}

    def _scorer(objective, thread_qs, row_dicts):
        return dict(scores)

    plan = build_topicality_eligibility(
        rows, objective="the research objective", floor=0.30,
        scorer=_scorer, is_hard=True, hard_floor=0.15,
    )
    # < hard_floor (0.05) HARD-quarantined; the 0.15-0.30 band (0.20) SOFT-demoted (kept);
    # >= floor (0.80) stays.
    assert "https://junk.example" in plan.eligibility_excluded_ids
    assert "https://band.example" not in plan.eligibility_excluded_ids
    assert "https://good.example" not in plan.eligibility_excluded_ids
    # the band row carries a demote weight (order-not-drop), never a hard exclusion.
    assert plan.url_to_quality_weight.get("https://band.example", 1.0) < 1.0


def test_fix5c_single_floor_when_hard_floor_none() -> None:
    # hard_floor=None -> byte-identical single-floor behavior: ALL below-floor rows quarantine.
    rows = [
        {"source_url": "https://a.example", "statement": "x"},
        {"source_url": "https://b.example", "statement": "y"},
    ]
    scores = {0: 0.05, 1: 0.20}

    def _scorer(objective, thread_qs, row_dicts):
        return dict(scores)

    plan = build_topicality_eligibility(
        rows, objective="obj", floor=0.30, scorer=_scorer, is_hard=True,
    )
    assert "https://a.example" in plan.eligibility_excluded_ids
    assert "https://b.example" in plan.eligibility_excluded_ids  # 0.20 < 0.30, no band


# ---------------------------------------------------------------------------
# (i-integration) FIX 2(a)+(c): the seam LOADS a written pin (same sha, no recompile);
# an absent pin fires the recompile-at-seam WARNING + manifest stamp.
# ---------------------------------------------------------------------------

_REAL_ARTIFACT = (
    REPO_ROOT
    / "outputs/gate_e2e_final2/workforce/drb_72_ai_labor/draw1/planning_gate_artifact.json"
)


@pytest.mark.skipif(not _REAL_ARTIFACT.is_file(), reason="real draw1 artifact fixture absent")
def test_fix2_seam_loads_written_pin_same_sha(tmp_path: Path) -> None:
    """FIX 2(a): the pin written to the TASK-LEVEL sweep dir is loaded VERBATIM by the seam
    (its contract_sha256 honored, NOT recomputed) — the hand-off the keystone bug broke."""
    import json

    import scripts.run_honest_sweep_r3 as rhs

    d = json.loads(_REAL_ARTIFACT.read_text(encoding="utf-8"))
    expected_sha = d.get("contract_sha256", "")
    assert expected_sha  # sanity

    # write the pin to the sweep run_dir the seam reads (mirrors FIX 2(a)).
    sweep = tmp_path / "workforce" / "drb_72_ai_labor"
    sweep.mkdir(parents=True, exist_ok=True)
    (sweep / "planning_gate_artifact.json").write_text(
        json.dumps(d, ensure_ascii=False), encoding="utf-8")

    logs: list[str] = []
    art = rhs._gate_load_or_compile_artifact(
        "the prompt", sweep, run_id="TEST", log=logs.append,
    )
    assert art is not None
    assert (art.contract_sha256 or "") == expected_sha  # loaded verbatim, NOT recompiled
    assert any("loaded pinned artifact" in m for m in logs)
    assert not any("RECOMPILED AT SEAM" in m for m in logs)


def test_fix2c_recompile_stamp_warns_and_stamps() -> None:
    """FIX 2(c): the recompile-at-seam signal logs a WARNING and stamps the per-Task
    telemetry so manifest['gate_contract_recompiled_at_seam']=True lands on every manifest."""
    import scripts.run_honest_sweep_r3 as rhs

    # fresh ContextVar state (simulate a run that set no other feature telemetry).
    token = rhs._FEATURE_TELEMETRY_CTX.set(None)
    try:
        logs: list[str] = []
        rhs._stamp_gate_recompiled_at_seam(logs.append)
        assert any("RECOMPILED AT SEAM" in m and "WARNING" in m for m in logs)
        feat = rhs._FEATURE_TELEMETRY_CTX.get()
        assert isinstance(feat, dict)
        assert feat.get("gate_contract_recompiled_at_seam") is True
    finally:
        rhs._FEATURE_TELEMETRY_CTX.reset(token)


def test_fix2c_stamp_merges_into_existing_telemetry() -> None:
    """The stamp must MERGE (not clobber) any pre-existing feature telemetry dict."""
    import scripts.run_honest_sweep_r3 as rhs

    token = rhs._FEATURE_TELEMETRY_CTX.set({"storm_query_expansion": {"fired": True}})
    try:
        rhs._stamp_gate_recompiled_at_seam(lambda _m: None)
        feat = rhs._FEATURE_TELEMETRY_CTX.get()
        assert feat.get("storm_query_expansion") == {"fired": True}  # preserved
        assert feat.get("gate_contract_recompiled_at_seam") is True  # added
    finally:
        rhs._FEATURE_TELEMETRY_CTX.reset(token)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
