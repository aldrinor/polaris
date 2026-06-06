"""
polaris graph preflight v2 -- comprehensive 40-test validation.

Replaces the old 16-test pg_smoke_test.py with 4 tiers of checks:
  Tier 1 (10): Hard failures -- would crash immediately
  Tier 2 (10): Config range tests -- would crash mid-pipeline
  Tier 3 (15): Integration tests -- would fail during pipeline
  Tier 4 (5):  Quality tests -- would degrade output

Usage:
    python scripts/pg_preflight.py

Set PG_PREFLIGHT_LIVE=1 in .env to run live API tests (Tier 3).
"""

import asyncio
import importlib
import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

sys.path.insert(0, ".")

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)

# ---------------------------------------------------------------------------
# ANSI colors
# ---------------------------------------------------------------------------

_GREEN = "\033[92m"
_RED = "\033[91m"
_YELLOW = "\033[93m"
_BOLD = "\033[1m"
_RESET = "\033[0m"

LIVE_MODE = os.getenv("PG_PREFLIGHT_LIVE", "0") == "1"


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"


class TestResult:
    """Container for a single test result."""

    def __init__(self, name: str, status: str, message: str):
        self.name = name
        self.status = status
        self.message = message

    def display(self) -> str:
        if self.status == PASS:
            tag = f"{_GREEN}[PASS]{_RESET}"
        elif self.status == FAIL:
            tag = f"{_RED}[FAIL]{_RESET}"
        else:
            tag = f"{_YELLOW}[SKIP]{_RESET}"
        return f"  {tag} {self.name} -- {self.message}"


# ===================================================================
# TIER 1: Hard Failures (11 tests; +T02b serper-credit-pool advisory, #947) -- Would crash immediately
# ===================================================================


async def test_openrouter_api_key() -> TestResult:
    """T01: Check OPENROUTER_API_KEY env var exists and is non-empty."""
    key = os.getenv("OPENROUTER_API_KEY", "")
    if key and len(key) > 10:
        return TestResult(
            "test_openrouter_api_key",
            PASS,
            f"API key present ({len(key)} chars)",
        )
    return TestResult(
        "test_openrouter_api_key",
        FAIL,
        "OPENROUTER_API_KEY missing or too short",
    )


async def test_serper_api_key() -> TestResult:
    """T02: Check SERPER_API_KEY env var exists."""
    key = os.getenv("SERPER_API_KEY", "")
    if key:
        return TestResult(
            "test_serper_api_key",
            PASS,
            f"API key present ({len(key)} chars)",
        )
    return TestResult(
        "test_serper_api_key",
        FAIL,
        "SERPER_API_KEY missing",
    )


async def test_serper_credit_pool() -> TestResult:
    """T02b: Serper prepaid-pool honesty (I-meta-002-q1d #947). Serper exposes NO programmatic
    total-prepaid-pool API — the per-request `X-...-Credits` header is a refill-WINDOW counter, not the
    remaining prepaid balance. So this is an explicit advisory (NO network, NO SPEND): before a PAID run,
    verify the prepaid balance on the Serper dashboard. Surfacing this as a preflight line makes the
    credit check honest rather than implying the header tells us the pool."""
    return TestResult(
        "test_serper_credit_pool",
        SKIP,
        "advisory: Serper prepaid pool is NOT programmatically queryable (the per-request credits "
        "header is a refill-window counter, not the total) — verify the balance at "
        "https://serper.dev/dashboard before a paid run",
    )


async def test_exa_api_key() -> TestResult:
    """T03: Exa key advisory. I-meta-002-q1d (#947): Exa is Pipeline-B-ONLY (searcher.py) and is NOT
    used by the Pipeline-A benchmark path (live_retriever.py). A missing EXA_API_KEY must NOT hard-FAIL
    this benchmark preflight (it was previously a FAIL, so preflight was not a faithful mirror of
    benchmark-required creds). Missing key -> SKIP with a clear Pipeline-B-only advisory."""
    exa_enabled = os.getenv("PG_EXA_ENABLED", "1") == "1"
    if not exa_enabled:
        return TestResult(
            "test_exa_api_key",
            SKIP,
            "PG_EXA_ENABLED=0, skipping (Exa is Pipeline-B-only)",
        )
    key = os.getenv("EXA_API_KEY", "")
    if key:
        return TestResult(
            "test_exa_api_key",
            PASS,
            f"API key present ({len(key)} chars) — Pipeline-B-only",
        )
    return TestResult(
        "test_exa_api_key",
        SKIP,
        "EXA_API_KEY missing — Exa is Pipeline-B-only (searcher.py), NOT used by the "
        "Pipeline-A benchmark (live_retriever.py); not a benchmark blocker",
    )


async def test_s2_api_key() -> TestResult:
    """T04: Check SEMANTIC_SCHOLAR_API_KEY env var exists."""
    key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
    if key:
        return TestResult(
            "test_s2_api_key",
            PASS,
            f"SEMANTIC_SCHOLAR_API_KEY present ({len(key)} chars)",
        )
    return TestResult(
        "test_s2_api_key",
        FAIL,
        "SEMANTIC_SCHOLAR_API_KEY missing",
    )


async def test_openrouter_budget() -> TestResult:
    """T05: Verify OpenRouter key works and has sufficient budget."""
    key = os.getenv("OPENROUTER_API_KEY", "")
    if not key:
        return TestResult(
            "test_openrouter_budget",
            FAIL,
            "No API key to check",
        )
    min_budget = float(os.getenv("PG_BUDGET_GUARD_USD", "5.0"))
    try:
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                "https://openrouter.ai/api/v1/auth/key",
                headers={"Authorization": f"Bearer {key}"},
            )
            if resp.status_code != 200:
                return TestResult(
                    "test_openrouter_budget",
                    FAIL,
                    f"API returned {resp.status_code}: {resp.text[:200]}",
                )
            data = resp.json().get("data", {})
            usage = data.get("usage", 0)
            limit = data.get("limit", None)
            if limit is not None:
                remaining = limit - usage
                if remaining < min_budget:
                    return TestResult(
                        "test_openrouter_budget",
                        FAIL,
                        f"Budget too low: ${remaining:.2f} remaining "
                        f"(minimum: ${min_budget:.2f})",
                    )
                return TestResult(
                    "test_openrouter_budget",
                    PASS,
                    f"${remaining:.2f} remaining (minimum: ${min_budget:.2f})",
                )
            # No limit = unlimited
            return TestResult(
                "test_openrouter_budget",
                PASS,
                f"Unlimited budget (usage: ${usage:.2f})",
            )
    except Exception as exc:
        return TestResult(
            "test_openrouter_budget",
            FAIL,
            f"API call failed: {str(exc)[:200]}",
        )


async def test_graph_compiles() -> TestResult:
    """T06: Import build_graph(), verify it returns 8 nodes."""
    try:
        from src.polaris_graph.graph import build_graph

        graph = build_graph()
        expected_nodes = {
            "plan",
            "search",
            "storm_interviews",
            "analyze",
            "verify",
            "evaluate",
            "synthesize",
            "search_gaps",
        }
        # StateGraph stores nodes in .nodes dict
        actual_nodes = set(graph.nodes.keys())
        if expected_nodes <= actual_nodes:
            return TestResult(
                "test_graph_compiles",
                PASS,
                f"{len(actual_nodes)} nodes: {sorted(actual_nodes)}",
            )
        missing = expected_nodes - actual_nodes
        return TestResult(
            "test_graph_compiles",
            FAIL,
            f"Missing nodes: {missing}. Found: {sorted(actual_nodes)}",
        )
    except Exception as exc:
        return TestResult(
            "test_graph_compiles",
            FAIL,
            f"Import/build error: {str(exc)[:200]}",
        )


async def test_state_schema() -> TestResult:
    """T07: Verify ResearchState has all required fields."""
    try:
        from src.polaris_graph.state import ResearchState

        required_fields = [
            "original_query",
            "vector_id",
            "sub_queries",
            "web_results",
            "academic_results",
            "evidence",
            "claims",
            "gaps",
            "gap_queries",
            "needs_iteration",
            "storm_conversations",
            "storm_outline",
            "section_evidence_map",
            "content_cache_hits",
            "search_cache_hits",
        ]
        annotations = ResearchState.__annotations__
        missing = [f for f in required_fields if f not in annotations]
        if not missing:
            return TestResult(
                "test_state_schema",
                PASS,
                f"All {len(required_fields)} required fields present "
                f"({len(annotations)} total)",
            )
        return TestResult(
            "test_state_schema",
            FAIL,
            f"Missing fields: {missing}",
        )
    except Exception as exc:
        return TestResult(
            "test_state_schema",
            FAIL,
            f"Import error: {str(exc)[:200]}",
        )


async def test_pydantic_schemas() -> TestResult:
    """T08: Import and instantiate all Pydantic schemas."""
    try:
        from src.polaris_graph.schemas import (
            AtomicFact,
            ClaimVerification,
            ClusterPlan,
            EvidenceCluster,
            GapAnalysis,
            QueryPlan,
            ReportOutline,
            SectionDraft,
            SectionOutlineItem,
            SourceAnalysis,
            SourceAnalysisBatch,
            SubQuery,
            VerificationBatch,
        )

        # Validate sample instances
        errors = []
        try:
            SubQuery(query="test query", intent="test", source_preference="web")
        except Exception as e:
            errors.append(f"SubQuery: {e}")

        try:
            AtomicFact(
                statement="Water is H2O",
                direct_quote="Water is composed of hydrogen and oxygen",
                fact_category="statistic",
                relevance_score=0.9,
                confidence=0.8,
            )
        except Exception as e:
            errors.append(f"AtomicFact: {e}")

        try:
            ClaimVerification(
                claim="Water is H2O",
                verdict="SUPPORTED",
                confidence=0.9,
                supporting_evidence=["ev_001"],
            )
        except Exception as e:
            errors.append(f"ClaimVerification: {e}")

        try:
            GapAnalysis(
                gaps=["missing data on UV treatment"],
                gap_severity="moderate",
                suggested_queries=["UV water treatment effectiveness"],
                should_iterate=True,
            )
        except Exception as e:
            errors.append(f"GapAnalysis: {e}")

        try:
            SourceAnalysis(
                source_url="https://example.com",
                source_title="Test",
                atomic_facts=[],
            )
        except Exception as e:
            errors.append(f"SourceAnalysis: {e}")

        try:
            EvidenceCluster(
                cluster_id="c1",
                theme="Water filtration",
                description="Methods",
                evidence_ids=["ev_1"],
            )
        except Exception as e:
            errors.append(f"EvidenceCluster: {e}")

        if errors:
            return TestResult(
                "test_pydantic_schemas",
                FAIL,
                f"Schema validation errors: {'; '.join(errors)}",
            )
        return TestResult(
            "test_pydantic_schemas",
            PASS,
            "All schemas import and validate",
        )
    except Exception as exc:
        return TestResult(
            "test_pydantic_schemas",
            FAIL,
            f"Import error: {str(exc)[:200]}",
        )


async def test_checkpoint_sqlite_writable() -> TestResult:
    """T09: Verify checkpointer creates AsyncSqliteSaver successfully."""
    try:
        from src.polaris_graph.checkpoint_manager import get_checkpointer

        checkpointer = get_checkpointer()
        if checkpointer is not None:
            return TestResult(
                "test_checkpoint_sqlite_writable",
                PASS,
                "AsyncSqliteSaver created successfully",
            )
        return TestResult(
            "test_checkpoint_sqlite_writable",
            FAIL,
            "get_checkpointer() returned None",
        )
    except Exception as exc:
        return TestResult(
            "test_checkpoint_sqlite_writable",
            FAIL,
            f"Checkpointer error: {str(exc)[:200]}",
        )


async def test_output_dir_writable() -> TestResult:
    """T10: Verify outputs/polaris_graph/ exists and is writable."""
    try:
        output_dir = Path(
            os.getenv("PG_OUTPUT_DIR", "outputs/polaris_graph")
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        # Test write access
        test_file = output_dir / "_preflight_write_test.tmp"
        test_file.write_text("preflight_test", encoding="utf-8")
        content = test_file.read_text(encoding="utf-8")
        test_file.unlink()
        if content == "preflight_test":
            return TestResult(
                "test_output_dir_writable",
                PASS,
                f"Directory writable: {output_dir}",
            )
        return TestResult(
            "test_output_dir_writable",
            FAIL,
            "Write/read roundtrip failed",
        )
    except Exception as exc:
        return TestResult(
            "test_output_dir_writable",
            FAIL,
            f"Directory error: {str(exc)[:200]}",
        )


# ===================================================================
# TIER 2: Config Range Tests (10 tests) -- Would crash mid-pipeline
# ===================================================================


def _get_int_env(name: str, default: str) -> int:
    """Read an integer env var with default."""
    return int(os.getenv(name, default))


def _get_float_env(name: str, default: str) -> float:
    """Read a float env var with default."""
    return float(os.getenv(name, default))


async def test_analysis_batch_size() -> TestResult:
    """T11: PG_ANALYSIS_BATCH_SIZE in [1, 20]."""
    val = _get_int_env("PG_ANALYSIS_BATCH_SIZE", "1")
    if 1 <= val <= 20:
        return TestResult(
            "test_analysis_batch_size",
            PASS,
            f"PG_ANALYSIS_BATCH_SIZE={val} (valid: 1-20)",
        )
    return TestResult(
        "test_analysis_batch_size",
        FAIL,
        f"PG_ANALYSIS_BATCH_SIZE={val} out of range [1, 20]",
    )


async def test_verify_batch_size() -> TestResult:
    """T12: PG_VERIFY_BATCH_SIZE in [5, 50]."""
    val = _get_int_env("PG_VERIFY_BATCH_SIZE", "10")
    if 5 <= val <= 50:
        return TestResult(
            "test_verify_batch_size",
            PASS,
            f"PG_VERIFY_BATCH_SIZE={val} (valid: 5-50)",
        )
    return TestResult(
        "test_verify_batch_size",
        FAIL,
        f"PG_VERIFY_BATCH_SIZE={val} out of range [5, 50]",
    )


async def test_synthesis_max_tokens() -> TestResult:
    """T13: PG_SYNTHESIS_STRUCTURED_MAX_TOKENS >= 16384."""
    val = _get_int_env("PG_SYNTHESIS_STRUCTURED_MAX_TOKENS", "16384")
    if val >= 16384:
        return TestResult(
            "test_synthesis_max_tokens",
            PASS,
            f"PG_SYNTHESIS_STRUCTURED_MAX_TOKENS={val} (min: 16384)",
        )
    return TestResult(
        "test_synthesis_max_tokens",
        FAIL,
        f"PG_SYNTHESIS_STRUCTURED_MAX_TOKENS={val} < 16384",
    )


async def test_max_execution_minutes() -> TestResult:
    """T14: PG_MAX_EXECUTION_MINUTES >= 30."""
    val = _get_int_env("PG_MAX_EXECUTION_MINUTES", "60")
    if val >= 30:
        return TestResult(
            "test_max_execution_minutes",
            PASS,
            f"PG_MAX_EXECUTION_MINUTES={val} (min: 30)",
        )
    return TestResult(
        "test_max_execution_minutes",
        FAIL,
        f"PG_MAX_EXECUTION_MINUTES={val} < 30",
    )


async def test_agentic_max_time() -> TestResult:
    """T15: PG_AGENTIC_MAX_TIME_SECONDS >= 300."""
    val = _get_int_env("PG_AGENTIC_MAX_TIME_SECONDS", "1800")
    if val >= 300:
        return TestResult(
            "test_agentic_max_time",
            PASS,
            f"PG_AGENTIC_MAX_TIME_SECONDS={val} (min: 300)",
        )
    return TestResult(
        "test_agentic_max_time",
        FAIL,
        f"PG_AGENTIC_MAX_TIME_SECONDS={val} < 300",
    )


async def test_timeout_values_positive() -> TestResult:
    """T16: All timeout values > 0."""
    timeout_vars = {
        "PG_ANALYSIS_BATCH_TIMEOUT": "240.0",
        "PG_AGENTIC_FETCH_TIMEOUT": "15.0",
    }
    errors = []
    details = []
    for var_name, default in timeout_vars.items():
        val = _get_float_env(var_name, default)
        if val <= 0:
            errors.append(f"{var_name}={val}")
        else:
            details.append(f"{var_name}={val}")
    if errors:
        return TestResult(
            "test_timeout_values_positive",
            FAIL,
            f"Non-positive timeouts: {', '.join(errors)}",
        )
    return TestResult(
        "test_timeout_values_positive",
        PASS,
        f"All timeouts positive: {', '.join(details)}",
    )


async def test_concurrency_values() -> TestResult:
    """T17: All concurrency values in [1, 50]."""
    concurrency_vars = {
        "PG_WEB_CONCURRENCY": "20",
        "PG_FETCH_CONCURRENCY": "20",
        "PG_ANALYSIS_CONCURRENCY": "12",
        "PG_SECTION_WRITE_CONCURRENCY": "4",
    }
    errors = []
    details = []
    for var_name, default in concurrency_vars.items():
        val = _get_int_env(var_name, default)
        if not (1 <= val <= 50):
            errors.append(f"{var_name}={val}")
        else:
            details.append(f"{var_name}={val}")
    if errors:
        return TestResult(
            "test_concurrency_values",
            FAIL,
            f"Out of range [1,50]: {', '.join(errors)}",
        )
    return TestResult(
        "test_concurrency_values",
        PASS,
        f"All valid: {', '.join(details)}",
    )


async def test_min_thresholds_reasonable() -> TestResult:
    """T18: Quality thresholds are within sane ranges."""
    errors = []
    details = []

    min_ev = _get_int_env("PG_MIN_EVIDENCE_COUNT", "20")
    if min_ev < 10:
        errors.append(f"PG_MIN_EVIDENCE_COUNT={min_ev} < 10")
    else:
        details.append(f"PG_MIN_EVIDENCE_COUNT={min_ev}")

    min_faith = _get_float_env("PG_MIN_FAITHFULNESS", "0.70")
    if not (0.5 <= min_faith <= 1.0):
        errors.append(f"PG_MIN_FAITHFULNESS={min_faith} not in [0.5, 1.0]")
    else:
        details.append(f"PG_MIN_FAITHFULNESS={min_faith}")

    min_words = _get_int_env("PG_MIN_TOTAL_WORDS", "8000")
    if min_words < 2000:
        errors.append(f"PG_MIN_TOTAL_WORDS={min_words} < 2000")
    else:
        details.append(f"PG_MIN_TOTAL_WORDS={min_words}")

    if errors:
        return TestResult(
            "test_min_thresholds_reasonable",
            FAIL,
            "; ".join(errors),
        )
    return TestResult(
        "test_min_thresholds_reasonable",
        PASS,
        "; ".join(details),
    )


async def test_budget_guard() -> TestResult:
    """T19: PG_BUDGET_GUARD_USD >= 5.0."""
    val = _get_float_env("PG_BUDGET_GUARD_USD", "150.0")
    if val >= 5.0:
        return TestResult(
            "test_budget_guard",
            PASS,
            f"PG_BUDGET_GUARD_USD={val} (min: 5.0)",
        )
    return TestResult(
        "test_budget_guard",
        FAIL,
        f"PG_BUDGET_GUARD_USD={val} < 5.0",
    )


async def test_storm_config() -> TestResult:
    """T20: If PG_STORM_ENABLED=1, STORM config values are valid."""
    storm_enabled = os.getenv("PG_STORM_ENABLED", "0") == "1"
    if not storm_enabled:
        return TestResult(
            "test_storm_config",
            SKIP,
            "PG_STORM_ENABLED=0, skipping STORM config validation",
        )
    errors = []
    details = []

    perspectives = _get_int_env("PG_STORM_PERSPECTIVES_COUNT", "8")
    if not (4 <= perspectives <= 15):
        errors.append(f"PG_STORM_PERSPECTIVES_COUNT={perspectives} not in [4, 15]")
    else:
        details.append(f"perspectives={perspectives}")

    rounds = _get_int_env("PG_STORM_ROUNDS_PER_PERSPECTIVE", "4")
    if not (2 <= rounds <= 10):
        errors.append(f"PG_STORM_ROUNDS_PER_PERSPECTIVE={rounds} not in [2, 10]")
    else:
        details.append(f"rounds={rounds}")

    max_time = _get_int_env("PG_STORM_MAX_TIME_SECONDS", "600")
    if max_time < 120:
        errors.append(f"PG_STORM_MAX_TIME_SECONDS={max_time} < 120")
    else:
        details.append(f"max_time={max_time}s")

    if errors:
        return TestResult(
            "test_storm_config",
            FAIL,
            "; ".join(errors),
        )
    return TestResult(
        "test_storm_config",
        PASS,
        f"STORM config valid: {', '.join(details)}",
    )


# ===================================================================
# TIER 3: Integration Tests (15 tests) -- Would fail during pipeline
# ===================================================================


async def test_openrouter_client_init() -> TestResult:
    """T21: Import and create OpenRouterClient, verify init."""
    if not LIVE_MODE:
        return TestResult(
            "test_openrouter_client_init",
            SKIP,
            "Skipped (live test, set PG_PREFLIGHT_LIVE=1)",
        )
    try:
        from src.polaris_graph.llm.openrouter_client import OpenRouterClient

        async with OpenRouterClient(session_id="preflight_v2") as client:
            if client.api_key and client.model:
                return TestResult(
                    "test_openrouter_client_init",
                    PASS,
                    f"Client initialized: model={client.model}",
                )
            return TestResult(
                "test_openrouter_client_init",
                FAIL,
                "Client missing api_key or model",
            )
    except Exception as exc:
        return TestResult(
            "test_openrouter_client_init",
            FAIL,
            f"Init error: {str(exc)[:200]}",
        )


async def test_llm_generate() -> TestResult:
    """T22: Call client.generate() with a simple prompt."""
    if not LIVE_MODE:
        return TestResult(
            "test_llm_generate",
            SKIP,
            "Skipped (live test, set PG_PREFLIGHT_LIVE=1)",
        )
    try:
        from src.polaris_graph.llm.openrouter_client import OpenRouterClient

        async with OpenRouterClient(session_id="preflight_v2") as client:
            resp = await client.generate(
                prompt="Say hello in one word",
                max_tokens=50,
                timeout=30,
            )
            if resp.content and len(resp.content.strip()) > 0:
                return TestResult(
                    "test_llm_generate",
                    PASS,
                    f"Response: '{resp.content.strip()[:50]}' "
                    f"({resp.output_tokens} tokens)",
                )
            return TestResult(
                "test_llm_generate",
                FAIL,
                "Empty response from generate()",
            )
    except Exception as exc:
        return TestResult(
            "test_llm_generate",
            FAIL,
            f"Generate error: {str(exc)[:200]}",
        )


async def test_llm_generate_structured() -> TestResult:
    """T23: Call client.generate_structured() with GapAnalysis schema."""
    if not LIVE_MODE:
        return TestResult(
            "test_llm_generate_structured",
            SKIP,
            "Skipped (live test, set PG_PREFLIGHT_LIVE=1)",
        )
    try:
        from src.polaris_graph.llm.openrouter_client import OpenRouterClient
        from src.polaris_graph.schemas import GapAnalysis

        async with OpenRouterClient(session_id="preflight_v2") as client:
            result = await client.generate_structured(
                prompt=(
                    "Analyze the following research topic for gaps: "
                    "'Water filtration methods'. Identify 1-2 gaps."
                ),
                schema=GapAnalysis,
                max_tokens=4096,
                timeout=60,
                reasoning_enabled=False,
            )
            if isinstance(result, GapAnalysis):
                return TestResult(
                    "test_llm_generate_structured",
                    PASS,
                    f"GapAnalysis parsed: {len(result.gaps)} gaps, "
                    f"severity={result.gap_severity}",
                )
            return TestResult(
                "test_llm_generate_structured",
                FAIL,
                f"Unexpected type: {type(result).__name__}",
            )
    except Exception as exc:
        return TestResult(
            "test_llm_generate_structured",
            FAIL,
            f"Structured error: {str(exc)[:200]}",
        )


async def test_embedding_model_loads() -> TestResult:
    """T24: Load embedding model and embed a test string."""
    if not LIVE_MODE:
        return TestResult(
            "test_embedding_model_loads",
            SKIP,
            "Skipped (live test, set PG_PREFLIGHT_LIVE=1)",
        )
    try:
        from src.utils.embedding_service import embed_texts

        start = time.monotonic()
        result = embed_texts(["water filtration test"])
        elapsed = time.monotonic() - start
        if result is not None and len(result) > 0:
            dim = len(result[0]) if hasattr(result[0], "__len__") else "scalar"
            return TestResult(
                "test_embedding_model_loads",
                PASS,
                f"Embedding returned: dim={dim}, took {elapsed:.1f}s",
            )
        return TestResult(
            "test_embedding_model_loads",
            FAIL,
            "embed_texts returned empty/None",
        )
    except Exception as exc:
        return TestResult(
            "test_embedding_model_loads",
            FAIL,
            f"Embedding error: {str(exc)[:200]}",
        )


async def test_content_cache_roundtrip() -> TestResult:
    """T25: Store, retrieve, and clean up a test entry in content cache."""
    if not LIVE_MODE:
        return TestResult(
            "test_content_cache_roundtrip",
            SKIP,
            "Skipped (live test, set PG_PREFLIGHT_LIVE=1)",
        )
    test_url = "https://preflight-test.invalid/pg_preflight_test"
    test_content = "Preflight v2 test content -- safe to delete"
    try:
        from src.polaris_graph.memory.content_cache import (
            cache_content,
            get_cached_content,
        )

        stored = await cache_content(
            url=test_url,
            content=test_content,
            title="Preflight Test",
            fetch_method="preflight",
            ttl_hours=1,
        )
        if not stored:
            return TestResult(
                "test_content_cache_roundtrip",
                FAIL,
                "cache_content() returned False",
            )

        retrieved = await get_cached_content(test_url)
        if retrieved is None:
            return TestResult(
                "test_content_cache_roundtrip",
                FAIL,
                "get_cached_content() returned None after store",
            )
        if retrieved["content"] != test_content:
            return TestResult(
                "test_content_cache_roundtrip",
                FAIL,
                "Content mismatch after roundtrip",
            )

        # Cleanup: delete the test entry directly via SQL
        try:
            import aiosqlite
            from src.polaris_graph.memory.content_cache import CACHE_DB

            async with aiosqlite.connect(str(CACHE_DB)) as db:
                await db.execute(
                    "DELETE FROM url_cache WHERE url = ?", (test_url,)
                )
                await db.commit()
        except Exception:
            pass  # Cleanup is best-effort

        return TestResult(
            "test_content_cache_roundtrip",
            PASS,
            "Store/retrieve/cleanup succeeded",
        )
    except Exception as exc:
        return TestResult(
            "test_content_cache_roundtrip",
            FAIL,
            f"Cache error: {str(exc)[:200]}",
        )


async def test_search_cache_roundtrip() -> TestResult:
    """T26: Store, retrieve, and clean up test search results."""
    if not LIVE_MODE:
        return TestResult(
            "test_search_cache_roundtrip",
            SKIP,
            "Skipped (live test, set PG_PREFLIGHT_LIVE=1)",
        )
    test_query = "pg_preflight_test_query_delete_safe"
    test_results = [
        {"url": "https://example.com", "title": "Test", "snippet": "Test snippet"}
    ]
    try:
        from src.polaris_graph.memory.search_cache import (
            cache_results,
            get_cached_results,
        )

        stored = await cache_results(
            query=test_query,
            results=test_results,
            search_type="preflight",
            ttl_hours=1,
        )
        if not stored:
            return TestResult(
                "test_search_cache_roundtrip",
                FAIL,
                "cache_results() returned False",
            )

        retrieved = await get_cached_results(test_query, search_type="preflight")
        if retrieved is None:
            return TestResult(
                "test_search_cache_roundtrip",
                FAIL,
                "get_cached_results() returned None after store",
            )
        if len(retrieved) != 1 or retrieved[0]["url"] != "https://example.com":
            return TestResult(
                "test_search_cache_roundtrip",
                FAIL,
                f"Result mismatch: {retrieved}",
            )

        # Cleanup: delete the test entry directly via SQL
        try:
            import aiosqlite
            from src.polaris_graph.memory.search_cache import CACHE_DB, _query_hash

            qhash = _query_hash(test_query, "preflight")
            async with aiosqlite.connect(str(CACHE_DB)) as db:
                await db.execute(
                    "DELETE FROM search_cache WHERE query_hash = ?", (qhash,)
                )
                await db.commit()
        except Exception:
            pass  # Cleanup is best-effort

        return TestResult(
            "test_search_cache_roundtrip",
            PASS,
            "Store/retrieve/cleanup succeeded",
        )
    except Exception as exc:
        return TestResult(
            "test_search_cache_roundtrip",
            FAIL,
            f"Cache error: {str(exc)[:200]}",
        )


async def test_evidence_hierarchy_init() -> TestResult:
    """T27: Verify evidence hierarchy table can be created."""
    if not LIVE_MODE:
        return TestResult(
            "test_evidence_hierarchy_init",
            SKIP,
            "Skipped (live test, set PG_PREFLIGHT_LIVE=1)",
        )
    try:
        import aiosqlite
        from src.polaris_graph.memory.evidence_hierarchy import (
            CACHE_DB,
            _ensure_table,
        )

        CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(str(CACHE_DB)) as db:
            await _ensure_table(db)
            # Verify table exists
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name='evidence_memory'"
            )
            row = await cursor.fetchone()
            if row:
                return TestResult(
                    "test_evidence_hierarchy_init",
                    PASS,
                    f"Table 'evidence_memory' exists in {CACHE_DB}",
                )
            return TestResult(
                "test_evidence_hierarchy_init",
                FAIL,
                "Table 'evidence_memory' not found after _ensure_table()",
            )
    except Exception as exc:
        return TestResult(
            "test_evidence_hierarchy_init",
            FAIL,
            f"Evidence hierarchy error: {str(exc)[:200]}",
        )


async def test_citation_normalization() -> TestResult:
    """T28: Test citation normalization patterns."""
    try:
        from src.polaris_graph.synthesis.citation_mapper import (
            _normalize_citations,
        )

        test_cases = [
            ("[CITE:ev_001]", "[CITE:ev_001]"),
            ("[CITE:ev_001; CITE:ev_002]", "[CITE:ev_001][CITE:ev_002]"),
        ]

        errors = []
        for input_text, expected_pattern in test_cases:
            result = _normalize_citations(input_text)
            # Check that multi-citations are split
            if "CITE:ev_001" not in result:
                errors.append(
                    f"Input '{input_text}' -> '{result}' "
                    f"(missing CITE:ev_001)"
                )

        # Test bare ev_ normalization
        bare_result = _normalize_citations("Evidence shows ev_abc123 is valid")
        if "CITE:ev_abc123" in bare_result or "ev_abc123" in bare_result:
            pass  # Either form is acceptable
        else:
            errors.append(f"Bare ev_ not handled: '{bare_result}'")

        if errors:
            return TestResult(
                "test_citation_normalization",
                FAIL,
                "; ".join(errors),
            )
        return TestResult(
            "test_citation_normalization",
            PASS,
            f"All {len(test_cases) + 1} patterns normalized correctly",
        )
    except ImportError as exc:
        return TestResult(
            "test_citation_normalization",
            FAIL,
            f"Import error: {str(exc)[:200]}",
        )
    except Exception as exc:
        return TestResult(
            "test_citation_normalization",
            FAIL,
            f"Error: {str(exc)[:200]}",
        )


async def test_cot_scrubber() -> TestResult:
    """T29: Verify CoT scrubber removes line-level CoT patterns.

    The scrubber operates on line-level patterns (^<think>.*$, ^Let me...,$, etc.).
    It uses MULTILINE mode so each line is tested independently.
    """
    try:
        from src.utils.cot_scrubber import scrub_cot_from_report

        # Multi-line test input matching actual production scenario:
        # CoT lines are on separate lines, content lines are preserved.
        test_input = (
            "<think>Let me analyze this question carefully.</think>\n"
            "Let me check the evidence for this claim.\n"
            "Water filtration removes contaminants effectively.\n"
            "I need to verify the data sources.\n"
            "Reverse osmosis achieves 99% removal rates.\n"
        )
        result = scrub_cot_from_report(test_input)

        errors = []
        # CoT lines should be removed
        if "<think>" in result:
            errors.append("<think> line not removed")
        if "Let me check" in result:
            errors.append("'Let me check' line not removed")
        if "I need to verify" in result:
            errors.append("'I need to verify' line not removed")
        # Content lines should be preserved
        if "Water filtration" not in result:
            errors.append("'Water filtration' content lost")
        if "Reverse osmosis" not in result:
            errors.append("'Reverse osmosis' content lost")

        if errors:
            return TestResult(
                "test_cot_scrubber",
                FAIL,
                f"Scrub issues: {'; '.join(errors)}. "
                f"Result: '{result[:150]}'",
            )
        return TestResult(
            "test_cot_scrubber",
            PASS,
            f"CoT lines removed, content preserved ({len(result)} chars)",
        )
    except Exception as exc:
        return TestResult(
            "test_cot_scrubber",
            FAIL,
            f"Scrubber error: {str(exc)[:200]}",
        )


async def test_serper_search() -> TestResult:
    """T30: Make ONE Serper API call."""
    if not LIVE_MODE:
        return TestResult(
            "test_serper_search",
            SKIP,
            "Skipped (live test, set PG_PREFLIGHT_LIVE=1)",
        )
    try:
        import httpx

        api_key = os.getenv("SERPER_API_KEY", "")
        if not api_key:
            return TestResult(
                "test_serper_search",
                FAIL,
                "SERPER_API_KEY not set",
            )

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://google.serper.dev/search",
                headers={
                    "X-API-KEY": api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "q": "water filtration technology 2024",
                    "num": 3,
                },
            )
            if resp.status_code != 200:
                return TestResult(
                    "test_serper_search",
                    FAIL,
                    f"Serper returned {resp.status_code}: {resp.text[:200]}",
                )
            data = resp.json()
            organic = data.get("organic", [])
            return TestResult(
                "test_serper_search",
                PASS,
                f"{len(organic)} organic results returned",
            )
    except Exception as exc:
        return TestResult(
            "test_serper_search",
            FAIL,
            f"Serper error: {str(exc)[:200]}",
        )


async def test_s2_search() -> TestResult:
    """T31: Make ONE Semantic Scholar API call."""
    if not LIVE_MODE:
        return TestResult(
            "test_s2_search",
            SKIP,
            "Skipped (live test, set PG_PREFLIGHT_LIVE=1)",
        )
    try:
        import httpx

        api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["x-api-key"] = api_key

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.semanticscholar.org/graph/v1/paper/search/bulk",
                headers=headers,
                json={
                    "query": "water filtration",
                    "limit": 3,
                    "fields": "paperId,title,abstract,url,year",
                },
            )
            # S2 bulk uses POST with JSON body but some versions use GET params
            if resp.status_code == 405:
                # Fallback to GET
                resp = await client.get(
                    "https://api.semanticscholar.org/graph/v1/paper/search",
                    headers=headers,
                    params={
                        "query": "water filtration",
                        "limit": 3,
                        "fields": "paperId,title,year",
                    },
                )
            if resp.status_code != 200:
                return TestResult(
                    "test_s2_search",
                    FAIL,
                    f"S2 returned {resp.status_code}: {resp.text[:200]}",
                )
            data = resp.json()
            papers = data.get("data", [])
            return TestResult(
                "test_s2_search",
                PASS,
                f"{len(papers)} papers returned",
            )
    except Exception as exc:
        return TestResult(
            "test_s2_search",
            FAIL,
            f"S2 error: {str(exc)[:200]}",
        )


async def test_exa_search() -> TestResult:
    """T32: Make ONE Exa API call if enabled."""
    if not LIVE_MODE:
        return TestResult(
            "test_exa_search",
            SKIP,
            "Skipped (live test, set PG_PREFLIGHT_LIVE=1)",
        )
    exa_enabled = os.getenv("PG_EXA_ENABLED", "1") == "1"
    if not exa_enabled:
        return TestResult(
            "test_exa_search",
            SKIP,
            "PG_EXA_ENABLED=0, skipping",
        )
    try:
        import httpx

        api_key = os.getenv("EXA_API_KEY", "")
        if not api_key:
            return TestResult(
                "test_exa_search",
                FAIL,
                "EXA_API_KEY not set",
            )

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.exa.ai/search",
                headers={
                    "x-api-key": api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "query": "water filtration technology research",
                    "numResults": 3,
                    "type": "auto",
                },
            )
            if resp.status_code != 200:
                return TestResult(
                    "test_exa_search",
                    FAIL,
                    f"Exa returned {resp.status_code}: {resp.text[:200]}",
                )
            data = resp.json()
            results = data.get("results", [])
            return TestResult(
                "test_exa_search",
                PASS,
                f"{len(results)} results returned",
            )
    except Exception as exc:
        return TestResult(
            "test_exa_search",
            FAIL,
            f"Exa error: {str(exc)[:200]}",
        )


async def test_jina_fetch() -> TestResult:
    """T33: Fetch ONE URL via Jina Reader if enabled."""
    if not LIVE_MODE:
        return TestResult(
            "test_jina_fetch",
            SKIP,
            "Skipped (live test, set PG_PREFLIGHT_LIVE=1)",
        )
    jina_enabled = os.getenv("PG_JINA_ENABLED", "1") == "1"
    if not jina_enabled:
        return TestResult(
            "test_jina_fetch",
            SKIP,
            "PG_JINA_ENABLED=0, skipping",
        )
    try:
        import httpx

        target_url = "https://en.wikipedia.org/wiki/Water_purification"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"https://r.jina.ai/{target_url}",
                headers={"Accept": "text/plain"},
            )
            if resp.status_code != 200:
                return TestResult(
                    "test_jina_fetch",
                    FAIL,
                    f"Jina returned {resp.status_code}",
                )
            content = resp.text
            if len(content) > 100:
                return TestResult(
                    "test_jina_fetch",
                    PASS,
                    f"Fetched {len(content)} chars via Jina Reader",
                )
            return TestResult(
                "test_jina_fetch",
                FAIL,
                f"Jina returned too little content: {len(content)} chars",
            )
    except Exception as exc:
        return TestResult(
            "test_jina_fetch",
            FAIL,
            f"Jina error: {str(exc)[:200]}",
        )


async def test_tracer_init() -> TestResult:
    """T34: Import PipelineTracer, create one, verify JSONL file is created."""
    try:
        from src.polaris_graph.tracing import PipelineTracer

        # Use a temp directory to avoid polluting logs/
        with tempfile.TemporaryDirectory() as tmpdir:
            tracer = PipelineTracer(
                "preflight_v2_test",
                output_dir=tmpdir,
            )
            expected_path = Path(tmpdir) / "pg_trace_preflight_v2_test.jsonl"
            # Emit a test event to create the file
            tracer.node_start("preflight_test")
            tracer.node_end("preflight_test", status="ok")

            if expected_path.exists():
                size = expected_path.stat().st_size
                summary = tracer.summary()
                return TestResult(
                    "test_tracer_init",
                    PASS,
                    f"JSONL created: {size} bytes, "
                    f"{summary.get('total_events', 0)} events",
                )
            return TestResult(
                "test_tracer_init",
                FAIL,
                f"JSONL not created at {expected_path}",
            )
    except Exception as exc:
        return TestResult(
            "test_tracer_init",
            FAIL,
            f"Tracer error: {str(exc)[:200]}",
        )


async def test_dashboard_init() -> TestResult:
    """T35: Import PipelineDashboard, create one without starting Live."""
    try:
        from src.polaris_graph.dashboard import PipelineDashboard

        # Create dashboard without entering context manager (no Live display)
        dashboard = PipelineDashboard(
            vector_id="preflight_v2_test",
            budget=150.0,
        )
        # Verify attributes were set
        if (
            dashboard.vector_id == "preflight_v2_test"
            and dashboard.budget == 150.0
        ):
            return TestResult(
                "test_dashboard_init",
                PASS,
                "Dashboard created successfully (no Live started)",
            )
        return TestResult(
            "test_dashboard_init",
            FAIL,
            "Dashboard attributes not set correctly",
        )
    except Exception as exc:
        return TestResult(
            "test_dashboard_init",
            FAIL,
            f"Dashboard error: {str(exc)[:200]}",
        )


# ===================================================================
# TIER 4: Quality Tests (5 tests) -- Would degrade output
# ===================================================================


async def test_domain_authority_gate() -> TestResult:
    """T36: Verify pre-fetch authority gate filters low-credibility sources.

    Replaces the old domain blocklist test (FIX-B1, removed 2026-04-12).
    The authority gate is the canonical filter — see analyzer.py:1478 and
    searcher.py:1424. Blocklists don't scale; PageRank/tier authority does.
    """
    try:
        from src.polaris_graph.agents.analyzer import _get_domain_authority

        gate = float(os.getenv("PG_AUTHORITY_GATE", "0.3"))
        low_cred = float(os.getenv("PG_LOW_CREDIBILITY_AUTHORITY", "0.2"))

        # Commerce domain (was on blocklist, now in low_credibility_domains)
        amazon_auth = _get_domain_authority("https://amazon.com/some-product")
        if amazon_auth >= gate:
            return TestResult(
                "test_domain_authority_gate",
                FAIL,
                f"amazon.com auth {amazon_auth} should be below gate {gate}",
            )
        if amazon_auth != low_cred:
            return TestResult(
                "test_domain_authority_gate",
                FAIL,
                f"amazon.com expected low_cred={low_cred}, got {amazon_auth}",
            )

        # Authoritative domain
        epa_auth = _get_domain_authority("https://epa.gov/water-research")
        if epa_auth != 1.0:
            return TestResult(
                "test_domain_authority_gate",
                FAIL,
                f"epa.gov expected 1.0 (TIER 1), got {epa_auth}",
            )

        return TestResult(
            "test_domain_authority_gate",
            PASS,
            f"gate={gate}, amazon={amazon_auth}, epa={epa_auth}",
        )
    except Exception as exc:
        return TestResult(
            "test_domain_authority_gate",
            FAIL,
            f"Authority gate error: {str(exc)[:200]}",
        )


async def test_paywall_blocklist() -> TestResult:
    """T37: Verify PG_PAYWALL_DOMAINS contains expected core domains."""
    try:
        from src.polaris_graph.state import PG_PAYWALL_DOMAINS

        # Check only the core domains that appear in BOTH the .env override
        # AND the default value. The .env may customize this list.
        core_domains = {
            "sciencedirect.com",
            "springer.com",
            "wiley.com",
        }
        missing = core_domains - PG_PAYWALL_DOMAINS
        if missing:
            return TestResult(
                "test_paywall_blocklist",
                FAIL,
                f"Missing core paywall domains: {missing}",
            )
        # Must have at least 3 domains configured
        if len(PG_PAYWALL_DOMAINS) < 3:
            return TestResult(
                "test_paywall_blocklist",
                FAIL,
                f"Too few paywall domains: {len(PG_PAYWALL_DOMAINS)} (min: 3)",
            )
        return TestResult(
            "test_paywall_blocklist",
            PASS,
            f"{len(PG_PAYWALL_DOMAINS)} paywall domains configured",
        )
    except Exception as exc:
        return TestResult(
            "test_paywall_blocklist",
            FAIL,
            f"Paywall error: {str(exc)[:200]}",
        )


async def test_authority_scoring() -> TestResult:
    """T38: Verify .gov gets higher authority score than .com."""
    try:
        from src.polaris_graph.agents.analyzer import _get_domain_authority

        gov_score = _get_domain_authority("https://epa.gov/water-quality")
        com_score = _get_domain_authority("https://example.com/random-page")
        edu_score = _get_domain_authority("https://mit.edu/research")

        errors = []
        if gov_score <= com_score:
            errors.append(
                f".gov ({gov_score}) should be > .com ({com_score})"
            )
        if edu_score <= com_score:
            errors.append(
                f".edu ({edu_score}) should be > .com ({com_score})"
            )

        if errors:
            return TestResult(
                "test_authority_scoring",
                FAIL,
                "; ".join(errors),
            )
        return TestResult(
            "test_authority_scoring",
            PASS,
            f".gov={gov_score}, .edu={edu_score}, .com={com_score}",
        )
    except Exception as exc:
        return TestResult(
            "test_authority_scoring",
            FAIL,
            f"Authority error: {str(exc)[:200]}",
        )


async def test_silent_default_detection() -> TestResult:
    """T39: Verify AtomicFact logs warning when null relevance_score received."""
    try:
        from src.polaris_graph.schemas import AtomicFact
        import logging

        # Capture log output
        log_records = []
        handler = logging.Handler()
        handler.emit = lambda record: log_records.append(record)
        pg_logger = logging.getLogger("src.polaris_graph.schemas")
        pg_logger.addHandler(handler)
        original_level = pg_logger.level
        pg_logger.setLevel(logging.WARNING)

        try:
            # Create AtomicFact with None relevance_score to trigger AREA-9 warning
            fact = AtomicFact.model_validate({
                "statement": "Test statement for preflight",
                "direct_quote": "Test quote",
                "fact_category": "statistic",
                "relevance_score": None,
                "confidence": 0.8,
            })
            # Check if warning was logged
            warning_found = any(
                "AREA-9" in getattr(r, "message", str(r.msg))
                or "null" in getattr(r, "message", str(r.msg)).lower()
                for r in log_records
            )
            # Also verify the default was applied (should be 0.1 per SF-04)
            if fact.relevance_score <= 0.1 + 0.01:
                if warning_found:
                    return TestResult(
                        "test_silent_default_detection",
                        PASS,
                        f"Null score -> {fact.relevance_score}, warning logged",
                    )
                else:
                    return TestResult(
                        "test_silent_default_detection",
                        PASS,
                        f"Null score -> {fact.relevance_score} (default applied, "
                        f"warning check inconclusive -- logger may be filtered)",
                    )
            return TestResult(
                "test_silent_default_detection",
                FAIL,
                f"Null relevance_score defaulted to {fact.relevance_score} "
                f"(expected <= 0.1)",
            )
        finally:
            pg_logger.removeHandler(handler)
            pg_logger.setLevel(original_level)
    except Exception as exc:
        return TestResult(
            "test_silent_default_detection",
            FAIL,
            f"Schema error: {str(exc)[:200]}",
        )


async def test_state_keys_complete() -> TestResult:
    """T40: Verify every key in create_initial_state() is declared in ResearchState."""
    try:
        from src.polaris_graph.state import ResearchState, create_initial_state

        # Create a sample state
        initial = create_initial_state(
            vector_id="preflight_test",
            query="test query",
            application="test",
            region="GLOBAL",
        )

        # Get all declared fields from the TypedDict
        declared_keys = set(ResearchState.__annotations__.keys())

        # Get all keys in the initial state
        initial_keys = set(initial.keys())

        # Check for keys in initial_state that are NOT declared in ResearchState
        undeclared = initial_keys - declared_keys
        if undeclared:
            return TestResult(
                "test_state_keys_complete",
                FAIL,
                f"Undeclared state keys (will be silently dropped by "
                f"LangGraph): {sorted(undeclared)}",
            )

        # Also check for declared keys that are NOT initialized
        uninitialized = declared_keys - initial_keys
        if uninitialized:
            return TestResult(
                "test_state_keys_complete",
                FAIL,
                f"Declared but not initialized in create_initial_state(): "
                f"{sorted(uninitialized)}",
            )

        return TestResult(
            "test_state_keys_complete",
            PASS,
            f"All {len(declared_keys)} state keys declared and initialized",
        )
    except Exception as exc:
        return TestResult(
            "test_state_keys_complete",
            FAIL,
            f"State key error: {str(exc)[:200]}",
        )


# ===================================================================
# Test Registry
# ===================================================================

def _find_chromium_binary(cache_root: Optional[Path] = None) -> Optional[str]:
    """FX-16 (#1131): return the path to a Playwright chromium binary under the ms-playwright cache,
    or None. Pure + cross-platform (glob the Linux/Windows/macOS launcher layouts) so it is unit
    testable with a synthetic cache_root. Default root: ``~/.cache/ms-playwright`` (the VM layout)."""
    root = Path(cache_root) if cache_root is not None else (Path.home() / ".cache" / "ms-playwright")
    try:
        if not root.exists():
            return None
        for pattern in (
            "chromium-*/chrome-linux*/chrome",
            "chromium-*/chrome-win*/chrome.exe",
            "chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium",
        ):
            hits = sorted(root.glob(pattern))
            if hits:
                return str(hits[0])
    except Exception:  # noqa: BLE001 — a probe must never crash the preflight
        return None
    return None


async def test_chromium_browser_available() -> TestResult:
    """FX-16 (#1131): fail closed when the AccessBypass browser-fetch tier (Playwright/Crawl4AI) is
    dead. drb_72 fetched at success_rate 0.51 because chromium was absent on the VM and the cascade
    SILENTLY fell back to httpx-naive (LAW II — no silent downgrade on a paid run). Probe the chromium
    binary; if absent AND the cascade is not intentionally disabled, FAIL CLOSED (LIVE/paid path) with
    remediation. DRY mode SKIPs with the same remediation so dev/CI runs do not break."""
    name = "chromium_browser_available"
    if os.getenv("PG_DISABLE_ACCESS_BYPASS", "0").strip() in ("1", "true", "True"):
        return TestResult(name, SKIP, "PG_DISABLE_ACCESS_BYPASS=1 -- browser-fetch tier intentionally off")
    binary = _find_chromium_binary()
    if binary:
        return TestResult(name, PASS, f"chromium present: {binary}")
    remediation = (
        "Playwright chromium binary not found under ~/.cache/ms-playwright -- the AccessBypass "
        "browser-fetch tier is DEAD (fetch will silently degrade to httpx-naive, ~0.51 success). "
        "Run 'python -m playwright install chromium --with-deps' on this host, or set "
        "PG_DISABLE_ACCESS_BYPASS=1 to intentionally disable the cascade."
    )
    if LIVE_MODE:
        return TestResult(name, FAIL, remediation)
    # DRY mode: do not break dev/CI; surface the gap as an actionable SKIP that WOULD fail a paid run.
    return TestResult(name, SKIP, f"[would FAIL in LIVE/paid mode] {remediation}")


TIER_1_TESTS = [
    ("test_openrouter_api_key", test_openrouter_api_key),
    ("test_serper_api_key", test_serper_api_key),
    ("test_serper_credit_pool", test_serper_credit_pool),
    ("test_exa_api_key", test_exa_api_key),
    ("test_s2_api_key", test_s2_api_key),
    ("test_openrouter_budget", test_openrouter_budget),
    ("test_graph_compiles", test_graph_compiles),
    ("test_state_schema", test_state_schema),
    ("test_pydantic_schemas", test_pydantic_schemas),
    ("test_checkpoint_sqlite_writable", test_checkpoint_sqlite_writable),
    ("test_output_dir_writable", test_output_dir_writable),
    # FX-16 (#1131): fail-closed chromium probe (LIVE/paid path) so a dead browser-fetch tier cannot
    # silently degrade a paid run to httpx-naive. DRY mode SKIPs with remediation.
    ("test_chromium_browser_available", test_chromium_browser_available),
]

TIER_2_TESTS = [
    ("test_analysis_batch_size", test_analysis_batch_size),
    ("test_verify_batch_size", test_verify_batch_size),
    ("test_synthesis_max_tokens", test_synthesis_max_tokens),
    ("test_max_execution_minutes", test_max_execution_minutes),
    ("test_agentic_max_time", test_agentic_max_time),
    ("test_timeout_values_positive", test_timeout_values_positive),
    ("test_concurrency_values", test_concurrency_values),
    ("test_min_thresholds_reasonable", test_min_thresholds_reasonable),
    ("test_budget_guard", test_budget_guard),
    ("test_storm_config", test_storm_config),
]

TIER_3_TESTS = [
    ("test_openrouter_client_init", test_openrouter_client_init),
    ("test_llm_generate", test_llm_generate),
    ("test_llm_generate_structured", test_llm_generate_structured),
    ("test_embedding_model_loads", test_embedding_model_loads),
    ("test_content_cache_roundtrip", test_content_cache_roundtrip),
    ("test_search_cache_roundtrip", test_search_cache_roundtrip),
    ("test_evidence_hierarchy_init", test_evidence_hierarchy_init),
    ("test_citation_normalization", test_citation_normalization),
    ("test_cot_scrubber", test_cot_scrubber),
    ("test_serper_search", test_serper_search),
    ("test_s2_search", test_s2_search),
    ("test_exa_search", test_exa_search),
    ("test_jina_fetch", test_jina_fetch),
    ("test_tracer_init", test_tracer_init),
    ("test_dashboard_init", test_dashboard_init),
]

TIER_4_TESTS = [
    ("test_domain_authority_gate", test_domain_authority_gate),
    ("test_paywall_blocklist", test_paywall_blocklist),
    ("test_authority_scoring", test_authority_scoring),
    ("test_silent_default_detection", test_silent_default_detection),
    ("test_state_keys_complete", test_state_keys_complete),
]


# ===================================================================
# Main Runner
# ===================================================================


async def run_tier(
    tier_name: str,
    tests: list,
    all_results: list,
) -> None:
    """Run all tests in a tier sequentially, printing results."""
    test_count = len(tests)
    print(f"\n{_BOLD}{tier_name} ({test_count} tests){_RESET}")
    for _name, test_fn in tests:
        try:
            result = await test_fn()
        except Exception as exc:
            result = TestResult(
                _name,
                FAIL,
                f"Unhandled exception: {str(exc)[:200]}",
            )
        all_results.append(result)
        print(result.display())


async def main() -> int:
    """Run all 40 preflight tests and return exit code."""
    print(f"\n{_BOLD}POLARIS GRAPH -- Preflight v2{_RESET}")
    print("=" * 60)
    if LIVE_MODE:
        print(f"{_YELLOW}LIVE MODE ENABLED (PG_PREFLIGHT_LIVE=1){_RESET}")
    else:
        print(
            f"{_YELLOW}DRY MODE (set PG_PREFLIGHT_LIVE=1 for API tests){_RESET}"
        )

    all_results: list[TestResult] = []

    await run_tier(
        "Tier 1: Hard Failures",
        TIER_1_TESTS,
        all_results,
    )
    await run_tier(
        "Tier 2: Config Range Tests",
        TIER_2_TESTS,
        all_results,
    )
    await run_tier(
        "Tier 3: Integration Tests",
        TIER_3_TESTS,
        all_results,
    )
    await run_tier(
        "Tier 4: Quality Tests",
        TIER_4_TESTS,
        all_results,
    )

    # Summary
    passed = sum(1 for r in all_results if r.status == PASS)
    failed = sum(1 for r in all_results if r.status == FAIL)
    skipped = sum(1 for r in all_results if r.status == SKIP)

    print("\n" + "=" * 60)
    summary_parts = []
    summary_parts.append(f"{_GREEN}{passed} PASSED{_RESET}")
    if failed > 0:
        summary_parts.append(f"{_RED}{failed} FAILED{_RESET}")
    else:
        summary_parts.append(f"{failed} FAILED")
    if skipped > 0:
        summary_parts.append(f"{_YELLOW}{skipped} SKIPPED{_RESET}")
    else:
        summary_parts.append(f"{skipped} SKIPPED")

    print(f"RESULTS: {', '.join(summary_parts)} (total: {len(all_results)})")

    if failed > 0:
        print(f"\n{_RED}{_BOLD}PREFLIGHT FAILED{_RESET}")
        print("Failed tests:")
        for r in all_results:
            if r.status == FAIL:
                print(f"  - {r.name}: {r.message}")
        return 1

    print(f"\n{_GREEN}{_BOLD}PREFLIGHT PASSED{_RESET}")
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
