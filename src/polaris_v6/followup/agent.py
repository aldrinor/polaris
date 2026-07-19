"""Phase 3 substrate: deterministic stub follow-up agent.

The real Phase 3 implementation calls the verifier model with a
prompt that constrains it to the parent run's evidence pool. Phase 0
ships this stub to lock the contract: takes a parent EvidenceContract
+ a question, returns a FollowUpAnswer with status determined by simple
keyword overlap. This is enough for the F11 endpoint contract test.
"""

from __future__ import annotations

import re

from polaris_v6.followup.schema import FollowUpAnswer
from polaris_v6.schemas.evidence_contract import EvidenceContract

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(text.lower()) if len(t) > 2}


def answer_followup(
    *,
    parent: EvidenceContract,
    question: str,
) -> FollowUpAnswer:
    """Answer a follow-up question against a parent run's evidence pool.

    Deterministic Phase 0 stub: tokenises the question and scores each parent
    evidence span by token overlap, then constructs an answer from the top few
    matching spans with provenance tokens. The returned status is:

    - ``evidence_insufficient`` if the question has no content tokens;
    - ``out_of_scope`` if no pool span shares any token with the question;
    - ``answered`` otherwise, citing up to the 3 highest-overlap spans.

    Args:
        parent: The parent run's evidence contract; recall is restricted to its
            ``evidence_pool``.
        question: The follow-up question text.

    Returns:
        A ``FollowUpAnswer`` whose ``status`` reflects the outcome above and,
        when answered, includes ``answer_text``, ``used_evidence_ids``, and
        ``provenance_tokens``.
    """
    q_tokens = _tokens(question)
    if not q_tokens:
        return FollowUpAnswer(
            parent_run_id=parent.run_id,
            question=question,
            status="evidence_insufficient",
            rationale="Question contains no content tokens after normalization.",
        )

    pool_hits: list[tuple[str, int]] = []
    for span in parent.evidence_pool:
        span_tokens = _tokens(span.span_text)
        overlap = len(q_tokens & span_tokens)
        if overlap > 0:
            pool_hits.append((span.evidence_id, overlap))

    if not pool_hits:
        return FollowUpAnswer(
            parent_run_id=parent.run_id,
            question=question,
            status="out_of_scope",
            rationale=(
                "No tokens in the question overlap with the parent run's "
                "evidence pool. Start a new run to broaden retrieval."
            ),
        )

    pool_hits.sort(key=lambda h: -h[1])
    used_ids = [eid for eid, _ in pool_hits[:3]]

    if len(used_ids) < 1:
        return FollowUpAnswer(
            parent_run_id=parent.run_id,
            question=question,
            status="evidence_insufficient",
            rationale="Insufficient supporting evidence after deduplication.",
            used_evidence_ids=[],
        )

    spans_by_id = {s.evidence_id: s for s in parent.evidence_pool}
    tokens = []
    for ev_id in used_ids:
        span = spans_by_id[ev_id]
        tokens.append(f"[#ev:{ev_id}:{span.span_start}-{span.span_end}]")

    sentences = [
        spans_by_id[eid].span_text + f" {tokens[i]}"
        for i, eid in enumerate(used_ids)
    ]
    answer_text = " ".join(sentences)

    return FollowUpAnswer(
        parent_run_id=parent.run_id,
        question=question,
        status="answered",
        answer_text=answer_text,
        used_evidence_ids=used_ids,
        provenance_tokens=tokens,
        rationale=(
            f"Question shares content tokens with {len(pool_hits)} pool members; "
            f"top-{len(used_ids)} used as supporting evidence."
        ),
    )
