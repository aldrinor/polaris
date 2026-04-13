"""
polaris graph smoke test — verify all components are connected.

Tests (16 total):
Core (9):
  1. Environment variables  2. Graph compilation  3. State initialization
  4. Schema validation  5. Serper web search  6. Semantic Scholar
  7. OpenRouter generate()  8. OpenRouter reason()  9. OpenRouter structured()

SOTA Sprint (7):
  10. Jina Reader fetch (free tier, no key)
  11. Exa neural search (requires EXA_API_KEY)
  12. Firecrawl scrape (requires FIRECRAWL_API_KEY)
  13. Domain authority gate (PG_AUTHORITY_GATE, replaced FIX-B1 blocklist)
  14. Off-topic evidence filter
  15. Redundancy detection
  16. Abstract metric validation
"""

import asyncio
import json
import logging
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger("smoke_test")

PASS = "PASS"
FAIL = "FAIL"
results = []


def record(name: str, status: str, detail: str = ""):
    results.append({"name": name, "status": status, "detail": detail})
    icon = "+" if status == PASS else "X"
    print(f"  [{icon}] {name}: {status} {detail}")


async def test_openrouter_generate():
    """Test OpenRouter generate() — clean prose, no CoT."""
    try:
        from src.polaris_graph.llm.openrouter_client import OpenRouterClient

        async with OpenRouterClient() as client:
            resp = await client.generate(
                prompt="What is 2+2? Reply with just the number.",
                system="You are a math assistant.",
                max_tokens=10,
            )
            if resp.content and "4" in resp.content:
                record("OpenRouter generate()", PASS, f"'{resp.content.strip()}'")
            else:
                record("OpenRouter generate()", FAIL, f"Unexpected: '{resp.content}'")
    except Exception as e:
        record("OpenRouter generate()", FAIL, str(e)[:200])


async def test_openrouter_reason():
    """Test OpenRouter reason() — reasoning separated from content."""
    try:
        from src.polaris_graph.llm.openrouter_client import OpenRouterClient

        async with OpenRouterClient() as client:
            resp = await client.reason(
                prompt="Is 7 a prime number? Explain briefly.",
                system="You are a math expert.",
                effort="low",
                max_tokens=200,
            )
            has_content = bool(resp.content and len(resp.content) > 5)
            record(
                "OpenRouter reason()",
                PASS if has_content else FAIL,
                f"content={len(resp.content or '')} chars, "
                f"reasoning={'yes' if resp.reasoning else 'no'}",
            )
    except Exception as e:
        record("OpenRouter reason()", FAIL, str(e)[:200])


async def test_openrouter_structured():
    """Test OpenRouter structured output with Pydantic schema."""
    try:
        from src.polaris_graph.llm.openrouter_client import OpenRouterClient
        from pydantic import BaseModel

        class TestSchema(BaseModel):
            answer: str
            confidence: float

        async with OpenRouterClient() as client:
            parsed = await client.generate_structured(
                prompt="What is the capital of Japan? Rate your confidence 0-1.",
                schema=TestSchema,
                system="Answer concisely.",
            )
            if parsed and hasattr(parsed, "answer"):
                record(
                    "OpenRouter structured()",
                    PASS,
                    f"answer='{parsed.answer}', conf={parsed.confidence}",
                )
            else:
                record("OpenRouter structured()", FAIL, "No parsed output")
    except Exception as e:
        record("OpenRouter structured()", FAIL, str(e)[:200])


def test_serper_search():
    """Test Serper web search API."""
    try:
        from src.agents.search_agent import web_search

        results_list = web_search.invoke({
            "query": "electric vehicles air quality",
            "max_results": 3,
        })
        if isinstance(results_list, list) and len(results_list) > 0:
            record(
                "Serper web search",
                PASS,
                f"{len(results_list)} results, first: {results_list[0].get('title', '')[:50]}",
            )
        else:
            record("Serper web search", FAIL, f"Got: {type(results_list)}")
    except Exception as e:
        record("Serper web search", FAIL, str(e)[:200])


def test_semantic_scholar():
    """Test Semantic Scholar academic search API."""
    try:
        from src.agents.search_agent import academic_search

        results_list = academic_search.invoke({
            "query": "electric vehicles urban air quality",
            "max_results": 3,
        })
        if isinstance(results_list, list) and len(results_list) > 0:
            record(
                "Semantic Scholar",
                PASS,
                f"{len(results_list)} results, first: {results_list[0].get('title', '')[:50]}",
            )
        else:
            record("Semantic Scholar", FAIL, f"Got: {type(results_list)}")
    except Exception as e:
        record("Semantic Scholar", FAIL, str(e)[:200])


def test_graph_compilation():
    """Test LangGraph compilation."""
    try:
        from src.polaris_graph.graph import build_graph

        graph = build_graph()
        compiled = graph.compile()
        nodes = list(compiled.get_graph().nodes)
        record(
            "Graph compilation",
            PASS,
            f"{len(nodes)} nodes: {nodes}",
        )
    except Exception as e:
        record("Graph compilation", FAIL, str(e)[:200])


def test_state_initialization():
    """Test state creation with all fields."""
    try:
        from src.polaris_graph.state import create_initial_state

        state = create_initial_state(
            vector_id="SMOKE_TEST",
            query="test query",
            application="test",
            region="GLOBAL",
            stage=1,
        )
        required = [
            "vector_id", "original_query", "sub_queries", "evidence",
            "claims", "sections", "bibliography", "final_report",
            "quality_metrics", "timestamps",
        ]
        missing = [k for k in required if k not in state]
        if not missing:
            record("State initialization", PASS, f"{len(state)} fields")
        else:
            record("State initialization", FAIL, f"Missing: {missing}")
    except Exception as e:
        record("State initialization", FAIL, str(e)[:200])


def test_schema_validation():
    """Test Pydantic schemas can be instantiated."""
    try:
        from src.polaris_graph.schemas import (
            QueryPlan,
            SubQuery,
            SourceAnalysis,
            ClaimVerification,
            SectionDraft,
        )

        # Test SubQuery
        sq = SubQuery(
            query="test query",
            intent="find test data",
            source_preference="web",
        )

        # Test SectionDraft
        sd = SectionDraft(
            section_id="s1",
            title="Test",
            content="Test content [CITE:e1].",
            word_count=3,
            evidence_ids_used=["e1"],
            claims_made=["test claim"],
        )

        record("Schema validation", PASS, "All schemas valid")
    except Exception as e:
        record("Schema validation", FAIL, str(e)[:200])


def test_env_vars():
    """Test required environment variables exist."""
    required = [
        "OPENROUTER_API_KEY",
        "SERPER_API_KEY",
        "SEMANTIC_SCHOLAR_API_KEY",
    ]
    missing = [k for k in required if not os.environ.get(k)]
    if not missing:
        record(
            "Environment variables",
            PASS,
            f"All {len(required)} keys present",
        )
    else:
        record("Environment variables", FAIL, f"Missing: {missing}")

    # SOTA Sprint: Report new optional API keys status
    optional = {
        "JINA_API_KEY": "Jina Reader (works without, free tier 20 req/min)",
        "FIRECRAWL_API_KEY": "Firecrawl (REQUIRED for 96% web coverage)",
        "EXA_API_KEY": "Exa neural search (REQUIRED for semantic diversity)",
    }
    for key, desc in optional.items():
        val = os.environ.get(key, "")
        status = "SET" if val else "MISSING"
        logger.info(f"  Optional: {key} = {status} — {desc}")


# ---------------------------------------------------------------------------
# SOTA Sprint: New backend connectivity tests
# ---------------------------------------------------------------------------

async def test_jina_reader():
    """Test Jina Reader fetch — no API key needed for free tier."""
    try:
        import httpx

        test_url = "https://en.wikipedia.org/wiki/Water_purification"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"https://r.jina.ai/{test_url}",
                headers={
                    "Accept": "text/markdown",
                    "X-Return-Format": "markdown",
                },
            )
            if resp.status_code == 200 and len(resp.text.strip()) > 200:
                record(
                    "Jina Reader fetch",
                    PASS,
                    f"{len(resp.text)} chars from Wikipedia",
                )
            else:
                record(
                    "Jina Reader fetch",
                    FAIL,
                    f"status={resp.status_code}, len={len(resp.text)}",
                )
    except Exception as e:
        record("Jina Reader fetch", FAIL, str(e)[:200])


async def test_exa_search():
    """Test Exa neural search — requires EXA_API_KEY."""
    api_key = os.getenv("EXA_API_KEY", "")
    if not api_key:
        record("Exa neural search", FAIL, "EXA_API_KEY not set — backend INACTIVE")
        return
    try:
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.exa.ai/search",
                json={
                    "query": "water filtration technology",
                    "type": "neural",
                    "numResults": 3,
                    "useAutoprompt": True,
                },
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                count = len(data.get("results", []))
                record("Exa neural search", PASS, f"{count} results")
            else:
                record("Exa neural search", FAIL, f"status={resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        record("Exa neural search", FAIL, str(e)[:200])


async def test_firecrawl():
    """Test Firecrawl scrape — requires FIRECRAWL_API_KEY."""
    api_key = os.getenv("FIRECRAWL_API_KEY", "")
    if not api_key:
        record("Firecrawl scrape", FAIL, "FIRECRAWL_API_KEY not set — backend INACTIVE")
        return
    try:
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.firecrawl.dev/v1/scrape",
                json={"url": "https://www.epa.gov/ground-water-and-drinking-water", "formats": ["markdown"]},
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                md = data.get("data", {}).get("markdown", "")
                record("Firecrawl scrape", PASS, f"{len(md)} chars markdown")
            else:
                record("Firecrawl scrape", FAIL, f"status={resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        record("Firecrawl scrape", FAIL, str(e)[:200])


def test_domain_authority():
    """Test FIX-B2 authority gate (replaces FIX-B1 blocklist, removed 2026-04-12).

    Verifies _get_domain_authority returns the correct tier for:
    - High-tier government (epa.gov → 1.0)
    - Low-credibility commerce (amazon.com → PG_LOW_CREDIBILITY_AUTHORITY, default 0.2)
    - Unknown domain (randomblog.com → PG_DEFAULT_DOMAIN_AUTHORITY, default 0.5)

    The pre-fetch authority gate (PG_AUTHORITY_GATE, default 0.3) drops
    sources scoring below the threshold before fetch — this replaces
    the old hard blocklist.
    """
    try:
        from src.polaris_graph.agents.analyzer import _get_domain_authority

        epa_auth = _get_domain_authority("https://epa.gov/water")
        amazon_auth = _get_domain_authority("https://amazon.com/dp/B08")
        nature_auth = _get_domain_authority("https://nature.com/articles/123")
        unknown_auth = _get_domain_authority("https://randomblog.com/post")

        expected_default = float(os.getenv("PG_DEFAULT_DOMAIN_AUTHORITY", "0.5"))
        expected_low_cred = float(os.getenv("PG_LOW_CREDIBILITY_AUTHORITY", "0.2"))
        gate = float(os.getenv("PG_AUTHORITY_GATE", "0.3"))

        problems = []
        if epa_auth != 1.0:
            problems.append(f"EPA expected 1.0, got {epa_auth}")
        if nature_auth != 1.0:
            problems.append(f"Nature expected 1.0, got {nature_auth}")
        if amazon_auth != expected_low_cred:
            problems.append(f"Amazon expected {expected_low_cred} (low-cred), got {amazon_auth}")
        if unknown_auth != expected_default:
            problems.append(f"Unknown expected {expected_default}, got {unknown_auth}")
        # Pre-fetch gate must drop amazon (commerce) but keep unknown blogs
        if amazon_auth >= gate:
            problems.append(f"Amazon auth {amazon_auth} should be below gate {gate}")
        if unknown_auth < gate:
            problems.append(f"Unknown auth {unknown_auth} should be above gate {gate}")

        if not problems:
            record(
                "Domain authority gate",
                PASS,
                f"EPA={epa_auth}, Nature={nature_auth}, Amazon={amazon_auth} (<{gate}), "
                f"Unknown={unknown_auth} (>={gate})",
            )
        else:
            record("Domain authority gate", FAIL, "; ".join(problems))
    except Exception as e:
        record("Domain authority gate", FAIL, str(e)[:200])


def test_offtopic_filter():
    """Test FIX-B3: Off-topic evidence filter is importable and functional."""
    try:
        from src.polaris_graph.agents.analyzer import _filter_offtopic_evidence

        # Empty input should return empty (no crash)
        result = _filter_offtopic_evidence([], "test query")
        if isinstance(result, list) and len(result) == 0:
            record("Off-topic filter", PASS, "Function imported and handles empty input")
        else:
            record("Off-topic filter", FAIL, f"Unexpected return: {type(result)}")
    except Exception as e:
        record("Off-topic filter", FAIL, str(e)[:200])


def test_redundancy_detection():
    """Test FIX-C3: Redundancy detection is importable and functional."""
    try:
        from src.polaris_graph.synthesis.report_assembler import detect_redundancy
        from src.polaris_graph.state import ReportSection

        sections = [
            ReportSection(
                section_id="s1", title="A", content="Water filters remove contaminants effectively.",
                word_count=6, citation_ids=[], evidence_ids=[],
            ),
            ReportSection(
                section_id="s2", title="B", content="Completely different topic about solar energy panels.",
                word_count=7, citation_ids=[], evidence_ids=[],
            ),
        ]
        result = detect_redundancy(sections)
        if isinstance(result, dict) and "duplicate_pairs" in result:
            record("Redundancy detection", PASS, f"duplicate_pairs={result['duplicate_pairs']}")
        else:
            record("Redundancy detection", FAIL, f"Bad return: {result}")
    except Exception as e:
        record("Redundancy detection", FAIL, str(e)[:200])


def test_abstract_validation():
    """Test FIX-E2: Abstract metric validation is importable and functional."""
    try:
        from src.polaris_graph.synthesis.report_assembler import _validate_abstract_metrics

        # Hallucinated source count should trigger warning
        warnings = _validate_abstract_metrics(
            abstract="This report synthesizes evidence from 147 peer-reviewed sources.",
            unique_sources=29,
            total_citations=168,
            total_words=10000,
        )
        has_warning = len(warnings) > 0

        # Accurate count should not trigger
        no_warnings = _validate_abstract_metrics(
            abstract="This report examines water filtration methods.",
            unique_sources=29,
            total_citations=168,
            total_words=10000,
        )
        no_false_pos = len(no_warnings) == 0

        if has_warning and no_false_pos:
            record("Abstract validation", PASS, f"Caught hallucinated '147', no false positives")
        else:
            record("Abstract validation", FAIL, f"warning={has_warning}, no_false_pos={no_false_pos}")
    except Exception as e:
        record("Abstract validation", FAIL, str(e)[:200])


async def main():
    print("\n" + "=" * 60)
    print("polaris graph SMOKE TEST")
    print("=" * 60 + "\n")

    start = time.monotonic()

    # Sync tests
    test_env_vars()
    test_graph_compilation()
    test_state_initialization()
    test_schema_validation()
    test_serper_search()
    test_semantic_scholar()

    # Async tests — core LLM
    await test_openrouter_generate()
    await test_openrouter_reason()
    await test_openrouter_structured()

    # SOTA Sprint: New backend connectivity
    await test_jina_reader()
    await test_exa_search()
    await test_firecrawl()

    # SOTA Sprint: New quality functions (sync, no API calls)
    test_domain_authority()
    test_offtopic_filter()
    test_redundancy_detection()
    test_abstract_validation()

    elapsed = time.monotonic() - start

    # Summary
    passed = sum(1 for r in results if r["status"] == PASS)
    failed = sum(1 for r in results if r["status"] == FAIL)

    print(f"\n{'=' * 60}")
    print(f"RESULTS: {passed}/{len(results)} passed, {failed} failed")
    print(f"Time: {elapsed:.1f}s")
    print(f"{'=' * 60}")

    if failed > 0:
        print("\nFAILED TESTS:")
        for r in results:
            if r["status"] == FAIL:
                print(f"  - {r['name']}: {r['detail']}")
        sys.exit(1)
    else:
        print("\nAll systems GO for polaris graph!")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
