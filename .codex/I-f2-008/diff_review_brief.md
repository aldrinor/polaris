# Codex Diff Review — I-f2-008 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f2-008 — F2 evaluator walkthrough (reframed as automated, Codex-reviewed)
**Branch:** bot/I-f2-008
**Brief:** APPROVED iter 2 (iter1 REQ_CH 2P1 → iter2 APPROVE 0/0/3P2; all P2 addressed in implementation)
**Canonical-diff-sha256:** `524784e8dd9aa3c89e8a3a28e2190f76faca49005fca27a1288317ba210f56e9`
**LOC:** 335 net (over CHARTER §1 200-cap by 135) — **EXPLICIT LOC-CAP EXEMPTION REQUESTED, see below.**
**Format:** `npx prettier --check` clean.

## CHARTER §1 LOC-cap exemption ask

Original budget per `state/polaris_restart/issue_breakdown.md:332`: **"0 (walkthrough; no code)"**. The user-directive reframe (2026-05-06: "Codex signs, not user") replaces literal screen recordings with an automated 22-scenario Playwright walkthrough. The 22-scenario count is binding from the breakdown ("all 22 handled correctly per recording review"). 22 scenarios × ~12 LOC/scenario after Prettier reflow = ~264 LOC just for scenarios; plus shared mocks, transcript writer, type definitions = 276 LOC minimum.

Codex iter-1 brief P1 #2 said splitting fixtures does not reduce total net LOC. Splitting into 2 PRs would not reduce total net LOC; it would just spread it. The 200-cap exists to prevent scope creep — this PR is at the floor of "what does it take to deliver the binding 22-scenario walkthrough."

**Ask:** APPROVE this PR despite 335 LOC, given:
- Original budget was 0 (carve-out).
- Reframe is binding (user directive 2026-05-06).
- 22-scenario count is binding (breakdown).
- Spec is already minified (single test, parametrized scenarios, shared mock helpers).

If exemption denied → split into I-f2-008a + I-f2-008b at iter 2 (total LOC unchanged; spread across 2 PRs).

## Files

```
outputs/audits/I-f2-008/.gitignore                            NEW +1
outputs/audits/I-f2-008/walkthrough_acceptance.md             NEW +58
outputs/audits/I-f2-008/claude_audit.md                       NEW (excluded from canonical SHA per Issue convention)
web/tests/e2e/f2_walkthrough.spec.ts                          NEW +276
```

(Note: `outputs/audits/I-f2-008/` files are excluded from canonical-diff-sha256 per Issue convention but ARE present in the PR for Codex to read directly via filesystem. The canonical SHA captures only the spec + .gitignore + walkthrough_acceptance.md — wait, walkthrough_acceptance.md is also in `outputs/audits/I-f2-008/` so it's also excluded from the canonical SHA but PRESENT in the PR for review.)

## What changed

### `web/tests/e2e/f2_walkthrough.spec.ts`
Single chromium-only Playwright test that walks through 22 scenarios sequentially. Each scenario:
1. Sets up `page.route()` mocks for /api/intake + /api/disambiguation.
2. Submits a fixture input (or drops a synthetic file).
3. Asserts the expected DOM state via `[data-slot="disambiguation-modal"]` toBeHidden/Visible OR cluster-card count OR error message text.
4. Calls `record(description, expected, fn)` which appends PASS/FAIL to the `transcript[]` array.
5. Calls `page.unrouteAll()` between scenarios for isolation.

`afterAll` writes a markdown transcript table to `outputs/audits/I-f2-008/walkthrough_transcript.md` (gitignored). The static `walkthrough_acceptance.md` is the durable deliverable.

The 22 scenarios:
- 3 ambiguous (BPEI / MS treatment options / PR campaign metrics)
- 3 unambiguous (tirzepatide / metformin / aspirin)
- 3 is_ambiguous=false guard cases
- 3 French inputs
- 3 PDF drops (mime / extension only / non-PDF)
- 3 edge cases (empty / whitespace / very-long)
- 3 cluster picks (cluster_id 0/1/2)
- 1 cancel

### `outputs/audits/I-f2-008/walkthrough_acceptance.md`
Static 22-scenario table (description / expected / surface tested) + Codex acceptance criteria.

### `outputs/audits/I-f2-008/.gitignore`
`walkthrough_transcript.md` — keeps runtime artifact out of git per Codex iter-1 P1 #2.

## Iter-2 brief P2 advisories addressed

- **P2 #1 (stale committed-transcript wording):** Implementation does not commit transcript; .gitignore in place.
- **P2 #2 (root-relative path):** `path.resolve(__dirname, "../../../outputs/...")` — stable from `__dirname`.
- **P2 #3 (very-long-input no submit):** spec for `edge:long` only types + asserts value.length; no `intake-submit` click; `intakeCalls2 === 0`.

## Risks for Codex Red-Team

1. **LOC-cap exemption.** See section above. Strong case for exemption; if denied, splitting plan ready.

2. **Sequential test ordering.** Single test, all scenarios in one Playwright `test()` block. First failure halts; transcript captures up to failure. Trade-off vs separate tests: less granular reporting but lower per-test overhead.

3. **`page.unrouteAll()` between scenarios.** Clears prior route handlers. Without it, the second scenario would inherit the first's mock.

4. **`record()` rethrows on failure.** Stops the test at first failure. The transcript writer in `afterAll` still fires, capturing partial results.

5. **`afterAll` chromium-only guard.** `if (testInfo.project.name !== "chromium") return;` prevents non-chromium runs from overwriting the transcript.

6. **Hermeticity.** All scenarios use mocks. No real backend hit.

7. **Transcript path resolution.** `__dirname` is the spec file's directory; `../../../` resolves to repo root. Stable across `cd web && npx playwright test` invocations.

8. **22-count belt-and-suspenders.** `expect(transcript.length).toBe(22)` + `expect(every PASS).toBe(true)` — catches silent skips and silent-pass failures.

9. **No new package.json dep.**

10. **Format/type clean.** prettier + tsc clean.

## Out of scope

- Real human screen recordings (user-driven if desired).
- Backend writer for `needs_disambiguation` + `candidate_snippets` → I-f2-005a.

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
