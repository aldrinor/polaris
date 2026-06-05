# Claude architect audit — I-ready-016b (#1097): activate the readiness faithfulness flags in the Gate-B slate

Reviewer: Claude (architect). Scope: the END RESULT on `bot/I-ready-consolidated` (activation commit `78770645` + test-fixture commit `50040d91`). Method: §-1.1 line-by-line.

## 1. The gap closed

The 4 new readiness features shipped flag-gated **default OFF** (so each PR was byte-identical), but a grep of `scripts/dr_benchmark/run_gate_b.py` confirmed the Gate-B full-capability slate set **none** of them — so a full beat-both run would have left them OFF and the entire readiness audit would have been inert on the actual paid run. That is the silent-downgrade class the operator forbids. This change activates the 3 benchmark-relevant ones.

## 2. The change (verified)

- `run_gate_b_query()`: three `os.environ[...] = "1"` force-on lines (`PG_USE_SAFETY_REFUSAL`, `PG_SWEEP_NLI_CONFLICT`, `PG_SWEEP_TABLE_CELL_VERIFY`) immediately after the existing `PG_NLI_IN_BENCHMARK` force-on, with the identical `.env=0 must not win` rationale — so a conservative operator `.env=0` cannot silently downgrade a faithfulness layer. VERIFIED against the committed diff.
- `_BENCHMARK_PREFLIGHT_REQUIRED_FLAGS`: the same three added, so `preflight_full_capability()` raises (RuntimeError, zero spend) if any is off at preflight — the fail-closed no-silent-downgrade guard. VERIFIED.
- `PG_DOC_INGEST_BACKEND` correctly LEFT OUT (Codex brief-gate caught that adding it to the slate would crash `apply_full_capability_benchmark_slate` via `float('local')`, and the benchmark never reads it — it's a UI/upload-path/deployment-env setting). VERIFIED absent from `run_gate_b.py`.

## 3. Faithfulness-safety

All three only ADD a layer; none weakens or bypasses any gate:
- **Safety-refusal** operates on the input *question* upstream of retrieval/generation; fails OPEN on classifier error; high-precision on explicit harm-intent (never over-refuses clinical/policy research). It cannot drop a verified claim.
- **NLI semantic-conflict** is additive contradiction *surfacing* — it gates/drops no generated prose; it only discloses more disagreement (routed to the disclosure block + PT08).
- **Table-cell verify** DROPS only fabricated/unsupported numeric table rows — same direction as strict_verify; cannot pass a row strict_verify would drop.

None touches the 4-role D8 gate, strict_verify, the entailment verifier (`PG_STRICT_VERIFY_ENTAILMENT=enforce`, already slated), or the report.md verified-only surface. `verify_lock --consistency` = OK; no role/model/family change.

## 4. The diff-gate P2 (folded in)

Adding the three to the preflight required-set broke 4 EXISTING preflight tests in ISOLATION (they manually set the run_gate_b_query force-on flags before calling preflight but not the 3 new ones; the full suite had been masking it via env leakage). Fixed precedent-consistently by adding the 3 to each preflight env setup + the `_clear()` pop list — and the `_clear()` fix unmasked a 3rd file, which was caught by running the **FULL** dr_benchmark suite (290 passed) rather than just the changed file. No production change in this fix.

## 5. Verdict

Closes the silent-downgrade gap (the 3 faithfulness layers are now ON for the benchmark), faithfulness-safe (additive, force-on, fail-closed preflight strengthens the no-downgrade contract), `PG_DOC_INGEST_BACKEND` correctly scoped out (would have crashed the run). Codex brief APPROVE iter-2 + diff APPROVE; 290 dr_benchmark tests green; `verify_lock --consistency` OK.

**Architect verdict: APPROVE.** This makes `bot/I-ready-consolidated` actually exercise the readiness work on a paid run. Remaining before the full run is operator-gated (paid smoke + §-1.1 audit + budget/provider confirm).
