# Codex round 3 — M-INT-4 v3

## Round-2 close
v2 had 2 Codex-found MEDIUMs. Both fixed in v3 (commit 2615239):

### MEDIUM 3: in_scope+None domain bypassed v2's strip (FIXED)
- v2 only stripped domain when verdict != "in_scope"
- JSON `{"verdict":"in_scope","domain":null}` kept
  in_scope+None → adapter raised "in_scope but domain=None"
- Sweep helper dropped telemetry → no `[M-INT-4] scope_llm` line
- v3 fix: coerce in_scope+None to UNCERTAIN with rationale,
  mirroring the unsupported-domain path

### MEDIUM 4: NaN/inf confidence bypassed bool guard (FIXED)
- `float("NaN")` returns nan; `min(1.0, nan)` returns 1.0
  because nan comparisons are always False
- `float("1e309")` returns inf; `min(1.0, inf)` returns 1.0
- Both became perfect-confidence telemetry
- v3 fix: explicit `math.isfinite()` check BEFORE the clamp;
  non-finite → 0.0 fallback

## v3 regression tests
5 new tests:
- test_parse_in_scope_with_null_domain_coerces_to_uncertain (M3 repro)
- test_parse_in_scope_missing_domain_field_coerces_to_uncertain (M3 corner)
- test_parse_rejects_nan_confidence (M4 repro)
- test_parse_rejects_inf_confidence_via_string (M4 corner)
- test_parse_in_scope_with_unsupported_domain_still_coerces (v2 preserved check)

## Acceptance bar (re-verify all)
1. ✅ Imported (substrate + production class)
2. ✅ Invoked (telemetry alongside run_scope_gate)
3. ✅ Run-log evidence
4. ✅ Rollback flag PG_USE_LLM_SCOPE=0 disables (default 0)
5. ✅ Failure does NOT raise (per LAW II)
6. ✅ Adapter contract preserved by parser (M1+M2+M3+M4 all closed)

## Tests
- 16/16 M-INT-4 (6 v1 + 5 v2 + 5 v3) pass
- 70/70 M-D5 substrate tests still green

Branch: PL-honest-rebuild-phase-1
Commit: 2615239

## Verdict
GREEN | PARTIAL | BLOCKED
