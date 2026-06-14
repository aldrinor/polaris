"""I-arch-004 F07 + F04 — fail-closed faithfulness gates + checkpoint/resume durability.

F07 (#1249/#1252) — fail-open faithfulness gates closed:
  * The strict-gate benchmark slate preflight FAILS CLOSED when a binding faithfulness
    gate is unset/misconfigured (advisory NLI, conflict detector off, wrong entailment model).
  * The cross-document NLI conflict-judge ERROR FAILS CLOSED under strict gates — the
    detector RAISES ConflictJudgeUnavailableError (run holds) instead of the additive
    fail-open ('neutral', 0.0) silently dropping a possible real contradiction. NO phantom
    conflict is fabricated.

F04 (#539/#629) — corpus-snapshot checkpoint/resume:
  * The snapshot carries DATA ONLY (evidence rows + retrieval corpus/counts), NEVER a
    faithfulness verdict (HARD INVARIANT §-1.3). Round-trips losslessly; the reconstructed
    retrieval carries the same corpus so gates RE-RUN on the reloaded data.

All offline: the conflict judge is INJECTED (a fake); the preflight + snapshot are pure
env/JSON. No network, no model.
"""

from __future__ import annotations

import importlib
import json

import pytest

from src.polaris_graph.retrieval import semantic_conflict_detector as scd


# ───────────────────────── F07: conflict-judge strict fail-closed ─────────────────────────

_ROW_A = {
    "evidence_id": "ev_a", "tier": "T1", "source_url": "u1",
    "direct_quote": "Adjuvant chemotherapy improved overall survival in stage II colon cancer.",
}
_ROW_B = {
    "evidence_id": "ev_b", "tier": "T1", "source_url": "u2",
    "direct_quote": "Adjuvant chemotherapy provided no overall survival benefit in stage II colon cancer.",
}


def _erroring_judge(a, b):
    raise RuntimeError("simulated transport/parse fault on the conflict judge")


def _neutral_judge(a, b):
    return "neutral", 0.9


def test_conflict_judge_error_skips_pair_when_not_strict():
    """Default (non-strict) path: a per-pair judge error FAILS OPEN — the pair is skipped,
    never fabricated as a conflict, and the run is NOT held. This is the existing additive
    behavior and must stay byte-identical when strict_fail_closed is False."""
    pairs = scd.extract_pairs(scd.cluster_candidate_rows([_ROW_A, _ROW_B]))
    records = scd.detect_semantic_conflicts(pairs, _erroring_judge, strict_fail_closed=False)
    assert records == []  # skipped, no fabricated conflict, no raise


def test_conflict_judge_error_holds_run_when_strict():
    """F07 strict fail-CLOSED: a per-pair judge error must RAISE ConflictJudgeUnavailableError
    (the caller maps it to a run-level HOLD) instead of silently skipping the pair. This is the
    core anti-fail-open assertion: an unadjudicable pair under strict gates can NOT be dropped."""
    pairs = scd.extract_pairs(scd.cluster_candidate_rows([_ROW_A, _ROW_B]))
    with pytest.raises(scd.ConflictJudgeUnavailableError):
        scd.detect_semantic_conflicts(pairs, _erroring_judge, strict_fail_closed=True)


def test_conflict_strict_hold_does_not_fabricate_a_conflict():
    """The strict-gate hold signals 'could not adjudicate', NEVER 'a conflict exists'. A judge
    error must NOT manufacture a SemanticConflictRecord (that would be a fabrication + a false
    PT08 abort). The error is raised, and zero records are produced from the erroring pair."""
    pairs = scd.extract_pairs(scd.cluster_candidate_rows([_ROW_A, _ROW_B]))
    raised = False
    try:
        scd.detect_semantic_conflicts(pairs, _erroring_judge, strict_fail_closed=True)
    except scd.ConflictJudgeUnavailableError as exc:
        raised = True
        # No SemanticConflictRecord text leaks into the error — it is "could not adjudicate".
        assert "conflict judge errored" in str(exc).lower()
    assert raised


def test_strict_does_not_change_a_clean_neutral_run():
    """A judge that returns clean verdicts produces the SAME result under strict and non-strict —
    strict only changes the ERROR path, never a successful adjudication (no over-hold)."""
    pairs = scd.extract_pairs(scd.cluster_candidate_rows([_ROW_A, _ROW_B]))
    assert scd.detect_semantic_conflicts(pairs, _neutral_judge, strict_fail_closed=True) == []
    assert scd.detect_semantic_conflicts(pairs, _neutral_judge, strict_fail_closed=False) == []


def test_production_judge_raises_under_strict_on_transport_error(monkeypatch):
    """The PRODUCTION judge (not just the loop) must RAISE under strict gates on a transport
    error instead of returning the fail-open ('neutral', 0.0). Without this, the in-judge swallow
    would hide the error from the loop and strict fail-closed would be a no-op."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    judge = scd._SemanticContradictionJudge(strict_fail_closed=True)

    class _BoomClient:
        def post(self, *a, **k):
            raise RuntimeError("connection reset")

    judge._client = _BoomClient()
    with pytest.raises(RuntimeError):
        judge.judge("claim a", "claim b")


def test_production_judge_fails_open_neutral_when_not_strict(monkeypatch):
    """The non-strict production judge keeps its additive fail-open ('neutral', 0.0) on a
    transport error — byte-identical to the pre-F07 behavior."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    judge = scd._SemanticContradictionJudge(strict_fail_closed=False)

    class _BoomClient:
        def post(self, *a, **k):
            raise RuntimeError("connection reset")

    judge._client = _BoomClient()
    label, conf = judge.judge("claim a", "claim b")
    assert (label, conf) == ("neutral", 0.0)


# ───────────────────────── F07: fail-closed faithfulness-slate preflight ─────────────────────────

def _load_sweep_module():
    """Import the sweep module fresh so module-level env reads are not cached across tests."""
    import scripts.run_honest_sweep_r3 as mod
    return importlib.reload(mod)


def test_preflight_noop_when_strict_gates_off(monkeypatch):
    """When PG_BENCHMARK_STRICT_GATES is unset, the preflight is a no-op (no raise) even if the
    other slate vars are wrong — a non-benchmark run is byte-identical."""
    monkeypatch.delenv("PG_BENCHMARK_STRICT_GATES", raising=False)
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")  # would be wrong if strict
    mod = _load_sweep_module()
    mod.assert_faithfulness_slate_or_fail()  # must NOT raise


def test_preflight_fails_closed_on_advisory_nli(monkeypatch):
    """Strict gates ON but PG_STRICT_VERIFY_ENTAILMENT not 'enforce' (advisory NLI) -> FAIL CLOSED."""
    monkeypatch.setenv("PG_BENCHMARK_STRICT_GATES", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "warn")
    monkeypatch.setenv("PG_SWEEP_NLI_CONFLICT", "1")
    monkeypatch.setenv("PG_ENTAILMENT_MODEL", "z-ai/glm-5.1")
    mod = _load_sweep_module()
    with pytest.raises(mod.FaithfulnessSlatePreflightError) as exc:
        mod.assert_faithfulness_slate_or_fail()
    assert "PG_STRICT_VERIFY_ENTAILMENT" in str(exc.value)


def test_preflight_fails_closed_on_conflict_detector_off(monkeypatch):
    """Strict gates ON but PG_SWEEP_NLI_CONFLICT off -> FAIL CLOSED."""
    monkeypatch.setenv("PG_BENCHMARK_STRICT_GATES", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    monkeypatch.delenv("PG_SWEEP_NLI_CONFLICT", raising=False)
    monkeypatch.setenv("PG_ENTAILMENT_MODEL", "z-ai/glm-5.1")
    mod = _load_sweep_module()
    with pytest.raises(mod.FaithfulnessSlatePreflightError) as exc:
        mod.assert_faithfulness_slate_or_fail()
    assert "PG_SWEEP_NLI_CONFLICT" in str(exc.value)


def test_preflight_fails_closed_on_wrong_entailment_model(monkeypatch):
    """Strict gates ON but PG_ENTAILMENT_MODEL drifted off the locked mirror (e.g. a stale gemma)
    -> FAIL CLOSED."""
    monkeypatch.setenv("PG_BENCHMARK_STRICT_GATES", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    monkeypatch.setenv("PG_SWEEP_NLI_CONFLICT", "1")
    monkeypatch.setenv("PG_ENTAILMENT_MODEL", "google/gemma-4-31b-it")
    mod = _load_sweep_module()
    with pytest.raises(mod.FaithfulnessSlatePreflightError) as exc:
        mod.assert_faithfulness_slate_or_fail()
    assert "PG_ENTAILMENT_MODEL" in str(exc.value)
    assert "gemma" in str(exc.value)  # the exact drift class this guards


def test_preflight_passes_on_correct_slate(monkeypatch):
    """Strict gates ON + the full correct slate (enforce NLI + conflict on + mirror model +
    default entailment model unset == mirror) -> passes (no raise)."""
    monkeypatch.setenv("PG_BENCHMARK_STRICT_GATES", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    monkeypatch.setenv("PG_SWEEP_NLI_CONFLICT", "true")
    monkeypatch.delenv("PG_ENTAILMENT_MODEL", raising=False)  # default == mirror
    mod = _load_sweep_module()
    mod.assert_faithfulness_slate_or_fail()  # must NOT raise


# ───────────────────────── F04: corpus snapshot DATA round-trip ─────────────────────────

class _FakeRetrieval:
    """Minimal stand-in for LiveRetrievalResult carrying the fields the snapshot persists."""

    def __init__(self, sources, rows):
        self.classified_sources = sources
        self.evidence_rows = rows
        self.notes = ["a note"]
        self.total_candidates_pre_filter = 100
        self.candidates_fetched = 40
        self.candidates_failed_fetch = 5
        self.candidates_total = 90
        self.candidates_processed = 90
        self.extraction_finding_rows = len(rows)
        self.corpus_truncated = False
        self.api_calls = {"serper": 3}


def _corpus_source(url, tier):
    from src.polaris_graph.nodes.corpus_approval_gate import CorpusSource
    return CorpusSource(url=url, tier=tier, title="t", domain="d")


def test_snapshot_saves_data_not_a_verdict(tmp_path):
    """HARD INVARIANT §-1.3: the snapshot serializes EVIDENCE DATA only — never a faithfulness
    verdict / strict_verify result / 'verified' flag. Assert no verdict-shaped key is present."""
    from src.polaris_graph.generator import corpus_snapshot as cs

    rows = [{"evidence_id": "ev_000", "direct_quote": "x", "source_url": "u1"}]
    retr = _FakeRetrieval([_corpus_source("u1", "T1")], rows)
    path = cs.save_corpus_snapshot(
        tmp_path, run_id="R1", question="Q?", slug="s", domain="d",
        evidence_for_gen=rows, retrieval=retr,
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    flat = json.dumps(payload).lower()
    for banned in ("verdict", "verified", "strict_verify", "entailed", "release_allowed",
                   "faithful", "nli_label"):
        assert banned not in flat, f"snapshot must carry NO verdict; found {banned!r}"


def test_snapshot_round_trips_the_corpus(tmp_path):
    """The reloaded snapshot must reproduce the evidence_for_gen rows + the retrieval corpus so
    the gates re-run on IDENTICAL data."""
    from src.polaris_graph.generator import corpus_snapshot as cs

    rows = [
        {"evidence_id": "ev_000", "direct_quote": "claim one", "source_url": "u1", "tier": "T1"},
        {"evidence_id": "ev_001", "direct_quote": "claim two", "source_url": "u2", "tier": "T2"},
    ]
    retr = _FakeRetrieval([_corpus_source("u1", "T1"), _corpus_source("u2", "T2")], rows)
    cs.save_corpus_snapshot(
        tmp_path, run_id="R1", question="Q?", slug="s", domain="d",
        evidence_for_gen=rows, retrieval=retr,
    )
    payload = cs.load_corpus_snapshot(tmp_path)
    assert payload["evidence_for_gen"] == rows
    recon = cs.reconstruct_retrieval(payload)
    assert recon.evidence_rows == rows
    assert [s.url for s in recon.classified_sources] == ["u1", "u2"]
    assert [s.tier for s in recon.classified_sources] == ["T1", "T2"]
    assert recon.candidates_fetched == 40
    assert recon.extraction_finding_rows == 2


def test_resume_load_fails_loud_on_missing_snapshot(tmp_path):
    """A --resume reload with no snapshot present raises (fail loud) rather than silently
    restarting a fresh retrieval that re-bills the network."""
    from src.polaris_graph.generator import corpus_snapshot as cs

    with pytest.raises(cs.CorpusSnapshotError):
        cs.load_corpus_snapshot(tmp_path)


def test_resume_load_fails_loud_on_version_mismatch(tmp_path):
    """A schema_version mismatch raises (refuse to resume a stale-shaped corpus)."""
    from src.polaris_graph.generator import corpus_snapshot as cs

    cs.snapshot_path(tmp_path).write_text(
        json.dumps({"schema_version": 999, "evidence_for_gen": [{"x": 1}]}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(cs.CorpusSnapshotError):
        cs.load_corpus_snapshot(tmp_path)


def test_resume_load_fails_loud_on_empty_corpus(tmp_path):
    """An empty evidence_for_gen raises (refuse to resume a run with no generator corpus)."""
    from src.polaris_graph.generator import corpus_snapshot as cs

    cs.snapshot_path(tmp_path).write_text(
        json.dumps({"schema_version": cs.SNAPSHOT_SCHEMA_VERSION, "evidence_for_gen": []}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(cs.CorpusSnapshotError):
        cs.load_corpus_snapshot(tmp_path)


def test_snapshot_atomic_write_leaves_no_tmp(tmp_path):
    """The save is atomic (temp + replace); after a successful write no .tmp residue remains."""
    from src.polaris_graph.generator import corpus_snapshot as cs

    rows = [{"evidence_id": "ev_000", "direct_quote": "x", "source_url": "u1"}]
    retr = _FakeRetrieval([_corpus_source("u1", "T1")], rows)
    cs.save_corpus_snapshot(
        tmp_path, run_id="R1", question="Q?", slug="s", domain="d",
        evidence_for_gen=rows, retrieval=retr,
    )
    assert not list(tmp_path.glob("*.tmp"))
    assert cs.snapshot_path(tmp_path).exists()


# ───────────────────── F04: INTEGRATION — run_one_query(resume=True) ─────────────────────

class _RetrievalSentinel(RuntimeError):
    """Raised if the MAIN run_live_retrieval is invoked on a resume run (it must NOT be)."""


class _ReachedGeneration(RuntimeError):
    """Sentinel raised by the generator stub AFTER it captures the evidence it received, so the
    test asserts the resume path threaded through to the generation rejoin without driving the
    entire 2500-line post-generation block."""


def test_resume_reaches_generation_with_snapshot_rows_and_no_reretrieval(tmp_path, monkeypatch):
    """F04 ACCEPT (integration): a --resume run on a deterministic out-root must
      (1) NOT call the main run_live_retrieval (no re-retrieval), and
      (2) hand the GENERATOR the snapshot's evidence rows (so the gates re-run on the reloaded
          DATA, not a cached verdict — the generator is the rejoin point, downstream of which
          strict_verify / NLI / 4-role / D8 all fire).
    This is the discriminating test: it executes the resume seam end-to-end through the 23
    guards, not just the snapshot module in isolation."""
    import asyncio
    from types import SimpleNamespace

    import scripts.run_honest_sweep_r3 as sweep
    from src.polaris_graph.generator import corpus_snapshot as cs

    monkeypatch.setenv("PG_CAPTURE_PIN", "0")
    monkeypatch.delenv("PG_V30_PHASE2_ENABLED", raising=False)  # keep the contract block offline
    monkeypatch.delenv("PG_BENCHMARK_STRICT_GATES", raising=False)
    monkeypatch.setenv("PG_USE_RESEARCH_PLANNER", "0")  # legacy outline path (no planner LLM)

    # Use the 'tech' domain so the corpus-adequacy gate (which is template-driven and stricter for
    # 'clinical') does not abort the run before generation — F04 resume is what we test here, not
    # adequacy. A generous tier mix keeps any adequacy floor satisfied regardless of domain.
    q = {"domain": "tech", "slug": "resume_smoke", "question": "Resume test question?"}
    run_dir = tmp_path / q["domain"] / q["slug"]
    run_dir.mkdir(parents=True, exist_ok=True)

    # Seed a snapshot (as if a prior run was killed mid-generation) with enough T1-T3 sources/rows
    # to clear any corpus-adequacy floor, so the resume path reaches the generation rejoin.
    snap_rows = []
    snap_sources = []
    for i in range(12):
        tier = "T1" if i < 5 else ("T2" if i < 9 else "T3")
        url = f"https://example.org/src{i}"
        snap_rows.append({
            "evidence_id": f"ev_{i:03d}", "direct_quote": f"snapshot claim {i}",
            "source_url": url, "tier": tier,
        })
        snap_sources.append(_corpus_source(url, tier))
    retr = _FakeRetrieval(snap_sources, snap_rows)
    cs.save_corpus_snapshot(
        run_dir, run_id="PRIOR", question=q["question"], slug=q["slug"], domain=q["domain"],
        evidence_for_gen=snap_rows, retrieval=retr,
    )

    # The MAIN retrieval must never be called on resume.
    def _retrieval_must_not_run(**kwargs):
        raise _RetrievalSentinel("main run_live_retrieval was called on a --resume run")

    monkeypatch.setattr(sweep, "run_live_retrieval", _retrieval_must_not_run)

    # Minimal scope gate (deterministic, no network).
    def _fake_scope(*args, **kwargs):
        protocol = SimpleNamespace(
            scope_decision="accepted", scope_rejected=False, scope_rejection_code=None,
            scope_reasons=[], needs_user_review=False,
            to_json_dict=lambda: {"decision": "accepted"},
        )
        return SimpleNamespace(protocol=protocol, protocol_sha256="0" * 64)

    monkeypatch.setattr(sweep, "run_scope_gate", _fake_scope)
    monkeypatch.setattr(sweep, "_classify_scope_with_llm", lambda **k: None)

    # Capture what the generator receives, then stop (so we don't drive the post-gen block).
    captured: dict = {}

    async def _capture_generator(*args, **kwargs):
        captured["evidence"] = kwargs.get("evidence")
        raise _ReachedGeneration("reached generation rejoin")

    monkeypatch.setattr(sweep, "generate_multi_section_report", _capture_generator)

    # run_one_query traps exceptions into an error manifest; that is fine — we assert on the
    # captured evidence + the retrieval sentinel, which prove the resume seam fired.
    asyncio.run(sweep.run_one_query(q, tmp_path, resume=True))

    assert "evidence" in captured, "resume path never reached the generation rejoin"
    got_ids = [r.get("evidence_id") for r in (captured["evidence"] or [])]
    expected_ids = [f"ev_{i:03d}" for i in range(12)]
    assert got_ids == expected_ids, (
        f"generator did not receive the snapshot rows on resume; got {got_ids!r}"
    )
