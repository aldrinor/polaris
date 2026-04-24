M-63 code audit pass-2 — xhigh reasoning.

**Skip git status.** Codex at gpt-5.4 + xhigh (project default).

## Context

Pass-1 verdict was REJECT with 3 blockers + 3 mediums at
`outputs/codex_findings/m63_code_audit/findings.md`. Claude fixed
all six in commit `dc29e56`. This is the pass-2 audit to verify
the fixes are correct and complete.

## Pass-1 issues + how Claude claims to have fixed them

### Blocker 1 — M-44 outline injection erased ContractSectionPlanExt

**Claim**: `_m44_inject_primaries_into_outline` in
`src/polaris_graph/generator/multi_section_generator.py:2430-2450`
now short-circuits on `isinstance(plan, ContractSectionPlanExt)`
and passes the plan through unchanged (identity preserved), with
an `action=skipped_contract_plan` log entry.

**Verify**:
- Does the new type check fire before the `_m44_section_is_primary_eligible`
  branch? I.e., does it take precedence over the legacy SectionPlan
  handling?
- Is the import (inside the function body) stable against circular-
  import concerns?
- Does `_bounded_run` now actually see the ContractSectionPlanExt
  and dispatch to `run_contract_section`?
- Is there any OTHER place that rebuilds plans as plain SectionPlan
  after M-44? (Search for `SectionPlan(` constructions between
  M-44 call site and `_bounded_run`.)

### Blocker 2 — non-gap LLM-exception hit compose_gap_payload's hard raise

**Claim**: `_fill_one_slot` in
`src/polaris_graph/generator/contract_section_runner.py:176-213`
now calls a new helper `_build_not_extractable_payload` for both
the LLM-exception path AND the parse-failure path, producing an
all-`not_extractable` payload that cites `bound_ev_id=entity_id`.
Gap-path still uses `compose_gap_payload` correctly.

**Verify**:
- Does `_build_not_extractable_payload` produce a valid
  SlotFillPayload that M-59 surfaces as FAIL_MIN_FIELDS
  (curator-actionable), not silently dropped?
- Is `provenance_class=frame_row.provenance_class.value` correct
  (preserves the original non-gap class) vs a gap-like override?
- Added regression test
  `test_blocker2_non_gap_llm_exception_does_not_raise` — does it
  actually exercise the exception path on a non-gap row?

### Blocker 3 — run_contract_section didn't match legacy shape

**Claim**: Rewritten `run_contract_section` in
`contract_section_runner.py:232-420`:
- Builds `raw_draft` as body-only prose (no `### Heading` lines)
- Runs rewrite → strict_verify → `resolve_provenance_to_citations`
  → gets flat `resolved_body` + populated `biblio_slice`
- Re-iterates kept sentences, groups by originating slot via
  `tokens[0].evidence_id → entity_to_slot_id`, builds per-slot
  sentence lists with `[N]` markers, emits verified_text with
  `### subsection_title` headings
- Falls back to `resolved_body` when kept > 0 but grouping
  fails (no tokens)

**Verify**:
- Does the per-sentence re-resolution logic agree with
  `resolve_provenance_to_citations`'s acceptance rules (≥3 content
  words, ≥15 chars, `\s+([.!?,;])` whitespace cleanup)?
- Is the citation-number assignment consistent with the
  flat-resolution biblio_slice? (First-appearance order,
  1-based.)
- Does the fallback path (`resolved_body` when grouping fails)
  match the legacy shape (`[N]` citations + biblio_slice)?
- Are the `biblio_slice` entries compatible with
  `_merge_bibliographies` + `_remap_section_markers_to_global`
  downstream? I.e., does each entry carry `num`, `evidence_id`,
  `url`, `tier`, `statement`?
- What happens if all kept sentences have `tokens[0].evidence_id`
  NOT in `entity_to_slot_id` (cross-section citation)? Code
  continues — is that the right semantic?

### Medium 1 — ev_ids was slot[0] only

**Claim**: Sweep runner `run_honest_sweep_r3.py:1099-1123` now
unions entity_ids from ALL slots in first-appearance order.

**Verify**:
- Is the ordering stable across runs?
- Does the union preserve the "primary entity first" convention
  that M-42e assumes?
- Are duplicate entity_ids (same entity in multiple slots)
  collapsed correctly?

### Medium 2 — M-50 didn't skip contract-anchored anchors

**Claim**:
- New parameter `m50_skip_anchors: set[str] | None` on
  `generate_multi_section_report`
- `_m50_select_candidate_trials` call site strips
  `direct_set - m50_skip_anchors` before selection
- New sweep helper `_compute_m50_skip_anchors` does
  normalized-substring match between contract entity_ids and
  primary_trial_anchors

**Verify**:
- Substring match correctness:
  - `surpass_2_primary` normalized = `surpass2primary`
  - `SURPASS-2` normalized = `surpass2`
  - `surpass2 in surpass2primary` = True ✓
- False-positive risk: `surpass_2_primary` also substring-matches
  `SURPASS-2`. What about `surpass_20_primary` vs `SURPASS-2`?
  `surpass2` matches `surpass20primary` → would falsely suppress
  SURPASS-2 for a SURPASS-20 entity. Is that a real risk with
  the current anchor set?
- Is `m50_skip_anchors=None` a true no-op (default path)?

### Medium 3 — evidence-pool namespace collision

**Claim**: Fix at BOTH layers:
1. M-54 loader
   (`src/polaris_graph/nodes/report_contract.py:258-288`)
   rejects `^ev_\d+$` entity ids AND non-ASCII entity ids at
   schema-load time
2. `register_frame_rows_into_evidence_pool`
   (`contract_section_runner.py:116-141`) raises ValueError
   when the pool has a non-v30_frame_row entry at the target key

**Verify**:
- Is the M-54 regex `^ev_\d+$` exactly the live-retrieval format?
  (Check `src/polaris_graph/retrieval/live_retriever.py` for the
  counter format.)
- Does the ASCII-only check catch all non-ASCII that would break
  the sentence splitter, or could unicode spaces / zero-width
  characters slip through?
- Does the defense-in-depth register raise actually surface
  loudly, or is it caught somewhere in the runner's exception
  handler and silently swallowed?
- Does the raise happen BEFORE any LLM token is billed? (Check
  call order in sweep runner Phase-2 prep block.)

### New regression tests Codex asked for

Pass-1 findings §Next item 5: "Add a real
`generate_multi_section_report(..., v30_contract_plans=...)`
integration test before rerunning the audit."

**Verify**: Does the new `TestCodexM63RejectRegressions` class
actually exercise the full dispatch path from
`generate_multi_section_report` through `_bounded_run` to
`run_contract_section`? If not, is there a reason to defer that
test to M-64 integration (where the real live_corpus + contract
compile happens)?

## Scope gate

Also verify: the 19 pre-existing test failures Claude reports
unrelated to Phase-2 (M-42 NICE, M-36 trial summary mocks, M-49
V28 preservation, test_m201 selection, test_m207 invariant,
test_manifest_contract) — are those actually pre-existing, or
did the M-63 changes mask a real regression?

## Output

Write to `outputs/codex_findings/m63_code_audit/pass2_findings.md`.

Format:
```markdown
# Codex M-63 pass-2 audit

**Verdict**: APPROVED | CONDITIONAL-no-blockers | CONDITIONAL-blockers | REJECT

## Pass-1 issue resolution status

1. Blocker 1 (M-44 type erasure): RESOLVED | PARTIAL | NOT_RESOLVED — <why>
2. Blocker 2 (LLM-exception fallback): ...
3. Blocker 3 (SectionResult parity): ...
4. Medium 1 (ev_ids union): ...
5. Medium 2 (M-50 skip): ...
6. Medium 3 (pool collision): ...

## New findings (if any)

<blockers, mediums, nits with file:line>

## Scope regression sanity check

Pre-existing 19 failures: <CONFIRMED pre-existing | found real
regression at ...>

## Next

On APPROVED / CONDITIONAL-no-blockers: Claude proceeds to M-64
(validator promotion — real M-59 against actual SlotFillPayloads,
drop `phase1_retrieval_coverage_only` warning, add
`phase2_report_coverage` semantic marker). On REJECT: Claude
fixes + resubmits pass-3.
```

Keep under 200 lines. Full xhigh reasoning budget. M-63 pass-2
is the last gate before Phase-2 full-scale sweep can run.
