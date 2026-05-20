HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# ⚠ HARD CONSTRAINTS — NOT CODEX-NEGOTIABLE ⚠

- **#626 stays OPEN.** This PR is I-cd-016a (harness-only); does NOT close #626. I-cd-016b (#674) closes #626 with the real OpenRouter run artifact.
- **Tightly scoped:** smoke script + auth + race-handling + cancel-on-timeout + docs only. NO bridge fixes.
- **Two NEW bug issues filed**: I-cd-016c (#675 — audit bridge model fallback bug) + I-cd-016d (#676 — GPG signer preflight via /transparency is shallow). Both block I-cd-016b (#674) from satisfying real-artifact acceptance; do NOT block I-cd-016a.
- **GPG key handling and real OpenRouter spend are operator-supervised; this PR does not invoke them.**

# Codex brief review — I-cd-016a (under #626): harness only

Does NOT close #626. Ships a harness that can be invoked by I-cd-016b operator-time once the two bridge bugs (I-cd-016c + I-cd-016d) are addressed.

## §0 — Iter-1 + iter-2 fold-in (4 + 3 + 3 findings, 2 split to new issues)

**iter-1 P1 (close-#626 framing) → DONE**: scope-split executed; PR description + docstrings explicit.

**iter-1 P1 (smoke success-only) → DONE**: smoke PASS requires `pipeline_verdict == "success"` AND at least 1 section with at least 1 `verifier_pass=true` sentence.

**iter-1 P1 (auth handling) → DONE**: harness logs in via POST `/auth/login`, stores JWT, sends bearer token on all calls.

**iter-1 P1 (GPG signer preflight) → PARTIALLY DONE + FILED I-cd-016d (#676)**: harness PREFLIGHTS by GET `/transparency` (stub check; non-empty `signing_key_fingerprint` is a necessary-but-not-sufficient signal). The real preflight endpoint lands at I-cd-016d (#676). Harness docstring documents this as a known limitation; operator confirms via `scripts/v6_preflight.py` manually for now.

**iter-2 P1 (lock-verification broken by audit bridge bug) → FILED I-cd-016c (#675)**: dropped lock-verification assertions from this PR's smoke. The bug `build_slice_chain()` falls back to `generator_model='unknown'` / `evaluator_model='strict_verify_v1'` is filed at I-cd-016c (#675). Harness asserts ONLY: bundle conformance (v1.0 schema from I-cd-012), `pipeline_verdict == "success"`, ≥1 verified section. Lock-verification assertions will be re-enabled at I-cd-016b after I-cd-016c fixes the bridge.

**iter-2 P1 (Novel — SSE-run_complete race)**: SSE `run_complete` event fires BEFORE actor marks `lifecycle_status=completed`. `/bundle.tar.gz` rejects non-completed lifecycle rows. Resolution: after SSE `run_complete`, smoke polls `GET /runs/{run_id}` until `lifecycle_status == "completed"` AND `pipeline_status == "success"` (bounded retry: 30 × 2s) BEFORE fetching the bundle.

**iter-2 P2 #1 (cancel-on-timeout)**: smoke POSTs `/runs/{id}/cancel` before exiting if the SSE wallclock cap (default 600s) fires. Prevents runaway spend.

**iter-2 P2 #2 (POLARIS_AUTH_DISABLED=1 mode)**: smoke skips `/auth/login` when env `POLARIS_SMOKE_AUTH_DISABLED=1` is set (operator runs in dev). Documented in runbook.

**iter-2 P2 #3 (duration_ms = wallclock)**: smoke reports its OWN measured wallclock as `duration_ms`, NOT bundle.latency_ms (which is pipeline-A retrieval-only).

## §A — Final scope: 1 NEW smoke script + 1 doc section + 1 audit note

| # | File | Action |
|---|---|---|
| 1 | `scripts/live_run_smoke.py` (NEW) | Operator-runs harness. Reads env: `POLARIS_V6_BACKEND_URL` (default `http://localhost:8000`), `POLARIS_SMOKE_USERNAME` + `POLARIS_SMOKE_PASSWORD` (required unless `POLARIS_SMOKE_AUTH_DISABLED=1`), `POLARIS_SMOKE_TIMEOUT_S` (default 600). CLI: `--question <text>` + `--template <id>`. Flow: (1) GET `/transparency` → assert `signing_key_fingerprint != ""` (STUB preflight; real preflight at I-cd-016d); (2) IF `POLARIS_SMOKE_AUTH_DISABLED != "1"`: POST `/auth/login` → store JWT, send bearer; (3) POST `/runs` → get `run_id`; (4) SSE `/stream/{run_id}` until `run_complete`, with `--timeout` wallclock cap; if timeout: POST `/runs/{run_id}/cancel` then exit non-zero; (5) Poll `GET /runs/{run_id}` until `lifecycle_status == "completed"` (bounded 30 × 2s); (6) GET `/runs/{run_id}/bundle.tar.gz` → extract to tmp; (7) `check_bundle_conformance(extracted_dir)` → assert `valid=True`; (8) parse `verified_report.json` → assert `pipeline_verdict == "success"` AND ≥1 section with ≥1 verifier_pass=true sentence; (9) print measured wallclock duration_ms + verifier_pass section count + bundle SHA. Lock-verification assertions deferred to I-cd-016b after I-cd-016c lands. Exit 0 PASS, non-zero FAIL with structured error code (MISSING_SIGNER / AUTH_FAILED / RUN_CANCELED / TIMEOUT / BUNDLE_FETCH_FAILED / CONFORMANCE_FAILED / VERDICT_NOT_SUCCESS / NO_VERIFIED_SECTIONS). |
| 2 | `docs/runbook.md` | Add "Live-run smoke (I-cd-016a harness)" section. Documents: prereqs (POLARIS_JWT_SECRET, POLARIS_STATIC_ACCOUNTS_PATH, POLARIS_GPG_KEY_ID, OPENROUTER_API_KEY on the backend; POLARIS_SMOKE_USERNAME + POLARIS_SMOKE_PASSWORD on the client; PG_MAX_COST_PER_RUN cap on the worker), invocation, expected output, common failure codes + remediation, plus the known limitations (lock-verification deferred to I-cd-016b after I-cd-016c bridge fix; GPG preflight stub until I-cd-016d). |
| 3 | `outputs/audits/I-cd-016/harness_ready.md` (NEW) | Phase-N-PARTIAL-honest manifest documenting: (a) backend infrastructure intact (hermetic capstone passes); (b) this PR ships the harness; (c) I-cd-016b (#674) is the operator-supervised live run that closes #626; (d) I-cd-016c (#675) is a real bridge bug that blocks I-cd-016b lock-verification; (e) I-cd-016d (#676) is a real GPG preflight gap that blocks I-cd-016b confidence. Documents the dependency chain explicitly. |

## §B — Scope discipline (what this PR does NOT do)

- **Fix the audit bridge model fallback** (I-cd-016c #675 owns this).
- **Fix the GPG preflight** (I-cd-016d #676 owns this).
- **Run real OpenRouter calls** (I-cd-016b #674 owns this).
- **Close #626** (I-cd-016b owns this).
- **Build new backend infrastructure** (capstone proves intact).
- **Wire CI to run the smoke** (operator-runs only; CI can't absorb real OpenRouter cost).
- **Lock-verification assertions** in the smoke — DEFERRED until I-cd-016c lands.
- **Accept abort_* as PASS** — success-only per iter-1 P1.

## §C — Smoke + acceptance (for THIS PR, not for #626)

- `python -m py_compile scripts/live_run_smoke.py`: parse clean.
- `python scripts/live_run_smoke.py --help`: argparse usable.
- Ruff lint clean.
- NOT required to actually run the harness end-to-end (that's I-cd-016b).

## §D — Risk surface

- **No real OpenRouter spend in this PR**.
- **Smoke is opt-in by operator**.
- **Race-condition handling + cancel-on-timeout**: prevents the production bugs from masquerading as harness bugs at I-cd-016b time.
- **Documented limitations**: lock-verification + real-GPG-preflight tracked at I-cd-016c + I-cd-016d.

## §E — Residual questions for Codex iter-3

1. Race-handling: poll bound (30 × 2s = 60s) sufficient OR longer? My read: 60s is generous since the actor finalize is a sqlite UPDATE.
2. Cancel-on-timeout: should also unset the in-flight Redis Streams keys, OR is the backend's cancel actor sufficient? My read: backend's responsibility per `runs.py:cancel`.
3. SSE consumption: minimal http stream-reader OR `httpx`/`aiohttp` library? My read: `requests.get(stream=True)` + iter_lines() — no new dependency.
4. Reporting: print a single-line summary suitable for `tee` to log file OR a JSON object for machine-parsing? My read: human-readable summary + a final `RESULT: PASS|FAIL` line for grep.

## §F — Output schema — return EXACTLY this

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
