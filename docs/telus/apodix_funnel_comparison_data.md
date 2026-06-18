# Apodix — Data-Funnel Comparison: Verified Numbers Ledger

*Dated 2026-06-18. Every figure below is primary-sourced and independently measured (not vendor self-report). Personally re-fetched/verified the two load-bearing arXiv papers (2509.04499 Table 1, 2604.03173 abstract) on 2026-06-18. Backing research: workflow wcldl4oxf (9 agents, 506k tokens). No accuracy benchmark is claimed for Apodix's own gate — Apodix entries are architectural.*

## 1. The cross-engine data funnel (apples-to-apples)

The single best apples-to-apples source is **DeepTRACE Table 1** (arXiv 2509.04499, Venkit et al., Sept 2025) — all Deep-Research agents tested on the SAME statement-level, LLM-judge-validated-against-humans methodology. Personally verified verbatim 2026-06-18 via arxiv.org/html/2509.04499v1.

| Engine (Deep Research) | Sources listed / report | Citation accuracy | Unsupported statements |
|---|---|---|---|
| **OpenAI GPT-5 DR** | 18.3 | **79.1%** (best) | **12.5%** (best) |
| **Gemini DR** | 33.2 | 50.3% | 53.6% |
| **Perplexity DR** | 7.7 | 58.0% | **97.5%** (worst) |
| **YouChat DR** | 57.2 | 72.3% | 74.6% |
| **Copilot Think Deeper** | — | 62.1% | 90.2% |

- *Citation accuracy* = fraction of statement-citations where the cited source actually supports the statement.
- *Unsupported statements* = fraction of relevant statements not supported by ANY listed source.
- Caveat: Sept 2025, predates Gemini Deep Research Max (Apr 2026); versions as tested then.

## 2. Search queries generated / task

- **Gemini**: ~80 (standard), up to ~160 (Deep Research Max). Source: Google AI dev docs ai.google.dev/gemini-api/docs/interactions/deep-research (Apr 2026).
- **OpenAI**: not publicly disclosed (developers.openai.com/api/docs/guides/deep-research).
- **Perplexity**: 21 queries → 27 citations in the official API documentation example (single illustrative example, docs.perplexity.ai, Mar 2025).

## 3. Citation-URL hallucination (a distinct failure mode)

arXiv **2604.03173** (Rao, Wong, Callison-Burch — "Detecting and Correcting Reference Hallucinations in Commercial LLMs and Deep Research Agents"). Abstract personally verified 2026-06-18:
- **3–13% of citation URLs are hallucinated; 5–18% non-resolving** across deep-research agents.
- "Deep research agents generate substantially more citations per query than search-augmented LLMs but hallucinate URLs at higher rates."
- `urlhealth` self-correction tool reduces non-resolving URLs by 6–79× to under 1%.
- (Per-engine 13.3% for gemini-2.5-pro-deepresearch is in the full text, NOT the abstract — cite the abstract-confirmed RANGE on slides, not the single figure.)

## 4. The depth paradox (the structural argument)

arXiv **2605.06635** ("Cited but Not Verified", Onweller et al., May 2026), depth ablation:
- **GPT-5.4 fact-check: 78.6% (2 tool calls) → 16.7% (150 tool calls)** — a 62-point collapse.
- Meanwhile Link-Works and Relevant-Content stay **95–100% at every depth.**
- Claude Opus 4.6 degrades more gracefully (80.0% → 57.9%).
- Across all 14 frontier models: factual accuracy 39–77%; link validity >94%; relevance >80%.

## 5. CJR / Tow Center news-attribution errors (8 engines, Mar 2025)

Grok-3 **94%** wrong · ChatGPT Search **67%** · Perplexity free **37%** (best) · Copilot ~69% of answered · Gemini "completely correct on only one occasion" of 200.

## 6. Apodix column — ARCHITECTURAL, not a benchmark

From the codebase (real constants, not marketing):
- **Query expansion**: STORM 8 perspectives × 4 rounds = up to 32 search-driven interview rounds (`PG_STORM_PERSPECTIVES_COUNT=8`, `PG_STORM_ROUNDS_PER_PERSPECTIVE=4`; Stanford STORM arXiv:2402.14207).
- **Retrieve**: thousands of candidates, FULL-CONTENT fetch, recall-first.
- **Consolidate**: per-CLAIM basket — all corroborators kept (weight-and-consolidate DNA).
- **Verify**: independent entailment of every sentence vs the EXACT cited span — deterministic floor (span-bounds + numeric-subset + content-word overlap ≥2, `PG_PROVENANCE_MIN_CONTENT_OVERLAP` default 2) UNDER a different-family judge (writer deepseek-v4-pro ≠ checker glm-5.1/minimax-m2/qwen3.6).
- **Unsupported claims**: dropped or labelled "could-not-verify" — never asserted as fact.
- **Seal**: GPG-signed, offline-re-executable per-claim record.

**Honesty rail:** no citation-accuracy / unsupported-rate % is claimed for Apodix's own gate. The competitor numbers above are independently-measured findings about the FIELD. The Apodix column describes the ARCHITECTURE that makes those failure modes structurally impossible to ship (dropped/labelled), not a measured score.

## 7. Latest 2026 movement, by direction (each dated + primary-sourced)

**Frontier:** Gemini Deep Research Max (Apr 2026, ~160 queries) · Perplexity "Computer" (Jun 2026, BrowseComp 40.7→83.8%) · urlhealth benchmark (arXiv 2604.03173, Apr 2026).
**Research:** Elicit Systematic Review PRISMA 2020 (May 2026, 1.0% hallucination on 5,100 extractions, 95% recall) · FutureHouse Robin in Nature (May 2026) · scite MCP (Feb 2026, 1.6B citations).
**Vertical:** OpenEvidence $250M Series D / $12B, 20M consults/mo, Epic (Jan–Feb 2026) · Harvey + LexisNexis Shepard's, $11B (Mar 2026).
**Verification (Apodix's lane):** AAR arXiv 2602.13855 (Feb 2026) · Deterministic Integrity Gates arXiv 2606.09500 (Jun 2026, 27/27 vs 11/27) · Contextual GLM 88% FACTS (2025) · Vectara HHEM-2.3 multi-domain (Nov 2025).

**The convergence:** frontier scales breadth · research proves traceability · verticals monetise the verification layer · the science specifies the deterministic floor. Apodix builds all four into one sovereign, signed pipeline.
