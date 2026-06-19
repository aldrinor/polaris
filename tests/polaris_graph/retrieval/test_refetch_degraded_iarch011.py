"""BUG-B02 / BUG-B04 (I-arch-011) — behavioral test: degraded-row Zyte re-fetch.

THE BUG this proves the fix for: on the cert run, 96/528 sources fetched as
DEGRADED stubs/shells (e.g. the NEJM 489-char and FDA P960009 266-char anti-bot
shells) and were FLAGGED but NEVER re-fetched, so the disease-staging slot was
ungroundable. The free fetch cascade returns the shell with ``success`` already
decided, so a plain re-run re-derives the identical shell — the fix must ESCALATE
to a FORCED Zyte browser re-fetch of the degraded URL.

This is a BEHAVIORAL end-to-end test (not a flag-set check). It drives the REAL
``run_live_retrieval`` loop (seed_only path) with:
  - ``_fetch_content`` monkeypatched to return a thin paywall/anti-bot STUB
    (ok=False, short body) — exactly the degraded row class.
  - ``AccessBypass._try_zyte`` monkeypatched at the ZYTE CLIENT SEAM (one level
    BELOW the lane's own wrapper, per the reviewer's "go deeper" guidance) so we
    assert the forced Zyte path is ACTUALLY CALLED for the degraded row.
  - ``ZYTE_API_KEY`` present (the re-fetch is a silent no-op without it).

Pre-fix the loop never calls ``_try_zyte`` for a degraded row, so the row stays
degraded and is excluded from the grounded count — the success assertion FAILS.

Faithfulness invariants asserted:
  * SUCCESS: a usable (non-content-starved) Zyte body REPOPULATES ``direct_quote``,
    the degraded flags are CLEARED, and the row counts as grounded.
  * FAILURE: an unrecovered stub STAYS LABELED degraded and is EXCLUDED from the
    real adequacy gate's ``count_grounded_rows`` — never passed off as full text.
"""
from __future__ import annotations

import os

import pytest

from src.polaris_graph.nodes.corpus_adequacy_gate import count_grounded_rows
from src.polaris_graph.retrieval import live_retriever
from src.tools.access_bypass import AccessBypass, AccessResult


# The B04 FDA P960009 degraded-row class: a 266-char device-PMA stub of THIN REAL
# clinical prose. It CLEARS the 200-char starvation floor and carries NO landing/
# abstract marker phrase, so ``is_content_starved`` and ``_is_landing_or_abstract_
# page`` BOTH return False — the ONLY signal that it is degraded is the fetch
# layer's own paywall-stub verdict (``ok=False``). This is the exact shape the
# starvation/landing trigger MISSES; the test must exercise it (not the easy
# access-denial shortcut) per the §-1.4 "fires on the real rows" rule.
_DEGRADED_STUB = (
    "Summary of Safety and Effectiveness Data. The device is indicated for the "
    "staging of disease in adult patients. Clinical studies demonstrated safety "
    "and effectiveness for the intended use in the target population across the "
    "enrolled study cohort and follow-up period."
)

# A real full-text body recovered by the forced Zyte browser path — long, prose,
# NOT content-starved. Distinct marker so we can prove the row's grounding span
# was repopulated with the Zyte body (not the stub).
_ZYTE_FULL_TEXT = (
    "Disease staging in this Phase 3 trial followed the AJCC eighth-edition "
    "criteria. " + ("The recurrence-free survival analysis enrolled patients "
    "across thirty-two sites and reported a hazard ratio of 0.61 with a "
    "ninety-five percent confidence interval of 0.48 to 0.77. " * 12)
)

_SEED_URL = "https://www.nejm.org/doi/full/10.1056/NEJMoa-test-b04"


def _stub_fetch_content(url, max_chars, *args, **kwargs):
    """Return the degraded anti-bot stub for every URL (ok=False, short body).

    Mirrors ``_fetch_content``'s 5-tuple: (content, ok, title, body_type, jsonld).
    ok=False reflects the paywall-stub verdict; the short body still flows into the
    ``if content:`` degraded path in the per-URL loop.
    """
    return (_DEGRADED_STUB, False, "Degraded NEJM stub", "paywall_shell", "")


def _run_seed_only(monkeypatch, *, zyte_succeeds: bool):
    """Drive the real run_live_retrieval seed_only loop on one degraded URL.

    Patches the Zyte CLIENT seam (``AccessBypass._try_zyte``) so we can assert the
    forced Zyte path is invoked and control success/failure. Returns
    (evidence_rows, zyte_calls).
    """
    # Force the serial fetch path so the monkeypatched _fetch_content is the seam.
    monkeypatch.setenv("PG_USE_PARALLEL_FETCH", "0")
    # Enable the default-OFF degraded re-fetch + present a Zyte key (otherwise the
    # re-fetch is a deliberate, fail-loud no-op).
    monkeypatch.setenv("PG_REFETCH_DEGRADED_VIA_ZYTE", "1")
    monkeypatch.setenv("ZYTE_API_KEY", "test-zyte-key-not-real")
    # Redesign ON so an UNRECOVERED degraded row is appended WITH its flags (rather
    # than legacy hard-dropped) — required to inspect the failure-case flag state.
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "1")
    # Keep the loop offline + cheap.
    monkeypatch.setenv("PG_ENABLE_LIVE_OA_RESOLVER", "0")

    monkeypatch.setattr(live_retriever, "_fetch_content", _stub_fetch_content)
    # No OpenAlex network in the test.
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
        research_question="disease staging recurrence-free survival",
        seed_urls=[_SEED_URL],
        seed_only=True,
        enable_openalex_enrich=False,
        enable_prefetch_filter=False,
        anchor_seed=False,
    )
    return result.evidence_rows, zyte_calls


def test_fda_style_stub_is_only_degraded_via_fetch_verdict():
    """Guard: the FDA-style stub is degraded ONLY via the fetch ``ok=False``
    verdict — NOT starvation, NOT landing. This is the trigger path a
    starvation/landing-only check would MISS (§-1.4), so the recovery tests below
    genuinely exercise it rather than the easy access-denial shortcut."""
    assert not live_retriever.is_content_starved(_DEGRADED_STUB)
    assert not live_retriever._is_landing_or_abstract_page(_DEGRADED_STUB)


def test_degraded_row_triggers_forced_zyte_refetch_and_recovers(monkeypatch):
    """SUCCESS path: a degraded stub forces a Zyte re-fetch that recovers it.

    FAILS on pre-fix code: pre-fix the loop never calls _try_zyte for a degraded
    row, so the row stays degraded and is NOT counted as grounded.
    """
    rows, zyte_calls = _run_seed_only(monkeypatch, zyte_succeeds=True)

    # The forced Zyte path was actually invoked for the degraded URL. This is the
    # assertion that FAILS pre-fix (no re-fetch is wired).
    assert zyte_calls == [_SEED_URL], (
        "expected exactly one forced Zyte re-fetch of the degraded seed URL; "
        f"got {zyte_calls!r} (pre-fix: the path is never reached)"
    )

    assert len(rows) == 1, f"expected one evidence row, got {len(rows)}"
    row = rows[0]

    # The grounding span was REPOPULATED with the recovered Zyte full text (the
    # marker phrase), not the stub.
    assert "Disease staging" in row["direct_quote"], (
        "direct_quote was not repopulated with the recovered Zyte body"
    )
    assert _DEGRADED_STUB not in row["direct_quote"], (
        "direct_quote still carries the degraded stub text"
    )

    # The degraded flags are CLEARED — the row is a recovered full-text row.
    for flag in ("content_starved", "landing_page", "down_weighted", "fetch_degraded"):
        assert not row.get(flag), f"recovered row must not carry {flag!r}=True"

    # And it counts as a real grounded source in the actual adequacy gate.
    assert count_grounded_rows(rows) == 1, (
        "recovered row must count toward the grounded source total"
    )


def test_unrecovered_degraded_row_stays_labeled_and_excluded(monkeypatch):
    """FAILURE path: when Zyte cannot recover the stub the row stays degraded.

    Faithfulness invariant: an unrecovered stub is NEVER passed off as full text —
    it stays flagged and is EXCLUDED from the grounded count.
    """
    rows, zyte_calls = _run_seed_only(monkeypatch, zyte_succeeds=False)

    # The forced Zyte re-fetch was still ATTEMPTED on the degraded row.
    assert zyte_calls == [_SEED_URL], (
        f"expected one forced Zyte re-fetch attempt; got {zyte_calls!r}"
    )

    assert len(rows) == 1, f"expected one (flagged) evidence row, got {len(rows)}"
    row = rows[0]

    # The row STAYS labeled degraded (content-starved stub, down-weighted).
    assert row.get("content_starved") is True, (
        "unrecovered stub must stay labeled content_starved"
    )
    assert row.get("down_weighted") is True, (
        "unrecovered stub must stay down-weighted (kept at low weight, not full text)"
    )

    # And it is EXCLUDED from the real adequacy gate's grounded count — never
    # laundered as a grounded full-text source.
    assert count_grounded_rows(rows) == 0, (
        "an unrecovered degraded stub must NOT count as a grounded source"
    )


def test_refetch_is_noop_without_zyte_key(monkeypatch):
    """Without ZYTE_API_KEY the re-fetch is a deliberate, fail-loud no-op.

    The Zyte client seam must NOT be reached (the wrapper short-circuits and warns)
    and the row stays degraded — byte-faithful to the silent-no-op fail-loud rule.
    """
    monkeypatch.delenv("ZYTE_API_KEY", raising=False)
    monkeypatch.setenv("PG_REFETCH_DEGRADED_VIA_ZYTE", "1")

    zyte_calls: list[str] = []

    async def _fake_try_zyte(self, url):  # pragma: no cover — must NOT be called
        zyte_calls.append(url)
        return AccessResult(
            url=url, content="", access_method="zyte",
            legal_alternative=None, success=False, metadata={},
        )

    monkeypatch.setattr(AccessBypass, "_try_zyte", _fake_try_zyte, raising=True)

    recovered = live_retriever._try_refetch_degraded_row(_SEED_URL)

    assert recovered == "", "no recovery is possible without a Zyte key"
    assert zyte_calls == [], (
        "the Zyte client seam must not be reached without a key (fail-loud no-op)"
    )
