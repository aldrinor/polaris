"""I-cap-002 feature 1/4 (#1060): extract STORM perspective questions as benchmark search queries.

STORM (`agents/storm_interviews.run_storm_interviews`) produces multi-perspective interview rounds.
For the benchmark we use ONLY the QUESTION text of each round as an additional search query — the
serialized conversation rounds do not persist the per-question decomposed `search_queries`, so the
contract is questions-only. STORM never produces evidence (`direct_quote`) here; it only widens the
search-query fan-out, so the verbatim-span faithfulness path (live_retriever -> strict_verify) is
untouched.
"""

from __future__ import annotations

from typing import Any


def extract_storm_questions(
    storm_conversations: list[dict[str, Any]] | None,
    cap: int = 30,
) -> list[str]:
    """Flatten STORM conversation rounds into a deduplicated, bounded list of question strings.

    Order-preserving, case-insensitive de-duplication. Returns at most ``cap`` questions. Robust to
    missing/empty keys (returns ``[]`` rather than raising).
    """
    if cap <= 0:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for conversation in storm_conversations or []:
        if not isinstance(conversation, dict):
            continue
        for round_ in conversation.get("rounds", []) or []:
            if not isinstance(round_, dict):
                continue
            # Coerce to str defensively — a malformed {"question": 123} must not raise.
            question = str(round_.get("question") or "").strip()
            if not question:
                continue
            key = question.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(question)
            if len(out) >= cap:
                return out
    return out
