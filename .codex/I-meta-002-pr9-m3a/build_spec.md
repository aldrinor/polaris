# M3a build spec — native_gate_b_inputs builder module (I-meta-002 PR-9/M3a) — NO SPEND, NO NETWORK

The M3 DESIGN was APPROVED by Codex iter 2 (`.codex/I-meta-002-pr9-m3/codex_brief_verdict_iter2.txt`,
verdict: APPROVE, zero P0/P1, 4 P2 refinements). This is M3a — the pure-function native input builder.
M3b (the run_one_query seam + M1 no-leak amendment + Gate-B caller + seam test) is the NEXT sub-PR.

## Locked constraints (from the approved design)
- NATIVE-ONLY: build inputs from `config/scope_templates/<domain>.yaml` +
  `config/architecture/d8_release_policy.yaml` ONLY. NEVER read `outputs/dr_benchmark/` (gold rubric,
  competitor answers) — §-1.1 lethal. Add an explicit module-level comment stating this.
- NO NETWORK / NO SPEND: pure functions; tests use fixtures only (tests/fixtures/), no httpx, no I/O
  to the real run dir (the builder RETURNS data; M3b writes it).
- Fail-closed everywhere (raise, never silently default).
- snake_case; explicit imports; named constants; no except:pass; no unittest.mock in src/; no
  datetime.now in library code.
- 200-LOC cap applies — keep M3a tight; M3b is separate.

## Module: src/polaris_graph/roles/native_gate_b_inputs.py
(Location per Codex P2: OUTSIDE src/polaris_graph/benchmark/ — keep Gate-B wiring separate from frozen
benchmark/audit code.)

Reuse existing types — READ first: `src/polaris_graph/roles/sweep_integration.py` (FourRoleClaim,
FourRoleEvaluationInputs), `src/polaris_graph/roles/release_policy.py` (CoverageLedger, D8PolicyConfig,
load_d8_policy_config, _MATERIAL_SEVERITIES, s0_must_cover_categories), the EvidenceDocument type
(find its definition + its canonical-identifier fields: doi / pmid / url), and
`src/polaris_graph/generator/multi_section_generator.py` (MultiSectionResult, SectionResult,
kept_sentences_pre_resolve) + `provenance_generator.py` (SentenceVerification.sentence/tokens/is_verified,
ProvenanceToken.evidence_id). Also read `config/scope_templates/clinical.yaml`
per_query_report_contract[clinical_tirzepatide_t2dm].required_entities for the real entity shape
(id/type/anchor/doi/url_pattern/required_fields).

Implement (pure functions):

1. `load_required_entities(template: dict, slug: str) -> list[dict]`
   - Return `template["per_query_report_contract"][slug]["required_entities"]`.
   - FAIL CLOSED (raise a clear ValueError) if the slug has no per_query_report_contract entry OR
     required_entities is missing/empty. (Native denominator must exist.)

2. `validate_entity_severity(entity: dict, d8_config: D8PolicyConfig) -> tuple[str, str | None]`
   (the §7.E schema-validator, FAIL CLOSED — Codex P1 iter1):
   - severity = entity["severity"]; must be one of S0/S1/S2/S3 (raise if missing/invalid — NEVER
     default to S3).
   - if severity == "S0": entity MUST declare a valid `s0_category` ∈ d8_config.s0_must_cover_categories
     AND a non-empty `coverage_content_requirements` (list of deterministic required tokens/phrases).
     Raise if missing/invalid s0_category, or S0-without-category, or S0-without-content-requirements.
   - return (severity, s0_category_or_None).

3. `claim_covers_entity(claim_evidence_ids, claim_text, entity, evidence_lookup) -> bool`
   plus an S0-specific check. Coverage rules (§7.D, Codex-tightened + P2 #4):
   - ENTITY coverage: True iff the claim cites evidence whose CANONICAL identifier EXACTLY matches the
     entity's canonical identifier. Canonical identifiers = DOI, PMID, and full canonical URL (exact).
     A broad `url_pattern` FRAGMENT must NOT grant coverage (fail closed: only an exact full canonical
     URL/DOI/PMID match counts). anchor-string-in-sentence alone does NOT grant coverage.
   - S0 SAFETY-CATEGORY coverage (stricter): an S0 category-specific entity is covered ONLY when the
     claim BOTH (a) matches the entity's canonical evidence (the entity rule above) AND (b) the claim
     text deterministically satisfies the entity's `coverage_content_requirements` (e.g. all required
     tokens/phrases present, case-insensitive, deterministic). A broad label/source citation must NOT
     satisfy a safety category without the content match.

4. `build_native_gate_b_inputs(*, multi, template, slug, domain, evidence_lookup,
   model_slugs, d8_config) -> NativeGateBBundle`
   where `NativeGateBBundle` is a small dataclass holding `inputs: FourRoleEvaluationInputs` AND
   `audit_map: dict[str, dict]` (Codex P2 #2 — builder RETURNS the bundle; M3b writes
   four_role_claim_audit.json; the builder does NOT do file I/O).
   - required_element_ids = [e["id"] for e in load_required_entities(template, slug)].
   - validate every entity via validate_entity_severity (fail-closed).
   - For each kept (is_verified) sentence across multi.sections in section order, with section_index si
     and sentence_index xi:
     - claim_id = f"{si:02d}-{xi:03d}-{h}" where h = first 8 hex of sha256(normalized sentence)
       (normalized = lowercased + whitespace-collapsed). Deterministic, unique, non-blank. (P2 #2 + iter1.)
     - claim_text = the sentence.
     - evidence_documents = resolve each ProvenanceToken.evidence_id via evidence_lookup →
       EvidenceDocument. FAIL CLOSED (raise) on any unknown evidence_id or empty evidence text.
     - covered_element_ids = the entity ids this claim covers per rule 3 (entity rule; S0 entities only
       when content-match also holds).
     - severity = MAX severity among covered entities (order S0>S1>S2>S3); if it covers no required
       entity → "S3" (observe-only).
     - s0_categories = the s0_category values of the S0 category-specific entities it covers (rule 3b,
       content-validated) — never inherited from a non-category element.
   - required_s0_categories = sorted set of s0_category across the question's S0 required_entities.
   - inputs = FourRoleEvaluationInputs(claims=[...], coverage_ledger=CoverageLedger(
     required_element_ids=required_element_ids), required_s0_categories=required_s0_categories,
     model_slugs=model_slugs, rewrite_already_attempted=False). (covered_element_ids stays EMPTY on
     input — the sweep rebuilds the numerator from VERIFIED finals.)
   - audit_map: claim_id -> {section_index, section_title, sentence, evidence_ids, covered_element_ids,
     severity, s0_categories}.
   - FAIL CLOSED if there are zero kept sentences (no vacuous input) — let
     run_four_role_evaluation's own empty-claims guard also catch it, but raise here with a clear msg.
   - NEVER import or read anything under outputs/dr_benchmark.

## Tests: tests/roles/test_native_gate_b_inputs.py (fixtures only, NO network)
Use small in-test fixture objects (a fake MultiSectionResult-like structure with sections +
kept_sentences_pre_resolve, fake EvidenceDocument lookup, a fixture scope-template dict in
tests/fixtures/ with required_entities carrying severity/s0_category/coverage_content_requirements +
doi/pmid/url). Cover:
- missing per_query_report_contract for slug / empty required_entities -> raise.
- missing severity / invalid severity value -> raise (NEVER default S3).
- S0 entity without s0_category, invalid s0_category, or without coverage_content_requirements -> raise.
- entity coverage on EXACT DOI match; EXACT PMID match; EXACT full-URL match.
- a broad url_pattern FRAGMENT does NOT grant coverage (fail closed).
- anchor-string-in-sentence alone does NOT grant coverage.
- S0 category covered only when evidence match AND content-requirement match both hold; a claim citing
  the S0 entity's evidence but NOT containing the required content does NOT get S0 credit.
- claim_id deterministic (same sentence -> same id) + unique across different sentences; audit_map
  emitted with the right keys.
- unknown evidence_id / empty evidence text -> raise.
- severity = MAX over covered entities; claim covering nothing -> S3; s0_categories only from covered
  S0 category entities.
- zero kept sentences -> raise.
- a test asserting the module never references "outputs/dr_benchmark" / "rubric" (grep the source or
  assert no such import) — contamination guard.

## Verify
python -c "import src.polaris_graph.roles.native_gate_b_inputs" ;
python -m pytest tests/roles/test_native_gate_b_inputs.py -q
Report files created + results. Do NOT commit.
