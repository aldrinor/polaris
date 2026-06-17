# BREADTH FIX must ALSO cover QUESTION-RESPONSIVENESS (proven by the Q78 §-1.1 audit, 2026-06-16)

The Q78 audit (w8ndhzmom) result: **faithfulness PASS** (0 fabrications, ~90% verified, Claude+Codex agree) but **BEAT-BOTH FAIL** — Q78 loses to BOTH gpt_5_5_pro and gemini_3_1_pro on **question-responsiveness, completeness, and structure**, NOT on faithfulness.

Root: the Q78 question had 3 explicit parts — (1) PD warning signs BY STAGE; (2) which signs alert FAMILY MEMBERS to intervene / seek help; (3) for post-DBS patients, DAILY-LIFE adjustments + support strategies. POLARIS rendered generic clinical sections (Efficacy / Mechanism / Long-term Outcomes / Safety / Population Subgroups) — it did NOT directly answer the 3 asks. So the report is faithful but OFF-TARGET, and thin (13 sources).

## Therefore the breadth/contract/render fix (workflow w25o8pmva → build) MUST cover THREE things, not two:
1. **Multi-citation per claim** — surface the whole verified corroborating basket (already-computed), not 1 source.
2. **Broaden past the contract** — surface high-weight non-contract sources (the 437 dropped), breadth EMERGES from honest weighting, no forced number.
3. **QUESTION-RESPONSIVE contract** — the required_entities / sections must be DERIVED FROM THE QUESTION's actual sub-parts (what the user asked), not a generic domain template. The report must directly answer the asks (e.g. for Q78: warning-signs-by-stage, family-intervention-cues, post-DBS-daily-life), then support each with the weighted multi-citation evidence.

## Faithfulness guard (unchanged): never relax strict_verify / NLI / 4-role / span-grounding / the floor; every citation is a verified real support; responsiveness restructures WHAT is asked/answered, it never fabricates an answer the evidence doesn't support (an unanswerable sub-part is disclosed as a gap, not invented).

ACTION: when BREADTH_FIX_DESIGN.md lands, verify it covers all THREE. If it covers only multi-citation + broaden, EXTEND the design (+ re-gate Codex) to add the question-responsive contract before building.

## ADD (proven by the Q72 §-1.1 audit, 2026-06-16): the render fix must ALSO kill REDUNDANCY + preserve HEDGING
Q72 audit: 414/414 VERIFIED, 0 fabrications (faithfulness PASS) — but BEAT-BOTH FAIL because the generator RESTATES the same ~30 sources' propositions 13-20x each to FILL the required sections (the brynjolfsson trio restated ~13x, autor ~20x, acemoglu ~14x). Every restatement is VERIFIED-but-redundant (extractive paraphrase, no new fact) -> the report is verbose + low-information. Codex also flagged ~10 OVER-CERTAINTY claims (a theoretical model's "always" stated as a settled general finding; ev_426 employment-share variable-label looseness).
=> The render/contract fix MUST therefore also:
4. ANTI-REDUNDANCY: a claim/proposition is rendered ONCE with its whole multi-citation basket; do NOT reword the same proposition across sections to fill space. Breadth (more distinct sources/propositions) is the structural cure; add a de-dup-by-proposition guard at render so the same atomic claim is not restated N times.
5. HEDGE PRESERVATION: when a source frames a finding as conditional/model-based/scenario/suggestive, the rendered claim must KEEP that framing (no association->causal or "supports"->"established" upgrade). This is faithfulness-adjacent (over-certainty is a soft faithfulness defect) and must never be relaxed.
Both 4 and 5 are the SAME contract/render layer as breadth+responsiveness; fold them into the one render fix.

## ADVISOR RELAUNCH BLOCKERS (2026-06-16) — all BLOCK the 5-run relaunch, Codex diff-gate won't catch them
1. **Item-2 weighted_enrichment.py is the REAL fix and is REQUIRED.** Q78 was a SUCCESS-path run (pass completed, 485 weighted+basketed) yet ~13 rendered → it is the STRUCTURAL FUNNEL (render universe = 5 contract entities + planner picks; 437 unbound sources never OFFERED to any section), NOT the degrade path. Death-fix + item-1 alone → relaunch REPRODUCES the collapse. Do not let a later loop tick rationalize "1b parallelize → baskets render → breadth back on" — that only fixes the degrade, not the funnel.
2. **Insertion point = AFTER credibility_analysis resolved (~:6707), NOT :6482.** At :6482 credibility_analysis is None → select_unbound_supports_by_weight returns [] → no section → byte-identical → breadth SILENTLY not fixed while every test+gate stays GREEN (the arch005 green-gate-but-broken trap). Checklist item for the build + the combined gate.
3. **Negative-control test is MANDATORY (design §4 assertion 3).** "Breadth up" alone passes even if a gate were relaxed. The test must prove breadth-up AND faithfulness-identical (the 3 negative-control rows — UNSUPPORTED member, numeric-fabricated, content-mismatch — render NOWHERE).
4. **Flag must be in the DEPLOYED run slate + behaviorally proven.** Committed ≠ wired (arch005). Preflight canary must show MORE distinct verified sources actually surface, not just "PG_BREADTH_ENRICHMENT_ENABLED is set".
5. **Resumed runs MUST re-generate with the flag on, NOT reuse pre-breadth postgen.** ITEM-5 PG_RESUME_REUSE_POSTGEN default-OFF ensures this; deploy recipe corrected (the stale "Q72/Q78 reuse postgen cheap" note removed). Reusing old drafts → breadth inert → wasted spend.
6. **Death-fix gate:** fold into the FINAL COMBINED diff gate; do NOT burn a separate iteration (Codex already confirmed content correct + faithfulness-neutral; only the git-tracking artifact remained and it is fixed).
