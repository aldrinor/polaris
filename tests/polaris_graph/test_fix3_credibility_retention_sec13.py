"""FIX-3 piece 3 (I-deepfix-001, §-1.3) — STOP the silent hard-drop of a
`not ok` + EMPTY-content candidate (HEADLINE test).

THE BUG this proves the fix for: a candidate that fetched `ok=False` with EMPTY
content (the doi.org-timeout -> naive-paywall -> empty-body case) never reaches
the `if content:` block in `run_live_retrieval`'s per-URL loop, so the ONLY
`evidence_rows.append` site is skipped and the source is SILENTLY HARD-DROPPED.
A high-credibility failed academic DOI vanishes while a low-tier source that
fetched fine is kept — credibility inversion. The existing F30 down-weight path
ALSO lives inside `if content:`, so it does NOT cover the empty-content case.

THE FIX: under the EXISTING `PG_SWEEP_CREDIBILITY_REDESIGN` flag, append a
DISCLOSED zero-weight evidence row (`retrieval_weight=0.0`, `down_weighted=True`,
`fetch_failed=True`, `full_text_capable=False`, `direct_quote=""`) so the source
is RETAINED in the pool at zero weight, NOT dropped (§-1.3 WEIGHT-not-FILTER /
disclose-don't-drop).

This is a BEHAVIORAL end-to-end test: it drives the REAL `run_live_retrieval`
seed_only loop with `_fetch_content` monkeypatched to return the empty+not-ok
tuple. Mirrors the test_refetch_degraded_iarch011 harness.

FAITHFULNESS invariants asserted:
  * The retained row carries `direct_quote == ""` (and sets NO `statement`), so it
    can NEVER ground a claim — the provenance generator's grounding fallback
    (`direct_quote or statement or ""`) yields "" -> the row is unusable for
    grounding (proven structurally below).
  * `retrieval_weight == 0.0` so it sorts LAST in the selector.
  * OFF path (flag unset) -> NO row appended -> byte-identical legacy hard-drop.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.retrieval import live_retriever


# An empty-content `not ok` candidate — the doi.org-timeout -> naive-paywall ->
# empty-body class that the piece-3 fix retains. Distinct from the B04 stub
# (which has NON-empty content and rides the `if content:` degraded path).
_SEED_URL = "https://doi.org/10.1056/NEJMoa-test-fix3-empty"


def _empty_notok_fetch(url, max_chars, *args, **kwargs):
    """Return the (content, ok, title, body_type, jsonld) 5-tuple of `_fetch_content`
    for an EMPTY-content fetch failure: content="" and ok=False. This is the path
    that never reaches `if content:` and was silently hard-dropped pre-fix."""
    return ("", False, "", "", "")


def _run_seed_only(monkeypatch, *, redesign_on: bool):
    """Drive the real run_live_retrieval seed_only loop on one empty+not-ok URL."""
    # Serial fetch path so the monkeypatched _fetch_content is the seam.
    monkeypatch.setenv("PG_USE_PARALLEL_FETCH", "0")
    # Keep the loop offline + cheap.
    monkeypatch.setenv("PG_ENABLE_LIVE_OA_RESOLVER", "0")
    # The degraded Zyte re-fetch fires only INSIDE `if content:` (non-empty body);
    # disable it so it cannot interfere with the empty-content path under test.
    monkeypatch.delenv("PG_REFETCH_DEGRADED_VIA_ZYTE", raising=False)
    if redesign_on:
        monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "1")
    else:
        monkeypatch.delenv("PG_SWEEP_CREDIBILITY_REDESIGN", raising=False)

    monkeypatch.setattr(live_retriever, "_fetch_content", _empty_notok_fetch)
    monkeypatch.setattr(
        live_retriever, "_bounded_openalex_enrich", lambda *a, **k: {}
    )

    result = live_retriever.run_live_retrieval(
        research_question="disease staging recurrence-free survival",
        seed_urls=[_SEED_URL],
        seed_only=True,
        enable_openalex_enrich=False,
        enable_prefetch_filter=False,
        anchor_seed=False,
    )
    return result


def test_redesign_on_retains_failed_empty_fetch_at_zero_weight(monkeypatch):
    """HEADLINE: redesign ON -> a `not ok` + empty-content candidate is RETAINED as
    a disclosed zero-weight row (NOT silently hard-dropped)."""
    result = _run_seed_only(monkeypatch, redesign_on=True)
    rows = result.evidence_rows

    assert len(rows) == 1, (
        f"expected one RETAINED zero-weight row, got {len(rows)} "
        "(pre-fix: the empty+not-ok candidate is silently hard-dropped -> 0 rows)"
    )
    row = rows[0]

    # Disclosed zero-weight retention — the §-1.3 contract.
    assert row.get("retrieval_weight") == 0.0, "retained row must carry weight 0.0"
    assert row.get("down_weighted") is True
    assert row.get("fetch_failed") is True
    assert row.get("full_text_capable") is False

    # FAITHFULNESS: empty grounding span + NO statement => can never ground a claim.
    assert row.get("direct_quote") == "", "retained row must carry an EMPTY direct_quote"
    assert "statement" not in row, (
        "retained row must NOT set `statement` — else the provenance grounding "
        "fallback (direct_quote or statement) would launder the title as a span"
    )
    # The source URL + tier are disclosed (so a human/auditor sees the retained item).
    assert row.get("source_url") == _SEED_URL
    assert "tier" in row


def test_redesign_off_is_byte_identical_hard_drop(monkeypatch):
    """OFF path (flag unset): the empty+not-ok candidate is NOT retained — legacy
    byte-identical hard-drop, NO row appended."""
    result = _run_seed_only(monkeypatch, redesign_on=False)
    assert len(result.evidence_rows) == 0, (
        "OFF path must be byte-identical legacy hard-drop (no retained row)"
    )
    # The failure is still counted in the funnel telemetry (honest), independent of
    # whether the row is retained.
    assert result.candidates_failed_fetch >= 1


def test_retained_zero_weight_row_cannot_ground_a_claim(monkeypatch):
    """Structural faithfulness proof: the retained row's grounding surface, read the
    SAME way the provenance generator reads it (`direct_quote or statement or ""`),
    is EMPTY — so the row can never supply a grounding span."""
    result = _run_seed_only(monkeypatch, redesign_on=True)
    row = result.evidence_rows[0]
    # This is the exact expression provenance_generator.py uses to pull a grounding
    # span (provenance_generator.py:1480). It must resolve to "" for this row.
    grounding_surface = row.get("direct_quote") or row.get("statement") or ""
    assert grounding_surface == "", (
        "the retained zero-weight row must expose NO grounding surface — it is "
        "disclosed corpus metadata only, never a citable span"
    )
