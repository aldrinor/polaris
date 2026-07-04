"""W4 (I-deepfix-001) — FAIL-LOUD behavioral test that the per-DOMAIN authority
cache tiers ONE representative per (domain + genre signature) via GLM and
PROPAGATES that domain-level authority WEIGHT to every row sharing the signature,
so a large corpus with repeated domains pays the LLM at most once per domain-genre.

The failure this closes: on a large corpus each row tiered its OWN GLM call, which
blows the bounded-parallel wall + the consecutive-fallback breaker, so most rows
degrade to the rules-floor deny-list precisely on the biggest corpora. The test
drives ``classify_sources_llm_tiering`` with a COUNTING fake ``call_llm`` (offline,
$0) and asserts:
  * ON: the LLM is called ONCE per unique domain-genre signature (not once per row).
  * ON: every row still gets a tier (no source dropped, §-1.3) and rows sharing a
    signature share the tier (domain-level authority WEIGHT propagated).
  * OFF: byte-identical — the LLM is called once per ROW (legacy fan-out).

Faithfulness is untouched: tiering is a per-source WEIGHT; the cache only dedups
the GLM call by domain-genre, it never drops or gates a source.
"""
from __future__ import annotations

import json

import pytest

from src.polaris_graph.retrieval.credibility_llm_tiering import (
    classify_sources_llm_tiering,
)
from src.polaris_graph.retrieval.tier_classifier import ClassificationSignals

_FLAG = "PG_TIER_DOMAIN_AUTHORITY_CACHE"


class _CountingCaller:
    """A deterministic offline fake GLM caller: returns a fixed tier keyed by the
    domain embedded in the prompt, and counts how many times it is invoked."""

    def __init__(self, tier_by_host: dict[str, str]):
        self.tier_by_host = tier_by_host
        self.calls = 0

    def __call__(self, prompt: str) -> str:
        self.calls += 1
        # The prompt embeds "url: <url>"; pick the tier by matching a known host.
        tier = "T4"
        for host, t in self.tier_by_host.items():
            if host in prompt:
                tier = t
                break
        return json.dumps({"tier": tier, "reason": "test"})


def _signals(url: str, pub_type: str = "article", src_type: str = "journal"):
    return ClassificationSignals(
        url=url,
        openalex_publication_type=pub_type,
        openalex_source_type=src_type,
        title="Example source",
    )


def _corpus_repeated_domains():
    """9 rows across 3 domains x 1 genre each => 3 unique domain-genre signatures."""
    rows = []
    for _ in range(4):
        rows.append(_signals("https://nature.com/articles/x"))
    for _ in range(3):
        rows.append(_signals("https://who.int/report/y", "report", "report"))
    for _ in range(2):
        rows.append(_signals("https://reddit.com/r/z", "", ""))
    return rows


def test_off_calls_llm_once_per_row(monkeypatch):
    """Default-OFF: legacy fan-out — the LLM is called once per ROW."""
    monkeypatch.delenv(_FLAG, raising=False)
    monkeypatch.setenv("PG_TIER_LLM_PARALLEL", "0")  # serial => deterministic count
    caller = _CountingCaller({"nature.com": "T1", "who.int": "T3", "reddit.com": "T7"})
    signals = _corpus_repeated_domains()
    result = classify_sources_llm_tiering(signals, call_llm=caller)
    assert len(result) == len(signals), "no source may be dropped"
    assert caller.calls == len(signals), (
        f"OFF must be per-row: expected {len(signals)} calls, got {caller.calls}"
    )


def test_on_calls_llm_once_per_domain_signature(monkeypatch):
    """FLAG ON: the LLM is called ONCE per unique (domain + genre) signature, not
    once per row — the real cache effect."""
    monkeypatch.setenv(_FLAG, "1")
    monkeypatch.setenv("PG_TIER_LLM_PARALLEL", "0")
    caller = _CountingCaller({"nature.com": "T1", "who.int": "T3", "reddit.com": "T7"})
    signals = _corpus_repeated_domains()
    result = classify_sources_llm_tiering(signals, call_llm=caller)

    assert len(result) == len(signals), "no source may be dropped (§-1.3)"
    # 3 unique domain-genre signatures => at most 3 GLM calls, far fewer than 9 rows.
    assert caller.calls == 3, (
        f"ON must pay GLM once per domain-genre: expected 3 calls, got {caller.calls}"
    )
    assert caller.calls < len(signals), "cache must reduce the number of GLM calls"

    # Rows sharing a domain-genre share the tier (domain-level WEIGHT propagated).
    tiers = [r.tier.value for r in result]
    assert tiers[0] == tiers[1] == tiers[2] == tiers[3], "nature.com rows must agree"
    assert tiers[4] == tiers[5] == tiers[6], "who.int rows must agree"
    assert tiers[7] == tiers[8], "reddit.com rows must agree"

    # The propagated (non-representative) rows carry the audit-trail reason so the
    # WEIGHT is never a silent copy.
    assert any(
        "domain_authority_cache_propagated" in reason
        for r in result for reason in r.reasons
    ), "propagated rows must disclose the domain-authority-cache basis"

    # The honest cache disclosure rides on the batch status.
    status = getattr(result, "tiering_status", {})
    assert status.get("domain_authority_cache") is True
    assert status.get("unique_domain_signatures") == 3
    assert status.get("total_rows") == len(signals)


def test_on_no_domain_rows_escalate_individually(monkeypatch):
    """Rows with NO resolvable domain are never pooled under a blank key — each
    escalates on its own (a blank host must not launder N sources into one tier)."""
    monkeypatch.setenv(_FLAG, "1")
    monkeypatch.setenv("PG_TIER_LLM_PARALLEL", "0")
    caller = _CountingCaller({})
    signals = [_signals(""), _signals(""), _signals("https://nature.com/a")]
    result = classify_sources_llm_tiering(signals, call_llm=caller)
    assert len(result) == 3
    # 2 no-domain rows (unique each) + 1 nature.com = 3 signatures => 3 calls.
    assert caller.calls == 3, (
        f"no-domain rows must escalate individually: expected 3, got {caller.calls}"
    )


def test_on_retracted_row_never_inherits_clean_domain_tier(monkeypatch):
    """FAIL-LOUD (Fable P1): a RETRACTED row sharing a domain-genre signature with a
    CLEAN representative must NEVER inherit the representative's positive tier via
    the per-domain authority cache.

    The cache pooled rows by (domain + genre) only, so a retracted nature.com row
    behind a clean nature.com representative would silently receive the clean T-tier
    — laundering a retracted source into a journal's authority and bypassing the
    rules-floor Rule 0 (``R0_retracted`` -> UNKNOWN) whose whole job is to keep a
    retracted source out of any positive tier. The fix escalates any per-row
    exclusion signal individually. This asserts the retracted rows land at UNKNOWN
    with the ``R0_retracted`` floor and do NOT carry the propagated-cache reason,
    while the clean rows still pool and agree.
    """
    monkeypatch.setenv(_FLAG, "1")
    monkeypatch.setenv("PG_TIER_LLM_PARALLEL", "0")
    caller = _CountingCaller({"nature.com": "T1"})

    clean_a = _signals("https://nature.com/articles/clean-a")
    clean_b = _signals("https://nature.com/articles/clean-b")
    clean_c = _signals("https://nature.com/articles/clean-c")
    # Retracted via the OpenAlex flag.
    retr_flag = _signals("https://nature.com/articles/retr-flag")
    retr_flag.openalex_is_retracted = True
    # Retracted via an explicit leading title marker (OpenAlex flag unset).
    retr_title = _signals("https://nature.com/articles/retr-title")
    retr_title.title = "Retracted: A study of glucose control"
    signals = [clean_a, retr_flag, clean_b, retr_title, clean_c]

    result = classify_sources_llm_tiering(signals, call_llm=caller)
    assert len(result) == len(signals), "no source may be dropped (§-1.3)"

    retr_flag_res = result[1]
    retr_title_res = result[3]
    for res, label in ((retr_flag_res, "flag"), (retr_title_res, "title")):
        assert "R0_retracted" in res.matched_rules, (
            f"retracted-{label} row must keep its Rule-0 floor, not inherit a clean "
            f"tier; matched_rules={res.matched_rules}"
        )
        assert not any(
            "domain_authority_cache_propagated" in r for r in res.reasons
        ), (
            f"retracted-{label} row must NOT be a propagated cache member: "
            f"reasons={res.reasons}"
        )

    # The three clean nature.com rows still pool and agree (WEIGHT propagated among
    # the genuinely-clean rows — the fix isolates ONLY the excluded rows).
    clean_tiers = {result[0].tier, result[2].tier, result[4].tier}
    assert len(clean_tiers) == 1, (
        f"clean same-domain rows must still share the domain tier: {clean_tiers}"
    )
    # And the retracted rows are strictly NOT the clean positive tier.
    assert retr_flag_res.tier not in clean_tiers, (
        "retracted row must not equal the clean domain tier"
    )
    assert retr_title_res.tier not in clean_tiers


def test_on_stub_row_never_inherits_clean_domain_tier(monkeypatch):
    """FAIL-LOUD (Fable P1): a T7-STUB row (short fetched body) sharing a domain-genre
    with a clean representative must escalate individually, not inherit the clean
    tier. A stub is a per-row degradation the rules-floor keys on individually
    (Rule 1 -> T7 stub / fetch_degraded); pooling it would launder a stub into the
    domain's full-text authority.
    """
    monkeypatch.setenv(_FLAG, "1")
    monkeypatch.setenv("PG_TIER_LLM_PARALLEL", "0")
    caller = _CountingCaller({"nature.com": "T1"})

    clean_a = _signals("https://nature.com/articles/full-a")
    clean_a.fetched_content_length = 20000
    clean_b = _signals("https://nature.com/articles/full-b")
    clean_b.fetched_content_length = 20000
    stub = _signals("https://nature.com/articles/stub")
    stub.fetched_content_length = 200  # < T7_STUB_CONTENT_CHARS
    signals = [clean_a, stub, clean_b]

    result = classify_sources_llm_tiering(signals, call_llm=caller)
    assert len(result) == len(signals)
    stub_res = result[1]
    assert not any(
        "domain_authority_cache_propagated" in r for r in stub_res.reasons
    ), f"stub row must not be a propagated cache member: reasons={stub_res.reasons}"
    # The two clean full-text rows still pool.
    assert result[0].tier == result[2].tier, "clean full-text rows must still pool"


def test_stub_row_keeps_floor_fetch_degraded_signal_not_clean_llm_tier(monkeypatch):
    """FAIL-LOUD (Codex iter-3 P1): a T7-STUB row must KEEP its deterministic
    rules-floor exclusion/degradation signal — it must NOT be handed a clean
    positive LLM tier that DROPS the ``fetch_degraded`` / T7 floor the adequacy lane
    reads to exclude the stub from grounded-content counts.

    Prior hole: the W4 ``__excluded__`` cache key stopped a stub from POOLING into a
    clean domain, but the excluded stub — as its OWN domain-cache representative (and
    on the legacy per-row + single-source paths) — still ran the LLM override in
    ``llm_tier_one``, which blocked only retractions, not stubs. So the GLM's clean
    tier overwrote the floor and the fresh ClassificationResult carried
    ``fetch_degraded=False`` — laundering a body-we-could-not-read into the domain's
    full-text authority. The fix guards ``llm_tier_one`` on ``_has_per_row_exclusion_
    signal`` so a stub keeps its floor result on ALL paths.

    Two flavors, driven with a caller that would hand out a CLEAN positive tier:
      * a KNOWN-SCHOLARLY-VENUE stub (nature.com): floor keeps the venue tier BUT
        with ``fetch_degraded=True`` — assert that flag survived (would be False if
        the LLM tier had overwritten it);
      * a NON-scholarly stub (who.int report): floor is T7 via ``R1_stub_content_
        length`` — assert the stub kept T7 and the floor rule (the GLM would have
        said T3).
    Run under BOTH the cache-ON and cache-OFF (legacy per-row) legs so the guard is
    proven on every path, not just the cache representative path.
    """
    from src.polaris_graph.retrieval.tier_classifier import TierLevel

    for cache_flag in ("1", "0"):
        monkeypatch.setenv(_FLAG, cache_flag)
        monkeypatch.setenv("PG_TIER_LLM_PARALLEL", "0")
        # The caller would hand a CLEAN positive tier to whatever it tiers; if the
        # stub reached the LLM override it would be laundered to T1 (nature) / T3 (who).
        caller = _CountingCaller({"nature.com": "T1", "who.int": "T3"})

        venue_stub = _signals("https://nature.com/articles/stub")
        venue_stub.fetched_content_length = 200  # < T7_STUB_CONTENT_CHARS
        nonvenue_stub = _signals("https://who.int/report/y", "report", "report")
        nonvenue_stub.fetched_content_length = 200
        result = classify_sources_llm_tiering(
            [venue_stub, nonvenue_stub], call_llm=caller,
        )
        assert len(result) == 2, "no source dropped (§-1.3)"

        venue_res, nonvenue_res = result[0], result[1]

        # Known-scholarly-venue stub: the degradation LABEL must survive. If the LLM
        # override had fired, the fresh result would carry fetch_degraded=False.
        assert venue_res.fetch_degraded is True, (
            f"[cache={cache_flag}] scholarly-venue stub LOST its fetch_degraded floor "
            f"signal — the LLM override laundered it (tier={venue_res.tier.value}, "
            f"rules={venue_res.matched_rules})"
        )
        assert "llm_tiering" not in venue_res.matched_rules, (
            f"[cache={cache_flag}] scholarly-venue stub must keep the deterministic "
            f"floor result, not the LLM tier: matched_rules={venue_res.matched_rules}"
        )

        # Non-scholarly stub: the T7 floor + R1 rule must survive; the GLM would have
        # said T3, so seeing T3 / llm_tiering here is the laundering the fix closes.
        assert nonvenue_res.tier == TierLevel.T7, (
            f"[cache={cache_flag}] non-scholarly stub was laundered off its T7 floor to "
            f"{nonvenue_res.tier.value} (LLM override leaked); rules={nonvenue_res.matched_rules}"
        )
        assert "R1_stub_content_length" in nonvenue_res.matched_rules, (
            f"[cache={cache_flag}] non-scholarly stub must keep its R1_stub_content_length "
            f"floor rule: matched_rules={nonvenue_res.matched_rules}"
        )
        assert "llm_tiering" not in nonvenue_res.matched_rules, (
            f"[cache={cache_flag}] non-scholarly stub must not carry the LLM tier: "
            f"matched_rules={nonvenue_res.matched_rules}"
        )


def test_metadata_only_row_still_llm_tiers_breadth_preserved(monkeypatch):
    """FAIL-LOUD guard on the OTHER side: a metadata-only row (fetched_content_length
    == 0, no body fetched yet) is NOT a stub and MUST still receive its LLM tier —
    the stub guard must not over-reach and suppress breadth on not-yet-fetched rows
    (§-1.3 WEIGHT, no drop). content_length 0 is explicitly excluded from the stub
    signal; this proves the guard keys on a genuinely-short body only."""
    monkeypatch.setenv(_FLAG, "0")  # legacy per-row leg
    monkeypatch.setenv("PG_TIER_LLM_PARALLEL", "0")
    caller = _CountingCaller({"nature.com": "T1"})
    meta_only = _signals("https://nature.com/articles/meta")
    meta_only.fetched_content_length = 0  # metadata-only, no body fetched
    result = classify_sources_llm_tiering([meta_only], call_llm=caller)
    assert result[0].matched_rules == ["llm_tiering"], (
        "a metadata-only (content_length==0) row must still get its LLM tier — the "
        f"stub guard must not suppress it: matched_rules={result[0].matched_rules}"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
