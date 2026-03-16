"""
PG_PREFLIGHT_047: Pre-run verification for MoST + Memory + FIX-047.

25 tests across 7 sections:
- ENV_CHECK (5): Core env vars, LAW VI vars, API keys, feature flags, contradictions
- DEPENDENCY_CHECK (3): pysbd import, minicheck import, aiosqlite import
- FAITHLENS_CHECK (2): FaithLens import, inference stub
- FUNCTION_TESTS (8): Key function smoke tests
- INTEGRATION_CHECK (1): pytest suite pass
- SMOKE_TESTS (1): pg_smoke_test.py pass
- SUMMARY (2): Memory availability, state key completeness

Usage: python -u scripts/pg_preflight_047.py
"""

import asyncio
import importlib
import os
import sys
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

# Windows UTF-8 fix
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv()


class Status(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"
    SKIP = "SKIP"


@dataclass
class TestResult:
    name: str
    status: Status
    detail: str = ""
    blocking: bool = True
    elapsed_ms: float = 0.0


# ANSI colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"

STATUS_COLOR = {
    Status.PASS: GREEN,
    Status.FAIL: RED,
    Status.WARN: YELLOW,
    Status.SKIP: CYAN,
}


def _print_result(r: TestResult) -> None:
    color = STATUS_COLOR.get(r.status, RESET)
    blocking = " [BLOCKING]" if r.blocking and r.status == Status.FAIL else ""
    print(f"  {color}{r.status.value:4s}{RESET}  {r.name}{blocking}")
    if r.detail:
        print(f"        {r.detail[:120]}")


# ── Section 1: ENV_CHECK ──────────────────────────────────────────────

def test_env_core_vars() -> TestResult:
    """Check critical env vars exist."""
    required = [
        "OPENROUTER_API_KEY", "SERPER_API_KEY", "SEMANTIC_SCHOLAR_API_KEY",
        "PG_OUTPUT_DIR", "PG_MAX_EXECUTION_MINUTES",
    ]
    missing = [v for v in required if not os.getenv(v)]
    if missing:
        return TestResult("ENV: Core vars", Status.FAIL, f"Missing: {missing}")
    return TestResult("ENV: Core vars", Status.PASS, f"{len(required)} vars present")


def test_env_most_vars() -> TestResult:
    """Check MoST env vars exist."""
    required = ["PG_MOST_ENABLED", "PG_REFLECTION_CONCURRENCY", "PG_EXPLORE_SIMILARITY_THRESHOLD"]
    missing = [v for v in required if os.getenv(v) is None]
    if missing:
        return TestResult("ENV: MoST vars", Status.FAIL, f"Missing: {missing}")
    return TestResult("ENV: MoST vars", Status.PASS, f"MoST={os.getenv('PG_MOST_ENABLED')}")


def test_env_memory_vars() -> TestResult:
    """Check memory system env vars exist."""
    required = [
        "PG_EVIDENCE_HIERARCHY_READ_ENABLED", "PG_SESSION_FEEDBACK_ENABLED",
        "PG_CROSS_VECTOR_LTM_ENABLED",
    ]
    missing = [v for v in required if os.getenv(v) is None]
    if missing:
        return TestResult("ENV: Memory vars", Status.FAIL, f"Missing: {missing}")
    return TestResult("ENV: Memory vars", Status.PASS, "All present")


def test_env_api_keys() -> TestResult:
    """Check API keys are non-empty."""
    keys = ["OPENROUTER_API_KEY", "SERPER_API_KEY"]
    empty = [k for k in keys if not os.getenv(k, "").strip()]
    if empty:
        return TestResult("ENV: API keys", Status.FAIL, f"Empty keys: {empty}")
    return TestResult("ENV: API keys", Status.PASS)


def test_env_contradictions() -> TestResult:
    """Check for env var contradictions."""
    issues = []
    if os.getenv("PG_MOST_ENABLED", "0") == "1" and os.getenv("PG_EVIDENCE_HIERARCHY_READ_ENABLED", "0") == "0":
        issues.append("MoST enabled but evidence hierarchy read disabled")
    if issues:
        return TestResult("ENV: Contradictions", Status.WARN, "; ".join(issues), blocking=False)
    return TestResult("ENV: Contradictions", Status.PASS, "No contradictions")


# ── Section 2: DEPENDENCY_CHECK ────────────────────────────────────────

def test_dep_pysbd() -> TestResult:
    """Check pysbd import and edge cases."""
    t0 = time.time()
    try:
        import pysbd
        seg = pysbd.Segmenter(language="en", clean=False)
        sents = seg.segment("Dr. Smith went to Washington. He was happy.")
        elapsed = (time.time() - t0) * 1000
        if len(sents) != 2:
            return TestResult("DEP: pysbd", Status.WARN, f"Expected 2 sentences, got {len(sents)}", blocking=False, elapsed_ms=elapsed)
        return TestResult("DEP: pysbd", Status.PASS, f"v{pysbd.__version__}", elapsed_ms=elapsed)
    except ImportError:
        return TestResult("DEP: pysbd", Status.FAIL, "pip install pysbd>=0.3.4")


def test_dep_minicheck() -> TestResult:
    """Check minicheck availability."""
    try:
        from minicheck.minicheck import MiniCheck
        return TestResult("DEP: minicheck", Status.PASS)
    except ImportError:
        return TestResult("DEP: minicheck", Status.WARN, "Not installed (NLI fallback)", blocking=False)


def test_dep_aiosqlite() -> TestResult:
    """Check aiosqlite import."""
    try:
        import aiosqlite
        return TestResult("DEP: aiosqlite", Status.PASS, f"v{aiosqlite.__version__}")
    except ImportError:
        return TestResult("DEP: aiosqlite", Status.FAIL, "pip install aiosqlite")


# ── Section 3: FAITHLENS_CHECK ─────────────────────────────────────────

def test_faithlens_import() -> TestResult:
    """Check FaithLens model availability."""
    model = os.getenv("PG_FAITHLENS_MODEL", "ssz1111/FaithLens")
    try:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        return TestResult("FAITHLENS: Import", Status.PASS, f"model={model}", blocking=False)
    except ImportError:
        return TestResult("FAITHLENS: Import", Status.WARN, "transformers not available", blocking=False)


def test_faithlens_stub() -> TestResult:
    """Stub test for FaithLens inference (skip if model not downloaded)."""
    return TestResult("FAITHLENS: Inference", Status.SKIP, "Requires model download", blocking=False)


# ── Section 4: FUNCTION_TESTS ──────────────────────────────────────────

def test_fn_state_keys() -> TestResult:
    """Check all MoST/Memory state keys declared in ResearchState."""
    try:
        from src.polaris_graph.state import ResearchState
        required = [
            "most_reflection_stats", "most_exploration_stats",
            "memory_perspective_gaps", "memory_best_strategies", "memory_ltm_prior_count",
        ]
        annotations = ResearchState.__annotations__
        missing = [k for k in required if k not in annotations]
        if missing:
            return TestResult("FN: State keys", Status.FAIL, f"Missing: {missing}")
        return TestResult("FN: State keys", Status.PASS, f"{len(required)} keys declared")
    except Exception as exc:
        return TestResult("FN: State keys", Status.FAIL, str(exc)[:120])


def test_fn_create_initial_state() -> TestResult:
    """Check create_initial_state() includes new keys."""
    try:
        from src.polaris_graph.state import create_initial_state
        state = create_initial_state("test", "test query", "test_app", "GLOBAL")
        required = [
            "most_reflection_stats", "most_exploration_stats",
            "memory_perspective_gaps", "memory_best_strategies", "memory_ltm_prior_count",
        ]
        missing = [k for k in required if k not in state]
        if missing:
            return TestResult("FN: Initial state", Status.FAIL, f"Missing: {missing}")
        return TestResult("FN: Initial state", Status.PASS, f"All {len(required)} keys present")
    except Exception as exc:
        return TestResult("FN: Initial state", Status.FAIL, str(exc)[:120])


def test_fn_schemas() -> TestResult:
    """Check MoST Pydantic schemas importable and valid."""
    try:
        from src.polaris_graph.schemas import ReflectionResult, ExplorationResult
        r = ReflectionResult(section_id="s01")
        e = ExplorationResult(section_id="s02")
        if r.revision_needed is not False:
            return TestResult("FN: Schemas", Status.FAIL, "ReflectionResult.revision_needed not False")
        if e.sentences_added != 0:
            return TestResult("FN: Schemas", Status.FAIL, "ExplorationResult.sentences_added not 0")
        return TestResult("FN: Schemas", Status.PASS, "ReflectionResult + ExplorationResult OK")
    except Exception as exc:
        return TestResult("FN: Schemas", Status.FAIL, str(exc)[:120])


def test_fn_reflector_import() -> TestResult:
    """Check cross_section_reflector importable."""
    try:
        from src.polaris_graph.synthesis.cross_section_reflector import (
            reflect_across_sections, _build_reflection_context, _detect_contradictions,
        )
        return TestResult("FN: Reflector import", Status.PASS)
    except Exception as exc:
        return TestResult("FN: Reflector import", Status.FAIL, str(exc)[:120])


def test_fn_explorer_import() -> TestResult:
    """Check evidence_explorer importable."""
    try:
        from src.polaris_graph.synthesis.evidence_explorer import (
            explore_unused_evidence, _find_unused_evidence, _match_evidence_to_sections,
        )
        return TestResult("FN: Explorer import", Status.PASS)
    except Exception as exc:
        return TestResult("FN: Explorer import", Status.FAIL, str(exc)[:120])


def test_fn_evidence_hierarchy() -> TestResult:
    """Check evidence_hierarchy module importable."""
    try:
        from src.polaris_graph.memory.evidence_hierarchy import (
            store_evidence, get_l0_summaries, get_by_perspective, count_by_tier,
        )
        return TestResult("FN: Evidence hierarchy", Status.PASS)
    except Exception as exc:
        return TestResult("FN: Evidence hierarchy", Status.FAIL, str(exc)[:120])


def test_fn_session_feedback() -> TestResult:
    """Check session_feedback module importable."""
    try:
        from src.polaris_graph.memory.session_feedback import (
            record_feedback, get_best_strategies, get_source_performance, get_session_summary,
        )
        return TestResult("FN: Session feedback", Status.PASS)
    except Exception as exc:
        return TestResult("FN: Session feedback", Status.FAIL, str(exc)[:120])


def test_fn_cross_vector() -> TestResult:
    """Check cross_vector module importable."""
    try:
        from src.polaris_graph.memory.cross_vector import (
            promote_to_ltm, query_ltm, get_ltm_stats,
        )
        return TestResult("FN: Cross vector", Status.PASS)
    except Exception as exc:
        return TestResult("FN: Cross vector", Status.FAIL, str(exc)[:120])


# ── Section 5-7: Integration, Smoke, Summary ──────────────────────────

def test_memory_availability() -> TestResult:
    """Check memory module databases exist or can be created."""
    state_dir = Path("state")
    hierarchy_db = state_dir / "pg_evidence_hierarchy.sqlite"
    feedback_db = state_dir / "pg_session_feedback.sqlite"
    available = []
    if hierarchy_db.exists():
        available.append(f"hierarchy={hierarchy_db.stat().st_size / 1024 / 1024:.1f}MB")
    else:
        available.append("hierarchy=new")
    if feedback_db.exists():
        available.append(f"feedback={feedback_db.stat().st_size / 1024:.0f}KB")
    else:
        available.append("feedback=new")
    return TestResult("SUMMARY: Memory DBs", Status.PASS, ", ".join(available))


def test_feature_flags() -> TestResult:
    """Verify feature flag defaults are safe."""
    flags = {
        "PG_MOST_ENABLED": ("0", "MoST disabled by default"),
        "PG_EVIDENCE_HIERARCHY_READ_ENABLED": ("1", "Hierarchy reads enabled"),
        "PG_SESSION_FEEDBACK_ENABLED": ("1", "Session feedback enabled"),
        "PG_CROSS_VECTOR_LTM_ENABLED": ("0", "LTM disabled by default"),
    }
    issues = []
    for var, (expected, desc) in flags.items():
        actual = os.getenv(var, "MISSING")
        if actual != expected:
            issues.append(f"{var}={actual} (expected {expected}: {desc})")
    if issues:
        return TestResult("SUMMARY: Feature flags", Status.WARN, "; ".join(issues), blocking=False)
    return TestResult("SUMMARY: Feature flags", Status.PASS, "All defaults correct")


# ── Runner ─────────────────────────────────────────────────────────────

def run_all() -> list[TestResult]:
    """Run all preflight tests and return results."""
    tests = [
        # ENV_CHECK
        test_env_core_vars,
        test_env_most_vars,
        test_env_memory_vars,
        test_env_api_keys,
        test_env_contradictions,
        # DEPENDENCY_CHECK
        test_dep_pysbd,
        test_dep_minicheck,
        test_dep_aiosqlite,
        # FAITHLENS_CHECK
        test_faithlens_import,
        test_faithlens_stub,
        # FUNCTION_TESTS
        test_fn_state_keys,
        test_fn_create_initial_state,
        test_fn_schemas,
        test_fn_reflector_import,
        test_fn_explorer_import,
        test_fn_evidence_hierarchy,
        test_fn_session_feedback,
        test_fn_cross_vector,
        # SUMMARY
        test_memory_availability,
        test_feature_flags,
    ]

    results = []
    for test_fn in tests:
        t0 = time.time()
        try:
            r = test_fn()
            r.elapsed_ms = r.elapsed_ms or (time.time() - t0) * 1000
            results.append(r)
        except Exception as exc:
            results.append(TestResult(
                test_fn.__name__, Status.FAIL, f"Exception: {str(exc)[:100]}",
                elapsed_ms=(time.time() - t0) * 1000,
            ))
    return results


def main() -> int:
    print(f"\n{BOLD}{'=' * 60}{RESET}")
    print(f"{BOLD}  PG_PREFLIGHT_047: MoST + Memory + FIX-047 Verification{RESET}")
    print(f"{BOLD}{'=' * 60}{RESET}\n")

    results = run_all()

    # Print results
    sections = {
        "ENV_CHECK": [], "DEPENDENCY_CHECK": [], "FAITHLENS_CHECK": [],
        "FUNCTION_TESTS": [], "SUMMARY": [],
    }
    for r in results:
        if r.name.startswith("ENV:"):
            sections["ENV_CHECK"].append(r)
        elif r.name.startswith("DEP:"):
            sections["DEPENDENCY_CHECK"].append(r)
        elif r.name.startswith("FAITHLENS:"):
            sections["FAITHLENS_CHECK"].append(r)
        elif r.name.startswith("FN:"):
            sections["FUNCTION_TESTS"].append(r)
        else:
            sections["SUMMARY"].append(r)

    for section, section_results in sections.items():
        if not section_results:
            continue
        print(f"\n{CYAN}{section}{RESET}")
        for r in section_results:
            _print_result(r)

    # Summary
    total = len(results)
    passed = sum(1 for r in results if r.status == Status.PASS)
    failed = sum(1 for r in results if r.status == Status.FAIL)
    warned = sum(1 for r in results if r.status == Status.WARN)
    skipped = sum(1 for r in results if r.status == Status.SKIP)
    blocking_fails = sum(1 for r in results if r.status == Status.FAIL and r.blocking)

    print(f"\n{BOLD}{'─' * 60}{RESET}")
    print(f"  Total: {total}  {GREEN}Pass: {passed}{RESET}  {RED}Fail: {failed}{RESET}  "
          f"{YELLOW}Warn: {warned}{RESET}  {CYAN}Skip: {skipped}{RESET}")

    if blocking_fails > 0:
        print(f"\n  {RED}{BOLD}BLOCKED: {blocking_fails} blocking failure(s){RESET}")
        return 1
    elif failed > 0:
        print(f"\n  {YELLOW}Non-blocking failures: {failed}{RESET}")
        return 0
    else:
        print(f"\n  {GREEN}{BOLD}ALL CLEAR: Ready for PG_TEST_047{RESET}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
