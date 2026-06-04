# Codex diff review — sub-PR 3b chip restore (#900)

## §0 cap directive (abbreviated)

```
HARD CAP 5. iter 1. Verdict APPROVE iff zero P0+P1.
```

## Phase

Diff review. Single-file restore of `web/app/intake/components/auto_domain_chip.tsx`.

## What changed

ONE file added: `web/app/intake/components/auto_domain_chip.tsx` (188 LOC) — verbatim restoration from sub-PR 3's original commit `6a6c73f2` (before the descope `bc419a76`).

## Why

Per #886 root-cause investigation 2026-05-25:
- Chip renders correctly in PRODUCTION builds (`next start`, what CI + deployed Polaris run)
- Failure during sub-PR 3 dev was a Turbopack-dev-mode HMR WebSocket handshake issue on Windows
- The descope on sub-PR 3 was both over-conservative AND incomplete: it deleted the file but left the `import` and `<AutoDomainChip>` JSX mount in `intake_form.tsx` (and the chip-related test cases in `intake_v6.spec.ts`). This is why PR #885's lint+typecheck CI is currently FAILING.

Restoring the file:
1. Completes the integration the commit-message claim of sub-PR 3 promised
2. Fixes PR #885's CI failure (TS2305 "module not found")
3. Enables the chip to ship to Carney's demo (since CI + prod run `next start`)

## Specific checks

- `chip_file_verbatim_from_6a6c73f2`: PASS / FAIL — content matches the original commit
- `intake_form_already_imports_chip`: PASS / FAIL — `intake_form.tsx` on this branch has the import + JSX mount (no edit needed)
- `intake_v6_spec_already_tests_chip`: PASS / FAIL — `intake_v6.spec.ts` on this branch has the chip-related test cases (no edit needed)
- `typecheck_passes_locally`: PASS / FAIL — `npm run typecheck` returns 0 errors
- `fixes_pr_885_typecheck_failure`: PASS / FAIL — when merged on top of sub-PR 3, the missing-module import error is resolved
- `prod_build_renders_chip`: PASS / FAIL — confirmed via debug page `web/app/debug_chip/page.tsx` (now deleted; results in #886 comment)

## Output schema (BIND)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
specific_check_responses:
  chip_file_verbatim_from_6a6c73f2: PASS | FAIL_with_detail
  intake_form_already_imports_chip: PASS | FAIL_with_detail
  intake_v6_spec_already_tests_chip: PASS | FAIL_with_detail
  typecheck_passes_locally: PASS | FAIL_with_detail
  fixes_pr_885_typecheck_failure: PASS | FAIL_with_detail
  prod_build_renders_chip: PASS | FAIL_with_detail
```
