"""I-beatboth-fix-000 (#1171) — RETRIEVAL BREADTH-COLLAPSE chain — offline funnel-delta smokes.

Each test asserts ONE sub-fix's discovery-funnel widening AND that the default-OFF path is
byte-identical. ALL OFFLINE (no network): the HTTP/agentic/STORM seams are stubbed. None of these
fixes touch strict_verify, the entailment/NLI judge, or the 4-role seam — every test here is purely
DISCOVERY-breadth (candidates) or telemetry/observability.

  BB-001  scope-validator: containment keeps short on-topic queries that jaccard drops; OFF identical.
  BB-002  Serper page loop: PG_SERPER_STOP_ON_ZERO_NEW continues past a sub-per_page page; OFF identical.
  BB-003  OpenAlex search: cursor paging accumulates across pages > the legacy 25; OFF single page.
  BB-004  Semantic Scholar: a HTTP-200 zero-yield traces a DISTINCT ok_zero/zero_yield (not silent ok).
  BB-005  agentic harvest: harvest cap decoupled from fetch cap (discovery telemetry only).
  BB-006  STORM web_results: harvest_storm_urls returns ONLY web_results[*].url, NEVER synthesized text.
  BB-007  OA resolver: placeholder PG_UNPAYWALL_EMAIL -> resolver-unavailable trace (no silent no-op).
"""
from __future__ import annotations

import logging

import pytest

import src.polaris_graph.retrieval.domain_backends as db
import src.polaris_graph.retrieval.live_retriever as lr
from src.polaris_graph.retrieval.agentic_url_harvester import (
    harvest_agentic_urls,
    harvest_storm_urls,
)
from src.polaris_graph.retrieval.prefetch_offtopic_filter import SearchCandidate
from src.polaris_graph.retrieval.scope_query_validator import (
    validate_amplified_queries,
)


# ─────────────────────────────────────────────────────────────────────────────
# BB-001 — scope-validator containment vs jaccard
# ─────────────────────────────────────────────────────────────────────────────

def _wide_anchor_protocol() -> dict:
    """A ~30-token anchor (research_question + PICO) — the size that punishes short
    on-topic queries under symmetric Jaccard (tiny intersection / huge union)."""
    return {
        "research_question": (
            "To what extent will artificial intelligence and automation technologies "
            "displace or transform jobs across the labor market over the next decade, "
            "and what does the empirical economics literature conclude about net "
            "employment effects and wage polarization in advanced economies?"
        ),
        "population": "workers in advanced economies",
        "intervention": "artificial intelligence automation",
        "outcome": "employment wages displacement",
    }


# Eight SHORT (4-6 token) on-topic queries — each shares a few anchor terms but its
# union with the 30-token anchor is huge, so jaccard sits far under any sane floor.
_SHORT_ONTOPIC = [
    "automation employment effects",
    "artificial intelligence labor market",
    "wage polarization advanced economies",
    "job displacement automation decade",
    "net employment effects automation",
    "labor market transformation technology",
    "economics literature automation jobs",
    "ai workers displacement wages",
]


def test_bb001_containment_keeps_short_ontopic_where_jaccard_drops(monkeypatch):
    """At the legacy code-default floor 0.15 (the forensic's chokepoint: "floor=0.15 kept=5
    dropped=35"), symmetric jaccard drops the short on-topic queries (all score 0.067-0.143 < 0.15
    against the 28-token anchor) while containment keeps them. Funnel delta: jaccard <=2 kept,
    containment >=7 kept — the #1 retrieval-breadth chokepoint widened."""
    proto = _wide_anchor_protocol()
    floor = 0.15  # the legacy code default — the exact floor the forensic recorded the collapse at

    monkeypatch.setenv("PG_SCOPE_SIM_MEASURE", "jaccard")
    jac = validate_amplified_queries(list(_SHORT_ONTOPIC), proto, floor=floor)
    # research_question is always prepended (always_keep_anchor); count only the 8 amplified.
    jac_kept = [q for q in jac.kept if q in _SHORT_ONTOPIC]

    monkeypatch.setenv("PG_SCOPE_SIM_MEASURE", "containment")
    con = validate_amplified_queries(list(_SHORT_ONTOPIC), proto, floor=floor)
    con_kept = [q for q in con.kept if q in _SHORT_ONTOPIC]

    assert len(jac_kept) <= 2, f"jaccard should drop most short on-topic queries, kept {jac_kept}"
    assert len(con_kept) >= 7, f"containment should keep short on-topic queries, kept {con_kept}"


def test_bb001_off_default_is_jaccard_byte_identical(monkeypatch):
    """Unset PG_SCOPE_SIM_MEASURE == explicit jaccard == legacy behaviour (kept/dropped identical)."""
    proto = _wide_anchor_protocol()
    monkeypatch.delenv("PG_SCOPE_SIM_MEASURE", raising=False)
    default = validate_amplified_queries(list(_SHORT_ONTOPIC), proto, floor=0.08)
    monkeypatch.setenv("PG_SCOPE_SIM_MEASURE", "jaccard")
    explicit = validate_amplified_queries(list(_SHORT_ONTOPIC), proto, floor=0.08)
    assert default.kept == explicit.kept
    # OFF reason string carries NO measure suffix (byte-identical legacy reason).
    assert all(r.startswith("below_scope_floor_") and not r.endswith("jaccard")
               for _q, _s, r in default.dropped)


def test_bb001_containment_still_drops_genuine_drift(monkeypatch):
    """The gate is KEPT, not removed: off-anchor drift still fails under containment."""
    proto = _wide_anchor_protocol()
    monkeypatch.setenv("PG_SCOPE_SIM_MEASURE", "containment")
    drift = ["Japan national health insurance elderly care", "blockchain agriculture supply chain"]
    res = validate_amplified_queries(drift, proto, floor=0.08)
    dropped_q = [d[0] for d in res.dropped]
    assert any("Japan" in q for q in dropped_q)
    assert any("blockchain" in q for q in dropped_q)


def test_bb001_unrecognised_measure_fails_loud(monkeypatch):
    monkeypatch.setenv("PG_SCOPE_SIM_MEASURE", "cosine")
    with pytest.raises(ValueError):
        validate_amplified_queries(["x y z"], _wide_anchor_protocol(), floor=0.08)


# ─────────────────────────────────────────────────────────────────────────────
# BB-002 — Serper page loop (stop-on-zero-new)
# ─────────────────────────────────────────────────────────────────────────────

def _install_serper_pages(monkeypatch, pages: dict[int, list[str]]):
    calls: list[int] = []

    def _fake(query, per_page, page, headers):
        calls.append(page)
        urls = pages.get(page, [])
        items = [{"url": u, "title": "t", "snippet": "s", "source": "serper"} for u in urls]
        return items, True, 1.0, 100, ""

    monkeypatch.setattr(lr, "_serper_fetch_page", _fake)
    monkeypatch.setenv("SERPER_API_KEY", "test-key")
    return calls


def test_bb002_stop_on_zero_new_continues_past_short_page(monkeypatch):
    """With the flag ON, a sub-per_page page that adds NEW urls does NOT stop the loop."""
    monkeypatch.setenv("PG_SERPER_STOP_ON_ZERO_NEW", "1")
    monkeypatch.setenv("PG_SERPER_TOTAL_PER_QUERY", "60")
    # page 1: only 5 urls (< per_page 20) but all NEW -> must continue; page 2: 8 more NEW.
    calls = _install_serper_pages(monkeypatch, {
        1: [f"https://x/{i}" for i in range(5)],
        2: [f"https://x/{i}" for i in range(5, 13)],
        3: [],  # zero new -> stop
    })
    out = lr._serper_search("q", num=20)
    assert calls == [1, 2, 3], f"expected to page past the short page, got {calls}"
    assert len(out) == 13


def test_bb002_stop_on_zero_new_stops_on_duplicate_page(monkeypatch):
    """A page that adds 0 NEW (all duplicates) stops the loop even with budget remaining."""
    monkeypatch.setenv("PG_SERPER_STOP_ON_ZERO_NEW", "1")
    monkeypatch.setenv("PG_SERPER_TOTAL_PER_QUERY", "200")
    monkeypatch.setenv("PG_SERPER_MAX_PAGES", "5")
    calls = _install_serper_pages(monkeypatch, {
        1: [f"https://x/{i}" for i in range(20)],
        2: [f"https://x/{i}" for i in range(20)],  # all duplicates -> 0 new -> stop
        3: [f"https://x/{i}" for i in range(40, 60)],  # never reached
    })
    out = lr._serper_search("q", num=20)
    assert calls == [1, 2], f"duplicate page should stop the loop, got {calls}"
    assert len(out) == 20


def test_bb002_off_default_short_page_stops_byte_identical(monkeypatch):
    """OFF (default): a sub-per_page page-1 stops immediately — the legacy FX-17 behaviour."""
    monkeypatch.delenv("PG_SERPER_STOP_ON_ZERO_NEW", raising=False)
    monkeypatch.setenv("PG_SERPER_TOTAL_PER_QUERY", "60")
    calls = _install_serper_pages(monkeypatch, {
        1: [f"https://x/{i}" for i in range(5)],
        2: [f"https://x/{i}" for i in range(5, 13)],  # would be reached only if the flag were on
    })
    out = lr._serper_search("q", num=20)
    assert calls == [1], f"OFF must stop on the short page (legacy), got {calls}"
    assert len(out) == 5


# ─────────────────────────────────────────────────────────────────────────────
# BB-003 — OpenAlex cursor paging
# ─────────────────────────────────────────────────────────────────────────────

def _make_oa_works(start: int, n: int) -> list[dict]:
    return [
        {"id": f"https://openalex.org/W{i}", "doi": "", "display_name": f"work {i}",
         "publication_year": 2023}
        for i in range(start, start + n)
    ]


def test_bb003_cursor_paging_accumulates_past_25(monkeypatch):
    """With per_page=200 + max_pages>1, the cursor loop accumulates across pages (> the legacy 25)."""
    monkeypatch.setenv("PG_OPENALEX_PER_PAGE", "200")
    monkeypatch.setenv("PG_OPENALEX_MAX_PAGES", "3")
    seen_params: list[dict] = []
    pages = {
        "*": {"results": _make_oa_works(0, 200), "meta": {"next_cursor": "c2"}},
        "c2": {"results": _make_oa_works(200, 200), "meta": {"next_cursor": "c3"}},
        "c3": {"results": _make_oa_works(400, 50), "meta": {"next_cursor": None}},
    }

    def _fake_get_json(url, params=None):
        seen_params.append(dict(params or {}))
        return pages.get((params or {}).get("cursor"), {"results": [], "meta": {}})

    monkeypatch.setattr(db, "_http_get_json", _fake_get_json)
    # limit=450 so the loop must consume all 3 cursor pages (200+200+50) to accumulate past 25.
    out = db.openalex_search("automation labor", limit=450)
    assert len(out) == 450, f"cursor loop should accumulate across pages, got {len(out)}"
    assert len(out) > 25, "BB-003: must accumulate well past the legacy 25/query single-page cap"
    # per_page=200 sent (the OpenAlex max), and the cursor param threaded across all 3 pages.
    assert all(p["per_page"] == 200 for p in seen_params)
    assert seen_params[0]["cursor"] == "*"
    assert len(seen_params) == 3
    assert [p["cursor"] for p in seen_params] == ["*", "c2", "c3"]


def test_bb003_off_default_single_page_no_cursor_byte_identical(monkeypatch):
    """OFF (per_page unset=25, max_pages unset=1): exactly the legacy single 25-cap request, no cursor."""
    monkeypatch.delenv("PG_OPENALEX_PER_PAGE", raising=False)
    monkeypatch.delenv("PG_OPENALEX_MAX_PAGES", raising=False)
    seen_params: list[dict] = []

    def _fake_get_json(url, params=None):
        seen_params.append(dict(params or {}))
        return {"results": _make_oa_works(0, 25), "meta": {"next_cursor": "c2"}}

    monkeypatch.setattr(db, "_http_get_json", _fake_get_json)
    out = db.openalex_search("automation labor", limit=100)
    assert len(seen_params) == 1, "OFF must issue exactly one page"
    assert "cursor" not in seen_params[0], "OFF request must NOT carry a cursor param (byte-identical)"
    assert seen_params[0]["per_page"] == 25  # max(1, min(100, 25))
    assert len(out) == 25


# ─────────────────────────────────────────────────────────────────────────────
# BB-004 — Semantic Scholar zero-yield loud signal
# ─────────────────────────────────────────────────────────────────────────────

class _FakeResp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.content = b"{}"

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _install_s2(monkeypatch, payload):
    traced: list[dict] = []

    def _fake_get(self, url, params=None, headers=None):
        return _FakeResp(200, payload)

    monkeypatch.setattr(_FakeClient, "get", _fake_get, raising=False)
    monkeypatch.setattr(lr.httpx, "Client", lambda *a, **k: _FakeClient())

    def _fake_trace(tool_name, **kw):
        if tool_name == "s2":
            traced.append({"tool": tool_name, **kw})

    monkeypatch.setattr(lr, "_trace_tool", _fake_trace)
    monkeypatch.setattr(lr, "_trace_query", lambda *a, **k: None)
    return traced


def test_bb004_zero_yield_traces_distinct_signal(monkeypatch):
    """A HTTP-200 with 0 usable papers traces status=ok_zero + zero_yield=True (NOT silent ok)."""
    traced = _install_s2(monkeypatch, {"data": []})
    out = lr._s2_bulk_search("metformin", limit=12)
    assert out == []
    s2_row = traced[-1]
    assert s2_row["status"] == "ok_zero", f"zero-yield must trace ok_zero, got {s2_row['status']}"
    assert s2_row["zero_yield"] is True
    assert s2_row["result_count"] == 0


def test_bb004_nonzero_yield_stays_ok(monkeypatch):
    """A normal yield stays status=ok with zero_yield=False (byte-identical success semantics)."""
    payload = {"data": [
        {"title": "p", "abstract": "a", "openAccessPdf": {"url": "https://oa/p.pdf"},
         "externalIds": {"DOI": "10.1/x"}, "paperId": "P1", "year": 2023, "venue": "v"},
    ]}
    traced = _install_s2(monkeypatch, payload)
    out = lr._s2_bulk_search("metformin", limit=12)
    assert len(out) == 1
    s2_row = traced[-1]
    assert s2_row["status"] == "ok"
    assert s2_row["zero_yield"] is False
    assert s2_row["result_count"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# BB-005 — agentic harvest cap honored (decoupled from fetch)
# ─────────────────────────────────────────────────────────────────────────────

def _agentic_result_with(n: int) -> dict:
    return {"web_results": [{"url": f"https://a/{i}", "title": "t", "snippet": "s"} for i in range(n)]}


def test_bb005_harvest_cap_honored_dedup_intact():
    """harvest_agentic_urls(result_with_1933, cap=800) returns 800 (the raised discovery cap)."""
    res = _agentic_result_with(1933)
    out = harvest_agentic_urls(res, cap=800)
    assert len(out) == 800
    assert len(set(out)) == 800  # dedup intact


def test_bb005_harvest_cap_smaller_than_discovered_truncates():
    """The fetch cap (100) truncates the harvested set — the budget-respecting fetch subset."""
    res = _agentic_result_with(1933)
    out = harvest_agentic_urls(res, cap=100)
    assert len(out) == 100


# ─────────────────────────────────────────────────────────────────────────────
# BB-006 — STORM URL-ONLY harvest (faithfulness contract)
# ─────────────────────────────────────────────────────────────────────────────

def _storm_out_with(n: int) -> dict:
    """A STORM result carrying web_results URLs AND synthesized text that must NEVER be harvested."""
    return {
        "storm_conversations": [{"q": "interview q", "a": "interview answer text"}],
        "storm_outline": ["section 1", "section 2"],
        "web_results": [
            {"url": f"https://storm/{i}", "title": f"title {i}",
             "snippet": f"SYNTHESIZED-SNIPPET-{i}-must-not-be-evidence"}
            for i in range(n)
        ],
        "academic_results": [{"url": f"https://storm-ac/{i}", "title": "ac", "snippet": "ac snip"}
                             for i in range(3)],
        # synthesized fields that must NEVER appear in the harvest:
        "answer": "STORM SYNTHESIZED ANSWER — this is a paraphrase and must not be evidence",
        "key_findings": ["STORM KEY FINDING that is an LLM paraphrase"],
    }


def test_bb006_harvest_storm_urls_returns_only_urls():
    """harvest_storm_urls returns ONLY web_results/academic_results URLs — never synthesized text."""
    out = harvest_storm_urls(_storm_out_with(478), cap=200)
    assert len(out) == 200  # capped
    # Every returned item is a fetchable URL from the result streams.
    assert all(u.startswith("https://storm") for u in out)
    # The HARD contract: no synthesized STORM text leaked into the harvest.
    blob = " ".join(out)
    assert "SYNTHESIZED-SNIPPET" not in blob
    assert "SYNTHESIZED ANSWER" not in blob
    assert "KEY FINDING" not in blob
    assert "interview answer" not in blob


def test_bb006_harvest_storm_urls_deduped_and_capped():
    out = harvest_storm_urls(_storm_out_with(50), cap=200)
    assert len(out) == len(set(out))      # deduped
    assert len(out) == 53                 # 50 web + 3 academic, all distinct


def test_bb006_harvest_storm_urls_empty_safe():
    assert harvest_storm_urls(None, cap=200) == []
    assert harvest_storm_urls({}, cap=200) == []
    assert harvest_storm_urls(_storm_out_with(10), cap=0) == []


def test_bb006_storm_snippet_never_becomes_direct_quote():
    """A STORM seed URL flows as a URL-only candidate: harvest never carries the snippet as a quote.

    (The seed re-fetch makes direct_quote the verbatim FETCHED span; the harvest output is a bare
    URL string — there is no field through which the synthesized snippet could ride as evidence.)
    """
    out = harvest_storm_urls(_storm_out_with(5), cap=200)
    assert all(isinstance(u, str) and u.startswith("http") for u in out)


# ─────────────────────────────────────────────────────────────────────────────
# BB-007 — OA resolver placeholder-email guard
# ─────────────────────────────────────────────────────────────────────────────

def test_bb007_placeholder_email_traces_resolver_unavailable(monkeypatch):
    """The placeholder PG_UNPAYWALL_EMAIL -> resolver-unavailable trace + [] (no silent no-op)."""
    monkeypatch.setenv("PG_UNPAYWALL_EMAIL", "polaris@example.org")
    traced: list[dict] = []
    monkeypatch.setattr(lr, "_trace_tool",
                        lambda tool, **kw: traced.append({"tool": tool, **kw}))

    def _boom_client(*a, **k):
        raise AssertionError("Unpaywall must NOT be called with the placeholder email")
    monkeypatch.setattr(lr.httpx, "Client", _boom_client)

    out = lr._unpaywall_get_oa_urls("10.1056/NEJMoa2307563")
    assert out == []
    oa_rows = [t for t in traced if t["tool"] == "oa_resolver"]
    assert oa_rows, "expected an oa_resolver trace row"
    assert oa_rows[-1]["status"] == "unavailable"
    assert oa_rows[-1].get("resolver_unavailable") is True
    assert oa_rows[-1].get("error") == "placeholder_unpaywall_email"


def test_bb007_empty_email_also_unavailable(monkeypatch):
    monkeypatch.setenv("PG_UNPAYWALL_EMAIL", "")
    monkeypatch.setattr(lr, "_trace_tool", lambda *a, **k: None)
    monkeypatch.setattr(lr.httpx, "Client",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no call")))
    assert lr._unpaywall_get_oa_urls("10.1/x") == []


def test_bb007_real_email_resolves_stubbed(monkeypatch):
    """A REAL email lets the resolver fire; with a stubbed OA response it returns the OA url(s)."""
    monkeypatch.setenv("PG_UNPAYWALL_EMAIL", "research@polaris-dr.org")
    monkeypatch.setattr(lr, "_trace_tool", lambda *a, **k: None)

    class _Resp:
        status_code = 200

        def json(self):
            return {"is_oa": True, "best_oa_location": {"url_for_pdf": "https://oa/full.pdf"}}

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **k):
            return _Resp()

    monkeypatch.setattr(lr.httpx, "Client", lambda *a, **k: _Client())
    # Stub the shared parser to the canonical OA-URL shape.
    import src.polaris_graph.retrieval.frame_fetcher as ff
    monkeypatch.setattr(
        ff, "_parse_unpaywall_response",
        lambda d: {"is_oa": True, "oa_pdf_url": "https://oa/full.pdf", "oa_html_url": ""},
    )
    out = lr._unpaywall_get_oa_urls("10.1056/NEJMoa2307563")
    assert out == ["https://oa/full.pdf"]


def test_bb007_openalex_search_doi_threads_to_candidate_metadata(monkeypatch):
    """BB-007 part-2 regression: an openalex_search candidate WITH a DOI carries it in metadata
    AND its URL is doi.org — so _candidate_oa_hints + _extract_doi_from_url both surface the DOI to
    the OA resolver. (A DOI-less work gets an openalex.org/W url with metadata['doi']=None; there is
    genuinely no DOI to thread, so the resolver correctly cannot fire — not a bug.)"""
    def _fake_get_json(url, params=None):
        return {"results": [
            {"id": "https://openalex.org/W1", "doi": "https://doi.org/10.1/withdoi",
             "display_name": "has doi", "publication_year": 2023},
            {"id": "https://openalex.org/W2", "doi": "", "display_name": "no doi",
             "publication_year": 2022},
        ], "meta": {}}

    monkeypatch.setattr(db, "_http_get_json", _fake_get_json)
    monkeypatch.delenv("PG_OPENALEX_PER_PAGE", raising=False)
    monkeypatch.delenv("PG_OPENALEX_MAX_PAGES", raising=False)
    out = db.openalex_search("q", limit=10)
    by_title = {c.title: c for c in out}
    # WITH-doi candidate: url is doi.org AND metadata carries the DOI -> resolver can fire.
    with_doi = by_title["has doi"]
    assert with_doi.url.startswith("https://doi.org/")
    assert with_doi.metadata["doi"] == "https://doi.org/10.1/withdoi"
    assert lr._candidate_oa_hints(with_doi.metadata)[0] == "https://doi.org/10.1/withdoi"
    # NO-doi candidate: openalex.org/W url, metadata doi None -> genuinely no DOI to thread.
    no_doi = by_title["no doi"]
    assert no_doi.url.startswith("https://openalex.org/W")
    assert no_doi.metadata["doi"] is None
    assert lr._candidate_oa_hints(no_doi.metadata)[0] == ""
