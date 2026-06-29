"""I-deepfix-001 (#1344): wall-class RED->GREEN tests for the end-to-end fix campaign.

Each test simulates a WALL condition (a degraded/slow/blank judge, a CUDA-OOM, an
over-cap pair count, an off-enum judge token, a population mismatch) and asserts that
the stage now CONTINUES / HANDS OFF / SHIPS-DISCLOSED instead of hanging or
aborting-empty. RED before the fix (the prior behaviour HANGS or DROPS / ABORTS);
GREEN after (the fix bounds the wall / degrades-keep-all / labels-and-ships).

Offline: NO torch / sentence-transformers / GPU / network. Every scorer/judge is
injected via the existing seams; slow paths are simulated with `time.sleep` inside a
stub, NEVER a real model call.

Covers (the offline-isolatable subset of the 14 wall fixes):
  W01  corpus_adequacy_gate population reconcile (reported = classifier population)
  W04  consolidation_nli score_pairs wall + over-MAX_PAIRS skip-not-raise
  W06  content_relevance_judge escalation deadline (keep-at-full-weight on expiry)
  W07  credibility_llm_tiering batch wall + consecutive-fallback circuit-breaker
  W11  clinical strict_verify judge_error degrade-to-keep-with-label (always-release)
  W14  four-role judge_adapter off-enum degrade-this-claim (not the whole seam)
"""
from __future__ import annotations

import time

import pytest


# ───────────────────────────────────────────────────────────────────────────
# W01 — corpus_adequacy_gate population reconcile
# ───────────────────────────────────────────────────────────────────────────
def test_w01_reported_population_is_classifier_not_on_topic(monkeypatch):
    """The DECISION rides on-topic counts; the REPORTED total_sources/tier_counts must
    be the CLASSIFIER population so the spine FX-06 self-consistency tripwire holds.

    RED (pre-fix): total_sources/tier_counts re-tallied over ON-TOPIC evidence_rows →
    diverge from the classifier `dist` whenever ANY row is off-topic → FX-06 fires
    error_corpus_population_mismatch on a normal run.
    GREEN: reported total_sources == sum(classifier tier_counts); decision unchanged.
    """
    from src.polaris_graph.nodes.corpus_adequacy_gate import assess_corpus_adequacy

    # Classifier histogram = 3 sources. One evidence row is OFF-topic (low weight).
    classifier_tier_counts = {"T1": 2, "T2": 1}
    evidence_rows = [
        {"tier": "T1", "text": "a clinical finding", "relevance_weight": 0.9},
        {"tier": "T1", "text": "another finding", "relevance_weight": 0.9},
        {"tier": "T2", "text": "off topic chatter", "relevance_weight": 0.01},
    ]
    report = assess_corpus_adequacy(
        tier_counts=classifier_tier_counts,
        evidence_row_count=len(evidence_rows),
        domain="general",
        protocol=None,
        evidence_rows=evidence_rows,
    )
    # GREEN: reported population == classifier population (FX-06 equality by construction).
    assert report.total_sources == sum(classifier_tier_counts.values()) == 3
    assert dict(report.tier_counts) == classifier_tier_counts
    # The on-topic disclosure fields still carry the demoted count (methods honesty).
    assert report.on_topic_evidence_rows <= report.raw_grounded_evidence_rows


# ───────────────────────────────────────────────────────────────────────────
# W04 — consolidation_nli score_pairs wall + over-cap skip
# ───────────────────────────────────────────────────────────────────────────
def test_w04_over_max_pairs_skips_not_raises(monkeypatch):
    """An over-MAX_PAIRS scale guard must DEGRADE (skip, return no edges = unmerged =
    keep-all), not RAISE (which aborted the whole run via _apply_consolidation_nli).

    RED (pre-fix): `raise ValueError`. GREEN: returns [] (no merge), no exception.
    """
    import src.polaris_graph.synthesis.consolidation_nli as cnli

    monkeypatch.setenv("PG_CONSOLIDATION_NLI_MAX_PAIRS", "1")  # 3 texts => 3 pairs > 1

    def _never_called_predict(_batch):  # the predict must NOT run on the skip path
        raise AssertionError("predict should not run when pairs exceed the cap")

    edges = cnli.score_pairs(
        ["claim a", "claim b", "claim c"], predict_fn=_never_called_predict,
    )
    assert edges == []  # GREEN: skipped, no merge, no raise (keeps clusters unmerged)


def test_w04_scoring_wall_returns_partial_not_hangs(monkeypatch):
    """A slow cross-encoder must be bounded by PG_CONSOLIDATION_NLI_WALL_SECONDS: once
    the wall passes, STOP collecting edges and return the partial set (under-merge only).

    RED (pre-fix): pool.map blocks until ALL chunks finish (unbounded). GREEN: returns
    within ~the wall, not the full slow duration.
    """
    import src.polaris_graph.synthesis.consolidation_nli as cnli

    monkeypatch.setenv("PG_CONSOLIDATION_NLI_WALL_SECONDS", "1")
    monkeypatch.setenv("PG_CONSOLIDATION_NLI_WORKERS", "2")
    monkeypatch.setenv("PG_CONSOLIDATION_NLI_MAX_PAIRS", "100000")

    def _slow_predict(batch):
        time.sleep(5.0)  # each chunk takes 5s — far longer than the 1s wall
        # shape (len(batch), 3): index 1 = entailment; return non-entailing logits.
        return [[5.0, 0.0, 0.0] for _ in batch]

    texts = [f"claim {i}" for i in range(12)]  # 66 pairs -> several chunks
    t0 = time.monotonic()
    edges = cnli.score_pairs(texts, predict_fn=_slow_predict)
    elapsed = time.monotonic() - t0
    # GREEN: bounded ~ the wall (+ one in-flight chunk), nowhere near serial 6x5=30s.
    assert elapsed < 12.0, f"score_pairs did not honour the wall (took {elapsed:.1f}s)"
    assert isinstance(edges, list)  # partial (possibly empty) edge set, never a hang


# ───────────────────────────────────────────────────────────────────────────
# W06 — content_relevance escalation deadline
# ───────────────────────────────────────────────────────────────────────────
def test_w06_escalation_deadline_keeps_full_weight(monkeypatch):
    """When the GLM escalation deadline elapses, the un-escalated ambiguous passages are
    KEPT at FULL weight (always-release, never demote-on-timeout) — and the call returns
    promptly instead of blocking on the whole slow batch.

    RED (pre-fix): pool.map blocks until ALL ambiguous futures finish. GREEN: returns
    near the deadline; escalation_wall_hit set; demoted-on-timeout NEVER happens.
    """
    from src.polaris_graph.retrieval import content_relevance_judge as crj

    # Force every passage into the ambiguous band so they all need GLM escalation.
    monkeypatch.setenv("PG_CONTENT_RELEVANCE_WORKERS", "2")

    def _mid_band_reranker(pairs):
        return [0.5 for _ in pairs]  # mid-band => ambiguous => GLM escalation

    def _slow_glm(_question, _span):
        time.sleep(5.0)  # each GLM call is slow
        return ("INSUFFICIENT", "would demote if it returned")

    passages = [(i, f"http://x/{i}", f"body {i}") for i in range(8)]
    t0 = time.monotonic()
    report = crj.score_passages(
        "the research question",
        passages,
        glm_judge_fn=_slow_glm,
        reranker_predict_fn=_mid_band_reranker,
        deadline_monotonic=time.monotonic() + 1.0,  # 1s wall
    )
    elapsed = time.monotonic() - t0
    assert elapsed < 12.0, f"escalation did not honour the deadline ({elapsed:.1f}s)"
    assert report.escalation_wall_hit is True
    # GREEN: NO passage was demoted on the timeout — every verdict is full weight.
    assert all(v.weight == 1.0 for v in report.verdicts), (
        "a passage was demoted on the escalation timeout (violates always-release)"
    )
    assert report.n_scored == len(passages)  # no passage dropped (§-1.3)


# ───────────────────────────────────────────────────────────────────────────
# W07 — credibility_llm_tiering batch wall + circuit-breaker
# ───────────────────────────────────────────────────────────────────────────
def _make_signals(n):
    from src.polaris_graph.retrieval.tier_classifier import ClassificationSignals

    out = []
    for i in range(n):
        try:
            out.append(ClassificationSignals(url=f"http://src/{i}", domain=f"src{i}.org"))
        except TypeError:
            # Signature drift — fall back to a permissive constructor probe.
            out.append(ClassificationSignals(url=f"http://src/{i}"))  # type: ignore[call-arg]
    return out


def test_w07_batch_wall_keeps_floor_not_hangs(monkeypatch):
    """A blank/trickle tiering storm must be bounded by the batch wall: un-returned
    sources keep the deterministic rules-FLOOR (no drop), and the call returns promptly.

    RED (pre-fix): pool.map blocks until ALL N futures finish (unbounded). GREEN:
    returns near the wall; every source still has a tier (floor for un-returned).
    """
    from src.polaris_graph.retrieval import credibility_llm_tiering as clt

    monkeypatch.setenv("PG_TIER_LLM_WORKERS", "2")
    monkeypatch.setenv("PG_TIER_LLM_BATCH_WALL_SECONDS", "1")
    monkeypatch.setenv("PG_TIER_LLM_DEGRADE_AFTER", "0")  # isolate the WALL (no breaker)

    def _slow_caller(_prompt):
        time.sleep(5.0)  # each tiering call is slow
        return '{"tier": "T1", "confidence": 0.9}'

    signals = _make_signals(8)
    t0 = time.monotonic()
    results = clt.classify_sources_llm_tiering(signals, call_llm=_slow_caller)
    elapsed = time.monotonic() - t0
    assert elapsed < 12.0, f"tiering did not honour the batch wall ({elapsed:.1f}s)"
    # GREEN: 1:1 result list, every source has a (floor or LLM) tier — none dropped.
    assert len(results) == len(signals)
    assert all(getattr(r, "tier", None) is not None for r in results)


def test_w07_circuit_breaker_short_circuits_to_floor(monkeypatch):
    """After N consecutive fallbacks the breaker short-circuits the REMAINING sources
    straight to the rules-floor instead of paying the per-call budget on each.

    RED (pre-fix): no breaker — every source pays the (slow) call. GREEN: once the
    consecutive-fallback threshold trips, the remaining sources are NOT awaited.
    """
    from src.polaris_graph.retrieval import credibility_llm_tiering as clt

    monkeypatch.setenv("PG_TIER_LLM_WORKERS", "1")  # serial -> deterministic order
    monkeypatch.setenv("PG_TIER_LLM_BATCH_WALL_SECONDS", "0")  # isolate the BREAKER
    monkeypatch.setenv("PG_TIER_LLM_DEGRADE_AFTER", "2")

    calls = {"n": 0}

    def _always_fallback_caller(_prompt):
        calls["n"] += 1
        time.sleep(0.2)  # slow enough that the gather collects results incrementally
        return ""  # blank -> llm_tier_one returns None -> fallback

    signals = _make_signals(10)
    results = clt.classify_sources_llm_tiering(signals, call_llm=_always_fallback_caller)
    assert len(results) == len(signals)
    assert all(getattr(r, "tier", None) is not None for r in results)
    # GREEN: the breaker stops AWAITING calls well before all 10 sources (short-circuit).
    # With 1 worker + the 0.2s caller, futures complete one-at-a-time so the breaker trips
    # at the threshold and the remaining sources are not awaited (kept at the rules-floor).
    assert calls["n"] < 10, (
        f"circuit-breaker did not short-circuit (awaited {calls['n']}/10 calls)"
    )


# ───────────────────────────────────────────────────────────────────────────
# W11 — clinical strict_verify judge_error degrade-to-keep-with-label
# ───────────────────────────────────────────────────────────────────────────
class _JudgeStub:
    """A judge that returns a fixed (verdict, reason)."""

    def __init__(self, verdict, reason):
        self._v = verdict
        self._r = reason

    def judge(self, _sentence, _span):
        return (self._v, self._r)


def _verify_with_judge(monkeypatch, judge, env):
    """Run verify_sentence over a token'd sentence that passes the (a)-(e) gates,
    with the given judge stub installed and env applied. Returns (passed, reason)."""
    from datetime import datetime, timezone

    from src.polaris_graph.clinical_generator import strict_verify
    from src.polaris_graph.clinical_generator.strict_verify import verify_sentence
    from src.polaris_graph.clinical_retrieval.evidence_pool import (
        AdequacyVerdict,
        EvidencePool,
        Source,
        SourceTier,
    )

    full_text = "The trial reported a 12 percent improvement in the primary outcome."
    src = Source(
        url="https://www.urncst.org/article",
        domain="urncst.org",
        tier=SourceTier.T1,
        title="Source",
        snippet="snippet",
        full_text=full_text,
        full_text_available=True,
        source_id="src-1",
    )
    pool = EvidencePool(
        decision_id="dec-w11",
        sources=[src],
        adequacy=AdequacyVerdict(
            is_adequate=True,
            sources_per_tier={SourceTier.T1: 0, SourceTier.T2: 0, SourceTier.T3: 0},
            min_required_per_tier={SourceTier.T1: 0, SourceTier.T2: 0, SourceTier.T3: 0},
        ),
        retrieval_started_at_utc=datetime.now(timezone.utc),
        retrieval_finished_at_utc=datetime.now(timezone.utc),
        latency_ms=0,
        cost_usd=0.0,
    )
    monkeypatch.setattr(strict_verify, "_JUDGE_SINGLETON", judge, raising=False)
    monkeypatch.setattr(strict_verify, "_get_judge", lambda: judge)
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    sentence = (
        "The trial reported a 12 percent improvement in the primary outcome "
        f"[#ev:src-1:0-{len(full_text)}]."
    )
    return verify_sentence(sentence, pool)


def test_w11_judge_error_degrades_to_keep_when_always_release(monkeypatch):
    """A TRANSPORT judge_error on a span-grounded claim must DEGRADE to keep-with-label
    (not drop) when PG_STRICT_VERIFY_JUDGE_ERROR_ALWAYS_RELEASE is ON.

    RED (pre-fix): enforce mode drops the sentence on judge_error. GREEN: keeps it with
    the 'entailment_unverified_judge_error' label. A genuine NEUTRAL still drops.
    """
    je_judge = _JudgeStub("ENTAILED", "judge_error: socket closed (transport fault)")

    # ON: judge_error degrades to keep-with-label.
    passed, reason = _verify_with_judge(
        monkeypatch, je_judge,
        {"PG_STRICT_VERIFY_JUDGE_ERROR_ALWAYS_RELEASE": "1"},
    )
    assert passed is True and reason == "entailment_unverified_judge_error"


def test_w11_judge_error_still_drops_when_release_off(monkeypatch):
    """OFF (default): a judge_error keeps the byte-identical enforce-drop."""
    je_judge = _JudgeStub("ENTAILED", "judge_error: socket closed (transport fault)")
    passed, reason = _verify_with_judge(
        monkeypatch, je_judge,
        {"PG_STRICT_VERIFY_JUDGE_ERROR_ALWAYS_RELEASE": "0"},
    )
    assert passed is False and reason == "entailment_judge_error_fail_closed"


def test_w11_genuine_neutral_still_drops_with_release_on(monkeypatch):
    """Even with always-release ON, a GENUINE NEUTRAL verdict still DROPS (faithfulness
    not relaxed — the degrade applies ONLY to transport judge_error)."""
    neutral_judge = _JudgeStub("NEUTRAL", "the span does not entail this claim")
    passed, reason = _verify_with_judge(
        monkeypatch, neutral_judge,
        {"PG_STRICT_VERIFY_JUDGE_ERROR_ALWAYS_RELEASE": "1"},
    )
    assert passed is False and reason == "entailment_failed"


# ───────────────────────────────────────────────────────────────────────────
# W14 — four-role judge off-enum degrade-this-claim
# ───────────────────────────────────────────────────────────────────────────
def test_w14_judge_offenum_degrades_this_claim_not_seam(monkeypatch):
    """An off-enum Judge token must degrade THIS claim to UNSUPPORTED + a <judge_offenum>
    record (when PG_ROLE_TRANSPORT_DEGRADE is ON), NOT raise JudgeEnumError that tears
    down the whole D8 seam.

    RED (pre-fix): JudgeEnumError propagates uncaught. GREEN: returns the fail-closed
    UNSUPPORTED verdict + a degrade record. OFF: re-raises (byte-identical).
    """
    import src.polaris_graph.roles.judge_adapter as ja
    from src.polaris_graph.roles.judge_contract import JudgeEnumError

    class _OffEnumResponse:
        raw_text = '{"verdict": "supported."}'  # off-enum (punct + json wrap)
        served_model = "stub"

    class _OffEnumTransport:
        def complete(self, _request):
            return _OffEnumResponse()

    def _run():
        return ja.run_judge(
            _OffEnumTransport(),
            claim="The trial improved the outcome.",
            evidence="The trial improved the primary outcome.",
            mirror_verdict="SUPPORTED",
            sentinel_verdict="SUPPORTED",
            model_slug="stub/judge",
        )

    # ON: off-enum degrades THIS claim to the fail-closed verdict + a <judge_offenum> record.
    monkeypatch.setenv("PG_ROLE_TRANSPORT_DEGRADE", "1")
    verdict, records = _run()
    assert verdict == ja._JUDGE_FAIL_CLOSED_VERDICT
    assert any("judge_offenum" in (getattr(r, "raw_text", "") or "") for r in records)

    # OFF: re-raises JudgeEnumError (byte-identical fail-loud, the whole seam tears down).
    monkeypatch.setenv("PG_ROLE_TRANSPORT_DEGRADE", "0")
    with pytest.raises(JudgeEnumError):
        _run()
