V30 Phase-2 → INTERNET-FACING TOP-TIER PLAYER plan — xhigh reasoning.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## User mandate (verbatim)

> "if now, we need to make it fully functional, hold it on the
> internet, meet top tier player, how far we need to go from today,
> pls think deeply, and work out a plan with Codex, to give me
> the full plan"

This is a strategic-scope ask, not a code task. The user wants:
  - Honest distance assessment (today → internet-deployed)
  - Realistic timeline + sequencing
  - "Top tier player" = ChatGPT Deep Research + Gemini Deep Research
    + Perplexity Pro tier; matching them on what users actually pay for

## Today's snapshot (run-14 shipped 2026-04-26)

**Engine**: PRODUCTION-GRADE on the audit dimension
  - 396/396 tests green across V30..V33
  - 2 BB + 4 BO + 1 LB on 7 strategic dimensions
  - Beats Gemini on substance density + citation discipline
  - Loses to ChatGPT on absolute density + cross-jurisdiction synthesis
  - Reproducible: $0.0074 + 2h25m wall per query

**Gap to internet-facing product** (Claude's first-pass list):

  Tier 1 (block all users):
    - Custom research-question intake API + UI
    - Scope template builder (DOI/PMID hand-curation eats 10h+)
    - Run status streaming (today: 2h25m black box)
    - Result viewer (rendered report.md + citation hover)
    - Curator workflow for human_gap_tasks.json (M-61 path)

  Tier 2 (block real adoption):
    - Cost preview + budget guard
    - Pre-built scope template library
    - Multi-query batch sweeps
    - Export formats (PDF/DOCX/BibTeX/audit bundle)
    - Versioning + run diff

  Tier 3 (enterprise):
    - Multi-tenant auth + per-user run history
    - Citation health dashboard (DOI 404 alerts)
    - SOC2-style audit trail
    - Regression detection across shipped runs

## What "top tier player" means competitively

ChatGPT Deep Research (OpenAI):
  - Free tier ~5 deep research / week, paid tier $20-$200/month
  - Time-to-result: 5-30 min
  - Strength: dense factual content, broad source mix, smooth UX
  - Weakness (per our run-14 audit): 0 inline citations, no
    contradiction disclosure layer

Gemini Deep Research (Google):
  - Bundled in Gemini Advanced
  - Time-to-result: 5-15 min
  - Strength: long-form coverage, polished writing
  - Weakness (audit): 58 promotional adjectives, 0 95% CIs across
    6,835 words, mixed-tier source stack (PR/promo)

Perplexity Pro:
  - $20/month
  - Time-to-result: 30s-2min
  - Strength: fast, conversational, decent citations
  - Weakness: shallow vs deep-research artifacts

POLARIS V30 Phase-2 today:
  - $0.0074/query, 2h25m
  - Strength: audit-grade citations, contradiction disclosure,
    strict-verify provenance — UNIQUE in the comparison set
  - Weakness: no UI, no auth, no streaming, hand-curated contracts
    only, single-slug coverage, slow

## My (Claude's) initial assessment

Three structural deltas vs top-tier:
  1. **Speed gap**: 2h25m vs 5-30min. We need either (a) parallel
     contract execution (already partially batched) + cached
     retrieval, or (b) a fast-path "preview" mode that returns
     in 5-10min using just M-56 deterministic fetch + no full
     content-fetch + abstract-only synthesis.
  2. **Topic coverage gap**: 1 hand-curated contract today vs
     "any clinical question". We need either (a) auto-contract
     induction (LLM proposes the contract from research question)
     OR (b) a library of 50-200 pre-built contracts spanning
     common indications + drugs + biomarkers.
  3. **Distribution gap**: CLI script vs web UI + API + auth +
     billing. Standard SaaS plumbing. ~4-6 weeks engineering.

Honest distance assessment:
  - **Demo-grade ship** (single-slug, hardcoded UI): 2 weeks
  - **Beta-grade ship** (custom queries, auth, streaming, 5-10
    template library): 6-8 weeks
  - **Production-grade ship** (auto-contract induction, 100+
    template library, fast-path mode, billing, SOC2): 4-6 months
  - **Top-tier feature parity** (matching ChatGPT DR breadth +
    speed + auto-everything): 9-12 months

## What I want Codex's input on

1. **Speed strategy**: is fast-path preview mode (5-10min) more
   important than parallel-batch full sweeps? Or both?
2. **Topic coverage strategy**: auto-contract induction vs
   curated library? The induction path is research-grade hard
   (we'd need an LLM that proposes pivotal trials, regulatory
   anchors, mechanism papers from a research question — and
   doesn't hallucinate the SURPASS-2 PMID like our hand-curation
   did in run-1).
3. **Speed/quality tradeoff**: V30 Phase-2 takes 2h25m because
   we deterministically fetch every contract entity. That's the
   audit-grade discipline. Fast-path would bypass full-text
   fetch, drop M-66b-T, drop M-70 prose synthesis — which dimension
   regresses most? Worth the speed?
4. **Topic narrowness**: today only clinical_tirzepatide_t2dm
   ships. Is the right move (a) clone/curate 50 more clinical
   contracts and ship a "clinical-only" V1 product, or (b) push
   for cross-domain (clinical + policy + chemistry + DFT) earlier?
5. **Pricing/positioning**: with cost $0.0074/query, gross margin
   is huge. Where do we actually compete? "Audit-grade research
   for regulated industries" (pharma, biotech, gov) at $200/month
   pro tier? Or commodity DR at $20/month and bleed to ChatGPT?
6. **The 1 LB Regulatory gap**: ship the audit-grade niche FIRST
   (it's already differentiated) and add cross-jurisdiction
   synthesis later (V34/M-73)? Or block on closing that gap?
7. **Trust/safety blockers**: V30 Phase-2 is for clinical content.
   That's regulated. Do we need disclaimers? Gating to verified
   medical professionals? HIPAA scope statement? FDA-adjacent
   medical-device classification?
8. **Compute infra**: today 2h25m at $0.0074 on a single dev
   machine. To scale: how do we run N concurrent sweeps? Each
   sweep is 25-30 LLM calls + 300-500 web fetches. Need a
   distributed worker pool.

## Output

Write to `outputs/codex_findings/v30_phase2_to_production_plan/findings.md`:

```markdown
# Codex strategic plan: V30 Phase-2 → top-tier internet product

## Honest distance assessment

<weeks/months estimate per ship grade>

## Recommended sequencing

### Phase A — Demo-grade (T+0 to T+2 weeks)
<scope, deliverables, blockers>

### Phase B — Beta (T+2 to T+8 weeks)
<scope, deliverables, blockers>

### Phase C — Production (T+8 to T+24 weeks)
<scope, deliverables, blockers>

### Phase D — Top-tier feature parity (T+24 to T+52 weeks)
<scope, deliverables, blockers>

## Critical decisions (Codex's recommended call)

1. Speed: <fast-path preview vs parallel batch vs both>
2. Topic coverage: <auto-induction vs curated library vs hybrid>
3. Speed/quality tradeoff: <which dimensions regress in fast-path>
4. Topic narrowness: <clinical-only V1 vs multi-domain>
5. Pricing/positioning: <audit-grade niche vs commodity DR>
6. 1 LB Regulatory: <ship now vs block on V34>
7. Trust/safety: <HIPAA / disclaimers / professional gating>
8. Compute infra: <worker architecture for N concurrent sweeps>

## What V30 Phase-2 already wins on (don't lose)

<distinctive moats vs ChatGPT/Gemini/Perplexity>

## What V30 Phase-2 must add to compete

<table-stakes features the moat doesn't substitute for>

## Realistic competitive positioning at each phase

<who do we beat / lose to at A/B/C/D>

## Risk factors

<technical risk, market risk, regulatory risk>

## Recommended starting bundle

<what should land first, with concrete acceptance criteria>
```

Be direct about disagreements with my framing. Under 600 lines.
Full xhigh budget. This is the strategic plan, not a code task.
