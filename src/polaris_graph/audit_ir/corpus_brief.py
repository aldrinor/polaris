"""Question-Bound Corpus Brief emitter (M-12 — Phase B).

Per FINAL_PLAN.md:
  - "Narrow form: answer one user question over a selected corpus,
    emit cited brief"
  - "Per-paragraph inline citations OR explicit 'insufficient
    support' labels"
  - "NOT 'Workspace Brief' or 'WikiLLM' in product copy — those
    import wrong expectations"

The brief is a sequence of paragraphs. Each paragraph is either:
  (a) a SUPPORTED claim with citations to retrieved chunks, OR
  (b) an INSUFFICIENT-SUPPORT label naming the sub-question that
      could not be answered.

Why explicit-insufficient: per LAW II ("fail loud, no silent
fallbacks") the brief MUST NOT silently fabricate or hedge over a
gap. If retrieval returned nothing relevant for a sub-question,
the brief says so verbatim. Operators downstream see the gap and
can rephrase the question or upload more documents.

Phase B implementation (deliberately simple):
  1. Retrieve top-K chunks (corpus_retriever.retrieve_chunks).
  2. If retrieval returned 0 chunks → emit a single
     INSUFFICIENT-SUPPORT paragraph saying so. No LLM call.
  3. Otherwise, ask the LLM to draft per-paragraph claims grounded
     in the retrieved chunks; structure: list of {claim, citations}.
  4. Validate every paragraph: each citation MUST reference a
     chunk_id from the retrieved set. Paragraphs whose claims
     cite an unknown chunk_id are dropped (per LAW II — never
     leak fabricated citations).
  5. If the validator drops every paragraph, emit a single
     INSUFFICIENT-SUPPORT paragraph instead of a hollow brief.

Phase B does NOT call out to OpenRouter directly here; it accepts
a pluggable `LlmClient` protocol so tests can pass a fake. The
inspector_router wires the real OpenRouter client. This isolates
the brief logic from network dependencies and lets us exercise
the validation paths deterministically in tests.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from src.polaris_graph.audit_ir.corpus_retriever import (
    DEFAULT_MIN_SCORE,
    DEFAULT_TOP_K,
    RetrievedChunk,
    retrieve_chunks,
)
from src.polaris_graph.audit_ir.workspace_store import WorkspaceStore


# ---------------------------------------------------------------------------
# Result records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BriefCitation:
    """One citation inside a brief paragraph."""

    chunk_id: str
    upload_id: str
    filename: str
    provenance: dict[str, Any]


@dataclass(frozen=True)
class BriefParagraph:
    """One paragraph in the brief.

    Either:
      - claim is non-empty AND citations is non-empty (supported), OR
      - support_status == "insufficient_support" with a rationale
        in `claim` and no citations.
    """

    claim: str
    citations: tuple[BriefCitation, ...] = field(default_factory=tuple)
    support_status: str = "supported"  # "supported" | "insufficient_support"


@dataclass(frozen=True)
class CorpusBrief:
    """Output of `compose_brief`."""

    workspace_id: str
    question: str
    paragraphs: tuple[BriefParagraph, ...]
    retrieved_chunks: tuple[RetrievedChunk, ...]


def brief_to_dict(b: CorpusBrief) -> dict[str, Any]:
    """JSON-friendly serialization."""
    return {
        "workspace_id": b.workspace_id,
        "question": b.question,
        "paragraphs": [
            {
                "claim": p.claim,
                "support_status": p.support_status,
                "citations": [asdict(c) for c in p.citations],
            }
            for p in b.paragraphs
        ],
        "retrieved_chunks": [
            {
                "chunk_id": c.chunk_id,
                "upload_id": c.upload_id,
                "filename": c.filename,
                "score": c.score,
                "provenance": c.provenance,
                # Trim long text in the API response; full text is
                # available via /api/inspector/uploads/.../chunks.
                "text_preview": c.text[:300],
            }
            for c in b.retrieved_chunks
        ],
    }


# ---------------------------------------------------------------------------
# LLM client protocol — pluggable for tests
# ---------------------------------------------------------------------------


class LlmClient(Protocol):
    """Minimal LLM interface the brief emitter needs.

    Codex M-12 review fix: `draft_brief` is now async because the
    real OpenRouter client is async. Sync test fakes implement
    this as `async def` too — there's no overhead since they don't
    actually do I/O.

    Implementations must:
      - Return JSON parseable as the schema described in the prompt.
      - Raise on any error (no silent fallbacks per LAW II).
    """

    async def draft_brief(
        self,
        question: str,
        chunks: list[RetrievedChunk],
    ) -> list[dict[str, Any]]:
        """Return a list of paragraph dicts:
          [{"claim": str, "citations": [{"chunk_id": str}, ...]}, ...]
        Raises on failure (timeout, malformed response, etc.).
        """
        ...


# ---------------------------------------------------------------------------
# Brief composition
# ---------------------------------------------------------------------------


_INSUFFICIENT_NO_RETRIEVAL = (
    "Insufficient support in this workspace for the question. No "
    "uploaded documents contained content relevant to the query. "
    "Upload more documents or rephrase the question."
)

_INSUFFICIENT_LLM_DROPPED_ALL = (
    "Insufficient support: the corpus contains chunks lexically "
    "related to the question, but none of the drafted claims could "
    "be tied back to a retrieved chunk. Operator should rephrase "
    "the question or review the corpus directly."
)


async def compose_brief(
    store: WorkspaceStore,
    workspace_id: str,
    question: str,
    llm: LlmClient,
    top_k: int = DEFAULT_TOP_K,
    min_score: float = DEFAULT_MIN_SCORE,
) -> CorpusBrief:
    """Compose a Question-Bound Corpus Brief over the workspace.

    Returns a CorpusBrief whose paragraphs are either supported
    (with non-empty citations) or labeled "insufficient_support".
    Never silently fabricates citations.

    Codex M-12 review fix: now async so it can `await` the real
    OpenRouter LLM client. Test fakes implement `draft_brief` as
    async too.

    Raises ValueError on unknown workspace (matches retrieve_chunks
    behavior so the API layer maps to 404).
    """
    chunks = retrieve_chunks(
        store=store, workspace_id=workspace_id, question=question,
        top_k=top_k, min_score=min_score,
    )

    if not chunks:
        return CorpusBrief(
            workspace_id=workspace_id, question=question,
            paragraphs=(BriefParagraph(
                claim=_INSUFFICIENT_NO_RETRIEVAL,
                support_status="insufficient_support",
            ),),
            retrieved_chunks=(),
        )

    raw_paragraphs = await llm.draft_brief(question=question, chunks=chunks)

    # Codex M-12 v2 review fix: an upload can be soft-deleted DURING
    # the LLM await. Re-snapshot the eligible-chunk set AFTER the
    # await and intersect — any chunk that was deleted while the
    # LLM was running is removed from the validation set so the
    # final brief never cites a chunk that's no longer eligible.
    eligible_now = store.list_eligible_chunks(workspace_id)
    eligible_ids_now = {c["chunk_id"] for c in eligible_now}
    chunks_by_id = {
        c.chunk_id: c for c in chunks if c.chunk_id in eligible_ids_now
    }

    validated: list[BriefParagraph] = []
    for p in raw_paragraphs:
        if not isinstance(p, dict):
            continue
        claim = (p.get("claim") or "").strip()
        if not claim:
            continue
        cites_raw = p.get("citations") or []
        if not isinstance(cites_raw, list):
            continue
        valid_cites: list[BriefCitation] = []
        seen_ids: set[str] = set()
        for c in cites_raw:
            if not isinstance(c, dict):
                continue
            cid = c.get("chunk_id")
            if not isinstance(cid, str) or cid in seen_ids:
                continue
            chunk = chunks_by_id.get(cid)
            if chunk is None:
                # Codex M-12 review fix: never leak fabricated
                # chunk_ids. Drop the citation; the paragraph as a
                # whole still requires ≥1 valid citation to count.
                continue
            seen_ids.add(cid)
            valid_cites.append(BriefCitation(
                chunk_id=chunk.chunk_id,
                upload_id=chunk.upload_id,
                filename=chunk.filename,
                provenance=chunk.provenance,
            ))
        if not valid_cites:
            continue
        validated.append(BriefParagraph(
            claim=claim,
            citations=tuple(valid_cites),
            support_status="supported",
        ))

    # Codex M-12 v2 review fix: filter retrieved_chunks to the
    # post-await eligible set so the API response never advertises
    # chunks that are no longer eligible for retrieval (e.g. their
    # upload was soft-deleted during the LLM await).
    surviving_retrieved = tuple(
        c for c in chunks if c.chunk_id in eligible_ids_now
    )

    if not validated:
        # LLM hallucinated all citations OR returned no usable
        # paragraphs (or all of them got pruned by the post-await
        # delete check). Emit explicit insufficient-support label
        # rather than a hollow brief.
        return CorpusBrief(
            workspace_id=workspace_id, question=question,
            paragraphs=(BriefParagraph(
                claim=_INSUFFICIENT_LLM_DROPPED_ALL,
                support_status="insufficient_support",
            ),),
            retrieved_chunks=surviving_retrieved,
        )

    return CorpusBrief(
        workspace_id=workspace_id, question=question,
        paragraphs=tuple(validated),
        retrieved_chunks=surviving_retrieved,
    )


# ---------------------------------------------------------------------------
# Default OpenRouter-backed LLM client (used by the API)
# ---------------------------------------------------------------------------


_DRAFT_BRIEF_SYSTEM = (
    "You are a research assistant drafting a tightly-cited brief. "
    "Every claim you write MUST cite at least one chunk by its "
    "chunk_id. Never invent chunk_ids; only cite chunks the user "
    "provided. If a sub-question cannot be answered from the chunks, "
    "OMIT that paragraph rather than hedging or fabricating. "
    "Output JSON of the exact form: "
    '{"paragraphs": [{"claim": "...", "citations": [{"chunk_id": "..."}]}]}.'
)


def _build_user_prompt(question: str, chunks: list[RetrievedChunk]) -> str:
    """Build a deterministic user prompt for the LLM."""
    lines = [
        f"Question: {question}",
        "",
        "Available chunks (cite by chunk_id):",
    ]
    for c in chunks:
        lines.append(
            f"---\nchunk_id: {c.chunk_id}\nfilename: {c.filename}\n"
            f"text:\n{c.text}\n"
        )
    lines.append("---")
    lines.append(
        "Respond with JSON only. Each paragraph cites at least one "
        "chunk_id from the list above."
    )
    return "\n".join(lines)


class OpenRouterBriefClient:
    """Real LLM client backed by OpenRouterClient.generate.

    Codex M-12 review fix: now async, awaits `generate()`, and
    parses `LLMResponse.content`. v1 incorrectly:
      - Called `asyncio.run()` from inside an async FastAPI route
        (raises "asyncio.run() cannot be called from a running
        event loop").
      - Treated the `LLMResponse` return value as a str
        (`AttributeError` on `.strip()`).

    Constructed lazily by the API layer so unit tests don't need
    network credentials.

    Per LAW II: any LLM error (timeout, malformed JSON, schema
    mismatch) propagates — we never fall back to a stub paragraph.
    """

    def __init__(self, openrouter_client: Any) -> None:
        """`openrouter_client` is an instance of
        `src.polaris_graph.llm.openrouter_client.OpenRouterClient`.
        Typed loosely to avoid pulling that import here."""
        self._client = openrouter_client

    async def draft_brief(
        self, question: str, chunks: list[RetrievedChunk]
    ) -> list[dict[str, Any]]:
        prompt = _build_user_prompt(question, chunks)
        # Inline call via the existing async client. We use generate
        # (not generate_structured) and parse the JSON ourselves so
        # this module doesn't import a Pydantic schema from the
        # OpenRouter client family — keeps the dependency arrows
        # clean.
        # Codex M-12 v2 review fix: removed `thinking_mode=False`
        # — the real OpenRouterClient.generate signature has no
        # such kwarg (would TypeError at call time and 500 the
        # endpoint). generate() already disables reasoning by
        # default for the prose path.
        response = await self._client.generate(
            prompt=prompt, system=_DRAFT_BRIEF_SYSTEM,
            max_tokens=4096,
        )
        # OpenRouterClient.generate returns LLMResponse, not str.
        text = getattr(response, "content", None)
        if text is None:
            # Tolerate plain-string returns from test doubles that
            # haven't migrated to LLMResponse-shaped fakes.
            text = response if isinstance(response, str) else ""
        if not isinstance(text, str):
            raise ValueError(
                f"LLM response.content must be str; got {type(text).__name__}"
            )
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
            # Trim trailing fence remnants.
            cleaned = cleaned.rstrip("`").strip()
        parsed = json.loads(cleaned)
        if not isinstance(parsed, dict) or "paragraphs" not in parsed:
            raise ValueError(
                "LLM brief response missing 'paragraphs' key; refusing "
                "to silently fabricate"
            )
        paragraphs = parsed["paragraphs"]
        if not isinstance(paragraphs, list):
            raise ValueError("LLM 'paragraphs' field must be a list")
        return paragraphs
