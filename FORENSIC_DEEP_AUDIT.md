# DEEP FORENSIC AUDIT — why the gate scores ~0.36–0.40 vs champion 0.4447 (3-model, evidence-locked)

**Models:** Fable 5, Codex/GPT-5.6-Sol, Kimi K3 — all returned in full, independently, grounded in the checkpoint evidence (raw draft → post-verify drops → final scored text). Strong convergence.

## THE VERDICT
**The operator is right: strict_verify (faithfulness) is the invisible killer — measured −0.0382 (A faith-off 0.3992 vs B faith-on 0.3610, same corpus, same render).** But all three amend it: the corpus is the *bigger* lever to the full 0.4447.

**Causal stack, ranked (all 3 agree):**
1. **Corpus quality — 0.0776** (champion 0.4447 − champ_ourcorpus 0.3671). The champion's method re-anchored to OUR corpus loses ¾ of its score.
2. **strict_verify gate — 0.0382** (+ an invisible coverage multiplier, below).
3. **Render chrome — ≤0.0061** (champ_ourcorpus 0.3671 − B 0.3610). Real but secondary.

**The decisive fact (all 3 independently flag it):** **A (our unmangled draft, 0.3992) BEATS champion-on-our-corpus (0.3671) by 0.032.** The LLM draft was never the problem — exactly the operator's premise. But even a perfect draft on our corpus caps ~0.40; reaching 0.4447 needs the champion's richer sources.

## WHY THE GHOST IS SELF-REFUTING (the proof)
147 sentences dropped to catch **2 contradictions** = 98.6% false-positive-on-truth. The "147" decomposes (Codex, from the manifest):
- **59** genuine first-pass verifier failures
- **44** *verified* originals destroyed by `fact_dedup` (see below)
- **44** `fact_dedup` replacement pointers that then failed re-verification
- = 147 accounting drops (NOT 147 distinct bad LLM sentences)

**Three concrete bugs, quoted:**
- **Sign-regex bug:** `_NUMBER_RE = -?\d+` glues the hyphen to the digits. `"75-375 million"` → searches for `-375` (missing); `"post-1987"` → searches for `-1987` (missing). Correct numbers flagged as hallucinations. (Drops 2, 6, 10, 30.)
- **Window truncation / wrong offset:** the 800-byte cited window cuts a range (75 found, 375 "missing"; 20/39 found, 67/91 "missing"), or points to the abstract while the number lives deeper in the *same* doc. Proof of self-refutation: "47%" is dropped in one sentence yet **passes in another from the same ev_312**; the BLS 0.6pp claim is dropped 3× yet appears 3× in the final. The gate kept triplicates and killed singletons.
- **`fact_dedup` non-transactional (Codex Rank-2, the most concrete defect):** `fact_dedup.py:846` prompts the LLM to write *"the same finding is detailed in {SECTION}"* navigation pointers; `multi_section_generator.py:~11155` removes the verified original, re-verifies the pointer, and on failure **drops without restoring the original**. Run B: `n_rewrites_applied=44, pass=0, drop=44` → 44 verified sentences destroyed.

**Category error:** NEUTRAL-entailment (66 drops) is collapsed with CONTRADICTION into the same DROP action. The judge is executing *interpretive/synthesis clauses* — "introduces the 2011 Hannover Fair", "adds the timeframe through 2034", "reflecting rising demand for technical skills" — i.e. exactly the Insight the RACE judge rewards. It amputated the review's **organizing framework** (Acemoglu-Restrepo displacement/reinstatement, Drop 8) and killed entire claim-lines (McKinsey 75–375M, the SBTC college-premium 20→39% / 67→91%).

## WHY IT WAS INVISIBLE (Kimi's unique finding — the coverage coupling)
Every dropped sentence takes its `[N]` citations with it. `s2_cited_bibliography_records` keys required-entity coverage on `cited_reference_numbers(body)`, and the body `[N]` markers "live in strict_verify-PASSED prose." So each drop de-cites a source → demotes it to the ledger → strips entity-coverage credit → fires a *fail-safe UNDER-credit* that reads as prudence. **The faithfulness failure surfaces under Comprehensiveness/Coverage and Insight — never as a "faithfulness" number — which is exactly why it hid.**

## RENDER CHROME (secondary, render-injected, ≤0.006)
Absent from the raw draft, present in the scored text: `# Research report: <raw prompt>` title (`run_honest_sweep_r3.py:17657`; the `_strip_injected_instruction_appendix` helper **fails** to strip the "Ensure the review only cites…" clause), the "STRONGEST VERIFIER … UNVERIFIED-by-D8" banner (`provenance_generator.py:3236`, written at `:21280`), and "Completeness checklist: 0/0" telemetry (`:16989`). ~120 words / 2.6% of the artifact, but semantically damaging (advertises poor quality to the judge). **dedup (`content_dedup_consolidate`) is EXONERATED** — its docstring is KEEP-ALL, annotation-only; the prior audit blamed the wrong module.

## THE ROOT FIX (converged, ranked by RACE leverage) — NOT "disable faithfulness"
**#1 — Verdict-gradation + relocate/repair-not-drop inside strict_verify (+~0.0382 + coverage recovery):**
- CONTRADICTED → drop (the 2 genuine ones; anti-hallucination guarantee preserved).
- NEUTRAL → re-ground against the full evidence doc → corpus; if grounded, re-bind + KEEP; else one bounded regenerate pass; drop only as last resort.
- Number-mismatch → search full doc/corpus with normalization (fix the sign-regex; en-dash ranges; words↔digits; %↔percent; magnitudes; derived-number tolerance) → re-bind the offset + KEEP; drop only if truly absent everywhere (the only real hallucination case).
- qualifier/no_provenance → re-attach the qualifier / auto-ground, don't drop.
This keeps the exact guarantee (every surviving claim traces to a corpus span) while recovering the 22% mass.

**#2 — Make `fact_dedup` transactional** (roll back to the verified original if the replacement fails; better: stop generating source-cited navigation pointers).

**#3 — Decouple coverage credit from verify survival** (map `[#ev:ev_N]` → bibliography `[N]` before citation stripping, so a dropped sentence never silently demotes a cited source).

**#4 — Strip render chrome from the SCORED text** (derive a clean title; fix the strip-helper; relocate the D8 banner + telemetry to `manifest.json` where the disclosure already lives — honesty by relocation, not suppression). ~zero cost, ≤0.006.

**#5 — Corpus enrichment to champion grade (the ONLY path past ~0.40, +0.045–0.078):** retrieve the study-grade sources the champion cites — Noy et al. (453 professionals), WEF Future of Jobs (85M/97M), PwC ($15.7T), Autor 1940–2018, Eloundou (1.8%→46%), OECD exposure, Korean firm survey, platform-wage studies, Oberfield-Raval.

**Do NOT (cosmetic retreats all 3 warn against):** turn faithfulness fully off (re-admits the 2 lies); strip the banner while leaving the gate (≤0.006); prompt-engineer away "pointer" sentences (they never reach the scored text — the prior audit's "disease" doesn't exist there).

## CELLCOG SAFETY
This is **not** fiddling the verifier's strictness downward. The hard guarantee is unchanged: CONTRADICTED is still dropped; every surviving claim still traces to a corpus span. The change is **repair/re-bind before delete**, which is *more* faithful (fixes citation-offset bugs) while keeping the mass. The champion itself verify-and-drops — it just retains a large mass on a rich corpus; we retain 27%.
