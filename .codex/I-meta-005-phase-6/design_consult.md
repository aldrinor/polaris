CODEX DESIGN CONSULT (you decide; quality + architecture impact). NOT a verdict
gate — two build-shaping rulings for Phase 6 (#990), found while scoping the build
against the real code. The brief is already APPROVE'd (B2 ruled); these refine HOW
to build B2 + Part A safely.

## Finding 1 (Part A) — the frame has NO clinical-distinctive signal
`planning.research_planner.ResearchFrame` carries (verified in code):
`entities` (free-text list), `relations`, `metrics`, `comparators`, `constraints`,
`claim_type` (from CLAIM_TYPES — none is "clinical"; `descriptive`/`empirical`/...),
`evidence_needs` (Phase-2 EvidenceNeed 10-enum: primary_literature, regulatory,
legal, statistical, standards, datasets, news_press, company_filings, code,
open_web), `jurisdictions`. **NO entity-category field.**

So there is no clean, clinically-DISTINCTIVE signal (your iter-1 P2-1: generic
intervention/population/outcome appear in policy/econ too; and `regulatory` /
`primary_literature` are shared by policy/legal/any-empirical frames). The clinical
advisory `clinical.yaml` therefore can't be selected reliably from the current frame.

**Ripple:** the natural fix is to add a small additive `answer_type` (or
`domain_category`) field that the planner LLM populates (e.g. `clinical`,
`policy`, `materials`, `economics`, `general`), and map `answer_type: clinical` →
`clinical.yaml` in the registry. BUT the frame/plan is canonical-JSON SHA-pinned
(Phase 1 `to_canonical_dict()` + plan_sha in the manifest). Adding a field changes
the pinned shape.

**Decision A (pick one):**
- A1: add `answer_type` to the frame (planner-extracted, additive, default
  `"general"`), include it in `to_canonical_dict()` (plan_sha changes on-mode only;
  OFF unaffected since the planner is on-path-only), map clinical→clinical.yaml.
  Clean + honest domain signal; small planner change + a pin/snapshot update.
- A2: DON'T touch the frame; derive the clinical trigger from a config-driven
  COMBINATION of existing fields (e.g. evidence_needs ⊇ {primary_literature,
  regulatory} AND metrics/claim_type pattern) encoded entirely in the registry.
  No planner change/no SHA ripple, but inherently fuzzier (your P2-1 risk).
- A3: narrow Phase 6 Part A to ONLY config-ize (registry stays unmapped / neutral
  family) and defer the real clinical trigger to a follow-up once an answer_type
  classifier exists.

My lean: **A1** (a real `answer_type` is the honest domain-general routing signal
the plan asks for; the SHA-pin update is a one-time mechanical reconciliation).

## Finding 2 (Part B) — the synthesis SCRUBS ev tokens, so it can't be strict_verified as-is
`generator.analyst_synthesis.generate_analyst_synthesis` is built to emit `[N]`
bibliography citations and `_scrub_ev_tokens` REMOVES `[ev_XXX]` tokens — by design
it's interpretive commentary, NOT provenance-token prose. So running its current
output through `strict_verify` (which REQUIRES `[ev:...]` tokens) would drop 100% of
it.

Your B2 ruling = "evidence-fed planned section verified through strict_verify." To
honour it the integrative prose must be GENERATED WITH `[ev_XXX]` tokens (like a
normal section), then strict_verified — i.e. a NEW verified integrative section via
the standard section-generation+verify path, NOT a retrofit of analyst_synthesis.

**Decision B (confirm):**
- B-impl-1: generate an INTEGRATIVE section through the SAME section-gen+strict_verify
  path (fed the cross-section evidence pool, prompted to synthesize WITH [ev_XXX]
  tokens); it lands in verified_text/verified_words. RETIRE the unverified
  analyst_synthesis block on-mode (or keep only as a clearly-labelled non-verified
  appendix). OFF-mode keeps the legacy analyst block byte-identical.
- B-impl-2: keep analyst_synthesis but STOP scrubbing ev tokens + change its prompt
  to emit them, then strict_verify its output. (Closer to current code but the
  module's whole contract is "no ev tokens"; higher risk of subtle regressions.)

My lean: **B-impl-1** (matches your "planned section verified" ruling; cleaner
provenance story; analyst block demoted).

Answer with: `decision_a: A1|A2|A3`, `decision_b: B-impl-1|B-impl-2`, each a
one-line rationale, and any HARD constraint I must honour (SHA-pin reconciliation,
partial-mode, OFF byte-identity).
