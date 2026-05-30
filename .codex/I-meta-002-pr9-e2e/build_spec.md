# Offline E2E build spec (I-meta-002 PR-9) — NO SPEND, NO NETWORK — Codex design APPROVE iter 2

Codex APPROVED the concrete proposal in .codex/I-meta-002-pr9-e2e/design_brief.md (zero P0/P1; 3 P2s,
all folded in below). This is the no-spend capstone: ONE offline harness proving the whole toolchain
runs end-to-end so canary day adds ONLY real model calls.

## Locked constraints
- NO MONEY / NO NETWORK: zero real LLM calls (generator AND 3 verifier roles faked/canned), zero socket.
- Use the EXISTING annotated clinical_tirzepatide_t2dm contract (NON-benchmark). NEVER read
  outputs/dr_benchmark gold rubric / competitor answers for POLARIS's own run.
- Frozen, no drift: claim_audit_scorer.py, runtime lock (do NOT promote). Reuse committed M3a/M3b/M4/M5
  + the external scorer scripts.
- Fail-closed; no vacuous pass; snake_case; explicit imports; no except:pass; no unittest.mock in
  src/scripts (stubs in tests OK).

## Build (the concrete proposal + Codex's 3 P2 refinements)
Files: `scripts/dr_benchmark/offline_e2e.py` (harness) + `tests/dr_benchmark/test_offline_e2e.py`
(drives + asserts) + fixtures under `tests/fixtures/offline_e2e/`.

1. **Generator faking (zero spend):** feed a CANNED set of kept verified sentences + a canned evidence
   pool fixture into the M3b 4-role seam (`run_four_role_seam` / the four_role_input_builder path) with
   an INJECTED FAKE RoleTransport (reuse the canned Mirror/Sentinel/Judge response pattern already in
   tests/dr_benchmark/test_gate_b_seam.py — no httpx, no socket). Over the annotated
   clinical_tirzepatide_t2dm contract. Do NOT call the live generator or run_one_query's live path.
2. **Chain:**
   a. 4-role seam -> a manifest dict with `four_role_evaluation` (final_verdicts + the M5
      evaluator_agrees map) + `four_role_claim_audit.json` written to a tmp run_dir.
   b. M4 pathB served==pinned gate over FIXTURE served-metadata -> assert PASS; AND a SECOND
      wrong-model served-metadata fixture -> assert fail-closed (Codex P2 #3: include BOTH).
   c. External scorer on SYNTHETIC fixtures: a FIXTURE reconciled coverage ledger + a FIXTURE rubric
      JSON -> score_run.score_one -> a per-claim scored ledger; then aggregate_systems -> systems
      summary. (Codex P2 #1: the fixture rubric/ledger MUST be clearly labeled synthetic/non-benchmark
      — e.g. a header field `synthetic: true` + a comment — and live under tests/fixtures/offline_e2e/,
      ISOLATED from outputs/dr_benchmark; the harness must NOT read outputs/dr_benchmark.)
3. **No-network FAIL-CLOSED (Codex P2 #2):** the test must BLOCK real network at the socket layer
   (e.g. monkeypatch socket.socket / socket.create_connection to raise) for the whole e2e, so a stray
   real connection FAILS the test — not merely assert "fake transport was used". Confirm the e2e still
   passes with sockets blocked (proving zero network).

## Assertions (non-vacuous)
- manifest carries `four_role_evaluation` with a NON-EMPTY `evaluator_agrees` map obeying the safe rule
  (a canned FABRICATED/UNSUPPORTED verdict -> False; a canned VERIFIED+kept claim -> True).
- `four_role_claim_audit.json` written + parseable, keys == final_verdicts keys.
- pathB gate: PASS on matching served-metadata; fail-closed (raises) on the wrong-model fixture.
- score_run emits a scored ledger file; aggregate_systems emits a systems summary file.
- socket blocked for the whole run (no-network fail-closed) and the e2e still passes.

## Verify
python -c "import scripts.dr_benchmark.offline_e2e" ;
python -m pytest tests/dr_benchmark tests/roles tests/architecture -q ;
python -m scripts.architecture.verify_lock --consistency ;
python -m scripts.dr_benchmark.gate_a_dry_run
Report files created + the chain it exercises + the assertions + confirm zero network/spend (socket
blocked). Do NOT commit.
