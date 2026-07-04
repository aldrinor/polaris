"""I-deepfix-001 U21 (T1 fetch-repair) — behavioral test: EMPTY-content failed-fetch
high-tier source is REPAIRED (or retained with a disclosed weight), never silently
zeroed out of citation.

THE BUG this proves the fix for (autopsy CONSOLIDATED_ISSUES.md U21): on the drb
fan-out runs, high-tier (T1) sources whose FIRST fetch returned EMPTY content
(ok=False, no body — the doi.org-timeout / anti-bot / paywall total-failure case)
never reached the in-``if content:`` BUG-B02/B04 degraded re-fetch. Their ONLY
disposition was the ``elif (not ok) and _credibility_redesign_enabled()`` branch,
which RETAINS the source but with ``direct_quote=""`` AND ``retrieval_weight=0.0``
— so it can never ground a claim and is "lost at citation time" (8 T1: AJCN,
Food & Function, Br J Dermatol).

This is a BEHAVIORAL end-to-end test (not a flag-set check). It drives the REAL
``run_live_retrieval`` seed_only loop with:
  - ``_fetch_content`` monkeypatched to return TOTAL FETCH FAILURE for the seed
    (content="", ok=False) — the EMPTY-content class the existing B02/B04 test
    (non-empty stub) does NOT cover.
  - ``AccessBypass._try_zyte`` monkeypatched at the ZYTE CLIENT SEAM so we assert
    the forced-Zyte REPAIR path is ACTUALLY invoked for the empty-fetch T1 row.
  - ``ZYTE_API_KEY`` present + ``PG_REFETCH_DEGRADED_VIA_ZYTE=1`` (the repair is a
    deliberate no-op without the flag/key).

Pre-fix the loop never calls ``_try_zyte`` for an EMPTY-content row (the repair
block does not exist), so the row is retained at zero weight with an empty quote
— the SUCCESS assertions below FAIL.

Faithfulness invariants asserted:
  * SUCCESS: a usable (non-content-starved, non-error) Zyte body makes the row a
    NORMAL citable full-text row — ``direct_quote`` is repopulated, it carries NO
    zero ``retrieval_weight`` / ``fetch_failed`` / ``fetch_degraded`` flag, and it
    counts as a grounded source.
  * FAILURE: an unrecovered empty fetch STAYS retained at the DISCLOSED zero weight
    with an empty quote (never fabricated as full text, never silently dropped).
"""
from __future__ import annotations

from src.polaris_graph.nodes.corpus_adequacy_gate import count_grounded_rows
from src.polaris_graph.retrieval import live_retriever
from src.tools.access_bypass import AccessBypass, AccessResult


# A real full-text body recovered by the forced-Zyte browser path — long prose,
# NOT content-starved, NOT an error/registry page. Distinct marker so we can prove
# the row's grounding span was populated with the Zyte body.
_ZYTE_FULL_TEXT = (
    "Vitamin D supplementation and cardiometabolic outcomes were assessed in this "
    "randomized controlled trial. " + (
        "The intervention arm enrolled participants across twenty-eight clinical "
        "centers and reported a mean between-group difference with a ninety-five "
        "percent confidence interval spanning the primary endpoint window. " * 12
    )
)

# A high-tier (T1) academic seed whose first fetch fails empty — the AJCN class
# named in the autopsy.
_SEED_URL = "https://academic.oup.com/ajcn/article/doi/10.1093/ajcn/nqx-u21-test"


def _empty_failed_fetch(url, max_chars, *args, **kwargs):
    """Return a TOTAL fetch failure: empty content, ok=False.

    Mirrors ``_fetch_content``'s 5-tuple (content, ok, title, body_type, jsonld).
    This is the U21 empty-content class that never reaches the in-``if content:``
    degraded re-fetch pre-fix.
    """
    return ("", False, "", "", "")


def _run_seed_only(monkeypatch, *, zyte_succeeds: bool):
    """Drive the real run_live_retrieval seed_only loop on one empty-fetch T1 URL.

    Returns (evidence_rows, zyte_calls).
    """
    # Serial fetch path so the monkeypatched _fetch_content is the seam.
    monkeypatch.setenv("PG_USE_PARALLEL_FETCH", "0")
    # Enable the default-OFF degraded/repair re-fetch + present a Zyte key.
    monkeypatch.setenv("PG_REFETCH_DEGRADED_VIA_ZYTE", "1")
    monkeypatch.setenv("ZYTE_API_KEY", "test-zyte-key-not-real")
    # Redesign ON so an UNRECOVERED empty fetch is RETAINED (disclosed zero-weight)
    # rather than legacy hard-dropped — required to inspect the failure-case state.
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "1")
    # Keep the loop offline + cheap.
    monkeypatch.setenv("PG_ENABLE_LIVE_OA_RESOLVER", "0")

    monkeypatch.setattr(live_retriever, "_fetch_content", _empty_failed_fetch)
    monkeypatch.setattr(
        live_retriever, "_bounded_openalex_enrich", lambda *a, **k: {}
    )

    zyte_calls: list[str] = []

    async def _fake_try_zyte(self, url):
        zyte_calls.append(url)
        if zyte_succeeds:
            return AccessResult(
                url=url, content=_ZYTE_FULL_TEXT, access_method="zyte",
                legal_alternative=None, success=True,
                metadata={"mode": "browserHtml"},
            )
        return AccessResult(
            url=url, content="", access_method="zyte",
            legal_alternative=None, success=False,
            metadata={"error": "still_blocked"},
        )

    monkeypatch.setattr(AccessBypass, "_try_zyte", _fake_try_zyte, raising=True)

    result = live_retriever.run_live_retrieval(
        research_question="vitamin D supplementation cardiometabolic outcomes",
        seed_urls=[_SEED_URL],
        seed_only=True,
        enable_openalex_enrich=False,
        enable_prefetch_filter=False,
        anchor_seed=False,
    )
    return result.evidence_rows, zyte_calls


def test_empty_fetch_t1_is_repaired_and_becomes_citable(monkeypatch):
    """SUCCESS path: an EMPTY-content failed fetch forces a Zyte repair that
    recovers the source to a citable, full-weight row.

    FAILS on pre-fix code: pre-fix the empty-content row never triggers a re-fetch
    (the repair block does not exist), so zyte is never called and the row is
    retained at zero weight with an empty quote.
    """
    rows, zyte_calls = _run_seed_only(monkeypatch, zyte_succeeds=True)

    # The forced-Zyte repair was actually invoked for the empty-fetch URL. This is
    # the assertion that FAILS pre-fix (no repair is wired for empty content).
    assert zyte_calls == [_SEED_URL], (
        "expected exactly one forced-Zyte repair of the empty-fetch T1 URL; "
        f"got {zyte_calls!r} (pre-fix: the repair path is never reached)"
    )

    assert len(rows) == 1, f"expected one evidence row, got {len(rows)}"
    row = rows[0]

    # The grounding span was POPULATED with the recovered Zyte full text.
    assert "Vitamin D supplementation" in row["direct_quote"], (
        "direct_quote was not populated with the recovered Zyte body — the source "
        "is still lost at citation time"
    )

    # The repaired row is a NORMAL citable row: NOT zero-weight, NOT flagged failed
    # / degraded.  (retrieval_weight is ABSENT on a full-weight row; if present it
    # must not be the down-weight/zero value.)
    assert row.get("retrieval_weight", 1.0) not in (0.0,), (
        "repaired row must not carry a zero retrieval_weight"
    )
    for flag in ("fetch_failed", "fetch_degraded", "down_weighted", "content_starved"):
        assert not row.get(flag), f"repaired full-text row must not carry {flag!r}=True"

    # And it counts as a real grounded source in the actual adequacy gate.
    assert count_grounded_rows(rows) == 1, (
        "repaired row must count toward the grounded source total"
    )


def test_empty_fetch_repair_miss_stays_disclosed_zero_weight(monkeypatch):
    """FAILURE path: when Zyte cannot recover the empty fetch, the source stays
    RETAINED at the disclosed zero weight with an empty quote — never fabricated as
    full text, never silently dropped (§-1.3 disclose-don't-drop).
    """
    rows, zyte_calls = _run_seed_only(monkeypatch, zyte_succeeds=False)

    # The forced-Zyte repair was still ATTEMPTED on the empty-fetch row.
    assert zyte_calls == [_SEED_URL], (
        f"expected one forced-Zyte repair attempt; got {zyte_calls!r}"
    )

    assert len(rows) == 1, f"expected one (disclosed) evidence row, got {len(rows)}"
    row = rows[0]

    # The source is RETAINED (not dropped) but as a disclosed zero-weight, empty-
    # quote row that can never ground a claim.
    assert row["source_url"] == _SEED_URL
    assert row.get("fetch_failed") is True, (
        "unrecovered empty fetch must stay labeled fetch_failed"
    )
    assert row.get("retrieval_weight") == 0.0, (
        "unrecovered empty fetch must stay at the disclosed zero weight"
    )
    assert row.get("direct_quote", "") == "", (
        "unrecovered empty fetch must carry an empty quote (never fabricated)"
    )

    # It is EXCLUDED from the real adequacy gate's grounded count — never laundered
    # as a grounded full-text source.
    assert count_grounded_rows(rows) == 0, (
        "an unrecovered empty-fetch row must NOT count as a grounded source"
    )
