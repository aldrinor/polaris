# FL-05 (#1124) diff-gate — ITER 2 of 5

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
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

## Scope
Fail-loud run-health backstop. Flag-gated `PG_RUN_HEALTH_GATE` (default OFF). Diff:
`.codex/I-ready-017/fl05_codex_diff.patch` (vs FX-18 verified tip `27697b3e`).

## Your iter-1 verdict (all 4 addressed)
- **P1 #1 (v6 schema):** `src/polaris_v6/schemas/run_status.py` `PipelineStatus` Literal omitted
  `abort_discovery_degraded` → RunStatusResponse 500 on a GET/list of an FL-05 abort.
- **P1 #2 (release_allowed):** override left `manifest.release_allowed` at the prior (often True)
  value → contradictory abort marked releasable.
- **P2 #1:** additive fields emitted even when gate OFF → "byte-identical default" claim untrue.
- **P2 #2:** `!= "0"` parse treated `false`/empty as ON for the default-OFF flag.

## What iter-2 changed
1. **P1 #1:** added `abort_discovery_degraded` to the v6 `PipelineStatus` Literal (the **5th**
   registration site, mirroring `abort_verifier_degraded`) + a `get_args(PipelineStatus)` membership
   test. Now UNIFIED_STATUS_VALUES + _SUMMARY_TO_UNIFIED + regression_lab + manifest-contract guard +
   v6 PipelineStatus all carry it.
2. **P1 #2:** the override now also sets `manifest['release_allowed'] = False` — status and the
   release flag can never contradict (mirrors the eval-gate invariant L5156-5158: a held status never
   reads as releasable).
3. **P2 #2:** robust truthy parse for the DEFAULT-OFF flag:
   `os.getenv("PG_RUN_HEALTH_GATE","0").strip().lower() in {"1","true","yes","on"}`.
4. **P2 #1:** kept always-emit (the FL-05 plan's observability intent — the 2 fields are additive,
   ignored by existing consumers, and the manifest-contract gate passes) and CORRECTED the claim: the
   default-OFF path leaves **status + control-flow + the release decision unchanged**; it is not
   "byte-identical" (it adds 2 observability fields). Comment, audit, and the test name all updated to
   say that precisely.

## Evidence
- **Offline smoke — `test_fl05_run_health_gate_iready017.py` → 8 passed** (added the v6
  `PipelineStatus` membership guard; renamed the default-OFF test to the accurate claim). Full gate
  decision matrix + the runner↔regression_lab mirror invariant retained.
- **Regression**: v6 `test_schemas` (5) + manifest_contract (13, taxonomy guard) — green.
- §-1.1: `outputs/audits/I-ready-017/fl05_s11_audit.md` (held storm attempted_empty; the 5-site
  registration + release_allowed + flag parse documented).

## Question
Are P1 #1 (v6 PipelineStatus + test) and P1 #2 (release_allowed=False on override) fully closed, the
flag parse robust, and the default-OFF behavior accurately described (status/control-flow/release
unchanged; 2 additive observability fields)? Anything blocking APPROVE?
