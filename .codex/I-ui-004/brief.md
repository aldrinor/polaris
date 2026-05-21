# Codex BRIEF review — I-ui-004 (#543) run-compare view

HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — P3/P2/cosmetic for non-blockers; P0/P1 only for real execution risks.
- If iter 5 returns REQUEST_CHANGES, Claude force-APPROVE's on remaining-non-P0/P1; no iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Design-spec review (brief IS the work for UI) — confirm sound BEFORE implementing.

## Goal (#543 / I-rdy-014b)
Operator picks TWO completed runs and sees the compare result. Distinct from /benchmark (POLARIS-vs-external). Backend exists + real-run wired (#680). Reachable from nav.

## Scope
**IN:** (a) api.ts — `ReportComparison` type + `listCompletedRuns(limit)` (GET /runs?status=completed) + `compareRuns(left,right)` (GET /runs/{left}/compare/{right}); (b) new route `web/app/compare/page.tsx` (two pickers + Compare + result); (c) nav: add "Compare" to BOTH `web/components/app_shell.tsx` PRIMARY_NAV + `web/app/components/home_keyboard_shell.tsx` PRIMARY_NAV. cyan-consistent with #704.
**OUT:** benchmark (separate); follow-up (#542, merged).

## Verified facts (grounded)
1. Endpoint: `GET /api/v6/runs/{left}/compare/{right}` → ReportComparison dict. **400** if left==right; **422** abort/release-blocked, **404** unknown (load_evidence_contract_for_run, #680). Auth-gated → use authFetch.
2. ReportComparison (src/polaris_v6/compare/differ.py): `{left_run_id, right_run_id, same_template, same_question, shared_evidence_ids[], only_left_evidence_ids[], only_right_evidence_ids[], shared_evidence_pct (0..1 float), frame_coverage_overlap[], only_left_frames[], only_right_frames[], left_contradictions, right_contradictions, pipeline_status_match, family_segregation_both_pass}`.
3. Runs list: `GET /api/v6/runs?status=completed&limit=N` → RunStatusResponse[] (#705). For the two pickers. authFetch.
4. No existing list/compare client in api.ts; no /compare route. Nav is duplicated in app_shell.tsx (most routes) + home_keyboard_shell.tsx (home). home_g1_g8 spec loops the 8 existing labels (visible-check, no exact count) → a 9th "Compare" link is safe.
5. Visual identity (#704, live): cyan oklch(0.50 0.20 200) --primary/--ring; Card/Button shadcn; the /compare route gets the global AppShell (NOT suppressed — only "/" is suppressed by AppShellGate).

## Design
**api.ts:**
- `export interface ReportComparison { ... }` mirroring the dataclass (numbers + string[]).
- `export async function listCompletedRuns(limit = 20): Promise<RunStatusResponse[]>` → authFetch GET `${BACKEND_URL}/runs?status=completed&limit=${limit}` → asJsonOrThrow.
- `export async function compareRuns(left: string, right: string): Promise<ReportComparison>` → authFetch GET `${BACKEND_URL}/runs/${encodeURIComponent(left)}/compare/${encodeURIComponent(right)}` → asJsonOrThrow.

**web/app/compare/page.tsx (client component):**
- On mount: listCompletedRuns → populate two `<select>` pickers (option label = `${template} · ${question.slice(0,60)} · ${run_id.slice(0,8)}`, value = run_id). If the list errors/empty → show "No completed runs to compare yet" + a link to /intake.
- Two selects (left, right) + a "Compare" Button (cyan, disabled if either unset or left===right — mirrors the backend 400). A small hint when left===right ("pick two distinct runs").
- On Compare: compareRuns(left,right) → render ReportComparison:
  - Header row: same_template / same_question / pipeline_status_match / family_segregation_both_pass as check/✗ badges.
  - shared_evidence_pct as a percentage (Math.round(pct*100)%).
  - Three evidence columns: shared (count + ids), only-left (count + ids), only-right (count + ids). Same for frames (overlap / only-left / only-right).
  - left_contradictions vs right_contradictions.
  - Defensive: render counts from array .length; show "—"/0 gracefully.
- States: idle | loading-list | submitting | {result} | {error}. Error mapping: 400 → "pick two distinct runs"; 404 → "one of the runs was not found"; 422 → "one run has no shippable evidence (aborted/release-blocked)"; else generic.

**nav:** add `{ href: "/compare", label: "Compare" }` to PRIMARY_NAV in app_shell.tsx + home_keyboard_shell.tsx (keep the existing 8 ordered; insert "Compare" after "Benchmark" in both for parity).

## Review focus
1. Auth: authFetch (gated route) correct for both clients? listCompletedRuns shape (RunStatusResponse[]) matches #705?
2. left===right guard (UI disable + backend 400 fallback) + error mapping (400/404/422) correct?
3. Nav parity: must "Compare" be added to BOTH navs to stay consistent (G1 "nav identical across routes")? Any home_g1_g8 break from a 9th link?
4. shared_evidence_pct is 0..1 float → render as %.
5. Defensive rendering of all the arrays/counts.
6. Any NOVEL P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
