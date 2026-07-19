"""
Mesh answer composer — single-answer composition from retrieved claims.

Takes a RetrievalResult from Unit 5's retrieve_claims, hydrates claims
from the store, builds an inline bibliography, formats claims for the
LLM, and composes a cited answer.

v1 design (CP-A lock):

  - Fresh implementation (NOT adapted from wiki_composer.py, which is
    coupled to WikiResult / section-based / report-level composition).
  - Single-answer composition — one RetrievalResult → one answer.
    Multi-section reports are a Unit 7+ feature.
  - LLM via protocol (_ComposeClient) — tests inject a mock, production
    passes OpenRouterClient.
  - Simpler prompt than wiki_composer's 13-rule academic COMPOSE_SYSTEM.
    Mesh answers are Q&A responses, not systematic review sections.
  - Post-processing: CoT scrub + [REF:N] → [N] normalization +
    artifact directive rendering (via artifact_directives.py).
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Protocol

from ..store import MeshStore, MeshStoreError
from .artifact_directives import render_artifacts
from src.polaris_graph.settings import resolve

logger = logging.getLogger(__name__)

COMPOSE_MAX_TOKENS = int(os.getenv("PG_MESH_COMPOSE_MAX_TOKENS", "4096"))
COMPOSE_TIMEOUT = int(resolve("PG_MESH_COMPOSE_TIMEOUT"))
MAX_CLAIMS_FOR_PROMPT = int(resolve("PG_MESH_MAX_CLAIMS_PROMPT"))


# ───── client protocol ─────

class _ComposeClient(Protocol):
    async def generate(
        self,
        *,
        prompt: str,
        system: str,
        max_tokens: int,
        timeout: int,
    ) -> str: ...


# ───── result container ─────

class ComposeResult:
    __slots__ = (
        "answer_text", "bibliography", "claim_ids_used",
        "artifact_paths", "raw_llm_output",
    )

    def __init__(self) -> None:
        self.answer_text: str = ""
        self.bibliography: list[dict] = []
        self.claim_ids_used: list[str] = []
        self.artifact_paths: list[str] = []
        self.raw_llm_output: str = ""

    def as_dict(self) -> dict:
        return {
            "answer_text": self.answer_text,
            "bibliography": list(self.bibliography),
            "claim_ids_used": list(self.claim_ids_used),
            "artifact_paths": list(self.artifact_paths),
        }


# ───── compose prompt ─────

MESH_COMPOSE_SYSTEM = """You are a research assistant answering a question from pre-verified claims.

RULES:
1. Write ONLY from the CLAIMS provided below. Do NOT add facts not in the claims.
2. Every factual statement MUST include its [N] citation number.
3. Interpretive commentary is allowed WITHOUT citations — but NEVER introduce new factual claims uncited.
4. Write in clear, professional prose. No first person.
5. Do NOT include chain-of-thought, planning, or meta-commentary.
6. When claims contain numeric data (percentages, p-values, sample sizes), report the numbers with their citations.
7. If claims contradict each other, present BOTH perspectives with citations and note the disagreement.
8. End with a 2-3 sentence summary of the key findings."""


# ───── public API ─────

async def compose_answer(
    client: _ComposeClient,
    store: MeshStore,
    *,
    workspace_id: str,
    retrieval_result: Any,
    question_text: str,
) -> ComposeResult:
    """
    Compose a cited answer from retrieved claims.

    Parameters
    ----------
    client : _ComposeClient
        LLM client with an async `generate` method.
    store : MeshStore
        Open mesh store for claim/source hydration.
    workspace_id : str
    retrieval_result : RetrievalResult
        From Unit 5's retrieve_claims.
    question_text : str
        The user's original question.

    Returns
    -------
    ComposeResult
    """
    result = ComposeResult()

    scored_claims = getattr(retrieval_result, "scored_claims", [])
    if not scored_claims:
        result.answer_text = (
            "No relevant claims were found in the knowledge base "
            "for this question."
        )
        return result

    # ── Hydrate claims + build bibliography ──
    hydrated, bibliography = _hydrate_claims(store, scored_claims)
    result.bibliography = bibliography
    result.claim_ids_used = [c["claim_id"] for c in hydrated]

    # ── Format for prompt ──
    if len(hydrated) > MAX_CLAIMS_FOR_PROMPT:
        hydrated = hydrated[:MAX_CLAIMS_FOR_PROMPT]

    claims_text = _format_claims(hydrated)
    bib_summary = _format_bibliography(bibliography)

    prompt = (
        f"QUESTION: {question_text}\n\n"
        f"CLAIMS (cite with [N]):\n{claims_text}\n\n"
        f"BIBLIOGRAPHY:\n{bib_summary}\n\n"
        f"Write a comprehensive answer using ONLY the claims above. "
        f"Cite every factual statement with [N]."
    )

    # ── LLM call ──
    raw = await client.generate(
        prompt=prompt,
        system=MESH_COMPOSE_SYSTEM,
        max_tokens=COMPOSE_MAX_TOKENS,
        timeout=COMPOSE_TIMEOUT,
    )
    # Extract text content — OpenRouterClient.generate() returns
    # LLMResponse, not str. Mocks return str. Handle both.
    if hasattr(raw, "content"):
        raw_text = raw.content or ""
    else:
        raw_text = str(raw)
    result.raw_llm_output = raw_text

    # ── Post-process ──
    text = _scrub_cot(raw_text)
    text = _normalize_refs(text)

    # ── Artifact rendering (FIX S7) ──
    claims_by_id = {c["claim_id"]: c for c in hydrated}
    text, artifacts = render_artifacts(text, claims_by_id)
    result.artifact_paths = artifacts

    result.answer_text = text.strip()
    return result


# ───── helpers ─────

def _hydrate_claims(
    store: MeshStore,
    scored_claims: list[tuple[str, float]],
) -> tuple[list[dict], list[dict]]:
    """
    Hydrate claim IDs into full dicts with source info, assign
    bibliography numbers.

    Returns (hydrated_claims, bibliography).
    """
    hydrated: list[dict] = []
    bib: list[dict] = []
    source_to_ref: dict[str, int] = {}

    for claim_id, score in scored_claims:
        claim = store.get_claim(claim_id)
        if claim is None:
            continue
        source = store.get_source(claim["source_page_id"])
        src_url = source.get("url", "") if source else ""
        src_title = source.get("title", "") if source else ""

        # Assign ref number (by first appearance of source)
        if src_url not in source_to_ref:
            ref_num = len(bib) + 1
            source_to_ref[src_url] = ref_num
            bib.append({
                "ref_num": ref_num,
                "url": src_url,
                "title": src_title,
                "authors": source.get("authors") if source else None,
                "year": source.get("year") if source else None,
                "doi": source.get("doi") if source else None,
            })

        hydrated.append({
            "claim_id": claim_id,
            "statement": claim["statement"],
            "direct_quote": claim.get("direct_quote", ""),
            "ref_num": source_to_ref[src_url],
            "relevance_score": score,
            "has_numeric": bool(claim.get("has_numeric")),
            "tier": claim.get("tier", "BRONZE"),
            "source_url": src_url,
            "source_title": src_title,
        })

    return hydrated, bib


def _format_claims(claims: list[dict]) -> str:
    lines: list[str] = []
    for c in claims:
        ref = c["ref_num"]
        stmt = c["statement"]
        quote = c.get("direct_quote", "")
        lines.append(f"[{ref}] {stmt}")
        if quote and quote.lower() != stmt.lower():
            lines.append(f"    QUOTE: \"{quote[:200]}\"")
    return "\n".join(lines)


def _format_bibliography(bib: list[dict]) -> str:
    lines: list[str] = []
    for entry in bib:
        ref = entry["ref_num"]
        title = entry.get("title") or "Untitled"
        url = entry.get("url") or ""
        year = entry.get("year") or ""
        lines.append(f"[{ref}] {title} ({year}) — {url}")
    return "\n".join(lines)


_COT_PATTERN = re.compile(
    r"<think>.*?</think>|<reasoning>.*?</reasoning>|"
    r"\*\*(?:Planning|Thinking|Analysis|Step \d).*?\*\*.*?\n",
    re.DOTALL | re.IGNORECASE,
)


def _scrub_cot(text: str) -> str:
    """Remove chain-of-thought artifacts from LLM output."""
    return _COT_PATTERN.sub("", text).strip()


_REF_PATTERN = re.compile(r"\[REF:(\d+)\]")


def _normalize_refs(text: str) -> str:
    """Convert [REF:N] → [N] for clean output."""
    return _REF_PATTERN.sub(r"[\1]", text)
