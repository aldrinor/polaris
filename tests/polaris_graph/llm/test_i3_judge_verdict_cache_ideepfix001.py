"""I-deepfix-001 fix I3 — behavioral tests for the judge verdict idempotency cache.

These prove the EFFECT (fail-loud RED->GREEN): an identical (model, sentence, span) triple is judged
ONCE and every later identical call is served from the cache WITHOUT re-invoking the (paid, 429-prone)
judge call, while distinct inputs each invoke it, the fail-closed sentinel is never cached, and disabling
the cache restores the byte-identical pre-I3 pass-through. Faithfulness-neutral: the cache only ever
returns a verdict the judge itself produced.

Pure / offline / $0 — the real judge network leg (`_judge_uncached`) is replaced with a deterministic
counter, and the judge object is built WITHOUT __init__ (no OPENROUTER_API_KEY, no httpx client, no
network) so the cache seam is exercised directly on the real `_EntailmentJudge.judge` wrapper.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.llm import judge_verdict_cache as vc
from src.polaris_graph.llm.entailment_judge import _EntailmentJudge


def _make_judge_with_counter(model="z-ai/glm-5.2", verdicts=None):
    """Build a real _EntailmentJudge WITHOUT __init__ (no env / httpx / network) and replace its
    uncached judge leg with a call counter. `verdicts` is an optional list of (verdict, reason) tuples
    served in order; the default is a fixed ENTAILED/ok. Returns (judge, counter_dict)."""
    judge = _EntailmentJudge.__new__(_EntailmentJudge)
    judge._model = model
    counter = {"calls": 0, "seen": []}
    seq = list(verdicts or [])

    def _fake_uncached(sentence, span):
        counter["calls"] += 1
        counter["seen"].append((sentence, span))
        if seq:
            return seq[min(counter["calls"] - 1, len(seq) - 1)]
        return ("ENTAILED", "ok")

    # instance-attribute function shadows the bound method; judge() calls self._judge_uncached(s, span).
    judge._judge_uncached = _fake_uncached
    return judge, counter


@pytest.fixture(autouse=True)
def _clean_cache(monkeypatch):
    monkeypatch.setenv("PG_JUDGE_VERDICT_CACHE", "1")
    vc.reset_cache()
    yield
    vc.reset_cache()


def test_i3_repeat_identical_call_is_served_from_cache_no_second_judge_call():
    """RED without I3: the judge leg fires twice for the same (claim, span). GREEN: fires ONCE."""
    judge, counter = _make_judge_with_counter(verdicts=[("NEUTRAL", "adds specificity")])
    s = "Semaglutide reduced HbA1c by 1.8%."
    span = "GLP-1 receptor agonists reduced HbA1c."

    first = judge.judge(s, span)
    second = judge.judge(s, span)

    assert first == ("NEUTRAL", "adds specificity")
    # faithfulness-neutral: the cached tuple is byte-identical to the judged tuple.
    assert second == first
    # THE EFFECT: the second identical call did NOT re-invoke the judge network leg.
    assert counter["calls"] == 1, f"expected 1 judge call, got {counter['calls']}"
    st = vc.stats()
    assert st["hits"] == 1 and st["stores"] == 1 and st["misses"] == 1


def test_i3_distinct_inputs_each_invoke_the_judge():
    """A different (sentence, span) is a cache miss and must re-invoke the judge (no false merge)."""
    judge, counter = _make_judge_with_counter()
    judge.judge("Claim A.", "Span A.")
    judge.judge("Claim B.", "Span B.")
    assert counter["calls"] == 2
    assert vc.stats()["misses"] == 2


def test_i3_same_span_different_claim_not_merged():
    """The key includes the CLAIM, so the same span with a different claim is a distinct decision."""
    judge, counter = _make_judge_with_counter()
    span = "GLP-1 receptor agonists reduced HbA1c."
    judge.judge("Semaglutide reduced HbA1c.", span)
    judge.judge("Tirzepatide reduced weight.", span)
    assert counter["calls"] == 2


def test_i3_fail_closed_sentinel_is_never_cached_stays_retryable():
    """A transient judge fault returns the fail-closed ('ENTAILED','judge_error:…') sentinel. It must
    NOT be cached, so a later identical call re-issues a fresh attempt at a real verdict."""
    judge, counter = _make_judge_with_counter(
        verdicts=[("ENTAILED", "judge_error: rate_limit_200"), ("CONTRADICTED", "span disagrees")]
    )
    s, span = "Drug X lowers blood pressure.", "Drug X raises blood pressure."

    first = judge.judge(s, span)   # sentinel — not cached
    second = judge.judge(s, span)  # must re-invoke and now get the real verdict

    assert first == ("ENTAILED", "judge_error: rate_limit_200")
    assert second == ("CONTRADICTED", "span disagrees")
    assert counter["calls"] == 2, "sentinel must stay retryable (never served from cache)"
    st = vc.stats()
    assert st["skipped_sentinel"] == 1
    # the real CONTRADICTED verdict IS cached: a third identical call is now a hit.
    third = judge.judge(s, span)
    assert third == ("CONTRADICTED", "span disagrees")
    assert counter["calls"] == 2


def test_i3_cache_disabled_env_is_byte_identical_passthrough(monkeypatch):
    """PG_JUDGE_VERDICT_CACHE=0 => no caching => the judge fires on every call (pre-I3 behavior)."""
    monkeypatch.setenv("PG_JUDGE_VERDICT_CACHE", "0")
    vc.reset_cache()
    judge, counter = _make_judge_with_counter()
    s, span = "Claim.", "Span."
    judge.judge(s, span)
    judge.judge(s, span)
    assert counter["calls"] == 2, "disabled cache must not memoize"
    assert vc.stats()["hits"] == 0


def test_i3_whitespace_normalized_key_merges_the_same_claim():
    """Two inputs that are the SAME claim/span modulo whitespace hit the same cache entry (safe merge —
    never merges two DIFFERENT claims)."""
    judge, counter = _make_judge_with_counter()
    judge.judge("Semaglutide  reduced   HbA1c.", "GLP-1 reduced HbA1c.")
    judge.judge("Semaglutide reduced HbA1c.", "GLP-1  reduced  HbA1c.")
    assert counter["calls"] == 1
    assert vc.stats()["hits"] == 1


def test_i3_model_is_part_of_the_key():
    """The judge MODEL is part of the key: the same (claim, span) under a different model is a distinct
    decision (a model swap must not serve another model's verdict)."""
    j1, c1 = _make_judge_with_counter(model="z-ai/glm-5.2")
    j2, c2 = _make_judge_with_counter(model="moonshotai/kimi-k2.6")
    s, span = "Claim.", "Span."
    j1.judge(s, span)
    j2.judge(s, span)
    assert c1["calls"] == 1 and c2["calls"] == 1


def test_i3_prompt_variant_is_part_of_the_key_no_cross_variant_merge(monkeypatch):
    """I3 P1 (Fable gate iter1): the verdict depends on the RESOLVED entailment prompt, which is a
    call-time variable (PG_ENTAILMENT_PROMPT_VARIANT). The SAME (model, sentence, span) under two DIFFERENT
    variants must be two DISTINCT cache decisions — otherwise a same-process prompt bakeoff would score
    every variant identically by serving variant-1's cached verdict. RED without the variant key (1 call,
    both variants merged); GREEN with it (2 calls, one per variant)."""
    judge, counter = _make_judge_with_counter(
        verdicts=[("NEUTRAL", "variant baseline"), ("CONTRADICTED", "variant widen_c")]
    )
    s, span = "Semaglutide reduced HbA1c.", "GLP-1 reduced HbA1c."

    monkeypatch.setenv("PG_ENTAILMENT_PROMPT_VARIANT", "baseline")
    first = judge.judge(s, span)

    monkeypatch.setenv("PG_ENTAILMENT_PROMPT_VARIANT", "widen_c")
    second = judge.judge(s, span)

    # THE EFFECT: the second call under a DIFFERENT variant is a cache MISS -> the judge re-fires.
    assert counter["calls"] == 2, f"variant switch must not be served from cache, got {counter['calls']}"
    assert first == ("NEUTRAL", "variant baseline")
    assert second == ("CONTRADICTED", "variant widen_c")

    # and re-issuing the SAME variant IS a hit (the variant scopes the entry, it does not disable caching).
    before = counter["calls"]
    monkeypatch.setenv("PG_ENTAILMENT_PROMPT_VARIANT", "baseline")
    third = judge.judge(s, span)
    assert third == ("NEUTRAL", "variant baseline")
    assert counter["calls"] == before, "same variant + same input must be served from cache"


def test_i3_fifo_eviction_bounds_the_cache(monkeypatch):
    """The cache is bounded by PG_JUDGE_VERDICT_CACHE_MAX with FIFO eviction (no unbounded growth)."""
    monkeypatch.setenv("PG_JUDGE_VERDICT_CACHE_MAX", "3")
    vc.reset_cache()
    judge, counter = _make_judge_with_counter()
    for i in range(5):
        judge.judge(f"Claim {i}.", f"Span {i}.")
    st = vc.stats()
    assert st["size"] == 3, f"cache must not exceed cap, size={st['size']}"
    assert st["evictions"] == 2
    # the oldest (Claim 0) was evicted -> re-judging it is a fresh call, not a hit.
    before = counter["calls"]
    judge.judge("Claim 0.", "Span 0.")
    assert counter["calls"] == before + 1
