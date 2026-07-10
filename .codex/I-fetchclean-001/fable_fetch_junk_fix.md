# I-fetchclean-001 — Fetch-junk leak fix design (Fable 5, 2026-07-10)

Live proof: `fetch_corpus_replay.py` over the real 921-URL drb_72 corpus found 90 junk leaks
at 450 scanned inside ACCEPTED spans (`failure_mode == ''`). Two distinct leak classes, two
distinct root causes, both fully traced in the LOCAL code below. Opus builds this immediately.

---

## 1. Root causes (file:line, verified by reading the live code)

### Leak class 1 — WHOLE junk pages accepted (bot_wall x18, error_page x2)

The refetch seam has exactly ONE whole-body junk gate, and it is the WRONG detector.

- `src/polaris_graph/retrieval/live_retriever.py:3316-3336`
  (`refetch_for_extraction_with_diagnostics`): after `_fetch_content`, the ONLY junk checks are
  `_cf.shell_reason` from `clean_fetch_body` (→ `fetch_shell`) and the front-matter screen
  (→ `wrong_content_front_matter`). Nothing else.
- `src/tools/access_bypass.py:2729-2734` (`clean_fetch_body`): `shell_reason` is set ONLY by
  `is_boilerplate_or_nonassertional(text)`.
- `src/tools/access_bypass.py:2464-2539` (`is_boilerplate_or_nonassertional`): its whole
  vocabulary is (a) whole-line crawl-marker fullmatch, (b) bare DOI, (c) table-number row,
  (d) four error tokens (`page not found`/`404`/`403 forbidden`/`access denied`) on a ≤400-char
  unit. **It has ZERO bot-wall / security-verification vocabulary.**

The correct detector already EXISTS and would catch every quoted leak:

- `src/polaris_graph/retrieval/shell_detector.py:85-107` — `CHALLENGE_PAGE_COOCCURRENCE`
  contains `("performing security verification", "protect against malicious bots")`, which is
  byte-for-byte the ev_932 / ev_955 SSRN wall text, and fires at ANY length. But
  `is_access_denial_stub` / `is_cited_span_shell` are NEVER called at the refetch seam. They run
  only inside `is_content_starved` (`live_retriever.py:4545-4586`, a different path) and at the
  cited-span verify gate. This is the exact vocabulary drift `shell_detector.py:14-20` was
  created to prevent — `is_boilerplate_or_nonassertional` was never re-pointed to it.

Two aggravating gaps upstream:

- `src/polaris_graph/retrieval/live_retriever.py:4276-4280` (`_fetch_content` success path):
  `clean_fetch_body(_stripped_body).cleaned_text` — **`shell_reason` is DISCARDED**. A winning
  backend whose body is a bot wall exits the cascade `ok=True` with no shell check at all.
- `src/tools/access_bypass.py:5409-5429` (`_try_jina_reader`): Jina success = HTTP 200 AND
  `len > 100`. A Jina-rendered SSRN/Cloudflare wall (~260 chars of markdown) is a "success"
  and can win the backend race.
- error_page leak ("Something went wrong. Wait a moment…"): this phrase is in NO vocabulary —
  not in `_ERROR_PAGE_TOKENS` (`access_bypass.py:2396-2407`), not in
  `SHORT_BODY_SHELL_MARKERS` (`shell_detector.py:161-180`).

(Note: `is_error_shell_text` / `classify_block_page` in access_bypass (549-913) also exist but
are wired only to the B02/B04 recovered-body adoption path (`live_retriever.py:4589-4633`) and
`classify_block_page` is default-OFF; neither runs at this seam, and `is_error_shell_text`'s
residual-≤3-words gate misses the SSRN wall anyway — its residual prose is too long.)

### Leak class 2 — chrome WELDED inside real articles (nav x64 incl. FPs, cookie x2, gov_banner x2, skip_nav, reading_time, scopus chrome)

- Jina Reader returns FULL-PAGE markdown — nav menus, cookie strips, gov banners, skip-nav
  links, reading-time widgets all included. `_try_jina_reader`
  (`access_bypass.py:5358-5376`) sends no element-removal option.
- `clean_fetch_body` (`access_bypass.py:2688-2734`) is an ALLOWLIST of literal chrome
  patterns (`access_bypass.py:2306-2662`) — Jina preamble, specific Cookiebot lines, specific
  social/login literals. **There is NO generic boilerplate / link-density / main-content pass
  on the markdown.** Every new site's nav is a new whack-a-mole regex.
- trafilatura (already a dependency, guarded entrypoint `safe_trafilatura_extract`
  `access_bypass.py:1931-1960`) runs ONLY on raw-HTML paths (`frame_fetcher.py:1124-1137`
  recovery, `src/utils/ingest.py:470-518`, direct-HTTP). **It is never applied to
  jina/crawl4ai markdown** — the two dominant backends bypass main-content extraction
  entirely.
- crawl4ai DOES use `PruningContentFilter(threshold=0.48)` (`access_bypass.py:4425-4426`) but
  falls back to RAW full-page markdown when fit_markdown is empty (`access_bypass.py:4543-4548`).
- The wound is amplified by `_build_provenance_quote` (`live_retriever.py:3356-3359`): the
  quote starts with the HEAD of the body — exactly where page nav sits in full-page markdown —
  so the ACCEPTED span is chrome-dominated even when real prose exists further down (ev_878
  openai nav, ev_1044 deloitte skip-nav, ev_954 ACM Cookiebot strip).

---

## 2. The fix

### OSS decision (operator directive: research 2026 SOTA, grab the best)

Candidates reviewed: trafilatura, resiliparse, jusText, readability-lxml, goose3, newspaper4k,
dragnet, boilerpy3. ALL of them are **HTML-DOM extractors** — they key on tag structure
(`<nav>`, `<header>`, class names, DOM depth). Our leak surface is **markdown** (Jina/crawl4ai
output); a markdown→HTML round-trip flattens everything to `<p>/<ul>/<li>` and destroys the DOM
signals those tools need, so none of them can run where the leak is. Verdict:

1. **KEEP trafilatura (already a dep, still the published F1 leader on HTML extraction
   benchmarks) for the raw-HTML paths** — correctly wired already, no change.
2. **For the markdown paths, implement the jusText/boilerpipe CORE HEURISTIC (link-density +
   prose-density block classification) natively on markdown lines** — ~100 LOC, pure,
   deterministic, zero new dependencies. This is not "own-code instead of the best tool"; it IS
   the best tool's algorithm, ported to the data shape the tools cannot ingest. The replay
   scanner already field-proved the measurement: line link-density ≥0.5 with ≥2 links found
   every one of the 64 nav leaks. Production adds the precision guards the scanner lacks.
3. **Defense at source (one line):** Jina Reader supports the `X-Remove-Selector` request
   header — send `nav,header,footer,aside` so most chrome never enters the pipe at all.

### Fix A — unify the whole-page shell vocabulary at the seam (leak class 1)

**A1. `src/polaris_graph/retrieval/shell_detector.py`** — add the missing error-page vocab
(single source of truth, LAW V):
- `CHALLENGE_PAGE_COOCCURRENCE` += `("something went wrong", "wait a moment and try again")`
  (the exact replay error_page text; ALL-of, never real prose).
- `SHORT_BODY_SHELL_MARKERS` += `"something went wrong. wait a moment"`.

**A2. `src/polaris_graph/retrieval/live_retriever.py` — refetch seam** (~3329, right after the
existing `_cf.shell_reason` branch): add, behind default-ON env `PG_FETCH_SHELL_VOCAB_GATE`
(OFF ⇒ byte-identical):

```python
if _fetch_shell_vocab_gate_enabled() and shell_detector.is_cited_span_shell(content):
    logger.info("[refetch_for_extraction] shell-vocab rejected url=%s len=%d", ...)
    diagnostics["failure_mode"] = "fetch_shell"
    return "", diagnostics
```

`shell_detector` is already module-imported here (see `live_retriever.py:4505-4507`).
`is_cited_span_shell` is the right entry: any-length unambiguous bot-wall/crawler-error
signatures + short-body-gated strong markers + corroboration-gated ambiguous phrases — the
false-drop analysis was already done under Codex review (#1276 iter-2).

**A3. `src/polaris_graph/retrieval/live_retriever.py` — `_fetch_content` winner check**
(~4199, right after `result = result_holder["value"]`, BEFORE the `if not result.success`
branch): probe the winner and, on a shell verdict, REROUTE into the EXISTING miss branch so the
OA resolver gets its recovery shot (recover-before-refuse), else the caller sees a MISS:

```python
_shell_reroute = ""
if result.success and result.content and _fetch_shell_vocab_gate_enabled():
    _probe_cf = clean_fetch_body(_strip_html(result.content))
    if _probe_cf.shell_reason:
        _shell_reroute = _probe_cf.shell_reason
    elif shell_detector.is_cited_span_shell(_probe_cf.cleaned_text):
        _shell_reroute = "bot_wall_shell_vocab"
if not result.success or not result.content or _shell_reroute:
    # existing miss branch (4202-4255): telemetry, OA resolver, honest stub return
```
- Log LOUD (`FETCH_SHELL_REFUSED url method reason`) + record telemetry reason so every
  refusal is disclosed (§-1.3.1a: a bot wall is a failed fetch, not a source).
- Cache `_probe_cf` and reuse it at 4276-4280 so `clean_fetch_body` doesn't run twice.
- This also FIXES the shell_reason-discard bug at 4279 (the discard site becomes the reuse
  site).

**A4. `src/polaris_graph/retrieval/frame_fetcher.py` — `_is_fetch_shell`** (~1165, before the
link-density check): add the same any-length check (same package, direct import):

```python
if shell_detector.is_cited_span_shell(stripped):
    return True, "bot_wall_shell_vocab"
```

### Fix B — markdown nav/boilerplate line filter (leak class 2)

**B1. `src/tools/access_bypass.py`** — new pure function `strip_markdown_nav_chrome(text) -> str`,
wired into `clean_fetch_body` after `strip_web_boilerplate` + the inline-token subs
(i.e. after line 2726), behind default-ON env `PG_FETCH_MD_NAV_STRIP` (OFF ⇒ byte-identical).

Algorithm (per line; the scanner-proven measurement + precision guards):

1. Track heading context while iterating: a heading matching
   `^#{1,6}\s*(references|bibliography|works cited|notes|endnotes|sources|citations|further reading)\b`
   (case-insensitive) opens REFERENCE MODE until the next same-or-higher-level heading.
2. Compute markdown-link density: chars inside `\[[^\]]*\]\([^)]*\)` spans / line length, and
   the link count.
3. **DROP the line iff** density ≥ 0.5 AND link_count ≥ 2 AND NOT reference-like AND NOT
   prose-like.
4. **reference-like (KEEP — the ev_037 bipartisanpolicy guard case):** in REFERENCE MODE, OR
   the line carries ≥1 citation signal: DOI `10\.\d{4,9}/`, `\bet al\b`, year `\b(19|20)\d{2}\b`,
   `\bpp?\.\s*\d`, vol/issue `\d+\s*\(\d+\)`, `arxiv|pmid|isbn`, `retrieved from|accessed`.
   A nav menu carries none of these; a citation line with URLs carries at least one.
5. **prose-like (KEEP):** ≥60% of the line's characters sit OUTSIDE link markup AND the line
   ends with sentence punctuation — a real sentence with incidental inline links survives.
6. Additionally drop STRUCTURE-ANCHORED standalone chrome lines the density test cannot see
   (single-link / no-link chrome), added to the same function (or the
   `_WEB_BOILERPLATE_LINE_RE` table at 2306-2662):
   - gov banner: `An official website of the United States government`,
     `Here's how you know`, `Official websites use .gov`, `Secure .gov websites use HTTPS`
     (whole-line);
   - skip-nav: `\[Skip to (?:main )?content\]\([^)]*\)`, whole-line `Skip to main content`,
     `#main-?content` anchor tokens (extends the existing MIT pattern at 2646);
   - reading-time: whole-line `^\d+\s*(?:Minute Read Time|min(?:ute)? read)$`;
   - Cookiebot consent-link run: `\[\]\(https?://www\.cookiebot\.com[^)]*\)` plus the
     adjacent `[Consent](…) [Details](…) [About](…)` link run (the ev_954 ACM strip);
   - Scopus citation chrome: `\[\d+ Link opens in a new tab\]\(https?://www\.scopus\.com[^)]*\)`
     `(?:\s*Scopus citations)?` (the ev_1048 wustl case) — structure-anchored, token-only
     removal, surrounding prose preserved.
7. Collapse the blank-line runs left behind (same as `strip_web_boilerplate:2460`).

Effect on the quote: nav sits at the head of full-page markdown; after B1 the head IS article
prose, so `_build_provenance_quote`'s head window stops being chrome-dominated with no change
to the quote builder itself. Bonus: a page that is ONLY nav becomes empty after B1 →
`empty_after_clean` shell → refused at the existing seam.

**B2. `src/tools/access_bypass.py` `_try_jina_reader`** (~5368-5372): add header
`"X-Remove-Selector": os.getenv("PG_JINA_REMOVE_SELECTOR", "nav,header,footer,aside")`
(empty value ⇒ header not sent ⇒ byte-identical). Source-level defense in depth; B1 remains
the guarantee (covers crawl4ai raw-markdown fallback, Zyte, naive-httpx paths too).

### Binding constraints (all fixes)

- Faithfulness engine (strict_verify / NLI / D8 / span-grounding) UNTOUCHED — everything here
  is input hygiene or refusal of a FAILED fetch.
- No credible on-topic source is deleted: a refused bot wall / error page is a chrome
  non-source (§-1.3.1a); nav-line removal keeps the source and its prose. Reference lists are
  byte-preserved via guards 1/4/5.
- Every flag defaults ON with a byte-identical OFF path; every refusal is logged + telemetry-
  recorded (fail loud, disclosed).

---

## 3. Exact files Opus edits

1. `src/polaris_graph/retrieval/shell_detector.py` — A1 vocab additions (2 tuples).
2. `src/polaris_graph/retrieval/live_retriever.py` — A2 seam branch (~3329); A3 winner
   probe/reroute in `_fetch_content` (~4199) + reuse of the probe at 4276-4280 (fixes the
   shell_reason discard); tiny `_fetch_shell_vocab_gate_enabled()` env helper.
3. `src/polaris_graph/retrieval/frame_fetcher.py` — A4 one branch in `_is_fetch_shell` (~1165).
4. `src/tools/access_bypass.py` — B1 `strip_markdown_nav_chrome` + wiring in
   `clean_fetch_body` (~2726) + the standalone chrome patterns; B2 Jina header.
5. `tests/polaris_graph/test_fetch_junk_gate.py` (new) + `tests/fixtures/fetch_junk_leaks/`
   — REAL leak spans from the replay report as fixtures: ev_932 SSRN wall → `fetch_shell`;
   ev_954 Cookiebot strip + ev_878 openai nav + ev_1044/902/880 skip-nav → stripped, prose
   kept; ev_037 bipartisanpolicy references → KEPT byte-identical (the guard case); a
   prose-with-inline-links paragraph → kept; both flags OFF → byte-identical output.

Estimated diff: ~160 LOC production + tests.

## 4. Fast retest (leaking subset first, then full)

1. Offline: `python -m pytest tests/polaris_graph/test_fetch_junk_gate.py -x -q` (the real
   leak spans must flip; the guard cases must not).
2. VM box2 (ssh6.vast.ai:38794): build `leak_urls.txt` = the ~90 leak rows' URLs from
   `outputs/fetch_corpus_replay_*/report.md`, then subset replay (scanner already supports it):
   ```
   PYTHONPATH=/workspace/POLARIS python3 scripts/fetch_corpus_replay.py \
     --snapshot outputs/paid_drb72_deep/workforce/drb_72_ai_labor/corpus_snapshot.json \
     --urls-file leak_urls.txt --out outputs/fetch_corpus_replay_fixcheck
   ```
   PASS = bot_wall / error_page / cookie / gov_banner / skip_nav / reading_time all ZERO
   inside accepted spans; every remaining `nav_link_density` hit is READ and is a genuine
   reference/citation line (quoted, §-1.1); ev_037 still ACCEPTED with its reference section
   intact.
3. Full 921-URL replay for regression: accepted (eligible) count must not drop materially vs
   the baseline run — refusals must be junk-only (read every new non-empty failure_mode row).
