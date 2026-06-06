# FX-09 (#1114) diff-gate — ITER 1 of 5

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

## Bug (BUG-05)
`judge_error_rate` divided by ALL verifier-checked sentences (702 in the held run)
but the entailment judge only runs on the subset passing every mechanical
strict_verify check first → the #1071 binding `abort_verifier_degraded` gate was
diluted ~2.87x. A degraded judge (30 errors) reports 30/702=0.043 (< 0.10 cap →
SHIPS) instead of ~30/245=0.122 (> cap → ABORTS).

## Fix (diff: `.codex/I-ready-017/fx09_codex_diff.patch`, vs FX-08 tip `c0d71881`)
1. At the run boundary (`run_one_query`, after `reset_run_cost()`): snapshot
   `_base_judge_tel = get_judge_telemetry()` (NOT reset — process-lifetime counters,
   reentrant; defensive try/except sets `_get_judge_telemetry=None` + zero base).
2. At the rate computation: denominator = `get_judge_telemetry()['calls']` delta;
   numerator = `judge_error` delta (counts errors even on KEPT sentences that failed
   open, which the reason-grep under-counts). Pure helper
   `_judge_calls_and_errors_from_telemetry(base, now)` for testability.
3. Telemetry-unavailable fallback = old reason-grep rate (fail-functional, never
   silently inert).
4. `verif_details`: `judge_calls` (denominator) + `verifier_sentences_checked`
   (context) added; `judge_error_sentences_checked` kept as back-compat alias (its
   only consumer is the internal abort log). Log lines updated to show judge calls.

## Evidence
- **§-1.1 on REAL output** (`outputs/audits/I-ready-017/fx09_s11_audit.md`): held
  `verification_details.json` shows denominator 702 (kept 176 + dropped 526) with 281
  no_provenance drops that never reach the judge; worst-case 30/702 ships vs 30/245
  aborts. Held run had 0 judge errors (rate 0 either way; the *structure* was diluted).
- **Offline smoke:** `pytest test_fx09_judge_error_rate_iready017.py` → 6 passed
  (N/245-not-N/702; real-telemetry delta via `_record_judge_outcome`; snapshot
  stability; process-lifetime second-run-delta; degraded-trip boundary; zero-calls
  guard). Regression: `test_feature_firing_telemetry_iready005` + `test_manifest_contract`
  → 21 passed.

## Faithfulness check
Strengthens the binding degraded-verifier abort (makes it fire when it should). No
grounding / strict_verify / 4-role change.

## Reentrancy note (please scrutinize)
Snapshot/delta assumes the sweep runs queries SEQUENTIALLY per process (it does — the
global counter is shared). If queries ever run CONCURRENTLY in-process the delta would
cross-contaminate; flag if you see a concurrent path I missed.

## Question
Is the denominator now correct (actual judge calls), faithfulness-strengthening, with
no broken consumer of the renamed/added manifest fields? Anything blocking?
