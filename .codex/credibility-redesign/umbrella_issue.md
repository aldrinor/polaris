## Goal
Replace the journal-only / tier-FLOOR sourcing model with a **weighted credibility prior** that is **independence-aware** and **discloses per-claim weight + origin-count + certainty**, with honest **both-sides** presentation on contested topics. Operator directive 2026-06-07: "many things are not journal, but still credibility... why you have tendency to make yourself into tunnel view." Deep research → honest gap → careful, phased fix.

## Why (frontier intelligence, `docs/frontier_credibility_intelligence_2026_06_07.md`)
No deployed system does credibility-weighted, both-sides deep research well. Frontier DR (OpenAI/Gemini/Perplexity/Claude/Copilot/Grok) narrate credibility as prose or a link list — **none discloses a credibility weight, a per-claim evidence strength, or any echo-chamber detection**. Academic tools fake credibility by **restricting to journals** (the filter we're abandoning). Formal methods (GRADE, weight-of-evidence) get it right but assume human reviewers. POLARIS already owns the hardest substrate — per-sentence `[#ev:id:start-end]` + `strict_verify`. The lead = extend that to **provenance + credibility-weight + independent-origin-count + certainty**, domain-conditional, independence-aware, that actually drives composition.

## Three unsolved problems = POLARIS's lead
1. Disclosed **per-claim credibility weight** (open whitespace).
2. **Source-independence / echo-chamber collapse** — 50 sites copying one press release count as ~1 (nobody deploys this; biggest opening).
3. Contested-topic **weight-and-disclose-with-forewarning** (the vax case: louder side = weaker side, shown honestly; abstain rather than fabricate balance).

## Target architecture (mapped onto EXISTING code where possible)
`retrieve(all-types) → score(two-axis, domain-conditional) → independence-collapse → claim-graph(cluster+contradiction) → aggregate-by-weight → compose-with-forewarning → per-claim disclose`. Plus (Codex-required additions): article+claim-level scoring, temporal/supersession, calibration/audit metrics, dissent-recall retrieval, additive final-verifier strengthening (NLI/entailment), multi-position both-sides UX. Reuses: `authority/` model, `tier_classifier`, `corroboration_count`, conflict detectors, voter/arbiter, `[#ev]` token.

## Non-negotiables
Faithfulness gates (strict_verify / 4-role D8 / provenance / two-family / corpus_approval) PRESERVED and only ever STRENGTHENED. Domain-aware (clinical keeps the high bar; news must not outweigh absence of clinical evidence). Sovereign. No single external rater hardwired (capture defense).

## Status
- Phase 1 (frontier research, 5 streams + synthesis): DONE; Codex completeness gate = NEEDS_ADDITIONS, corrections folded into the doc (§6).
- Phase 2 (line-by-line pipeline investigation + full phased plan): IN PROGRESS (Workflow B).
- Next: Codex **binding** plan-gate → operator approval → phased, Codex-gated PR delivery. **No code until the operator approves the plan.**

Relates to #1146 (journal-only removed) and #1147 (legal-OA fetch recovery).
