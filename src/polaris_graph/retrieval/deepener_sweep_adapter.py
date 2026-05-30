"""Sweep-side adapter for the citation-snowball evidence_deepener (I-meta-002-q1d #942-deepener).

Wires POLARIS's frontier-grade `evidence_deepener` (backward+forward S2 citation chase + recommendations
+ mechanism search) into the launch sweep behind a flag + a Stop-RAG value-based trigger. SAFETY DESIGN
(Codex brief-gate, Option A): the deepener only DISCOVERS relevant primary-paper URLs; those URLs are then
fed back through the EXISTING `run_live_retrieval(seed_urls=...)` chokepoint (fetch → classify_source_tier
→ is_content_starved → _build_provenance_quote), so a deepened paper earns its tier ONLY from fetched
content and a thin/abstract-only paper is DROPPED fail-closed — no tier laundering, zero new evidence-row
build logic that could drift from strict_verify.

Pure orchestration helpers (no I/O except the injected `deepen_evidence` coroutine). The sweep does the
merge + the `run_live_retrieval` pass; this module only builds the deepener state, runs the coroutine
safely from a sync caller, applies the trigger predicate, and extracts the discovered URLs.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import os
from typing import Any, Awaitable, Callable

# Model the deepener uses for its mechanism-query generation LLM call (env-overridable).
DEEPENER_LLM_MODEL = os.getenv("PG_SWEEP_DEEPENER_MODEL", "deepseek/deepseek-v4-pro")

# Default URL injection cap (bounds the deepener fetch pass; also env-overridable at the call site).
DEFAULT_DEEPENER_URL_CAP = 20


def should_trigger_deepener(
    *,
    flag_on: bool,
    has_s2_key: bool,
    has_seed_evidence: bool,
    adequacy_decision: str,
    total_uncovered: int,
) -> bool:
    """Stop-RAG value-based trigger (Codex brief-gate iter-1 required predicate). The deepener fires
    ONLY when it is enabled AND there is something to chase from AND the corpus is BORDERLINE — i.e.
    NOT on an already-comfortably-adequate corpus with full coverage.

    - `flag_on`: PG_SWEEP_EVIDENCE_DEEPENER truthy (default OFF — the deepener SPENDS).
    - `has_s2_key`: SEMANTIC_SCHOLAR_API_KEY present (the deepener no-ops without it).
    - `has_seed_evidence`: there is existing evidence to chase citations FROM (else "abort-impossible").
    - borderline := adequacy.decision != "proceed" (i.e. "expand"/"abort") OR post-R6 uncovered topics > 0.
    """
    if not (flag_on and has_s2_key and has_seed_evidence):
        return False
    return adequacy_decision != "proceed" or total_uncovered > 0


def build_deepener_state(evidence_rows: list[dict[str, Any]], question: str) -> dict[str, Any]:
    """Build the 3-key state the deepener reads (`iteration_count`, `evidence` carrying `source_url`,
    `original_query`). Pure."""
    evidence = []
    for ev in evidence_rows or []:
        # Strip BEFORE the blank check (Codex diff-gate iter-1 P1): a whitespace-only url is not seed
        # evidence.
        url = (ev.get("source_url") or ev.get("url") or "").strip()
        if url:
            evidence.append({"source_url": url})
    return {"iteration_count": 0, "evidence": evidence, "original_query": question or ""}


def run_deepener_sync(
    state: dict[str, Any],
    *,
    deepen_fn: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Run the async `deepen_evidence` coroutine from a SYNC caller WITHOUT raising RuntimeError if an
    event loop is already running (Codex brief-gate iter-1 P1). Normal sweep execution has no running
    loop → `asyncio.run`. If a loop IS running (async test harness / embedded caller), run the coroutine
    in an ISOLATED thread with its own loop so it fails closed locally and never aborts unrelated work.

    `deepen_fn` is injectable so offline tests pass a FAKE deepener (no network/spend). The REAL
    `deepen_evidence(client, state)` takes an OpenRouterClient FIRST (Codex diff-gate iter-2 P1) — the
    default closure constructs one and adapts it to the 1-arg `fn(state)` interface used here.
    """
    if deepen_fn is None:
        from src.polaris_graph.agents.evidence_deepener import deepen_evidence  # noqa: E402
        from src.polaris_graph.llm.openrouter_client import OpenRouterClient  # noqa: E402

        async def deepen_fn(_state: dict[str, Any]) -> dict[str, Any]:
            # Close the client after the pass to avoid leaking its async HTTP client (Codex diff-gate
            # iter-3 P2; mirrors the generator pattern, e.g. analyst_synthesis).
            client = OpenRouterClient(model=DEEPENER_LLM_MODEL)
            try:
                return await deepen_evidence(client, _state)
            finally:
                await client.close()

    try:
        asyncio.get_running_loop()
        loop_running = True
    except RuntimeError:
        loop_running = False

    if loop_running:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(lambda: asyncio.run(deepen_fn(state))).result()
    return asyncio.run(deepen_fn(state))


def discovered_urls(deepener_output: dict[str, Any] | None, *, cap: int = DEFAULT_DEEPENER_URL_CAP) -> list[str]:
    """Extract de-duplicated, non-blank discovered paper URLs from the deepener output, capped. These
    are seeded into the `run_live_retrieval(seed_urls=...)` chokepoint (not turned into evidence rows
    here — the existing fetch/tier/provenance pipeline does that)."""
    # Exact cap (Codex diff-gate iter-1 P1): a non-positive cap yields NO urls (and never flows a
    # negative into fetch_cap) — guard up front so the append-then-break can't return one url at cap=0.
    if cap is None or cap <= 0:
        return []
    papers = (deepener_output or {}).get("deepened_papers", []) or []
    out: list[str] = []
    seen: set[str] = set()
    for paper in papers:
        url = (paper.get("url") or "").strip() if isinstance(paper, dict) else ""
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(url)
        if len(out) >= cap:
            break
    return out
