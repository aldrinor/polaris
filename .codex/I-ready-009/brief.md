# Brief — I-ready-009 (#1081): generator answer-SHAPE domain-locked to clinical (non-clinical defect)

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## REVIEW ONLY — DO NOT MODIFY ANY FILE
Return ONLY the YAML verdict. **Do NOT edit/create source/test/config files, do NOT write a patch.**
You review this BRIEF's acceptance criteria; Claude authors the diff after APPROVE.

## ITER-1 RESOLUTION — your 3 P1 KILLED the planner approach; the design is REPLACED
Your iter-1 review correctly found that flipping `PG_USE_RESEARCH_PLANNER` is a trap (it bypasses
`load_scope_template`, `q['amplified']`, domain expanders, and V30 `per_query_report_contract`, dropping
source-critical seeds; and it leaks across the `--all` order). **The planner is no longer touched at
all.** The redesign is a NARROW, contract-preserving, generator-only outline-set switch:

The OFF-mode outline is an LLM call (`OUTLINE_SYSTEM_PROMPT` `:367`, `_call_outline` `:792`) that
instructs "title: one of {_ALLOWED_SECTIONS}". The defect is purely that `_ALLOWED_SECTIONS` (`:63-72`)
is a HARDCODED clinical list (Efficacy/Safety/...) used for every domain. Fix:
- **(1) Domain-native outline set, selected per-query by `q['domain']`, on the EXISTING off-path.** Add
  non-clinical allowed-section sets; `_call_outline` / the deterministic + archetype fallback outlines
  (`_build_deterministic_fallback_outline` `:547`, `_build_archetype_fallback_outline` `:768`) choose the
  set by domain, DEFAULTING to the clinical `_ALLOWED_SECTIONS` for clinical/unknown.
- **(2) `research_plan` stays None → the planner, scope template, amplified, and V30 contracts are
  UNTOUCHED** (your P1-1). **No env var is read or written** → nothing can leak across `--all` (your
  P1-2). The outline set is a pure function of `q['domain']`, recomputed every query.
- **(3) The clinical SECTION-PROSE prompt (`SECTION_SYSTEM_PROMPT_TEMPLATE`, rules 1-13 INCLUDING the
  primary-source-over-derivative + jurisdiction + claim-frame rules) is KEPT for ALL domains.** We do
  NOT route to the field-agnostic template, so NOTHING is lost (your P1-3). Empirically the clinical
  prose prompt already produced good attributed/hedged economics prose for drb_72 (run12: "According to
  Autor", per-sentence [ev]); only the outline LABELS were wrong. So part (b) field-agnostic hardening
  and part (c) advisory-family registration are NO LONGER NEEDED for this fix (the field-agnostic on-path
  stays inert) — I am dropping them from scope. If you disagree, say so.

**Net:** the diff is generator-internal outline-set selection only. Clinical-3 byte-identical; non-clinical
gets domain-native section headers; faithfulness machinery + all prose rigor + V30 contracts untouched.

## DECISION for you — the non-clinical outline taxonomy
What sections should non-clinical questions be allowed? Options:
- **(A) one generic domain-neutral research set** (e.g. Background / Key Findings / Evidence & Analysis /
  Comparative Assessment / Implications / Limitations) used for ALL non-clinical domains. Simple, safe,
  domain-agnostic. **My lean.**
- **(B) per-domain sets** (economics/workforce, policy/regulatory, tech, due-diligence) — richer but more
  config + must cover drb_72 (workforce/economics) and drb_90 (policy/liability) specifically.
- **(C) allow the outline LLM free-form titles for non-clinical** (no fixed list) — most flexible, least
  deterministic.
Which do you want, and must drb_72 (workforce) + drb_90 (policy) map to a sensible set under your choice?

## Smoke (offline, $0)
- Clinical byte-identical: a clinical-domain question → outline constrained to `_ALLOWED_SECTIONS`
  (contains "Efficacy"); the clinical section-prose prompt is selected (`use_field_agnostic=False`).
- Non-clinical: a workforce/economics-domain question → outline set is the non-clinical set, NOT
  `_ALLOWED_SECTIONS`; "Efficacy"/"Safety" are NOT in its allowed titles.
- `PG_USE_RESEARCH_PLANNER` is NOT read or set anywhere in the new code (grep proof) → no planner
  activation, no `--all` env leak.
- The clinical section-prose prompt (with the primary-source + jurisdiction + claim-frame rules) is used
  for non-clinical too (rigor preserved).

## Files I have ALSO checked
- `OUTLINE_SYSTEM_PROMPT` `:367`, `_call_outline` `:792`, `_parse_outline` `:399`, the two fallback
  outline builders `:547`/`:768` — all consume `_ALLOWED_SECTIONS`; the domain-set selection threads here.
- `SECTION_SYSTEM_PROMPT_TEMPLATE` (clinical prose, rules 1-13) — KEPT for all domains; untouched.
- The planner / V30 `per_query_report_contract` / scope-template path — NOT touched (the whole point).
- strict_verify / 4-role seam — untouched.

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
outline_taxonomy: generic_set | per_domain_sets | freeform | other
drop_parts_b_and_c_ok: yes | no
clinical_3_byte_identical: yes | no
```
