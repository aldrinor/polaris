# FX-11 (#1116) diff-gate — ITER 1 of 5

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Output schema (REQUIRED — reply with EXACTLY this YAML, nothing else)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Bug (BUG-10 + BUG-10b) — cost accounting only, NOT a faithfulness invariant
- `cumulative_cost_usd` was the per-instance `self.total_cost_usd`: non-monotonic across
  clients sharing a run; the live UI read the per-instance one (under-reports NOW). Held
  ledger: 26 decreasing steps of 472.
- All 590 four-role verifier calls (mirror/sentinel/judge) wrote ZERO ledger rows (held
  ledger call_types: only `entailment_judge` + `generate`).

## Fix (diff: `.codex/I-ready-017/fx11_codex_diff.patch`, vs FX-10 tip `e63c102b`)
- **BUG-10:** moved `_add_run_cost(api_cost)` to BEFORE `self.usage.record(...)` (match the
  judge add-then-write order); changed `cumulative_cost_usd` at all THREE producers
  (`usage.record` line-log + ledger, and the live-UI trace `llm_call` event) to
  `round(current_run_cost(), 4)` (shared monotonic run total, inclusive of this call).
  Per-call `cost_usd` unchanged (line item). `check_run_budget` NOT touched.
- **BUG-10b:** `RecordingTransport.complete` now appends a ledger row per role call
  (`call_type=f"role:{request.role}"`), mirroring
  `entailment_judge._append_judge_ledger_entry`, `cumulative_cost_usd` read AFTER the add
  (inclusive). Best-effort try/except — never breaks the verifier call or the budget check.

## Evidence
- **§-1.1 on REAL held ledger** (`outputs/audits/I-ready-017/fx11_s11_audit.md`): confirmed
  26 decreasing steps + 0 role rows (of 472). Fix proven by offline smoke (a fresh ledger
  needs a live run).
- **Offline smoke:** `test_fx11_cost_ledger_iready017` → 3 passed (monotonic run-total
  cumulative `[0.5,0.8,1.0]`, final==current_run_cost(), last cumulative != own cost_usd;
  two `role:` rows non-decreasing inclusive; best-effort write failure doesn't break the
  call). Regression: `test_entailment_judge_cost` (8) + full `tests/roles/` (437) pass.

## Safety checks (please scrutinize)
- `usage.record` has exactly ONE real caller (the `.record` at line 167 is the trace sink,
  a different object), so changing its internal cumulative to `current_run_cost()` is safe.
- No test asserts a specific `cumulative_cost_usd` value (only a docstring mention).
- The reorder is post-call; `check_run_budget` is still called pre-call by callers, so the
  budget GATE is unchanged.

## Question
Is the cumulative now a correct monotonic run-total (inclusive, all 3 producers) and are
role-call ledger rows complete + best-effort, with `check_run_budget` untouched? Anything
blocking?
