# Codex Brief Review — I-f4-005 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg".
- If iter 5 returns REQUEST_CHANGES, force-APPROVE.
- Verdict APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.

**Issue:** I-f4-005 — F4 200-sentence walkthrough (Codex-reviewed)
**Phase:** 1 / **Feature:** F4
**LOC budget:** 0 per breakdown. **CHARTER §1 hard cap: 200.**

## Reframe (per user directive 2026-05-06: "Codex signs, not user")

Original spec: "product-owner recording on 200-sentence run; hover/click latency <1s." Reframed (per I-f2-008 / I-f3-010 pattern): Codex-reviewed walkthrough doc cross-referencing the F4 substrate that already exists.

## Mission

Author `outputs/audits/I-f4-005/f4_walkthrough.md` documenting:
1. The 200-sentence walkthrough scenario (synthetic clinical run with 200 verify_decision events).
2. Cross-references to F4 substrate at HEAD:
   - `web/lib/sse_client.ts` — reconnect/backoff (I-f4-001)
   - `web/lib/sse_events.ts` — 6 event types (I-f4-002)
   - `web/app/audit_live/_panels.tsx` — 6 panels + 2 adversarial banners + cancel button (I-f4-002, I-f4-003, I-f4-004)
   - `web/lib/run_broadcast.ts` — multi-tab cancel (I-f4-003)
   - 4 Playwright test files: `sse_client.spec.ts`, `audit_live.spec.ts`, `audit_live_multitab.spec.ts`, `audit_live_adversarial.spec.ts`
3. The "<1s hover/click latency" acceptance: framed as a follow-up I-f4-005a (real product-owner recording on actual backend SSE feed); current substrate proves the SSE path delivers events at <1s in synthetic mocks (per I-f4-002 acceptance test).
4. Honest gap: production wiring of `subscribeToRun()` to the new SSEClient is named follow-up I-f4-001a; until then `/audit_live` is a test-route surface, not a production live-run UI.

## Acceptance criteria (binding)

1. `outputs/audits/I-f4-005/f4_walkthrough.md` (NEW): walkthrough doc cross-referencing 4 source files + 4 test files, naming gaps + follow-ups.

## Planned diff shape

```
outputs/audits/I-f4-005/f4_walkthrough.md   NEW +60
```

LOC: +60 net. Per breakdown's 0-LOC budget — exemption analogous to I-f2-008/I-f3-010 (binding walkthrough deliverable as Codex-reviewed audit doc instead of human screen recording).

## Out of scope

- Real human screen recording on a 200-sentence run → I-f4-005a follow-up (user-driven).
- Production wiring of `subscribeToRun()` → I-f4-001a.
- Backend SSE schema for the 6 event types → I-f4-002b.

## Risks for Codex Red-Team

1. **Walkthrough is doc-only.** Acceptance via Codex sign-off on the doc, not a live recording.
2. **Cross-references must point to real files at HEAD.** Brief author commits to verifying each file path exists before commit.
3. **Honest gap surfacing.** Doc explicitly calls out (a) production-wiring gap, (b) backend-SSE-schema gap.
4. **No new package dep.** No source changes.
5. **CHARTER §1 LOC cap.** 60 net (over 0-budget; exemption per I-f3-010 pattern).

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
