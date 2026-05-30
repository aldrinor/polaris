# Claude architect audit — PR9: search-credit hardening / preflight honesty (#947)

**Issue:** #947 (q1c-6, operator concern #3 — credit). **Branch:** `bot/I-meta-002-q1d-credit-hardening`.
**Both Codex gates APPROVE iter-1** (brief + diff, zero P0/P1; one brief-gate P2 doc-drift fixed). **NO
SPEND** — preflight advisory-only, 5 offline tests.

## What this fixes

`pg_preflight.py` (the §3.0 GATE-A pre-rental gate) misrepresented benchmark-required creds two ways
(Codex-verified #941):
1. **T03 falsely hard-FAILed on a missing `EXA_API_KEY`** — but Exa is **Pipeline-B-only** (`searcher.py`);
   the Pipeline-A benchmark path (`live_retriever.py`) has ZERO Exa usage (verified by grep; `PG_EXA_ENABLED`
   is defined in `state.py` and read only by searcher.py). So GATE-A could block a perfectly-ready Pipeline-A
   run on a cred the benchmark never uses.
2. **No honest Serper prepaid-pool signal** — Serper exposes no programmatic total-pool API (the per-request
   `X-...-Credits` header is a refill-window counter, not the balance).

## The fix (advisory-only, no-spend)

1. `test_exa_api_key` (T03): a missing `EXA_API_KEY` (with `PG_EXA_ENABLED=1`) now returns **SKIP** (was
   FAIL), with the message "Exa is Pipeline-B-only (searcher.py), NOT used by the Pipeline-A benchmark
   (live_retriever.py); not a benchmark blocker." PASS still when present; SKIP when `PG_EXA_ENABLED=0`.
   `state.PG_EXA_ENABLED` is NOT changed (Pipeline B keeps its behavior). Since the gate verdict counts ONLY
   FAIL (`failed = sum(... if r.status == FAIL)`; non-zero exit iff `failed > 0`), this removes a FALSE
   blocker without weakening the gate.
2. New `test_serper_credit_pool` (T02b, registered in `TIER_1_TESTS` after T02): an explicit advisory SKIP
   (NO network, NO SPEND) documenting that the Serper prepaid pool is not programmatically queryable and that
   the operator must verify the balance at the Serper dashboard before a paid run — so the credit check is
   honest rather than implying the header tells us the pool.
3. Tier-1 header comment 10→11 (brief-gate P2 doc-drift fix).

## Untouched

Every other preflight test, the benchmark path, `state.PG_EXA_ENABLED`, strict_verify, and the overall gate
verdict logic (still keys only on FAIL).

## Tests (5 pass, NO SPEND)

`tests/test_pg_preflight_credit.py`: Exa-missing → SKIP (not FAIL) + Pipeline-B-only message; Exa-present →
PASS; `PG_EXA_ENABLED=0` → SKIP; serper-credit-pool → advisory SKIP + dashboard note + "not programmatically
queryable"; serper-credit-pool registered in TIER_1_TESTS. Imports `pg_preflight` as a module so pytest does
not collect its async `test_*` functions. `py_compile` OK.

## Verdict

Makes the GATE-A preflight a faithful mirror of Pipeline-A-benchmark-required creds (Exa missing → advisory
SKIP, not FAIL), adds an honest no-spend Serper-pool advisory, and changes no other gate behavior. Both gates
APPROVE iter-1. Ready to queue for operator merge (Option A — no spend).
