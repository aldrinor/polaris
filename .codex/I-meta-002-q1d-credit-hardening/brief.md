HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings. Reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

RULE NOW — emit the YAML verdict block FIRST. APPROVE this CONCRETE plan or REQUEST_CHANGES with specifics.
Small preflight-honesty fix for the no-spend→spend gate (operator concern #3, credit). NO SPEND offline.

## Output schema (emit FIRST)
```yaml
verdict: APPROVE | REQUEST_CHANGES
p0: [...]
p1: [...]
p2: [...]
required_changes: [...]
convergence_call: accept_remaining
```

# Codex brief-gate (iter 1) — PR9: search-credit hardening / preflight honesty (#947)

Codex-verified gap (#941): `pg_preflight.py` (the §3.0 GATE-A pre-rental gate) misrepresents benchmark-
required creds in two ways: (a) T03 hard-FAILs on a missing `EXA_API_KEY` though Exa is Pipeline-B-ONLY and
is never used by the Pipeline-A benchmark; (b) there is no honest Serper prepaid-pool signal (the per-request
credits header is a refill-window counter, not the total). NO SPEND.

## GROUNDED FACTS (verified)
- `pg_preflight.py` TestResult statuses are PASS / FAIL / SKIP only; the overall verdict counts ONLY FAIL
  (`failed = sum(... if r.status == FAIL)`, line ~1808; non-zero exit iff `failed > 0`). SKIP is non-blocking.
- T03 `test_exa_api_key` (line ~115): `PG_EXA_ENABLED` defaults "1" → a missing `EXA_API_KEY` returned FAIL.
- **Verified (grep): Exa is ONLY in `src/polaris_graph/agents/searcher.py` (Pipeline B).
  `src/polaris_graph/retrieval/live_retriever.py` (the Pipeline-A benchmark path) has ZERO Exa usage.**
  `PG_EXA_ENABLED` is defined in `state.py:177` (default "1") and read only by searcher.py.
- Serper exposes no programmatic total-prepaid-pool endpoint (per-request `X-...-Credits` header is a
  refill-window counter). A real-balance probe would cost a credit (a paid search) — out of scope (NO SPEND).

## CONCRETE PROPOSAL (small, no-spend, advisory-only)
1. **T03 (`test_exa_api_key`)**: a missing `EXA_API_KEY` returns **SKIP** (advisory) instead of FAIL, with a
   clear message: "Exa is Pipeline-B-only (searcher.py), NOT used by the Pipeline-A benchmark
   (live_retriever.py); not a benchmark blocker." PASS still when present; SKIP when `PG_EXA_ENABLED=0`. This
   makes GATE-A a faithful mirror of benchmark-required creds (Exa missing no longer blocks the Pipeline-A
   benchmark preflight). I do NOT change `state.PG_EXA_ENABLED` (Pipeline B keeps its own behavior).
2. **New `test_serper_credit_pool` (T02b, registered in TIER_1_TESTS after T02)**: an explicit advisory SKIP
   (NO network, NO SPEND) documenting that the Serper prepaid pool is not programmatically queryable and that
   the operator must verify the balance on the Serper dashboard before a paid run — so the credit check is
   honest rather than implying the per-request header tells us the pool.
3. Tests (`tests/test_pg_preflight_credit.py`): Exa-missing → SKIP (not FAIL) + Pipeline-B-only message;
   Exa-present → PASS; PG_EXA_ENABLED=0 → SKIP; serper-credit-pool → advisory SKIP with the dashboard note +
   "not programmatically queryable"; serper-credit-pool registered in TIER_1_TESTS. Imports `pg_preflight` as
   a module (not `from ... import test_*`) so pytest does not collect the preflight's own async test_* funcs.

## Constraints / frozen
snake_case; explicit imports; no except:pass. Untouched: every other preflight test, strict_verify, the
benchmark path, `state.PG_EXA_ENABLED`. ≤40 LOC. NO SPEND.

## The real risks to rule on
1. Is downgrading T03 FAIL→SKIP correct (Exa is genuinely Pipeline-B-only, so it is NOT a Pipeline-A
   benchmark blocker), or does any Pipeline-A path consume Exa? (Claim: verified by grep — live_retriever has
   zero Exa; only searcher.py / Pipeline B uses it.)
2. Is an advisory SKIP the honest Serper-credit answer given no programmatic pool API + NO-SPEND? (Claim:
   yes — a real probe costs a credit; the documented manual-dashboard step is the faithful no-spend signal.)
3. Does SKIP truly not weaken GATE-A? (Claim: SKIP is non-blocking by design; only FAIL gates — and Exa was
   never a real benchmark requirement, so removing a false FAIL strengthens honesty, not weakens the gate.)

APPROVE iff this makes preflight a faithful mirror of Pipeline-A-benchmark-required creds (Exa missing →
advisory SKIP, not FAIL), adds an honest no-spend Serper-pool advisory, and changes no other gate behavior.
