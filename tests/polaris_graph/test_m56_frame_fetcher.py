"""M-56 tests: V30 deterministic frame fetcher.

Layer 2b of V30 Report Contract Architecture. All tests are
deterministic and run without network access — network is mocked
via an injected httpx.MockTransport.

Covers:
1. Pure parsers (CrossRef, Unpaywall, PubMed) given raw responses.
2. Orchestrator path dispatch:
   - DOI-primary: CrossRef → Unpaywall → PubMed fallback chain.
   - PMID-only-primary: skip CrossRef, use PubMed.
   - URL-pattern-primary (regulatory): skip all 3, emit METADATA_ONLY.
   - Anchor-only: emit FRAME_GAP_UNRECOVERABLE.
3. Provenance class transitions:
   - OA PDF found → OPEN_ACCESS
   - No OA + CrossRef abstract → ABSTRACT_ONLY
   - No OA + no CrossRef abstract + PubMed abstract → ABSTRACT_ONLY
   - Metadata but no abstract → METADATA_ONLY
   - All sources fail → FRAME_GAP_UNRECOVERABLE + failure_reason
4. Retrieval attempt log populated for every attempt.
5. Deterministic: same inputs → same FrameRow.
6. Retry on transient failures (503 then 200 → success).
7. fetch_compiled_frame preserves binding order.
"""
from __future__ import annotations

from typing import Any

import httpx
import pytest

from src.polaris_graph.nodes.frame_compiler import EvidenceBinding
from src.polaris_graph.retrieval.frame_fetcher import (
    FrameRow,
    ProvenanceClass,
    RetrievalAttempt,
    RetrievalTiming,
    _collect_identifiers,
    _parse_crossref_response,
    _parse_pubmed_xml,
    _parse_unpaywall_response,
    _summarize_failure,
    fetch_compiled_frame,
    fetch_frame_entity,
)


# ─────────────────────────────────────────────────────────────────────
# Fixture helpers
# ─────────────────────────────────────────────────────────────────────
def _binding(
    entity_id: str = "surpass_2_primary",
    entity_type: str = "pivotal_trial",
    primary: str = "doi:10.1056/NEJMoa2107519",
    secondaries: tuple[str, ...] = ("pmid:34010531",),
    slot: str = "efficacy_surpass_2",
) -> EvidenceBinding:
    return EvidenceBinding(
        entity_id=entity_id,
        entity_type=entity_type,
        primary_identifier=primary,
        secondary_identifiers=secondaries,
        rendering_slot=slot,
        required_fields=("N", "primary_endpoint"),
        min_fields_for_completion=2,
    )


def _crossref_response(
    doi: str = "10.1056/NEJMoa2107519",
    title: str = "Tirzepatide versus Semaglutide Once Weekly",
    abstract: str | None = (
        "<jats:p>BACKGROUND: tirzepatide. METHODS: we enrolled 1879.</jats:p>"
    ),
    year: int = 2021,
    journal: str = "New England Journal of Medicine",
) -> dict[str, Any]:
    msg: dict[str, Any] = {
        "DOI": doi,
        "title": [title],
        "container-title": [journal],
        "published-print": {"date-parts": [[year, 6, 10]]},
        "author": [
            {"family": "Frias", "given": "Juan P."},
            {"family": "Davies", "given": "Melanie J."},
        ],
    }
    if abstract is not None:
        msg["abstract"] = abstract
    return {"status": "ok", "message": msg}


def _unpaywall_response(
    *,
    is_oa: bool,
    pdf_url: str | None = None,
    html_url: str | None = None,
) -> dict[str, Any]:
    if is_oa:
        best: dict[str, Any] = {}
        if pdf_url is not None:
            best["url_for_pdf"] = pdf_url
            if html_url is None:
                best["url_for_landing_page"] = pdf_url
        if html_url is not None:
            best["url_for_landing_page"] = html_url
        return {
            "doi": "10.1056/NEJMoa2107519",
            "is_oa": True,
            "best_oa_location": best,
        }
    return {
        "doi": "10.1056/NEJMoa2107519",
        "is_oa": False,
        "best_oa_location": None,
    }


def _pubmed_xml(
    *, abstract: str = "Tirzepatide reduced HbA1c by 2.3%.",
    title: str = "Tirzepatide versus semaglutide",
    year: int = 2021,
    doi: str | None = "10.1056/NEJMoa2107519",
    pmid: str = "34010531",
) -> str:
    """Build a PubMed efetch-style XML fixture.

    The optional `doi` parameter emits an
    `<ELocationID EIdType="doi">` so M-56's DOI-consistency guard
    (V30 Phase-2 run-1 root-cause fix) can be exercised in tests.
    """
    doi_elt = (
        f'<ELocationID EIdType="doi" ValidYN="Y">{doi}</ELocationID>'
        if doi is not None else ""
    )
    return f"""<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID Version="1">{pmid}</PMID>
      <Article>
        {doi_elt}
        <ArticleTitle>{title}</ArticleTitle>
        <Abstract>
          <AbstractText>{abstract}</AbstractText>
        </Abstract>
        <AuthorList>
          <Author>
            <LastName>Frias</LastName>
            <Initials>JP</Initials>
          </Author>
        </AuthorList>
        <Journal>
          <Title>NEJM</Title>
          <JournalIssue>
            <PubDate><Year>{year}</Year></PubDate>
          </JournalIssue>
        </Journal>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>"""


class _Transport:
    """Programmable httpx transport that returns canned responses by
    URL substring match. Used to test the orchestrator without real
    network."""

    def __init__(self, rules: list[tuple[str, int, Any]]) -> None:
        """rules: list of (url_substring, status_code, body) tuples.
        body can be dict (JSON) or str (text)."""
        self.rules = rules
        self.call_log: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.call_log.append(url)
        for sub, status, body in self.rules:
            if sub in url:
                if isinstance(body, dict):
                    return httpx.Response(status, json=body)
                if isinstance(body, str):
                    return httpx.Response(
                        status, text=body,
                        headers={"content-type": "text/xml"},
                    )
                return httpx.Response(status)
        return httpx.Response(404, json={"error": "no_rule_matched"})


class _SequencedTransport:
    """Transport that returns different responses on successive calls
    to the same URL substring. Used to exercise retry on transient
    errors. `sequences[substring]` is consumed in FIFO order."""

    def __init__(self, sequences: dict[str, list[tuple[int, Any]]]) -> None:
        self.sequences = {k: list(v) for k, v in sequences.items()}
        self.call_log: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.call_log.append(url)
        for sub, seq in self.sequences.items():
            if sub in url and seq:
                status, body = seq.pop(0)
                if isinstance(body, dict):
                    return httpx.Response(status, json=body)
                if isinstance(body, str):
                    return httpx.Response(
                        status, text=body,
                        headers={"content-type": "text/xml"},
                    )
                return httpx.Response(status)
        return httpx.Response(404, json={"error": "no_rule_matched"})


def _client_with_transport(transport_fn: _Transport) -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(transport_fn),
        timeout=5.0,
    )


# ─────────────────────────────────────────────────────────────────────
# (1) Pure parsers
# ─────────────────────────────────────────────────────────────────────
class TestCrossrefParser:
    def test_full_parse(self) -> None:
        data = _crossref_response()
        parsed = _parse_crossref_response(data)
        assert parsed["doi"] == "10.1056/NEJMoa2107519"
        assert "Tirzepatide" in parsed["title"]
        assert parsed["year"] == 2021
        assert parsed["journal"] == "New England Journal of Medicine"
        assert len(parsed["authors"]) == 2
        assert "Frias" in parsed["authors"][0]
        assert "tirzepatide" in (parsed["abstract"] or "").lower()
        # JATS tags stripped
        assert "<jats:p>" not in (parsed["abstract"] or "")

    def test_empty_response(self) -> None:
        parsed = _parse_crossref_response({})
        assert parsed["title"] is None
        assert parsed["authors"] == ()
        assert parsed["year"] is None
        assert parsed["abstract"] is None

    def test_missing_abstract(self) -> None:
        data = _crossref_response(abstract=None)
        parsed = _parse_crossref_response(data)
        assert parsed["abstract"] is None
        assert parsed["title"]  # still present

    def test_fallback_year_from_issued(self) -> None:
        data = _crossref_response()
        del data["message"]["published-print"]
        data["message"]["issued"] = {"date-parts": [[2023, 1, 1]]}
        parsed = _parse_crossref_response(data)
        assert parsed["year"] == 2023


class TestUnpaywallParser:
    def test_oa_found(self) -> None:
        parsed = _parse_unpaywall_response(
            _unpaywall_response(is_oa=True, pdf_url="https://oa.example/x.pdf")
        )
        assert parsed["is_oa"] is True
        assert parsed["oa_pdf_url"] == "https://oa.example/x.pdf"

    def test_not_oa(self) -> None:
        parsed = _parse_unpaywall_response(
            _unpaywall_response(is_oa=False)
        )
        assert parsed["is_oa"] is False
        assert parsed["oa_pdf_url"] is None

    def test_empty_response(self) -> None:
        parsed = _parse_unpaywall_response({})
        assert parsed["is_oa"] is False


class TestPubmedParser:
    def test_full_parse(self) -> None:
        parsed = _parse_pubmed_xml(_pubmed_xml())
        assert "Tirzepatide" in parsed["abstract"]
        assert parsed["title"]
        assert parsed["year"] == 2021
        assert parsed["authors"][0].startswith("Frias")

    def test_malformed_returns_empty(self) -> None:
        parsed = _parse_pubmed_xml("<not>valid</xml")
        assert parsed == {}

    def test_empty_string(self) -> None:
        assert _parse_pubmed_xml("") == {}
        assert _parse_pubmed_xml("   ") == {}

    def test_labeled_abstract_sections(self) -> None:
        xml = """<PubmedArticleSet><PubmedArticle><MedlineCitation>
        <Article>
          <ArticleTitle>T</ArticleTitle>
          <Abstract>
            <AbstractText Label="BACKGROUND">High HbA1c.</AbstractText>
            <AbstractText Label="METHODS">RCT.</AbstractText>
          </Abstract>
        </Article></MedlineCitation></PubmedArticle></PubmedArticleSet>"""
        parsed = _parse_pubmed_xml(xml)
        assert "BACKGROUND:" in parsed["abstract"]
        assert "METHODS:" in parsed["abstract"]

    def test_doi_and_pmid_extracted(self) -> None:
        """V30 Phase-2 run-1 root-cause guard: the parser must
        surface PubMed's own DOI + PMID so the fetcher can
        detect contract DOI↔PMID mismatches before extraction."""
        xml = """<PubmedArticleSet><PubmedArticle><MedlineCitation>
        <PMID Version="1">34170647</PMID>
        <Article>
          <ELocationID EIdType="doi" ValidYN="Y">10.1056/NEJMoa2107519</ELocationID>
          <ArticleTitle>Tirzepatide versus Semaglutide</ArticleTitle>
          <Abstract><AbstractText>SURPASS-2 content.</AbstractText></Abstract>
        </Article></MedlineCitation></PubmedArticle></PubmedArticleSet>"""
        parsed = _parse_pubmed_xml(xml)
        assert parsed["doi"] == "10.1056/nejmoa2107519"
        assert parsed["pmid"] == "34170647"


# ─────────────────────────────────────────────────────────────────────
# (2) Identifier collection helper
# ─────────────────────────────────────────────────────────────────────
class TestCollectIdentifiers:
    def test_all_four_collected(self) -> None:
        b = _binding(
            primary="doi:10.1/a",
            secondaries=("pmid:123", "url:example.com", "anchor:T"),
        )
        ids = _collect_identifiers(b)
        assert ids == {
            "doi": "10.1/a", "pmid": "123",
            "url": "example.com", "anchor": "T",
        }

    def test_primary_wins_on_collision(self) -> None:
        b = _binding(
            primary="doi:PRIMARY",
            secondaries=("doi:SECONDARY",),
        )
        assert _collect_identifiers(b)["doi"] == "PRIMARY"


# ─────────────────────────────────────────────────────────────────────
# (3) Orchestrator path dispatch
# ─────────────────────────────────────────────────────────────────────
class TestOrchestratorOpenAccessPath:
    def test_oa_pdf_found_emits_open_access(self) -> None:
        transport = _Transport([
            ("api.crossref.org", 200, _crossref_response()),
            ("api.unpaywall.org", 200,
             _unpaywall_response(is_oa=True, pdf_url="https://x.pdf")),
        ])
        with _client_with_transport(transport) as client:
            row = fetch_frame_entity(_binding(), client=client)

        assert row.provenance_class == ProvenanceClass.OPEN_ACCESS
        assert row.oa_pdf_url == "https://x.pdf"
        assert row.quote_source == "crossref_abstract"
        assert "tirzepatide" in row.direct_quote.lower()
        assert row.doi == "10.1056/NEJMoa2107519"
        assert row.pmid == "34010531"
        assert row.year == 2021
        assert row.failure_reason is None
        assert len(row.retrieval_attempts) >= 2

    def test_doi_only_no_oa_crossref_abstract_yields_abstract_only(
        self,
    ) -> None:
        transport = _Transport([
            ("api.crossref.org", 200, _crossref_response()),
            ("api.unpaywall.org", 200, _unpaywall_response(is_oa=False)),
        ])
        with _client_with_transport(transport) as client:
            row = fetch_frame_entity(
                _binding(primary="doi:10.1056/NEJMoa2107519", secondaries=()),
                client=client,
            )

        assert row.provenance_class == ProvenanceClass.ABSTRACT_ONLY
        assert row.oa_pdf_url is None
        assert row.quote_source == "crossref_abstract"
        assert row.direct_quote  # non-empty

    def test_no_oa_no_crossref_abstract_but_pubmed_yields_abstract_only(
        self,
    ) -> None:
        cr_no_abs = _crossref_response(abstract=None)
        transport = _Transport([
            ("api.crossref.org", 200, cr_no_abs),
            ("api.unpaywall.org", 200, _unpaywall_response(is_oa=False)),
            ("eutils.ncbi.nlm.nih.gov", 200, _pubmed_xml()),
        ])
        with _client_with_transport(transport) as client:
            row = fetch_frame_entity(_binding(), client=client)

        assert row.provenance_class == ProvenanceClass.ABSTRACT_ONLY
        assert row.quote_source == "pubmed_abstract"
        assert "Tirzepatide" in row.direct_quote

    def test_html_only_oa_still_classified_open_access(self) -> None:
        """Unpaywall reports is_oa=True with only landing-page URL
        (no PDF). Still OPEN_ACCESS — HTML is fetchable at M-57."""
        transport = _Transport([
            ("api.crossref.org", 200, _crossref_response()),
            ("api.unpaywall.org", 200, _unpaywall_response(
                is_oa=True, pdf_url=None,
                html_url="https://oa.example/article",
            )),
        ])
        with _client_with_transport(transport) as client:
            row = fetch_frame_entity(_binding(), client=client)

        assert row.provenance_class == ProvenanceClass.OPEN_ACCESS
        assert row.oa_pdf_url == "https://oa.example/article"

    def test_metadata_only_when_no_abstract_no_oa(self) -> None:
        cr_no_abs = _crossref_response(abstract=None)
        transport = _Transport([
            ("api.crossref.org", 200, cr_no_abs),
            ("api.unpaywall.org", 200, _unpaywall_response(is_oa=False)),
            # PubMed returns 200 but empty body
            ("eutils.ncbi.nlm.nih.gov", 200, "   "),
        ])
        with _client_with_transport(transport) as client:
            row = fetch_frame_entity(_binding(), client=client)

        assert row.provenance_class == ProvenanceClass.METADATA_ONLY
        assert row.direct_quote == ""
        assert row.title  # we got metadata
        assert row.year == 2021


class TestOrchestratorDoiConsistencyGuard:
    """V30 Phase-2 run-1 root cause: contract had wrong PMID bound
    to SURPASS-2 (actually SPRINT). NEJM blocked the DOI fetch,
    M-56 fell back to PubMed, PubMed returned SPRINT abstract,
    M-58 extracted wrong-paper content that passed anti-fabrication
    (prose was verbatim in direct_quote). The guard rejects PubMed
    content when its ELocationID DOI does not match the bound DOI.

    Codex M-66 plan review Medium #4: regression coverage on this
    path + the RetrievalAttempt constructor shape for the mismatch
    branch.
    """

    def test_doi_mismatch_rejects_pubmed_abstract(self) -> None:
        """When PubMed returns a DOI different from the bound DOI,
        abstract_pubmed is NOT used. Combined with no crossref
        abstract + no OA, this yields METADATA_ONLY."""
        cr_no_abs = _crossref_response(abstract=None)
        # PubMed XML returns a totally unrelated DOI — simulates
        # the contract having the wrong PMID for the bound DOI.
        pm_wrong = _pubmed_xml(
            abstract="SPRINT prose about blood pressure.",
            title="Final Report of a Trial of Intensive BP Control",
            doi="10.1056/NEJMoa1901281",  # SPRINT's real DOI
        )
        transport = _Transport([
            ("api.crossref.org", 200, cr_no_abs),
            ("api.unpaywall.org", 200, _unpaywall_response(is_oa=False)),
            ("eutils.ncbi.nlm.nih.gov", 200, pm_wrong),
        ])
        with _client_with_transport(transport) as client:
            row = fetch_frame_entity(_binding(), client=client)

        # PubMed abstract MUST NOT leak into direct_quote
        assert "SPRINT" not in (row.direct_quote or "")
        assert "blood pressure" not in (row.direct_quote or "").lower()
        # With no OA and no extractable abstract → METADATA_ONLY
        assert row.provenance_class == ProvenanceClass.METADATA_ONLY
        # Mismatch must be recorded in the attempt log for M-60
        mismatch_attempts = [
            a for a in row.retrieval_attempts
            if "doi_mismatch" in (a.outcome or "")
        ]
        assert len(mismatch_attempts) == 1, (
            f"expected 1 doi_mismatch attempt, got "
            f"{[(a.source, a.outcome) for a in row.retrieval_attempts]}"
        )
        # The RetrievalAttempt constructor must accept the
        # canonical kwargs (source/url/attempt_index/http_status/
        # outcome). If the code ever regressed to the legacy
        # (method/endpoint/status_code/error/duration_ms) shape,
        # this branch would TypeError at runtime.
        a = mismatch_attempts[0]
        assert a.source == "pubmed"
        assert a.http_status is None
        assert "bound=" in a.outcome

    def test_doi_match_accepts_pubmed_abstract(self) -> None:
        """When PubMed's DOI matches the bound DOI, the abstract
        IS used — guard must not break the happy path."""
        cr_no_abs = _crossref_response(abstract=None)
        pm_correct = _pubmed_xml(
            abstract="Tirzepatide reduced HbA1c.",
            doi="10.1056/NEJMoa2107519",  # matches bound DOI
        )
        transport = _Transport([
            ("api.crossref.org", 200, cr_no_abs),
            ("api.unpaywall.org", 200, _unpaywall_response(is_oa=False)),
            ("eutils.ncbi.nlm.nih.gov", 200, pm_correct),
        ])
        with _client_with_transport(transport) as client:
            row = fetch_frame_entity(_binding(), client=client)

        assert row.provenance_class == ProvenanceClass.ABSTRACT_ONLY
        assert "Tirzepatide" in row.direct_quote
        assert row.quote_source == "pubmed_abstract"

    def test_pubmed_without_doi_element_still_works(self) -> None:
        """If the PubMed XML lacks <ELocationID>, we can't verify
        consistency but we can't reject either. Accept the
        abstract (backwards compat with pre-guard behavior)."""
        cr_no_abs = _crossref_response(abstract=None)
        pm_no_doi = _pubmed_xml(abstract="content.", doi=None)
        transport = _Transport([
            ("api.crossref.org", 200, cr_no_abs),
            ("api.unpaywall.org", 200, _unpaywall_response(is_oa=False)),
            ("eutils.ncbi.nlm.nih.gov", 200, pm_no_doi),
        ])
        with _client_with_transport(transport) as client:
            row = fetch_frame_entity(_binding(), client=client)

        assert row.provenance_class == ProvenanceClass.ABSTRACT_ONLY
        assert "content." in row.direct_quote


class TestOrchestratorRegulatoryUrlFetchM66bR:
    """V30 Phase-2 M-66b-R: url_pattern-primary regulatory
    entities (FDA/EMA/NICE/HC) now fetch content via
    AccessBypass (`_fetch_url_pattern`) instead of emitting
    METADATA_ONLY. Codex pass-3 approved test seam is
    `_fetch_url_pattern` (module-level monkeypatch), not
    httpx transport mocking.
    """

    def test_url_pattern_fetch_success_yields_open_access(
        self, monkeypatch,
    ) -> None:
        """Successful AccessBypass fetch produces OPEN_ACCESS
        with the fetched content as direct_quote."""
        from src.polaris_graph.retrieval import frame_fetcher as ff
        stub_content = (
            "MOUNJARO (tirzepatide) injection, for subcutaneous use. "
            "INDICATIONS: adjunct to diet and exercise to improve "
            "glycemic control in adults with T2D. WARNINGS: boxed "
            "warning for thyroid C-cell tumors." * 10
        )
        monkeypatch.setattr(
            ff, "_fetch_url_pattern",
            lambda url: (stub_content, url),
        )

        binding = EvidenceBinding(
            entity_id="fda_mounjaro_label",
            entity_type="regulatory",
            primary_identifier="url:https://www.fda.gov/drugs/mounjaro",
            secondary_identifiers=(),
            rendering_slot="regulatory_fda_t2d",
            required_fields=("indications", "boxed_warning"),
            min_fields_for_completion=2,
        )
        row = ff.fetch_frame_entity(binding)

        assert row.provenance_class == ProvenanceClass.OPEN_ACCESS
        assert row.quote_source == "url_pattern_fetch"
        assert "MOUNJARO" in row.direct_quote
        assert "INDICATIONS" in row.direct_quote
        # Attempt log records the AccessBypass success
        ab_attempts = [
            a for a in row.retrieval_attempts if a.source == "access_bypass"
        ]
        assert len(ab_attempts) == 1
        assert ab_attempts[0].outcome == "success"

    def test_url_pattern_fetch_failure_falls_back_to_metadata_only(
        self, monkeypatch,
    ) -> None:
        """AccessBypass fetch returns empty → METADATA_ONLY, not
        a crash. M-59 surfaces the entity as FAIL_MIN_FIELDS
        (curator-actionable)."""
        from src.polaris_graph.retrieval import frame_fetcher as ff
        monkeypatch.setattr(
            ff, "_fetch_url_pattern",
            lambda url: ("", ""),
        )

        binding = EvidenceBinding(
            entity_id="nice_ta924_t2d",
            entity_type="regulatory",
            primary_identifier=(
                "url:https://www.nice.org.uk/guidance/ta924"
            ),
            secondary_identifiers=(),
            rendering_slot="regulatory_nice_t2d",
            required_fields=("recommendation", "restrictions"),
            min_fields_for_completion=2,
        )
        row = ff.fetch_frame_entity(binding)

        assert row.provenance_class == ProvenanceClass.METADATA_ONLY
        assert row.direct_quote == ""
        # Attempt log records the failure
        ab_attempts = [
            a for a in row.retrieval_attempts if a.source == "access_bypass"
        ]
        assert len(ab_attempts) == 1
        assert "fetch_returned_no_content" in ab_attempts[0].outcome


class TestOrchestratorOaFullTextFetchM66bT:
    """V30 Phase-2 M-66b-T: Unpaywall-surfaced OA URLs now
    trigger an AccessBypass full-text fetch, enriching
    direct_quote from ~500-char abstract to up to 25K chars.
    """

    def test_oa_full_text_fetch_replaces_abstract_when_available(
        self, monkeypatch,
    ) -> None:
        """When OA fetch succeeds, direct_quote is the full text,
        NOT the crossref abstract."""
        from src.polaris_graph.retrieval import frame_fetcher as ff
        full_text = (
            "SURPASS-2 primary results. N=1879 adults with type 2 "
            "diabetes on metformin. Tirzepatide 5, 10, 15 mg vs "
            "semaglutide 1 mg once weekly. Primary endpoint: "
            "change in HbA1c at 40 weeks. ETD vs semaglutide: "
            "-0.15 (95% CI -0.28, -0.03; P=0.02); -0.39 "
            "(-0.51, -0.26; P<0.001); -0.45 (-0.57, -0.32; "
            "P<0.001). Eli Lilly and Company sponsored." * 5
        )
        monkeypatch.setattr(
            ff, "_fetch_url_pattern",
            lambda url: (full_text, url),
        )

        transport = _Transport([
            ("api.crossref.org", 200, _crossref_response()),
            ("api.unpaywall.org", 200,
             _unpaywall_response(is_oa=True, pdf_url="https://x.pdf")),
        ])
        with _client_with_transport(transport) as client:
            row = ff.fetch_frame_entity(_binding(), client=client)

        assert row.provenance_class == ProvenanceClass.OPEN_ACCESS
        # M-66b-T: direct_quote is the full text, not the abstract
        assert row.quote_source == "oa_full_text"
        assert "ETD vs semaglutide" in row.direct_quote
        # Truncated at cap
        assert len(row.direct_quote) <= ff._M66_CONTENT_CAP
        # Attempt log has the access_bypass success entry
        ab_attempts = [
            a for a in row.retrieval_attempts if a.source == "access_bypass"
        ]
        assert len(ab_attempts) == 1
        assert ab_attempts[0].outcome == "success"

    def test_oa_full_text_fetch_failure_falls_back_to_abstract(
        self, monkeypatch,
    ) -> None:
        """When OA fetch returns empty, direct_quote falls back
        to the crossref abstract (backwards-compatible with
        pre-M-66b behavior)."""
        from src.polaris_graph.retrieval import frame_fetcher as ff
        monkeypatch.setattr(
            ff, "_fetch_url_pattern",
            lambda url: ("", ""),
        )

        transport = _Transport([
            ("api.crossref.org", 200, _crossref_response()),
            ("api.unpaywall.org", 200,
             _unpaywall_response(is_oa=True, pdf_url="https://x.pdf")),
        ])
        with _client_with_transport(transport) as client:
            row = ff.fetch_frame_entity(_binding(), client=client)

        assert row.provenance_class == ProvenanceClass.OPEN_ACCESS
        # Fallback to crossref abstract
        assert row.quote_source == "crossref_abstract"
        assert "tirzepatide" in row.direct_quote.lower()

    def test_fetch_url_pattern_truncates_at_cap(
        self, monkeypatch,
    ) -> None:
        """V30 M-66b-T content cap (25K chars) — prevents prompt
        bloat from oversized OA PDFs.

        AccessBypass.fetch_with_bypass is async and returns an
        AccessResult dataclass (url, content, success, ...). Stub
        the class so we hit the async path + result-shape contract.
        """
        import asyncio
        from src.polaris_graph.retrieval import frame_fetcher as ff
        from src.tools.access_bypass import AccessResult

        oversized = "X" * (ff._M66_CONTENT_CAP + 10_000)

        class _StubAB:
            def __init__(self, *_a, **_kw) -> None:
                pass

            async def fetch_with_bypass(
                self, url: str, prefer_legal: bool = True,
            ) -> AccessResult:
                return AccessResult(
                    url=url, content=oversized,
                    access_method="stub",
                    legal_alternative=None,
                    success=True, metadata={},
                )

        monkeypatch.setattr(
            "src.tools.access_bypass.AccessBypass", _StubAB,
        )

        content, final_url = ff._fetch_url_pattern("https://example.com")
        assert len(content) == ff._M66_CONTENT_CAP
        assert final_url == "https://example.com"


class TestOrchestratorFailurePaths:
    def test_all_404_yields_gap(self) -> None:
        transport = _Transport([
            ("api.crossref.org", 404, {"message": "not found"}),
            ("api.unpaywall.org", 404, {"message": "not found"}),
            ("eutils.ncbi.nlm.nih.gov", 200, ""),
        ])
        with _client_with_transport(transport) as client:
            row = fetch_frame_entity(_binding(), client=client)

        assert row.provenance_class == ProvenanceClass.FRAME_GAP_UNRECOVERABLE
        assert row.failure_reason is not None
        assert "all sources failed" in row.failure_reason
        # Gap row still retains identifiers + attempts log
        assert row.doi == "10.1056/NEJMoa2107519"
        assert len(row.retrieval_attempts) >= 2

    def test_anchor_only_binding_yields_gap_without_network(self) -> None:
        binding = _binding(
            primary="anchor:SURPASS-CVOT",
            secondaries=(),
        )
        transport = _Transport([])
        with _client_with_transport(transport) as client:
            row = fetch_frame_entity(binding, client=client)

        assert row.provenance_class == ProvenanceClass.FRAME_GAP_UNRECOVERABLE
        assert row.retrieval_attempts == ()
        assert "anchor-only" in row.failure_reason
        # No network call fired
        assert transport.call_log == []

    def test_pmid_only_uses_pubmed(self) -> None:
        """PMID-only binding skips CrossRef + Unpaywall entirely."""
        binding = _binding(
            primary="pmid:34010531",
            secondaries=(),
        )
        transport = _Transport([
            ("eutils.ncbi.nlm.nih.gov", 200, _pubmed_xml()),
        ])
        with _client_with_transport(transport) as client:
            row = fetch_frame_entity(binding, client=client)

        assert row.provenance_class == ProvenanceClass.ABSTRACT_ONLY
        assert row.quote_source == "pubmed_abstract"
        assert row.pmid == "34010531"
        # No CrossRef or Unpaywall calls fired
        assert not any(
            "crossref" in u or "unpaywall" in u
            for u in transport.call_log
        )


class TestOrchestratorRegulatoryPath:
    def test_url_pattern_primary_yields_metadata_only_when_fetch_empty(
        self, monkeypatch,
    ) -> None:
        """V30 Phase-2 M-66b-R: url-pattern entities now route
        through `_fetch_url_pattern` (AccessBypass). When the
        fetch returns empty, METADATA_ONLY is preserved
        (backwards-compat with pre-M-66b)."""
        from src.polaris_graph.retrieval import frame_fetcher as ff
        monkeypatch.setattr(
            ff, "_fetch_url_pattern", lambda url: ("", ""),
        )
        binding = EvidenceBinding(
            entity_id="fda_mounjaro_label",
            entity_type="regulatory",
            primary_identifier="url:https://www.accessdata.fda.gov/.../mounjaro",
            secondary_identifiers=(),
            rendering_slot="regulatory_fda_t2d",
            required_fields=("indications", "boxed_warning"),
            min_fields_for_completion=2,
        )
        transport = _Transport([])
        with _client_with_transport(transport) as client:
            row = fetch_frame_entity(binding, client=client)

        assert row.provenance_class == ProvenanceClass.METADATA_ONLY
        assert "accessdata.fda.gov" in (row.url or "")
        assert row.quote_source == "url_pattern_placeholder"
        # No CrossRef/Unpaywall/PubMed network fired (regulatory
        # has no DOI/PMID; only AccessBypass is consulted, which
        # is mocked here)
        assert transport.call_log == []


# ─────────────────────────────────────────────────────────────────────
# (4) Retrieval attempt logging
# ─────────────────────────────────────────────────────────────────────
class TestRetryOnTransient:
    """Retry schedule is fixed-deterministic per docstring: 1s/2s/4s
    backoff. To keep tests fast we monkeypatch time.sleep to a no-op
    and check that 503 followed by 200 eventually succeeds."""

    def test_transient_503_then_200_succeeds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "src.polaris_graph.retrieval.frame_fetcher.time.sleep",
            lambda s: None,
        )
        transport = _SequencedTransport({
            "api.crossref.org": [
                (503, {"error": "service unavailable"}),
                (200, _crossref_response()),
            ],
            "api.unpaywall.org": [
                (200, _unpaywall_response(is_oa=False)),
            ],
        })
        client = httpx.Client(
            transport=httpx.MockTransport(transport),
            timeout=5.0,
        )
        try:
            row = fetch_frame_entity(
                _binding(primary="doi:10.1/x", secondaries=()),
                client=client,
            )
        finally:
            client.close()

        assert row.provenance_class == ProvenanceClass.ABSTRACT_ONLY
        # CrossRef retried: substring 'api.crossref.org' appeared >=2
        cr_calls = [u for u in transport.call_log if "crossref.org" in u]
        assert len(cr_calls) >= 2

        # Codex M-56 Blocker 2 fix: retry chain is visible as
        # separate attempts, NOT collapsed into one summary record.
        cr_attempts = [
            a for a in row.retrieval_attempts if a.source == "crossref"
        ]
        assert len(cr_attempts) == 2
        assert cr_attempts[0].attempt_index == 1
        assert cr_attempts[0].outcome == "retryable_http_503"
        assert cr_attempts[1].attempt_index == 2
        assert cr_attempts[1].outcome == "success"

    def test_exhausted_retries_emits_error_outcome(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "src.polaris_graph.retrieval.frame_fetcher.time.sleep",
            lambda s: None,
        )
        # Always 503 → should exhaust retries and log error
        transport = _Transport([
            ("api.crossref.org", 503, {"error": "x"}),
            ("api.unpaywall.org", 503, {"error": "x"}),
            ("eutils.ncbi.nlm.nih.gov", 503, ""),
        ])
        with _client_with_transport(transport) as client:
            row = fetch_frame_entity(_binding(), client=client)

        assert row.provenance_class == ProvenanceClass.FRAME_GAP_UNRECOVERABLE
        # Codex M-56 audit Blocker 2 fix: full retry chain visible
        # as one RetrievalAttempt per HTTP request. 3 attempts per
        # source × 2 sources (crossref + unpaywall; pubmed not
        # called because crossref/unpaywall already failed for this
        # binding with pmid) = at least 6 entries.
        for a in row.retrieval_attempts:
            assert (
                a.outcome.startswith("error:")
                or a.outcome.startswith("retryable_")
                or a.outcome == "not_found"
            )
        # Each source should have 3 attempts (max_retries)
        cr_attempts = [a for a in row.retrieval_attempts if a.source == "crossref"]
        assert len(cr_attempts) == 3
        assert [a.attempt_index for a in cr_attempts] == [1, 2, 3]
        # First 2 retryable, last terminal error
        assert cr_attempts[0].outcome == "retryable_http_503"
        assert cr_attempts[1].outcome == "retryable_http_503"
        assert cr_attempts[2].outcome == "error:http_503"


class TestAttemptURLQueryParams:
    """Codex M-56 audit Blocker 2 fix: logged URL for PubMed and
    Unpaywall must include the query params the retriever actually
    sent, so M-60 manifest can reconstruct the exact HTTP line."""

    def test_pubmed_attempt_url_includes_pmid_and_params(self) -> None:
        binding = _binding(
            primary="pmid:34010531",
            secondaries=(),
        )
        transport = _Transport([
            ("eutils.ncbi.nlm.nih.gov", 200, _pubmed_xml()),
        ])
        with _client_with_transport(transport) as client:
            row = fetch_frame_entity(binding, client=client)

        pm_attempts = [
            a for a in row.retrieval_attempts if a.source == "pubmed"
        ]
        assert len(pm_attempts) == 1
        url = pm_attempts[0].url
        assert "id=34010531" in url
        assert "db=pubmed" in url
        assert "rettype=abstract" in url
        assert "retmode=xml" in url

    def test_unpaywall_attempt_url_includes_email(self) -> None:
        transport = _Transport([
            ("api.crossref.org", 200, _crossref_response()),
            ("api.unpaywall.org", 200, _unpaywall_response(is_oa=False)),
        ])
        with _client_with_transport(transport) as client:
            row = fetch_frame_entity(
                _binding(primary="doi:10.1/x", secondaries=()),
                client=client,
            )

        up_attempts = [
            a for a in row.retrieval_attempts if a.source == "unpaywall"
        ]
        assert len(up_attempts) == 1
        assert "email=" in up_attempts[0].url


class TestRetrievalAttemptLog:
    def test_success_logged(self) -> None:
        transport = _Transport([
            ("api.crossref.org", 200, _crossref_response()),
            ("api.unpaywall.org", 200,
             _unpaywall_response(is_oa=True, pdf_url="https://x.pdf")),
        ])
        with _client_with_transport(transport) as client:
            row = fetch_frame_entity(_binding(), client=client)

        sources = {a.source for a in row.retrieval_attempts}
        assert {"crossref", "unpaywall"} <= sources
        # V30 Phase-2 M-66b-T: the OA full-text fetch adds an
        # access_bypass RetrievalAttempt that can be success OR
        # failure depending on whether the test stubs
        # _fetch_url_pattern. Filter to http-network attempts
        # (crossref, unpaywall, pubmed) for the 200-success check.
        http_sources = {"crossref", "unpaywall", "pubmed"}
        for a in row.retrieval_attempts:
            assert isinstance(a, RetrievalAttempt)
            if a.source in http_sources:
                assert a.http_status == 200
                assert a.outcome == "success"
                assert a.attempt_index == 1  # no retry on 200
        # Timings only emitted for http sources; access_bypass
        # attempts don't produce RetrievalTiming entries (M-66b-T
        # doesn't instrument AccessBypass internals).
        http_attempts = [
            a for a in row.retrieval_attempts if a.source in http_sources
        ]
        assert len(row.retrieval_timings) == len(http_attempts)
        for t in row.retrieval_timings:
            assert isinstance(t, RetrievalTiming)
            assert t.duration_ms >= 0

    def test_404_logged_as_not_found(self) -> None:
        transport = _Transport([
            ("api.crossref.org", 404, {"error": "not_found"}),
            ("api.unpaywall.org", 404, {"error": "not_found"}),
            ("eutils.ncbi.nlm.nih.gov", 404, ""),
        ])
        with _client_with_transport(transport) as client:
            row = fetch_frame_entity(_binding(), client=client)

        for a in row.retrieval_attempts:
            assert a.http_status == 404
            assert a.outcome == "not_found"


# ─────────────────────────────────────────────────────────────────────
# (5) Determinism
# ─────────────────────────────────────────────────────────────────────
class TestDeterminism:
    """Codex M-56 audit Blocker 1 fix: FrameRow payload (including
    retrieval_attempts) is now deterministic. Wall-clock duration
    lives in the separate retrieval_timings tuple, NOT compared."""

    def test_same_inputs_yield_byte_identical_payload(self) -> None:
        rules = [
            ("api.crossref.org", 200, _crossref_response()),
            ("api.unpaywall.org", 200,
             _unpaywall_response(is_oa=True, pdf_url="https://x.pdf")),
        ]
        t1 = _Transport(list(rules))
        t2 = _Transport(list(rules))
        with _client_with_transport(t1) as c1, _client_with_transport(t2) as c2:
            r1 = fetch_frame_entity(_binding(), client=c1)
            r2 = fetch_frame_entity(_binding(), client=c2)

        # Strong determinism claim: every payload field matches.
        # retrieval_attempts contains NO wall-clock data now and so
        # must compare equal in full.
        assert r1.entity_id == r2.entity_id
        assert r1.entity_type == r2.entity_type
        assert r1.rendering_slot == r2.rendering_slot
        assert r1.provenance_class == r2.provenance_class
        assert r1.direct_quote == r2.direct_quote
        assert r1.quote_source == r2.quote_source
        assert r1.doi == r2.doi and r1.pmid == r2.pmid
        assert r1.title == r2.title
        assert r1.authors == r2.authors
        assert r1.journal == r2.journal
        assert r1.year == r2.year
        assert r1.oa_pdf_url == r2.oa_pdf_url
        assert r1.failure_reason == r2.failure_reason
        # Byte-identical attempt log
        assert r1.retrieval_attempts == r2.retrieval_attempts
        # Timings have same shape but duration_ms may differ
        assert len(r1.retrieval_timings) == len(r2.retrieval_timings)
        for t1m, t2m in zip(r1.retrieval_timings, r2.retrieval_timings):
            assert t1m.source == t2m.source
            assert t1m.attempt_index == t2m.attempt_index

    def test_frame_row_without_timings_fully_comparable(self) -> None:
        """Additional Blocker 1 proof: a FrameRow variant with
        retrieval_timings zeroed must be structurally equal across
        runs — the determinism guarantee surfaces as direct equality
        once the non-deterministic tuple is stripped."""
        rules = [
            ("api.crossref.org", 200, _crossref_response()),
            ("api.unpaywall.org", 200, _unpaywall_response(is_oa=False)),
        ]
        t1 = _Transport(list(rules))
        t2 = _Transport(list(rules))
        with _client_with_transport(t1) as c1, _client_with_transport(t2) as c2:
            r1 = fetch_frame_entity(_binding(), client=c1)
            r2 = fetch_frame_entity(_binding(), client=c2)

        # Compare by constructing dict without retrieval_timings
        from dataclasses import replace
        r1_comparable = replace(r1, retrieval_timings=())
        r2_comparable = replace(r2, retrieval_timings=())
        assert r1_comparable == r2_comparable


# ─────────────────────────────────────────────────────────────────────
# (6) fetch_compiled_frame batch mode
# ─────────────────────────────────────────────────────────────────────
class TestCompiledFrameFetch:
    def test_preserves_binding_order(self) -> None:
        bindings = (
            _binding(entity_id="e1", primary="doi:10.1/a"),
            _binding(entity_id="e2", primary="doi:10.1/b"),
            _binding(entity_id="e3", primary="doi:10.1/c"),
        )
        transport = _Transport([
            ("api.crossref.org", 200, _crossref_response()),
            ("api.unpaywall.org", 200, _unpaywall_response(is_oa=False)),
        ])
        with _client_with_transport(transport) as client:
            rows = fetch_compiled_frame(bindings, client=client)

        assert tuple(r.entity_id for r in rows) == ("e1", "e2", "e3")
        assert all(
            r.provenance_class == ProvenanceClass.ABSTRACT_ONLY
            for r in rows
        )


# ─────────────────────────────────────────────────────────────────────
# (7) Failure summary composition
# ─────────────────────────────────────────────────────────────────────
class TestFailureSummary:
    def test_empty_attempts(self) -> None:
        assert "no retrieval" in _summarize_failure([])

    def test_composed(self) -> None:
        attempts = [
            RetrievalAttempt(
                source="crossref", url="url1", attempt_index=1,
                http_status=404, outcome="not_found",
            ),
            RetrievalAttempt(
                source="unpaywall", url="url2", attempt_index=1,
                http_status=500, outcome="error:http_500",
            ),
        ]
        summary = _summarize_failure(attempts)
        assert "crossref" in summary and "unpaywall" in summary
        assert "404" in summary and "500" in summary


# ─────────────────────────────────────────────────────────────────────
# (8) FrameRow contract
# ─────────────────────────────────────────────────────────────────────
class TestFrameRowContract:
    def test_is_gap_true_only_for_unrecoverable(self) -> None:
        row = FrameRow(
            entity_id="x", entity_type="t", rendering_slot="s",
            provenance_class=ProvenanceClass.FRAME_GAP_UNRECOVERABLE,
            direct_quote="", quote_source="none",
            doi=None, pmid=None, oa_pdf_url=None, url=None,
            title=None, authors=(), journal=None, year=None,
            failure_reason="test", retrieval_attempts=(),
        )
        assert row.is_gap() is True

        row2 = FrameRow(
            entity_id="x", entity_type="t", rendering_slot="s",
            provenance_class=ProvenanceClass.ABSTRACT_ONLY,
            direct_quote="stuff", quote_source="crossref_abstract",
            doi="10.1/x", pmid=None, oa_pdf_url=None, url=None,
            title="T", authors=(), journal="J", year=2024,
            failure_reason=None, retrieval_attempts=(),
        )
        assert row2.is_gap() is False

    def test_frame_row_is_frozen(self) -> None:
        row = FrameRow(
            entity_id="x", entity_type="t", rendering_slot="s",
            provenance_class=ProvenanceClass.ABSTRACT_ONLY,
            direct_quote="", quote_source="none",
            doi=None, pmid=None, oa_pdf_url=None, url=None,
            title=None, authors=(), journal=None, year=None,
            failure_reason=None, retrieval_attempts=(),
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            row.entity_id = "changed"  # type: ignore


# ─────────────────────────────────────────────────────────────────────
# (8) OpenAlex abstract fallback (issue #1033)
# ─────────────────────────────────────────────────────────────────────
def _openalex_response(
    *,
    doi: str = "10.1056/NEJMoa2107519",
    sentence: str = "Tirzepatide reduced HbA1c substantially in adults",
    title: str = "Tirzepatide versus Semaglutide Once Weekly",
    journal: str = "New England Journal of Medicine",
    year: int = 2021,
) -> dict[str, Any]:
    """Minimal OpenAlex /works/{doi} object with an
    abstract_inverted_index reconstructed from `sentence`."""
    inv: dict[str, list[int]] = {}
    for i, word in enumerate(sentence.split()):
        inv.setdefault(word, []).append(i)
    return {
        "doi": f"https://doi.org/{doi}",
        "title": title,
        "display_name": title,
        "publication_year": year,
        "authorships": [
            {"author": {"display_name": "Frias Juan P."}},
        ],
        "primary_location": {"source": {"display_name": journal}},
        "abstract_inverted_index": inv,
    }


class TestOpenAlexParser:
    def test_reconstruct_orders_by_position(self) -> None:
        from src.polaris_graph.retrieval.frame_fetcher import (
            _reconstruct_inverted_abstract,
        )
        # positions: 0 hello, 1 world, 2 again, 3 then, 4 again
        inv = {"world": [1], "hello": [0], "again": [2, 4], "then": [3]}
        assert (
            _reconstruct_inverted_abstract(inv)
            == "hello world again then again"
        )

    def test_reconstruct_empty_or_bad_returns_none(self) -> None:
        from src.polaris_graph.retrieval.frame_fetcher import (
            _reconstruct_inverted_abstract,
        )
        assert _reconstruct_inverted_abstract({}) is None
        assert _reconstruct_inverted_abstract(None) is None
        assert _reconstruct_inverted_abstract("not a dict") is None

    def test_parse_openalex_response_extracts_fields(self) -> None:
        from src.polaris_graph.retrieval.frame_fetcher import (
            _parse_openalex_response,
        )
        parsed = _parse_openalex_response(_openalex_response())
        assert parsed["doi"] == "10.1056/nejmoa2107519"
        assert "Tirzepatide" in parsed["abstract"]
        assert parsed["year"] == 2021
        assert parsed["journal"] == "New England Journal of Medicine"


class TestOpenAlexFallback:
    def test_fills_abstract_when_crossref_empty_and_no_pubmed(self) -> None:
        """The Q72 root case: CrossRef has metadata but no abstract,
        no OA, no PMID. OpenAlex's inverted-index abstract rescues the
        slot from 'not extractable' (METADATA_ONLY) to ABSTRACT_ONLY."""
        cr_no_abs = _crossref_response(abstract=None)
        transport = _Transport([
            ("api.crossref.org", 200, cr_no_abs),
            ("api.unpaywall.org", 200, _unpaywall_response(is_oa=False)),
            ("api.openalex.org", 200, _openalex_response()),
        ])
        with _client_with_transport(transport) as client:
            row = fetch_frame_entity(
                _binding(
                    primary="doi:10.1056/NEJMoa2107519", secondaries=()
                ),
                client=client,
            )
        assert row.provenance_class == ProvenanceClass.ABSTRACT_ONLY
        assert row.quote_source == "openalex_abstract"
        assert "Tirzepatide" in row.direct_quote
        assert "reduced HbA1c" in row.direct_quote  # ordering preserved
        assert any(
            "openalex" in a.source for a in row.retrieval_attempts
        )

    def test_doi_mismatch_rejected_falls_to_metadata_only(self) -> None:
        """OpenAlex returns a DIFFERENT DOI -> content rejected (we must
        not extract from the wrong work) -> METADATA_ONLY, mismatch
        logged. Mirrors the PubMed DOI-consistency guard."""
        cr_no_abs = _crossref_response(abstract=None)
        transport = _Transport([
            ("api.crossref.org", 200, cr_no_abs),
            ("api.unpaywall.org", 200, _unpaywall_response(is_oa=False)),
            ("api.openalex.org", 200,
             _openalex_response(doi="10.9999/WRONG.PAPER")),
        ])
        with _client_with_transport(transport) as client:
            row = fetch_frame_entity(
                _binding(
                    primary="doi:10.1056/NEJMoa2107519", secondaries=()
                ),
                client=client,
            )
        assert row.provenance_class == ProvenanceClass.METADATA_ONLY
        assert row.direct_quote == ""
        assert any(
            "doi_mismatch" in a.outcome for a in row.retrieval_attempts
        )

    def test_oa_locator_but_paywalled_fulltext_openalex_rescues(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Exact Q72 path: Unpaywall surfaces an OA locator, but the
        PDF 403s (full-text fetch returns nothing). Without OpenAlex
        the row was OPEN_ACCESS with an EMPTY quote -> 'not extractable'.
        OpenAlex abstract now fills direct_quote."""
        monkeypatch.setattr(
            "src.polaris_graph.retrieval.frame_fetcher._fetch_url_pattern",
            lambda url: ("", ""),
        )
        cr_no_abs = _crossref_response(abstract=None)
        transport = _Transport([
            ("api.crossref.org", 200, cr_no_abs),
            ("api.unpaywall.org", 200, _unpaywall_response(
                is_oa=True,
                pdf_url="https://paywalled.example/article.pdf")),
            ("api.openalex.org", 200, _openalex_response()),
        ])
        with _client_with_transport(transport) as client:
            row = fetch_frame_entity(
                _binding(
                    primary="doi:10.1056/NEJMoa2107519", secondaries=()
                ),
                client=client,
            )
        assert row.provenance_class == ProvenanceClass.OPEN_ACCESS
        assert row.quote_source == "openalex_abstract"
        assert "Tirzepatide" in row.direct_quote

    def test_crossref_abstract_present_skips_openalex(self) -> None:
        """When CrossRef already has an abstract, OpenAlex must NOT be
        called (priority + no wasted request)."""
        transport = _Transport([
            ("api.crossref.org", 200, _crossref_response()),
            ("api.unpaywall.org", 200, _unpaywall_response(is_oa=False)),
            ("api.openalex.org", 200, _openalex_response()),
        ])
        with _client_with_transport(transport) as client:
            row = fetch_frame_entity(
                _binding(
                    primary="doi:10.1056/NEJMoa2107519", secondaries=()
                ),
                client=client,
            )
        assert row.quote_source == "crossref_abstract"
        assert not any("openalex" in u for u in transport.call_log)

    def test_disabled_flag_skips_openalex(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """PG_OPENALEX_FRAME_FALLBACK=0 disables the fallback ->
        METADATA_ONLY, no OpenAlex request."""
        monkeypatch.setattr(
            "src.polaris_graph.retrieval.frame_fetcher."
            "_OPENALEX_FRAME_FALLBACK_ENABLED",
            False,
        )
        cr_no_abs = _crossref_response(abstract=None)
        transport = _Transport([
            ("api.crossref.org", 200, cr_no_abs),
            ("api.unpaywall.org", 200, _unpaywall_response(is_oa=False)),
            ("api.openalex.org", 200, _openalex_response()),
        ])
        with _client_with_transport(transport) as client:
            row = fetch_frame_entity(
                _binding(
                    primary="doi:10.1056/NEJMoa2107519", secondaries=()
                ),
                client=client,
            )
        assert row.provenance_class == ProvenanceClass.METADATA_ONLY
        assert not any("openalex" in u for u in transport.call_log)


# ─────────────────────────────────────────────────────────────────────
# (9) Thin oa_full_text stub must not block OpenAlex (issue #1034)
# ─────────────────────────────────────────────────────────────────────
_LONG_OPENALEX_SENTENCE = "Tirzepatide " + " ".join(
    f"finding{i}" for i in range(220)
)  # ~2000 chars >> a 540-char stub and >> the 1200 full-text threshold


class TestOpenAlexThinStubRichest:
    def test_pick_richest_longest_wins_ties_keep_priority(self) -> None:
        from src.polaris_graph.retrieval.frame_fetcher import (
            _pick_richest_abstract,
        )
        # OpenAlex longest -> wins despite CrossRef higher priority.
        t, s = _pick_richest_abstract(
            crossref="short", openalex="x" * 50, pubmed=None,
        )
        assert s == "openalex_abstract" and t == "x" * 50
        # Equal length -> CrossRef (higher priority) wins.
        t, s = _pick_richest_abstract(
            crossref="abcd", openalex="wxyz", pubmed=None,
        )
        assert s == "crossref_abstract"
        # Only a thin partial full-text present -> it is used last-resort.
        t, s = _pick_richest_abstract(
            crossref=None, openalex=None, pubmed=None,
            partial_full_text="stub",
        )
        assert s == "oa_full_text_partial"
        # All empty.
        assert _pick_richest_abstract(
            crossref=None, openalex=None, pubmed=None,
        ) == ("", "none")

    def test_thin_oa_fulltext_stub_does_not_block_openalex(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """THE #1034 BUG: aeaweb PDF 403s but Jina returns a ~540-char
        stub. The stub must NOT block OpenAlex; the richer OpenAlex
        abstract (>=1200) must win, not the stub."""
        stub = "X" * 540  # below _OA_FULLTEXT_MIN_CHARS (1200)
        monkeypatch.setattr(
            "src.polaris_graph.retrieval.frame_fetcher._fetch_url_pattern",
            lambda url: (stub, url),
        )
        cr_no_abs = _crossref_response(abstract=None)
        transport = _Transport([
            ("api.crossref.org", 200, cr_no_abs),
            ("api.unpaywall.org", 200, _unpaywall_response(
                is_oa=True,
                pdf_url="https://www.aeaweb.org/articles/pdf/x.pdf")),
            ("api.openalex.org", 200,
             _openalex_response(sentence=_LONG_OPENALEX_SENTENCE)),
        ])
        with _client_with_transport(transport) as client:
            row = fetch_frame_entity(
                _binding(
                    primary="doi:10.1056/NEJMoa2107519", secondaries=()
                ),
                client=client,
            )
        assert row.provenance_class == ProvenanceClass.OPEN_ACCESS
        assert row.quote_source == "openalex_abstract"  # NOT the stub
        assert "finding200" in row.direct_quote
        assert "XXXX" not in row.direct_quote  # the stub did not win
        assert len(row.direct_quote) > 540
        assert any(
            "openalex" in a.source for a in row.retrieval_attempts
        )

    def test_real_long_fulltext_still_preferred_over_openalex(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A genuine long OA full text (>= threshold) still wins; the
        thin-stub guard must not demote real full text."""
        real = "Genuine full text. " * 120  # ~2280 chars >= 1200
        monkeypatch.setattr(
            "src.polaris_graph.retrieval.frame_fetcher._fetch_url_pattern",
            lambda url: (real, url),
        )
        cr_no_abs = _crossref_response(abstract=None)
        transport = _Transport([
            ("api.crossref.org", 200, cr_no_abs),
            ("api.unpaywall.org", 200, _unpaywall_response(
                is_oa=True, pdf_url="https://oa.example/real.pdf")),
            ("api.openalex.org", 200,
             _openalex_response(sentence=_LONG_OPENALEX_SENTENCE)),
        ])
        with _client_with_transport(transport) as client:
            row = fetch_frame_entity(
                _binding(
                    primary="doi:10.1056/NEJMoa2107519", secondaries=()
                ),
                client=client,
            )
        assert row.provenance_class == ProvenanceClass.OPEN_ACCESS
        assert row.quote_source == "oa_full_text"
        assert "Genuine full text" in row.direct_quote
        # OpenAlex not even called (real full text resolved first).
        assert not any("openalex" in u for u in transport.call_log)
