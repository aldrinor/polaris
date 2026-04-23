# Claude's Strategic Path to Highest Quality

## The honest question

Can POLARIS beat ChatGPT DR + Gemini DR on all 7 dimensions,
autonomously, for the tirzepatide/T2D query? My honest answer:
**yes, but not by V29. Achievable by V30-V31 with focused
architectural work; NOT achievable with more incremental prompt/
selector tweaks.**

## Why V29 A+B alone won't get to 7/7

The gate_verdict.md V29 candidates (A+B = selector-level primary
reservation + generator injection) are **necessary but not
sufficient**. They fix the "primary in corpus but not in report"
defect which controls Dims 1, 4, 5. But Dim 7 (Narrative depth) has
a **different root cause**: even when the Thomas clamp paper IS
cited, V28's Mechanism section synthesizes from reviews rather than
extracting the clamp findings. M-47's regen with field-context
validator couldn't coerce the generator to quote M-value=63% from
the direct_quote. That's a prompt-architecture limitation, not a
selection limitation.

So V29 = A+B would likely yield: 4 BB + 3 BO + 0 LB (lifts Dim 1/4/5
to at least BEAT_ONE, keeps Dim 7 at LOSE_BOTH). Not 7/7.

## Where POLARIS has genuine structural advantages

These dimensions POLARIS already wins and can hold at BEAT_BOTH:
- **Regulatory** (4-jurisdiction coverage — no competitor does this)
- **Jurisdictional** (specific EMA pediatric / NICE TA924 content)
- **Contradictions** (14-item enumeration — competitors don't quantify)
- **Transparency** (per-sentence [ev_id] — competitors can't match)

These are not 4 separate dimensions to win; they're ONE structural
advantage (evidence-bound provenance + jurisdictional retrieval)
that happens to pay off across 2-3 measured dims. POLARIS's
transparency win is architectural, not tunable.

## Where POLARIS faces genuine structural headwinds

- **Primary-trial precision**: competitors quote NEJM/Lancet tables
  verbatim because they have editorial curation. POLARIS has strict_
  verify which PREVENTS fabrication but also REQUIRES the primary
  publication's direct_quote to contain the target number. Paywalled
  PDFs defeat this.
- **Narrative pharmacological depth**: Gemini's mechanism section
  reads like a textbook chapter because Gemini pulled from specific
  pharmacology reviews + primary pharmacokinetic papers. POLARIS
  uses whatever the retriever returns + relevance-ranks it. The
  retrieval layer doesn't know which review is the "Thieme connect"
  gold-standard review vs a generic StatPearls entry.

These aren't unfixable — but they require **corpus-quality over
quantity** discipline and a **two-stage generation** architecture.

## My recommended plan: Strategy β (architectural pipeline rewrite)

### V29: Selector primary-preservation (foundation)

V29 scope = gate_verdict candidates A + B + D:
- **A**: Selector HARD RESERVES anchor-matched M-42e primary rows,
  with NO tier-proportional override. If SURPASS-4 Del Prato is in
  live_corpus, it MUST be in selected_rows. Cap at 11 reservations
  (= number of anchors).
- **B**: Generator pulls anchor-matched primaries from live_corpus
  into the appropriate section's ev_ids IF the selector didn't
  pass them through. Redundant with A but catches selector bugs.
- **D**: Trial Summary table cell correction — either extract from
  direct_quote with M-42b deterministic logic OR drop the table
  entirely. No more "SURPASS-5 baseline 7.0%" errors.

**Expected V29 outcome**: 4 BEAT_BOTH + 2 BEAT_ONE + 1 LOSE_BOTH.
Structural lift on Dims 1, 4, 5. Narrative (Dim 7) stays LOSE_BOTH.

Cost: ~6 hours engineering + 1 sweep cycle (~3h). Low risk — V29 is
a narrow selector fix that can't make anything worse than V28.

### V30: Two-stage generator architecture (the real lift)

V30 scope: rewrite `generate_multi_section_report` as two-stage.

- **Stage A (primary-trial skeleton)**: outline cites ONLY pivotal
  primary publications with hard contract: each section's prose
  must quote at least 3 ETDs + their uncertainty from the primary
  direct_quote, with inline [ev_X] citations. If a primary fails
  strict_verify, **drop the section** rather than ship meta-analysis
  substitutes. Honest-under-failure > padded-with-derivatives.
- **Stage B (enrichment)**: expand with meta-analyses for effect-
  pooling, reviews for mechanism, regulatory for context. Uses
  existing M-42 bundle.
- **Mechanism-specific enrichment**: pull pharmacokinetic review +
  clamp study side-by-side; prompt requires M-value / half-life /
  receptor-affinity / clamp-cohort-N inline with citation. This is
  essentially M-47 but at generation time, not validation time.

**Expected V30 outcome**: 5-6 BEAT_BOTH + 1-2 BEAT_ONE + 0 LOSE_BOTH.
Lifts Dim 7 (Narrative) from LOSE_BOTH to BEAT_ONE at minimum,
possibly BEAT_BOTH if Mechanism extraction works.

Cost: 2-3 days engineering (new stage-aware generator) + 1 sweep.
Medium risk — V30 re-architects the generator stage, touches many
existing tests.

### V31: Ship OR push to 7/7

If V30 lands at 5-6 BB, V31 closes the remaining gaps:
- Trial Summary table specifically: pull from structured registries
  (ClinicalTrials.gov result_reporting) instead of PDF abstracts.
  Different corpus source yields structured data directly.
- M-47 final closure: allow primary-source quote BLOCK inclusion in
  Mechanism section (not just referenced) — POLARIS becomes a
  meta-review that reads the Gemini-style pharmacology section.

**V31 expected outcome**: 7/7 BEAT_BOTH.

Cost: 1 day + 1 sweep.

## Why NOT Strategy α (narrow engineering only)

V29 A+B alone stops at 4+3+0. That's better than V27 (1+4+2) but
not SHIPPABLE. If the goal is honest 7/7, V29 A+B is necessary
scaffolding; it's not the destination.

## Why NOT Strategy γ (relax strict_verify)

Strict_verify is POLARIS's core differentiator. Relaxing it to
gain narrative depth trades away Dim 6 (Contradictions) + Dim 7
(transparency). Net-zero or negative at best. DO NOT.

## Why NOT Strategy δ (test different question)

Not a bad idea in isolation, but it's orthogonal to the architectural
gap. Running V28 on materials chemistry would likely show a
different failure pattern, not the same one. Use-the-time-for-
architecture is better ROI.

## Why NOT Strategy ε (ship V28)

V28 regressed net dimensions vs V27. Shipping a regression is not
"quality focus"; it's accepting the autoloop failed to converge.
Also: V28 trial summary table is factually wrong (SURPASS-5
baseline 7.0% is incorrect). Shipping wrong numbers is worse than
shipping nothing.

## My single-most-impactful next action (V29 scope)

**Selector hard-reserves anchor-matched primary papers (candidate A
from gate_verdict).**

Concrete implementation: in `src/polaris_graph/retrieval/
evidence_selector.py`, after tier-balancing, post-process the
selected list: for each anchor in `primary_trial_anchors`, find
the best anchor-matched primary in live_corpus (not just in
selected_rows), and INSERT it into selected_rows if absent. Cap at
11 insertions. This is a 50-line change + tests + Codex audit —
ships in 1 day, lifts Dim 1 from LOSE_BOTH to BEAT_ONE, also
enables M-44 injection and M-50 subsection coverage to target
trials (SURPASS-2/4/CVOT/SURMOUNT-2).

Alone it doesn't hit 7/7. But it's a cheap, non-controversial,
necessary foundation. Ship it in V29, then the V30 generator
architecture pays off.

## Honest risk acknowledgement

The "two-stage generator" plan in V30 is significant re-architecture.
It touches `multi_section_generator.py` (~3500 lines) substantially
— outline → section → strict_verify → assembly flow gets a new
Stage A gate before outline. Previous refactors of this file
(M-42b, M-44, M-47, M-50) added ~1500 lines without a full
rewrite; V30 would be harder to make backwards-compatible. If a
V30 code audit surfaces blocker-class issues, V30 could slip by
a cycle.

Alternative if V30 slips: V30 = Strategy α++ (A+B+D from V29 + a
Mechanism-section-specific direct_quote injection for M-47 field
extraction). Smaller lift. Projected 5 BB + 2 BO + 0 LB —
still not 7/7 but closer than V28.

## Cost estimate

- V29: 6h eng + 3h sweep + $0.05 = ~10h / $5
- V30: 2-3d eng + 3h sweep + $0.05 = ~3d / $5
- V31: 1d eng + 3h sweep + $0.05 = ~1d / $5

Total: ~5 days engineering + 3 sweep cycles + ~$15 budget.

Budget check: V25→V28 consumed ~18h session wall-clock + ~$20
aggregate. V29-V31 is feasible within a ~80h aggregate session
budget. The §7 24h-per-cycle cap is not binding at this tempo.

## Bottom line

Ship the V29 foundation (A + B + D), then commit 2-3 days to V30
two-stage architecture, then V31 ships 7/7. Do NOT try to hit 7/7
in V29 with prompt/selector tweaks alone — the Mechanism-section
extraction problem is architectural, not prompt-tunable.

Codex's parallel strategic brief is running at
`outputs/codex_findings/v28_strategic_path/findings.md`. Cross-
review on landing; user decides scope.
