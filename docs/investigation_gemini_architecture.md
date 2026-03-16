# Technical Investigation: How Gemini Deep Research and Deep Think Actually Work

**Date**: 2026-03-14
**Purpose**: Architectural investigation for POLARIS pipeline redesign -- moving from threshold-driven quality gates to reasoning-driven quality emergence.
**Scope**: Internal mechanisms of Gemini Deep Research, Deep Think, and related grounded generation systems.

---

## 1. Gemini Deep Research: The Agent Loop Architecture

### 1.1 The Core Loop: Plan -> Search -> Read -> Think -> Iterate

Gemini Deep Research is an **agentic workflow** where a single user request triggers an autonomous loop of planning, searching, reading, and reasoning. The agent "autonomously determines how much reading and searching is necessary" -- there is no hard-coded iteration count.

**Operational Flow (from API documentation and reverse-engineering):**

1. **Plan**: The agent creates a detailed research plan, breaking the problem into smaller sub-tasks. It determines which sub-tasks can run in parallel vs. sequentially.
2. **Search**: Default tools are `google_search` and `url_context`. The agent generates search queries, executes them, reads results.
3. **Think**: At each step, the model "grounds itself on all information gathered so far, then identifies missing information and discrepancies it wants to explore."
4. **Iterate**: The loop continues until the agent's reasoning concludes that the information is sufficient, OR until the 60-minute maximum is reached.

**Key architectural detail**: This is NOT a fixed N-step pipeline. The model's OWN REASONING drives when to search more, what gaps exist, and when to stop. This is the fundamental difference from POLARIS's current approach.

### 1.2 Scale of Operations

From the API documentation, a typical research task involves:
- **Standard tasks**: ~80 search queries, ~250K input tokens, ~60K output tokens
- **Complex tasks**: ~160 search queries, ~900K input tokens, ~80K output tokens
- **Duration**: Most tasks complete in 5-20 minutes; max 60 minutes

### 1.3 Thinking Summaries: The Intermediate Reasoning

Gemini exposes "thinking summaries" between research steps via a specific event type (`chunk.delta.type === 'thought_summary'`). These summaries are the model's reasoning about:
- What it has learned so far
- What information is still missing
- What contradictions it has found
- What it intends to do next

**Critical insight**: The thinking summary IS the decision mechanism. The model does not check a threshold to decide "do I have enough evidence?" -- it REASONS about information sufficiency in natural language, just as a human researcher would think "I've found three sources confirming X, but no one addresses the mechanism behind Y, so I need to search for that specifically."

### 1.4 How Contradictions Are Handled

From multiple sources:
- The model "notes the conflict and which is more credible with 1-sentence reasoning"
- Deep Think explores multiple independent strategies, "generating various hypotheses, testing them against the context provided, and critiques its own proposed solutions"
- The system "performs multiple passes of self-critique to enhance clarity and detail"
- Contradictions are explicitly surfaced in the reasoning chain: "this information contradicts the earlier hypothesis, we need additional investigation from a different angle"

**Implication for POLARIS**: Contradictions should trigger MORE research from a different angle, not be averaged or ignored. The model should reason about WHY sources disagree and what that means for the claim.

### 1.5 Gemini's Internal Tooling (Reverse-Engineered)

A developer (Dejan.ai) accidentally triggered Gemini's internal reasoning disclosure, revealing:
- **Two-stage loop**: Thinking Stage (analyzes query, plans verification) -> Acting Stage (invokes tools or synthesizes)
- **Internal indexing**: `[n.n]` format where first digit = query sequence, second digit = result position within that query. Example: `[6.2]` = "second result from the sixth search query."
- **Verification-first**: "Only use tools to verify and update even known information. Never use your internal knowledge to answer."
- **Tool functions**: `GoogleSearch.SearchResults`, `GoogleSearch.PerQueryResult`, `ConversationRetrieval.RetrieveConversationsResult`
- **Code generation**: The model writes executable Python internally to manage search parameters (dates, filters, etc.)

**Key principle discovered**: Gemini operates on a "verify before synthesize" architecture. It NEVER generates from parametric knowledge alone -- every claim must be externally verified first. This is enforced at the system prompt level, not through post-hoc checking.

---

## 2. Grounding Mechanism: Technical Architecture

### 2.1 The GroundingMetadata API Structure

When grounding is enabled, Gemini returns a structured metadata object alongside the generated text:

```
GroundingMetadata:
  webSearchQueries[]         -- string array of search queries executed
  imageSearchQueries[]       -- image search queries
  retrievalQueries[]         -- queries for retrieval tools
  groundingChunks[]          -- array of source references
    .web.uri                 -- source URL
    .web.title               -- source title
    .image                   -- image source
    .retrievedContext        -- context from Vertex AI Search
    .maps                    -- Google Maps source
  groundingSupports[]        -- array linking text segments to sources
    .segment.startIndex      -- byte position (inclusive)
    .segment.endIndex        -- byte position (exclusive)
    .segment.text            -- the text span
    .groundingChunkIndices[] -- which sources support this text
    .confidenceScores[]      -- 0.0-1.0 per source, indicating support strength
  searchEntryPoint           -- HTML/CSS for search widget
  retrievalMetadata
    .googleSearchDynamicRetrievalScore  -- 0-1, likelihood search was helpful
```

### 2.2 How Grounding Works: During Generation, Not Post-Hoc

This is the most critical architectural distinction. Based on the evidence:

**The model generates text AND grounding simultaneously.** The model:
1. Receives search results as context
2. Generates response text
3. As it generates, it tracks which text segments map to which sources
4. The `groundingSupports` array links character ranges in the output to specific `groundingChunks`

**This is NOT post-hoc citation injection.** The segment-to-source mapping is produced during generation. Evidence: when output format changes (e.g., converting to JSON), "those offsets don't make sense anymore -- so Gemini just drops them." If grounding were post-hoc, it could re-compute offsets for any format.

### 2.3 Confidence Scores

Each `groundingSupport` entry includes `confidenceScores[]` (0.0-1.0) indicating how strongly each source supports that text segment. This is a per-segment, per-source score -- not a global threshold.

### 2.4 The Check Grounding API (Post-Hoc Verification)

Google ALSO offers a separate `check_grounding` API for post-hoc verification:
- Segments answer candidates into claims (typically sentences)
- Maps each claim to supporting facts using byte-position markers
- Returns per-claim support scores: "loosely approximate the fraction of claims that were found to be grounded"
- Defines perfect grounding as: "every claim in the answer candidate must be supported by one or more of the given facts -- the claim is wholly entailed by the facts"
- Supports `enableClaimLevelScore: true` for sentence-by-sentence verification
- Citation threshold configurable (default 0.6): higher = fewer but stronger citations
- Latency <500ms, usable in real-time

**Key distinction**: This is a SEPARATE API from generation-time grounding. Gemini has BOTH:
1. Generation-time grounding (model produces citations as it writes)
2. Post-hoc verification (separate API checks if generated claims are grounded)

### 2.5 High-Fidelity Grounding Mode

Google introduced "Grounding with high-fidelity mode" which:
- Uses a Gemini 1.5 Flash model fine-tuned to focus on customer-provided context
- Returns a grounding score AND source for each claim
- Designed for industries requiring zero parametric knowledge leakage (finance, healthcare)
- The model is adapted to "pay attention to the input context and not get distracted by other things"

**Implication for POLARIS**: This shows Google distinguishes between "normal grounding" (good enough for most cases) and "high-fidelity grounding" (every claim MUST come from context, no parametric knowledge allowed). POLARIS should operate in "high-fidelity" mode.

### 2.6 Grounded Generation vs. RAG: The Key Distinction

Google explicitly distinguishes:
- **Grounding**: The broader concept of "providing an LLM with external information to root its response in reality"
- **RAG**: A specific technique that retrieves documents BEFORE generation, putting them in context
- **RIG (Retrieval-Interleaved Generation)**: Google's approach where the model generates a "first draft," THEN identifies which claims need verification against external sources, retrieves data, and replaces incorrect claims

Google's DataGemma models implement RIG: the model generates, then self-identifies statistics that should be checked against Data Commons, runs those checks, and replaces incorrect values. This achieved 58% accuracy (vs 5-17% without checking).

---

## 3. Deep Think: Parallel Hypothesis Reasoning

### 3.1 Parallel Reasoning Architecture

Deep Think does NOT follow a single chain of thought. Instead:
- It "fans out across multiple hypotheses at once"
- Uses "layered inference rounds where Gemini iterates through several cycles of evaluation, pruning weaker branches while amplifying promising ones"
- The transformer backbone is "enhanced with dynamic routing layers that allocate computational resources across parallel threads, each pursuing a distinct logical path"

**Example**: For a differential equation, one thread derives analytical solutions while another simulates numerical approximations. A synthesis module evaluates coherence and selects optimal outputs.

### 3.2 Balanced Prompting

This is a key technique for preventing confirmation bias:
- The model is prompted to simultaneously attempt both **proof AND refutation** of a claim
- This prevents the model from latching onto the first plausible explanation
- Applied in Aletheia (the math research agent): "decoupling a reasoning model's final output from its intermediate thinking tokens, and adding well-chosen prompt scaffolding, enables the model to recognize flaws it initially overlooked"

**Implication for POLARIS**: When evaluating evidence, the system should not just ask "does this evidence support the claim?" but ALSO "what evidence would REFUTE this claim? Is there a reason this might be wrong?" This naturally produces higher-quality evaluation without thresholds.

### 3.3 The Aletheia Architecture (Generator-Verifier-Reviser)

Google's math research agent Aletheia reveals the clearest picture of how Deep Think works in practice:

**Three subagents**:
1. **Generator**: Produces candidate solutions/claims
2. **Verifier**: Evaluates whether the solution is correct/well-supported
3. **Reviser**: Fixes identified problems

**Loop**: "interact continuously until a solution is found that the Verifier approves, or until the attempts reach a preset (hyperparameter) limit"

**Stopping criteria**: The Verifier either:
- APPROVES the solution (quality emerges from reasoning), OR
- The system hits a compute budget (preset limit)

**Critical behavior**: The system "often admits failure to solve a problem" -- on one benchmark, it produced "No Output" for 40% of problems rather than generating low-quality answers. This is the OPPOSITE of POLARIS's current behavior where the system always produces something regardless of evidence quality.

### 3.4 Inference-Time Scaling

Deep Think implements a crucial principle: **more reasoning = better results**, with diminishing returns.
- "Compute could increase by orders of magnitude while yielding substantial gains in accuracy before eventually plateauing"
- The January 2026 version reduced compute needed for equivalent performance by 100x compared to 2025
- A "deep-thinking ratio" (ratio of deep-thinking tokens to total) shows "strong positive correlation with accuracy (average r=0.828)"
- This means: measuring HOW MUCH the model reasoned (not just output length) predicts quality better than word count or citation count

### 3.5 Self-Critique and Confidence

The system assigns confidence to parallel reasoning branches:
- Each thread undergoes "independent fact-checking against a curated knowledge graph before convergence"
- RLHF fine-tunes the parallel branches to mitigate hallucinations
- APIs expose confidence scores to allow "programmatic filtering of responses"
- The model uses "code-assisted verification" alongside reasoning

---

## 4. Evidence Evaluation: Reasoning, Not Thresholds

### 4.1 How Gemini Decides What to Include

Based on the investigation, Gemini does NOT use numeric thresholds for inclusion decisions. Instead:

**Generation-time grounding**: The model generates text conditioned on retrieved documents. If a claim cannot be traced to retrieved content, the model either:
- Does not generate it (prevention), or
- Generates it with lower confidence scores in the metadata (detection)

**The "verify before synthesize" principle**: The system instructions enforce that the model must verify claims against search results before including them. This is a REASONING constraint, not a numeric threshold.

### 4.2 The FACTS Grounding Benchmark: What Good Looks Like

Google's FACTS benchmark defines the gold standard:
- A response gets a POSITIVE label only if "all the claims in the response are grounded in the contents of the prompt"
- A response FAILS if "even one of the sentences is inaccurate"
- Claims are categorized as: **supported** (entailed by context), **unsupported** (not entailed), **contradictory** (falsified), or **no_rad** (requires no factual grounding)
- Uses "very strict" standards requiring "straightforward, indisputable evidence excerpts in the context"

**Key finding about quality vs length**: "Shorter responses that evade conveying comprehensive information can achieve high factuality scores despite poor instruction-following." This is why they added an eligibility filter -- the system must be BOTH factual AND comprehensive, not just one.

**Implication**: POLARIS's word count minimums are actually addressing a real problem (preventing evasive brevity), but they should be reasoning-driven ("does this report comprehensively address the research question?") not threshold-driven ("is it over 2000 words?").

### 4.3 Hallucination by Omission vs. Fabrication

Research distinguishes two types:
- **Fabrication**: The model invents information not in the sources
- **Omission**: The model lacks knowledge and confabulates based on "vague semantic associations"

A critical finding: "Grounding capability and fabrication resistance are distinct, weakly correlated properties -- models that excel at locating relevant information in documents may nonetheless fabricate answers at high rates."

Another finding: "Nearly half of the generated sentences belonging to correct answers cannot be grounded in the retrieved documents or pre-training corpus." Models produce correct answers "in sentences that are not directly supported by the retrieved documents or pre-training data" -- meaning the model blends parametric knowledge with retrieved content in ways that make individual sentences unverifiable even when the overall answer is correct.

### 4.4 The Groundedness Paradox

From the empirical study on groundedness in long-form generation:
- "Models frequently blend fabricated content with factually correct statements"
- "Plausible-sounding but erroneous connections between entities" -- models "accurately retrieve specific terms" while generating incorrect relationships
- Beam search decoding significantly improves groundedness WITHOUT sacrificing correctness
- Instruction tuning enhances both correctness and groundedness

**The deep lesson**: The model's DECODING STRATEGY (how it generates tokens) affects groundedness as much as the evidence it receives. This suggests quality should be shaped during generation, not just verified after.

---

## 5. Foundational Architectures: Self-RAG and ReClaim

### 5.1 Self-RAG: Reflection Tokens for Generation-Time Quality

Self-RAG (ICLR 2024, top 1% paper) is the clearest demonstration of reasoning-driven quality:

**Four reflection tokens** (generated BY the model as special tokens during text generation):
- **Retrieve**: Should I retrieve more information? (yes/no/continue)
- **IsRel**: Is this retrieved passage relevant to the query?
- **IsSup**: Is my generated text fully supported / partially supported / not supported by the passage?
- **IsUse**: How useful is this response overall? (1-5 scale)

**The generation algorithm**:
1. For each text segment, the model predicts a Retrieve token
2. If "yes": retriever fetches K passages; model generates IsRel for each
3. Model produces output text AND an IsSup token for each passage
4. At end: model generates IsUse token
5. **If IsSup = "No support": that segment continuation is FILTERED OUT during beam search**

**This is the key insight**: The model does not generate text and then check if it is supported. The model generates support assessments AS PART OF ITS OUTPUT TOKENS. Quality is not a post-hoc check -- it is part of the generation process itself.

**Segment-level beam search**: At each segment, Self-RAG generates K continuations (one per retrieved passage), then does beam search using a WEIGHTED COMBINATION of:
- IsSup probability (is this grounded?)
- IsRel probability (is the source relevant?)
- IsUse probability (is this useful?)

The weights are TUNABLE at inference time: "setting higher weights for IsSup increases citation-driven generation." This is controllable quality without hard thresholds -- the model ITSELF assesses quality, and you weight how much that assessment matters.

### 5.2 ReClaim: Interleaved Reference-Claim Generation

ReClaim (NAACL 2025) takes a different approach:

**Generation pattern**: Output = {reference_1, claim_1, reference_2, claim_2, ... reference_n, claim_n}

The model alternates between:
1. Generating a sentence-level reference (an exact quote from a source document)
2. Generating a claim that is supported by that reference

**Two-model variant (ReClaim w/IG)**:
- **ReferModel**: Given the query and all reference passages, selects the next relevant reference
- **ClaimModel**: Given ONLY the preceding reference (NOT the full corpus), generates a claim

**The constraint is architectural**: The ClaimModel literally cannot hallucinate because it only sees the reference it is supposed to be grounded in. It cannot access other information. Quality emerges from the architecture, not from checking.

**Results**: 87.7% correct attribution score, ~22% shorter citations than prior methods, 100% consistency and attribution ratios.

### 5.3 AGREE: Self-Grounding with Test-Time Adaptation

Google's AGREE framework (NAACL 2024) trains LLMs to self-ground:

**Training**: Fine-tune with LoRA on data where every sentence has citations. NLI model validates grounding during data construction. Two-tier scoring:
- Claims with NLI score > 0.7: receive citations
- Claims with NLI score > 0.5 but <= 0.7: borderline, may need more evidence
- Claims with NLI score <= 0.5: unsupported, flagged for retrieval

**Test-Time Adaptation (TTA)**:
1. Generate response with citations
2. Identify unsupported statements
3. Retrieve additional passages specifically to support those statements
4. Re-generate with expanded context
5. Repeat until all claims are supported or budget exhausted

**Key insight**: "When unsupported statements are identified, include additional information retrieved based on the unsupported statements." The model retrieves MORE evidence for SPECIFIC weak claims, rather than doing a blanket search.

---

## 6. Perplexity's Architecture: The Comparison

### 6.1 Pipeline Architecture

Perplexity operates on a fundamentally different architecture from Gemini:

**Retrieval layer**: Built on Vespa.ai, combining:
- Lexical retrieval (BM25)
- Vector embeddings (semantic)
- Metadata signals (freshness, authority)
- Multi-stage ranking: early stages narrow candidates, later stages use cross-encoders

**Chunk-level retrieval**: Documents AND their internal sections are independently retrievable. This lets Perplexity supply LLMs with "only the most relevant text spans."

### 6.2 Citation Integration

"Citations are not retrofitted post hoc; they are structurally embedded in the generation prompt and response logic, enforcing a rigorous link between every generated sentence and its factual basis."

The system "assembles a highly structured prompt, embedding ranked excerpts, metadata, and citation markers that guide the downstream generation process." This means citations are part of the PROMPT to the LLM, not added after.

### 6.3 Evidence Ranking

Perplexity applies:
- Authority scoring (domain credibility)
- Freshness signals (recency)
- Cross-source validation (agreement between sources)
- Sources that "consistently provide reliable, up-to-date information" are prioritized

---

## 7. The Key Insight: Reasoning-Driven Quality

### 7.1 The Paradigm Shift

Based on this investigation, the fundamental architectural difference between POLARIS and these systems is:

**POLARIS (current)**: Generate -> Verify (post-hoc) -> Threshold check -> Accept/Reject/Iterate
**Gemini/Self-RAG/ReClaim**: Reason about quality DURING generation -> Quality emerges from the generation process itself

The difference is not cosmetic. It is architectural:

| Aspect | Threshold-Driven (POLARIS) | Reasoning-Driven (Gemini/Self-RAG) |
|--------|---------------------------|-------------------------------------|
| Quality assessment | Post-hoc numeric check | Part of generation token stream |
| Stopping criteria | `word_count >= 2000` | Model reasons "have I covered this?" |
| Citation decisions | `citation_count >= 5` | Model generates IsRel+IsSup for each claim |
| Evidence sufficiency | `evidence_count >= 10` | Model identifies gaps and searches more |
| Contradiction handling | Average or ignore | Reason about why they disagree |
| Failure mode | Always produces output | Admits "I don't have enough evidence" |

### 7.2 How Quality Should Emerge

Based on the investigation, the mechanisms for reasoning-driven quality are:

**A. Generation-time assessment** (Self-RAG pattern):
- The model generates quality tokens (IsRel, IsSup, IsUse) alongside content tokens
- Beam search uses these tokens to PREVENT ungrounded text from being selected
- No post-hoc threshold check needed -- ungrounded content never makes it into the output

**B. Verification-first architecture** (Gemini pattern):
- The system NEVER generates from parametric knowledge
- Every claim must be traced to a retrieved source
- The system instruction enforces this, not a post-hoc checker
- Contradictions trigger more research, not averaging

**C. Architectural constraint** (ReClaim pattern):
- The claim generator ONLY sees the reference it must be grounded in
- It literally cannot hallucinate because it has no access to unverified information
- Quality is guaranteed by architecture, not by checking

**D. Iterative TTA** (AGREE pattern):
- After initial generation, identify SPECIFIC unsupported claims
- Retrieve evidence SPECIFICALLY for those claims (not blanket search)
- Re-generate until all claims are grounded or budget is exhausted
- This is targeted improvement, not threshold-based retry

### 7.3 What POLARIS Should Adopt

Based on this investigation, the POLARIS pipeline should move toward:

1. **Replace word-count gates with reasoning-based completeness assessment**: Instead of "is this report over 2000 words?", the model should reason about "does this report comprehensively address the research question? Are there important aspects that are missing?"

2. **Replace citation-count gates with claim-level grounding**: Instead of "does this report have at least 5 citations?", each claim should be individually assessed: "is this claim supported by evidence? If not, should it be removed or should more evidence be sought?"

3. **Replace evidence-count gates with information-gap reasoning**: Instead of "do we have at least 10 evidence pieces?", the model should reason about "what aspects of this question have we NOT yet found evidence for? Are there contradictions that need resolution?"

4. **Adopt the "admit failure" pattern**: Instead of always producing a report, the system should be able to say "I don't have sufficient evidence to make a well-grounded claim about X" -- this is what Aletheia does (40% "No Output" rate).

5. **Use balanced prompting for evidence evaluation**: When assessing a claim, simultaneously try to PROVE it and REFUTE it. This naturally produces better evaluation than a single-direction assessment.

6. **Target retrieval for weak claims**: When the verifier identifies unsupported claims, retrieve evidence SPECIFICALLY for those claims, not just do another round of general search.

---

## 8. Key Research Papers and Frameworks Referenced

### Core Architectures
- **Self-RAG** (Asai et al., ICLR 2024): Reflection tokens for generation-time grounding assessment
- **ReClaim** (arxiv 2407.01796, NAACL 2025): Interleaved reference-claim generation with 87.7% citation accuracy
- **AGREE** (arxiv 2311.09533, NAACL 2024): Self-grounding with test-time adaptation
- **Speculative RAG** (Google Research, 2024): Draft-then-verify with parallel generation and verifier confidence scoring

### Benchmarks and Evaluation
- **ALCE** (EMNLP 2023): First benchmark for automatic LLM citation evaluation -- fluency, correctness, citation quality
- **FACTS Grounding** (Google DeepMind, 2025): Benchmark measuring LLM ability to ground long-form responses; uses 3 independent judges
- **AttributionBench** (2024): Systematic benchmark for automatic attribution evaluators

### Gemini-Specific
- **Aletheia** (arxiv 2602.10177, Google DeepMind 2026): Generator-Verifier-Reviser math research agent; 95.1% on IMO-ProofBench
- **DataGemma/RIG** (Google, 2024): Retrieval-Interleaved Generation for fact-checking during generation
- **Grounding API** (Vertex AI): GroundingMetadata with segment-level confidence scores

### Groundedness Research
- **Groundedness in Long-Form Generation** (arxiv 2404.07060): "Nearly half of generated sentences cannot be grounded" -- beam search improves groundedness
- **Rubric-based Generative Verifier** (arxiv 2510.14660): Nugget-as-rubric paradigm for search-augmented LLM verification
- **GINGER** (arxiv 2503.18174): Information-nugget-based grounded generation

---

## 9. Summary: The Architecture POLARIS Needs

The investigation reveals a clear hierarchy of approaches, from least to most effective:

1. **Post-hoc threshold checking** (current POLARIS): Generate everything, then check metrics. This is the weakest approach because quality problems are only detected after generation, and the fix is often "generate again" with the same constraints.

2. **Post-hoc verification with targeted remediation** (AGREE/Check Grounding API): Generate, identify specific weak claims, retrieve evidence for THOSE claims, re-generate. Better because remediation is targeted, but still post-hoc.

3. **Generation-time quality tokens** (Self-RAG): The model generates quality assessments DURING generation, and beam search prevents ungrounded content from being selected. Quality emerges from the generation process.

4. **Architectural constraint** (ReClaim): The generation architecture PREVENTS hallucination by constraining what information the model can access when making each claim. Quality is guaranteed by design.

5. **Reasoning-driven agent loop** (Gemini Deep Research): The model reasons in natural language about information sufficiency, contradictions, and gaps. The "thinking summary" IS the quality mechanism. No thresholds needed because the model thinks about quality the way a human researcher would.

POLARIS should aim for a combination of approaches 2, 3, and 5: generation-time grounding awareness, targeted remediation for weak claims, and reasoning-driven iteration decisions.
