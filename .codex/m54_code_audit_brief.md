M-54 code audit — V30 Report Contract Architecture, Layer 1 of 5.

## Commit

`054e1a9` PL: M-54 — V30 Report Contract YAML schema + strict loader (Layer 1 of 5)

## Plan reference

`outputs/audits/v29/fix_plan_v30.md` M-54 + your pass-1 plan review at
`outputs/codex_findings/v30_fix_plan_review_pass1/findings.md`
(CONDITIONAL-no-blockers). M-54 was `root_cause_approved` unchanged —
you said "Correct earliest stage. This is the missing content-model
foundation. The §5 fields are populated and the classification is right."

## What changed

Three new files + one YAML append.

**New: `src/polaris_graph/nodes/report_contract.py`** (401 lines)

Runtime types:
- `ContractSchemaError(ValueError)` — raised with `{path, reason}` for
  every malformation. `__init__(self, path, reason)` builds the message
  `f"contract schema error at {path}: {reason}"`.
- `@dataclass(frozen=True) class RequiredEntity` — carries `id, type,
  required_fields, min_fields_for_completion, rendering_slot` as the
  five required fields plus optional pass-through fields for DOI,
  PMID, anchor, journal, year, population_scope, jurisdiction,
  label_name, url_pattern.
- `@dataclass(frozen=True) class RenderingSlot` — `id, section,
  subsection_title, ordering, required=True`.
- `@dataclass(frozen=True) class ReportContract` — resolved object
  with helper methods `entities_by_id()`, `slots_by_id()`,
  `entities_by_slot()` for downstream consumers.

Loader:
- `load_report_contract_for_slug(template, slug) -> ReportContract | None`
  strict validator. Returns `None` when contract absent (backwards-
  compat); raises `ContractSchemaError` with path on shape violation.
- Referential-integrity check: every `entity.rendering_slot` must
  resolve to a declared slot id.
- Forward-compat: unknown `schema_version` strings are ACCEPTED at
  loader level (M-55 compiler will emit warning). Registry exposed via
  `get_known_schema_versions() -> frozenset({"v30.1"})`.

**Per your revision #7 (M-62 generalization proof)**:
loader is **entity-type-agnostic**. Types like `"statute"`,
`"dft_primary"`, `"unknown_xyz_2099"` are all accepted at M-54. Only
empty-string type is rejected. M-55 compiler + M-57/58 renderers own
per-type vocabulary.

**Modified: `config/scope_templates/clinical.yaml`** (appended
`per_query_report_contract` block)

One slug `clinical_tirzepatide_t2dm`, schema_version `v30.1`:

- 8 pivotal_trial primaries (SURPASS-1 Rosenstock Lancet 2021, SURPASS-2
  Frías NEJM 2021 DOI 10.1056/NEJMoa2107519, SURPASS-3 Ludvik Lancet
  2021, SURPASS-4 Del Prato Lancet 2021, SURPASS-5 Dahl JAMA 2022,
  SURPASS-6 Rosenstock JAMA 2023, SURPASS-CVOT Nicholls NEJM 2025,
  SURMOUNT-2 Garvey Lancet 2023) — each with DOI + PMID + journal +
  year + required_fields (N, population, comparator, baseline_hba1c,
  primary_endpoint, timepoint, etd_with_uncertainty, safety_signal,
  study_design, sponsor) + min_fields_for_completion=5 +
  population_scope=direct.
- 1 mechanism_primary (Thomas clamp Lancet D&E 2022 DOI
  10.1016/S2213-8587(22)00041-1) — required_fields include
  m_value_pct_increase, first_phase_insulin_secretion, half_life_days,
  etc. min_fields_for_completion=3.
- 6 regulatory (FDA Mounjaro T2D, FDA Zepbound obesity, EMA Mounjaro
  pediatric, NICE TA924, NICE TA1026, Health Canada Product
  Monograph) — jurisdiction + label_name + url_pattern +
  jurisdiction-appropriate required_fields.

15 rendering_slots with section/subsection_title/ordering/required.

**New: `tests/polaris_graph/test_m54_contract_schema.py`** (53 tests
in 9 classes)

- `TestWellFormedContract` (4): single entity load, optional pass-
  through, regulatory fields pass-through, helper methods.
- `TestMissingRequiredFields` (8): schema_version/required_entities/
  rendering_slots/entity.id/entity.type/entity.required_fields/
  slot.section/slot.ordering all raise with precise path.
- `TestEntityTypeAgnostic` (4): **your revision #7 test** —
  `"statute"`, `"dft_primary"`, `"unknown_xyz_2099"` accepted;
  empty-string type still raises.
- `TestMinFieldsBounds` (5): zero, negative, exceeds-len, equals-len
  accepted, non-int raises.
- `TestReferentialIntegrity` (3): unknown slot reference raises,
  extra declared slots OK, duplicate entity id raises.
- `TestSchemaVersion` (4): known version loads, unknown future
  version accepted, accessor, non-string raises.
- `TestBackwardsCompat` (5): missing slug → None, missing block →
  None, None template → None, empty/whitespace slug → None,
  non-string slug → None.
- `TestMalformedShapes` (10): non-dict shapes + empty collections
  all rejected; bool coercion rejected (`required: "yes"` raises);
  non-int ordering rejected.
- `TestRealClinicalYaml` (9): loads real YAML, 15 entities + 15
  slots, all SURPASS trials present, Frías DOI verified, Thomas
  clamp DOI verified, all 6 regulatory entities present, ref-
  integrity on real contract, slot ordering unique per section.

**New: `scripts/_m54_append_contract.py`** — idempotent YAML append
utility (marked as "delete after M-54 lands" in docstring).

## Tests

`python -m pytest tests/polaris_graph/test_m54_contract_schema.py`:
**53/53 pass in 5.44s**.

Regression: `python -m pytest tests/polaris_graph/` shows 1167
passing plus 17 pre-existing failures (M-36/M-42/M-49 V27-baseline
preservation regressions — these ARE the V28/V29 drift V30 is
designed to fix, not M-54-introduced) and 3 pre-existing collection
errors (test_m25/m28/m29 use `polaris_graph` not `src.polaris_graph`).

## Descoped (explicit)

Per V30 plan §M-54 test coverage item (d) "domain-inheritance works":
**deferred from M-54 loader to M-55 compiler.** The current contract
is a flat per-slug map. If inheritance is later introduced (e.g.
`clinical_tirzepatide_hfpef inherits from clinical_tirzepatide_t2dm
then overrides SURPASS-6`), inheritance resolution belongs in M-55.
Loader remains a pure YAML-shape validator. Documented in module
docstring under `## Descoped at M-54`.

## What to audit

1. **Your plan review #7 (M-62 generalization proof)**: is the
   loader sufficiently entity-type-agnostic? Verify
   `test_accepts_policy_entity_type`, `test_accepts_materials_entity_type`,
   `test_accepts_completely_novel_type` — all PASS. Does
   `TestEntityTypeAgnostic` cover what you intended by "compiler
   tests must prove arbitrary entity types and slot types compile
   without code changes"?

2. **Path precision**: every raised `ContractSchemaError` carries a
   path like `per_query_report_contract.{slug}.required_entities[0].rendering_slot`.
   Is that precise enough for debug use or do you want richer
   context (e.g. the actual offending value echoed)?

3. **Referential integrity edge cases**: currently we fail on
   `entity.rendering_slot → unknown_slot`. Not flagged: (a) a slot
   declared but not referenced by any entity (intentionally
   permitted for future growth); (b) two entities sharing one slot
   (intentionally permitted per `entities_by_slot()` semantics
   allowing multi-entity rendering). Agree with both?

4. **Schema-version policy**: forward-compat says "unknown version
   accepted at loader". Your pass-1 review did not specify; is
   this the right behavior or should the loader reject?
   Counterargument: M-55 compiler can emit warning and still
   attempt compile. If loader rejects, a pinned newer template
   cannot be inspected at all.

5. **Descope of domain-inheritance**: V30 plan §M-54 (d) said
   "domain-inheritance works". I declared this deferred to M-55
   compiler rather than implemented at M-54 loader. Does that
   match your architectural intent, or should M-54 implement a
   minimal `extends:` key now?

6. **min_fields_for_completion semantics**: loader enforces
   `1 <= min <= len(required_fields)`. Is that inclusive bound on
   the upper side correct, or should `min == len` require special
   handling? (Contract rationale: `min == len` means "all
   required fields must be present to call the slot complete";
   that remains a valid contract.)

7. **Real YAML coverage**: the integration test class
   `TestRealClinicalYaml` loads the shipped contract and asserts
   15+15 counts plus SURPASS-2 DOI + Thomas clamp DOI + regulatory
   presence. Is there a more-strict integrity check you would
   want before the compiler lands?

8. **Delete-after-lands script**: `scripts/_m54_append_contract.py`
   is marked delete-after-M-54. Should it be removed in a follow-up
   PL commit, or retained as runbook for a policy-slug contract
   append at M-62?

## Strategic context

Per your true-root-cause cross-review: "POLARIS is corpus-driven,
competitors are frame-driven. The missing layer is a query-specific
report contract." M-54 ships that layer. M-55 (frame compiler) is
the next consumer; M-56 (deterministic retrieval) feeds off
compiler output; M-57 instantiates outline from rendering_slots;
M-58/59/60 use the entity/slot schema for structured fill +
validation + gap rendering; M-61 hybrid completion targets the
same schema; M-62 proves the whole chain works on a non-clinical
slug.

M-54 is the foundation that the other 8 layers bolt onto. If you
want changes before M-55 lands, now is the time.

Write verdict to `outputs/codex_findings/m54_code_audit/findings.md`.

On **APPROVED / CONDITIONAL-no-blockers**: Claude proceeds to M-55
(frame compiler).

On **CONDITIONAL with blockers**: Claude revises M-54 before M-55.
