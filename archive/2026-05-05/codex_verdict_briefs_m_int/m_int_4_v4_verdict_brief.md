# M-INT-4 v4 — Codex round-4 GREEN

## Codex verdict (verbatim)
> No findings.
>
> The round-3 LOW is closed. The parser now latches malformed
> confidence before any later normalization and forces a fail-closed
> non-`in_scope` result for the requested cases.
>
> Adversarial check: I found no path that reintroduces `in_scope`
> after `confidence_malformed` is set.
>
> VERDICT: GREEN

## Round summary
- Round 1: 2 MEDIUMs (domain leak, bool→1.0)
- Round 2: 2 MEDIUMs (in_scope+null, NaN/inf bypass)
- Round 3: 1 LOW (malformed confidence kept verdict=in_scope)
- Round 4: GREEN (no findings)

## Final state
- 21/21 M-INT-4 tests pass (verified by Codex with explicit
  `--basetemp C:\POLARIS\codex_tmp_m_int_4_v4_review`)
- 5 specific JSONs probed by Codex:
  - `-0.25` → uncertain ✅
  - `[]` → uncertain ✅
  - `2.0` → uncertain ✅
  - `0.0` → in_scope (legit low confidence) ✅
  - `1` → in_scope, confidence=1.0 ✅

## Acceptance bar — ALL met
1. ✅ Imported (substrate + production class)
2. ✅ Invoked (telemetry alongside run_scope_gate)
3. ✅ Run-log evidence (`[M-INT-4] scope_llm:` line code-path verified)
4. ✅ Rollback flag PG_USE_LLM_SCOPE=0 disables (default 0)
5. ✅ Failure does NOT raise (per LAW II)
6. ✅ Adapter contract preserved (M1+M2+M3+M4+LOW closed)

Branch: PL-honest-rebuild-phase-1
Commit: 51cf8a6

## Verdict
**GREEN — M-INT-4 LOCKED. Proceeding to M-INT-5.**
