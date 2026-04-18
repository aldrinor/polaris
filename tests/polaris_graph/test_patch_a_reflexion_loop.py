"""PATCH-A: Reflexion re-audit loop tests — DEPRECATED by HONEST-REBUILD Phase 1b.

HONEST-REBUILD status (2026-04-18): Phase 1b stripped the REMEDIATE-LOOP
from wiki_composer entirely (see commit 85f08b5 and
loopback/audit/PG_LB_SA_02_CONTENT_AUDIT.md). The Reflexion-style
rewrite-to-pass-metric loop was itself a source of NLI-gaming: iter-2
rewrites compressed sections by ~60% to beat the metric, deleting
evidence-synthesis content. The honest-rebuild replaces this with
strict_verify drop-on-failure + multi-section regen-once-if-kept-
fraction-too-low (see Gap-4 multi_section_generator.py).

These tests remain in the tree as a historical marker — they exercise
code that was intentionally removed. Marked xfail so the suite reads
clean.
"""
from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.xfail(
    reason=(
        "Phase 1b removed the REMEDIATE-LOOP from wiki_composer. "
        "These tests exercise deprecated Patch-A Reflexion code "
        "(commit 85f08b5). Kept as historical marker."
    ),
    strict=False,
)

from src.polaris_graph.wiki.wiki_builder import WikiResult


def _make_wiki_result() -> WikiResult:
    """Minimal WikiResult with one section, 3 claims."""
    claims = [
        {
            "evidence_id": f"ev_{i:03d}",
            "statement": f"Claim {i} statement with citation.",
            "source_url": f"https://example.com/paper{i}",
            "source_title": f"Paper {i}",
            "ref_num": i + 1,
            "direct_quote": f"quote {i}",
            "relevance_score": 0.8,
            "perspective": "Scientific",
            "fact_category": "statistic",
            "year": 2024,
            "authors": [f"Author{i}"],
            "doi": "",
            "source_type": "journal_article",
        }
        for i in range(3)
    ]
    return WikiResult(
        wiki_path="/tmp/test_wiki",
        section_claims={"s01": claims},
        bibliography=[
            {
                "ref_num": 1,
                "citation_number": 1,
                "url": "https://example.com/paper0",
                "title": "Paper 0",
                "authors": [],
                "year": 2024,
                "doi": "",
                "source_type": "journal_article",
                "evidence_ids": ["ev_000"],
                "formatted": "Paper 0 (2024)",
            }
        ],
        stats={"total_evidence": 3, "total_sources": 1},
    )


def _make_outline() -> list[dict]:
    return [
        {
            "section_id": "s01",
            "title": "Test Section",
            "description": "Test section description",
            "order": 1,
        }
    ]


def _make_audit_result(unsupported_ratio: float, needs_rewrite: bool) -> list[dict]:
    """Build a mock hallucination_audit result."""
    return [
        {
            "section_id": "s01",
            "title": "Test Section",
            "hallucination_ratio": unsupported_ratio,
            "needs_rewrite": needs_rewrite,
            "hallucinated_spans": [
                {"text": "flagged text", "nli_score": 0.1}
            ] if needs_rewrite else [],
        }
    ]


async def _run_compose(audit_side_effect, compose_return="Test prose [1]. Test claim [1]. Reviewed content."):
    """Helper: run compose_from_wiki with mocked detector + LLM."""
    from src.polaris_graph.wiki import wiki_composer

    client = MagicMock()
    client.generate = AsyncMock(return_value=compose_return)

    wiki_result = _make_wiki_result()
    outline = _make_outline()

    with patch(
        "src.polaris_graph.agents.hallucination_detector._is_enabled",
        return_value=True,
    ), patch(
        "src.polaris_graph.agents.hallucination_detector.audit_sections_for_hallucination",
        side_effect=audit_side_effect,
    ) as audit_mock, patch.object(
        wiki_composer, "_compose_one_section",
        AsyncMock(return_value=compose_return * 10),  # 80+ words
    ) as compose_mock, patch.object(
        wiki_composer, "_compose_abstract",
        AsyncMock(return_value="Abstract text. " * 10),
    ):
        result = await wiki_composer.compose_from_wiki(
            client=client,
            wiki_result=wiki_result,
            query="test query about risks",
            outline=outline,
        )
        return result, audit_mock, compose_mock


# ── Test 1: Loop iterates when flagged stays > 0 ────────────────────

def test_reflexion_loop_runs_multiple_iterations_when_still_flagged(monkeypatch):
    """If audit keeps flagging, loop runs up to MAX_REWRITE_ITERS times.

    Sequence:
      call 1: initial audit → flagged (triggers loop iter 1)
      call 2: re-audit after iter 1 → still flagged (triggers iter 2)
      call 3: re-audit after iter 2 → still flagged (loop exits at cap)
      call 4: abstract audit (always runs)
    """
    monkeypatch.setenv("PG_HALLUC_MAX_ITERS", "2")
    monkeypatch.setenv("PG_HALLUC_ENABLED", "1")
    # Return "flagged" for all section audits, "not flagged" for abstract
    call_count = {"n": 0}

    def audit_side(sections, evidence, research_query):
        call_count["n"] += 1
        if len(sections) == 1 and sections[0].get("section_id") == "abstract":
            return _make_audit_result(0.1, False)  # clean abstract
        return _make_audit_result(0.8, True)  # sections still flagged

    result, audit_mock, compose_mock = asyncio.run(_run_compose(audit_side))

    # Initial audit + 2 re-audits + 1 abstract audit = 4 total
    assert call_count["n"] == 4, f"expected 4 audit calls, got {call_count['n']}"
    # Compose called 3x: 1 initial composition + 2 rewrites (one per iter)
    assert compose_mock.call_count == 3, (
        f"expected 3 compose calls (1 initial + 2 rewrites), got {compose_mock.call_count}"
    )


# ── Test 2: Loop exits early when re-audit shows zero flagged ─────

def test_reflexion_loop_exits_on_convergence(monkeypatch):
    """First rewrite fixes everything → loop exits at iter 1.

    Sequence:
      call 1: initial audit → flagged
      call 2: re-audit after iter 1 rewrite → NOT flagged
      loop exits, no iter 2
      call 3: abstract audit
    """
    monkeypatch.setenv("PG_HALLUC_MAX_ITERS", "3")
    monkeypatch.setenv("PG_HALLUC_ENABLED", "1")
    call_count = {"n": 0}

    def audit_side(sections, evidence, research_query):
        call_count["n"] += 1
        if len(sections) == 1 and sections[0].get("section_id") == "abstract":
            return _make_audit_result(0.1, False)
        # First call = initial audit → flagged.
        # Second call = re-audit → clean.
        if call_count["n"] == 1:
            return _make_audit_result(0.8, True)
        return _make_audit_result(0.1, False)

    result, audit_mock, compose_mock = asyncio.run(_run_compose(audit_side))

    # Initial + 1 re-audit + abstract = 3 total
    assert call_count["n"] == 3, f"expected 3 audit calls, got {call_count['n']}"
    # 1 initial compose + 1 rewrite (iter 1) before convergence = 2
    assert compose_mock.call_count == 2


# ── Test 3: Loop exits when rewrite produces zero success ─────────

def test_reflexion_loop_breaks_when_all_rewrites_fail(monkeypatch):
    """If _compose_one_section returns empty/too-short output, rewrite_count
    stays 0 and the loop breaks — avoids infinite loop on LLM failures."""
    from src.polaris_graph.wiki import wiki_composer

    monkeypatch.setenv("PG_HALLUC_MAX_ITERS", "3")
    monkeypatch.setenv("PG_HALLUC_ENABLED", "1")

    call_count = {"n": 0}

    def audit_side(sections, evidence, research_query):
        call_count["n"] += 1
        if len(sections) == 1 and sections[0].get("section_id") == "abstract":
            return _make_audit_result(0.1, False)
        return _make_audit_result(0.8, True)  # always flagged

    client = MagicMock()
    client.generate = AsyncMock(return_value="x")

    wiki_result = _make_wiki_result()
    outline = _make_outline()

    with patch(
        "src.polaris_graph.agents.hallucination_detector._is_enabled",
        return_value=True,
    ), patch(
        "src.polaris_graph.agents.hallucination_detector.audit_sections_for_hallucination",
        side_effect=audit_side,
    ), patch.object(
        wiki_composer, "_compose_one_section",
        AsyncMock(return_value="too short"),  # <50 words → rewrite rejected
    ) as compose_mock, patch.object(
        wiki_composer, "_compose_abstract",
        AsyncMock(return_value="Abstract text. " * 10),
    ):
        asyncio.run(wiki_composer.compose_from_wiki(
            client=client,
            wiki_result=wiki_result,
            query="test query about risks",
            outline=outline,
        ))

    # Initial audit + 1 abstract audit = 2 total (no re-audit because break
    # fires when rewrite_count stays 0 on iter 1)
    assert call_count["n"] == 2, f"expected 2 audits, got {call_count['n']}"
    # 1 initial compose + 1 failed rewrite attempt = 2
    assert compose_mock.call_count == 2


# ── Test 4: Env var override cap = 1 disables second pass ─────────

def test_reflexion_loop_env_var_caps_iterations(monkeypatch):
    """PG_HALLUC_MAX_ITERS=1 limits to a single rewrite pass (no re-audit)."""
    monkeypatch.setenv("PG_HALLUC_MAX_ITERS", "1")
    monkeypatch.setenv("PG_HALLUC_ENABLED", "1")
    call_count = {"n": 0}

    def audit_side(sections, evidence, research_query):
        call_count["n"] += 1
        if len(sections) == 1 and sections[0].get("section_id") == "abstract":
            return _make_audit_result(0.1, False)
        return _make_audit_result(0.8, True)

    result, audit_mock, compose_mock = asyncio.run(_run_compose(audit_side))

    # Initial audit + 1 re-audit (iter 1 runs in full because cap=1) + abstract = 3
    # With cap=1 the loop still runs ONE rewrite iteration (which includes a re-audit),
    # so total is 1 initial + 1 re-audit + 1 abstract = 3.
    assert call_count["n"] == 3, f"expected 3 audit calls with cap=1, got {call_count['n']}"
    # 1 initial compose + 1 rewrite = 2
    assert compose_mock.call_count == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
