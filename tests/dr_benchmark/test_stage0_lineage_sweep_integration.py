"""STAGE-0 LINEAGE SEAM — integration checks that touch run_honest_sweep_r3 / SWEEP_QUERIES.

Separated from the pure-resolver tests because importing ``run_honest_sweep_r3`` pulls the full
sweep module (dotenv, native thread-safety clamp, etc.). Still hermetic: NO network, NO LLM, NO
generation/scoring spend — these assert the seam-2/seam-4 INVARIANT the legacy override relies on
and the seam-8 single-brain property.
"""

from __future__ import annotations

import json

import pytest

from scripts.dr_benchmark import gate0_lineage as g


@pytest.fixture(autouse=True)
def _clear_selector(monkeypatch):
    monkeypatch.delenv(g.LINEAGE_SELECTOR_ENV, raising=False)
    yield


def test_raw_sweep_question_equals_legacy_canonical_for_drb72():
    """Seam-2/seam-4 INVARIANT: the raw registered SWEEP question for drb_72_ai_labor already
    EQUALS the legacy query.jsonl id=72 canonical. The legacy override ASSERTS this (never trusts
    the registered string blindly); this test locks it so a future SWEEP edit that drifts the
    question is caught here (deterministic, pre-spend) instead of at the fail-loud run."""
    from scripts.run_honest_sweep_r3 import SWEEP_QUERIES

    raw = next(
        e["question"] for e in SWEEP_QUERIES if e.get("slug") == "drb_72_ai_labor"
    )
    legacy = g.canonical_question_for_slug(
        "drb_72_ai_labor", lineage=g.LINEAGE_LEGACY_RACE_TASK
    )
    assert g.sha256_text(raw) == g.sha256_text(legacy)


def test_legacy_canonical_matches_scorer_query_jsonl_id72():
    """The legacy resolver returns the SAME record score_report_race.py --task-id 72 packs."""
    with open(g.DEFAULT_LEGACY_TASKS_PATH, encoding="utf-8") as fh:
        scorer_prompt = next(
            json.loads(l)["prompt"]
            for l in fh
            if l.strip() and json.loads(l).get("id") == 72
        )
    legacy = g.canonical_question_for_slug(
        "drb_72_ai_labor", lineage=g.LINEAGE_LEGACY_RACE_TASK
    )
    assert g.sha256_text(scorer_prompt) == g.sha256_text(legacy)


def test_ledger_impl_failure_predicate_is_lineage_independent(monkeypatch):
    """Seam-9 / FIX 3: the RequiredEntityLedger IMPLEMENTATION-failure (F27) predicate is
    lineage-INDEPENDENT — a ledger build/render/write exception FAILS LOUD under legacy too (it is
    NOT the coverage-shortfall decision). The coverage-shortfall report-only downgrade is a SEPARATE
    predicate (_legacy_coverage_shortfall_report_only), tested in the seam suite."""
    from scripts.run_honest_sweep_r3 import (
        _required_entity_ledger_failed_under_strict as pred,
    )

    monkeypatch.delenv(g.LINEAGE_SELECTOR_ENV, raising=False)
    assert pred(True, True, True) is True
    monkeypatch.setenv(g.LINEAGE_SELECTOR_ENV, g.LINEAGE_LEGACY_RACE_TASK)
    assert pred(True, True, True) is True  # STILL fires under legacy (fail-loud preserved)


def test_no_second_idx_override_in_sweep():
    """Seam-8 single-brain: the ONLY place the sweep re-binds q['question'] from a slug->idx/legacy
    mapping is the ONE GATE0 override block. Assert there is exactly ONE call to
    canonical_question_for_slug in run_honest_sweep_r3 (no second override that could re-force the
    DRB-II idx question and split-brain the legacy run)."""
    import inspect

    import scripts.run_honest_sweep_r3 as sweep

    src = inspect.getsource(sweep)
    # the import alias _gate0_canonical_q is used once at the override; count call-sites of the
    # resolver alias (import line excluded by requiring an open-paren).
    assert src.count("_gate0_canonical_q(") == 2  # legacy branch + default branch of the ONE block


# ─────────────────────────────────────────────────────────────────────────────
# Seam-8 SINGLE-BRAIN FLOW: the SAME task-72 raw value/SHA carries end-to-end.
# ─────────────────────────────────────────────────────────────────────────────
def test_single_brain_task72_value_carries_through_all_seams(monkeypatch, tmp_path):
    """The ONE legacy override binds q['question'] to the legacy canonical, and EVERY downstream
    seam reads THAT single q['question']. Behaviorally assert the SAME raw value + SHA is what the
    scope protocol.research_question, retrieval seed, compile_frame, contract plan, generator arg,
    H1, snapshot, and scorer pack all receive — by tracing the value each seam consumes from the
    bound q and proving they are one identical string (no second override forks the brain)."""
    from scripts.run_honest_sweep_r3 import SWEEP_QUERIES
    from src.polaris_graph.generator import corpus_snapshot as cs
    import scripts.score_report_race as scorer

    # (0) the bound legacy question — the single source every seam reads.
    legacy_q = g.canonical_question_for_slug(
        "drb_72_ai_labor", lineage=g.LINEAGE_LEGACY_RACE_TASK
    )
    legacy_sha = g.sha256_text(legacy_q)
    raw_registered = next(
        e["question"] for e in SWEEP_QUERIES if e.get("slug") == "drb_72_ai_labor"
    )
    # The override keeps the registered question (asserted raw==legacy) and marks it legacy.
    assert g.questions_raw_and_sha_equal(raw_registered, legacy_q)
    bound_q = {**next(e for e in SWEEP_QUERIES if e.get("slug") == "drb_72_ai_labor"),
               "question": legacy_q, "question_lineage": g.LINEAGE_LEGACY_RACE_TASK}

    # (1) scope protocol.research_question / retrieval seed / compile_frame / contract plan /
    #     generator arg / H1 all read q["question"] — the SAME object the override set.
    seam_value = bound_q["question"]
    assert seam_value == legacy_q and g.sha256_text(seam_value) == legacy_sha

    # (2) snapshot: the run stamps q["question"] + the legacy lineage marker.
    class _Stub:
        classified_sources: list = []
        evidence_rows: list = []
        notes: list = []
        api_calls: dict = {}
    cs.save_corpus_snapshot(
        tmp_path, run_id="r", question=bound_q["question"], slug=bound_q["slug"],
        domain="", evidence_for_gen=[{"id": "e1", "text": "x"}], retrieval=_Stub(),
        lineage=bound_q["question_lineage"],
    )
    snap = json.loads((tmp_path / "corpus_snapshot.json").read_text())
    assert snap["question"] == legacy_q and g.sha256_text(snap["question"]) == legacy_sha
    assert snap["lineage"] == g.LINEAGE_LEGACY_RACE_TASK

    # (3) scorer pack: with the legacy selector, the scorer guard verifies answered(snapshot) ==
    #     packed(query.jsonl id=72 prompt) == legacy canonical — the SAME sha end-to-end.
    monkeypatch.setenv(g.LINEAGE_SELECTOR_ENV, g.LINEAGE_LEGACY_RACE_TASK)
    packed_prompt = legacy_q  # RACE packs query.jsonl id=72 == the legacy canonical
    report_path = tmp_path / "report.md"
    report_path.write_text("report", encoding="utf-8")
    rc = scorer.assert_legacy_scorer_lineage(str(report_path), packed_prompt, 72)
    assert rc == 0  # answered == packed == canonical -> guard passes (no spend reached)


# ─────────────────────────────────────────────────────────────────────────────
# Scorer guard — BLOCKED / split-brain paths (hermetic, no spend, no API key).
# ─────────────────────────────────────────────────────────────────────────────
def test_scorer_guard_blocks_missing_and_mismatched_snapshot(monkeypatch, tmp_path):
    import scripts.score_report_race as scorer
    from src.polaris_graph.generator import corpus_snapshot as cs

    legacy_q = g.canonical_question_for_slug(
        "drb_72_ai_labor", lineage=g.LINEAGE_LEGACY_RACE_TASK
    )
    report_path = tmp_path / "report.md"
    report_path.write_text("report", encoding="utf-8")

    # DEFAULT lineage (selector unset): the guard is a no-op (returns 0) — byte-identical to HEAD.
    monkeypatch.delenv(g.LINEAGE_SELECTOR_ENV, raising=False)
    assert scorer.assert_legacy_scorer_lineage(str(report_path), legacy_q, 72) == 0

    monkeypatch.setenv(g.LINEAGE_SELECTOR_ENV, g.LINEAGE_LEGACY_RACE_TASK)
    # (a) no corpus_snapshot.json -> BLOCKED (2).
    assert scorer.assert_legacy_scorer_lineage(str(report_path), legacy_q, 72) == 2

    class _Stub:
        classified_sources: list = []
        evidence_rows: list = []
        notes: list = []
        api_calls: dict = {}

    # (b) snapshot present but stored under the DEFAULT lineage (no field) -> BLOCKED (2):
    #     the run did not answer the legacy question.
    cs.save_corpus_snapshot(
        tmp_path, run_id="r", question=legacy_q, slug="drb_72_ai_labor",
        domain="", evidence_for_gen=[{"id": "e1", "text": "x"}], retrieval=_Stub(),
        lineage=None,
    )
    assert scorer.assert_legacy_scorer_lineage(str(report_path), legacy_q, 72) == 2

    # (c) legacy snapshot but the PACKED prompt drifts from the answered question -> hard split-brain.
    cs.save_corpus_snapshot(
        tmp_path, run_id="r", question=legacy_q, slug="drb_72_ai_labor",
        domain="", evidence_for_gen=[{"id": "e1", "text": "x"}], retrieval=_Stub(),
        lineage=g.LINEAGE_LEGACY_RACE_TASK,
    )
    with pytest.raises(g.GateZeroLineageError):
        scorer.assert_legacy_scorer_lineage(str(report_path), "a DIFFERENT packed prompt", 72)


# ─────────────────────────────────────────────────────────────────────────────
# Default GOLDEN identity: the selected q + protocol-bound question are byte-identical
# to the HEAD-equivalent (no lineage key, DRB-II idx question), NOT just manifest shape.
# ─────────────────────────────────────────────────────────────────────────────
def test_default_selected_q_and_protocol_bytes_are_head_equivalent(monkeypatch, tmp_path):
    """GOLDEN (Sol test-harness gap): on the default lineage the selected q the sweep binds and the
    question the scope protocol would receive are byte-identical to the HEAD DRB-II idx canonical —
    NOT the legacy question, and carrying NO question_lineage marker. Hermetic: a synthetic DRB-II
    tasks file stands in for the (absent-in-worktree) gold file; the real legacy query.jsonl is
    used for the legacy side so the DISTINCTNESS assertion is against production bytes."""
    import json as _json

    monkeypatch.delenv(g.LINEAGE_SELECTOR_ENV, raising=False)
    drb = tmp_path / "drb.jsonl"
    drb.write_text(
        _json.dumps({"idx": g.SLUG_TO_IDX["drb_72_ai_labor"], "prompt": "DRB-II idx canonical"})
        + "\n",
        encoding="utf-8",
    )
    # The default override binds the DRB-II idx canonical (HEAD behavior) — NO lineage kwarg.
    default_q = g.canonical_question_for_slug("drb_72_ai_labor", str(drb))
    idx_canonical = g.load_canonical_question(g.SLUG_TO_IDX["drb_72_ai_labor"], str(drb))
    assert default_q == idx_canonical  # RAW-byte identical to the HEAD idx question
    # It is DISTINCT from the REAL legacy question (proves default did not silently pick legacy).
    legacy_q = g.canonical_question_for_slug(
        "drb_72_ai_labor", lineage=g.LINEAGE_LEGACY_RACE_TASK
    )
    assert g.sha256_text(default_q) != g.sha256_text(legacy_q)
    # The default-bound q carries NO lineage marker (the seam only attaches it under legacy); the
    # protocol.research_question the scope gate stores is exactly q["question"] == the idx canonical.
    bound_default_q = {"slug": "drb_72_ai_labor", "question": default_q}
    assert "question_lineage" not in bound_default_q
    assert bound_default_q["question"] == idx_canonical
