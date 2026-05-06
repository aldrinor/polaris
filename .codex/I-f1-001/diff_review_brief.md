# Codex Diff Review Brief — I-f1-001 (ITER 1)

**Iter:** 1 of N (no hard cap per CLAUDE.md §8.3.1)

This is the SECOND of two Codex review gates for Issue I-f1-001 per plan §7.A LOCKED A2 + §3.0 5-artifact contract:

1. ✅ **Brief review** (Codex APPROVE iter 2): see `.codex/I-f1-001/codex_brief_verdict.txt`. Acceptance criteria correct.
2. ⏳ **Diff review** (this brief): Red-Team checklist on the actual code change.

## Hard requirements for this iter

1. **Static review only.** Do NOT attempt to run Playwright (requires Next.js dev server + Chromium download in Codex sandbox; will produce environmental errors irrelevant to code correctness). The empirical TypeScript + lint verification is included below.
2. **Emit the YAML schema block.**
3. **List ALL findings this iteration. No toothpaste-squeeze. Same quality bar.**

## Empirical verification (Claude verified)

- `npx tsc --noEmit -p .` from `web/` → no errors. (Confirmed silently via tool output.)
- `npm run lint` from `web/` → my new/modified files (`web/app/page.tsx`, `web/tests/e2e/landing_template_grid.spec.ts`, `web/tests/e2e/demo_walkthrough.spec.ts`, `web/scripts/capture_screenshots.mjs`) emit zero errors. The 5 errors reported are PRE-EXISTING in `web/app/benchmark/components/benchmark_board.tsx`, `web/app/benchmark/page.tsx`, `web/app/generation/components/generation_runner.tsx`, `web/app/generation/page.tsx`, `web/app/inspector/[runId]/page.tsx`, plus `web/.tmp_screenshots/walkthrough.js`. None are introduced by this diff.

## Artifacts under review

- `.codex/I-f1-001/brief.md` — Codex APPROVE'd iter-2 spec
- `.codex/I-f1-001/codex_diff.patch` — canonical PR diff with `# canonical-diff-sha256: cd67572919774f79bc3f6f350f5ade164ca5651948b874d2c69e57283573d76f` trailer
- `outputs/audits/I-f1-001/claude_audit.md` — Claude self-audit

## Files in this diff (5 files, +257 / -120 = +137 net)

```
web/app/page.tsx                                 MOD    +145 / -53   (replace demo_slices with 8-template grid)
web/tests/e2e/landing_template_grid.spec.ts      NEW    +86          (4 viewports + axe-core + 8-card visibility)
web/tests/e2e/home_walkthrough.spec.ts           DEL    -40          (retired — coverage migrates)
web/tests/e2e/demo_walkthrough.spec.ts           MOD    +25 / -27    (entry-point switch; drop Step badges)
web/scripts/capture_screenshots.mjs              MOD    +1 / -1      (description text)
```

LOC: 137 net within 150 budget. No overrun.

## Specific risks for Codex Red-Team

1. **CHARTER §3 LOC budget compliance.** +137 net within 150 budget. Pass.

2. **Card grid Tailwind v4 breakpoint mapping** — `grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4`. Verifies: 1920px → xl (≥1280) → 4-col; 1024px → lg (≥1024 <1280) → 3-col; 768px → md (≥768 <1024) → 2-col; 375px → base (<640) → 1-col. The viewport tests assert card visibility at all 4 sizes; layout column count is implied by Tailwind class semantics, not asserted directly via DOM. Codex: confirm this mapping is sufficient OR escalate to add per-viewport column-count assertions.

3. **Disabled cards a11y** — to-build cards have `aria-disabled="true"` on the `Card` component (a `div`), no `<Link>`, plus a fallback `<Button disabled tabIndex={-1} aria-disabled="true">Coming soon</Button>` that prevents keyboard activation. shadcn/ui `Card` is a div; `aria-disabled` on a div is informative but not interactive — does the axe-core scan flag this as misleading? My read: `aria-disabled` on a div is acceptable (WAI-ARIA permits it on widgets and group containers); the disabled `<Button>` provides the actual interaction barrier.

4. **`getByTestId("template-card-clinical-link")` resolution** — the link test-id is set on the `<Link>` element via `data-testid={...}-link`, not the wrapping `<Card>` (which has `data-testid={...}` without `-link`). Updated `demo_walkthrough.spec.ts` line 28-31 uses `template-card-clinical-link` directly, which resolves to the `<a>` element and supports `.click()`. Verify this resolution path works in Next.js 16's Link rendering (the `<Link>` renders `<a>` by default in Next 16 per the breaking-changes guide). Codex: confirm OR flag if any Next 16 Link rendering quirk affects testid propagation.

5. **Out-of-scope examples vs `out_of_scope_examples` schema** — brief acceptance #1 says "1 out-of-scope example (if non-empty)". I always render the out_of_scope line because every template's JSON has at least one entry. If a future template has empty `out_of_scope_examples`, the hardcoded card data would still ship a string (the embedded data has fallback text). Acceptable for hardcoded approach; runtime fetch (I-f1-007) would need a fallback path.

6. **Removed `demo_walkthrough.spec.ts` Step-badge test** — original test #3 asserted the presence of "Step 1".."Step 4" text. Those CardDescription strings no longer exist on the new home (template grid has no step labels). Removing the test is honest — coverage migrated to landing_template_grid.spec.ts which validates the new contract.

7. **Visual regression policy** — screenshots stored at `web/tests/e2e/screenshots/landing_template_grid_<vp>.png`. CI does not enforce pixel-diffing on Linux per existing `web_ci.yml` policy. Test asserts DOM presence + `data-testid` visibility. No false-negatives via missing baselines.

8. **Header preserved.** The 4-step demo flow (intake/retrieval/generation/benchmark) is no longer surfaced from `/`. Direct-URL access still works (`/intake`, `/retrieval`, `/generation`, `/benchmark`). The `demo_walkthrough.spec.ts` updated test confirms direct-URL navigation. Acceptable per F1 spec which calls for template-browse landing.

9. **`canonical-diff-sha256` trailer correctness** — `cd67572919774f79bc3f6f350f5ade164ca5651948b874d2c69e57283573d76f` produced via `git diff --cached -- ":(exclude).codex/I-f1-001/" ":(exclude)outputs/audits/I-f1-001/"`. CI's extraction: `grep -E '^# canonical-diff-sha256: [a-f0-9]{64}$' | tail -1 | awk '{print $3}'`.

10. **CI does NOT run the new spec** (Codex iter-2 P2-iter-2-001) — acknowledged in claude_audit.md as deferred. Adding a CI step would touch `.github/workflows/web_ci.yml` (CODEOWNERS-protected); separate Issue.

## Output schema (mandatory)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.

List ALL findings this iteration. Do NOT hold any back to drip-feed across iterations. Same quality bar regardless of iteration count. No hard cap on iterations.
