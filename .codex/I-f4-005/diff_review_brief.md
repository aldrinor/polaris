# Codex Diff Review — I-f4-005 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg".
- If iter 5 returns REQUEST_CHANGES, force-APPROVE.
- Verdict APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.

**Issue:** I-f4-005 — F4 200-sentence walkthrough (Codex-reviewed)
**Brief:** APPROVED iter 1 (per plan)
**Canonical-diff-sha256:** `d92996037abd898216bb7328faac97e25dc1ddb6f3db37c1ee70a17cbb454f28`
**LOC:** 45 net (well under CHARTER §1 200-cap; over breakdown 0-LOC budget per I-f3-010 walkthrough exemption pattern)

## Files

```
outputs/audits/I-f4-005/f4_walkthrough.md   NEW +45
```

## What changed

Walkthrough doc cross-referencing 5 source files + 4 Playwright test files at HEAD; documents 200-sentence scenario, "<1s hover/click latency" framing (synthetic acceptance via existing Playwright; production verification deferred to I-f4-005a follow-up); names 5 follow-up Issues with explicit gaps.

## Risks for Codex Red-Team

1. **All file references must exist at HEAD.** Spot-checked: `web/lib/sse_client.ts` (I-f4-001), `web/lib/sse_events.ts` (I-f4-002), `web/lib/run_broadcast.ts` (I-f4-003), `web/app/audit_live/_panels.tsx` + `page.tsx` (I-f4-002), 4 Playwright specs (I-f4-001/002/003/004).
2. **Walkthrough is doc-only** per I-f2-008/I-f3-010 reframe pattern.
3. **CHARTER §1 LOC cap.** 45 net; well under 200.
4. **No source code changes.**

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
