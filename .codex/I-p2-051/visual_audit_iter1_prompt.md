# Codex VISUAL audit — I-p2-051 (#849) Dashboard (Runs), A++/S bar — iter 1 of 5

You have VISION. Audit /dashboard (cred-gated monitoring list). It fetches GET /api/v6/runs;
these screenshots are rendered LOCALLY with a seeded client session + a Playwright route-mocked
/runs FIXTURE (visual audit only — fixture never shipped; page keeps fetching real data).
Front-load all; don't pick bone from egg; APPROVE iff zero P0/P1.

## What changed
- Bug fix (correctness): run dates rendered as CJK ("2026年5月21日") because formatWhen used
  toLocaleDateString(undefined,…) (host locale). Now "en-CA" → English ("May 21, 2026"). Same
  fix in recent_runs_strip.tsx (Home).
- Runs list gained brand shadow-card elevation + overflow-hidden.
- Page was already a competent tokenized list (loading/error/empty/populated + verdict tokens
  Verified/Declined/Error); only the above changed.

## Attached
1. dash_populated_desktop.png  2. dash_populated_mobile.png  3. dash_empty_desktop.png

## Locked / do NOT flag
- Brand #c8102e. Fixture is visual-audit-only. LIVE-populated verification DEFERRED (real JWT
  needed; page 401-redirects without it) — judge layout/states, not "verify it live".

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
per_screen_grades: { populated_desktop: "", populated_mobile: "", empty: "" }
novel_p0: [...]
continuing_p0: []
p1: [...]
p2: [...]
highest_leverage_change_to_S: "..."
convergence_call: continue | accept_remaining
```
APPROVE iff a confident A-tier monitoring list (English dates, clear verdicts, clean states),
zero P0/P1.
