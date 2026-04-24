M-55 code audit — tight.

**Skip git status.** Loopback/audit/ deletions remain from prior
cleanup; unrelated to M-55. Read only the three files named below.

## Scope

Commit `471613d`. Three files:

1. `src/polaris_graph/nodes/frame_compiler.py` (~230 lines) —
   M-55 compiler implementation. New module.
2. `tests/polaris_graph/test_m55_frame_compiler.py` (~500 lines) —
   35 tests in 11 classes.
3. `src/polaris_graph/nodes/report_contract.py` (M-54, already
   approved) — ONLY re-read if you need to verify compiler uses
   M-54 loader correctly.

Do NOT re-read the V30 plan or your prior M-54 findings.

## Your pass-1 revision to verify

You required: "**M-55 | root_cause_approved_with_revision**. Needs
one explicit guard against clinical hardcoding: compiler tests must
prove arbitrary entity types and slot types compile without code
changes."

Look at `TestEntityTypeAgnostic` (4 tests): does it satisfy that
revision?

## Questions

1. **Entity-type-agnostic guard**: `TestEntityTypeAgnostic` proves
   statute / dft_primary / unknown_xyz_2099 / mixed-types compile.
   Sufficient for your rev #7 requirement?
2. **Identifier priority order**: DOI > PMID > url_pattern >
   anchor. PMID=0 treated as non-identifier. Agree with priority
   and with the PMID=0 sentinel treatment?
3. **No-identifier rejection**: structurally valid contract entity
   with zero identifiers raises `FrameCompilerError` at M-55 (not
   M-54 loader). That enforces "must be retrievable" at the
   compilation stage. Correct layer for this check?
4. **Schema-version forward-compat**: unknown schema_version emits
   warning into `CompiledFrame.warnings` (doesn't abort). Agree
   with soft-warning semantics at M-55?
5. **Deterministic ordering**: sorted by
   `(slot.section, slot.ordering, entity.id)`. Sections compared
   alphabetically (no template-level section_order yet). Any
   concern that alphabetic section order could be wrong for the
   clinical template? (Efficacy < Mechanism < Regulatory
   alphabetically happens to match the plan; luck or intentional?)
6. **Domain-inheritance descoped** (carried from M-54): V30 ships
   one slug; `extends:` composition deferred until a second use-
   case is concrete. Match your architectural intent, or do you
   want a minimal `extends:` now?
7. **ContractSchemaError propagates from M-54**: `compile_frame`
   does not swallow M-54 shape errors. Correct layering?
8. **`research_question` pass-through**: empty string accepted;
   non-string raises. No semantic validation (e.g. no check that
   question mentions the slug topic). Correct — M-55 is pure
   structure, not semantics?

## Output

Write to `outputs/codex_findings/m55_code_audit/findings.md`.

Format:
```markdown
# Codex M-55 audit

**Verdict**: APPROVED | CONDITIONAL-no-blockers | CONDITIONAL-blockers | REJECT

## Answers

1. Entity-type-agnostic guard: ...
2. Identifier priority: ...
3. No-identifier rejection at compiler: ...
4. Schema-version forward-compat: ...
5. Deterministic ordering: ...
6. Domain-inheritance descoped: ...
7. Schema errors propagate: ...
8. research_question pass-through: ...

## Findings

<blockers, mediums, nits with file:line>

## Next

On APPROVED / CONDITIONAL-no-blockers: Claude proceeds to M-56
(deterministic DOI/PMID/Unpaywall retriever).
```

Keep findings.md under 120 lines. Terse beats verbose.
