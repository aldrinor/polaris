"""I-cap-002 feature 3/4 (#1060): harvest DISCOVERED URLs from an agentic-search result + a pure
seed-URL evidence merge core.

The agentic loop (``agents/searcher.execute_agentic_search``) is used in the benchmark for **URL
DISCOVERY ONLY**. Its LLM-written page summaries (``agentic_research_notebook``) must NEVER become
evidence — POLARIS's core invariant is verbatim-span faithfulness, and a model paraphrase masquerading
as a ``direct_quote`` would be a fabrication. So we read ONLY the discovered URLs here; the discovered
URLs are then fetched **verbatim** by ``live_retriever.run_live_retrieval(seed_urls=…, seed_only=True)``
and verified by strict_verify + the 4-role seam, exactly like the rest of the corpus.

Pure, stdlib-light functions (no network, no LLM, no new dependency):
- ``harvest_agentic_url_records`` — BUG-8 (I-arch-006 #1262): ordered, canonical-deduped, capped list
  of discovered candidates as ``HarvestedUrl`` records carrying the URL **plus** the search-engine
  ``title``/``snippet`` ANCHOR so a downstream topical-relevance screen has text to screen on. The
  snippet/title is search-API result metadata (the search-engine excerpt, NOT a POLARIS LLM
  paraphrase) used ONLY as a topical-screen WEIGHT input — it is NEVER promoted into evidence.
- ``harvest_agentic_urls`` — the URL-ONLY view (a thin wrapper over the record harvester): an ordered,
  canonical-deduped, capped list of discovered URLs (originals), for callers that want just URLs.
- ``harvest_storm_urls`` — BB-006 (#1171): the same URL-ONLY harvest applied to a STORM-interview
  result's ``web_results`` / ``academic_results`` streams (the 478/540 interview search-result URLs the
  benchmark previously discarded). NEVER reads STORM's synthesized answer/key_findings/snippet text.
- ``merge_seed_url_evidence`` — the deepener's dedup-by-URL + global evidence-id renumber core, factored
  out so it is unit-testable (and a future PR can repoint the deepener at it).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.polaris_graph.retrieval.saturation import canonical_source_url


@dataclass(frozen=True)
class HarvestedUrl:
    """A discovered candidate URL carried together with its search-engine ANCHOR (BUG-8, #1262).

    The ``title``/``snippet`` come from the upstream SEARCH-API result record (e.g.
    ``searcher.execute_agentic_search`` populates ``snippet`` from the result's abstract/title) — they
    are the search engine's own excerpt, NOT a POLARIS-LLM paraphrase. They are carried here ONLY so a
    later topical-relevance screen can WEIGHT a candidate (does it look on-topic?) without re-fetching.

    FAITHFULNESS (why this is safe): the anchor is a topical-screen WEIGHT input, never evidence. The
    candidate URL is still fetched VERBATIM by ``live_retriever.run_live_retrieval(seed_urls=…,
    seed_only=True)`` and every claim is gated by strict_verify + the 4-role seam exactly as before —
    promoting the snippet into a ``direct_quote`` would be a fabrication and is NOT done anywhere here.
    Per §-1.3 DNA this ENABLES a future WEIGHT-not-drop screen; it adds NO drop/filter/cap of its own.
    """

    url: str
    title: str = ""
    snippet: str = ""
    source_stream: str = ""  # "web_results" | "academic_results" | "agentic_url_accumulator"


def harvest_agentic_url_records(
    agentic_result: dict[str, Any] | None,
    cap: int = 200,
) -> list[HarvestedUrl]:
    """Return the discovered candidates from an ``execute_agentic_search`` result as ``HarvestedUrl``
    records — the URL **plus** its search-engine ``title``/``snippet`` anchor (BUG-8, I-arch-006 #1262).

    THE BUG (BUG-8 half-2): ``harvest_agentic_urls`` returned URL-ONLY, so a downstream topical-relevance
    screen had nothing to screen on. THE FIX: also carry a short anchor (title + snippet, from the search
    result the harvester ALREADY iterates) so a later WEIGHT-not-drop topical screen can judge relevance
    without a re-fetch. WHY FAITHFULNESS IS SAFE: the anchor is search-API metadata used only as a screen
    WEIGHT input; it is NEVER promoted into evidence (URLs are still fetched VERBATIM and gated by
    strict_verify + the 4-role seam). This harvester adds NO drop/filter/cap of its own (§-1.3 DNA).

    Order-preserving and DETERMINISTIC: harvests from the ordered ``web_results`` then ``academic_results``
    streams first (the authoritative, complete, append-ordered streams — incl. post-loop DDG / citation-
    chase URLs), then supplements with any ``agentic_url_accumulator`` entries not already seen.
    De-duplicates by ``canonical_source_url`` (scheme/tracking-stripped) but RETURNS the original fetchable
    URL (canonical strings would hurt the live fetch yield) and keeps the FIRST record's anchor. Returns at
    most ``cap`` records. NEVER reads ``agentic_research_notebook`` summaries (an LLM paraphrase). Robust to
    missing/empty keys (returns ``[]`` rather than raising). ``cap <= 0`` → ``[]``.
    """
    if cap <= 0:
        return []
    result = agentic_result or {}
    seen_canonical: set[str] = set()
    out: list[HarvestedUrl] = []

    def _consider(raw: Any, *, title: Any = "", snippet: Any = "", stream: str = "") -> None:
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
        out.append(
            HarvestedUrl(
                url=url,
                title=title.strip() if isinstance(title, str) else "",
                snippet=snippet.strip() if isinstance(snippet, str) else "",
                source_stream=stream,
            )
        )

    # Ordered result streams first (deterministic, complete). Anchor = search-engine title/snippet.
    for stream_key in ("web_results", "academic_results"):
        for rec in result.get(stream_key, []) or []:
            if len(out) >= cap:
                return out
            if isinstance(rec, dict):
                _consider(
                    rec.get("url"),
                    title=rec.get("title", ""),
                    snippet=rec.get("snippet", ""),
                    stream=stream_key,
                )
    # Supplement with the accumulator (a URL-only subset — no per-URL anchor available there).
    for url in result.get("agentic_url_accumulator", []) or []:
        if len(out) >= cap:
            return out
        _consider(url, stream="agentic_url_accumulator")
    return out


def harvest_agentic_urls(
    agentic_result: dict[str, Any] | None,
    cap: int = 200,
) -> list[str]:
    """Return ONLY the discovered URLs from an ``execute_agentic_search`` result (URL-only view).

    Backward-compatible thin wrapper over ``harvest_agentic_url_records`` (BUG-8, I-arch-006 #1262): same
    ordered, canonical-deduped, capped discovery, but projected down to the original fetchable URL strings
    that existing callers (``run_honest_sweep_r3.py``) already consume. NEVER reads
    ``agentic_research_notebook`` / summaries. Robust to missing/empty keys (returns ``[]`` rather than
    raising). ``cap <= 0`` → ``[]``.
    """
    return [rec.url for rec in harvest_agentic_url_records(agentic_result, cap=cap)]


def harvest_storm_urls(
    storm_result: dict[str, Any] | None,
    cap: int = 200,
) -> list[str]:
    """BB-006 (I-beatboth-fix-000 #1171): return ONLY the discovered URLs from a STORM
    ``run_storm_interviews`` result — the EXACT analogue of ``harvest_agentic_urls``.

    STORM grounds its multi-perspective interviews in REAL internet search results. Those
    URLs (``storm_result["web_results"]`` then ``["academic_results"]``, each a dict with
    ``url``/``title``/``snippet``) are legitimate candidate sources — but the run previously
    DISCARDED them, only re-using STORM's synthesized interview QUESTIONS as query strings.

    HARD URL-ONLY CONTRACT (faithfulness): this reads ONLY ``rec["url"]``. It NEVER reads the
    STORM-synthesized ``answer`` / ``key_findings`` / outline / conversation text, and NEVER
    the per-record ``snippet`` — promoting any LLM-synthesized STORM text into the evidence
    pool would be a fabrication path. The harvested URLs are then fetched VERBATIM by
    ``live_retriever.run_live_retrieval(seed_urls=…, seed_only=True)`` and gated by
    strict_verify + the 4-role seam exactly like every other candidate (empty direct_quote).

    Order-preserving + DETERMINISTIC; de-duplicates by ``canonical_source_url`` but RETURNS the
    original fetchable URL. Returns at most ``cap`` URLs. Robust to missing/empty keys (returns
    ``[]`` rather than raising). ``cap <= 0`` -> ``[]``.
    """
    if cap <= 0:
        return []
    result = storm_result or {}
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

    # Ordered result streams (deterministic). URL key ONLY — never answer/key_findings/snippet.
    for stream_key in ("web_results", "academic_results"):
        for rec in result.get(stream_key, []) or []:
            if len(out) >= cap:
                return out
            if isinstance(rec, dict):
                _consider(rec.get("url"))
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
