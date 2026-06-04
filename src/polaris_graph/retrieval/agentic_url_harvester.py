"""I-cap-002 feature 3/4 (#1060): harvest DISCOVERED URLs from an agentic-search result + a pure
seed-URL evidence merge core.

The agentic loop (``agents/searcher.execute_agentic_search``) is used in the benchmark for **URL
DISCOVERY ONLY**. Its LLM-written page summaries (``agentic_research_notebook``) must NEVER become
evidence — POLARIS's core invariant is verbatim-span faithfulness, and a model paraphrase masquerading
as a ``direct_quote`` would be a fabrication. So we read ONLY the discovered URLs here; the discovered
URLs are then fetched **verbatim** by ``live_retriever.run_live_retrieval(seed_urls=…, seed_only=True)``
and verified by strict_verify + the 4-role seam, exactly like the rest of the corpus.

Two pure, stdlib-light functions (no network, no LLM, no new dependency):
- ``harvest_agentic_urls`` — ordered, canonical-deduped, capped list of discovered URLs (originals).
- ``merge_seed_url_evidence`` — the deepener's dedup-by-URL + global evidence-id renumber core, factored
  out so it is unit-testable (and a future PR can repoint the deepener at it).
"""

from __future__ import annotations

from typing import Any

from src.polaris_graph.retrieval.saturation import canonical_source_url


def harvest_agentic_urls(
    agentic_result: dict[str, Any] | None,
    cap: int = 200,
) -> list[str]:
    """Return ONLY the discovered URLs from an ``execute_agentic_search`` result.

    Order-preserving and DETERMINISTIC: harvests from the ordered ``web_results`` then
    ``academic_results`` streams first (these are the authoritative, complete, append-ordered streams —
    incl. post-loop DDG / citation-chase URLs), then supplements with any ``agentic_url_accumulator``
    entries not already seen. De-duplicates by ``canonical_source_url`` (scheme/tracking-stripped) but
    RETURNS the original fetchable URL (canonical strings would hurt the live fetch yield). Returns at
    most ``cap`` URLs. NEVER reads ``agentic_research_notebook`` / summaries / snippets. Robust to
    missing/empty keys (returns ``[]`` rather than raising). ``cap <= 0`` → ``[]``.
    """
    if cap <= 0:
        return []
    result = agentic_result or {}
    seen_canonical: set[str] = set()
    out: list[str] = []

    def _consider(raw: Any) -> None:
        if len(out) >= cap:
            return
        url = (raw or "").strip() if isinstance(raw, str) else ""
        if not url:
            return
        try:
            key = canonical_source_url(url) or url
        except Exception:  # noqa: BLE001 — a malformed URL must not abort discovery
            key = url
        if key in seen_canonical:
            return
        seen_canonical.add(key)
        out.append(url)

    # Ordered result streams first (deterministic, complete).
    for stream_key in ("web_results", "academic_results"):
        for rec in result.get(stream_key, []) or []:
            if len(out) >= cap:
                return out
            if isinstance(rec, dict):
                _consider(rec.get("url"))
    # Supplement with the accumulator (subset; set-ordered, so appended last for completeness only).
    for url in result.get("agentic_url_accumulator", []) or []:
        if len(out) >= cap:
            return out
        _consider(url)
    return out


def merge_seed_url_evidence(
    staged_sources: list[Any],
    staged_rows: list[dict[str, Any]],
    new_sources: list[Any],
    new_rows: list[dict[str, Any]],
) -> tuple[list[Any], list[dict[str, Any]], int, int]:
    """Dedup-by-URL source merge + global evidence-id renumber (the deepener's accepted-source core).

    - ``new_sources`` whose ``.url`` is not already among ``staged_sources`` are appended; their URLs
      form the ACCEPTED set.
    - Only ``new_rows`` whose source URL (``source_url`` or ``url``) is in the ACCEPTED set are
      appended — so a duplicate source contributes NO rows (no evidence_row_count inflation).
    - Appended rows get a fresh ``evidence_id`` = ``ev_{base + i:03d}`` from ``len(staged_rows)`` so ids
      never collide/overwrite.

    Returns ``(merged_sources, merged_rows, accepted_source_count, accepted_row_count)``. Operates on
    COPIES; the inputs are not mutated. No I/O.
    """
    merged_sources = list(staged_sources)
    seen_urls = {getattr(s, "url", None) for s in merged_sources}
    accepted_src_urls: set[str] = set()
    accepted_sources = 0
    for src in new_sources:
        url = getattr(src, "url", None)
        if url and url not in seen_urls:
            seen_urls.add(url)
            merged_sources.append(src)
            accepted_src_urls.add(url)
            accepted_sources += 1

    merged_rows = list(staged_rows)
    base = len(merged_rows)
    accepted_rows = 0
    for ev in new_rows:
        ev_url = (ev.get("source_url") or ev.get("url") or "").strip()
        if not ev_url or ev_url not in accepted_src_urls:
            continue  # duplicate / not an accepted source — skip (no inflation)
        ev = dict(ev)  # copy so the caller's row object is not mutated
        ev["evidence_id"] = f"ev_{base + accepted_rows:03d}"
        merged_rows.append(ev)
        accepted_rows += 1

    return merged_sources, merged_rows, accepted_sources, accepted_rows
