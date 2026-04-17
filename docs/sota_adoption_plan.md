# SOTA Adoption Plan — Concrete Patches Against Existing OSS Patterns

This plan stops the "invent a fix every sprint" pattern. Each patch cites its open-source source, pins the pattern to specific file lines, and provides the diff.

All four patches target the defects documented in `docs/pg_lb_sa_01_deep_audit.md`. They are independent and can be applied in any order, but the suggested order maximises content-integrity return per line of change.

---

## Patch A — Reflexion re-audit loop

**Source:** `noahshinn/reflexion` — nested `while cur_iter < max_iters` with verify-rewrite-verify cycle.

**Defect it closes:** Deep audit §"What shipped broken" #1 — 8 sections flagged at 74.3 % unsupported, rewrites fired, but no second NLI audit ran before finalize. The final report could still be 74 % unsupported.

**Target file:** `src/polaris_graph/wiki/wiki_composer.py` lines 636-743.

**Pattern (Reflexion iteration):**
```python
cur_iter = 0
while cur_iter < max_iters:
    cur_iter += 1
    is_passing, feedback, _ = exe.execute(cur_func_impl, tests_i)
    if is_passing or cur_iter == max_iters - 1:
        break
    # reflect → rewrite → loop re-verifies
```

**Diff (summary):**

```diff
--- src/polaris_graph/wiki/wiki_composer.py  (current)
+++ src/polaris_graph/wiki/wiki_composer.py  (patched)
@@ -636,8 +636,24 @@
                 # FIX-HALLUC-REMEDIATE: Re-compose flagged sections with stricter
                 # anti-hallucination emphasis.
-                if flagged > 0:
-                    flagged_ids = {...}
+                MAX_REWRITE_ITERS = int(os.getenv("PG_HALLUC_MAX_ITERS", "2"))
+                cur_iter = 0
+                while flagged > 0 and cur_iter < MAX_REWRITE_ITERS:
+                    cur_iter += 1
+                    logger.info(
+                        "[wiki-compose] REMEDIATE-LOOP: iter %d/%d — %d flagged",
+                        cur_iter, MAX_REWRITE_ITERS, flagged,
+                    )
+                    flagged_ids = {
                         r["section_id"]
                         for r in hallucination_audit
                         if r.get("needs_rewrite")
                     }
@@ -715,7 +731,29 @@
                     if rewrite_count > 0:
                         # regenerate abstract from post-remediation sections
                         ...
+                        # REFLEXION: re-audit the rewritten sections before
+                        # deciding whether to loop again. Previously this audit
+                        # never ran, so the final report could still be 74%
+                        # unsupported as in PG_LB_SA_01.
+                        try:
+                            reaudit_sections = [
+                                {
+                                    "section_id": s.get("section_id", ""),
+                                    "title": s.get("title", ""),
+                                    "content": s.get("content", ""),
+                                    "evidence_ids": s.get("evidence_ids", []),
+                                }
+                                for s in sections
+                            ]
+                            hallucination_audit = audit_sections_for_hallucination(
+                                sections=reaudit_sections,
+                                evidence=evidence_chain,
+                                research_query=query,
+                            ) or []
+                            flagged = sum(
+                                1 for r in hallucination_audit
+                                if r.get("needs_rewrite")
+                            )
+                            avg = sum(
+                                r.get("hallucination_ratio", 0)
+                                for r in hallucination_audit
+                            ) / max(len(hallucination_audit), 1)
+                            logger.info(
+                                "[wiki-compose] REMEDIATE-LOOP: iter %d post-rewrite "
+                                "avg unsupported %.1f%%, %d still flagged",
+                                cur_iter, avg * 100, flagged,
+                            )
+                        except Exception as _reaudit_exc:
+                            logger.warning(
+                                "[wiki-compose] REMEDIATE-LOOP: re-audit failed: %s — "
+                                "exiting loop",
+                                str(_reaudit_exc)[:200],
+                            )
+                            break
+                    else:
+                        # No rewrites succeeded this iteration; don't loop forever.
+                        break
+                if flagged > 0:
+                    logger.warning(
+                        "[wiki-compose] REMEDIATE-LOOP: still %d sections flagged "
+                        "after %d iterations — shipping with known defects",
+                        flagged, MAX_REWRITE_ITERS,
+                    )
```

**Env var:** `PG_HALLUC_MAX_ITERS` (default 2). Safe because rewrites are bounded and each iteration logs its own metrics.

**Tests to add:** `tests/polaris_graph/test_halluc_reaudit_loop.py`:
1. Mock 2 sections; first audit flags both; after rewrite first pass flags 1; after second pass flags 0 → loop exits.
2. Mock 2 sections; all rewrites fail → loop breaks immediately on first `rewrite_count == 0`.
3. Mock 2 sections; 3rd audit still flags 2 → loop exits at `MAX_REWRITE_ITERS=2` with warning log.
4. Env var override to 1 disables second pass.

**Expected impact:** PG_LB_SA_01-scale runs should exit the loop with <25 % unsupported per section, OR with an explicit warning that the rewrite didn't converge. Either way the current silent-defect case is eliminated.

---

## Patch B — STORM cross-section polish pass

**Source:** `stanford-oval/storm/knowledge_storm/storm_wiki/modules/article_polish.py` — `PolishPageModule` with `remove_duplicate=True`.

**Defect it closes:** Deep audit §Dimension 10 — §Risks line 91 disclaims six signals that are characterized in other sections (DVT, thyroid C-cell, suicidality, lean-mass, rebound regain, malnutrition). Section-isolated composition cannot see the contradiction.

**STORM's prompt (paraphrased from article_polish.py):**
> "You are a faithful text editor that is good at finding repeated information in the article and deleting them to make sure there is no repetition in the article. You won't delete any non-repeated part in the article. You will keep the inline citations and article structure (indicated by '#', '##', etc.) appropriately. Do your job for following article."

**Target file:** `src/polaris_graph/wiki/wiki_composer.py` — new function `_polish_cross_section` called after the REMEDIATE loop, before `_assemble_report` (current line 814).

**Drop-in function:**

```python
# Append to wiki_composer.py

POLISH_ENABLED = os.getenv("PG_CROSS_SECTION_POLISH", "1") == "1"

async def _polish_cross_section(
    client: OpenRouterClient,
    query: str,
    sections: list[dict],
    abstract: str,
) -> tuple[list[dict], str]:
    """STORM-style cross-section polish pass.

    Runs ONE LLM call over the concatenated report to detect and repair
    two classes of cross-section defects:

    1. DISCLAIMERS-THAT-CONTRADICT-CONTENT: a section that says
       "X is not characterized here" / "the evidence does not include Y"
       when X or Y IS characterized in another section of the same document.
       (PG_LB_SA_01 §Risks line 91 → DVT, thyroid C-cell, etc.)

    2. DUPLICATE CLAIMS: the same numeric finding repeated verbatim across
       sections with different framing. The polish pass keeps the most
       contextual occurrence and trims the duplicate.

    The pass preserves inline [N] citations and H2/H3 structure exactly —
    STORM's prompt explicitly mandates this. No claim is added; claims may
    only be removed or reworded.
    """
    if not POLISH_ENABLED or len(sections) < 2:
        return sections, abstract

    # Concatenate for cross-section visibility
    section_texts = []
    for s in sections:
        title = s.get("title", "")
        content = s.get("content", "")
        section_texts.append(f"## {title}\n\n{content}")
    joined = "\n\n".join(section_texts)

    system = (
        "You are a faithful text editor. You find two kinds of defects in "
        "multi-section evidence reports and repair them:\n\n"
        "(A) DISCLAIMERS-THAT-CONTRADICT-CONTENT. A sentence that says a "
        "topic is 'not characterized here' / 'not substantiated by the "
        "claims' / 'not covered in this section' — when another section of "
        "the same document DOES characterize that topic. Repair: delete the "
        "false disclaimer sentence. Do not invent new content.\n\n"
        "(B) DUPLICATE CLAIMS. The same numeric finding stated twice across "
        "different sections with the same citation. Repair: keep the most "
        "contextual occurrence, delete the other. Do not merge citations "
        "into unrelated sentences.\n\n"
        "HARD RULES:\n"
        "- Preserve every [N] citation marker. Do not renumber.\n"
        "- Preserve every '## Title' heading. Do not rename sections.\n"
        "- Do not add new factual claims. Only remove or shorten.\n"
        "- Return the full edited report, section headings intact.\n"
    )
    prompt = (
        f"Original research question: {query}\n\n"
        f"Report to polish:\n\n{joined}\n\n"
        "Return the polished report. Preserve all ## headings and [N] citations."
    )

    try:
        polished = await client.generate(
            prompt=prompt,
            system=system,
            max_tokens=COMPOSE_MAX_TOKENS,
            temperature=0.1,
            call_type="generate:polish",
        )
    except Exception as exc:
        logger.warning(
            "[wiki-compose] POLISH: cross-section polish failed: %s — "
            "shipping unpolished",
            str(exc)[:200],
        )
        return sections, abstract

    if not polished or len(polished) < len(joined) * 0.5:
        logger.warning(
            "[wiki-compose] POLISH: polish output truncated "
            "(%d chars vs original %d) — shipping unpolished",
            len(polished or ""), len(joined),
        )
        return sections, abstract

    # Re-split by '## ' heading. Preserve original section_ids and
    # evidence_ids; only content text is replaced.
    new_section_map = {}
    for block in re.split(r"(?m)^##\s+", polished):
        block = block.strip()
        if not block:
            continue
        first_nl = block.find("\n")
        if first_nl == -1:
            continue
        title = block[:first_nl].strip()
        content = block[first_nl + 1:].strip()
        new_section_map[title] = content

    polished_sections = []
    for s in sections:
        title = s.get("title", "")
        new_content = new_section_map.get(title)
        if new_content is None:
            polished_sections.append(s)
            continue
        polished_sec = dict(s)
        polished_sec["content"] = new_content
        polished_sections.append(polished_sec)

    logger.info(
        "[wiki-compose] POLISH: cross-section polish applied "
        "(%d sections, input=%d chars, output=%d chars)",
        len(polished_sections), len(joined), len(polished),
    )
    return polished_sections, abstract
```

**Call site (wiki_composer.py around current line 814, before `_assemble_report`):**
```python
sections, abstract = await _polish_cross_section(
    client=client, query=query, sections=sections, abstract=abstract,
)
```

**Env var:** `PG_CROSS_SECTION_POLISH` (default `1`, disable for A/B comparison).

**Tests:**
1. Input with §Risks disclaiming "DVT not characterized" and §Pharmacology citing DVT → disclaimer removed, Pharmacology preserved.
2. Input with no disclaimers and no duplicates → output equals input (no unintended edits).
3. Polish LLM returns garbage (<50 % of input length) → fallback to unpolished, warning logged.
4. Polish LLM adds a fabricated sentence → verify by citation-set-equality check; if polished set ⊄ original, reject.

**Limitation inherited from STORM:** deduplication is LLM-reasoning based. No algorithmic cross-section comparison. Trade-off acknowledged: if the polish LLM itself is weak (the operator-fabrication concern in loopback), this becomes another self-grading layer. Mitigation: make this the ONLY place where cross-section reconciliation happens, so running it without a polish call gives A/B evidence.

---

## Patch C — FDA/EMA regulatory label dedup by setid

**Source:** FDA `accessdata.fda.gov/drugsatfda_docs/label/<YEAR>/<NDC>s<REV>lbl.pdf` URL structure. The `<NDC>s<REV>` pair — for WEGOVY: `215256s000`, `215256s007`, `215256s024`, `215256s033` — all share the application number `215256` which identifies the drug, not the label revision.

**Defect it closes:** Deep audit §Dimension 7 — four WEGOVY label revisions `[26][27][28][29]` treated as four distinct bibliography entries. Current `FIX-DEDUP-PAPER` (wiki_builder.py lines 958-1002) keys on DOI / PMID and finds no collisions for regulatory documents.

**Target file:** `src/polaris_graph/wiki/wiki_builder.py` — extend `_extract_pmid` and `_extract_doi` helpers with a third extractor `_extract_regulatory_id`.

**Diff (wiki_builder.py, lines 964-985):**

```diff
     def _extract_pmid(u: str) -> str:
         m = re.search(r"/articles/PMC(\d+)", u or "")
         return f"pmc{m.group(1)}" if m else ""

+    def _extract_regulatory_id(u: str) -> str:
+        """Collapse FDA/EMA labels across revisions.
+
+        FDA accessdata.fda.gov path:
+          /drugsatfda_docs/label/<YEAR>/<NDC>s<REV>lbl.pdf
+        The <NDC> (application number) identifies the drug. <REV> is the
+        revision. Four WEGOVY labels 215256s000/s007/s024/s033 all share
+        NDC=215256 and should collapse to one bibliography entry.
+
+        EMA ema.europa.eu path:
+          /en/documents/product-information/<product>-epar-product-information_en.pdf
+        The <product> slug identifies the drug across revisions.
+        """
+        # FDA: capture application number before 's<rev>'
+        m = re.search(
+            r"/drugsatfda_docs/label/\d+/(\d+)s\d+lbl\.pdf",
+            u or "",
+            re.IGNORECASE,
+        )
+        if m:
+            return f"fda-{m.group(1)}"
+        # EMA: capture product slug before '-epar-product-information'
+        m = re.search(
+            r"/product-information/([^/]+?)-epar-product-information",
+            u or "",
+            re.IGNORECASE,
+        )
+        if m:
+            return f"ema-{m.group(1).lower()}"
+        return ""
+
     def _extract_doi(best_claim: dict, url: str) -> str:
         ...

     paper_key_to_canonical: dict[str, str] = {}
     canonical_to_merge_targets: dict[str, list[str]] = {}
     for canonical, best in url_to_best.items():
         url_display = canonical_to_display.get(canonical, canonical)
         doi = _extract_doi(best, url_display)
         pmid = _extract_pmid(url_display)
-        paper_key = doi or pmid
+        regulatory = _extract_regulatory_id(url_display)
+        paper_key = doi or pmid or regulatory
         if not paper_key:
             continue
```

**Tests:**
1. Four WEGOVY URLs with s000/s007/s024/s033 revisions → one bibliography entry with 4 evidence_ids.
2. Ozempic + WEGOVY (same manufacturer, different NDC) → two distinct entries.
3. Ozempic EMA label at two revision URLs → one entry.
4. An FDA label and a PMC review both about semaglutide → two entries (doi/pmid vs fda keys don't collide).

**Bibliography metadata:** when merging, keep the most recent year and display that label's URL. Older revisions attach as additional `evidence_ids`.

---

## Patch D — OpenAlex authority tier + work_id dedup

**Source:** OpenAlex `/works` API. Per `api.openalex.org`:
- `type`: `"article"`, `"book"`, `"dataset"`, `"preprint"`, `"book-chapter"`, `"editorial"`, `"letter"`, `"review"`, `"other"`.
- `primary_location.source.type`: `"journal"`, `"repository"`, `"book series"`, `"ebook platform"`, `"conference"`.
- Top-level `id`: canonical OpenAlex work ID (e.g. `https://openalex.org/W4396850943`) that dedupes across mirror locations (PubMed Central + publisher PDF + institutional repository).

**Defect it closes:** Deep audit §Dimension 7 (authority) + §Dimension 1 (non-peer-reviewed sources tiered SILVER). Six references on this run — Motley Rice law firm [15], Medium blog [5], Fella Health telehealth [7], thegutpunch blog [18], ResearchSquare preprint [32], NHS JS high-school journal [4] — all tiered SILVER despite being non-peer-reviewed. OpenAlex would flag these by `type` and `source.type`.

**New file:** `src/polaris_graph/tools/openalex_client.py`

```python
"""OpenAlex API client for source canonicalization and authority scoring.

Adopted from the OpenAlex public API (docs.openalex.org). Free, no key
required, 100 000 requests/day anon, 10 req/sec with polite pool header.

Two operations:

1. canonicalize(url, doi, title) -> OpenAlexWork | None
   Returns the canonical OpenAlex work ID, source type, and publication
   type. Used for bibliography dedup across revisions (same work at
   publisher vs PMC vs institutional repo collapses to one work_id) and
   for authority-tier gating.

2. authority_tier(work) -> 'GOLD' | 'SILVER' | 'BRONZE' | 'BLOCKED'
   Maps (type, source.type, is_retracted) to our internal tier:

     GOLD:    type in {'article', 'review'} and source.type == 'journal'
              and not is_retracted
     SILVER:  type == 'preprint' OR source.type == 'repository'
              (preprints and institutional repos — legitimate but
               unreviewed)
     BRONZE:  type in {'book-chapter', 'book', 'dataset', 'editorial',
              'letter', 'other'}
              (grey literature, non-primary)
     BLOCKED: is_retracted OR type == 'erratum'
              (explicit retractions block citation)
"""
from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

OPENALEX_BASE = "https://api.openalex.org"
POLITE_EMAIL = os.getenv("OPENALEX_EMAIL", "")
CACHE_DB = Path(os.getenv("OPENALEX_CACHE_DB", "cache/openalex.sqlite"))
TIMEOUT = float(os.getenv("OPENALEX_TIMEOUT", "10"))
ENABLED = os.getenv("PG_OPENALEX_ENABLED", "1") == "1"


@dataclass
class OpenAlexWork:
    work_id: str            # canonical: https://openalex.org/W...
    doi: str                # https://doi.org/10... or ''
    title: str
    type: str               # 'article', 'preprint', 'book-chapter', ...
    source_type: str        # 'journal', 'repository', 'book series', ...
    source_name: str        # e.g. 'Nature Medicine'
    publication_year: int
    is_retracted: bool

    def authority_tier(self) -> str:
        if self.is_retracted or self.type == "erratum":
            return "BLOCKED"
        if self.type in {"article", "review"} and self.source_type == "journal":
            return "GOLD"
        if self.type == "preprint" or self.source_type == "repository":
            return "SILVER"
        return "BRONZE"


def _cache_init() -> None:
    CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(CACHE_DB)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS works ("
        " key TEXT PRIMARY KEY,"          # 'doi:10...' or 'title:...'
        " work_id TEXT,"
        " doi TEXT,"
        " title TEXT,"
        " type TEXT,"
        " source_type TEXT,"
        " source_name TEXT,"
        " publication_year INTEGER,"
        " is_retracted INTEGER,"
        " fetched_at TEXT DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.commit()
    conn.close()


def _cache_get(key: str) -> Optional[OpenAlexWork]:
    if not CACHE_DB.exists():
        return None
    conn = sqlite3.connect(CACHE_DB)
    row = conn.execute(
        "SELECT work_id, doi, title, type, source_type, source_name,"
        " publication_year, is_retracted FROM works WHERE key = ?",
        (key,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return OpenAlexWork(
        work_id=row[0], doi=row[1], title=row[2], type=row[3],
        source_type=row[4], source_name=row[5], publication_year=row[6],
        is_retracted=bool(row[7]),
    )


def _cache_put(key: str, w: OpenAlexWork) -> None:
    conn = sqlite3.connect(CACHE_DB)
    conn.execute(
        "INSERT OR REPLACE INTO works (key, work_id, doi, title, type,"
        " source_type, source_name, publication_year, is_retracted)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (key, w.work_id, w.doi, w.title, w.type, w.source_type,
         w.source_name, w.publication_year, int(w.is_retracted)),
    )
    conn.commit()
    conn.close()


async def _fetch_work(params: dict) -> Optional[dict]:
    headers = {"User-Agent": f"POLARIS/1.0 (mailto:{POLITE_EMAIL})"} if POLITE_EMAIL else {}
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.get(f"{OPENALEX_BASE}/works", params=params, headers=headers)
        if r.status_code != 200:
            return None
        data = r.json()
        results = data.get("results", [])
        return results[0] if results else None


def _parse_work(data: dict) -> OpenAlexWork:
    primary = data.get("primary_location") or {}
    source = primary.get("source") or {}
    return OpenAlexWork(
        work_id=data.get("id", ""),
        doi=data.get("doi", "") or "",
        title=data.get("title", "") or "",
        type=data.get("type", "other") or "other",
        source_type=source.get("type", "") or "",
        source_name=source.get("display_name", "") or "",
        publication_year=data.get("publication_year", 0) or 0,
        is_retracted=bool(data.get("is_retracted", False)),
    )


async def canonicalize(
    url: str = "",
    doi: str = "",
    title: str = "",
) -> Optional[OpenAlexWork]:
    """Look up a work by DOI first, fall back to title search."""
    if not ENABLED:
        return None
    _cache_init()

    if doi:
        key = f"doi:{doi.lower().lstrip('https://doi.org/').rstrip('/')}"
        hit = _cache_get(key)
        if hit:
            return hit
        data = await _fetch_work({"filter": f"doi:{doi}"})
        if data:
            w = _parse_work(data)
            _cache_put(key, w)
            return w

    if title:
        key = f"title:{title.lower().strip()[:200]}"
        hit = _cache_get(key)
        if hit:
            return hit
        data = await _fetch_work({"search": title[:300], "per_page": 1})
        if data:
            w = _parse_work(data)
            _cache_put(key, w)
            return w

    return None
```

**Integration into `_build_bibliography` (wiki_builder.py line 921):**

```diff
 def _build_bibliography(section_claims: dict[str, list[dict]]) -> list[dict]:
     ...
+    # PATCH D: OpenAlex authority + work_id dedup
+    from src.polaris_graph.tools import openalex_client
+    if openalex_client.ENABLED:
+        openalex_cache = {}  # canonical_url -> OpenAlexWork | None
+        for canonical, best in url_to_best.items():
+            try:
+                # Reuse existing doi extraction
+                doi = _extract_doi(best, canonical_to_display.get(canonical, canonical))
+                title = best.get("source_title", "")
+                loop = asyncio.get_event_loop()
+                w = loop.run_until_complete(
+                    openalex_client.canonicalize(doi=doi, title=title)
+                )
+                openalex_cache[canonical] = w
+            except Exception as exc:
+                logger.debug("[wiki] OpenAlex lookup failed for %s: %s", canonical[:60], exc)
+                openalex_cache[canonical] = None
+
+        # Add OpenAlex work_id as a third dedup key
+        for canonical, w in openalex_cache.items():
+            if w and w.work_id and canonical not in merged_away:
+                if w.work_id not in paper_key_to_canonical:
+                    paper_key_to_canonical[w.work_id] = canonical
+                else:
+                    primary = paper_key_to_canonical[w.work_id]
+                    canonical_to_merge_targets.setdefault(primary, []).append(canonical)
+                    merged_away.add(canonical)
```

**Bibliography entries get two new fields:**
```python
bibliography.append({
    ...
    "openalex_id": w.work_id if w else "",
    "source_type_normalized": w.source_type if w else "",  # 'journal' / 'repository' / ...
    "publication_type": w.type if w else "",               # 'article' / 'preprint' / ...
    "authority_tier": w.authority_tier() if w else "UNKNOWN",
    ...
})
```

**Authority gate wire-in (separate from this patch):** The evidence tier assigner (`src/polaris_graph/synthesis/quality_tier_assigner.py` — verify path) reads `authority_tier` from the bibliography entry and OVERRIDES its computed tier if BRONZE or BLOCKED. Law firms (Motley Rice), Medium blogs, telehealth sites will fail OpenAlex lookup (no DOI, no academic title match) → `authority_tier = UNKNOWN`. They get demoted to BRONZE by a second rule: `if authority_tier in {'UNKNOWN', 'BRONZE', 'BLOCKED'}: tier = 'BRONZE'`.

**Env vars:**
- `PG_OPENALEX_ENABLED` (default 1)
- `OPENALEX_EMAIL` (recommended — unlocks the polite pool with 10x higher rate limits)
- `OPENALEX_CACHE_DB` (default `cache/openalex.sqlite`)
- `OPENALEX_TIMEOUT` (default 10s)

**Tests:**
1. DOI 10.1056/NEJMoa2307563 → SELECT trial → `type=article`, `source_type=journal` → GOLD.
2. ResearchSquare URL → `type=preprint` → SILVER.
3. Motley Rice URL + no DOI + title not in OpenAlex → `None` → UNKNOWN → demoted to BRONZE.
4. Wegovy 2021 label URL + title "Wegovy Prescribing Information" → OpenAlex probably `None` (regulatory docs not indexed) → UNKNOWN → BRONZE + still gets collapsed by Patch C setid rule.
5. Cache hit path: second call with same DOI returns cached result without HTTP.

**Dependency:** `httpx` — already in `requirements.txt` for other integrations.

---

## Adoption order and cost

| Patch | LOC | Tests | Risk | Impact |
|---|---|---|---|---|
| A — Reflexion re-audit loop | ~50 | 4 | Low (bounded loop with fallback) | Closes "silent 74 % defect" case |
| C — FDA setid dedup | ~40 | 4 | Very low (adds a third dedup key, doesn't modify existing) | Kills four-Wegovy-labels duplication |
| B — STORM polish pass | ~120 + prompt | 4 | Medium (one more LLM call, 5-10s; falls back if output is short) | Closes cross-section contradiction class |
| D — OpenAlex authority | ~200 + new file | 5 | Medium (adds external API dependency; graceful fallback if 404/timeout) | Blocks law firms / Medium blogs from citing |

**Suggested apply order: A → C → B → D.** A and C are near-zero-risk mechanical additions that close two defects immediately. B adds the cross-section polish which needs a real LLM (so it's most useful in a paid run, not a loopback run). D is the biggest change and requires OPENALEX_EMAIL for production use.

Each patch is independently mergeable. Each ships with its own env var so it can be toggled off in a single run for A/B validation.

---

## What this does not fix

Four defects from the deep audit are not addressed here:

1. **Quality gate reads LLM-fallback faithfulness, not NLI.** Separate patch: `src/polaris_graph/graph.py` `quality_gate_result` should read from `hallucination_audit` (post-rewrite-loop) not from `quality_metrics["faithfulness_score"]`. Trivial.
2. **FIX-PRISMA-METHODS / FIX-SANRA-METHODS.** Static boilerplate appended to §Methodology. Trivial. Belongs in `wiki_composer.py` as a `_methods_disclosure()` helper.
3. **Orphan `## Key Findings` H2 on §5.** Markdown linting with `pymarkdown` would catch it before ship. Belongs in a `_validate_markdown_structure()` post-compose step.
4. **Abstract regen 7200s timeout.** Wrap the `await client.generate()` call in `tenacity.retry(stop=stop_after_attempt(2), wait=wait_fixed(60), timeout=300)`. Trivial.

These four are all under 50 LOC each and could be bundled as a single cleanup commit after Patches A-D. They're not called out here because they don't have a clear OSS pattern to copy — they're just bugs.

---

## Validation plan

After applying Patches A+B+C:

1. **Smoke test:** `python -u -m scripts.pg_smoke_test` (expect 16/16 pass).
2. **Loopback re-run:** PG_LB_SA_01 with the same query. Compare `docs/pg_lb_sa_01_deep_audit.md` defect list against the new run. Expected to close: defect #1 (post-rewrite audit missing), §Dimension 7 Wegovy duplicates, §Dimension 10 cross-section contradiction.
3. **Paid validation:** one GLM-5.1 run with PG_LOOPBACK_MODE=0 specifically to separate operator-fabrication effects from pipeline fixes. This is the point where swapping the LLM actually matters — with Patches A/B/C in place, the remaining defects should be LLM-choice-dependent.

After applying Patch D:

4. **OpenAlex live test:** one-off script that canonicalizes 35 bibliography entries from PG_LB_SA_01 and prints their `authority_tier`. Expect: Motley Rice, Medium, thegutpunch, Fella Health → BRONZE; NEJM, PMC, Nature → GOLD; ResearchSquare → SILVER.
5. **Full re-run:** PG_LB_SA_01 + Patch D. Expected to close: six SILVER-tiered non-peer-reviewed sources now BRONZE.

No pipeline changes are LLM-model-dependent. The same patches apply to Claude, GLM, Kimi, Qwen, or GPT-backed runs.
