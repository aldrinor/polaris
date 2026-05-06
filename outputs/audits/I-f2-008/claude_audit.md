# Claude Architect Audit — I-f2-008 (F2 walkthrough)

**Branch:** bot/I-f2-008 / **Diff SHA256:** `fffa30bb0709172b46e276917db75e144bd98003d47445c0fb51496bf3799032` (will be recomputed if changed in iter)
**LOC:** 335 net insertions — **OVER CHARTER §1 200-cap by 135 lines.** Explicit exemption requested below.
**Format:** `npx prettier --check` clean.

## CHARTER §1 LOC-cap exemption request

I-f2-008 was budgeted at **LOC 0** in the original breakdown (`state/polaris_restart/issue_breakdown.md:332`): "0 (walkthrough; no code)". The reframe (per user directive 2026-05-06 "Codex signs, not user") replaces the literal screen-recording walkthrough with an automated Playwright walkthrough that exercises 22 scenarios. The walkthrough IS the deliverable. The 22-scenario corpus is fixed by the breakdown's acceptance ("all 22 handled correctly"). Therefore:

- The spec source is the walkthrough definition (not "code that does work" but a verification matrix). 276 LOC for 22 scenarios = ~12 LOC/scenario, which is already minimal (single `record()` invocation + 2-3 assertions per scenario).
- The acceptance doc (58 LOC) is the static deliverable Codex reviews instead of recordings.
- The .gitignore (1 line) keeps runtime transcripts out of git per Codex iter-2 P1 #2 fix.

**Exemption argued:** I-f2-008 was carve-out (LOC 0) in the original budget; the reframe necessarily lifts to a non-zero spec LOC. The 22-scenario size is a binding requirement of the breakdown, not Claude's choice. The 200-cap exists to prevent scope creep; this PR is at the floor of "what does it take to deliver the binding 22-scenario walkthrough deliverable." Splitting into 2 PRs would not reduce total net LOC; it would just spread it across PRs.

**Alternative if exemption denied:** brief author commits to splitting into I-f2-008a (acceptance doc + 11 scenarios) and I-f2-008b (11 more scenarios) at iter 2 of diff review. Total LOC unchanged; just spread.

## Files

```
outputs/audits/I-f2-008/.gitignore                            NEW +1
outputs/audits/I-f2-008/walkthrough_acceptance.md             NEW +58
web/tests/e2e/f2_walkthrough.spec.ts                          NEW +276
```

## Iter-2 brief P2 advisories — addressed in implementation

- **P2 #1 (stale "transcript committed" wording):** Risk section in this audit document does NOT mention transcript commit. Implementation honors `.gitignore` for the runtime transcript.
- **P2 #2 (root-relative transcript path):** Spec uses `path.resolve(__dirname, "../../../outputs/audits/I-f2-008/walkthrough_transcript.md")` — `__dirname` is the spec file's directory; `../../../` resolves to repo root. Stable regardless of `process.cwd()`.
- **P2 #3 (very-long-input no submit):** Spec for `edge:long` ONLY types and asserts `value.length === 2000`. Does NOT click submit. Confirmed by `intakeCalls2 === 0` assertion AND no `intake-submit` click.

## Architecture review

1. **Single test, 22 scenarios.** Reduces per-test overhead. `transcript[]` accumulates across the test body. `afterAll` writes the artifact.

2. **`page.unrouteAll()` between scenarios.** Clears prior route handlers so each scenario's mock is isolated.

3. **`test.skip(({browserName}) => browserName !== "chromium")`** — chromium-only walkthrough per Codex iter-1 P2 #1.

4. **`record(d, e, fn)` helper.** Wraps each scenario; on success appends PASS, on failure appends FAIL + rethrows so the test halts at first failure (deterministic transcript).

5. **Final assertions.** `expect(transcript.length).toBe(22)` + `expect(every PASS).toBe(true)` are belt-and-suspenders: if any scenario silently skipped, length<22; if any fell through without throwing, the PASS rate guard catches it.

6. **`afterAll` writes transcript.** Skipped on non-chromium projects (no overwrite). Path resolved via `__dirname`.

## LAW + invariant checks

- **LAW II:** Scenario assertions are sharp; `record()` rethrows on failure. ✓
- **LAW V:** snake_case test file naming. ✓
- **LAW VI:** No magic numbers beyond 22 (the binding scenario count from breakdown). ✓
- **§9.4:** No `unittest.mock`; Playwright `page.route` only. ✓
- **§8.4:** No real network. ✓
- **CHARTER §1 200-cap:** 335 — exemption requested above.

## Test plan coverage

22 scenarios per `walkthrough_acceptance.md` table. Mapping in `f2_walkthrough.spec.ts`:
- 3 ambiguous queries (BPEI / MS treatment options / PR campaign metrics)
- 3 unambiguous (tirzepatide/metformin/aspirin)
- 3 is_ambiguous=false guard
- 3 French inputs
- 3 PDF drops
- 3 edge cases (empty/whitespace/long)
- 3 cluster picks (cluster_id 0/1/2)
- 1 cancel

Total: 22.

## Out of scope

- Real human screen recordings (user-driven if desired).
- Backend writer (I-f2-005a follow-up).

## Verdict

APPROVE for Codex diff review **WITH** explicit LOC-cap exemption request.
