"""I-bug-096 — judge-error telemetry counters.

Per Codex review of I-bug-092: the entailment-judge fail-open path
returns ("ENTAILED", "judge_error: ...") on transient OpenRouter
errors. A persistent outage could make the gate silently inert. These
tests pin the counter behavior so an operator can poll
get_judge_telemetry() and alert on judge_error rate.

Counter ownership: strict_verify-side per Codex iter-1 brief verdict.
Tests use FakeJudge to drive verdicts; counters tick from inside
verify_sentence's entailment branch, not the judge itself.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from polaris_graph.clinical_generator import strict_verify
from polaris_graph.clinical_generator.strict_verify import (
    get_judge_telemetry,
    reset_judge_telemetry,
    verify_sentence,
)
from polaris_graph.clinical_retrieval.evidence_pool import (
    AdequacyVerdict,
    EvidencePool,
    Source,
    SourceTier,
)


@pytest.fixture(autouse=True)
def _reset_counters() -> None:
    """Each test starts with zero counters."""
    reset_judge_telemetry()


# ---------- Fixtures ----------

def _src(full_text: str) -> Source:
    return Source(
        url="https://www.example.org/article",
        domain="example.org",
        tier=SourceTier.T1,
        title="t",
        snippet="s",
        full_text=full_text,
        full_text_available=True,
        source_id="src-1",
    )


def _pool(full_text: str) -> EvidencePool:
    return EvidencePool(
        decision_id="dec-tel",
        sources=[_src(full_text)],
        adequacy=AdequacyVerdict(
            is_adequate=True,
            sources_per_tier={
                SourceTier.T1: 1, SourceTier.T2: 0, SourceTier.T3: 0,
            },
            min_required_per_tier={
                SourceTier.T1: 0, SourceTier.T2: 0, SourceTier.T3: 0,
            },
        ),
        retrieval_started_at_utc=datetime.now(timezone.utc),
        retrieval_finished_at_utc=datetime.now(timezone.utc),
        latency_ms=0,
        cost_usd=0.0,
    )


class _FakeJudge:
    def __init__(self, verdict: str, reason: str = "fake") -> None:
        self.verdict = verdict
        self.reason = reason

    def judge(self, sentence: str, span: str) -> tuple[str, str]:
        return self.verdict, self.reason


def _install(monkeypatch, fake: _FakeJudge) -> None:
    monkeypatch.setattr(strict_verify, "_JUDGE_SINGLETON", fake, raising=False)
    monkeypatch.setattr(strict_verify, "_get_judge", lambda: fake)


_FULL_TEXT = (
    "Adults with chronic pain reported clinical benefit "
    "from regular treatment over the trial period."
)
_SENTENCE = (
    "Adults with chronic pain reported clinical benefit "
    f"[#ev:src-1:0-{len(_FULL_TEXT)}]."
)


# ---------- Counter starts at zero ----------

def test_telemetry_starts_at_zero() -> None:
    snap = get_judge_telemetry()
    assert snap == {
        "calls": 0,
        "entailed": 0,
        "neutral": 0,
        "contradicted": 0,
        "judge_error": 0,
    }


# ---------- Calls counter ----------

def test_calls_increments_on_each_judge_invocation(monkeypatch) -> None:
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    _install(monkeypatch, _FakeJudge("ENTAILED"))
    pool = _pool(_FULL_TEXT)
    for _ in range(5):
        verify_sentence(_SENTENCE, pool)
    snap = get_judge_telemetry()
    assert snap["calls"] == 5
    assert snap["entailed"] == 5


# ---------- Per-verdict counters ----------

def test_entailed_verdict_increments_entailed(monkeypatch) -> None:
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    _install(monkeypatch, _FakeJudge("ENTAILED"))
    verify_sentence(_SENTENCE, _pool(_FULL_TEXT))
    snap = get_judge_telemetry()
    assert snap["entailed"] == 1
    assert snap["neutral"] == 0
    assert snap["contradicted"] == 0
    assert snap["judge_error"] == 0


def test_neutral_verdict_increments_neutral(monkeypatch) -> None:
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    _install(monkeypatch, _FakeJudge("NEUTRAL"))
    verify_sentence(_SENTENCE, _pool(_FULL_TEXT))
    snap = get_judge_telemetry()
    assert snap["neutral"] == 1
    assert snap["entailed"] == 0


def test_contradicted_verdict_increments_contradicted(monkeypatch) -> None:
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    _install(monkeypatch, _FakeJudge("CONTRADICTED"))
    verify_sentence(_SENTENCE, _pool(_FULL_TEXT))
    snap = get_judge_telemetry()
    assert snap["contradicted"] == 1


# ---------- Judge_error counter (the key telemetry) ----------

def test_judge_error_increments_on_fail_open(monkeypatch) -> None:
    """Judge fail-open returns ('ENTAILED', 'judge_error: ...') —
    counter MUST tick judge_error, NOT entailed.

    This is the whole point of I-bug-096: distinguish "gate accepted
    the sentence" from "gate failed open and we don't actually know."
    """
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    _install(
        monkeypatch,
        _FakeJudge("ENTAILED", "judge_error: TimeoutError"),
    )
    verify_sentence(_SENTENCE, _pool(_FULL_TEXT))
    snap = get_judge_telemetry()
    assert snap["judge_error"] == 1, "fail-open MUST count as judge_error"
    assert snap["entailed"] == 0, "fail-open MUST NOT count as entailed"
    assert snap["calls"] == 1


def test_judge_error_distinct_from_entailed_in_mixed_run(monkeypatch) -> None:
    """Mixed run: 2 real ENTAILED + 1 fail-open + 1 NEUTRAL = realistic
    operator dashboard scenario.
    """
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    pool = _pool(_FULL_TEXT)

    _install(monkeypatch, _FakeJudge("ENTAILED", "looks good"))
    verify_sentence(_SENTENCE, pool)
    verify_sentence(_SENTENCE, pool)

    _install(monkeypatch, _FakeJudge("ENTAILED", "judge_error: HTTPError"))
    verify_sentence(_SENTENCE, pool)

    _install(monkeypatch, _FakeJudge("NEUTRAL"))
    verify_sentence(_SENTENCE, pool)

    snap = get_judge_telemetry()
    assert snap["calls"] == 4
    assert snap["entailed"] == 2
    assert snap["neutral"] == 1
    assert snap["judge_error"] == 1
    assert snap["contradicted"] == 0


# ---------- Off mode does NOT tick counters ----------

def test_off_mode_does_not_tick_calls(monkeypatch) -> None:
    """Off mode pays zero cost (cost discipline) — counters stay zero
    even with a singleton present. Per Codex iter-1 brief verdict:
    "off-mode does not need telemetry for this issue."
    """
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    _install(monkeypatch, _FakeJudge("NEUTRAL"))
    verify_sentence(_SENTENCE, _pool(_FULL_TEXT))
    snap = get_judge_telemetry()
    assert snap["calls"] == 0
    assert snap["neutral"] == 0


# ---------- Snapshot vs live reference ----------

def test_get_judge_telemetry_returns_snapshot_not_live(monkeypatch) -> None:
    """Mutating the return value of get_judge_telemetry() MUST NOT
    mutate the underlying counters — operators reading the snapshot
    should not be able to corrupt the source.
    """
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    _install(monkeypatch, _FakeJudge("ENTAILED"))
    verify_sentence(_SENTENCE, _pool(_FULL_TEXT))
    snap = get_judge_telemetry()
    snap["calls"] = 999
    snap["entailed"] = 999
    fresh = get_judge_telemetry()
    assert fresh["calls"] == 1
    assert fresh["entailed"] == 1


# ---------- reset_judge_telemetry ----------

def test_reset_judge_telemetry_zeroes_all(monkeypatch) -> None:
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    _install(monkeypatch, _FakeJudge("ENTAILED"))
    verify_sentence(_SENTENCE, _pool(_FULL_TEXT))
    assert get_judge_telemetry()["calls"] == 1
    reset_judge_telemetry()
    snap = get_judge_telemetry()
    assert all(v == 0 for v in snap.values())


def test_reset_judge_telemetry_is_public_callable() -> None:
    """Sanity: reset_judge_telemetry is exported as a public name from
    the module, not behind an underscore. Operators can deliberately
    call this between job windows.
    """
    assert hasattr(strict_verify, "reset_judge_telemetry")
    assert not strict_verify.reset_judge_telemetry.__name__.startswith("_")
