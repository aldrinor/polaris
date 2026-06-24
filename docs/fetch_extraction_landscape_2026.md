# Fetch & Content-Extraction Landscape 2025/2026 — Best Practice + Open-Source Solutions (I-fetch-007)

**Status:** research deliverable, operator-requested 2026-06-23. Section "FETCH & CONTENT EXTRACTION"
of the standard pipeline-section review (`docs/standard_process_pipeline_section_review.md`).
**Method:** deep research — frontier-only (2025/2026), every candidate primary-source-verified for
year + URL + license, then grounded against the actual POLARIS fetch/extraction modules in this repo.
**Scope guard (read first):** this doc is the **URL → clean text subsystem ONLY** — the scrape backend
(how a URL becomes a clean string) plus main-content / boilerplate / paywall / PDF-table handling. The
isolation axis is **extraction QUALITY on a fixed URL set** (main-content recall, boilerplate
precision, paywall-bypass success, table fidelity) — NOT end-to-end. Rerankers, credibility/quality
weights, embedders, late-interaction retrieval, and claim-level dedup are the RETRIEVAL and
CONSOLIDATION sections — `docs/retrieval_landscape_2026.md` + `docs/consolidation_landscape_2026.md`
own those. This doc cross-references them; it does not re-litigate them.
**Operator's pain that drove this:** "we have a bunch of methods plus Zyte, but we are also fetching a
lot of junk into the content." Junk enters at exactly two layers this section owns: the **scrape
backend** (a bad fetch returns a challenge-page / paywall shell, not content) and the **extractor**
(boilerplate/chrome/nav mixed into the body). This doc bakes both off.

---

## 0. The one-paragraph answer

The fetch path is sound and the extractor of record is the right one. Junk that this section can fix
has two shapes. The first is a **bad fetch** — a Cloudflare/DataDome challenge page, a paywall shell, a
404 stub — where the URL never became real content; POLARIS already screens these (`shell_detector`,
`is_content_starved`, the `PAYWALL_STUB` fail-loud) and the genuine 2025/2026 lever is a stronger
anti-bot fetch (Camoufox MPL-2.0) behind the Zyte commercial yardstick that has no OSS equal. The
second is **boilerplate inside an otherwise-good body** — nav, cookie banners, social chrome, mastheads
— killed only by the extractor and a line-level strip, both of which POLARIS has (Trafilatura of
record + `clean_fetch_body`). The single highest-value 2025/2026 finding for THIS section is that **one
HTML extractor never suffices**: the WCXB benchmark (arXiv 2605.21097, May 2026) shows top systems
converge on articles (F1 ~0.93) but diverge hard on structured pages (0.41–0.84), so the frontier
recipe is a **union of extractors** (Trafilatura 2.x floor + Resiliparse, with rs-trafilatura and
MinerU-HTML as candidates to beat behaviorally). The clinical-PDF case is a separate, load-bearing
lane: POLARIS already runs Docling-first → PyMuPDF-fallback, and the 2026 frontier there is **MinerU2.5
/ MinerU2.5-Pro** (OmniDocBench-v1.6 SOTA 95.69, April 2026), license-gated and sovereign-OK. The hard
constraint that separates an OSS-deployable pick from a yardstick here is **deterministic vs
generative**: POLARIS is provenance-gated (strict_verify checks verbatim spans), so generative HTML→MD
converters (ReaderLM-v2, Firecrawl `/parse`, ScrapeGraphAI) are a faithfulness hazard and can only be
yardstick/inspiration, never the content-of-record.

---

## 1. What POLARIS has today (verified in the repo, not assumed)

| Layer | Current POLARIS implementation | Verified location |
|---|---|---|
| Fetch / render | crawl4ai (Playwright/Chromium render) — Apache-2.0 sovereign fetch engine, per-loop concurrency-gated | `access_bypass.py` `_try_crawl4ai`, `_get_crawl4ai_semaphore:718` |
| Fetch / unblock (paywall, anti-bot) | **Zyte API** paid fallback (browserHtml), circuit-breaker + telemetry; **silent no-op without `ZYTE_API_KEY`** (fails loud as `PAYWALL_STUB_NO_ZYTE`) | `access_bypass.py:96` (`_ZYTE_API_ENDPOINT`), `:72-101`; `live_retriever.py:2900` |
| HTML extraction (content of record) | **Trafilatura is the extractor of record** via the ONE guarded entrypoint `safe_trafilatura_extract`; readability-lxml then regex as fallback | `access_bypass.py:943`; `frame_fetcher.py` |
| SIGSEGV containment for extraction | `safe_trafilatura_extract` size-gates libxml2; `PG_TRAFILATURA_SUBPROCESS=1` for true hard-kill containment | `access_bypass.py:943-971`, `_trafilatura_extract_subprocess:897` |
| Line-level junk strip (the correct-altitude chrome fix) | `clean_fetch_body` → `strip_web_boilerplate` + `_WEB_BOILERPLATE_LINE_RE` + `_INLINE_SOCIAL_CHROME_RE`, **wired on the live path** | `access_bypass.py` `clean_fetch_body:1661`, `strip_web_boilerplate:1412`, `_WEB_BOILERPLATE_LINE_RE:1320`, `_INLINE_SOCIAL_CHROME_RE:1565` |
| Non-assertional / stub screen | `is_boilerplate_or_nonassertional` (crawl marker / bare DOI / table-number row / 404 stub) | `access_bypass.py:1437` |
| Bad-fetch screen | `shell_detector` (access-denial markers + Cloudflare co-occurrence), `is_content_starved`, `_is_access_denial_stub` | `live_retriever.py:2974`, `:2988`; `shell_detector` module |
| **Clinical-PDF extraction** | **Docling-first → PyMuPDF (fitz) fallback**; page-count pre-check skips Docling on oversize (OOM guard); Sci-Hub OA-PDF last-resort path | `live_retriever.py` `_extract_pdf_text:2900`, `_docling_extract:3977`, `:2220` (PDF route), `:4090` (Sci-Hub) |
| Document-level quality gate | `content_quality_gate.score_content_quality` — DEFAULT-OFF (`PG_V3_CONTENT_QUALITY_GATE=0`); **wrong altitude for chrome-in-good-doc** (see §5) | `content_quality_gate.py:43` |

**Three corrections to carry forward, grounded in the repo:**

1. **Trafilatura is already the extractor of record, not a fallback.** The extractor choice is not the
   gap — the gap is that POLARIS runs ONE extractor where the 2026 frontier runs a union (§3).
2. **POLARIS already has a clinical-PDF lane, and it is Docling-first.** The retrieval-section doc
   listed "add MinerU-HTML" as if there were no PDF lane; in fact `_extract_pdf_text` runs Docling
   then PyMuPDF today. The frontier question is therefore *Docling vs MinerU2.5*, not *add a lane*.
3. **The correct chrome fix exists and is wired** (`clean_fetch_body` at the live path). The
   document-level gate is the wrong altitude (it min-vetoes whole short docs; chrome inside long good
   docs passes) — do NOT flip `PG_V3_CONTENT_QUALITY_GATE` as the junk fix. This was already proven in
   this repo's own forensic; §5 carries the receipt.

---

## 2. Why junk gets in: the two layers THIS section owns

Junk that the fetch/extraction subsystem can fix has two shapes, and each dies at a different place.

- **Bad fetch (the URL never became content).** A Cloudflare/DataDome challenge page, a login wall, a
  paywall shell, a 404 stub. The body is junk because the *fetch* failed, not because extraction failed.
  This dies at the **scrape backend** (better render / anti-bot / paid unblock) and the **bad-fetch
  screen** (`shell_detector`, `is_content_starved`). POLARIS handles this and fails loud; the 2026
  lever is a stronger anti-bot browser (Camoufox) behind Zyte.
- **Boilerplate inside a good body.** Nav, ads, cookie banners, social chrome, journal mastheads,
  "subscribe" rows — *about the right page* but not content. This dies at the **extractor**
  (main-content isolation) and the **line-level strip** (`clean_fetch_body`). A better search API or a
  reranker does nothing for it.

Note the boundary with the retrieval section: **on-topic SEO spam** (a shallow, keyword-stuffed page
that IS real content about the right subject) is NOT a fetch/extraction defect — extraction did its job
and returned the page's real body. That is a *credibility/quality-weight* problem and belongs to
`docs/retrieval_landscape_2026.md` §5 (the quality-weight ADD). This section does not try to fix it;
trying to would mean a hard-drop quality classifier, which violates weight-not-filter (CLAUDE.md §-1.3).

---

## 3. The 2025/2026 best-practice fetch→clean pipeline (ordered)

The convergent recipe across the WCXB benchmark, the OmniDocBench/table-extraction literature, and the
2026 anti-bot guides. Apply in this order:

1. **Fetch / render / unblock** — Playwright/Chromium (crawl4ai) for JS pages; an anti-bot stealth
   browser (Camoufox) when the default render is challenged; the paid commercial unblock (Zyte) for
   hard paywalls/anti-bot. Does NO cleaning. Faithfulness-neutral.
2. **Bad-fetch screen** — reject challenge pages / paywall shells / 404 stubs BEFORE extraction so a
   shell never reaches the body. POLARIS does this (`shell_detector`, `is_content_starved`). Fail loud,
   never silently substitute.
3. **HTML main-content extraction — a UNION, not one extractor (the #1 2026 finding).** Per WCXB
   (arXiv 2605.21097), no single deterministic extractor wins across page types: top systems converge
   on articles (F1 ~0.93) but diverge on structured pages (0.41–0.84). **Independently corroborated** by
   "Beyond a Single Extractor" (arXiv 2602.19548, Feb 2026), which shows combining extractors via a
   union lifts DCLM-Baseline token yield by up to **71%** while holding quality, and that extractor
   choice on structured content (tables/code) swings downstream tasks by up to 10 pts (WikiTQ) / 3 pts
   (HumanEval) — a second, non-WCXB source for the union thesis (dissolves the §8 COI-alone concern).
   The frontier recipe runs Trafilatura **and** Resiliparse (and optionally rs-trafilatura / MinerU-HTML)
   and unions/votes their output to lift recall on non-article pages. **Faithfulness rule: deterministic
   extractors only — they keep verbatim spans; never let an LLM rewrite a span the verifier later checks.**
4. **Line-level boilerplate strip** — remove boilerplate *lines inside* an otherwise-good page (nav,
   cookie banners, social chrome, mastheads). The only technique that fixes chrome-mixed-into-content
   without dropping the page. **POLARIS already does this** (`clean_fetch_body`). Allowlist-only,
   whole-line/multi-token-anchored, byte-safe — raises faithfulness by denying the gate its own chrome
   to self-entail.
5. **Clinical-PDF / structured lane** — for journal PDFs and trial/dose tables, a layout-aware parser
   (Docling today; MinerU2.5 the 2026 frontier) that preserves table structure. Trafilatura/HTML
   extractors mangle tables; this is a separate lane with a PyMuPDF text-only fallback.
6. **Obvious-junk structural floor (the only allowed drop)** — Gopher-class checks (symbol/repetition
   ratios, mojibake, min-length) for bodies that are structurally not prose. POLARIS's
   `content_quality_gate.py` + `junk_detection.py`. Keep as the structural floor; do NOT promote the
   document gate to the live chrome fix (§5).

Everything past step 6 (relevance rerank, quality weight, consolidation) is the retrieval/consolidation
sections, not this one.

---

## 4. The fixed-URL-set bake-off — isolation axis + metrics (no e2e)

**Acceptance is behavioral and isolated, not a vendor leaderboard number.** Build a fixed URL set, run
each candidate URL→text in isolation, and score extraction quality directly. No candidate is crowned on
a self-reported or COI'd number.

**The fixed URL set (≥3 slices):**
- **General web** — sample from the live corpus across WCXB's 7 page types (articles, forums, products,
  collections, listings, documentation, service pages) so non-article divergence is measured, not hidden.
- **Paywalled / anti-bot** — a slice of publisher/journal URLs that 403 or challenge on the free path,
  to measure paywall-bypass success (the Zyte / Camoufox axis).
- **Clinical-PDF slice (load-bearing, per the task)** — journal PDFs with real dose/trial tables, plus
  a few scanned/OCR-needed pages, to measure table fidelity (this is where Docling vs MinerU2.5 is
  decided and where HTML extractors are irrelevant).

**Metrics (isolation axis):**
- **Main-content recall** + **boilerplate precision** → F1 against a hand-labeled body (the WCXB metric).
- **Per-page-type F1** (never a single aggregate — WCXB's whole point is that the aggregate hides the
  structured-page collapse).
- **Paywall/anti-bot bypass success rate** (fraction of challenged URLs that yield real body) +
  fetch latency/cost.
- **Table fidelity for the clinical slice** — TEDS/GriTS as the cheap automatic score, BUT note the
  2026 caveat below; an **LLM-as-judge semantic table score** is the higher-fidelity arbiter.
- **Faithfulness preservation** — verbatim spans survive (a real claim's exact text is byte-present in
  the extracted body so strict_verify can ground it). Any candidate that paraphrases is disqualified as
  content-of-record regardless of its F1.

**2026 scoring caveat (verified):** for the table slice, "Beyond String Matching" (arXiv 2603.18652,
March 2026) shows **TEDS correlates only r=0.68 with human judgment** vs **r=0.93 for an LLM-as-judge
semantic score** across 21 parsers. So use TEDS as the cheap pre-filter and an LLM-judge (on the
sovereign GLM slate, not GPT) as the deciding arbiter for the clinical-PDF lane.

**Second independent PDF yardstick (verified):** ParseBench (arXiv 2604.08538, April 2026, LlamaIndex)
scores ~2,000 human-verified enterprise pages across five capability axes — **tables, charts,
content-faithfulness, semantic-formatting, visual-grounding** (14 methods benched). Use it alongside
OmniDocBench-v1.6 + TEDS so the clinical-PDF lane is decided on at least two independent harnesses, not
one. Its content-faithfulness and per-axis framing aligns with this doc's own caveat that a single
aggregate (raw TEDS) hides per-capability collapse — but its top scorer (LlamaParse Agentic, 84.9%) is a
proprietary SaaS, so ParseBench is a **measurement reference, not a candidate source** for sovereign use.

---

## 5. The document-gate trap (do NOT flip `PG_V3_CONTENT_QUALITY_GATE`)

Same finding the retrieval-section doc carries, restated here because it sits in this section's code.
A naive reading says "turn on the content-quality gate to kill junk." **That is wrong, and this repo
already proved it wrong in writing.**

- Repo forensic, I-beatboth-010 finding idx 47 (P1): *"`content_quality_gate`
  (`PG_V3_CONTENT_QUALITY_GATE`) is DORMANT and wrong-altitude (scores the WHOLE document
  pre-extraction, not the cited span). Do NOT enable it as the fix … REJECT flipping
  `PG_V3_CONTENT_QUALITY_GATE` — wrong-altitude; the line-level strip is the correct mechanism."*
- Confirmed in code: `score_content_quality(text, url)` takes a whole-document string and check #1 is a
  ~500-char min-veto (paywall-shell heuristic). The operator's chrome is *inside* long good documents,
  which this gate passes. It is a structural floor for whole-junk bodies, not a chrome remover.

The correct altitude is the line-level strip, which exists and is wired (`clean_fetch_body`). Keep
extending its allowlist patterns as new chrome shapes appear (the I-beatboth-011 commits already added
Scribd/Facebook/YouTube/ResearchGate/MDPI/MIT/journal-masthead patterns) — inside the line-level
machinery, never by promoting the document gate. This entry is an application of the standing rule
(`feedback_avoidable_vs_structural_review_miss`): **a recommendation that describes flipping a
cap/floor on is auto-reject until line-by-line grounded.**

---

## 6. KEEP vs ADD vs FIX (against the current crawl4ai + Zyte + Trafilatura + Docling stack)

**The current stack is fundamentally sound. The gaps are concentrated, not architectural.**

### KEEP (verified present and correct)
- **crawl4ai** (Apache-2.0) — sovereign Playwright/Chromium fetch engine. Keep.
- **Zyte API** — best paywall/anti-bot paid unblock; operator-keyed. The **one** place no OSS equal
  exists (Camoufox raises the free-tier ceiling but does not replace Zyte for hard DataDome/Akamai).
  Keep — and verify `ZYTE_API_KEY` is deployed (the no-op-without-key gap is a known retrieval-blind
  failure, `fact_zyte_key_location_and_deploy_env`).
- **Trafilatura** (Apache-2.0) via `safe_trafilatura_extract` — the right deterministic extractor of
  record. Keep; the SIGSEGV size-gate + subprocess containment is correct and load-bearing.
- **`clean_fetch_body` line-level strip** — the correct-altitude chrome fix, already wired. Keep +
  extend patterns.
- **Docling** (MIT) as the PDF lane — keep as the floor; bake off vs MinerU2.5 (ADD-3).
- **`shell_detector` / `is_content_starved` / `is_boilerplate_or_nonassertional`** — keep as the
  bad-fetch + non-assertional screen.
- **`content_quality_gate.py` / `junk_detection.py`** — keep as the obvious-junk STRUCTURAL floor; do
  NOT promote the document gate to the live chrome fix (§5).

### ADD / FIX (priority order)
1. **Union-of-extractors for HTML (the biggest genuine extraction gap).** Run Trafilatura **and**
   Resiliparse (Apache-2.0) and union/vote, to recover the non-article recall WCXB shows a single
   extractor loses (F1 0.41–0.84 on structured pages). Deterministic only; verbatim-preserving.
   Flag-gated; bake off rs-trafilatura and MinerU-HTML-0.6B as candidates-to-beat, never default-on.
2. **Stronger anti-bot fetch tier — bake off Camoufox vs Nodriver/Patchright, do NOT crown Camoufox
   unbenchmarked.** Camoufox (MPL-2.0) is a Firefox-fork stealth browser that bypasses anti-bot systems
   Chromium trips, raising the *free-tier* fetch-success ceiling before the paid Zyte fallback fires
   (fewer `PAYWALL_STUB` shells, lower Zyte spend). MPL-2.0 is file-level copyleft — usable as a separate
   fetch backend (not statically linked into a proprietary binary). **But this doc's own rule is "bake
   off, don't crown on one number" (§1, §4), so Camoufox is a CANDIDATE, not a foregone pick:** the 2026
   head-to-head benchmark (Ian L. Paterson, May 2026, 7 stealth tools × 31 Cloudflare/anti-bot targets,
   651 verdicts) ranks **Nodriver 28 OK > Camoufox = Patchright 25 OK** — i.e. Nodriver (Chromium-CDP
   stealth) actually leads Camoufox on that slice, and the real differentiator is *automation-protocol
   fingerprinting*, not the browser engine. So reframe ADD-2 to **bake Camoufox vs Nodriver/Patchright on
   POLARIS's own anti-bot URL slice** (the head-to-head as reference, not as the decider), behavioral
   accept on bypass-success-rate. Camoufox keeps one unique edge worth the union: it passed google-search
   where Chromium-based tools failed.
3. **Clinical-PDF lane: bake off MinerU2.5 vs the incumbent Docling.** MinerU2.5 / MinerU2.5-Pro is the
   2026 PDF-parsing frontier (OmniDocBench-v1.6 SOTA 95.69, beating Gemini 3 Pro / Qwen3-VL-235B) at
   1.2B params, vLLM-served. License is custom-Apache (commercial-OK well under the 100M-MAU / $20M-mo
   thresholds; attribution required) — sovereign-deployable for POLARIS. Decide on the clinical table
   slice with the LLM-judge arbiter (§4), not raw TEDS. **Lower-resource third candidate:** LiteParse
   (Apache-2.0, LlamaIndex, v2.1.2 June 2026) is a deterministic, local-first PDF parser (PDFium text +
   Tesseract OCR + spatial grid-projection to preserve column/indentation layout) — CPU-cheap, no GPU,
   and deterministic (unlike the generative VLMs), so it is a faithfulness-safe bake-off entry where a
   1.2B VLM's GPU cost is not justified. Bake it in the same clinical-PDF slice; it is lighter than
   Docling/MinerU but targets the same faithful-layout problem.
4. **Confirm the bad-fetch screen fires at every fetch seam.** `shell_detector` + `is_content_starved`
   exist; behaviorally verify they screen crawl4ai, Zyte, AND the PDF/Sci-Hub paths (not just one),
   so a challenge-page/paywall-shell never reaches extraction on any backend. Behavioral, not "confirm
   it runs."

### DO NOT add
- **Generative HTML→MD/JSON converters as the content-of-record** — ReaderLM-v2 (Jina, CC-BY-NC + a
  1.5B generative model), Firecrawl `/parse`, ScrapeGraphAI. They rewrite the body; for a
  provenance-gated pipeline (strict_verify on verbatim spans) that is a fabrication/omission hazard.
  Yardstick/inspiration only. (Independent confirmation they are not even fast/accurate enough to
  tempt: ReaderLM-v2 scores WCXB F1 0.741 at 10,410 ms/page vs rs-trafilatura 0.859 at 44 ms/page.)
- **Marker** (GPL + Open-RAIL-M paid commercial weights) — license-blocked for sovereign commercial
  deploy. Yardstick-only.
- Any **hard-drop quality classifier** at this layer — violates weight-not-filter; on-topic SEO spam is
  the retrieval section's quality-weight job, not a fetch-layer drop.

---

## 7. The bake-off candidate list (the next step)

Open-source-first (sovereignty). Every license below is verified against the primary source in §9.

**HTML main-content extraction (deterministic, content-of-record):**
- **Trafilatura 2.x** (Apache-2.0) — incumbent / safe floor. WCXB F1 0.791 @ 97 ms.
- **Resiliparse** (Apache-2.0) — recall-biased union partner; fastest (WCXB F1 0.797 @ 28 ms). Lead ADD.
- **rs-trafilatura** (license UNVERIFIED — single-author, pre-1.0) — WCXB F1 0.859 @ 44 ms (the number
  to beat behaviorally). **COI flag: the WCXB benchmark author (Murrough Foley) and rs-trafilatura
  appear to be the same author** — treat the leaderboard rank as a candidate-to-bench, not a crown.
- **MinerU-HTML (0.6B)** (introduced in AICC, arXiv 2511.16397, Nov 2025; paper CC-BY-4.0 — the HTML
  artifact's weight license still maps to MinerU custom-Apache, honor attribution) — a model-based HTML
  extractor that reformulates content extraction as **sequence labeling** (extractive/deterministic, not
  free-form generative — load-bearing for the §3/§6 faithfulness rule). AICC reports **81.8% ROUGE-N F1
  vs Trafilatura's 63.6%**; WCXB independently scores it F1 0.827 @ 1,570 ms (slow). Bake-off candidate
  for hard structured pages only.
- **jusText** (BSD) — classic 3rd union member (WCXB F1 0.707). Cheap diversity.

**Clinical-PDF / structured lane (layout-aware, table-preserving):**
- **Docling** (MIT) — incumbent floor; clean license, fast, TableFormer >91% TEDS on FinTabNet.
- **MinerU2.5 / MinerU2.5-Pro** (custom-Apache) — 2026 OmniDocBench-v1.6 SOTA (95.69), 1.2B, vLLM. Lead
  PDF ADD. License sovereign-OK under thresholds. **§8.4 cost axis:** it is a 1.2B VLM that needs
  GPU/vLLM per PDF — the bake-off must weigh GPU/latency cost against accuracy, not crown on accuracy
  alone; Docling's layout models are far lighter, so MinerU2.5 must EARN the GPU cost on the clinical
  slice.
- **LiteParse** (Apache-2.0, LlamaIndex / run-llama, v2.1.2 June 2026) — deterministic, local-first PDF
  parser (PDFium text + Tesseract OCR + spatial grid-projection for column/indentation faithfulness).
  CPU-only, no GPU, deterministic → faithfulness-safe lower-resource bake-off candidate where MinerU2.5's
  GPU cost is not justified. Lighter than Docling/MinerU; same faithful-layout target.
- **PyMuPDF (fitz)** (AGPL-3.0 / commercial) — incumbent text-only fallback. **AGPL flag (LIVE
  exposure, not hypothetical):** this is in the CURRENT floor (`_extract_pdf_text` fallback), so the
  AGPL obligation already applies to the deployed pipeline — verify it against the hosted-service model;
  pdfplumber/pypdf is the permissive alternative if AGPL is a blocker.
- *(pdfmux — 0.911 TEDS, May 2026, beats Docling 0.887 — EXCLUDED: commercial SaaS, not OSS/sovereign.
  GLM-OCR (arXiv 2603.10910) — EXCLUDED: dominated by MinerU2.5-Pro per opendatalab's own
  OmniDocBench-v1.6 comparison. Both are yardstick-only.)*

**Fetch / render / anti-bot:**
- **crawl4ai** (Apache-2.0) — incumbent render engine. Keep.
- **Camoufox** (MPL-2.0) — anti-bot stealth Firefox fork; lead fetch ADD for the free-tier ceiling.
- **Zyte API** (commercial) — the paid-unblock yardstick that STAYS (no OSS equal for hard anti-bot).
- *(Firecrawl v2 / Jina Reader / Stagehand / Browser Use — proprietary SaaS or generative; yardstick
  / inspiration only, not sovereign content-of-record.)*

**Extraction scoring harness:**
- **WCXB** (CC-BY-4.0) — the independent main-content F1 yardstick (2,008 pages, 7 page types).
- **OmniDocBench v1.6** (CVPR-2025 lineage) — the independent PDF-parsing yardstick.
- **ParseBench** (CC-BY-4.0, arXiv 2604.08538, LlamaIndex, April 2026) — second independent PDF yardstick
  (~2,000 human-verified pages; 5 axes: tables/charts/content-faithfulness/semantic-formatting/visual-
  grounding; 14 methods). Measurement reference alongside OmniDocBench-v1.6 — its top scorer is a SaaS,
  so it is a yardstick, not a sovereign source.
- **LLM-as-judge semantic table score** (per arXiv 2603.18652) on the sovereign GLM slate — the
  deciding table-fidelity arbiter (TEDS r=0.68 vs LLM-judge r=0.93 vs humans).

**Cross-ref (NOT baked off here — other sections own them):** near-dup dedup on extracted bodies
(`ContentDeduplicator`, retrieval §5), credibility/quality WEIGHT for on-topic spam (retrieval §6),
reranker (retrieval), embedder Qwen3-Embedding-8B (I-arch-009), claim-level dedup (consolidation).

---

## 8. Honest uncertainty

- **WCXB is author-aligned / COI-flagged.** Its top system (rs-trafilatura, F1 0.859) shares an author
  with the benchmark. The per-type *divergence* finding (the union-of-extractors rationale) is robust
  and independently reproducible; the exact rank of rs-trafilatura is not adoption-grade. Hence the
  behavioral bake-off on POLARIS's own fixed URL set.
- **rs-trafilatura license is unverified** (single-author, pre-1.0 repo). Do not adopt as default until
  the repo license is confirmed; Resiliparse (Apache-2.0) is the safe union partner regardless.
- **MinerU is custom-Apache, not vanilla Apache-2.0.** Verified: commercial OK below 100M MAU / $20M
  monthly revenue + mandatory attribution; auto-terminates above. POLARIS is well under the thresholds,
  so it is sovereign-deployable — but the attribution obligation must be honored in any hosted service.
- **PyMuPDF is AGPL-3.0** — fine internally, but verify against the hosted-service deployment model
  before relying on it as a shipped fallback; pdfplumber is the permissive alternative.
- **Vendor benchmark numbers are not cross-comparable** (WCXB F1 vs OmniDocBench score vs FinTabNet
  TEDS measure different things on different data). None is a head-to-head — hence the isolation bake-off.
- **Camoufox is NOT an unbenchmarked crown — it may lose the anti-bot slice to Nodriver.** The one 2026
  head-to-head we have (Ian L. Paterson, May 2026, 7 tools × 31 targets, 651 verdicts) ranks Nodriver 28
  OK > Camoufox = Patchright 25 OK, and finds the real differentiator is automation-protocol
  fingerprinting, not browser engine. That benchmark is a single secondary source (one author's slice of
  Cloudflare targets), so it is a *reason to bake off*, not a verdict — POLARIS must run Camoufox vs
  Nodriver/Patchright on its own anti-bot URL slice. (Note: the gap-finder's claimed "Camoufox
  maintenance-gap / performance-regression" flag could NOT be confirmed at the cited benchmark URL, so it
  is not asserted here.)
- **The exact per-source contribution of each junk shape needs a behavioral replay (§-1.4)** on a banked
  `corpus_snapshot.json` before the bake-off invests in new tooling. Highest-confidence claims: (a) the
  line-level strip is the correct chrome mechanism and is already wired; (b) the highest-value
  extraction ADD is union-of-extractors (WCXB-grounded); (c) the clinical-PDF frontier is MinerU2.5 vs
  Docling, decided on an LLM-judge table score.

---

## 9. Primary sources (2025/2026) — year + URL + license

- **WCXB: A Multi-Type Web Content Extraction Benchmark** — arXiv 2605.21097, submitted 2026-05-20,
  CC-BY-4.0 (Murrough Foley). 2,008 pages / 7 page types / 1,613 domains. Leaderboard:
  https://webcontentextraction.org/ ; repo https://github.com/Murrough-Foley/web-content-extraction-benchmark
- **Beyond a Single Extractor: Re-thinking HTML-to-Text Extraction for LLM Pretraining** — arXiv
  2602.19548, submitted 2026-02-23, arXiv license (paper; methods use Trafilatura/Resiliparse, Apache-2.0).
  Second, non-WCXB source for the union thesis: union of extractors lifts DCLM-Baseline token yield by up
  to 71%; extractor choice on tables/code swings downstream tasks (WikiTQ +10 pts, HumanEval +3 pts).
- **AICC: Parse HTML Finer, Make Models Better — A 7.3T AI-Ready Corpus Built by a Model-Based HTML
  Parser** — arXiv 2511.16397, submitted 2025-11-20, CC-BY-4.0. The primary source for **MinerU-HTML**: a
  0.6B sequence-labeling (extractive, not generative) HTML extractor; 81.8% ROUGE-N F1 vs Trafilatura
  63.6%; introduces the AICC 7.3T-token corpus.
- **ParseBench: A Document Parsing Benchmark for AI Agents** — arXiv 2604.08538, submitted 2026-04-09,
  CC-BY-4.0 (LlamaIndex). ~2,000 human-verified pages; 14 methods × 5 axes (tables/charts/content-
  faithfulness/semantic-formatting/visual-grounding); top scorer LlamaParse Agentic 84.9% (SaaS,
  yardstick-only). Second independent PDF yardstick alongside OmniDocBench-v1.6.
- **LiteParse** — Apache-2.0, https://github.com/run-llama/liteparse (LlamaIndex; v2.1.2 released
  2026-06-19). Deterministic, local-first PDF parser (PDFium text + Tesseract OCR + spatial grid-
  projection). CPU-only, faithfulness-safe lower-resource clinical-PDF candidate.
- **Anti-detect browser benchmark (head-to-head)** — Ian L. Paterson, published 2026-05-13 (updated
  2026-06-07), secondary source (no license; references OSS tools Nodriver / Patchright / curl-cffi /
  Camoufox). 7 stealth tools × 31 Cloudflare/anti-bot targets, 651 verdicts: Nodriver 28 OK > Camoufox =
  Patchright 25 OK. https://ianlpaterson.com/blog/anti-detect-browser-benchmark-patchright-nodriver-curl-cffi/
- **Beyond String Matching: Semantic Evaluation of PDF Table Extraction** — arXiv 2603.18652,
  March 2026 (Horn & Keuper, IMLA Offenburg / Mannheim). TEDS r=0.68 vs LLM-judge r=0.93; 21 parsers.
- **MinerU2.5: A Decoupled Vision-Language Model for Efficient High-Resolution Document Parsing** —
  arXiv 2509.22186 (Sept 2025); weights `opendatalab/MinerU2.5-2509-1.2B` (HF).
- **MinerU2.5-Pro: Pushing the Limits of Data-Centric Document Parsing at Scale** — arXiv 2604.04771
  (April 2026); OmniDocBench-v1.6 score 95.69 (absolute SOTA). Custom-Apache license:
  https://github.com/opendatalab/MinerU/blob/master/LICENSE.md
- **OmniDocBench: Benchmarking Diverse PDF Document Parsing** — CVPR 2025 (arXiv 2412.07626); 1,651
  pages / 10 doc types. The independent PDF-parsing yardstick.
- **Resiliparse** — Apache-2.0, https://github.com/chatnoir-eu/chatnoir-resiliparse (WCXB F1 0.797 @ 28 ms).
- **Trafilatura** — Apache-2.0, the deterministic extractor of record (WCXB F1 0.791 @ 97 ms).
- **Camoufox** — MPL-2.0 anti-detect Firefox fork, https://github.com/daijro/camoufox (2026 anti-bot frontier).
- **crawl4ai** — Apache-2.0, https://github.com/unclecode/crawl4ai (incumbent render engine).
- **Docling** — MIT (incumbent PDF lane; TableFormer >91% TEDS on FinTabNet).
- **Marker** — GPL + Open-RAIL-M paid commercial weights — yardstick-only, NOT sovereign-deployable.
- **ReaderLM-v2** (Jina) — CC-BY-NC, 1.5B generative HTML→MD (WCXB F1 0.741 @ 10,410 ms) — generative
  faithfulness hazard; yardstick/inspiration only.
- **Firecrawl v2 / `/parse` / Jina Reader** — proprietary SaaS, generative — yardstick only.

---

## 10. Relevant files (for the bake-off brief)

- `src/tools/access_bypass.py` — `safe_trafilatura_extract:943` (extractor of record),
  `clean_fetch_body:1661`, `strip_web_boilerplate:1412`, `_WEB_BOILERPLATE_LINE_RE:1320`,
  `_INLINE_SOCIAL_CHROME_RE:1565`, `is_boilerplate_or_nonassertional:1437`, Zyte path `:72-101/:96`,
  crawl4ai `_get_crawl4ai_semaphore:718`
- `src/polaris_graph/retrieval/live_retriever.py` — `_extract_pdf_text:2900` (Docling-first → PyMuPDF),
  `_docling_extract:3977`, PDF route `:2220`, Sci-Hub OA-PDF `:4090`, `is_content_starved:2988`,
  `_is_access_denial_stub:2974`, `PAYWALL_STUB` fail-loud `:2900-2915`
- `src/polaris_graph/retrieval/shell_detector` — bad-fetch / access-denial / Cloudflare screen (single source)
- `src/polaris_graph/retrieval/content_quality_gate.py:43` — document-level gate (do NOT flip on as the chrome fix)
- `src/polaris_graph/authority/junk_detection.py` — structural junk floor
- `src/polaris_graph/generator/fetch_snapshot.py` — post-fetch corpus checkpoint (resume-from-nearest; DATA-only, not extraction)
- `docs/retrieval_landscape_2026.md` / `docs/consolidation_landscape_2026.md` — adjacent sections
  (reranker, quality weight, dedup, embedder, claim-dedup) — cross-referenced, not duplicated here

---

## 11. Recency audit (2026-06-23/24) — is this 2025/2026 frontier, or did old methods sneak in?

Operator challenge: "Are these the 2025/2026 best way for fetch+extraction, not old old methods?"
Every method below was date-checked against its primary source; pre-2024 is rejected unless it is the
genuine incumbent floor (and then flagged as floor, not frontier).

**Verdict: frontier.** The only pre-2024 methods present are the genuine incumbent floors we keep
(Trafilatura, readability-lxml as last-resort, PyMuPDF), each explicitly marked as floor and each
benched against a 2026 challenger.

| Method | Date / status | Frontier or floor — and what it bakes against |
|---|---|---|
| WCXB benchmark | 2026-05 (arXiv 2605.21097) | **Frontier** — the 2026 main-content yardstick + the union-of-extractors evidence |
| Beyond a Single Extractor | 2026-02 (arXiv 2602.19548) | **Frontier** — second, non-WCXB source for union-of-extractors (71% token-yield) |
| AICC / MinerU-HTML | 2025-11 (arXiv 2511.16397) | **Frontier** — primary source for MinerU-HTML (0.6B sequence-labeling, 81.8 vs 63.6 ROUGE-N F1) |
| ParseBench | 2026-04 (arXiv 2604.08538) | **Frontier (yardstick)** — second independent PDF-parsing harness (SaaS top scorer; reference only) |
| LiteParse | 2026-06 (v2.1.2, Apache-2.0) | **Frontier** — deterministic CPU-only clinical-PDF candidate; bake vs Docling/MinerU2.5 |
| Anti-bot head-to-head benchmark | 2026-05 (Paterson) | **Frontier (yardstick)** — Nodriver 28 > Camoufox 25; reframes ADD-2 to a bake-off, not a crown |
| MinerU2.5-Pro | 2026-04 (arXiv 2604.04771) | **Frontier** — 2026 PDF-parsing SOTA; the clinical-PDF ADD |
| "Beyond String Matching" table eval | 2026-03 (arXiv 2603.18652) | **Frontier** — TEDS-is-not-enough; the table-fidelity arbiter |
| Camoufox | 2026-active (MPL-2.0) | **Frontier** — 2026 anti-bot stealth fetch |
| Resiliparse | maintained, Apache-2.0 | **Current** — WCXB-verified union partner, fastest |
| Trafilatura | 2.x maintained | **Floor (still-SOTA on articles)** — benched vs rs-trafilatura + Resiliparse |
| Docling | maintained, MIT | **Current floor** — benched vs MinerU2.5 |
| readability-lxml (2010) | last-resort fallback only | **Dated** — kept ONLY as final regex-tier fallback; replaced by Trafilatura/union |
| PyMuPDF | AGPL, maintained | **Floor** — text-only PDF fallback; benched vs Docling/MinerU |
| ReaderLM-v2 / Firecrawl /parse | 2025/2026 generative | **Frontier-but-excluded** — generative, faithfulness hazard; yardstick only |
| pdfmux | 2026-05 (0.911 TEDS, beats Docling 0.887) | **Frontier-but-excluded** — commercial SaaS, not OSS/sovereign; yardstick only |
| GLM-OCR | 2026-03 (arXiv 2603.10910) | **Frontier-but-excluded** — dominated by MinerU2.5-Pro on OmniDocBench-v1.6 per opendatalab's own comparison |

**What the audit says to fold in (the real value of the question):**
- **Union-of-extractors is the headline 2026 move** the prior single-extractor design missed — WCXB
  makes it concrete with per-page-type F1, not a vibe.
- **The clinical-PDF question is Docling-vs-MinerU2.5, not "add a lane"** — POLARIS already has a
  Docling lane; the frontier is whether MinerU2.5's 95.69 OmniDocBench beats it on POLARIS's own
  journal-PDF slice, decided by an LLM-judge table score (TEDS alone is too weak, r=0.68).
- **Anti-bot is a bake-off, not a Camoufox crown** — the 2026 head-to-head (Paterson) ranks Nodriver 28
  > Camoufox = Patchright 25 on a 31-target Cloudflare slice and shows automation-protocol fingerprinting
  (not engine) is the real differentiator. So the free-tier fetch lever is "bake Camoufox vs
  Nodriver/Patchright on POLARIS's own slice" — still a Zyte-spend reducer, not a Zyte replacement.
- **Generative extractors got better but are still the wrong tool here** — for a provenance-gated
  pipeline the deterministic union wins on both faithfulness AND (per WCXB) raw F1/latency.

**Net:** the design is 2025/2026-current; the highest-value corrections from the audit are (1) move
from one HTML extractor to a deterministic union (WCXB-grounded), and (2) frame the clinical-PDF lane
as a Docling-vs-MinerU2.5 bake-off decided on an LLM-judge table score, not raw TEDS.

---

## 12. Recency-completeness note (2026-06-24, I-recency-001 #1296)

This doc is now **recency-complete** for the 2025/2026 fetch+extraction frontier: a completeness critic
flagged 5 missing candidates; each was primary-source-verified (year + URL + license) and folded in.

**Added (all verified 2025/2026, all real):**
- **Beyond a Single Extractor** (arXiv 2602.19548, Feb 2026, arXiv license) — second, non-WCXB source for
  the union-of-extractors thesis (71% token yield); dissolves the §8 WCXB-COI-alone concern. → §3, §8, §9, §11.
- **AICC / MinerU-HTML** (arXiv 2511.16397, Nov 2025, CC-BY-4.0) — the previously-missing primary source
  for MinerU-HTML; confirms it is a 0.6B **sequence-labeling extractive** (not generative) parser, 81.8 vs
  63.6 ROUGE-N F1 over Trafilatura; resolves the §7 "VERIFY license/artifact" flag. → §7, §9, §11.
- **ParseBench** (arXiv 2604.08538, Apr 2026, CC-BY-4.0, LlamaIndex) — second independent PDF-parsing
  yardstick alongside OmniDocBench-v1.6 (SaaS top scorer → reference, not a sovereign source). → §4, §7, §9, §11.
- **LiteParse** (run-llama/liteparse, Apache-2.0, v2.1.2 Jun 2026) — deterministic CPU-only clinical-PDF
  candidate (PDFium + Tesseract + grid-projection), faithfulness-safe lower-resource bake-off entry vs
  Docling/MinerU2.5. → §6, §7, §9, §11.
- **Anti-bot head-to-head benchmark** (Paterson, May 2026, secondary source) — demotes the unbenchmarked
  "Camoufox crown" to a **bake-off** (Nodriver 28 > Camoufox = Patchright 25; protocol-fingerprinting is
  the real axis). Dated-crown correction. → §6 ADD-2, §8, §11.

**Honest corrections vs the gap-finder's claims (per LAW II — assert only what the source supports):**
- ParseBench: used the verified abstract numbers (~2,000 human-verified pages, 14 methods, 5 axes); the
  gap-finder's "167,000+ test rules" figure was NOT in the abstract and is not asserted.
- LiteParse: it is PDFium + Tesseract (not "TypeScript-native parser" / "Tesseract.js" as the gap-finder
  wrote); the verified-from-repo description is used.
- Camoufox: the gap-finder's "maintenance-gap / performance-regression" flag could NOT be confirmed at the
  cited benchmark URL, so it is omitted (only the verified ranking is asserted).

**Rejected (none — all 5 verified real, 2025/2026, and relevant).**
