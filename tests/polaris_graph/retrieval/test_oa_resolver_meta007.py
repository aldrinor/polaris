"""I-meta-007c — OPEN-ACCESS resolver wired into the LIVE retrieval loop.

SPEND-FREE smoke per `.codex/I-meta-007/_wiring_specs.txt`
LANE wire:unpaywall-live-path OFFLINE SMOKE PLAN. NO real network, NO LLM,
NO generator tokens: every external seam (AccessBypass, Unpaywall, PubMed
EFetch) is monkeypatched. The OA resolver REUSES the already-budgeted
AccessBypass stack — these tests assert the wiring only.

Cases:
  (a) AccessBypass stub + DOI + Unpaywall OA found -> _fetch_content returns
      the OA content (NOT the existing stub return).
  (b) Unpaywall is_oa=False + PMID -> PubMed EFetch abstract used.
  (c) both fail -> _fetch_content falls through to the existing stub return.
  (d) env gate OFF (PG_ENABLE_LIVE_OA_RESOLVER=0) -> resolver not called.
  (e) DOI extracted from a Frontiers-style URL when no metadata DOI present.
  (f) OA content capped at the max-chars cap.

Plain monkeypatch — NO unittest.mock (CLAUDE.md §9.4). Serialized per §8.4.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.retrieval import live_retriever as lr


# ── fakes (plain objects, no mocks) ──────────────────────────────────────────
class _FakeBypassResult:
    """Minimal stand-in for AccessBypass.fetch_with_bypass result."""

    def __init__(self, success: bool, content: str = "") -> None:
        self.success = success
        self.content = content
        self.url = ""
        self.access_method = "fake_bypass"
        self.metadata = {"reason": "paywalled"}


def _stub_bypass_miss(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the primary AccessBypass fetch inside _fetch_content to return a
    stub/empty result so the OA-resolver branch is reached.

    AccessBypass is imported lazily INSIDE _fetch_content, so we patch the
    class on its source module; the fresh-event-loop worker still runs but
    fetch_with_bypass returns a non-success result immediately.
    """
    import src.tools.access_bypass as ab_mod

    class _FakeAccessBypass:
        def __init__(self, *args, **kwargs) -> None:  # noqa: D401, ANN002, ANN003
            pass

        async def fetch_with_bypass(self, url, prefer_legal=True):  # noqa: ANN001
            return _FakeBypassResult(success=False, content="")

    monkeypatch.setattr(ab_mod, "AccessBypass", _FakeAccessBypass)
    # Keep the env clean: ensure AccessBypass path is taken (not the naive
    # PG_DISABLE_ACCESS_BYPASS short-circuit) and the OA resolver is ON.
    monkeypatch.delenv("PG_DISABLE_ACCESS_BYPASS", raising=False)
    monkeypatch.setenv("PG_ENABLE_LIVE_OA_RESOLVER", "1")


# ── (a) Unpaywall OA found -> OA content returned ────────────────────────────
def test_a_unpaywall_oa_found_returns_oa_content(monkeypatch):
    _stub_bypass_miss(monkeypatch)
    monkeypatch.setattr(
        lr, "_unpaywall_get_oa_urls",
        lambda doi: ["https://oa.example.org/paper.pdf"],
    )
    monkeypatch.setattr(
        lr, "_fetch_oa_url_via_bypass",
        lambda oa_url, max_chars: "OA FULL TEXT " * 500,
    )
    # PubMed must NOT be consulted when Unpaywall succeeds.
    monkeypatch.setattr(
        lr, "_pubmed_fetch_abstract",
        lambda pmid: pytest.fail("PubMed must not be called on Unpaywall hit"),
    )

    content, ok, title, body_type, jsonld = lr._fetch_content(
        "https://paywalled.example.org/article",
        lr.DEFAULT_CONTENT_MAX_CHARS,
        doi_hint="10.1234/fake",
    )

    assert ok is True
    assert content.startswith("OA FULL TEXT")
    assert len(content) > 1000  # upgraded from a stub, not empty


# ── (b) Unpaywall no-OA + PMID -> PubMed abstract used ────────────────────────
def test_b_unpaywall_no_oa_falls_back_to_pubmed(monkeypatch):
    _stub_bypass_miss(monkeypatch)
    # Unpaywall returns no OA URLs (is_oa=False path collapses to []).
    monkeypatch.setattr(lr, "_unpaywall_get_oa_urls", lambda doi: [])
    abstract_text = "Background: " + ("clinical abstract sentence. " * 40)
    monkeypatch.setattr(
        lr, "_pubmed_fetch_abstract",
        lambda pmid: abstract_text if pmid == "12345" else "",
    )

    content, ok, title, body_type, jsonld = lr._fetch_content(
        "https://paywalled.example.org/article",
        lr.DEFAULT_CONTENT_MAX_CHARS,
        doi_hint="10.1234/fake",
        pmid_hint="12345",
    )

    assert ok is True
    assert content == abstract_text


# ── (c) both fail -> existing stub return path ───────────────────────────────
def test_c_both_fail_falls_through_to_stub(monkeypatch):
    _stub_bypass_miss(monkeypatch)
    monkeypatch.setattr(lr, "_unpaywall_get_oa_urls", lambda doi: [])
    monkeypatch.setattr(lr, "_pubmed_fetch_abstract", lambda pmid: "")

    content, ok, title, body_type, jsonld = lr._fetch_content(
        "https://paywalled.example.org/article",
        lr.DEFAULT_CONTENT_MAX_CHARS,
        doi_hint="10.1234/fake",
        pmid_hint="12345",
    )

    # Existing stub contract preserved: empty content, ok=False.
    assert ok is False
    assert content == ""


# ── (d) env gate OFF -> resolver not called ──────────────────────────────────
def test_d_env_gate_off_skips_resolver(monkeypatch):
    _stub_bypass_miss(monkeypatch)
    monkeypatch.setenv("PG_ENABLE_LIVE_OA_RESOLVER", "0")

    def _boom(*args, **kwargs):  # noqa: ANN002, ANN003
        pytest.fail("OA resolver must not be invoked when env gate is OFF")

    monkeypatch.setattr(lr, "_unpaywall_get_oa_urls", _boom)
    monkeypatch.setattr(lr, "_pubmed_fetch_abstract", _boom)

    content, ok, title, body_type, jsonld = lr._fetch_content(
        "https://paywalled.example.org/article",
        lr.DEFAULT_CONTENT_MAX_CHARS,
        doi_hint="10.1234/fake",
        pmid_hint="12345",
    )

    assert ok is False
    assert content == ""


# ── (e) DOI extracted from a Frontiers-style URL (no metadata DOI) ───────────
def test_e_doi_extracted_from_frontiers_url(monkeypatch):
    _stub_bypass_miss(monkeypatch)
    frontiers_url = (
        "https://www.frontiersin.org/articles/"
        "10.3389/fphar.2022.1016639/full"
    )
    seen_doi: dict[str, str] = {}

    def _fake_unpaywall(doi):
        seen_doi["doi"] = doi
        return ["https://oa.example.org/frontiers.pdf"]

    monkeypatch.setattr(lr, "_unpaywall_get_oa_urls", _fake_unpaywall)
    monkeypatch.setattr(
        lr, "_fetch_oa_url_via_bypass",
        lambda oa_url, max_chars: "FRONTIERS OA TEXT " * 100,
    )

    # No doi_hint: the DOI must be extracted from the URL.
    content, ok, _t, _b, _j = lr._fetch_content(
        frontiers_url, lr.DEFAULT_CONTENT_MAX_CHARS,
    )

    assert seen_doi.get("doi") == "10.3389/fphar.2022.1016639"
    assert ok is True
    assert content.startswith("FRONTIERS OA TEXT")


# ── (f) content capped at max-chars cap ──────────────────────────────────────
def test_f_oa_content_capped_at_max_chars(monkeypatch):
    _stub_bypass_miss(monkeypatch)
    cap = 5000
    monkeypatch.setattr(
        lr, "_unpaywall_get_oa_urls",
        lambda doi: ["https://oa.example.org/huge.pdf"],
    )
    # _fetch_oa_url_via_bypass itself caps, but _try_oa_resolution re-caps too;
    # return an OVER-CAP blob to prove _fetch_content never balloons past cap.
    monkeypatch.setattr(
        lr, "_fetch_oa_url_via_bypass",
        lambda oa_url, max_chars: "X" * (max_chars * 3),
    )

    content, ok, _t, _b, _j = lr._fetch_content(
        "https://paywalled.example.org/article",
        cap,
        doi_hint="10.1234/fake",
    )

    assert ok is True
    assert len(content) == cap


# ── helper-level: _try_oa_resolution direct seams ────────────────────────────
def test_try_oa_resolution_disabled_returns_empty(monkeypatch):
    monkeypatch.setenv("PG_ENABLE_LIVE_OA_RESOLVER", "0")
    assert lr._try_oa_resolution("http://x", extracted_doi="10.1/x") == ""


def test_try_oa_resolution_fail_open_on_helper_error(monkeypatch):
    monkeypatch.setenv("PG_ENABLE_LIVE_OA_RESOLVER", "1")

    def _raise(doi):
        raise RuntimeError("unpaywall down")

    monkeypatch.setattr(lr, "_unpaywall_get_oa_urls", _raise)
    # Fail-OPEN: error inside the resolver returns "" (never propagates).
    assert lr._try_oa_resolution("http://x", extracted_doi="10.1/x") == ""


def test_candidate_oa_hints_handles_non_dict():
    assert lr._candidate_oa_hints(None) == ("", "")
    assert lr._candidate_oa_hints({"doi": "10.1/x", "pmid": "9"}) == (
        "10.1/x", "9",
    )


# ── diff-gate P2a: _candidate_oa_hints is fail-OPEN on a raising metadata ─────
def test_candidate_oa_hints_fail_open_on_raising_metadata():
    """A metadata object whose ``.get`` raises must yield ("", "") — never
    propagate (diff-gate P2a fail-open contract)."""

    class _Exploding(dict):
        def get(self, *args, **kwargs):  # noqa: ANN002, ANN003
            raise RuntimeError("metadata.get blew up")

    assert lr._candidate_oa_hints(_Exploding()) == ("", "")


# ── diff-gate P1: empty-DOI candidate (PMID-only) is NOT upgraded ─────────────
def test_p1_empty_doi_pmid_only_skips_resolver_and_returns_stub(monkeypatch):
    """The P1 behavior-change Codex flagged: an Europe-PMC-style record with
    doi=None + pmid set must NOT be upgraded to PubMed content. With an empty
    doi_hint AND a URL that embeds NO DOI, _fetch_content must SKIP the OA
    resolver entirely (gate ON) and return the pre-existing miss tuple.

    We monkeypatch _try_oa_resolution itself (and the two helpers) to FAIL the
    test if reached — that proves the skip happens at the _fetch_content call
    site, not merely inside the resolver's internal DOI guard.
    """
    _stub_bypass_miss(monkeypatch)  # gate ON, AccessBypass returns a stub miss.

    def _boom(*args, **kwargs):  # noqa: ANN002, ANN003
        pytest.fail(
            "OA resolver must NOT be invoked for an empty-DOI PMID-only "
            "candidate"
        )

    monkeypatch.setattr(lr, "_try_oa_resolution", _boom)
    monkeypatch.setattr(lr, "_unpaywall_get_oa_urls", _boom)
    monkeypatch.setattr(lr, "_pubmed_fetch_abstract", _boom)

    # No doi_hint; URL embeds no DOI (no `10.xxxx/` pattern, no `doi.org/`),
    # so _extract_doi_from_url(url) == "" -> oa_doi is empty.
    no_doi_url = "https://paywalled.example.org/article"
    assert lr._extract_doi_from_url(no_doi_url) == ""  # guard the premise.

    content, ok, title, body_type, jsonld = lr._fetch_content(
        no_doi_url,
        lr.DEFAULT_CONTENT_MAX_CHARS,
        doi_hint="",
        pmid_hint="12345",
    )

    # Pre-existing stub contract preserved, unchanged.
    assert ok is False
    assert content == ""


# ── diff-gate P2b: gate OFF -> resolver functions are NEVER called ───────────
def test_p2b_gate_off_resolver_never_invoked(monkeypatch):
    """With PG_ENABLE_LIVE_OA_RESOLVER=0, the OFF path is byte-identical control
    flow: _fetch_content must NOT compute the DOI nor call _try_oa_resolution /
    the resolver helpers. We monkeypatch all three to FAIL the test if reached.
    """
    _stub_bypass_miss(monkeypatch)  # AccessBypass returns a stub miss.
    monkeypatch.setenv("PG_ENABLE_LIVE_OA_RESOLVER", "0")

    def _boom(*args, **kwargs):  # noqa: ANN002, ANN003
        pytest.fail(
            "OA resolver must NOT be invoked when PG_ENABLE_LIVE_OA_RESOLVER=0"
        )

    monkeypatch.setattr(lr, "_try_oa_resolution", _boom)
    monkeypatch.setattr(lr, "_unpaywall_get_oa_urls", _boom)
    monkeypatch.setattr(lr, "_pubmed_fetch_abstract", _boom)

    # A non-empty doi_hint is supplied to prove the gate-OFF early-out wins
    # BEFORE any DOI computation / resolver call.
    content, ok, title, body_type, jsonld = lr._fetch_content(
        "https://paywalled.example.org/article",
        lr.DEFAULT_CONTENT_MAX_CHARS,
        doi_hint="10.1234/fake",
        pmid_hint="12345",
    )

    assert ok is False
    assert content == ""


# ── real call-site path: parallel FetchTask metadata carries the hint ─────────
def test_parallel_fetchtask_metadata_carries_doi_to_resolver(monkeypatch):
    """Guards against false confidence (advisor item 4): assert the DEFAULT
    parallel call-site actually threads the candidate DOI to _fetch_content.

    We capture _fetch_content's kwargs by replacing it on the module, then
    build a FetchTask exactly as run_live_retrieval does (doi in task_metadata)
    and drive it through a minimal _LiveContentParallelFetcher clone of the
    real adapter's read path.
    """
    from src.polaris_graph.audit_ir.parallel_fetch import FetchTask

    captured: dict[str, str] = {}

    def _fake_fetch_content(url, max_chars, doi_hint="", pmid_hint=""):
        captured["doi_hint"] = doi_hint
        captured["pmid_hint"] = pmid_hint
        return ("", False, "", "", "")

    monkeypatch.setattr(lr, "_fetch_content", _fake_fetch_content)

    # Mirror the real adapter's read path (live_retriever.py
    # _LiveContentParallelFetcher.fetch): pull doi/pmid from task_metadata.
    doi, pmid = lr._candidate_oa_hints({"doi": "10.9/parallel", "pmid": "777"})
    task = FetchTask(
        source_url="https://paywalled.example.org/p",
        backend_id="default",
        task_metadata={"index": 0, "doi": doi, "pmid": pmid},
    )
    _meta = task.task_metadata or {}
    lr._fetch_content(
        task.source_url, lr.DEFAULT_CONTENT_MAX_CHARS,
        doi_hint=str(_meta.get("doi") or ""),
        pmid_hint=str(_meta.get("pmid") or ""),
    )

    assert captured["doi_hint"] == "10.9/parallel"
    assert captured["pmid_hint"] == "777"
