---
name: flat-result-diagnosis-2026-07-22
description: "Why the 7-lever task-72 RACE draw was flat (0.4962); the cleaner-keeps-well-formed-tables correction; instruction-gated eligibility approved"
metadata:
  node_type: memory
  type: project
  originSessionId: 21e87760-8436-4090-870d-99ef2121882e
---

**2026-07-22 — Sol+Fable diagnosis of the flat 7-lever RACE result (task 72, full arm, K3 generator, draw 1 = 0.4962).**

Per-dimension: Insight 0.5079 (w.32) ✅ beat ref, Comp 0.5072 (w.29) ✅ beat ref, Instruction-Following 0.4821 (w.25) ❌, Readability 0.4690 (w.14) ❌. Two up, two down → net flat. The IF+Read losses (~-0.0088 weighted) were ~2× the Insight+Comp gains (~+0.0046).

**ROOT CAUSES (Fable-verified against real judged artifacts):**
1. **Explicit "only" instruction violated.** Task-72 prompt: "only cites high-quality, English-language journal articles" (criteria give exclusivity ~0.25 of IF mass). Our §-1.3 weight-don't-filter kept all 997 sources → judged body cites ~42% non-journal (OECD 18x, ILO 8x, World Bank 6x, IMF 6x, working papers, blogs, preprints) and even TELLS the judge evidence is "secondary/anecdotal/unclassified." Biggest single loss.
2. **4IR + industry miss.** Prompt asks AI as "Fourth Industrial Revolution" driver + "various industries." Judged text: 0 "4IR"/"Fourth Industrial Revolution", no sectoral section — though a "Sectoral Disruptions" section was PLANNED in the outline (11 sections) but never rendered (a real render bug). Reference has 4IR framing + a dedicated sectoral section.
3. **Prose quality (Readability).** Judged text 67% bullets, only **17 bold vs reference's 119**; headline stats repeated 4-7x (40%, 18%, 80%, 19%, 1.8%). Repetition-guard + coverage-spine were OFF.

**CRITICAL CORRECTION to [[race-scoring-mechanics]]:** the cleaner does NOT universally strip tables. The task-72 REFERENCE kept **18 table rows** through cleaning. Ours (109 raw) → 0 in judged text because MALFORMED (multiline cells break markdown) + repetitive. Tables CAN help if well-formed + non-repetitive + validated on the cleaned output. Length is NOT the issue: judged 9,080 words vs ref 9,029 (parity); raw 14,384 shrank 41% under cleaning vs ref 17%.

**Levers that WORK (keep):** facet packs (1024/1024 coverage), basket synthesis, narrative attribution, route-all → the Insight/Comp wins. Table levers got ZERO judged credit (stripped) — not proven bad, just malformed.

**OPERATOR DECISION (2026-07-22):** approved **instruction-gated eligibility** — when the PROMPT states a hard "only/exclusive" source constraint, restrict the judged body + bibliography to eligible sources; retain everything internally + disclose in a sidecar. Doctrine-legal: master_plan:95 pre-authorizes "explicit user journal-only mode"; §-1.3 bans NUMBER-forcing, not honoring explicit instructions. NOT the banned faith-ghost (that's faithfulness/NLI). LOAD-BEARING precondition: metadata recovery/backfill (only 5/139 have venue metadata) — else it guts the report. Must run at composition-PLANNING time, not a post-gen strip.

**BUILD PLAN (Fable-ranked, all complementary → build all then measure once per [[build-all-then-measure-rule]]):** (1) narrative consolidation [Read], (2) semantic coverage obligations + fix vanished-section render [IF+Comp], (3) instruction-gated eligibility + backfill [IF], (4) cleaned-output acceptance guard [Read/measurement]. No completed OFF-control arm yet → causal attribution still unproven; the same-harness `current` arm must run alongside the treatment.
