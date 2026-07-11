"""THE shared fold-in seam for the agentic outliner (factored 2026-07-11).

Every path that brings EXTERNAL fetched content into ``workspace.ev_store`` — ``search_more_evidence``
today, ``fetch_url`` next — MUST re-enter through this ONE seam so the faithfulness engine stays the
only hard gate and the id space can never collide. Factored out of ``outline_agent.py`` (was
``_offset_renumber`` :629 + ``_stamp_and_delete`` :802) so both tools share the identical unit
instead of copy-pasting it.

The seam, in order (design §):
  1. URL-dedup vs. the rows already in ``ev_store`` (never re-fold a page we already hold).
  2. ``_offset_renumber`` — assign ``ev_{offset+i}`` ids and HARD fail-loud if any new id collides
     with an existing id (a collision is a programming bug in the offset math, not a data
     condition — LAW II: never swallow).
  3. ``_stamp_and_delete`` — S2 stamp pass: content-integrity chrome delete (pure) + topic-judge
     off-topic delete (LLM, fail-open). §-1.3.1 junk carve-out only; the rest of
     WEIGHT-AND-CONSOLIDATE is untouched downstream.
  4. Insert the survivors into ``ev_store``.

No number and no citation is ever invented here; this seam only renumbers, dedups, and deletes
junk. Computed numbers take the SEPARATE verified ``[#calc:]`` lane (outline/verified_compute.py).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


def _offset_renumber(
    new_rows: list[dict[str, Any]], offset: int, existing_ids: set[str],
) -> list[dict[str, Any]]:
    """THE sharp seam (design §): renumber ``new_rows`` to ``ev_{offset+i}`` and HARD
    fail-loud assert the new id set never intersects ``existing_ids``. A collision here is a
    programming bug in the offset computation, not a data condition — it must never be
    swallowed (LAW II: fail loudly, never silently degrade)."""
    renumbered: list[dict[str, Any]] = []
    new_ids: set[str] = set()
    for i, row in enumerate(new_rows):
        new_id = f"ev_{offset + i:03d}"
        if new_id in existing_ids or new_id in new_ids:
            raise AssertionError(
                f"outline_agent id-collision seam FAILED: {new_id!r} already present "
                f"(existing_ids has it: {new_id in existing_ids}; batch dup: {new_id in new_ids}). "
                "This must never happen — the offset computation has a bug."
            )
        new_ids.add(new_id)
        copied = dict(row)
        copied["evidence_id"] = new_id
        renumbered.append(copied)
    assert new_ids.isdisjoint(existing_ids), (
        "outline_agent id-collision seam FAILED post-hoc: new ids intersect existing ids "
        f"({sorted(new_ids & existing_ids)})"
    )
    return renumbered


async def _stamp_and_delete(
    rows: list[dict[str, Any]], research_question: str, agent_model: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """S2 stamp pass: content-integrity chrome detection (pure, no LLM) THEN semantic
    topic-judge off-topic screen (LLM, fail-open). Returns (kept, deleted_chrome,
    deleted_offtopic). §-1.3.1: only genuine junk/off-topic is deleted here — the rest of
    the WEIGHT-AND-CONSOLIDATE DNA (tier/credibility weighting) is untouched downstream."""
    if not rows:
        return [], [], []

    from src.tools.access_bypass import detect_content_integrity_junk  # noqa: PLC0415

    survivors: list[dict[str, Any]] = []
    deleted_chrome: list[dict[str, Any]] = []
    for row in rows:
        body = max(
            (
                str(row.get(k) or "") for k in (
                    "fetched_body", "full_text", "content", "extracted_text",
                    "raw_content", "raw_text", "page_text", "direct_quote",
                    "statement", "source_text", "body", "text",
                )
            ),
            key=len, default="",
        )
        url = str(row.get("source_url") or row.get("url") or "")
        title = str(row.get("title") or row.get("source_title") or "")
        try:
            is_junk, cls = detect_content_integrity_junk(body, url, title)
        except Exception as exc:  # noqa: BLE001 — fail-open, never delete on a predicate bug
            logger.warning("[outline_agent] content-integrity check errored (fail-open): %s", exc)
            is_junk, cls = False, ""
        if is_junk:
            copied = dict(row)
            copied["deletion_reason"] = f"content_integrity_junk:{cls}"
            deleted_chrome.append(copied)
        else:
            survivors.append(row)

    if not survivors:
        return [], deleted_chrome, []

    try:
        # Lazy imports from outline_agent avoid a module-load import cycle (outline_agent imports
        # THIS module at top). By call time outline_agent is fully initialized.
        from src.polaris_graph.outline.outline_agent import (  # noqa: PLC0415
            _env_int, _sync_llm_bridge,
        )
        from src.polaris_graph.retrieval.topic_relevance_gate import (  # noqa: PLC0415
            classify_topic_relevance, topic_gate_enabled,
        )
        if not topic_gate_enabled():
            return survivors, deleted_chrome, []
        llm_callable = _sync_llm_bridge(
            agent_model, _env_int("PG_SCOPE_TOPIC_MAX_TOKENS", 1200),
        )
        import asyncio  # noqa: PLC0415
        topic_result = await asyncio.to_thread(
            classify_topic_relevance, survivors, research_question, llm_callable,
        )
        kept = list(getattr(topic_result, "kept_rows", None) or survivors)
        dropped = list(getattr(topic_result, "dropped_rows", None) or [])
        deleted_offtopic = []
        for row in dropped:
            copied = dict(row)
            copied["deletion_reason"] = "confirmed_offtopic_subject"
            deleted_offtopic.append(copied)
        return kept, deleted_chrome, deleted_offtopic
    except Exception as exc:  # noqa: BLE001 — topic judge is fail-open by design
        logger.warning("[outline_agent] topic judge skipped (fail-open): %s", exc)
        return survivors, deleted_chrome, []


@dataclass
class FoldInResult:
    """The outcome of one fold-in of external fetched rows through the shared seam."""

    kept_rows: list[dict[str, Any]] = field(default_factory=list)
    n_url_dup: int = 0
    deleted_chrome: list[dict[str, Any]] = field(default_factory=list)
    deleted_offtopic: list[dict[str, Any]] = field(default_factory=list)

    @property
    def n_kept(self) -> int:
        return len(self.kept_rows)

    @property
    def n_deleted(self) -> int:
        return len(self.deleted_chrome) + len(self.deleted_offtopic)


async def fold_in_fetched_rows(
    workspace: Any,
    fetched_rows: list[dict[str, Any]],
    *,
    research_question: str,
    agent_model: str,
    insert: bool = True,
) -> FoldInResult:
    """The reusable fold-in unit: url-dedup -> offset-renumber (hard id-collision assert) ->
    S2 stamp/delete -> insert survivors into ``workspace.ev_store``.

    Shared by ``search_more_evidence`` and (next) ``fetch_url`` so a second content path can NEVER
    diverge from the id-collision guard or the junk/off-topic screen. Returns a ``FoldInResult``
    carrying the survivors and per-stage counts for the caller's disclosure/markdown. ``insert``
    is always True in production; a caller may set it False to inspect the survivors without
    mutating the store.
    """
    existing_urls = workspace.existing_urls()
    deduped_rows = [
        r for r in fetched_rows
        if str(r.get("source_url") or r.get("url") or "").strip() not in existing_urls
        or not str(r.get("source_url") or r.get("url") or "").strip()
    ]
    n_url_dup = len(fetched_rows) - len(deduped_rows)

    offset = workspace.next_ev_offset()
    existing_ids = set(workspace.ev_store.keys())
    renumbered = _offset_renumber(deduped_rows, offset, existing_ids)

    kept_rows, deleted_chrome, deleted_offtopic = await _stamp_and_delete(
        renumbered, research_question, agent_model,
    )

    if insert:
        for row in kept_rows:
            workspace.ev_store[row["evidence_id"]] = row

    return FoldInResult(
        kept_rows=kept_rows,
        n_url_dup=n_url_dup,
        deleted_chrome=deleted_chrome,
        deleted_offtopic=deleted_offtopic,
    )
