V30 Phase-2 → USER WISHLIST DEEP DIVE — xhigh reasoning.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## User mandate (verbatim)

> "if I upload it and run now, what functions user want, pls
> think deeply with Codex as well, user will want WikiLLM, the
> function to upload massive amount of data for analysis, the
> function for snowball memory and knowledge, the function to
> generate chart, table and artifact and infograhic, or even
> 1 click to make slide, video, infographic in top quality,
> like Manus and Notebook LLM, I need that user wish list
> carefully first"

This is a strategic-PRD ask. The user has named 7 specific
capabilities by reference to top-tier products (NotebookLM,
Manus AI). I want the joint Claude+Codex take on:
  - Whether each is a need-to-have, nice-to-have, or trap
  - Whether V30 Phase-2's audit-grade moat survives them
  - Realistic build cost + sequencing
  - What user expectations they import (the "what NotebookLM
    means" problem — a feature name carries assumptions about
    quality)

## User-named capabilities (verbatim from the message)

  1. WikiLLM — wiki-style synthesis from internal corpus
  2. Massive data upload + analysis
  3. Snowball memory + knowledge accumulation
  4. Chart / table / artifact generation
  5. Infographic generation
  6. 1-click slide deck (Manus-class)
  7. 1-click video (NotebookLM Audio Overview-class)

## Reference products + what users actually expect from them

NotebookLM (Google):
  - Upload up to ~50 sources (PDFs, Google Docs, slides, web URLs)
  - Auto-generate: study guide, briefing doc, FAQ, timeline,
    "Audio Overview" (~10min two-host podcast)
  - Free tier; integrated in Workspace
  - Time-to-first-artifact: <2 min for chat, ~5-10min for audio

Manus AI:
  - Autonomous agent that completes multi-step tasks
  - 1-click deliverables: research reports, slide decks, websites,
    spreadsheets, dashboards
  - "Click and walk away" UX — user describes outcome, agent ships
  - Heavy artifact generation (HTML reports, JS visualizations,
    branded PDFs)
  - Tier $19-$99/mo

Perplexity Spaces / Pages:
  - Upload + chat against documents
  - Auto-generated Pages (research report style)
  - Spaces for ongoing knowledge accumulation
  - $20/mo Pro tier

ChatGPT Deep Research + Canvas:
  - Long-form research synthesis
  - Canvas for collaborative editing
  - Code Interpreter for chart/table generation
  - GPT-4o image gen for infographics

## V30 Phase-2's CURRENT capability vs each user wish

Wish 1 — WikiLLM: NOT in V30 Phase-2 ship path
  - `wiki_composer.py` exists in repo but disabled under V30
  - V30 uses contract-anchored extraction (15 entities) NOT
    free-form wiki synthesis from arbitrary corpus
  - Memory rule: 3 defects fixed in wiki_composer; OpenAI shim
    when OpenRouter blocked

Wish 2 — Massive upload: PARTIAL
  - Live retrieval already pulls 300-500 sources per run
  - But user-uploaded documents (PDFs, Google Docs, slides):
    no path. AccessBypass fetches URLs. No file upload UI/API
  - No corpus persistence per-user

Wish 3 — Snowball memory: PARTIAL
  - Memory caches exist: cross-vector cache, content cache, search
    cache, evidence hierarchy cache, session feedback cache, exa
    cache (memory: MAX-QUALITY)
  - But no per-user knowledge graph that grows across sessions
  - Codex run-7 audit framing: V30 audit-grade is single-shot,
    not iterative-amplification

Wish 4 — Chart/table/artifact: PARTIAL
  - M-42b deterministic Trial Summary table builder (text-only)
  - Trial Program Timeline (text-only)
  - Bibliography (text-only)
  - NO chart generation (no plotly/matplotlib in pipeline)
  - NO image artifacts
  - Output is markdown report.md

Wish 5 — Infographic: NOT IMPLEMENTED
  - Would require image-gen LLM + design templates
  - Audit-grade discipline: every visual claim must be
    citation-bound (NotebookLM/Manus do not do this)

Wish 6 — Slide deck: NOT IMPLEMENTED
  - Would require deck composition layer (e.g., Reveal.js,
    python-pptx) + design template + LLM-driven outline
  - Manus-class: takes report → 12-20 slides with visuals,
    speaker notes, branded theme

Wish 7 — Video / audio overview: NOT IMPLEMENTED
  - Would require: TTS (multi-voice for podcast format), script
    generation (NotebookLM uses two-host conversation prompt),
    audio mixing, optional video synthesis
  - Compute/cost shock: TTS at scale + video gen is expensive

## What I want Codex's input on

For each wish, I want Codex's take on:

1. **User expectation mapping** — when a user says "WikiLLM"
   or "infographic", what is the implicit quality bar (vs
   NotebookLM/Manus)? Where does V30 Phase-2's audit-grade
   discipline conflict with that bar?

2. **Moat impact** — does adding the feature DILUTE V30's
   audit-grade differentiation, or AMPLIFY it? E.g., a slide
   deck with citation-bound bullet points may strengthen the
   moat; a NotebookLM-style podcast with 10min of unhedged
   conversational claims may break it.

3. **Sequencing call** — within the joint plan from the prior
   strategic review (Phases A-D), where does each wishlist item
   land? Phase A demo, Phase B beta, Phase C production, or
   Phase D top-tier?

4. **Build cost + technical risk** — honest engineering days
   per item.

5. **Anti-pattern flags** — which user wishes are TRAPS that
   would force V30 to compete on the wrong axis (e.g., chasing
   Manus on infographic polish when our actual moat is provenance
   binding)?

6. **Compositional gap** — V30 today produces a report.md.
   Wishes 4-7 (chart/infographic/slide/video) are all
   COMPOSITIONAL on top of report.md. Should that composition
   layer be ONE module (artifact_composer) with multiple output
   formats? Or per-format separate stacks?

7. **The "1-click magic" UX** — Manus and NotebookLM win on
   "click and walk away". V30 today is "configure scope template
   → wait 2h → read report". Is the gap closeable with a single
   UI that hides the contract complexity? Or is V30's audit
   discipline incompatible with 1-click magic?

8. **Citation density carries through?** — V30 run-14 has 112
   inline citations in markdown. When that becomes a slide deck
   (12-20 slides) or video (10min podcast), do those citations
   survive in usable form? NotebookLM podcasts have ZERO inline
   citations in the audio.

9. **Massive upload reality** — 300-500 PDFs uploaded by user
   per session. Each PDF needs OA scrape, parse, chunk, embed,
   index. That's a vector DB layer + ingestion pipeline. Is that
   in scope or a separate product (RAG-as-a-service)?

10. **NotebookLM-style snowball** — NotebookLM lets you save
    notes and they persist across sessions. Manus has a "memory"
    feature. POLARIS has run-history but no cross-run knowledge
    accumulation. Should we add a per-workspace persistent
    knowledge graph? Or is that a Phase D feature?

## What Codex should output

Write to `outputs/codex_findings/v30_user_wishlist_plan/findings.md`:

```markdown
# Codex user-wishlist deep dive: V30 Phase-2 → top-tier feature parity

## Per-wish analysis

For each of: WikiLLM, massive upload, snowball memory, chart/table,
infographic, slide deck, video/audio:

  - User expectation (what NotebookLM/Manus set as bar)
  - V30 today (none / partial / full)
  - Moat impact (dilute / neutral / amplify)
  - Build cost (engineering days, honest)
  - Phase placement (A/B/C/D from prior plan)
  - Anti-pattern flag (yes/no, with reasoning)
  - Specific competitor benchmark
  - Acceptance criteria

## Trap detection

Which 1-3 of the 7 wishes are TRAPS?
Why they'd hurt V30's competitive positioning.
What to ship instead that satisfies the user need.

## Critical UX call

Is "1-click magic" compatible with audit-grade discipline?
If yes, how. If no, what alternative UX wins.

## Proposed composition layer

If artifact composition (4-7) belongs in one module, sketch it.
If per-format, justify.

## Citation-discipline carry-through

For each output format (deck/video/infographic), does the
citation layer survive? In what form?

## Snowball + upload architecture

Ingestion + persistence layer needed for wishes 2 + 3.
Recommended scope (or "out of scope for V30 Phase-2 era").

## Recommended PRD bundle for the next ship

Concrete subset of the 7 wishes that:
  - Lands in 4-12 weeks
  - Strengthens (not dilutes) audit-grade moat
  - Wins specific user moments NotebookLM/Manus don't

## Risks Codex sees that Claude missed
```

Be direct. Under 600 lines. Full xhigh budget. The user is
asking the right strategic question — pick the right wishes to
build, drop the traps.
