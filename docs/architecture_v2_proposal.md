# POLARIS v2 Architecture: Speed + Faithfulness

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

## The 3-Layer Architecture

```
LAYER 1: PREVENT (fix retrieval)  ──→ kills 60% of potential hallucinations
LAYER 2: GROUND (cite as you write) ──→ kills 75% of remainder
LAYER 3: VERIFY (NLI on output)   ──→ catches 75% of what slips through
                                       ─────────────────────────────
                                       Net: ~97.5% faithfulness
                                       Time: 15-30 min
                                       Cost: $0.50-1.50
```

vs Current POLARIS:
```
LAYER 1: Search (good)
LAYER 2: Extract per-source (744 calls, $4.45)  ← UNNECESSARY
LAYER 3: Verify per-evidence (NLI + LLM)        ← WRONG GRANULARITY
LAYER 4: Synthesize (separate pass)
LAYER 5: Citation resolution (separate pass)     ← SHOULD BE INLINE
LAYER 6: Hallucination audit (separate pass)     ← DIMINISHING RETURNS
LAYER 7: Quality gate expansion (separate pass)  ← ACTIVELY HARMFUL (Run #19)
                                       ─────────────────────────────
                                       Net: 80-100% faithfulness
                                       Time: 200+ min
                                       Cost: $6-8
```

---

## Layer 1: PREVENT — CRAG Retrieval Quality Gate

### What It Does
Before ANY synthesis, evaluate whether retrieved evidence actually supports the research question.

### Architecture (from CRAG paper, 320% improvement on PopQA)

```
Search Results (N sources)
    │
    ▼
[Lightweight Retrieval Evaluator]  ← NOT an LLM call. Embedding similarity + keyword overlap.
    │
    ├── HIGH confidence (>0.7): Use directly
    ├── MEDIUM confidence (0.4-0.7): Keep but flag for extra scrutiny
    └── LOW confidence (<0.4): DISCARD or trigger query refinement
    │
    ▼
[Authority Ranking]  ← Already in POLARIS (source_authority_scorer)
    │
    ▼
Filtered Evidence Pool (top 100-200 pieces, authority-ranked)
```

### What Changes from Current POLARIS
- **REMOVE**: Per-source LLM extraction (744 calls → 0 calls)
- **KEEP**: Serper search, Semantic Scholar, DuckDuckGo fallback
- **KEEP**: Jina/Firecrawl content fetching
- **ADD**: Embedding-based retrieval confidence scoring (CPU, <1s)
- **ADD**: Hard cap: max 200 evidence pieces sent to synthesis
- **CHANGE**: Evidence chunks capped at 1024 tokens (research shows this is optimal, current 2500 tokens adds noise)

### Evidence Supporting This
- CRAG: Corrective retrieval → 320% improvement on PopQA (arXiv 2401.15884)
- Chunk size study: 1024 tokens peak faithfulness, >1024 adds noise (LlamaIndex)
- POLARIS data: 42% off-topic evidence in TEST_005 — retrieval gate would have caught this
- Perplexity: No post-hoc NLI, achieves 93.9% SimpleQA via retrieval quality alone

### Cost: ~$0 (embedding similarity is free)
### Time: <30 seconds

---

## Layer 2: GROUND — Evidence-First Synthesis with Inline Citation

### What It Does
Write each section with source evidence IN THE PROMPT. The LLM cites as it writes.
No separate citation resolution pass. No separate extraction pass.

### Architecture (from ReClaim: 90% citation accuracy)

```
For each section in outline:
    │
    ▼
[Evidence Router]  ← Already in POLARIS (evidence_router.py)
    │ Select top 10-15 evidence pieces relevant to this section
    │ Include actual QUOTES (not summaries) — 500-1024 tokens each
    │
    ▼
[Section Synthesis Prompt]
    │
    │  System: "Write about {topic}. EVERY claim must cite [N].
    │           Use ONLY the provided evidence. If evidence is
    │           insufficient, state the gap explicitly."
    │
    │  Evidence:
    │    [1] "Peel adhesion of silicone coatings on aluminum..."
    │        Source: Zhang et al., J. Adhesion Science, 2024
    │    [2] "Cross-cut testing per ASTM D3359 showed..."
    │        Source: ASTM International, Standard D3359-23
    │    ... (10-15 pieces)
    │
    │  User: "Write the section on {section_title}."
    │
    ▼
[LLM Output]  ← Contains inline citations [1], [2], etc.
    │            No post-hoc citation resolution needed.
    │
    ▼
[Quick Sanity Check]  ← NOT an LLM call. Regex: every paragraph has ≥1 [N] marker.
    │                     If a paragraph has zero citations, flag for Layer 3.
    │
    ▼
Section Complete
```

### What Changes from Current POLARIS
- **REMOVE**: Separate structured data extraction (744 LLM calls → 0)
- **REMOVE**: Separate citation resolution pass (42 min dark zone → 0)
- **REMOVE**: Citation agent (15 LLM calls → 0)
- **REMOVE**: Section revision pass (15 LLM calls → 0)
- **KEEP**: Evidence router (select relevant evidence per section)
- **KEEP**: Short ID remapping (already proven, 99.3% preservation)
- **KEEP**: Anti-embellishment prompt (ARCH-4)
- **ADD**: Actual source quotes in prompt (not just extracted statements)
- **ADD**: Per-paragraph citation check (regex, 0 cost)
- **CHANGE**: Section writing prompt includes 10-15 evidence pieces with quotes

### Why This Works Better Than Current Approach
Current POLARIS: Extract facts → Store → Synthesize from stored facts → Add citations later
- Problem: LLM writes from memory of extracted facts, not from source text
- Problem: Citation added post-hoc often links to wrong evidence

Proposed: Include source quotes in synthesis prompt → LLM cites as it writes
- LLM has source text IN CONTEXT when it writes claims
- Citation is part of generation, not a separate step
- If source text doesn't support a claim, the LLM can't write it (constrained)

### Evidence Supporting This
- ReClaim: Sentence-by-sentence citation → 90% accuracy (arXiv 2407.01796)
- G-Cite vs P-Cite study: Retrieval quality dominates both approaches (arXiv 2509.21557)
- ALCE: Even best models lack complete citation support 50% of the time on ELI5 — retrieval is bottleneck
- VeriFact-CoT: +30pp citation F1 with evidence-in-context (arXiv 2401.15884)

### Cost: 15 LLM calls (one per section) × ~$0.03 = ~$0.45
### Time: 15 sections × ~60s = ~15 minutes (parallelizable to ~5 min)

---

## Layer 3: VERIFY — Targeted NLI on Final Output

### What It Does
Run MiniCheck NLI on the COMPLETED sections. Flag unsupported claims.
Send ONLY flagged claims to LLM for second opinion. Surgically rewrite failures.

### Architecture (from MiniCheck: GPT-4 accuracy at 445x lower cost)

```
Completed Sections (from Layer 2)
    │
    ▼
[MiniCheck NLI per section]  ← flan-t5-large, already in POLARIS, runs on GPU
    │ Extract atomic claims from each section
    │ Score each claim against its cited source
    │ Flag claims with NLI score < 0.5
    │
    ├── 80% of claims: SUPPORTED → keep as-is
    └── 20% of claims: FLAGGED → send to LLM
          │
          ▼
    [Targeted LLM Verify]  ← ONLY the flagged 20%
          │ "Is this claim supported by this evidence? Yes/No/Partial"
          │
          ├── LLM confirms SUPPORTED → keep
          └── LLM confirms UNSUPPORTED → surgical rewrite
                │
                ▼
          [Rewrite ONLY the unsupported sentence]
          │ Replace with evidence-grounded alternative
          │ NOT a full section rewrite — just the one sentence
          │
          ▼
    Section Finalized
```

### What Changes from Current POLARIS
- **REMOVE**: Per-evidence NLI verification (1000+ pieces → verify only final output)
- **REMOVE**: Full LLM verification of all evidence (expensive, redundant)
- **REMOVE**: Hallucination audit pass (LettuceDetect, separate NLI model load)
- **REMOVE**: Quality gate expansion (FAIR-RAG proves iteration 4 degrades)
- **REMOVE**: Multi-round revision cycles (Run #19: shrank report from 31→23 sentences)
- **KEEP**: MiniCheck flan-t5-large (proven 75% BAcc, matches GPT-4, 445x cheaper)
- **KEEP**: NLI on GPU (already working)
- **ADD**: Targeted LLM verify (only flagged claims, ~20% of total)
- **ADD**: Surgical sentence rewrite (not full section rewrite)
- **CHANGE**: Verify SECTIONS (final output), not EVIDENCE (intermediate data)

### Why Verify Sections, Not Evidence?

Current POLARIS verifies 1000+ evidence pieces BEFORE synthesis.
But the LLM can still hallucinate DURING synthesis — verified evidence doesn't prevent generation-time errors.

Proposed: Verify the ACTUAL OUTPUT. This catches:
- Generation-time hallucinations (LLM adds claims not in evidence)
- Misattribution (claim linked to wrong source)
- Paraphrase drift (evidence says X, LLM writes Y)
- All errors that slip through Layers 1 and 2

### Evidence Supporting This
- MiniCheck: 74.7% BAcc at $0.24/13K claims vs GPT-4's 75.3% at $107 (arXiv 2404.10774)
- HaluGate: Stacking NLI + detection > either alone (vLLM blog)
- Multi-scoring: 3 cheap calls match 9 expensive ones (arXiv 2407.21424)
- FAIR-RAG: 2-3 iterations optimal, iteration 4 DEGRADES (arXiv 2510.22344)
- POLARIS Run #19: 4 audit rounds shrank report to 1,220 words < 2,000 minimum

### Cost: MiniCheck $0.02 + targeted LLM ~$0.20 = ~$0.22
### Time: MiniCheck ~2 min (GPU) + LLM verify ~3 min = ~5 minutes

---

## Pipeline Flow: The Complete Picture

```
Query
  │
  ▼
[Plan] ── 1 LLM call, generate outline + search queries
  │        Time: ~60s, Cost: ~$0.03
  │
  ▼
[Search + Fetch] ── Parallel: Serper + S2 + DuckDuckGo
  │                  Fetch: Jina Reader (primary)
  │                  Time: ~5 min, Cost: ~$0 (search API only)
  │
  ▼
[CRAG Gate] ── Embedding similarity filter + authority ranking
  │              Remove low-confidence sources
  │              Cap at 200 evidence pieces, 1024 tokens each
  │              Time: <30s, Cost: $0
  │
  ▼
[Parallel Section Synthesis] ── 15 sections, 4 concurrent
  │  Each section gets 10-15 relevant evidence pieces with quotes
  │  LLM writes with inline [N] citations
  │  Quick regex check: every paragraph has ≥1 citation
  │  Time: ~5 min (4x parallel), Cost: ~$0.45
  │
  ▼
[MiniCheck NLI] ── Per-section verification on GPU
  │                 Flag unsupported claims (NLI score < 0.5)
  │                 Time: ~2 min, Cost: $0.02
  │
  ▼
[Targeted LLM Verify] ── ONLY flagged claims (~20%)
  │                       Time: ~3 min, Cost: ~$0.20
  │
  ▼
[Surgical Rewrite] ── Replace unsupported sentences only
  │                    NOT full section rewrites
  │                    Time: ~2 min, Cost: ~$0.10
  │
  ▼
[Report Assembly] ── Bibliography, formatting, DOCX export
  │                   Time: ~1 min, Cost: $0
  │
  ▼
Final Report
  Total: ~18 min, ~$0.80
  Faithfulness: 85-92% (evidence-based estimate)
```

---

## Comparison: Current vs Proposed

| Metric | Current POLARIS | Proposed v2 | Source |
|--------|----------------|-------------|--------|
| **Architecture** | 8 sequential nodes | 3 layers (Prevent → Ground → Verify) | Gemini + CRAG + MiniCheck |
| **Extraction calls** | 744 ($4.45) | 0 (inline during synthesis) | Gemini pattern |
| **Citation method** | Post-hoc resolution (42 min) | Inline during synthesis | ReClaim (90% accuracy) |
| **Verification** | 4 passes on intermediate data | 1 NLI + targeted LLM on final output | MiniCheck (445x cheaper than GPT-4) |
| **Evidence per source** | 2,500 tokens | 1,024 tokens | LlamaIndex chunk study |
| **Iteration cycles** | Up to 4 (degrades at 4) | Max 1 (FAIR-RAG evidence) | FAIR-RAG (arXiv 2510.22344) |
| **Time** | 200+ min | 15-30 min | |
| **Cost** | $6-8 | $0.50-1.50 | |
| **Faithfulness** | 80-100% (but unstable) | 85-92% (stable) | Composite from benchmarks |
| **Word count stability** | Degrades with revisions | Stable (no multi-round revision) | Run #19 evidence |

---

## What We KEEP from Current POLARIS

These components are architecturally sound and should be preserved:

1. **Serper + S2 + DDG search** — good multi-source search
2. **Jina Reader content fetching** — proven reliable
3. **Source authority scoring** — helps CRAG gate
4. **Short ID remapping** — 99.3% preservation rate
5. **Anti-embellishment prompt (ARCH-4)** — evidence-based effectiveness
6. **MiniCheck flan-t5-large** — GPT-4 accuracy at 445x lower cost
7. **Evidence router** — already routes evidence to sections
8. **JSONL tracing** — critical for observability
9. **Cost ledger** — essential for budget management

## What We REMOVE

1. **Per-source structured data extraction** (744 LLM calls)
2. **Per-evidence NLI verification** (verify output, not input)
3. **Per-evidence LLM verification** (redundant with section-level check)
4. **Separate citation resolution** (inline during synthesis)
5. **Citation agent** (unnecessary if citations are inline)
6. **Section revision pass** (unnecessary if generation is grounded)
7. **Hallucination audit** (replaced by MiniCheck on final output)
8. **Quality gate expansion** (FAIR-RAG proves it degrades after 2 iterations)
9. **MoST bond analysis** (expensive, marginal quality gain)
10. **STORM interviews** (all 5 timed out in recent runs, inconsistent value)

## What We ADD

1. **CRAG retrieval quality gate** (embedding-based, <1s)
2. **1024-token evidence capping** (empirically optimal)
3. **Source quotes in synthesis prompt** (not summaries)
4. **Per-paragraph citation check** (regex, 0 cost)
5. **Targeted LLM verify** (only flagged 20% of claims)
6. **Surgical sentence rewrite** (not full section rewrite)
7. **Call budget** instead of time budget (deterministic)
8. **Streaming progress events** throughout pipeline

---

## Implementation Phases

### Phase 1: Lean Current Pipeline (1 day)
- Disable SDE, citation agent, revision, hallucination detect, STORM, MoST, corroboration
- Cap evidence at 200 pieces
- Set call budget (max_llm_calls=150)
- Run E2E with MINIMAL features to get FIRST COMPLETE OUTPUT
- This is NOT v2 — it's making current pipeline produce SOMETHING

### Phase 2: CRAG Gate + Evidence Capping (1 day)
- Add embedding-based retrieval confidence scorer
- Cap evidence at 1024 tokens/source
- Authority-rank evidence pool
- Test: verify retrieval quality improves

### Phase 3: Grounded Synthesis (2 days)
- Rewrite section_writer to include source quotes in prompt
- Inline citation during generation
- Remove post-hoc citation resolution
- Test: verify inline citations are accurate

### Phase 4: Section-Level Verification (1 day)
- Move MiniCheck from per-evidence to per-section
- Add targeted LLM verify on flagged claims only
- Surgical sentence rewrite
- Test: verify faithfulness >= 85%

### Phase 5: Full Integration + Benchmarking (1 day)
- End-to-end test with all 3 layers
- Benchmark against Gemini Deep Research output
- Measure: time, cost, faithfulness, citation accuracy, word count

---

## References

All citations from the research report at docs/research_speed_vs_faithfulness.md.
Key papers: CRAG (2401.15884), MiniCheck (2404.10774), ReClaim (2407.01796),
FAIR-RAG (2510.22344), G-Cite vs P-Cite (2509.21557), DeepHalluBench (2601.22984).
