# Codex brief — I-p2-051 (#849): Dashboard (Runs) S-audit + CJK-date fix

HARD ITERATION CAP: 5. iter 1. Front-load findings; reserve P0/P1 for real risks. APPROVE iff
the plan is sound + doesn't break the contract.

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Context
/dashboard (cred-gated, monitoring-only) fetches GET /api/v6/runs → 401-redirects to /sign-in
on the live site without a real reviewer JWT. Audited by rendering locally (seeded client
session + route-mocked /runs fixture — visual-audit-only, never shipped).

## Plan
The page was already a competent tokenized list (loading/error/empty/populated + verdict tokens).
Assess-first; change only what's below A:
1. FIX (correctness): run dates rendered CJK ("2026年5月21日") — toLocaleDateString(undefined)
   used the host locale. Force "en-CA" → English. Same bug in recent_runs_strip.tsx (Home).
2. Polish: runs-list brand shadow-card elevation; mobile title line-clamp-2.
Preserve logic + testids + the real fetch. LIVE-populated verification DEFERRED (needs creds).

## Note
Already gated downstream: visual `-i` APPROVE (desktop A / mobile A- / empty A); code diff
APPROVE (zero findings). This brief records acceptance for the artifact set.
