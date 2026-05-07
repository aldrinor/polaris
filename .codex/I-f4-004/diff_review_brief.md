# Codex Diff Review — I-f4-004 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg".
- If iter 5 returns REQUEST_CHANGES, force-APPROVE.
- Verdict APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.

**Issue:** I-f4-004 — F4 adversarial 80% fetch fail + zero-verified-abort
**Brief:** APPROVED iter 2 (per plan; iter-2 verdict was REQUEST_CHANGES citing missing impl which is the diff-stage subject)
**Canonical-diff-sha256:** `d1c410b98b72704ef70312db433f741fdeb6306e4d3ba2a4a5dbdec8beeb367b`
**LOC:** 142 net (58 under CHARTER §1 200-cap)
**Tests:** Lint clean.

## Files

```
web/app/audit_live/_panels.tsx               EDIT +55
web/tests/e2e/audit_live_adversarial.spec.ts NEW +87
```

## What changed

**`_panels.tsx`:** Added cumulative counters state INDEPENDENT of MAX_EVENTS panel slice (per Codex iter-1 P1). `setCumulative` increments source_dropped, retrieval_candidate, verify_decision_kept/dropped per event. `verify_decision` payload parsed via try/catch fail-closed. Renders `partial-evidence-warning` when cumulative drops/candidates ≥ 0.8 (with floor candidates ≥ 5) and `zero-verified-abort` when all kept = 0 with at least 1 verify_decision processed.

**`audit_live_adversarial.spec.ts`:** 4 Playwright tests:
1. partial-evidence (10 candidates + 8 drops = 80%)
2. zero-verified-abort (5 verify_decisions all kept:false)
3. normal-path (10/1/5-kept) — waits for 5 events processed THEN asserts no banners
4. cap-boundary (100 candidates + 50 drops = 50%) — proves cumulative counters work past MAX_EVENTS=50 panel slice

## Risks for Codex Red-Team

1. **Cumulative counters never reset.** Intentional — total run-level state.
2. **Try/catch JSON parse fail-closed.** Malformed payload counted as dropped (conservative).
3. **`retrieval_candidate >= 5` floor.** Avoids false positives on small samples.
4. **§9.4 N/A frontend.**
5. **CHARTER §1 LOC cap.** 142 net.
6. **No new package dep.**

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
