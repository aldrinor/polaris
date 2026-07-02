"""U25 (I-deepfix-001): OpenAlex 0-candidate un-mask + config-driven API-key auth.

Root cause (verified live 3/3 from this machine): the 2026-02-13 OpenAlex policy
503-rate-limits anonymous ``/works?search=`` requests. ``domain_backends.openalex_search``
swallowed that 503 (fail-open -> ``[]``), and the ``live_retriever`` discovery wiring
recorded ``status='ok'`` for a 0-candidate return -- so discovery ``success_rate`` read
1.0 on a backend that returned NOTHING (a silent downgrade; LAW II). Discovery diversity
was carried only by SemanticScholar + Serper.

Two-part fix, two-part test (ALL OFFLINE -- no network, no model; a fake httpx transport
provides the OpenAlex responses, so this satisfies CLAUDE.md §8.4 + the offline-smoke gate):

  Part 1 (query):  ``openalex_search`` merges the config-driven ``api_key`` / ``mailto``
                   query params (``PG_OPENALEX_API_KEY`` / ``PG_OPENALEX_MAILTO``; empty
                   when unset -> byte-identical keyless request) and FAILS LOUD on a
                   non-200 (raises ``OpenAlexHTTPError``) instead of masking it as ``[]``.

  Part 2 (un-mask): the wiring records a genuine 200-empty as ``status='ok_zero'``
                   (``zero_yield``) and an HTTP error as ``status='fail'`` (``zero_yield``)
                   -- a 0-candidate return is NEVER ``'ok'``, so ``success_rate`` drops
                   below 1.0. A genuine 200-with-results stays ``'ok'``.

RED before the fix / GREEN after:
  * ``test_success_rate_not_masked_on_zero_candidates`` FAILS pre-fix (the wiring records
    ``'ok'`` -> ``success_rate`` 1.0) and PASSES post-fix (``'ok_zero'`` -> 0.0). This
    assertion references NO new symbol, so it is a CLEAN failure (not an import error).
  * ``test_openalex_search_raises_on_503`` FAILS pre-fix (``openalex_search`` returns
    ``[]`` with no raise) and PASSES post-fix (raises an ``OpenAlexHTTPError``, a
    ``RuntimeError`` subclass).

Nothing here touches the frozen faithfulness engine (strict_verify / NLI / 4-role /
provenance / span-grounding): the change is discovery telemetry + a discovery HTTP-auth
param. Faithfulness is unaffected -- every candidate still flows through the SAME
fetch / tier / strict_verify chokepoint.
"""
from __future__ import annotations

import httpx
import pytest

import src.polaris_graph.retrieval.domain_backends as _db
import src.polaris_graph.retrieval.live_retriever as lr
import src.polaris_graph.telemetry.tool_tracer as tt
from src.polaris_graph.retrieval.prefetch_offtopic_filter import SearchCandidate

_NL = (
    "What are the cardiovascular outcomes of tirzepatide in adults with type 2 "
    "diabetes according to the randomized controlled trial literature?"
)

# The exact rate-limit body OpenAlex returns for anonymous search under load
# (2026-02-13 policy; reproduced live in the U25 root-cause investigation).
_RATE_LIMIT_BODY = {
    "error": "Search temporarily unavailable",
    "message": (
        "Anonymous search is temporarily rate-limited due to heavy load. "
        "Please use a free API key: https://openalex.org/rest-api"
    ),
}


def _works(n: int) -> dict:
    """A well-formed OpenAlex /works page with ``n`` resolvable works (no next cursor)."""
    return {
        "results": [
            {
                "doi": f"https://doi.org/10.1000/u25.{i}",
                "id": f"https://openalex.org/W{1000 + i}",
                "display_name": f"U25 work {i}",
                "publication_year": 2024,
            }
            for i in range(n)
        ],
        "meta": {"next_cursor": None},
    }


def _install_fake_openalex_transport(monkeypatch, response_for, captured):
    """Route every ``httpx.Client`` GET through a MockTransport (no network).

    ``response_for(request) -> httpx.Response``; ``captured`` collects the outgoing
    requests so a test can assert the exact query params that reached OpenAlex.
    """
    real_client = httpx.Client

    def _handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return response_for(request)

    def _factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(_handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", _factory)


def _single_page(monkeypatch):
    """Force a deterministic single keyless page regardless of the ambient .env slate."""
    monkeypatch.setenv("PG_OPENALEX_MAX_PAGES", "1")
    monkeypatch.setenv("PG_OPENALEX_PER_PAGE", "25")


# ─────────────────────────────────────────────────────────────────────────────
# Part 1 — domain_backends.openalex_search: auth params + fail-loud on non-200
# ─────────────────────────────────────────────────────────────────────────────


def test_openalex_search_raises_on_503(monkeypatch):
    """RED->GREEN: a 503 (anonymous-search rate-limit) must FAIL LOUD, not return [].

    Pre-fix ``openalex_search`` swallows the 503 and returns ``[]`` (no raise) -> this
    fails. Post-fix it raises ``OpenAlexHTTPError`` (a ``RuntimeError`` subclass) that
    carries the 503 status. The expected type is spelled ``RuntimeError`` so the test
    module imports cleanly against the pre-fix tree (where ``OpenAlexHTTPError`` does
    not yet exist)."""
    _single_page(monkeypatch)
    captured: list[httpx.Request] = []
    _install_fake_openalex_transport(
        monkeypatch,
        lambda req: httpx.Response(503, json=_RATE_LIMIT_BODY),
        captured,
    )

    with pytest.raises(RuntimeError) as exc_info:
        _db.openalex_search("q", limit=10)

    # The raised error must carry the 503 so the caller can record it honestly.
    assert "503" in str(exc_info.value)
    status_code = getattr(exc_info.value, "status_code", None)
    assert status_code == 503
    assert captured, "the backend must have actually issued the OpenAlex request"


def test_genuine_200_empty_returns_empty_without_raise(monkeypatch):
    """A real 200 with results=[] (no matching works) is an honest zero -> [], NO raise.

    This is the case the caller must be able to distinguish from the 503 failure."""
    _single_page(monkeypatch)
    captured: list[httpx.Request] = []
    _install_fake_openalex_transport(
        monkeypatch,
        lambda req: httpx.Response(200, json={"results": [], "meta": {"next_cursor": None}}),
        captured,
    )

    out = _db.openalex_search("q", limit=10)
    assert out == []
    assert captured, "a genuine-empty run still issues the request"


def test_openalex_search_returns_candidates_on_results(monkeypatch):
    """A 200 with 3 works -> 3 SearchCandidates (source='openalex_search')."""
    _single_page(monkeypatch)
    captured: list[httpx.Request] = []
    _install_fake_openalex_transport(
        monkeypatch,
        lambda req: httpx.Response(200, json=_works(3)),
        captured,
    )

    out = _db.openalex_search("q", limit=10)
    assert len(out) == 3
    assert all(isinstance(c, SearchCandidate) for c in out)
    assert all(c.source == "openalex_search" for c in out)
    assert all(c.url for c in out)


def test_auth_params_present_when_configured(monkeypatch):
    """RED->GREEN: PG_OPENALEX_API_KEY + PG_OPENALEX_MAILTO reach the request as
    ``api_key`` / ``mailto`` query params (per developers.openalex.org)."""
    _single_page(monkeypatch)
    monkeypatch.setenv("PG_OPENALEX_API_KEY", "test-key-123")
    monkeypatch.setenv("PG_OPENALEX_MAILTO", "a@b.c")
    captured: list[httpx.Request] = []
    _install_fake_openalex_transport(
        monkeypatch,
        lambda req: httpx.Response(200, json=_works(1)),
        captured,
    )

    _db.openalex_search("q", limit=10)

    assert captured, "no OpenAlex request was issued"
    params = captured[0].url.params
    assert params.get("api_key") == "test-key-123"
    assert params.get("mailto") == "a@b.c"
    # the core search params are still intact (auth is additive, never overriding)
    assert params.get("search") == "q"


def test_auth_params_absent_when_unset_byte_identical(monkeypatch):
    """auth-off is byte-identical: NO api_key / mailto key when the env is unset."""
    _single_page(monkeypatch)
    monkeypatch.delenv("PG_OPENALEX_API_KEY", raising=False)
    monkeypatch.delenv("PG_OPENALEX_MAILTO", raising=False)
    captured: list[httpx.Request] = []
    _install_fake_openalex_transport(
        monkeypatch,
        lambda req: httpx.Response(200, json=_works(1)),
        captured,
    )

    _db.openalex_search("q", limit=10)

    assert captured
    params = captured[0].url.params
    assert "api_key" not in params
    assert "mailto" not in params
    assert params.get("search") == "q"


# ─────────────────────────────────────────────────────────────────────────────
# Part 2 — live_retriever wiring: a 0-candidate backend must NOT read success_rate=1.0
# ─────────────────────────────────────────────────────────────────────────────


def _run_retrieval_with_openalex(monkeypatch, openalex_impl):
    """Run the minimal offline retrieval that hits the OpenAlex discovery branch,
    with a FRESH bound tool tracer, and return that tracer. All other backends are
    stubbed empty (mirrors the FX-18b harness)."""
    monkeypatch.setenv("PG_OPENALEX_SEARCH", "1")
    monkeypatch.setenv("PG_ENABLE_TOOL_TRACKER", "1")
    # Keep the run OFFLINE + light (§8.4): the OpenAlex discovery trace we assert on is
    # emitted BEFORE the relevance gate, so disabling the embedder relevance gate + the
    # W2 reranker judge changes nothing under test but avoids loading any model on CPU.
    monkeypatch.setenv("PG_RETRIEVAL_RELEVANCE_GATE", "0")
    monkeypatch.setenv("PG_CONTENT_RELEVANCE_JUDGE", "0")

    monkeypatch.setattr(lr, "_serper_search", lambda q, num=10, api_calls=None: [])
    monkeypatch.setattr(lr, "_s2_bulk_search", lambda query, limit=20: [])
    monkeypatch.setattr(_db, "openalex_search", openalex_impl)
    monkeypatch.setattr(
        lr, "_fetch_content",
        lambda url, max_chars, **kwargs: (
            "Tirzepatide lowered major adverse cardiovascular events in the trial. " * 8,
            True, "T", "html", "",
        ),
    )

    tt.reset_tool_tracer()
    tt.get_tool_tracer()  # bind a fresh singleton the wiring's _trace_tool records into
    lr.run_live_retrieval(
        research_question=_NL,
        protocol=None,
        anchor_seed=True,
        enable_openalex_enrich=False,
        enable_prefetch_filter=False,
        fetch_cap=10,
    )
    return tt.get_tool_tracer()


def _openalex_rows(tracer):
    return [c for c in tracer.get_calls() if c.tool_name == "openalex_search"]


def test_success_rate_not_masked_on_zero_candidates(monkeypatch):
    """RED->GREEN (the headline U25 assertion, no new symbol referenced).

    OpenAlex returns 0 candidates (as the swallowed 503 did in production). Pre-fix the
    wiring records status='ok' -> success_rate 1.0 (the mask). Post-fix it records
    status='ok_zero' (zero_yield) -> success_rate 0.0. A backend that returned NOTHING
    must never read as a 1.0-success."""
    tracer = _run_retrieval_with_openalex(monkeypatch, lambda q, limit=20: [])

    rows = _openalex_rows(tracer)
    assert rows, "the OpenAlex discovery branch did not fire"
    assert all(r.metadata.get("result_count") == 0 for r in rows)

    # THE un-mask: a 0-candidate backend must not read success_rate == 1.0.
    summary = tracer.manifest()["summary_by_tool"]["openalex_search"]
    assert summary["success_rate"] == 0.0

    # And the honest signal is surfaced: status='ok_zero' + zero_yield=True, never 'ok'.
    assert all(r.status == "ok_zero" for r in rows)
    assert all(r.metadata.get("zero_yield") is True for r in rows)


def test_http_error_recorded_as_fail_not_ok(monkeypatch):
    """RED->GREEN: an OpenAlex HTTP error (503) is recorded status='fail' with
    zero_yield=True and the error text carrying the 503 -- never masked as 'ok'.

    The zero_yield=True assertion is the RED leg (the pre-fix fail branch never set it)."""
    oa_err = getattr(_db, "OpenAlexHTTPError", RuntimeError)

    def _raise_503(q, limit=20):
        raise oa_err("HTTP 503 from https://api.openalex.org/works")

    tracer = _run_retrieval_with_openalex(monkeypatch, _raise_503)

    rows = _openalex_rows(tracer)
    assert rows, "the OpenAlex discovery branch did not fire"
    assert all(r.status == "fail" for r in rows)
    assert all(r.metadata.get("zero_yield") is True for r in rows)
    assert all("503" in (r.error or "") for r in rows)

    summary = tracer.manifest()["summary_by_tool"]["openalex_search"]
    assert summary["success_rate"] == 0.0


def test_real_hits_still_recorded_ok(monkeypatch):
    """Regression: a genuine non-empty OpenAlex return still records status='ok'
    (zero_yield falsy) -> success_rate 1.0. The un-mask must not penalize real hits."""
    def _two_hits(q, limit=20):
        return [
            SearchCandidate(url="https://oa.org/a", title="A", snippet="", source="openalex_search"),
            SearchCandidate(url="https://oa.org/b", title="B", snippet="", source="openalex_search"),
        ]

    tracer = _run_retrieval_with_openalex(monkeypatch, _two_hits)

    rows = _openalex_rows(tracer)
    assert rows, "the OpenAlex discovery branch did not fire"
    assert all(r.status == "ok" for r in rows)
    assert all(r.metadata.get("result_count") == 2 for r in rows)
    assert all(not r.metadata.get("zero_yield") for r in rows)

    summary = tracer.manifest()["summary_by_tool"]["openalex_search"]
    assert summary["success_rate"] == 1.0
