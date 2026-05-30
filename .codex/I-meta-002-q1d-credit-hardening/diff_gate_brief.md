HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL findings. Reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

RULE NOW — emit the YAML verdict block FIRST. Read ONLY the patch at
`.codex/I-meta-002-q1d-credit-hardening/codex_diff.patch` (2 files, +~80/-5). NO SPEND.

## Output schema (emit FIRST)
```yaml
verdict: APPROVE | REQUEST_CHANGES
p0: [...]
p1: [...]
p2: [...]
required_changes: [...]
convergence_call: accept_remaining
```

# Codex diff-gate (iter 1) — PR9: search-credit hardening / preflight honesty (#947)

Verify the diff implements the brief-gate-APPROVE'd plan (brief APPROVE iter 1).

## What to verify
1. `test_exa_api_key` (T03): a missing `EXA_API_KEY` (with PG_EXA_ENABLED=1) now returns **SKIP** (was FAIL),
   with the "Exa is Pipeline-B-only … not a benchmark blocker" message. PASS when present; SKIP when
   PG_EXA_ENABLED=0. `state.PG_EXA_ENABLED` is NOT changed.
2. New `test_serper_credit_pool` (T02b) — advisory SKIP, NO network, documents the manual Serper-dashboard
   step; registered in `TIER_1_TESTS` right after `test_serper_api_key`.
3. Tier-1 header comment updated 10→11 (the brief-gate P2 doc-drift fix).
4. The overall gate verdict still keys ONLY on FAIL (SKIP non-blocking) — so the change cannot make a
   genuinely-broken run pass, AND removes a FALSE FAIL on a Pipeline-B-only cred.

## Evidence (verified by Claude main-thread, NO SPEND)
- 5 tests PASS (`tests/test_pg_preflight_credit.py`): Exa-missing → SKIP (not FAIL) + Pipeline-B-only msg;
  Exa-present → PASS; PG_EXA_ENABLED=0 → SKIP; serper-credit-pool advisory SKIP + dashboard note + "not
  programmatically queryable"; serper-credit-pool registered in TIER_1_TESTS. `py_compile` OK.
- Tests import `pg_preflight` as a module (not `from ... import test_*`) so pytest does not collect the
  preflight's own async test_* functions.

## The real risks to rule on
1. Does downgrading T03 FAIL→SKIP weaken GATE-A? (Claim: no — Exa is verified Pipeline-B-only; it was never
   a real Pipeline-A benchmark requirement, so this removes a FALSE blocker; SKIP is non-blocking by design.)
2. Is the Serper advisory honest + no-spend (no network probe)? (Claim: yes — pure advisory SKIP.)
3. Any other preflight test, the benchmark path, or strict_verify touched? (Claim: no — only T03 + the new
   advisory + the count comment.)

APPROVE iff the diff downgrades the false Exa FAIL to an advisory SKIP, adds the honest no-spend Serper-pool
advisory, updates the count comment, and changes no other gate behavior.
