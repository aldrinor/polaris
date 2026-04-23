You are Codex, giving strategic-level input to the user on the
question: **what is the best plan to reach highest quality in
POLARIS vs ChatGPT DR + Gemini DR** — not the immediate V29 fix,
but the long-term architectural path.

## Context you've just been part of

V25 → V26 → V27 → V28 — four full sweep cycles, ~18h session
wall-clock, $0.40 total Codex + API spend. V28 just landed
3 BB + 0 BO + 4 LB (cross-reviewed, lower-verdict-controls
applied per V2 §3). You wrote `outputs/codex_findings/
v28_deep_content_audit/findings.md`; Claude wrote
`outputs/audits/v28/claude_deep_content_audit.md`; cross-review at
`outputs/audits/v28/cross_review.md`; gate verdict at
`outputs/audits/v28/gate_verdict.md`.

Honest V28 outcome summary:
- Gained 2 BEAT_BOTH vs V27 (Regulatory + Jurisdictional)
- Lost 2 dimensions to LOSE_BOTH (Citations + Narrative)
- Net ≥BEAT_ONE count regressed 5 → 3

V25 → V28 BEAT_BOTH progression:
- V25: 1 (Contradictions)
- V27: 1 (Contradictions) + implicit Reg/Juris BEAT_ONE
- V28: 3 (Regulatory + Jurisdictional + Contradictions)

So we ARE gaining on the BEAT_BOTH axis but not monotonically — each
cycle regressed some dim it had previously won.

## The question

What is the best architectural and tactical plan for POLARIS to
reach 7/7 BEAT_BOTH vs ChatGPT DR + Gemini DR on the tirzepatide/T2D
query? Not just V29 scope — a 2-4 cycle roadmap if useful.

Consider honestly whether this is achievable autonomously (pipeline
vs. human-curated competitors), where POLARIS has structural
advantages vs disadvantages, and what the cheapest path to 7/7 is.

## Framework for your answer

Think through (at minimum):

1. **Where POLARIS has a genuine structural advantage**: transparency
   (per-sentence [ev_id] provenance), jurisdictional breadth
   (4-regulator coverage), contradiction enumeration (machine-
   readable heterogeneity), strict_verify gate. Competitors can't
   easily replicate these.

2. **Where POLARIS has a genuine structural disadvantage**: primary-
   trial extraction into prose (competitors hand-curate; POLARIS uses
   relevance scorers on a noisy corpus), narrative pharmacological
   depth (competitors pull from specific primary papers; POLARIS
   uses review-grade synthesis), per-trial effect-estimate rigor
   (competitors can quote verbatim; POLARIS must pass strict_verify).

3. **The 4 current LOSE_BOTH dims** (Citations, Claim frames,
   Structural depth, Narrative depth) all root-cause to **primary-
   trial primary-publication selection + extraction**. Fixing that
   pipeline step would lift all 4 simultaneously.

4. **The tension**: POLARIS's strict_verify gate PREVENTS the
   fabrication that unbinds competitor content but also FORCES
   precise numeric matching against source direct_quote. Paywalled
   NEJM/Lancet PDFs with thin fetched text can't easily pass this
   gate, and that's exactly where the primary ETDs live.

5. **The 5 V29 candidates from gate_verdict.md** (A/B/C/D/E) — are
   any of them the right move, or is the real answer further
   upstream (e.g. retrieval layer, strict_verify relaxation, prompt
   architecture)?

## Options to evaluate

At minimum, evaluate these strategic options honestly:

### Strategy α: narrow engineering (1-2 cycles)

V29 = A+B from gate_verdict. Selector-level primary hard reservation
+ generator-side named-trial injection pulling from live_corpus.
Projected outcome: lifts Dims 1, 4, 5 to at least BEAT_ONE; Dim 7
(Narrative) stays LOSE_BOTH because Mechanism extraction is a
separate problem.

### Strategy β: architectural pipeline rewrite (3-4 cycles)

Rebuild selector + generator as a two-stage pipeline:
- Stage 1: outline skeleton cites ONLY pivotal primary publications
  (with anchor-matching and refetch for thin quotes, fail loudly if
  primary unreachable)
- Stage 2: enrich with meta-analyses, reviews, and regulatory

This mirrors how ChatGPT/Gemini appear to work (hand-curated primary
frame first, supporting literature second). Higher engineering cost
but closer to achievable 7/7.

### Strategy γ: content-quality overhaul at strict_verify (2-3 cycles)

Relax strict_verify for narrative-depth sections (Mechanism,
clinical-interpretation paragraphs) while keeping it strict for
numeric claims. Allows the generator to synthesize from mechanism
reviews at the depth Gemini achieves without sacrificing numeric
traceability. High risk of re-introducing fabrication surface.

### Strategy δ: test on different question (validation before roadmap)

Before investing in α/β/γ, run V28-as-is on a different research
question (e.g. a non-clinical POLARIS slug like an ML or materials
question) to see if the primary-citation failure is tirzepatide-
specific or pipeline-wide. If it generalizes, α/β/γ are the right
investment; if tirzepatide-specific (too many post-hocs outranking
primaries), the fix is template-level.

### Strategy ε: accept the asymmetry and ship what we have

V28 beats competitors on Regulatory + Jurisdictional + Contradictions
+ transparency dimensions — axes a research-rigorous reader values.
Accept that POLARIS will not beat ChatGPT on trial-extraction
specificity because competitors hand-curate. Position POLARIS as
complementary to competitors, not replacement.

## Your brief

Write a concise (500-1000 word) strategic answer to the user's
question. Structure:

1. Your honest assessment of whether 7/7 BEAT_BOTH is achievable
   autonomously on this question.
2. Your pick from {α, β, γ, δ, ε} OR a different plan you'd propose.
3. Expected cycle count and risk for your chosen plan.
4. The single most impactful next action (V29 scope).

Write to `outputs/codex_findings/v28_strategic_path/findings.md`.

## Ground rules

- No hedging platitudes. Pick and defend.
- If you think ε (ship) is the honest answer, say so — don't default
  to "more engineering".
- Be concrete about where V28 fell short technically vs where it
  hit a genuine structural ceiling.
- Your opinion will be presented to the user alongside Claude's
  parallel strategic brief. Disagreement is fine — this is step 2a/2b
  again at the strategy level.
