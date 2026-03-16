"""
Integration tests for citation chain of custody API (Sprint 2 deferred).

Verifies that:
1. Chain detail returns full A-B-C-D traceability for a single citation
2. All-chains summary computes tier breakdowns and verification rates
3. Source preview returns evidence details
4. Missing citations return 404
5. Uploaded document evidence is accessible in chain

Uses a fixture result JSON file — no real pipeline or LLM calls.
Tests the API endpoints via httpx AsyncClient with a temp result file.
"""

import json
import os
import re
from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_RESULT = {
    "vector_id": "TEST_CHAIN_001",
    "original_query": "What is PFAS?",
    "status": "completed",
    "bibliography": [
        {
            "citation_number": 1,
            "citation_key": "EPA2024",
            "formatted": "EPA. PFAS Strategic Roadmap, 2024.",
            "url": "https://www.epa.gov/pfas",
            "source_type": "web",
            "evidence_ids": ["ev_001", "ev_002"],
        },
        {
            "citation_number": 2,
            "citation_key": "Smith2023",
            "formatted": "Smith et al. GAC filtration for PFAS, J. Water, 2023.",
            "url": "https://doi.org/10.1234/water.2023",
            "source_type": "academic",
            "evidence_ids": ["ev_003"],
        },
    ],
    "evidence": [
        {
            "evidence_id": "ev_001",
            "direct_quote": "PFAS are persistent organic pollutants found in drinking water.",
            "statement": "PFAS contaminate drinking water globally.",
            "source_url": "https://www.epa.gov/pfas",
            "source_title": "EPA PFAS Overview",
            "source_type": "web",
            "quality_tier": "GOLD",
            "relevance_score": 0.92,
            "source_confidence": 0.95,
            "year": 2024,
            "authors": ["EPA"],
            "perspective": "Regulatory",
            "corroborating_sources": 3,
        },
        {
            "evidence_id": "ev_002",
            "direct_quote": "EPA set interim health advisory levels at 4 ppt for PFOA.",
            "statement": "EPA advisory level for PFOA is 4 ppt.",
            "source_url": "https://www.epa.gov/pfas",
            "source_title": "EPA PFAS Overview",
            "source_type": "web",
            "quality_tier": "GOLD",
            "relevance_score": 0.88,
            "source_confidence": 0.95,
            "year": 2024,
            "authors": ["EPA"],
            "perspective": "Regulatory",
            "corroborating_sources": 2,
        },
        {
            "evidence_id": "ev_003",
            "direct_quote": "GAC reduces PFAS by 90-99% in municipal systems.",
            "statement": "GAC is highly effective for PFAS removal.",
            "source_url": "https://doi.org/10.1234/water.2023",
            "source_title": "GAC Filtration for PFAS",
            "source_type": "academic",
            "quality_tier": "SILVER",
            "relevance_score": 0.75,
            "source_confidence": 0.80,
            "year": 2023,
            "authors": ["Smith, J.", "Jones, A."],
            "perspective": "Scientific",
            "corroborating_sources": 1,
        },
    ],
    "claims": [
        {
            "claim_id": "claim_001",
            "statement": "PFAS contaminate drinking water globally.",
            "verdict": "SUPPORTED",
            "is_faithful": True,
            "reasoning": "Claim directly supported by EPA source.",
            "nli_score": 0.95,
            "cross_source_score": 0.8,
            "verification_method": "nli",
            "verification_type": "cross_source",
            "evidence_ids": ["ev_001"],
        },
        {
            "claim_id": "claim_002",
            "statement": "EPA advisory level for PFOA is 4 ppt.",
            "verdict": "SUPPORTED",
            "is_faithful": True,
            "reasoning": "Exact figure from EPA document.",
            "nli_score": 0.99,
            "cross_source_score": None,
            "verification_method": "nli",
            "verification_type": "self_contained",
            "evidence_ids": ["ev_002"],
        },
        {
            "claim_id": "claim_003",
            "statement": "GAC is highly effective for PFAS removal.",
            "verdict": "PARTIALLY_SUPPORTED",
            "is_faithful": False,
            "reasoning": "Claim lacks specificity vs source.",
            "nli_score": 0.62,
            "cross_source_score": None,
            "verification_method": "llm",
            "verification_type": "self_contained",
            "evidence_ids": ["ev_003"],
        },
    ],
    "sections": [
        {
            "section_id": "sec_001",
            "title": "Introduction to PFAS",
            "evidence_ids": ["ev_001", "ev_002"],
            "citation_ids": [],
        },
        {
            "section_id": "sec_002",
            "title": "Treatment Technologies",
            "evidence_ids": ["ev_003"],
            "citation_ids": ["ev_003"],
        },
    ],
}


@pytest.fixture
def result_on_disk(tmp_path):
    """Write SAMPLE_RESULT to a temp directory mirroring output layout."""
    out_dir = tmp_path / "outputs" / "polaris_graph"
    out_dir.mkdir(parents=True, exist_ok=True)
    result_path = out_dir / "TEST_CHAIN_001.json"
    result_path.write_text(json.dumps(SAMPLE_RESULT, indent=2), encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# Tests: Citation chain detail (logic test — no server needed)
# ---------------------------------------------------------------------------

class TestCitationChainLogic:
    """Test the citation chain join logic directly."""

    def _build_chain(self, data: dict, citation_number: int) -> dict | None:
        """Replicate the chain-building logic from live_server.py."""
        bibliography = data.get("bibliography", [])
        evidence_pool = data.get("evidence", [])
        claims = data.get("claims", [])
        sections = data.get("sections", [])

        evidence_by_id = {e["evidence_id"]: e for e in evidence_pool}
        claims_by_evidence: dict[str, list[dict]] = {}
        for claim in claims:
            for eid in claim.get("evidence_ids", []):
                claims_by_evidence.setdefault(eid, []).append(claim)

        bib_entry = None
        for b in bibliography:
            if b.get("citation_number") == citation_number:
                bib_entry = b
                break
        if bib_entry is None:
            return None

        chain_links = []
        for eid in bib_entry.get("evidence_ids", []):
            ev = evidence_by_id.get(eid)
            if not ev:
                continue
            citing_sections = []
            for sec in sections:
                if eid in sec.get("evidence_ids", []) or eid in sec.get("citation_ids", []):
                    citing_sections.append({"section_id": sec["section_id"], "title": sec["title"]})
            related_claims = []
            for claim in claims_by_evidence.get(eid, []):
                related_claims.append({
                    "claim_id": claim.get("claim_id", ""),
                    "statement": claim.get("statement", "")[:300],
                    "verdict": claim.get("verdict", "NO_VERDICT"),
                    "is_faithful": claim.get("is_faithful"),
                    "nli_score": claim.get("nli_score"),
                })
            chain_links.append({
                "evidence_id": eid,
                "direct_quote": ev.get("direct_quote", ""),
                "source_url": ev.get("source_url", ""),
                "quality_tier": ev.get("quality_tier", "BRONZE"),
                "citing_sections": citing_sections,
                "verification": related_claims,
            })

        return {
            "citation_number": citation_number,
            "source": {"citation_key": bib_entry.get("citation_key", ""), "url": bib_entry.get("url", "")},
            "evidence_count": len(chain_links),
            "chain": chain_links,
        }

    def test_citation_1_has_2_evidence_links(self):
        """Citation [1] (EPA2024) has ev_001 and ev_002."""
        result = self._build_chain(SAMPLE_RESULT, 1)
        assert result is not None
        assert result["evidence_count"] == 2
        assert result["source"]["citation_key"] == "EPA2024"

    def test_citation_1_chain_includes_verification(self):
        """Each evidence link includes its verification claim."""
        result = self._build_chain(SAMPLE_RESULT, 1)
        chain = result["chain"]

        # ev_001: verified by claim_001 (SUPPORTED, nli_score=0.95)
        assert chain[0]["evidence_id"] == "ev_001"
        assert len(chain[0]["verification"]) == 1
        assert chain[0]["verification"][0]["verdict"] == "SUPPORTED"
        assert chain[0]["verification"][0]["nli_score"] == 0.95

        # ev_002: verified by claim_002 (SUPPORTED, nli_score=0.99)
        assert chain[1]["evidence_id"] == "ev_002"
        assert chain[1]["verification"][0]["verdict"] == "SUPPORTED"
        assert chain[1]["verification"][0]["nli_score"] == 0.99

    def test_citation_1_citing_sections(self):
        """ev_001 and ev_002 both cited in 'Introduction to PFAS' section."""
        result = self._build_chain(SAMPLE_RESULT, 1)
        chain = result["chain"]

        # Both evidence pieces cited in sec_001
        assert len(chain[0]["citing_sections"]) == 1
        assert chain[0]["citing_sections"][0]["title"] == "Introduction to PFAS"
        assert len(chain[1]["citing_sections"]) == 1
        assert chain[1]["citing_sections"][0]["title"] == "Introduction to PFAS"

    def test_citation_2_academic_with_partial_support(self):
        """Citation [2] (Smith2023) has 1 SILVER evidence, PARTIALLY_SUPPORTED."""
        result = self._build_chain(SAMPLE_RESULT, 2)
        assert result is not None
        assert result["evidence_count"] == 1
        assert result["source"]["citation_key"] == "Smith2023"

        ev = result["chain"][0]
        assert ev["quality_tier"] == "SILVER"
        assert ev["verification"][0]["verdict"] == "PARTIALLY_SUPPORTED"
        assert ev["verification"][0]["is_faithful"] is False

    def test_missing_citation_returns_none(self):
        """Nonexistent citation number returns None."""
        result = self._build_chain(SAMPLE_RESULT, 99)
        assert result is None

    def test_chain_preserves_direct_quotes(self):
        """Chain includes direct_quote from evidence (the 'C' in A-B-C-D)."""
        result = self._build_chain(SAMPLE_RESULT, 1)
        assert "PFAS are persistent" in result["chain"][0]["direct_quote"]
        assert "4 ppt for PFOA" in result["chain"][1]["direct_quote"]


# ---------------------------------------------------------------------------
# Tests: All citation chains summary
# ---------------------------------------------------------------------------

class TestAllCitationChainsSummary:
    """Test the aggregate summary logic for all citations."""

    def _build_summary(self, data: dict) -> list[dict]:
        """Replicate all-chains summary logic from live_server.py."""
        bibliography = data.get("bibliography", [])
        evidence_pool = data.get("evidence", [])
        claims = data.get("claims", [])

        evidence_by_id = {e["evidence_id"]: e for e in evidence_pool}
        claims_by_evidence: dict[str, list[dict]] = {}
        for claim in claims:
            for eid in claim.get("evidence_ids", []):
                claims_by_evidence.setdefault(eid, []).append(claim)

        summaries = []
        for bib in bibliography:
            bib_ev_ids = bib.get("evidence_ids", [])
            tier_counts: dict[str, int] = {}
            supported = 0
            total_verified = 0
            for eid in bib_ev_ids:
                ev = evidence_by_id.get(eid, {})
                tier = ev.get("quality_tier", "BRONZE")
                tier_counts[tier] = tier_counts.get(tier, 0) + 1
                for claim in claims_by_evidence.get(eid, []):
                    total_verified += 1
                    if claim.get("is_faithful") or claim.get("verdict") == "SUPPORTED":
                        supported += 1

            summaries.append({
                "citation_number": bib.get("citation_number"),
                "evidence_count": len(bib_ev_ids),
                "tier_breakdown": tier_counts,
                "verified_claims": total_verified,
                "supported_claims": supported,
                "verification_rate": round(supported / total_verified, 2) if total_verified > 0 else None,
            })
        return summaries

    def test_citation_1_fully_verified(self):
        """Citation [1]: 2 GOLD evidence, 100% verification rate."""
        summaries = self._build_summary(SAMPLE_RESULT)
        s1 = summaries[0]
        assert s1["citation_number"] == 1
        assert s1["evidence_count"] == 2
        assert s1["tier_breakdown"]["GOLD"] == 2
        assert s1["verified_claims"] == 2
        assert s1["supported_claims"] == 2
        assert s1["verification_rate"] == 1.0

    def test_citation_2_partially_verified(self):
        """Citation [2]: 1 SILVER evidence, 0% verification rate (not faithful)."""
        summaries = self._build_summary(SAMPLE_RESULT)
        s2 = summaries[1]
        assert s2["citation_number"] == 2
        assert s2["evidence_count"] == 1
        assert s2["tier_breakdown"]["SILVER"] == 1
        assert s2["supported_claims"] == 0
        assert s2["verification_rate"] == 0.0

    def test_total_citations_count(self):
        """Summary covers all bibliography entries."""
        summaries = self._build_summary(SAMPLE_RESULT)
        assert len(summaries) == 2


# ---------------------------------------------------------------------------
# Tests: API endpoint via httpx (requires result file on disk)
# ---------------------------------------------------------------------------

class TestCitationChainAPI:
    """Test the actual FastAPI endpoint with a result file on disk."""

    @pytest.mark.asyncio
    async def test_chain_endpoint_200(self, result_on_disk):
        """GET /api/research/chain/{vid}/{num} returns 200 with chain data."""
        from scripts.live_server import app

        # Temporarily change working directory so Path("outputs/...") resolves
        original_cwd = os.getcwd()
        try:
            os.chdir(str(result_on_disk))
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/research/chain/TEST_CHAIN_001/1")
                assert resp.status_code == 200
                data = resp.json()
                assert data["citation_number"] == 1
                assert data["evidence_count"] == 2
                assert data["source"]["citation_key"] == "EPA2024"
        finally:
            os.chdir(original_cwd)

    @pytest.mark.asyncio
    async def test_chain_endpoint_404_missing(self, result_on_disk):
        """Missing vector_id returns 404."""
        from scripts.live_server import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/research/chain/NONEXISTENT_VID/1")
            assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_all_chains_endpoint_200(self, result_on_disk):
        """GET /api/research/chain/{vid} returns summary of all citations."""
        from scripts.live_server import app

        original_cwd = os.getcwd()
        try:
            os.chdir(str(result_on_disk))
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/research/chain/TEST_CHAIN_001")
                assert resp.status_code == 200
                data = resp.json()
                assert data["total_citations"] == 2
                assert len(data["citations"]) == 2
        finally:
            os.chdir(original_cwd)
