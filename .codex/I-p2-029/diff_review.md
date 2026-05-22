# Codex DESIGN+DIFF review — I-p2-029 (#768): unified nav + role model

HARD ITERATION CAP: 5. iter 1. APPROVE iff zero P0/P1 (code + the relevant design dims). Final line MERGE AUTHORIZED if mergeable. Canonical-diff-sha256 `ad8a73c67c9b04a4de77839f2b881447e8debfa59bbf05b5bb96bac22d428efa`. web/ only.

## Design note (no visual change — code refactor + model)
This dedupes the nav (was duplicated in both shells) into @/lib/nav + adds the role model. The nav renders IDENTICALLY (same 9 items: Home/Intake/Dashboard/Upload/Benchmark/Compare/Contracts/Pin Replay/Memory) — visual is unchanged vs the #742-verified shell (build-green; pure refactor). Rubric dims most relevant: user-flow (nav consistency across shells now guaranteed), code-correctness, a11y (1 header/Primary nav/1 main preserved).

## Diff
- NEW web/lib/nav.ts (shared PRIMARY_NAV + NavItem + navForRole, isomorphic pure filter).
- NEW web/lib/roles.ts (5 roles, ROLE_LABELS, DEFAULT_ROLE — PRESENTATION-ONLY, commented NOT authorization).
- web/components/app_shell.tsx + web/app/components/home_keyboard_shell.tsx: removed duplicated const; import + render navForRole(PRIMARY_NAV, DEFAULT_ROLE).

## Review focus (brief-iter-1 P2s)
1. Role model presentation-only, no naming/comments implying enforcement? (Codex P2-1)
2. nav.ts + navForRole isomorphic; no server/client import or hydration pitfall across the two shells? (P2-2)
3. Both shells render the identical 9 items; home_g1_g8 (1 header/Primary nav/1 main) preserved?
4. Any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```
