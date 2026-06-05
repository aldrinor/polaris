# Codex DIFF-gate — I-ready-009 (#1081): non-clinical domain-neutral outline (generator-only)

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE'd on remaining-non-P0/P1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## REVIEW ONLY — DO NOT MODIFY ANY FILE
Return ONLY the YAML verdict. **Do NOT edit/create source/test files, do NOT write a patch.** You are
the independent reviewer of an already-committed diff.

## ITER-1 RESOLUTION (you returned REQUEST_CHANGES with 1 P1 — fixed; re-verify)
Your iter-1 P1 was real: `_call_outline`'s RETRY prompt was still built from the clinical
`OUTLINE_SYSTEM_PROMPT` + hard-coded clinical section names, so a non-clinical retry leaked clinical
guidance then got parsed out against the generic allow-list (forcing the deterministic fallback). FIXED:
the retry `tighter_system` now branches by domain — clinical/unknown is BYTE-IDENTICAL (unchanged
clinical hard requirements); non-clinical bases on the selected `_outline_system_prompt` (generic) +
domain-neutral hard requirements (4-6 sections, >=8 ev_ids, generic title list, no clinical section
names). +2 behavioral retry tests added (a FORCED retry: non-clinical retry has zero clinical leak;
clinical retry byte-identical). 29 tests + 140 multi_section/outline regression green. Your iter-1
confirmations stand (planner_untouched / clinical_byte_identical / faithfulness_machinery_untouched =
yes). **Re-verify the retry path now applies the generic switch end-to-end and clinical retry is
unchanged.**

## What this is
The committed diff implementing the brief you APPROVE'd at iter-2 (contract-preserving generator-only
outline-set switch; generic_set; clinical-3 byte-identical; parts b/c dropped). Patch:
`.codex/I-ready-009/codex_diff.patch` (HEAD 590e29de, branch bot/I-ready-009-generator-shape, stacked
on bot/I-ready-013). Files: `multi_section_generator.py`, `run_honest_sweep_r3.py` (+4), the test file.

## The fix
Non-clinical questions were forced into clinical section headers (Efficacy/Safety/Population Subgroups).
Now: `_allowed_sections_for_domain(domain)` + `_ALLOWED_SECTIONS_GENERIC` (clinical/unknown keep the
clinical `_ALLOWED_SECTIONS` byte-identical; else the generic set) + `OUTLINE_SYSTEM_PROMPT_GENERIC` +
`_select_outline_system_prompt(domain)`, threaded through `_call_outline`, `_parse_outline` (new
`allowed_sections` param), the deterministic fallback, `generate_multi_section_report` (new `domain`
param), and the `run_one_query` call (`q["domain"]`).

## Verify (this is the §-1.1 generator surface — the same things your iter-1 brief review flagged)
1. **The planner is NOT touched.** Confirm NO `PG_USE_RESEARCH_PLANNER` is read or written anywhere in
   the new code, and the outline-set switch never reads `research_plan`. So V30 `per_query_report_
   contract` / scope template / amplified are preserved (your iter-1 P1-1), and there is NO `--all`
   env leak (your iter-1 P1-2) — the domain is a pure per-call function arg.
2. **The clinical section-PROSE prompt is UNCHANGED for ALL domains.** Confirm
   `_select_section_system_prompt` still keys on `use_field_agnostic` (planner), NOT on the new domain
   switch — so rules 1-13 incl. primary-source-over-derivative + jurisdiction are preserved for
   non-clinical too (your iter-1 P1-3). We do NOT route to the field-agnostic template.
3. **Clinical-3 byte-identical.** `_allowed_sections_for_domain("clinical")` / `("")` ==
   `_ALLOWED_SECTIONS`; `OUTLINE_SYSTEM_PROMPT` is unchanged (still contains Efficacy/SURPASS/Mechanism);
   `_select_outline_system_prompt("clinical")` returns it. A clinical run is byte-for-byte the same.
4. **No over-reach.** The generic outline prompt drops the clinical section-name rules (M-40/SURPASS/
   Efficacy-Safety) that would contradict the generic title list, but KEEPS the T1-T7 tier hierarchy +
   primary-source + injection-as-data discipline. The deterministic fallback is domain-aware too.
5. **strict_verify / 4-role D8 / provenance / two-family UNTOUCHED** — confirm the diff touches only the
   generator outline path + the one `domain=` pass.

## Smoke evidence (offline, $0)
- 27 new tests (clinical & unknown byte-identical; non-clinical generic set with no clinical labels;
  outline-prompt selection; parse validation accepts/drops by set; domain-aware fallback; no-planner-env;
  generate has `domain` default ""; prose-prompt selection unchanged).
- 138 multi_section/outline regression tests green. py_compile clean. `git diff --stat` = only
  multi_section_generator.py + run_honest_sweep_r3.py (+ test).

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
planner_untouched: yes | no
clinical_byte_identical: yes | no
faithfulness_machinery_untouched: yes | no
```
