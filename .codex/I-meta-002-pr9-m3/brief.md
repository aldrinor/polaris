# Codex brief-gate (DESIGN) — I-meta-002 PR-9 (M3): contamination-clean Gate-B production caller for the 4-role evaluation — NO SPEND

> **DESIGN / BRIEF REVIEW, NOT a diff review.** No implementation yet. ITER 2: every iter-1 ruling
> below has been incorporated into the design. Please verify I captured your rulings faithfully and
> APPROVE the design so build can start, or REQUEST_CHANGES with corrections.

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings. Reserve P0/P1 for real execution/safety risks.
- If you're holding back a design objection for the next round — surface it now; iter 6 does not exist.
- Verdict APPROVE iff the design (now seam B + your tightened mapping rules + prereq handling) is
  correct and safe to build.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
key_handling_ruling: hard_require | warn | other   # the §8 residual you did not rule in iter 1
convergence_call: continue | accept_remaining
```

## CHANGELOG — your iter-1 rulings, now incorporated (please verify)
1. **Timing seam = B** (inject builder callback). C REJECTED (fail-open: a post-gen second pass can
   leave a pre-D8 publishable success/release manifest if skipped/crashed). → §6 now specifies B only.
2. **claim→element**: exact/canonical evidence-id match grants ENTITY coverage ONLY; anchor-string-in-
   sentence alone is NOT accepted; **S0 safety-category credit is NOT granted by evidence-id match** —
   it requires category-specific native signals + deterministic claim-content validation. → §7.D rewritten.
3. **severity/S0**: native pre-registered annotations (not a type→severity heuristic), **schema-
   validated + fail-closed** — missing/invalid severity, invalid S0 category, or S0-without-category
   RAISES; never silently defaults to S3. Claim inherits MAX severity over covered elements; S0
   categories inherit ONLY from covered category-specific elements. → §7.E rewritten.
4. **required_element_ids**: contract IDs only, fail-closed on missing slug/empty entities, never read
   `outputs/dr_benchmark`. → §7.A unchanged (approved).
5. **claim_id**: builder-owned deterministic id = position + short normalized-sentence hash (NOT
   position alone); builder emits an audit map `claim_id -> {section_index, section_title, sentence,
   evidence_ids}`. → §7.B rewritten.
6. **evidence_documents**: resolve kept-sentence `ProvenanceToken.evidence_id` against the final
   generation evidence pool / `evidence_pool.json`; fail-closed on missing/empty evidence text. → §7.C unchanged (approved).
7. **benchmark contracts = SEPARATE prerequisite** (not M3): author from question text + native
   scope/completeness/D8 ONLY; attestation artifact (author/reviewer, inputs used, date, explicit
   no-gold/no-competitor statement); freeze before any benchmark run. M3's offline seam test MAY use
   the existing non-benchmark `clinical_tirzepatide_t2dm` contract AFTER adding+validating native
   severity/S0 annotations. → §5 rewritten; tracked as a separate item.
8. **module location**: builder lives OUTSIDE `src/polaris_graph/benchmark/` (keep Gate-B wiring
   separate from frozen benchmark/audit code). → §9 now `src/polaris_graph/roles/native_gate_b_inputs.py`.
9. **§8 key handling** was NOT ruled in iter 1 — §8 below now states a concrete proposal; please rule
   (`key_handling_ruling`).

## HARD CONSTRAINTS (operator-locked, NOT consultable — do not reopen)
1. **NATIVE-ONLY, NEVER THE GOLD RUBRIC.** Inputs (required-element denominator, claim→element
   coverage, severity) built ONLY from `config/scope_templates/<domain>.yaml`,
   `config/completeness_checklists/<domain>.yaml`, `config/architecture/d8_release_policy.yaml`.
   NEVER `outputs/dr_benchmark/` (rubric, freeze pin, competitor answers). §-1.1 LETHAL otherwise.
2. **NO MONEY / NO NETWORK in this PR.** M3 = wiring + offline tests with an INJECTED fake
   RoleTransport. No Vast deploy, no OpenRouter verifier calls. Paid run = later canary.
3. **D8 is the SINGLE binding gate.** No second gate.
4. **Sweep must NOT synthesize claim_ids or the coverage denominator** — origin must be explicit +
   auditable (the injected builder + native config).
5. **200-LOC PR cap** → M3a/M3b split (§9).
6. Operator BLIND.
7. Frozen, no drift: `claim_audit_scorer.py`, runtime lock (do NOT promote), canonical pipeline
   statuses, M1 `openai_compatible_transport.py` (except the narrow §8 no-leak amendment if you rule
   it belongs here), M2 `verify_serving_identity.py`.

## 2. Context
Codex full-readiness item 3 = M3. M1 (transport) + M2 (serving config + identity probe) committed +
APPROVE'd; Gate-A green (334 tests). This brief designs M3 (iter 2).

## 3. Grounded data flow + types (file:line — verbatim)
- `run_one_query(q, out_root, *, four_role_transport=None, four_role_inputs=None)`
  (`run_honest_sweep_r3.py:1206-1226`). 4-role branch at 3139-3220, INSIDE run_one_query, AFTER
  `multi = await generate_multi_section_report(...)` (~2319). Activates iff `PG_FOUR_ROLE_MODE in
  (1,true,True)` AND `four_role_transport is not None`; raises if on and inputs missing; calls
  `run_four_role_evaluation(...)`; then OVERRIDES `manifest['release_allowed']` + `manifest['status']`
  from D8 and demotes the legacy gate to advisory.
- Callers pass NEITHER arg: `run_honest_sweep_r3.py:3634`, `run_r5_rerun.py:39`,
  `run_r6_validation.py:41`. Scope resolved inside via `load_scope_template(q["domain"])` → `_template`;
  `q["slug"]`/`q["domain"]` identify the question.
- `FourRoleClaim(claim_id, claim_text, evidence_documents:list[EvidenceDocument], severity:str,
  s0_categories:list[str]=[], covered_element_ids:list[str]=[])` (`sweep_integration.py:62-77`).
  `FourRoleEvaluationInputs(claims, coverage_ledger, required_s0_categories, model_slugs,
  rewrite_already_attempted=False)` (`:80-96`).
- `CoverageLedger(required_element_ids:list[str], covered_element_ids:set[str]=set())`
  (`release_policy.py:107-125`); raises if required empty, raises if covered non-empty on input,
  credits `claim.covered_element_ids` ONLY on VERIFIED final verdict (`sweep_integration.py:165-182,234-235`).
- Severities `S0,S1,S2,S3` (`release_policy.py:49`; S3 observe-only). Default S0 categories
  (`d8_release_policy.yaml:29-34`): contraindications, dosing_limits, black_box_warnings,
  pregnancy_renal_hepatic_cautions, regulatory_status. Threshold 0.70.
- `multi` = `MultiSectionResult` (`multi_section_generator.py:139`): `sections:list[SectionResult]`;
  `SectionResult` (`:79-120`) has `title:str` (no stable id), `verified_text`,
  `kept_sentences_pre_resolve:list[SentenceVerification]`. `SentenceVerification`
  (`provenance_generator.py:398-407`): `sentence:str`, `tokens:list[ProvenanceToken]`, `is_verified`,
  `resolved_citation_marker`. `ProvenanceToken`: `evidence_id`, `start`, `end`, `raw`. No claim_id /
  covered_element_ids / severity.
- Native elements: `per_query_report_contract[<slug>].required_entities[*]` with `id`, `type`,
  `anchor`, `doi`/`url_pattern`, `required_fields`. Only `clinical_tirzepatide_t2dm` (clinical) +
  `policy_medicare_drug_price` (policy) have contracts; the 5 benchmark slugs have NONE.
- No existing helper maps `multi`→claims / scope→required_element_ids / claim→element/severity. M3 builds these.

## 4. Contamination boundary (confirmed iter 1) — M3 never reads `outputs/dr_benchmark/`.

## 5. Benchmark-contract prerequisite (SEPARATE item per your ruling — NOT M3)
The 5 golden slugs have no `per_query_report_contract`. Authoring native, pre-registered,
gold-rubric-BLIND contracts (with §7.E severity/S0 annotations) for them is a SEPARATE prerequisite
item, tracked as `I-meta-002 PR-pre / native benchmark contracts`. Procedure: derive `required_entities`
from the QUESTION text + POLARIS native scope/completeness/D8 policy ONLY; NO `outputs/dr_benchmark`,
no frozen rubric, no competitor answers. Emit an attestation artifact
(`.codex/<id>/contract_attestation.txt`: author/reviewer, inputs used, date, explicit
"no gold rubric / no competitor access" statement); freeze the contracts (SHA pin) before any benchmark
run. **M3's own offline test uses the EXISTING `clinical_tirzepatide_t2dm` contract** after adding +
validating §7.E native severity/S0 annotations to it (a small, non-benchmark, contamination-free change).

## 6. Timing seam = B (FINAL, per your ruling)
Add a `four_role_input_builder` parameter to `run_one_query` (default None; backward-compatible —
when None the existing behavior is byte-unchanged). When `PG_FOUR_ROLE_MODE` is on AND
`four_role_transport is not None`: AFTER generation, the branch calls
`four_role_inputs = four_role_input_builder(multi=multi, template=_template, slug=q["slug"],
domain=q["domain"], evidence_pool=<the run's evidence pool>)` and proceeds with the existing fail-closed
path (raise if the builder returns None, or returns empty claims / empty required set — the
`run_four_role_evaluation` guards already enforce this). The builder is M3-owned + native-only; the
sweep does NOT own the synthesis logic. Because the D8 override of `manifest['release_allowed']` +
`manifest['status']` happens INSIDE `run_one_query` before the manifest is finalized/written
(`run_honest_sweep_r3.py:3319` writes manifest.json AFTER the branch), there is no window where a
publishable success manifest exists before the gate runs — the fail-open risk you flagged for C does
not exist for B. (If `four_role_inputs` is ALSO passed directly — e.g. a static one in a unit test —
it is used as-is and the builder is not called; builder takes precedence only when provided.)

## 7. Deterministic native mapping rules (incorporating your rulings)
- **A. required_element_ids** = `per_query_report_contract[slug].required_entities[*].id` for the
  question's domain/slug. FAIL CLOSED (raise) if no contract for the slug or empty required_entities.
  Native, never gold. (APPROVED iter 1.)
- **B. claim_id** = `f"{section_index:02d}-{sentence_index:03d}-{h}"` where `h` is a short hex of a
  SHA-256 over the NORMALIZED sentence text (lowercased, whitespace-collapsed), over kept (is_verified)
  sentences in section order. Deterministic, reproducible, unique, non-blank. The builder ALSO emits an
  audit map `claim_id -> {section_index, section_title, sentence, evidence_ids}` persisted alongside the
  run (e.g. `four_role_claim_audit.json`) so every claim_id is traceable. (Per your iter-1 change.)
- **C. evidence_documents** = resolve each kept sentence's `ProvenanceToken.evidence_id` against the
  run's FINAL generation evidence pool (`evidence_pool.json` / the in-scope pool object) → the
  `EvidenceDocument`. FAIL CLOSED on any missing evidence_id or empty evidence text. (APPROVED iter 1.)
- **D. claim→covered_element_ids** (your tightened rule):
  - ENTITY coverage: a claim covers required_entity E iff the claim cites evidence whose CANONICAL
    identifier (doi/pmid/url) EXACTLY matches E's `doi`/`url_pattern`. Anchor-string-in-sentence alone
    does NOT grant coverage.
  - S0 SAFETY-CATEGORY coverage is STRICTER: an S0 category-specific element E (severity S0, with an
    `s0_category` + a declared `coverage_content_requirements`: deterministic required tokens/`required_fields`
    the claim text must contain) is covered ONLY when the claim BOTH (a) cites E's canonical evidence
    AND (b) deterministically satisfies E's `coverage_content_requirements`. So no broad label/source
    citation can satisfy a safety category — the claim must actually carry the category content. A claim
    contributes E to `covered_element_ids` only if both conditions hold (entity) / all three hold (S0).
- **E. severity + s0_categories** (your validated-native-annotation rule): each `required_entities[*]`
  declares a PRE-REGISTERED native `severity: S0|S1|S2|S3`, and when `severity: S0` it MUST declare a
  valid `s0_category` ∈ d8 `s0_must_cover_categories` AND `coverage_content_requirements`. The loader
  SCHEMA-VALIDATES and FAILS CLOSED (raise): missing/invalid severity, invalid s0_category, or
  S0-without-category/without-content-requirements → error; NEVER silently default to S3. A claim's
  `severity` = MAX severity among the elements it covers (S0>S1>S2>S3); a claim covering no required
  element → S3 (observe-only). A claim's `s0_categories` = the `s0_category` values of the S0
  category-specific elements it covers (per rule D, content-validated) — never inherited from a
  non-category element. `required_s0_categories` for the question = the set of `s0_category` across the
  question's S0 required_entities.

## 8. Per-role key handling (§8 residual — please rule `key_handling_ruling`)
M3 constructs the verifier transport. Your M2 note: M1's transport falls back to `OPENROUTER_API_KEY`
when `PG_<ROLE>_API_KEY` is unset, which could leak the OpenRouter key to a self-host box. M2 fixed the
PROBE; M1's transport still leaks. PROPOSAL: a narrow M1 amendment (mirroring M2) so the 3 self-host
verifier roles NEVER fall back to `OPENROUTER_API_KEY` — they use `PG_<ROLE>_API_KEY` or NO
Authorization header (keyless self-host vLLM is valid, per M2). M3's transport construction then needs
no key gymnastics. (Do NOT hard-require a per-role key — that would break the valid keyless self-host
case M2 established.) **Please rule**: is the narrow M1 no-OpenRouter-fallback amendment the right fix,
done as part of M3b (or a dedicated micro-PR), vs a runtime warning only?

## 9. Acceptance criteria + sub-PR split (per your iter-1 P2s)
- **M3a** — `src/polaris_graph/roles/native_gate_b_inputs.py` (OUTSIDE benchmark/, per your ruling):
  pure functions — scope→required_element_ids loader (§7.A, fail-closed); §7.E severity/S0
  schema-validator (fail-closed); `multi`→FourRoleClaim builder (§7.B claim_id + audit map, §7.C
  evidence resolution); §7.D entity + S0-content claim→element mapper. Returns
  `FourRoleEvaluationInputs`. Unit tests (no network): missing-contract → raise; missing/invalid
  severity → raise; S0-without-category/content → raise; entity coverage on exact evidence-id match;
  S0 coverage requires evidence + content match (broad-label citation does NOT grant S0 credit);
  claim_id deterministic + audit map emitted; missing evidence → raise.
- **M3b** — the §6 seam (`four_role_input_builder` param in `run_one_query`) + the §8 M1 no-leak
  amendment (if you rule it here) + a Gate-B caller that constructs `OpenAICompatibleRoleTransport`,
  sets `PG_FOUR_ROLE_MODE`, passes the M3a builder. ONE offline test drives the full seam with an
  INJECTED fake RoleTransport over the EXISTING `clinical_tirzepatide_t2dm` contract (+ its new §7.E
  annotations), asserting the D8 decision flows to `manifest['release_allowed']`/`status` and no
  network/spend.
- (benchmark native contracts: SEPARATE prereq item per §5.)
Please confirm the split + module location, or restructure.

## 10. Files I have ALSO checked / relevant
- `sweep_integration.py`, `release_policy.py` — read; M3a feeds their existing types, no drift to their logic.
- M1/M2 — M3 constructs (not modifies) the transport, except the narrow §8 M1 no-leak amendment if you rule it here.
- `outputs/dr_benchmark/` — M3 MUST NOT read (contamination).

## 11. Questions for Codex
1. Did I capture all 8 iter-1 rulings faithfully (CHANGELOG)? Any misread?
2. `key_handling_ruling` (§8): narrow M1 no-OpenRouter-fallback amendment in M3b vs warn-only vs other?
3. §7.D: is "entity = canonical evidence-id match; S0 = evidence-id match AND declared
   content-requirement match" the determinism you want, and is `coverage_content_requirements` the right
   native field to add to S0 elements?
4. §6 seam B: confirm the manifest-write-after-branch argument closes the fail-open window.
5. §9 split + `native_gate_b_inputs.py` location — approve or restructure?
6. Any remaining contamination / fail-open / double-gate / no-spend risk?

APPROVE only if seam B + the tightened mapping/severity rules + the separate-prereq handling are
correct, native-only, fail-closed, no-spend, and safe to build.
