# Codex DIFF review — I-ready-006 (#1082) query-complexity router — ITER 5 (last before §8.3.1 cap)

## iter-4 was REQUEST_CHANGES (2 P1, 1 P2) — ALL FIXED, STRUCTURALLY (this is iter-5):
- **P1-1 cohort-prevalence:** "population of children WITH asthma / adults WITH COPD / people WITH
  migraine" routed simple. FIX (per your "without enumerating disease names" blocker): a STRUCTURAL
  `_COHORT_PREVALENCE` regex — `(population|number|prevalence|proportion|...) of <…> (with|who have|
  taking|using|on|diagnosed|suffering|affected|prescribed|treated)` ⇒ complex. Catches the whole
  class; "population of Canada?" (no cohort qualifier) stays simple. 4 cohort reprobes now complex.
- **P1-2 investment-judgment:** "Is Tesla stock overvalued? / a buy?" routed simple. FIX: added
  overvalued/undervalued/fair-value/buy/sell/hold/bullish/bearish/price-target/"should I buy" to
  `_COMPLEX_INTENT`. 3 reprobes now complex; "Apple revenue in 2023" stays simple.
- **P2 (over-serve):** "France?"/"Canada?" trailing-`?` broke the entity regex → only 0.70. FIX:
  strip trailing punctuation; civic queries now reach 0.85 and pass the 0.80 gate.

---

# Codex DIFF review — I-ready-006 (#1082) query-complexity router — ITER 1 (context)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

You APPROVED the brief (`.codex/I-ready-006/brief.md`): classifier_choice=deterministic_heuristic,
rightsizing_scope=cap_plus_adequacy, defer_split_adjustment=yes, + 4 P2s (all incorporated below).
Diff: `.codex/I-ready-006/codex_diff.patch` (vs base bot/I-ready-004).

## iter-1 diff was REQUEST_CHANGES (1 P1, 1 P2) — BOTH FIXED (this is the iter-2 diff):
- **P1-1 (clinical-safety, the important one):** clinical outcome/safety factual-RATE queries
  ("mortality rate of Semaglutide", "incidence of Guillain-Barré after Shingrix") were classifying
  high-confidence simple → reduced cap + 1-source adequacy → under-served. FIX: a `_CLINICAL_CONTENT`
  guard in complexity_router.py is checked FIRST — ANY clinical/medical/epidemiology/safety term
  (mortality/incidence/prevalence/survival/adverse/drug/disease/vaccine/dose/clinical + drug-INN
  suffixes -mab/-nib/-gliptin/-glutide/-statin/-sartan/-pril/... ) ⇒ `complex` 0.9 BEFORE the simple
  branch. Erring toward complex is the SAFE direction. 7 clinical probes (incl. both of yours) now
  assert complex; the simple stock/GDP/capital cases still assert simple.
- **P2-1 (fail-open):** the env parses (PG_COMPLEXITY_MIN_CONFIDENCE / PG_SIMPLE_FETCH_CAP) are now
  INSIDE the routing try/except — a malformed value falls back to the FULL path (never aborts
  error_unexpected). A source-check test locks the fail-open except.

## iter-2 diff was REQUEST_CHANGES (continuing P1) — FIXED (this is the iter-3 diff):
- The clinical DENYLIST still missed "death" / "fatality" / "GBS" / "COVID" / "Shingrix" (a denylist
  can never be complete). FIX: FLIP THE POLARITY — "simple" now REQUIRES a positive `_SAFE_FACTUAL_CUE`
  ALLOWLIST (financial / economic / corporate / geographic / civic: stock price / market cap / revenue
  / GDP / inflation rate / population / capital of / founded / CEO / ...). A query with NO safe cue —
  incl. "What is the death rate from COVID-19?", "rate of GBS after Shingrix?", "fatality rate of
  Ebola?" — FAILS OPEN to complex REGARDLESS of whether the denylist names the disease. Generic
  "rate of" / "how many" are NO LONGER simple cues (they can be a clinical outcome rate). The
  `_CLINICAL_CONTENT` guard remains as defense-in-depth. 11 clinical/outcome probes (incl. all of
  yours) now assert complex; the financial/GDP/capital cases still assert simple.

## iter-3 diff was REQUEST_CHANGES (2 P1, 1 P2) — ALL FIXED (this is the iter-4 diff):
- **P1-1 (clinical, continuing):** "population with obesity / taking statins / using Ozempic / with
  long COVID" routed simple. Root causes: (a) the safe allowlist's bare `population` allowed
  "population WITH a disease"; (b) the `_CLINICAL_CONTENT` stems (`obes`/`diabet`/`statin`) were
  `\b`-bounded so they did NOT match "obesity"/"diabetes"/"statins". FIX: tightened the allowlist to
  `population of` (civic only); rewrote the clinical guard to PREFIX-match (`\b(?:stem)\w*`) so
  obesity/diabetes/statins match, + added covid/long-covid/ebola/measles/sepsis/stroke/guillain/gbs +
  common drug brand names. 5 epidemiology reprobes now assert complex.
- **P1-2 (due-diligence):** "Apple revenue drivers and competitive risks", "Microsoft revenue
  exposure to OpenAI", "Apple profit risk from China tariffs" routed simple. FIX: added
  driver/risk/exposure/competiti/outlook/threat/tariff/"next N years"/scenario/... to
  `_COMPLEX_INTENT`. 4 due-diligence reprobes now assert complex; "Apple revenue in 2023" stays simple.
- **P2-1 (override drop):** the simple adequacy override was only on the FIRST adequacy check;
  the expansion/deepener/agentic recomputes (now lines ~2611/2711/2858) dropped it → a simple-routed
  run reverted to clinical defaults + aborted. FIX: all 4 assess_corpus_adequacy calls now pass the
  override; a source-check test asserts overrides >= adequacy-call-sites.

## What the diff does
**New module** `src/polaris_graph/nodes/complexity_router.py` — deterministic, fail-open
`classify_complexity(question) -> ComplexityDecision(complexity, confidence, reasons)`. Pure stdlib +
re (no LLM, no model — §8.4-safe + offline). `simple` iff a factual/quantity cue + a named-entity
proxy + bounded length AND NO compare/causal/mechanism/synthesis/clinical-evaluative intent; else
`complex`. NEVER raises (a malformed input returns low-confidence `complex`).

**Wiring in run_one_query** (after the scope-gate, before the fetch-cap read; all closed over the
outer try):
- `PG_COMPLEXITY_ROUTING` (default OFF → byte-identical). When ON: `classify_complexity(q["question"])`
  → `_simple_routed = complexity=="simple" AND confidence >= PG_COMPLEXITY_MIN_CONFIDENCE (0.80)`.
- `_simple_routed` → fetch cap = `PG_SIMPLE_FETCH_CAP` (40) instead of the slate 1000.
- `_simple_routed` → `assess_corpus_adequacy(..., override=_SIMPLE_ADEQUACY_THRESHOLDS)` — a FULL
  profile (Codex P2-1): min_total_sources=1, all tier floors 0, min_evidence_rows=1,
  max_t5_plus_t6_fraction=1.0, max_t7_fraction=0.50. Passed as an EXPLICIT override (override >
  protocol > default) so it NEVER mutates the hashed scope protocol (Codex P2-3).
- `complexity_routing` manifest field added on the SUCCESS path ONLY when routing is ON (Codex P2-2 —
  byte-identical OFF, no field).

**FAIL-OPEN (clinical-safety):** any router error / confidence < 0.80 / non-simple ⇒ the FULL
heavyweight path. A clinical / comparison / mechanism / dosing query is NEVER under-served.

**FAITHFULNESS INVARIANT (unchanged):** strict_verify per-sentence provenance + the 4-role D8 binding
gate + provenance tokens are NOT touched — every emitted sentence is verified identically. The router
only picks WHICH path/thresholds a confidently-simple query takes. A relaxed-adequacy simple query
ships ONLY grounded prose (strict_verify drops the rest) or lands at abort_no_verified_sections.

**Deferred (you approved):** the financial split-adjustment required-entity → a follow-up issue.

## Evidence (offline, no model, no spend)
- 17/17 `test_complexity_router_iready006.py`: SIMPLE incl. the multi-entity "Telus and Bell stock
  price over 20 years" (high-confidence simple, P2-4); COMPLEX/ambiguous fail-open (compare / why /
  mechanism / systematic review / dosing / "tell me about diabetes"); empty/None fail-open; the FULL
  simple-adequacy profile (P2-1); the right-sizing behaviour (a 1-T5-source corpus is `abort/expand`
  under clinical defaults but `proceed` under the simple override); and a source-check that the
  routing + manifest field + adequacy override are gated OFF by default (P2-2/P2-3).
- 44 more green: the adequacy-gate suite + benchmark-stack-activation + the domain-router integration
  that drives run_one_query end-to-end (proves the default-OFF routing block is byte-identical).
- py_compile clean (module + sweep + test).

## Review focus
(1) Is OFF byte-identical (no behavior change, no manifest field when PG_COMPLEXITY_ROUTING unset)?
(2) Is FAIL-OPEN airtight — can any path under-serve a complex/clinical query? (3) Does the adequacy
override truly avoid mutating the hashed protocol (explicit override param)? (4) Is the classifier
sound — any simple-mislabel of a query that needs deep research (esp. clinical)? (5) Faithfulness:
strict_verify/4-role untouched; the router is pre-retrieval.

## NOTE — scope + pre-existing (don't block)
- rightsizing_scope=cap_plus_adequacy (per your decision) — the section-floor relaxation is NOT in
  this PR (a smaller follow-up if wanted). The manifest field is success-path; abort-path coverage
  can be a follow-up.
- The locked 5-question benchmark does NOT set PG_COMPLEXITY_ROUTING → byte-identical; this activates
  on the general/real-user path only.

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
