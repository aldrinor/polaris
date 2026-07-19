"""
Mesh Q&A orchestrator — ask a question, get a cited answer.

Wraps the retrieve → compose pipeline in a conversational layer with
multi-turn thread support via the `questions.parent_id` chain.

v1 design (CP-A lock):

  - Coreference resolution via simple concatenation (not LLM). The
    last 3 Q&A pairs from the thread + the new question are joined
    into a single string, then embedded. The embedding of "Q: What
    filters remove PFOS? A: GAC and RO... Q: What about the cost?"
    naturally captures "the cost" as PFOS filtration cost.

  - Thread model uses `questions.parent_id` chain (already in schema).
    No separate threads table. First question has parent_id=NULL.

  - NEARBY auto-expansion: when gap_classify returns NEARBY and
    budget allows, `AskResult.gap_category` tells the caller (Unit 8
    CLI) to prompt the user. The actual search expansion requires a
    web/academic searcher the mesh doesn't own — Unit 8+ wires that.

  - The `ask()` function is async because `compose_answer` is async.
    Store CRUD and thread walking are synchronous.
"""

from __future__ import annotations

import logging
from typing import Any

from ..compose.composer import ComposeResult, compose_answer
from ..retrieve.gap_classify import check_nearby_budget
from ..retrieve.retrieval import lethal_retrieve
from ..store import MeshStore, MeshStoreError

logger = logging.getLogger(__name__)

THREAD_CONTEXT_PAIRS = 3


# ───── result container ─────

class AskResult:
    __slots__ = (
        "question_id", "answer_id", "answer_text", "bibliography",
        "gap_category", "claim_ids_used", "artifact_paths",
        "nearby_budget_available",
    )

    def __init__(self) -> None:
        self.question_id: str = ""
        self.answer_id: str = ""
        self.answer_text: str = ""
        self.bibliography: list[dict] = []
        self.gap_category: str = "ORTHOGONAL"
        self.claim_ids_used: list[str] = []
        self.artifact_paths: list[str] = []
        self.nearby_budget_available: bool = False

    def as_dict(self) -> dict:
        return {
            "question_id": self.question_id,
            "answer_id": self.answer_id,
            "answer_text": self.answer_text,
            "bibliography": list(self.bibliography),
            "gap_category": self.gap_category,
            "claim_ids_used": list(self.claim_ids_used),
            "artifact_paths": list(self.artifact_paths),
            "nearby_budget_available": self.nearby_budget_available,
        }


# ───── public API ─────

async def ask(
    client: Any,
    store: MeshStore,
    *,
    workspace_id: str,
    question_text: str,
    parent_question_id: str | None = None,
    asked_by: str | None = None,
    K: int = 40,
    question_embedding: Any | None = None,
) -> AskResult:
    """
    Ask a question and get a cited answer from the mesh.

    Parameters
    ----------
    client : _ComposeClient
        LLM client passed through to compose_answer.
    store : MeshStore
    workspace_id : str
    question_text : str
        The raw user question.
    parent_question_id : str | None
        If this is a follow-up question, the ID of the previous question
        in the thread. Enables coreference resolution via context
        concatenation.
    asked_by : str | None
        Optional user identifier.
    K : int
        Number of claims to retrieve.
    question_embedding : np.ndarray | None
        Pre-computed embedding (tests pass this to avoid loading the
        real model).

    Returns
    -------
    AskResult
    """
    ws = store.get_workspace(workspace_id)
    if ws is None:
        raise MeshStoreError(f"Workspace not found: {workspace_id}")

    result = AskResult()

    # ── Step 1: insert question row ──
    q_id = store.insert_question(
        workspace_id=workspace_id,
        text=question_text,
        parent_id=parent_question_id,
        asked_by=asked_by,
    )
    result.question_id = q_id

    # ── Step 2: build thread context for coreference ──
    resolved = _build_resolved_question(
        store, q_id, question_text,
    )

    # ── Step 3: retrieve ──
    retrieval = lethal_retrieve(
        store,
        workspace_id=workspace_id,
        question_text=question_text,
        K=K,
        resolved_question=resolved,
        question_embedding=question_embedding,
    )
    result.gap_category = retrieval.gap_category

    # ── Step 4: check NEARBY budget ──
    if retrieval.gap_category == "NEARBY":
        result.nearby_budget_available = check_nearby_budget(
            store, workspace_id,
        )
        if result.nearby_budget_available:
            logger.info(
                "ask: gap=NEARBY, budget available — caller should "
                "trigger auto-expansion for workspace %s",
                workspace_id,
            )

    # ── Step 5: compose ──
    compose_result: ComposeResult = await compose_answer(
        client,
        store,
        workspace_id=workspace_id,
        retrieval_result=retrieval,
        question_text=question_text,
    )
    result.answer_text = compose_result.answer_text
    result.bibliography = compose_result.bibliography
    result.claim_ids_used = compose_result.claim_ids_used
    result.artifact_paths = compose_result.artifact_paths

    # ── Step 6: insert answer row ──
    ans_id = store.insert_answer(
        question_id=q_id,
        text=compose_result.answer_text,
        retrieved_claims=[cid for cid, _ in retrieval.scored_claims],
        cited_claims=compose_result.claim_ids_used,
        artifact_paths=compose_result.artifact_paths,
    )
    result.answer_id = ans_id

    logger.info(
        "ask: q=%s ans=%s gap=%s claims=%d",
        q_id, ans_id, result.gap_category, len(result.claim_ids_used),
    )
    return result


# ───── helpers ─────

def _build_resolved_question(
    store: MeshStore,
    question_id: str,
    question_text: str,
) -> str:
    """
    Build a coreference-resolved question by concatenating the last
    N Q&A pairs from the thread history with the current question.

    For v1, this is simple string concatenation — no LLM call. The
    embedding of the concatenated string naturally captures pronouns
    like "it", "the cost", "those filters" by proximity to their
    referents in the preceding Q&A context.
    """
    history = store.get_thread_history(
        question_id, last_n=THREAD_CONTEXT_PAIRS,
    )
    if not history:
        return question_text

    parts: list[str] = []
    for pair in history:
        parts.append(f"Q: {pair['question']}")
        if pair.get("answer"):
            parts.append(f"A: {pair['answer'][:500]}")
    parts.append(f"Q: {question_text}")
    return "\n".join(parts)
