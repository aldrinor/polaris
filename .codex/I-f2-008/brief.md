# Codex Brief Review — I-f2-008 (ITER 2 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 2 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f2-008 — F2 evaluator walkthrough
**LOC budget:** 0 per breakdown (originally "no code; walkthrough"). Reframed: automated walkthrough script + Codex sign-off. **CHARTER §1 hard cap: 200.**

## Reframe (per user directive 2026-05-06: "Codex is the guy who signs, not me")

Original breakdown: "product-owner walkthrough; record-screen 3 sessions × 22-input corpus." Reframed: automated Playwright walkthrough that exercises the 22-input corpus against the F2 surfaces, captures DOM state per scenario, produces a transcript document, and submits to Codex for the "all 22 handled correctly per recording review" sign-off. Codex review IS the acceptance gate (per user 2026-05-06).

## Iter-1 verdict resolution (REQUEST_CHANGES → addressed in this iter 2)

**P1 #1 (MS/PR 2-char inputs rejected by length<3 gate):** ADDRESSED. Replaced with `"MS treatment options"` (multiple sclerosis vs Microsoft) and `"PR campaign metrics"` (public relations vs progress report) — both >3 chars and still ambiguous-entity targets.

**P1 #2 (LOC accounting omits committed transcript):** ADDRESSED. Transcript is NOT committed. The acceptance doc `walkthrough_acceptance.md` IS the durable 22-scenario table, hand-filled by Claude after running the spec locally once; the test's runtime-generated transcript is gitignored. Codex reviews the static acceptance doc + the spec source.

**P2 #1 (chromium-only run):** ADDRESSED. Spec uses `test.skip(({browserName}) => browserName !== "chromium", "f2 walkthrough is chromium-only")` to short-circuit firefox + webkit projects. Transcript writes are now also no-op'd outside chromium, so re-running across projects does not corrupt the artifact.

**P2 #2 (very-long-input expected behavior):** ADDRESSED. Pinned to client-side `maxLength={2000}`: the test types 2500 chars and asserts the input's `value.length === 2000` (browser truncation; no API call, no error message). The backend's `too_long > 1000` cutoff is server-side and not exercised here.

## Mission

Author one Playwright walkthrough spec that walks through 22 F2 scenarios end-to-end, captures pass/fail + DOM observables per scenario, and writes a structured transcript to `outputs/audits/I-f2-008/walkthrough_transcript.md`. The transcript is then submitted to Codex along with this brief's acceptance criteria for the "all 22 handled correctly" verdict.

The 22-input corpus covers the F2 acceptance surface:
- 3 ambiguous-query positives (modal fires with N clusters): "BPEI" / 3 clusters; "MS treatment options" / 2 clusters; "PR campaign metrics" / 5 clusters.
- 3 unambiguous-query negatives (no modal): "tirzepatide ...", "metformin ...", "aspirin ...".
- 3 needs_disambiguation=true + is_ambiguous=false negatives (defensive guard): same 3 unambiguous queries with backend mocked to return is_ambiguous=false despite needs_disambiguation=true.
- 3 French-language inputs (English-only message, no API call): canonical French clinical questions.
- 3 PDF-drop scenarios: PDF mime type; PDF .pdf extension only; non-PDF (no banner).
- 3 edge cases: empty input (existing 3-char gate), very-long input (existing 2000-char limit), pure-whitespace input.
- 4 cluster-pick post-state assertions: BPEI pick cluster_id=0 / 1 / 2; assert label flows to parent.

Total: 22 scenarios.

## Substrate (HONEST)

- I-f2-002 through I-f2-007 merged: cluster_labeler, /api/disambiguation, DisambiguationModal, intake page wiring, BPEI e2e, negative tests, French heuristic, PDF banner.
- `web/tests/e2e/intake_disambiguation.spec.ts` (positive BPEI), `intake_disambiguation_negative.spec.ts` (2 negative cases), `intake_edge.spec.ts` (French + PDF) cover ~7 of the 22 scenarios. This Issue extends to the full 22.
- `web/playwright.config.ts` runs against `next start` per existing pattern.

## Acceptance criteria (binding)

1. **`web/tests/e2e/f2_walkthrough.spec.ts`** (NEW): one parametrized Playwright spec walking through 22 scenarios. For each scenario:
   - Description string (e.g. "BPEI / 3 clusters / fires modal").
   - Setup: mock /api/intake + /api/disambiguation per scenario fixture.
   - Action: type input, submit (or drop file for PDF tests).
   - Assertion: scenario-specific (modal visible / hidden / French error / PDF banner / etc.).
   - On success/failure, append a row to a `transcript[]` array.
   - At spec teardown: write `transcript[]` as Markdown to `outputs/audits/I-f2-008/walkthrough_transcript.md`.
   - LOC: ~140 pre-Prettier (parametrization keeps duplication low).

2. **`outputs/audits/I-f2-008/walkthrough_acceptance.md`** (NEW): the durable, committed walkthrough deliverable. Hand-filled by Claude AFTER running the spec locally once. Contains:
   - The 22 scenarios in a table (description / expected outcome / observed outcome / verdict).
   - User-directive reframe ("Codex signs, not user").
   - Run command: `cd web && npx playwright test --project=chromium tests/e2e/f2_walkthrough.spec.ts`.
   - LOC: ~50.

3. **`outputs/audits/I-f2-008/.gitignore`** (NEW, 1 line: `walkthrough_transcript.md`): keeps the runtime transcript out of git so LOC budget covers only the static acceptance doc + spec.

## Planned diff shape

```
web/tests/e2e/f2_walkthrough.spec.ts                        NEW +140
outputs/audits/I-f2-008/walkthrough_acceptance.md           NEW +50
outputs/audits/I-f2-008/.gitignore                          NEW +1
```

LOC: +191 net pre-Prettier. CHARTER §1 200-cap headroom: 9. The runtime transcript is gitignored — does NOT count toward LOC.

## Out of scope

- Real recording of human walkthrough sessions → user-driven if they wish to record; not blocking this Issue.
- Backend writer for `needs_disambiguation` + `candidate_snippets` → I-f2-005a (already named follow-up).
- F3 issues → start after I-bug-079.

## Risks for Codex Red-Team

1. **Prettier reflow over LOC cap.** 190 net is tight. Mitigation: parametrized scenarios via `for (const scenario of SCENARIOS)`. If reflow still pushes over, scenarios live in a separate fixture file (`f2_walkthrough_fixtures.ts`) to keep the spec under cap.

2. **22-scenario coverage.** Brief enumerates 22; if Codex wants different coverage, brief author commits to swapping in iter 2.

3. **Transcript artifact.** `walkthrough_transcript.md` is generated by the test (writeFile in `afterAll`). The artifact is committed in the same PR by Claude post-test-run (via `git add` after running the test once locally). The transcript IS the deliverable Codex reviews for the "all 22 handled correctly" verdict.

4. **Test runtime.** 22 scenarios × ~1s each ≈ 22s. Single Playwright project (chromium). Acceptable.

5. **Mocks reused from prior tests.** /api/intake + /api/disambiguation route patterns from I-f2-005, I-f2-006 are reused. No new infrastructure.

6. **Edge case: pure-whitespace input.** Existing form trims and gates on `length < 3`; pure-whitespace passes through `trim()` + length check. Test asserts the existing error message displays.

7. **PDF-drop scenarios share the hydration-race guard from I-f2-007.** Wait for `pdf-drop-ready` `data-ready="1"` before dispatching synthetic DragEvent.

8. **Cluster-pick post-state.** 4 sub-tests covering cluster_id=0/1/2 plus a Cancel-only path asserting `disambig-picked-label === ""` (no write on cancel).

9. **CHARTER §1 LOC cap.** 190 net, tight. Brief author commits to fixture-extraction if reflow drives over.

10. **No new package.json dep.**

11. **`afterAll` write to outputs/audits/I-f2-008/.** Playwright supports `afterAll` hooks; `writeFileSync` from `node:fs`. The transcript path is repo-relative.

12. **Test idempotency.** Re-running overwrites the transcript. Each run produces a fresh artifact that reflects the latest pass/fail state.

13. **Codex review of transcript.** The transcript table includes per-scenario verdict (PASS/FAIL). Codex reviews the table and the underlying spec to confirm coverage matches the 22-scenario corpus + each verdict is justified.

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
