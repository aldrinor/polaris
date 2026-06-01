CODEX SCOPE DECISION (you decide; quality-impact framed). NOT a verdict gate — a
single scope ruling for Phase 5 (#989) finding-dedup + corroboration.

## The empirical finding
The Phase-5 brief (which you APPROVE'd iter 2) assumed
`contradiction_detector.extract_numeric_claims` is "already field-agnostic" and
reusable for finding extraction. Empirical probe on the real function:
- It emits AT MOST ONE numeric claim per row (one predicate, one value via
  `_find_value_in_context`).
- It returns `[]` for NON-CLINICAL numerics. Verified empties:
  - "The intervention increased GDP by 3.2% in 2024." → []
  - "The policy reduced emissions by 12.5% by 2030." → []
  - "The model improved accuracy by 8.4% on the benchmark." → []
  Clinical quotes extract fine ("Tirzepatide weight loss 20.9% at week 72" →
  (tirzepatide, weight loss, 20.9, %, "at week 72")).

## What the current build does (already implemented, finding_dedup.py)
- CLINICAL corpora: full dedup-by-finding + `corroboration_count` =
  independent registrable-domains. Works (3 same-finding rows from 3 domains →
  1 rep, corroboration_count=3; different endpoint → separate; same-domain → 1).
- NON-CLINICAL numeric rows: 0 extracted findings → kept as SAFE SINGLETONS. Never
  falsely merged, never dropped, but earn NO corroboration_count. So corroboration
  is EFFECTIVE for clinical, INERT-but-SAFE for non-clinical. No correctness bug,
  no unique-claim loss — purely a COVERAGE gap.

## The tension
Gap D (the plan) frames corroboration as "intrinsically domain-general" and "the
primary sovereign defense for fields with thin OpenAlex coverage" — i.e. exactly
the NON-clinical/niche fields where our extractor is inert. So clinical-only
corroboration undercuts gap D's stated rationale for non-clinical domains. BUT the
immediate benchmark (DRB-EN clinical-3 + source-critical-2) is clinical, where the
build is fully effective.

## The decision (pick one)
- **A. Ship clinical-effective + non-clinical-safe for Phase 5; defer a
  field-agnostic numeric-finding extractor to a NEW follow-up issue.** Lowest risk,
  no over-merge exposure, honest documented limitation. Corroboration domain-
  generality lands in a later phase.
- **B. Add a conservative field-agnostic numeric-finding fallback NOW** (regex
  number+unit + a conservative context key) so non-clinical findings also cluster.
  Higher gap-D value, but introduces over-merge risk (a wrong merge inflates
  corroboration or, worse, could collapse distinct findings) and a fuzzy
  context-match threshold (a magic number) unless the key is exact-match, which
  makes it mostly inert anyway.

## Constraints you must weigh
- Operator standing directive this session: "beat ChatGPT/Gemini on ALL aspects,
  no subpar, no circle-jerking."
- HARD safety: NO unique-claim loss (clinical-lethal). Option B must not raise that
  risk for clinical rows (the clinical extractor stays primary; B is a fallback only
  when clinical extraction returns []).
- Zero spend; no LLM in extraction; no host literals.

Answer with a short ruling: `decision: A | B`, one-paragraph rationale, and if B,
the EXACT conservative key you'd require to avoid over-merge.
