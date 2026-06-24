# Retrieval Landscape 2025/2026 — Best Practice + Open-Source Solutions (I-ret-001 #1293)

**Status:** research deliverable, operator-requested 2026-06-23. Section 2 ("retrieval") of the
standard pipeline-section review (`docs/standard_process_pipeline_section_review.md`).
**Method:** deep research — 7 layers, 9 parallel agents, primary-source verified for 2025/2026, then
a completeness critic, then every current-stack claim grounded against the actual POLARIS repo.
**Operator's pain that drove this:** "we have a bunch of methods plus Zyte, but we are also fetching a
lot of junk into the content." This report answers that directly.

---

## 0. The one-paragraph answer

The operator is still seeing junk. Here is the honest reason. Junk has two halves. The first half is
nav/ads/cookie-banner/social chrome — and the *mechanism* that removes it (a line-level boilerplate
strip, `clean_fetch_body` in `src/tools/access_bypass.py`) is correct-altitude and present, and its
known chrome patterns were extended on this branch under I-beatboth-011 (#1289). But that work is not
merged to main and has not been behaviorally validated, so I cannot claim it clears the junk — only
that it targets the right thing. The wrong fix — turning on the document-level `content_quality_gate` —
was already rejected in this repo's own forensic as "wrong altitude," and the deep-research synthesis
re-proposed it anyway; do not. The second half of junk is **on-topic SEO spam**: keyword-stuffed,
shallow, marketing copy that is *about the right subject*. No line strip and no reranker can catch it,
because it reads as relevant. POLARIS has no defense for this half today. That is most likely what the
operator is still seeing, and the fix is a lever POLARIS genuinely lacks: a **credibility/quality
weight** on every source. So the retrieval bake-off's #1 target is that weight. The other three
2025/2026 levers are a **real cross-encoder reranker** (a small one, not a 4B), a **structured/clinical
extraction lane** for tables, and **near-duplicate dedup run before basket weight** so syndicated copies
cannot fake corroboration.

---

## 1. What POLARIS has today (verified in the repo, not assumed)

| Layer | Current POLARIS implementation | Verified location |
|---|---|---|
| Search / discovery | Serper (Google-grade SERP) | live retrieval path |
| Fetch / unblock | crawl4ai (render) + Zyte API (paywall/anti-bot unblock) | `src/tools/access_bypass.py` |
| Extraction | **Trafilatura is the content-of-record** (`safe_trafilatura_extract`), readability-lxml then regex as fallback | `access_bypass.py`, `frame_fetcher.py` |
| Line-level junk strip | `clean_fetch_body` → `strip_web_boilerplate` + `_WEB_BOILERPLATE_LINE_RE`, **wired on the live path** | `access_bypass.py:1412/1661`; `live_retriever.py:2080, 4586` |
| Document-level quality gate | `content_quality_gate.score_content_quality` — DEFAULT-OFF (`PG_V3_CONTENT_QUALITY_GATE=0`), wired only in `analyzer.py:808` | `content_quality_gate.py:43` |
| Near-dup dedup | `ContentDeduplicator` (MinHash + SimHash) exists; imported by analyzer/graph paths | `src/utils/content_deduplicator.py` |
| Claim-level dedup | `fact_dedup` — sentence/numeric-signature consolidation (a different thing from URL near-dup) | `generator/fact_dedup.py` |
| "Rerank" | **No real cross-encoder.** `_rerank_and_reserve` is no-model lexical token-overlap; `prefetch_offtopic_filter` is embedding-cosine off-topic screening. Comment confirms "no torch reranker added (§8.4)" | `live_retriever.py:3178`; `evidence_selector.py:2065` |
| Embedder | all-MiniLM today; decision already made to move to Qwen3-Embedding-8B | I-arch-009 (#1266) |

**Three corrections to the raw research synthesis, grounded in the repo:**

1. **Trafilatura is already the primary extractor, not a fallback.** The extractor itself is not the
   gap. What comes after extraction is.
2. **The correct junk fix already exists and is wired.** `clean_fetch_body` runs on the live fetch
   path at `live_retriever.py:2080` and again before the provenance quote is built at `:4586`. This is
   the I-beatboth-011 (#1289) work — line-level chrome strip, junk-source screen at three fresh-run
   injection seams, plus 12 §-1.1 chrome/NUL/repetition defects fixed.
3. **POLARIS has no real reranker.** Adding a cross-encoder is a genuine new capability, not a
   duplicate of something already present.

---

## 2. Why junk gets in: the two halves (this is the crux)

Junk has two halves, and no single tool fixes both.

- **Off-topic junk** — pages about the wrong subject. Killed by search ranking and a relevance
  reranker. POLARIS partly handles this with the embedding-cosine off-topic filter.
- **On-topic junk** — keyword-stuffed SEO spam, marketing copy, nav/ads/cookie-banners, and boilerplate
  that is *about the right subject*. This scores HIGH on every search API and every reranker and passes
  straight through. It dies only at two places: **extraction** (line-level strip) and **credibility
  weighting**. A better SERP API or a better reranker does nothing for it.

The operator's pain is mostly the second half. That is why the fix is the line-level strip plus a
credibility weight, not a new search engine.

---

## 3. The 2025/2026 best-practice cleaning pipeline (ordered)

This is the convergent recipe across the extraction, quality, dedup, and reranking research. Apply in
this order:

1. **Render / unblock** — Playwright for JS pages; Zyte for paywalled/anti-bot. Does no cleaning.
2. **Extract-clean (the #1 anti-junk lever)** — a deterministic main-content extractor isolates the
   body and drops nav/ads/chrome. Trafilatura 2.x is the deterministic default. Per "Beyond a Single
   Extractor" (arXiv 2602.19548), one extractor never suffices — a union of trafilatura + resiliparse
   raises token yield because only ~39% of pages survive all extractors. **Faithfulness rule: use
   deterministic extractors that keep verbatim spans; never let an LLM rewrite a span the verifier
   later checks.**
3. **Line-level strip** — remove boilerplate *lines inside* an otherwise-good page. This is the only
   technique that fixes junk-mixed-into-real-content without dropping the page. **POLARIS already does
   this** (`clean_fetch_body`). The 2025/2026 research equivalent is FinerWeb (DeBERTa-v3 line-strip).
4. **Near-dup dedup on extracted bodies** — MinHash + LSH collapses mirrored/syndicated copies so junk
   cannot fake corroboration in a basket. Run it *after* extraction (so chrome differences do not
   defeat the body match) and *before* basket weight is computed (so corroboration is not double-
   counted). RAG-specific evidence: arXiv 2605.09611 (byte-exact dedup in RAG, three-regime analysis).
5. **Obvious-junk hard floor (the only allowed drop)** — Gopher-class structural checks (symbol/bullet/
   repetition ratios, mojibake, min-length) plus structural junk detection. This is POLARIS's
   `content_quality_gate.py` + `junk_detection.py`. **But the document-level gate is the wrong altitude
   for the operator's junk** (see §4).
6. **Relevance rerank (drops OFF-TOPIC only)** — an instruction-aware cross-encoder with a calibrated
   threshold. Does NOT remove on-topic spam.
7. **Quality + credibility as a WEIGHT (never a drop)** — a learned quality score plus tier/authority
   weight, surfaced to consolidation and faithfulness. This is where on-topic-but-shallow SEO spam is
   *demoted*, not deleted. Consistent with the weight-not-filter DNA (CLAUDE.md §-1.3).

---

## 4. The document-gate trap (do NOT flip `PG_V3_CONTENT_QUALITY_GATE`)

The raw research synthesis named "turn on `PG_V3_CONTENT_QUALITY_GATE`" as its #1, near-free
recommendation. **That is wrong, and this repo already proved it wrong in writing.**

- Repo forensic, I-beatboth-010 finding idx 47 (P1), `coverage_codex_verdict.stderr.txt:258`:
  *"`content_quality_gate` (`PG_V3_CONTENT_QUALITY_GATE`) is DORMANT and wrong-altitude (scores the
  WHOLE document pre-extraction, not the cited span). Do NOT enable it as the fix (a long real PDF with
  a few chrome lines passes the document-level checks; chrome still leaks at span-selection). REJECT
  flipping `PG_V3_CONTENT_QUALITY_GATE` — wrong-altitude; the line-level strip is the correct
  mechanism."*
- Confirmed in code: `score_content_quality(text, url)` takes a whole-document string and check #1 is
  "reject < 500 chars (likely paywall shell)." It is a document-level min-veto. The operator's junk is
  chrome *inside* long good documents, which this gate passes.

The correct altitude is the line-level strip, which already exists and is already wired. Its known
pattern gaps were already closed on this branch: I-beatboth-011 idx 46/68/b1/b2 added whole-line,
multi-token-anchored patterns for Scribd ("Download free for N days", "Upload Document"), Facebook
("Like Comment Share", inline blob image URLs), YouTube ("N subscribers Subscribed", "Tap to unmute"),
ResearchGate ("CITATIONS N READS N"), journal masthead/ISSN, publisher login-nav, and MDPI/MIT nav
(`access_bypass.py:1343-1368`). So the completeness critic's "the strip misses Scribd/FB/YT social
chrome" finding is itself stale — it describes gaps the recent commits closed. The genuine open item at
this layer is behavioral: confirm the strip actually fires at every injection seam on a real run (it is
not merged or validated yet), and keep extending patterns as new chrome shapes appear — both inside the
existing line-level machinery, not the document gate.

This entry is itself an application of the standing rule (`feedback_avoidable_vs_structural_review_miss`):
**a recommendation that describes flipping a cap/floor on is auto-reject until line-by-line grounded.**

---

## 5. KEEP vs ADD (against the current Serper + Zyte + crawl4ai + Trafilatura stack)

**The current stack is fundamentally sound. The gaps are concentrated, not architectural.**

### KEEP (verified present and correct)
- **Serper** — Google-grade SERP. Keep. (Optionally add a parallel neural path for long-tail recall.)
- **Zyte API** — best paywall/anti-bot unblock; operator-keyed. This is the **one** place no
  open-source equal exists (crawl4ai covers the rest of fetch). Keep.
- **crawl4ai** — sovereign Apache-2.0 fetch engine. Keep.
- **Trafilatura** — the right deterministic extractor of record. Keep.
- **`clean_fetch_body` line-level strip** — the correct-altitude junk fix, already wired. Keep + extend
  patterns.
- **`content_quality_gate.py` / `junk_detection.py`** — keep as the obvious-junk structural floor; do
  NOT promote the document gate to the live junk fix.
- **`ContentDeduplicator` (MinHash/SimHash)** — keep; verify wiring (see ADD-4).

### ADD / FIX (priority order)
1. **Credibility / quality WEIGHT signal (the biggest genuine gap).** A cheap learned quality score,
   emitted as a per-source weight, never a drop. Two candidate mechanisms: re-seeded fastText
   (DCLM / Ultra-FineWeb) trained with the domain's authoritative sources as positives and SEO-spam as
   negatives; or an Essential-Web-style 0.5B SLM annotator (arXiv 2506.14111) emitting a quality/
   complexity taxonomy label. This is the single biggest missing piece for on-topic SEO spam, and it
   slots cleanly into weight-not-filter. POLARIS already has tier/authority scoring; this extends the
   weight basis to *learned content quality*.
2. **A real cross-encoder reranker (genuine gap).** The current "rerank" is lexical token-overlap and
   cannot encode a credibility bar. **Pick a small model, not a 4B.** Per the 2026 leaderboards,
   `gte-reranker-modernbert-base` (149M, Apache-2.0) and `nemotron-rerank-1b` rank above
   Qwen3-Reranker-4B on Hit@1 at a fraction of the GPU/latency cost — which matters under the §8.4
   resource discipline. Flag-gated; calibrated drop-threshold for the OFF-TOPIC half only.
3. **Confirm near-dup dedup runs BEFORE basket weight.** `ContentDeduplicator` exists but may be
   analyzer-only. Wire/verify that MinHash collapses syndicated copies on the live path *before*
   consolidation computes basket weight, else a dozen reposts of one press release double-count as
   corroboration. Behavioral check, not just "confirm it runs."
4. **A structured/clinical extraction lane (MinerU-HTML).** Trafilatura mangles dose tables and trial
   matrices (TEDS 0.341 vs MinerU 0.739). For a clinical corpus this is load-bearing. Add as the
   high-quality lane with Trafilatura fallback. **Verify the model-weight license before commercial
   deploy** (code is Apache-2.0; weights under-specified).
5. **Optional: FinerWeb line-strip** as a learned complement to the existing regex line-strip, for
   boilerplate the patterns miss.

### DO NOT add
- Any **hard-drop quality classifier** — violates weight-not-filter.
- **CC-BY-NC** components in production (ReaderLM-v2, Jina-reranker-v3, zerank-2) — inspiration only.
- **LLM-semantic extractors as the content-of-record** (ScrapeGraphAI, per-page LLM distillation) — a
  fabrication/omission hazard for a provenance-gated pipeline. The deep-research-stack literature sells
  per-page LLM distillation as the universal lever; for POLARIS it is a faithfulness risk.

---

## 6. The retrieval bake-off candidate list (the next step)

Open-source-first (sovereignty). **Acceptance is behavioral, not a vendor score:** run each candidate
on a banked `corpus_snapshot.json` and measure (a) junk reduction, (b) recall preservation — did a real
source get dropped, (c) faithfulness intact (§-1.4). No candidate is crowned on a vendor/COI number.

**Extraction (content-of-record):**
- Trafilatura 2.x (Apache-2.0) — incumbent / safe default
- MinerU-HTML (Apache-2.0 code; verify weights) — structured/clinical lane
- Resiliparse (Apache-2.0) — recall-biased ensemble partner (union with Trafilatura)

**Reranker (relevance gate, Apache-2.0 only):**
- `gte-reranker-modernbert-base` (149M) — lead candidate to bench (vendor leaderboards put it at top
  accuracy for lowest cost; the behavioral bake-off decides, not the leaderboard)
- `nemotron-rerank-1b` (verify license)
- BGE-reranker-v2-m3 — cheap baseline
- Qwen3-Reranker-4B / -8B — one candidate, NOT the presumptive pick (4B GPU cost)
- zerank-1-small — calibrated scores (makes a fixed drop-threshold trustworthy)
- *(Jina-reranker-v3, zerank-2 excluded — CC-BY-NC)*

**Quality WEIGHT signal:**
- Re-seeded fastText (DCLM / Ultra-FineWeb mechanism)
- Essential-Web 0.5B SLM annotator (arXiv 2506.14111) — taxonomy labels as weights
- FineWeb-Edu embed + linear head — alternative mechanism

**Dedup:**
- MinHash + LSH threshold sweep (datasketch MIT / text-dedup Apache-2.0) + RETSim for spun spam

**Search (optional breadth add, parallel to Serper):**
- Exa (neural long-tail), Brave (independent index + Goggles), SearXNG (sovereign aggregator of
  arXiv/PubMed/Semantic Scholar)

**Late-interaction / multi-vector retrieval (NEW — material gap from the 2026-06-23 recency audit):**
- `GTE-ModernColBERT-base` (Apache-clean base) — lead candidate to bench
- `Reason-ModernColBERT` (150M; beats all ≤7B models on BRIGHT reasoning-retrieval; CC-BY-NC but
  reproducible to Apache in a <2h fine-tune) — tooling: PyLate (LightOn, arXiv 2508.03555)
- Token-level MaxSim late interaction is a distinct 2025 retrieval frontier strong on out-of-domain,
  long-context, and reasoning-intensive retrieval — the deep-research regime. Bench against the
  single-vector embedder path, do not assume it replaces it.

**Embedder (cross-ref, decision already made):** Qwen3-Embedding-8B per I-arch-009 (#1266) — the top
commercially-clean/Apache open-weight pick. Note here so the reranker recommendation does not float
without its embedding substrate; not re-baked-off in this section. (Yardsticks-to-beat:
Llama-Embed-Nemotron-8B leads multilingual MTEB but is CC-non-commercial; Gemini-001 leads English MTEB
but is closed — both non-sovereign.)

---

## 7. Honest uncertainty

- **Benchmark numbers are vendor/self-reported and not cross-comparable** (Qwen3 on MTEB-R vs Jina/mxbai
  on BEIR; rs-trafilatura's WCXB is author-aligned). None is an independent head-to-head — hence the
  behavioral bake-off requirement.
- **License verify-before-adopt:** MinerU-HTML model weights, rs-trafilatura repo license, FinerWeb and
  AI-slop code licenses are under-specified in the fetched sources.
- **Automatic AI-slop / SEO-spam detection is genuinely immature** (AUPRC 0.52–0.55, GPT-5 κ≈0). Use it
  only as a low-weight down-rank, never a gate.
- **The exact contribution of each junk source needs a behavioral replay (§-1.4)** before the bake-off
  invests in new tooling. Highest-confidence claim: the line-level strip is the correct mechanism and is
  already wired; the highest-value ADD is the credibility/quality weight, then the small reranker.

---

## 8. Relevant files (for the bake-off brief)

- `src/tools/access_bypass.py` — `clean_fetch_body:1661`, `strip_web_boilerplate:1412`,
  `_WEB_BOILERPLATE_LINE_RE:1320`, `safe_trafilatura_extract` (the line-level strip + extractor of record)
- `src/polaris_graph/retrieval/live_retriever.py` — `_rerank_and_reserve:3178` (lexical, no
  cross-encoder), `clean_fetch_body` wired at `:2080` and `:4586`
- `src/polaris_graph/retrieval/content_quality_gate.py:43` — document-level gate (do NOT flip on as the
  junk fix)
- `src/polaris_graph/authority/junk_detection.py` — structural floor
- `src/polaris_graph/retrieval/prefetch_offtopic_filter.py` — embedding-cosine off-topic
- `src/utils/content_deduplicator.py` — MinHash/SimHash near-dup (verify live-path wiring)
- `src/polaris_graph/generator/fact_dedup.py` — claim-level dedup (not URL near-dup)
- `.codex/I-beatboth-010/coverage_codex_verdict.stderr.txt:258` — the idx-47 forensic rejecting the
  document-gate flip

## 9. Primary sources (2025/2026)
- "Beyond a Single Extractor" — arXiv 2602.19548 (union of extractors)
- Essential-Web v1.0 — arXiv 2506.14111 (0.5B SLM quality/complexity annotator)
- Taxonomy-Guided Recovery of High-Performing Data — arXiv 2606.07778 (weight-not-filter for low-tier)
- Byte-Exact Dedup in RAG — arXiv 2605.09611 (RAG-specific dedup, three-regime)
- Qwen3-Embedding / Qwen3-Reranker (Apache-2.0) — github.com/QwenLM/Qwen3-Embedding
- Open-source reranker alternatives 2026 — zeroentropy.dev (gte-modernbert, nemotron-rerank leaderboard)
- IterResearch / Tongyi DeepResearch — arXiv 2510.24701 / 2511.07327 (query-gen winner, prior section)

---

## 10. Recency audit (2026-06-23) — is this 2025/2026 frontier, or did old methods sneak in?

Operator challenge: "Are these the 2025/2026 best way for retrieval, not old old methods?" An
adversarial recency audit (10 agents, 144 web lookups, every method date-checked against its primary
source, plus two critics: one hunting for any old method crowned as current, one hunting for missing
2025/2026 methods).

**Verdict: both critics returned `all_current_frontier`. No dated method is crowned as frontier.** Of
46 methods checked: 26 genuine 2025/2026 frontier, 13 classic-but-still-SOTA (each verified against a
2025/2026 source that still uses it for this exact job), 7 dated/superseded.

**The 7 dated methods — and every one is already flagged in this report as old and replaced, not
recommended:**

| Dated method | Why dated | What replaces it (verified) |
|---|---|---|
| readability-lxml (2010) | DOM-scoring heuristic; WebMainBench ~0.654 vs Trafilatura 0.640 / MinerU 0.900 | Trafilatura 2.x primary; MinerU-HTML quality lane. We keep readability ONLY as last-resort fallback |
| rs-trafilatura | single-author, pre-1.0, self-reported numbers — do not pick as the frontier | MinerU-HTML (quality) + Trafilatura 2.x (heuristic). Bake-off only, never default |
| fastText DCLM classifier (2024) | prior generation; beaten on its own benchmark | Ultra-FineWeb (already named) + Nemotron-CC ensemble |
| RETSim/UniSim (2023) | repo archived 2025-04, no 2025 maintenance | SemHash/Model2Vec + MinHash+LSH |
| SimHash (2002) | MinHash+LSH beats it for text dedup; no modern corpus pipeline picks it | MinHash+LSH (already the recommendation) |
| BGE-reranker-v2-m3 (2024) | only genuinely pre-2025 reranker; 2025 Apache-2.0 cohort beats it | Qwen3-Reranker / gte-reranker-modernbert (already named) |
| all-MiniLM-L6-v2 (2020) | **POLARIS's CURRENT embedder** — 256-tok cap, MTEB ~56; this is the defect, not a recommendation | Qwen3-Embedding-8B (already decided, I-arch-009 #1266) |

So the answer is **yes, frontier** — and the only "old old methods" present are the ones we are
explicitly replacing, including our own all-MiniLM embedder.

**The classic-but-still-SOTA calls that an expert would double-check, and why they held (web-verified):**
MinHash+LSH (1997) is still the documented 2025 production dedup standard (FineWeb2, RedPajama-V2,
Zyda-2, Olmo3 all run it); Brave Search is SOTA precisely because Microsoft retired the Bing Search API
on 2025-08-11, leaving Brave the only large independent Western index; Gopher structural rules (2021)
are still the cheap first-pass floor in Dolma/FineWeb; PubMed/arXiv/OpenAlex are corpus-ACCESS APIs
(neural rerankers layer on top, they do not replace the access path); SearXNG is the one sovereign
search option (everything else in that layer is proprietary SaaS).

**What the audit says we MISSED — fold into the bake-off (this is the real value of the question):**

- **MATERIAL — late-interaction / multi-vector retrieval (a whole layer we under-evaluated).** Both
  critics flagged it. `Reason-ModernColBERT` / `GTE-ModernColBERT` via PyLate (LightOn, arXiv
  2508.03555, CIKM 2025): a 150M late-interaction retriever beats every model up to 7B on BRIGHT, the
  gold-standard *reasoning-intensive* retrieval benchmark — exactly the deep-research regime POLARIS
  targets. The report had it only as a BGE-M3 footnote. Sovereignty: GTE-ModernColBERT-base is the
  cleaner-licensed base (Reason-ModernColBERT is CC-BY-NC but reproducible to Apache in a <2h
  fine-tune). **Add late-interaction as a first-class bake-off layer.**
- **Search:** Tavily and Parallel.ai (the de-facto 2025/2026 agent-search APIs returning LLM-ready
  excerpts vs Serper's raw SERP), Semantic Scholar API, Linkup. All proprietary — weigh against
  sovereign SearXNG.
- **Fetch:** Firecrawl v2/v2.5, Stagehand v3, Browser Use (agentic interaction for login/JS-walls).
- **Extraction:** ReaderLM-v2 (Jina HTML→MD SLM — but generative, faithfulness caveat applies),
  jusText (3rd extractor in the Apple union), and adopting the union as a *deployment pattern* not just
  citing the paper; MainWebBench/AICC as the independent extraction yardstick.
- **Quality:** Nemotron-CC ensemble (+5.6 MMLU over DCLM), FineWeb2-hq language-adaptive thresholds,
  and **Recycling-the-Web / REWIRE** (rewrite low-quality docs instead of dropping — directly aligned
  with weight-don't-filter).
- **Chunking/dedup:** **Contextual Retrieval (Anthropic)** — prepend an LLM-generated context blurb to
  each chunk before embedding; SemHash+Model2Vec; LSHBloom and GPU-MinHash (FED) for scale.
- **Reranking:** Qwen3-VL-Reranker (multimodal), Cohere Rerank 4 (proprietary), ERank.
- **Embedding:** EmbeddingGemma (sub-500M on-device), Granite-Embedding-R2 (IBM Apache-2.0
  long-context); Gemini-001 and Llama-Embed-Nemotron-8B as non-sovereign yardsticks-to-beat (one minor
  honesty fix: Qwen3-Embedding-8B is the top *commercially-clean/Apache* open-weight pick, not the
  outright #1 — Llama-Embed-Nemotron-8B leads multilingual MTEB but is CC-non-commercial).
- **Orchestration:** Tongyi DeepResearch 30B, MiroThinker-1.7, TTD-DR (diffusion-style report
  generation), Salesforce EDR/SFR-DeepResearch — open-weight/OSS deep-research stacks to study.

**Net:** the report is 2025/2026-current; the highest-value correction from the audit is adding
late-interaction retrieval (ColBERT-style) as a first-class bake-off layer, because it is purpose-built
for the reasoning-retrieval job a deep-research pipeline lives on.
