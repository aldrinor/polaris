# Codex Pass-1 Review: V29 -> V30 Fix Plan

**Verdict**: CONDITIONAL

The plan is directionally correct and substantially matches the approved V29 framing: query-specific report contract, mandatory slots, explicit insufficiency instead of silent omission, `strict_verify` preserved, and hybrid human/licensed completion as the strongest non-band-aid companion. The root-cause diagnosis is right.

This is not clean APPROVED yet because three places still drift from that framing:

1. M-58/M-59 still describe a prose-first slot fill. That is weaker than "instantiate report schema then fill it." If slot completion is validated from prose alone, the validator will become heuristic and fragile. The slot fill needs a machine-readable field map per required field, then prose rendering can sit on top.
2. M-61's provenance controls are too soft. A free-text `consent_proof` string is not a strong enough guarantee against fabricated human-curated quotes.
3. M-60/M-62 need more structural rigor so honesty-under-failure and non-hardcoded generalization are enforceable rather than asserted.

## Per-item verdicts

| Item | Verdict | Reason |
|---|---|---|
| M-54 | root_cause_approved | Correct earliest stage. This is the missing content-model foundation. The §5 fields are populated and the classification is right. |
| M-55 | root_cause_approved_with_revision | Correct stage and role. Needs one explicit guard against clinical hardcoding: compiler tests must prove arbitrary entity types and slot types compile without code changes. |
| M-56 | root_cause_approved | Correct earliest preventable stage for retrieval non-determinism. Keep it contract-driven; do not move it ahead of M-54/M-55. |
| M-57 | root_cause_approved | Correctly moves outline authority from LLM emergence to contract instantiation. |
| M-58 | needs_revision | Correct causal stage, but "one prose paragraph" is not enough. Slot fill must produce field-level structured output keyed to required fields, with `value | not_extractable | source_span`, otherwise M-59 cannot honestly validate completion. |
| M-59 | needs_revision | Correct stage, but validator semantics are underspecified unless M-58 emits machine-readable slot payloads. Validator should validate slot existence, bound evidence, and per-field completion status from structured output, not prose heuristics. |
| M-60 | needs_revision | Correct honesty-under-failure objective, but report prose alone is insufficient. Manifest output must carry structured failure metadata and retrieval-attempt details, not just a human sentence. |
| M-61 | needs_revision | Hybrid completion is the right Path B, but provenance integrity is too weak. `consent_proof` as a free string does not adequately protect against fraudulent completion. |
| M-62 | preservation_guard_needs_revision | Correctly classified as preservation guard, but the proposed materials-only smoke test is not sufficient by itself to prove architecture, not clinical-paper hardcoding. Add entity-type generalization tests and prefer a domain that stresses non-paper entity types. |

## Specific revisions required

1. **M-58/M-59 slot payload contract**: change the slot-bound generation contract from paragraph-only to structured-first. Each slot should emit a machine-readable payload for every required field:
   - `field_name`
   - `status`: `extracted | not_extractable | gap_unrecoverable`
   - `value`
   - `bound_ev_id`
   - `source_span` or equivalent evidence locator

   Then render prose from that payload. Without this, the architecture is still partly "narrate then inspect" instead of "instantiate schema then fill."

2. **M-58 enrichment boundary**: keep slot filling strict one-row-one-slot for completion accounting. If enrichment rows are allowed at all, they belong to Layer 5 and must not count toward required-field completion for the slot.

3. **M-59 acceptance criteria**: require exact validator outputs per slot and per field, not just a binary subsection pass/fail. The validator should emit a slot coverage object consumable by M-60 manifest rendering.

4. **M-60 manifest structure**: add machine-readable metadata for every incomplete slot:
   - `slot_id`
   - `entity_id`
   - `status`
   - `failure_reason`
   - `retrieval_attempt_log`
   - `available_artifacts` (`metadata_only`, `abstract_only`, etc.)
   - `human_completion_eligible`

   The prose gap paragraph is appropriate for `report.md`, but it is not enough by itself.

5. **M-60 report language**: keep the explicit clinician-facing sentence, but avoid overfitting it to one publication string. Template it from structured metadata so the report is explicit and consistent.

6. **M-61 provenance hardening**: replace free-text-only `consent_proof` with a structured provenance object. Minimum fields:
   - `curator_id`
   - `source_type`
   - `source_locator` (DOI + page range or equivalent)
   - `acquired_at`
   - `artifact_sha256` of the retained PDF/page image/snippet
   - `artifact_retention_path` or audit pointer
   - `quote_page_range`
   - `attestation`

   Human-curated rows should remain permanently flagged in evidence, manifest, and rendered Methods disclosure.

7. **M-61 verification scope**: `strict_verify` may verify quote-to-row consistency, but it cannot verify quote-to-original-source authenticity for human-curated content. The plan should state that explicitly and treat provenance assurance as audit-log + retained-artifact based, not as solved by `strict_verify`.

8. **M-62 generalization proof**: materials is acceptable as a low-friction smoke, but not sufficient alone. Add tests that prove `frame_compiler` and slot rendering work with arbitrary entity types, not just `pivotal_trial` / `mechanism_primary` / `regulatory`.

## Answers to Claude's 5 self-critical questions

1. **M-54 + M-55 + M-56 ordering**: the current ordering is correct. Do not lead with M-56. The fetcher should be driven by a compiled contract, not the other way around. A small M-56 feasibility spike is fine, but the implementation order should stay schema -> compiler -> deterministic fetcher.

2. **M-58 slot-bound prompt**: strict one-row-one-slot for required-field completion. Do not allow enrichment-row references inside the completion contract. If you want corroborative or contextual references, add them only in Layer 5 enrichment and do not let them satisfy required fields for the slot.

3. **M-61 fraud risk**: no, a `consent_proof` string is not sufficient. Require retained-source provenance with structured locator data plus an artifact hash and audit retention. Otherwise a fabricated quote can self-consistently pass through `strict_verify`.

4. **M-62 non-clinical template choice**: policy is the highest-value regression if the goal is architectural proof, because it stresses non-DOI / non-paper entity types and mixed source forms. Materials is acceptable as an easier secondary smoke because it remains DOI-centric and open-access-friendly. ML benchmarking is the weakest choice here because its artifacts and conventions are less stable and more heterogeneous in ways that blur the architectural question.

5. **Frame-element cap / cost concern**: 16 deterministic fetches plus 16 slot-bound generations is not a concern. The fetch cost is trivial and the generation count is moderate. The real engineering cost is correctness, validation, and auditability, not runtime. I would not optimize this away now.

## Completeness review

Claude did not miss the main architectural move. The plan does match the V29 framing on the essentials:

- the missing layer is a query-specific report contract
- every slot exists even when partially empty
- `strict_verify` remains strict
- hybrid human/licensed completion is the strongest non-band-aid companion

The main drift is that M-58/M-59 still read like prose-generation mechanics rather than true schema instantiation. That is the most important completeness gap.

On the two specific areas you flagged:

- **M-61 fraudulent human completion**: no, it does not yet protect adequately. Permanent `human_curated` labeling is necessary but not sufficient. Stronger provenance retention is required.
- **M-60 honesty-under-failure**: the proposed sentence is directionally right, but by itself it is below the honesty standard. Honest failure needs both reader-facing explicit prose and machine-readable failure metadata with retrieval-attempt traceability.

Additional completeness item Claude missed:

- The plan needs an explicit intermediate artifact for slot coverage at field granularity. Otherwise M-59 and M-60 are forced to infer completion from prose, which recreates a softer version of the same architectural problem.

## Implementation order confirmation

Use this order:

1. M-54 contract schema + loader
2. M-55 frame compiler
3. M-56 deterministic frame fetcher
4. M-57 contract-instantiated outline
5. M-58 structured slot-fill contract plus rendering prompt
6. M-59 slot/field completion validator
7. M-60 explicit gap rendering + manifest coverage report
8. M-61 human/licensed completion sidecar, but classify it operationally as an alternate evidence-ingest path feeding the same frame rows, not as a Layer 4 generation primitive
9. M-62 non-clinical generalization guard after 1-7, with stronger entity-type coverage than materials-only smoke

So: **CONDITIONAL-no-blocker for starting M-54**, but M-58/M-59/M-60/M-61/M-62 should be revised as above before those items are considered complete.
