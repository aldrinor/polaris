# POLARIS v2 Architecture: Speed + Faithfulness (Revised)

## Revision History

| Rev | Date | Changes |
|-----|------|---------|
| 1.0 | 2026-03-16 | Initial 3-layer proposal |
| 2.0 | 2026-03-16 | Addressed 9 architectural loopholes (3 fatal, 3 severe, 3 moderate) |

---

## The Core Insight

Faithfulness is determined by 3 factors, in order of impact:

| Factor | Impact on Faithfulness | Current POLARIS | Evidence |
|--------|----------------------|-----------------|----------|
| **Retrieval quality** | 60%+ of hallucinations | Good search, no retrieval gate | CRAG: 320% improvement |
| **Grounded generation** | 25%+ of remaining | Anti-embellishment prompt | ReClaim: 90% citation accuracy |
| **Post-hoc verification** | Catches ~75% of residual | 4 passes, 200+ min, $4+ | MiniCheck: 75% at $0.02 |

Our 4-pass verification pipeline attacks the LEAST impactful factor at the HIGHEST cost.
Gemini attacks the MOST impactful factor (retrieval) at near-zero marginal cost.
The answer is not either/or — it's doing the RIGHT thing at each layer.

---

## The 3-Layer Architecture (Revised)

```
LAYER 1: PREVENT (fix retrieval)  -----> kills 60% of potential hallucinations
LAYER 2: GROUND (cite as you write) ---> kills 75% of remainder
LAYER 3: VERIFY (NLI on output)   -----> catches 75% of what slips through
                                         --------------------------------
                                         Net: ~97.5% faithfulness
                                         Time: 15-30 min
                                         Cost: $0.50-1.50
```

vs Current POLARIS:
```
LAYER 1: Search (good)
LAYER 2: Extract per-source (744 calls, $4.45)  <-- UNNECESSARY
LAYER 3: Verify per-evidence (NLI + LLM)        <-- WRONG GRANULARITY
LAYER 4: Synthesize (separate pass)
LAYER 5: Citation resolution (separate pass)     <-- SHOULD BE INLINE
LAYER 6: Hallucination audit (separate pass)     <-- DIMINISHING RETURNS
LAYER 7: Quality gate expansion (separate pass)  <-- ACTIVELY HARMFUL (Run #19)
                                         --------------------------------
                                         Net: 80-100% faithfulness
                                         Time: 200+ min
                                         Cost: $6-8
```

---

## 9 Loopholes Addressed in This Revision

| # | Loophole | Severity | Fix | Layer Affected |
|---|----------|----------|-----|----------------|
| L1 | Parallel Citation Collision | FATAL | Globally unique [SRC-NNN] IDs, remap in assembly | Layer 2 |
| L2 | NLI flan-t5-large fails on scientific text | FATAL | Cheap LLM gate replaces flan-t5 as primary | Layer 3 |
| L3 | Blind Outline (outline before search) | FATAL | Outline generated AFTER search, from retrieved evidence | Layer 1/2 boundary |
| L4 | Citation Misattribution Death Spiral | SEVERE | Semantic search before rewrite, verify against ALL chunks | Layer 3 |
| L5 | Frankenstein Narrative (parallel isolation) | SEVERE | Section Blueprint with definitions + boundaries | Layer 2 |
| L6 | Naive Context Fracture (orphan chunks) | SEVERE | Context-Enriched Chunking: prepend doc title + abstract | Layer 1 |
| L7 | Missing Deduplication (SEO clones) | MODERATE | MinHash/Jaccard dedup BEFORE CRAG gate | Layer 1 |
| L8 | Phantom Query Refinement (0 LLM in CRAG) | MODERATE | Budget 1 LLM call for query refinement on LOW-confidence | Layer 1 |
| L9 | Surgical Rewrite Tissue Rejection | MODERATE | Paragraph-level rewrite, not sentence-level | Layer 3 |

---

## Layer 1: PREVENT — CRAG Retrieval Quality Gate

### What It Does
Before ANY synthesis, evaluate whether retrieved evidence actually supports the research question.
Deduplicate, enrich context, and filter to a high-quality evidence pool.

### Architecture (Revised — addresses L3, L6, L7, L8)

```
Query
  |
  v
[Search Query Generation] -- 1 LLM call, generate 10-20 search queries
  |                          (outline NOT generated yet -- L3 fix)
  |                          Time: ~30s, Cost: ~$0.02
  v
[Search + Fetch] -- Parallel: Serper + S2 + DuckDuckGo
  |                 Fetch: Jina Reader (primary), Firecrawl (fallback)
  |                 Time: ~5 min, Cost: ~$0 (search API only)
  v
[Context-Enriched Chunking] -- L6 FIX
  | For each fetched document:
  |   1. Extract document title + abstract/intro (first 200 tokens)
  |   2. Split remaining content into 1024-token chunks
  |   3. PREPEND doc metadata header to EVERY chunk:
  |      "Source: {title} | {author} | {year}\nContext: {abstract_snippet}\n---\n{chunk_text}"
  |   This costs 0 LLM calls. ~100-150 tokens overhead per chunk.
  |   Without this, a chunk saying "the results showed 95% removal"
  |   has no context about WHAT was removed, from WHAT study.
  v
[MinHash/Jaccard Dedup] -- L7 FIX
  | Remove near-duplicate chunks (Jaccard > 0.80)
  | Already proven in POLARIS (POLARIS_JACCARD_DUP_THRESHOLD=0.80)
  | Prevents SEO clones and syndicated content from filling capacity
  | Cost: $0, Time: <5s (CPU, MinHash signatures)
  v
[Lightweight Retrieval Evaluator] -- CRAG core
  | NOT an LLM call. Embedding similarity + keyword overlap.
  | Score each chunk against the original query.
  |
  |-- HIGH confidence (>0.7): Use directly
  |-- MEDIUM confidence (0.4-0.7): Keep but flag for extra scrutiny
  |-- LOW confidence (<0.4): Route to Query Refinement
  v
[Query Refinement] -- L8 FIX (ONLY for LOW-confidence results)
  | IF >40% of chunks score LOW:
  |   1 LLM call to refine queries based on what WAS found
  |   "These sources were retrieved but seem off-topic: {samples}.
  |    The research question is: {query}.
  |    Generate 5 refined search queries."
  |   Re-search with refined queries, re-evaluate
  | ELSE: skip (most queries won't need this)
  | Cost: $0.02 (when triggered), Time: ~60s
  v
[Authority Ranking] -- Already in POLARIS (source_authority_scorer)
  v
[Evidence-Informed Outline] -- L3 FIX (outline AFTER search)
  | 1 LLM call with the ACTUAL retrieved evidence summaries
  | "Given these {N} sources about {topic}, generate a report outline.
  |  Organize sections around what the evidence ACTUALLY covers,
  |  not what you assume the topic should cover."
  | This prevents empty sections and evidence-outline mismatch.
  | Cost: ~$0.03, Time: ~60s
  v
Filtered Evidence Pool (top 150-200 pieces, authority-ranked, deduped, context-enriched)
```

### What Changes from Current POLARIS
- **REMOVE**: Per-source LLM extraction (744 calls -> 0 calls)
- **REMOVE**: Pre-search outline generation (moved to post-search)
- **KEEP**: Serper search, Semantic Scholar, DuckDuckGo fallback
- **KEEP**: Jina/Firecrawl content fetching
- **KEEP**: Source authority scoring
- **KEEP**: MinHash/Jaccard dedup (already proven, POLARIS_JACCARD_DUP_THRESHOLD=0.80)
- **ADD**: Context-Enriched Chunking — doc title + abstract prepended to every chunk (L6)
- **ADD**: MinHash dedup BEFORE retrieval gate, not after (L7)
- **ADD**: Embedding-based retrieval confidence scoring (CPU, <1s)
- **ADD**: Query refinement on LOW-confidence results — 1 LLM call max (L8)
- **ADD**: Evidence-informed outline generation AFTER search (L3)
- **ADD**: Hard cap: max 200 evidence pieces sent to synthesis
- **CHANGE**: Evidence chunks capped at 1024 tokens + ~100-150 token context header

### Evidence Supporting This
- CRAG: Corrective retrieval -> 320% improvement on PopQA (arXiv 2401.15884)
- Chunk size study: 1024 tokens peak faithfulness, >1024 adds noise (LlamaIndex)
- POLARIS data: 42% off-topic evidence in TEST_005 -- retrieval gate would have caught this
- Perplexity: No post-hoc NLI, achieves 93.9% SimpleQA via retrieval quality alone
- POLARIS JACCARD_DUP_THRESHOLD=0.80 already proven effective for dedup
- Blind outline: Current POLARIS generates outline before search, leading to sections with 0 evidence

### Cost: ~$0.05 (1 outline LLM call + conditional 1 refinement call)
### Time: ~7 min (search 5m + chunking/dedup/gate <30s + outline 60s)

---

## Layer 2: GROUND — Evidence-First Synthesis with Inline Citation

### What It Does
Write each section with source evidence IN THE PROMPT. The LLM cites as it writes.
No separate citation resolution pass. No separate extraction pass.
All sections share a Section Blueprint to prevent narrative fragmentation.

### Architecture (Revised — addresses L1, L5)

```
Evidence-Informed Outline (from Layer 1)
  |
  v
[Section Blueprint Generation] -- L5 FIX
  | 1 LLM call to generate a coordination document:
  |   - Shared definitions (e.g., "DVS-PEI" defined once, all sections reference)
  |   - Section boundaries: "Section 3 covers X, Section 4 covers Y — do NOT repeat"
  |   - Key terms glossary
  |   - Cross-references: "Section 7 should reference findings from Section 3"
  |   - Narrative arc: introduction -> background -> analysis -> synthesis -> conclusion
  | This is passed to ALL parallel section writers as shared context.
  | Cost: ~$0.03, Time: ~30s
  v
[Global Source Registry] -- L1 FIX
  | Assign globally unique IDs to every source ONCE, before synthesis:
  |   SRC-001: Zhang et al., J. Adhesion Science, 2024
  |   SRC-002: ASTM International, Standard D3359-23
  |   SRC-003: Kim & Park, Surface Engineering, 2023
  |   ...
  | Each evidence chunk tagged with its SRC-NNN.
  | All 15 section writers use the SAME SRC-NNN IDs.
  | No collision possible — IDs are globally unique.
  | Cost: $0, Time: <1s (programmatic assignment)
  v
For each section in outline (4 concurrent):
  |
  v
[Evidence Router] -- Already in POLARIS (evidence_router.py)
  | Select top 10-15 evidence pieces relevant to this section
  | Include actual QUOTES (not summaries) -- 500-1024 tokens each
  | Each quote tagged with its globally unique SRC-NNN
  v
[Section Synthesis Prompt]
  |
  | System: "You are writing section {N} of a research report.
  |
  |          SECTION BLUEPRINT (shared context):
  |          {blueprint}
  |
  |          RULES:
  |          - EVERY factual claim MUST cite [SRC-NNN].
  |          - Use ONLY the provided evidence. If evidence is
  |            insufficient, state the gap explicitly.
  |          - Do NOT define terms already defined in the blueprint.
  |          - Do NOT repeat content assigned to other sections.
  |          - Include a **Key Findings** subsection if this section
  |            has 3+ quantitative results."
  |
  | Evidence:
  |   [SRC-001] "Peel adhesion of silicone coatings on aluminum..."
  |       Source: Zhang et al., J. Adhesion Science, 2024
  |   [SRC-002] "Cross-cut testing per ASTM D3359 showed..."
  |       Source: ASTM International, Standard D3359-23
  |   ... (10-15 pieces, all with globally unique SRC-NNN IDs)
  |
  | User: "Write the section on {section_title}."
  v
[LLM Output] -- Contains inline citations [SRC-001], [SRC-002], etc.
  |              All sections use same ID namespace. No collision.
  v
[Quick Sanity Check] -- NOT an LLM call. Regex: every paragraph has >=1 [SRC-NNN].
  |                     If a paragraph has zero citations, flag for Layer 3.
  v
Section Complete (with globally unique source IDs)

--- After all sections complete ---

[Sequential Citation Remapping] -- L1 FIX (final step)
  | Remap SRC-NNN to sequential [1], [2], [3] for the FINAL report.
  | Build bibliography from the global source registry.
  | This is purely mechanical — no LLM call needed.
  | Already proven: short ID remapping has 99.3% preservation rate.
  | Cost: $0, Time: <1s
```

### What Changes from Current POLARIS
- **REMOVE**: Separate structured data extraction (744 LLM calls -> 0)
- **REMOVE**: Separate citation resolution pass (42 min dark zone -> 0)
- **REMOVE**: Citation agent (15 LLM calls -> 0)
- **REMOVE**: Section revision pass (15 LLM calls -> 0)
- **KEEP**: Evidence router (select relevant evidence per section)
- **KEEP**: Short ID remapping (already proven, 99.3% preservation)
- **KEEP**: Anti-embellishment prompt (ARCH-4)
- **ADD**: Global Source Registry with SRC-NNN IDs assigned ONCE before synthesis (L1)
- **ADD**: Section Blueprint for cross-section coordination (L5)
- **ADD**: Actual source quotes in prompt (not summaries)
- **ADD**: Per-paragraph citation check (regex, 0 cost)
- **ADD**: Post-synthesis sequential [1],[2],[3] remapping from SRC-NNN (L1)
- **CHANGE**: Section writing prompt includes 10-15 evidence pieces with globally unique IDs

### Why This Works Better Than Current Approach
Current POLARIS: Extract facts -> Store -> Synthesize from stored facts -> Add citations later
- Problem: LLM writes from memory of extracted facts, not from source text
- Problem: Citation added post-hoc often links to wrong evidence
- Problem: 15 parallel sections all use [1],[2],[3] pointing to DIFFERENT sources (L1)
- Problem: Parallel sections repeat definitions and overlap content (L5)

Proposed: Include source quotes with global IDs + shared blueprint -> LLM cites as it writes
- LLM has source text IN CONTEXT when it writes claims
- Citation is part of generation, not a separate step
- If source text doesn't support a claim, the LLM can't write it (constrained)
- Global SRC-NNN IDs prevent collision across parallel sections (L1)
- Section Blueprint prevents repetition and ensures narrative coherence (L5)

### Evidence Supporting This
- ReClaim: Sentence-by-sentence citation -> 90% accuracy (arXiv 2407.01796)
- G-Cite vs P-Cite study: Retrieval quality dominates both approaches (arXiv 2509.21557)
- ALCE: Even best models lack complete citation support 50% of the time on ELI5 -- retrieval is bottleneck
- VeriFact-CoT: +30pp citation F1 with evidence-in-context (arXiv 2401.15884)
- POLARIS short ID remapping: 99.3% preservation rate (proven in TEST_032)
- POLARIS Run #19: Quality gate expansion caused citation scrambling (ISSUE-26)

### Cost: 1 blueprint call ($0.03) + 15 section calls ($0.45) = ~$0.48
### Time: Blueprint ~30s + 15 sections at 4x parallel ~5 min = ~6 min

---

## Layer 3: VERIFY — Targeted Verification on Final Output

### What It Does
Run cheap LLM verification on the COMPLETED sections. Flag unsupported claims.
Verify flagged claims against ALL section evidence (not just cited source).
Rewrite failures at paragraph level to preserve cohesion.

### Architecture (Revised — addresses L2, L4, L9)

```
Completed Sections (from Layer 2)
  |
  v
[Claim Extraction] -- Regex + heuristics, NOT an LLM call
  | Split each section into atomic claims (sentences with citations)
  | Tag each claim with its cited SRC-NNN
  | ~200-400 claims for a 15-section report
  v
[Cheap LLM Initial Gate] -- L2 FIX (replaces flan-t5-large as primary)
  | Use Haiku/Flash/Llama-3-8B ($0.25/M tokens) instead of flan-t5-large
  | For each claim: "Is this claim supported by the cited evidence? Yes/No/Partial"
  | Batch 10-20 claims per call for efficiency
  |
  | WHY NOT flan-t5-large:
  |   - 512-token context window truncates scientific evidence
  |   - 6.6% pass rate on materials science in Run #2 (PG035)
  |   - Only 74.7% BAcc on general text -- worse on niche domains
  |   - Defaults to NOT_SUPPORTED when it doesn't understand domain jargon
  |
  | WHY cheap LLM:
  |   - Understands domain context (materials science, chemistry, etc.)
  |   - 8K-32K context window fits full evidence chunks
  |   - ~$0.03-0.05 per batch of 20 claims
  |   - Still 10-50x cheaper than GPT-4/Claude verification
  |
  |-- 75-85% of claims: SUPPORTED -> keep as-is
  |-- 15-25% of claims: FLAGGED -> advanced verification
  v
[Semantic Evidence Search] -- L4 FIX (before any rewrite)
  | For each FLAGGED claim:
  |   1. Embed the claim text
  |   2. Search against ALL evidence chunks (not just the cited one)
  |   3. If a different chunk supports the claim:
  |      -> Fix the citation (misattribution), don't rewrite the claim
  |   4. If no chunk supports the claim:
  |      -> Route to rewrite
  |
  | This prevents the Death Spiral:
  |   Old: Claim says "95% removal" citing SRC-005 -> NLI says unsupported
  |        -> Rewrite removes true fact
  |   New: Claim says "95% removal" citing SRC-005 -> NLI says unsupported
  |        -> Semantic search finds SRC-012 says "95% removal"
  |        -> Fix citation to [SRC-012], keep the fact
  |
  | Cost: $0 (embedding similarity), Time: <5s
  v
[Paragraph-Level Rewrite] -- L9 FIX (replaces sentence-level rewrite)
  | For claims that are truly unsupported by ANY evidence:
  |   1. Identify the paragraph containing the unsupported claim
  |   2. Rewrite the ENTIRE paragraph, not just the sentence
  |   3. Provide the paragraph's evidence set + surrounding paragraphs for context
  |   4. Prompt: "Rewrite this paragraph to remove unsupported claim X.
  |              Maintain flow with the preceding and following paragraphs.
  |              Every remaining claim must cite [SRC-NNN]."
  |
  | WHY paragraph, not sentence:
  |   - Sentence removal creates "topic jumps" (e.g., A, _, C reads awkwardly)
  |   - Paragraph rewrite can redistribute the word budget
  |   - Preserves topic sentences and transitions
  |   - LLM sees enough context to maintain coherence
  |
  | NOT a full section rewrite -- still targeted, just at paragraph granularity
  |
  | Cost: ~$0.01-0.02 per rewrite, typically 3-8 paragraphs flagged
  v
[MiniCheck NLI Spot-Check] -- flan-t5-large as SECONDARY validator
  | ONLY on rewritten paragraphs (not the entire report)
  | Quick NLI check that the rewrite didn't introduce NEW hallucinations
  | If NLI flags the rewrite: delete the paragraph entirely + log gap
  | This is flan-t5-large's strength: binary "is this text grounded?" on short passages
  | where domain expertise matters less than textual entailment
  |
  | Cost: $0.002, Time: <30s
  v
Section Finalized
```

### What Changes from Current POLARIS
- **REMOVE**: Per-evidence NLI verification (1000+ pieces -> verify only final output)
- **REMOVE**: Full LLM verification of all evidence (expensive, redundant)
- **REMOVE**: Hallucination audit pass (LettuceDetect, separate NLI model load)
- **REMOVE**: Quality gate expansion (FAIR-RAG proves iteration 4 degrades)
- **REMOVE**: Multi-round revision cycles (Run #19: shrank report from 31->23 sentences)
- **REMOVE**: flan-t5-large as PRIMARY verifier (L2: fails on scientific domains)
- **KEEP**: MiniCheck flan-t5-large as SECONDARY spot-check on rewrites only
- **KEEP**: NLI on GPU (already working)
- **ADD**: Cheap LLM (Haiku/Flash/Llama-3-8B) as primary verification gate (L2)
- **ADD**: Semantic evidence search before rewrite — fix citations, not facts (L4)
- **ADD**: Paragraph-level rewrite instead of sentence-level (L9)
- **CHANGE**: Verify SECTIONS (final output), not EVIDENCE (intermediate data)

### Why This Verification Architecture?

**Two-tier verification:**
1. Cheap LLM understands MEANING (domain context, scientific terms, nuance)
2. flan-t5-large understands ENTAILMENT (is text A derivable from text B?)

Neither alone is sufficient:
- LLM alone: May rubber-stamp plausible-sounding claims (Run #47: 100% faith, rubber-stamped)
- NLI alone: Rejects valid scientific claims it can't parse (Run #2: 6.6% pass rate)

The L4 fix (semantic search before rewrite) is critical because:
- 30-40% of "unsupported" verdicts are actually misattributions, not hallucinations
- The claim IS supported, just by a different source than the one cited
- Rewriting a true, well-written sentence because the citation is wrong is a net loss

### Evidence Supporting This
- MiniCheck: 74.7% BAcc on general text, much lower on niche domains (arXiv 2404.10774)
- POLARIS Run #2 (PG035): flan-t5-large had 6.6% pass rate on materials science evidence
- POLARIS memory lesson #19: NLI too strict for niche domains, 90% evidence killed on DVS-PEI
- HaluGate: Stacking NLI + detection > either alone (vLLM blog)
- FAIR-RAG: 2-3 iterations optimal, iteration 4 DEGRADES (arXiv 2510.22344)
- POLARIS Run #19: 4 audit rounds shrank report to 1,220 words < 2,000 minimum

### Cost: Cheap LLM ~$0.15 + semantic search $0 + rewrites ~$0.10 + NLI spot-check $0.002 = ~$0.25
### Time: LLM verify ~3 min + semantic search <5s + rewrites ~2 min + NLI ~30s = ~6 min

---

## Pipeline Flow: The Complete Picture (Revised)

```
Query
  |
  v
[Search Query Generation] -- 1 LLM call, generate 10-20 search queries
  |                          NOTE: NO outline yet (L3 fix)
  |                          Time: ~30s, Cost: ~$0.02
  |
  v
[Search + Fetch] -- Parallel: Serper + S2 + DuckDuckGo
  |                  Fetch: Jina Reader (primary), Firecrawl (fallback)
  |                  Time: ~5 min, Cost: ~$0 (search API only)
  |
  v
[Context-Enriched Chunking] -- L6 FIX
  |  Prepend doc title + abstract to every 1024-token chunk
  |  Time: <5s, Cost: $0
  |
  v
[MinHash Dedup] -- L7 FIX
  |  Remove near-duplicate chunks (Jaccard > 0.80)
  |  Time: <5s, Cost: $0
  |
  v
[CRAG Gate] -- Embedding similarity filter + authority ranking
  |              Remove low-confidence sources
  |              Time: <30s, Cost: $0
  |
  v
[Query Refinement] -- L8 FIX (conditional)
  |  IF >40% LOW confidence: 1 LLM call to refine queries, re-search
  |  Time: 0-90s, Cost: $0-0.02
  |
  v
[Evidence-Informed Outline] -- L3 FIX (outline AFTER search)
  |  1 LLM call with actual retrieved evidence summaries
  |  Outline reflects what evidence actually covers
  |  Time: ~60s, Cost: ~$0.03
  |
  v
[Section Blueprint] -- L5 FIX
  |  1 LLM call: shared definitions, section boundaries, narrative arc
  |  Passed to ALL parallel section writers as context
  |  Time: ~30s, Cost: ~$0.03
  |
  v
[Global Source Registry] -- L1 FIX
  |  Assign SRC-001, SRC-002, ... to every source. Programmatic, no LLM.
  |  Time: <1s, Cost: $0
  |
  v
[Parallel Section Synthesis] -- 15 sections, 4 concurrent
  |  Each section gets:
  |    - Section Blueprint (shared context)
  |    - 10-15 relevant evidence pieces with quotes
  |    - All evidence tagged with globally unique SRC-NNN
  |  LLM writes with inline [SRC-NNN] citations
  |  Quick regex check: every paragraph has >=1 [SRC-NNN] marker
  |  Time: ~5 min (4x parallel), Cost: ~$0.45
  |
  v
[Cheap LLM Verification] -- L2 FIX (replaces flan-t5 as primary)
  |  Batch claims, verify via Haiku/Flash/Llama-3-8B
  |  Flag unsupported claims (~15-25%)
  |  Time: ~3 min, Cost: ~$0.15
  |
  v
[Semantic Evidence Search] -- L4 FIX
  |  For flagged claims: search ALL evidence for alternative support
  |  Fix misattributions before rewriting
  |  Time: <5s, Cost: $0
  |
  v
[Paragraph-Level Rewrite] -- L9 FIX
  |  Rewrite paragraphs with unsupported claims
  |  NOT sentence-level (preserves cohesion)
  |  Time: ~2 min, Cost: ~$0.10
  |
  v
[MiniCheck NLI Spot-Check] -- flan-t5 as secondary validator
  |  Verify only rewritten paragraphs
  |  Time: <30s, Cost: $0.002
  |
  v
[Sequential Citation Remap] -- L1 FIX
  |  SRC-NNN -> [1], [2], [3] for final output
  |  Build bibliography from global registry
  |  Time: <1s, Cost: $0
  |
  v
[Report Assembly] -- Bibliography, formatting, DOCX export
  |                   Time: ~1 min, Cost: $0
  |
  v
Final Report
  Total: ~20 min, ~$0.85
  Faithfulness: 87-94% (evidence-based estimate, accounting for domain-aware verification)
```

---

## Comparison: Current vs Proposed (Revised)

| Metric | Current POLARIS | Proposed v2 (Revised) | Source |
|--------|----------------|----------------------|--------|
| **Architecture** | 8 sequential nodes | 3 layers + 9 loophole fixes | Gemini + CRAG + MiniCheck |
| **Extraction calls** | 744 ($4.45) | 0 (inline during synthesis) | Gemini pattern |
| **Citation method** | Post-hoc resolution (42 min) | Inline with globally unique SRC-NNN | ReClaim + L1 fix |
| **Outline timing** | Before search (blind) | After search (evidence-informed) | L3 fix |
| **Verification primary** | flan-t5-large (fails on sci) | Cheap LLM (domain-aware) | L2 fix |
| **Verification secondary** | N/A (flan-t5 only) | flan-t5-large (spot-check rewrites) | Two-tier design |
| **Misattribution handling** | Rewrite the claim | Fix the citation first, then rewrite if needed | L4 fix |
| **Parallel coordination** | None (sections isolated) | Section Blueprint (shared context) | L5 fix |
| **Chunk context** | Raw text (orphan chunks) | Doc title + abstract prepended | L6 fix |
| **Dedup timing** | After synthesis (too late) | Before CRAG gate (prevents waste) | L7 fix |
| **Rewrite granularity** | Sentence-level | Paragraph-level | L9 fix |
| **Evidence per source** | 2,500 tokens | 1,024 tokens + ~150 token context header | LlamaIndex + L6 |
| **Iteration cycles** | Up to 4 (degrades at 4) | Max 1 (FAIR-RAG evidence) | FAIR-RAG |
| **Time** | 200+ min | 15-30 min | |
| **Cost** | $6-8 | $0.50-1.50 | |
| **Faithfulness** | 80-100% (unstable) | 87-94% (stable, domain-aware) | Composite |
| **Word count stability** | Degrades with revisions | Stable (paragraph rewrite, no iteration) | Run #19 evidence |

---

## What We KEEP from Current POLARIS

These components are architecturally sound and should be preserved:

1. **Serper + S2 + DDG search** -- good multi-source search
2. **Jina Reader content fetching** -- proven reliable
3. **Firecrawl fallback** -- for JavaScript-heavy pages
4. **Source authority scoring** -- feeds CRAG gate
5. **Short ID remapping** -- 99.3% preservation rate (extended to SRC-NNN paradigm)
6. **Anti-embellishment prompt (ARCH-4)** -- evidence-based effectiveness
7. **MiniCheck flan-t5-large** -- repurposed as secondary spot-check validator
8. **Evidence router** -- already routes evidence to sections
9. **JSONL tracing** -- critical for observability
10. **Cost ledger** -- essential for budget management
11. **MinHash/Jaccard dedup** -- proven at 0.80 threshold

## What We REMOVE

1. **Per-source structured data extraction** (744 LLM calls)
2. **Per-evidence NLI verification** (verify output, not input)
3. **Per-evidence LLM verification** (redundant with section-level check)
4. **Separate citation resolution** (inline during synthesis with global IDs)
5. **Citation agent** (unnecessary if citations are inline)
6. **Section revision pass** (unnecessary if generation is grounded)
7. **Hallucination audit** (LettuceDetect/NLI replaced by cheap LLM + NLI spot-check)
8. **Quality gate expansion** (FAIR-RAG proves it degrades after 2 iterations)
9. **MoST bond analysis** (expensive, marginal quality gain)
10. **STORM interviews** (all 5 timed out in recent runs, inconsistent value)
11. **Pre-search outline generation** (replaced by post-search evidence-informed outline)
12. **flan-t5-large as PRIMARY verifier** (fails on scientific domains)

## What We ADD

1. **Context-Enriched Chunking** -- doc title + abstract prepended to every chunk (L6)
2. **MinHash dedup BEFORE CRAG gate** -- prevent SEO clones filling capacity (L7)
3. **CRAG retrieval quality gate** -- embedding-based, <1s
4. **Conditional query refinement** -- 1 LLM call when >40% LOW confidence (L8)
5. **Evidence-informed outline** -- generated AFTER search (L3)
6. **Section Blueprint** -- shared definitions, boundaries, narrative arc (L5)
7. **Global Source Registry** -- SRC-NNN IDs assigned once, used by all sections (L1)
8. **Source quotes in synthesis prompt** -- not summaries
9. **Per-paragraph citation check** -- regex, 0 cost
10. **Cheap LLM verification gate** -- Haiku/Flash/Llama-3-8B as primary verifier (L2)
11. **Semantic evidence search before rewrite** -- fix citations, not facts (L4)
12. **Paragraph-level rewrite** -- preserves cohesion (L9)
13. **flan-t5-large as secondary spot-check** -- verify only rewrites
14. **Sequential citation remap in assembly** -- SRC-NNN -> [1],[2],[3] (L1)
15. **Call budget** instead of time budget (deterministic)
16. **Streaming progress events** throughout pipeline

---

## LLM Call Budget

| Stage | Calls | Model | Cost |
|-------|-------|-------|------|
| Search query generation | 1 | Primary (Kimi K2.5) | $0.02 |
| Query refinement (conditional) | 0-1 | Primary | $0-0.02 |
| Evidence-informed outline | 1 | Primary | $0.03 |
| Section Blueprint | 1 | Primary | $0.03 |
| Section synthesis (parallel) | 15 | Primary | $0.45 |
| Claim verification (batched) | 10-15 | Cheap (Haiku/Flash) | $0.15 |
| Paragraph rewrites | 3-8 | Primary | $0.10 |
| **Total** | **32-42** | | **$0.78-0.80** |

Plus non-LLM costs:
- Search API calls: ~$0 (Serper free tier, S2 free)
- flan-t5-large NLI spot-check: $0.002 (GPU, local)
- Embedding similarity: $0 (CPU, local)
- MinHash dedup: $0 (CPU, local)

**Total: ~$0.80-1.00 per report**

vs Current POLARIS: 744+ LLM calls, $6-8 per report

---

## Implementation Phases (Revised)

### Phase 1: Lean Current Pipeline (1 day)
- Disable SDE, citation agent, revision, hallucination detect, STORM, MoST, corroboration
- Cap evidence at 200 pieces
- Set call budget (max_llm_calls=150)
- Run E2E with MINIMAL features to get FIRST COMPLETE OUTPUT
- This is NOT v2 -- it's making current pipeline produce SOMETHING

### Phase 2: CRAG Gate + Evidence Quality (1 day)
- Add Context-Enriched Chunking (L6: prepend doc title + abstract)
- Re-insert MinHash dedup BEFORE retrieval gate (L7)
- Add embedding-based retrieval confidence scorer
- Cap evidence at 1024 tokens/source + 150 token context header
- Authority-rank evidence pool
- Test: verify retrieval quality improves

### Phase 3: Evidence-Informed Outline + Blueprint (1 day)
- Move outline generation to AFTER search (L3)
- Add Section Blueprint generation (L5)
- Add Global Source Registry with SRC-NNN (L1)
- Add conditional query refinement (L8)
- Test: verify outline matches actual evidence, no empty sections

### Phase 4: Grounded Synthesis (2 days)
- Rewrite section_writer to include source quotes with SRC-NNN IDs in prompt
- Inline citation during generation
- Remove post-hoc citation resolution
- Pass Section Blueprint to all parallel workers
- Add sequential citation remap SRC-NNN -> [1],[2],[3] in assembly (L1)
- Test: verify inline citations are accurate, no collision across sections

### Phase 5: Domain-Aware Verification (1 day)
- Replace flan-t5-large primary with cheap LLM gate (L2)
- Add semantic evidence search before rewrite (L4)
- Implement paragraph-level rewrite (L9)
- Keep flan-t5-large as secondary spot-check on rewrites
- Test: verify faithfulness >= 85%, no valid claims deleted

### Phase 6: Full Integration + Benchmarking (1 day)
- End-to-end test with all 3 layers + all 9 loophole fixes
- Benchmark against Gemini Deep Research output
- Measure: time, cost, faithfulness, citation accuracy, word count
- Compare misattribution rate (should drop with L4 fix)
- Compare narrative coherence (should improve with L5 fix)

---

## Risk Analysis

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Cheap LLM rubber-stamps claims | Medium | High (false safety) | Two-tier: LLM + NLI spot-check. Compare results. |
| Section Blueprint too generic | Medium | Low (sections still isolated) | Few-shot examples in blueprint prompt. Iterate. |
| Context header inflates token count | Low | Medium (more $ per section) | 150 tokens/chunk = ~15% overhead on 1024. Acceptable. |
| Query refinement loop runs away | Low | Medium (time/cost) | Hard cap: 1 refinement attempt max. No loops. |
| Paragraph rewrite changes meaning | Medium | Medium (faithfulness) | NLI spot-check on rewrites. Delete paragraph if spot-check fails. |
| Evidence-informed outline biased | Low | Low (sections cover what's found) | Actually a FEATURE: outline should reflect available evidence. |

---

## References

All citations from the research report at docs/research_speed_vs_faithfulness.md.
Key papers: CRAG (2401.15884), MiniCheck (2404.10774), ReClaim (2407.01796),
FAIR-RAG (2510.22344), G-Cite vs P-Cite (2509.21557), DeepHalluBench (2601.22984).

Loophole analysis: User feedback session 2026-03-16 (9 architectural loopholes identified).
