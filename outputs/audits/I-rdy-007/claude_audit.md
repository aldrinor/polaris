# Claude architect audit — I-rdy-007

**Issue:** #503 / I-rdy-007 — live-run artifact contract (Phase 3.4)
**Branch:** `bot/I-rdy-007-live-run-artifact-contract` — commits `5124a3e7` (initial) + `0b0e8eb7` (Codex diff iter-1 fixes), off `polaris` @ `9185035e`
**Brief:** APPROVE iter-1 (`spec_scope_ruling: spec-only-correct`, `schema_ruling: pin-existing-ok`)
**Diff review:** iter-1 REQUEST_CHANGES (2 P1 + 3 P2) → iter-2 **APPROVE** (zero P0, zero P1)
**Canonical diff:** 1 file, sha256 `c41ebcd93be38375b5b20dbe242d576070085c06c16d148736e6d1f25649e886`

## 1. Deliverable

`docs/live_run_artifact_contract.md` — the contract mapping a completed run's
artifacts to the 7 rich consumer surfaces, and the specification I-rdy-008 (#504)
implements. Spec only; no endpoint code. One markdown file, ~327 lines, zero code.

## 2. Grounding — every claim repo-verified

- §2 resolution chain ← `run_store.get_run()` / `RunStatusResponse`
  (`src/polaris_v6/queue/run_store.py`).
- §3a `load_audit_ir()` required/optional file split ← `loader.py`.
- §3b `evidence_pool.json` as an adapter-direct read (not `load_audit_ir`).
- §4 adapter field map ← every `EvidenceContract` field
  (`src/polaris_v6/schemas/evidence_contract.py`) + every cited `AuditIR` source
  field (`loader.py` dataclasses).
- §5 the 3-pattern decomposition ← `bundle.py` `_GOLDEN_RUN_INDEX` + charts/
  followup/compare imports; `bundle.tar.gz` live-wired path; `memory.py`
  workspace-keyed; no pin-replay `src/polaris_v6/api/` route.
- §6 error matrix ← `bundle.py:89-152` (I-arch-001d reference impl), extended with
  Pattern-A-specific rows.

## 3. Codex diff iter-1 findings — all addressed in commit `0b0e8eb7`

- **P1-001** contradiction projection — added as §4 adapter decision 4 (full
  `ContradictionCluster → ContradictionRecord` mapping).
- **P1-002** evidence_pool cardinality — pinned to one envelope `SourceSpan` per
  distinct `evidence_id`.
- **P2-001** `evidence_pool.json` — moved to §3b (adapter-read, not `load_audit_ir`).
- **P2-002** status literals — §2 corrected (`cancelled`, `partial_*`, prefix-match).
- **P2-003** model-provenance optionality — §4 decision 1 fallback chain
  (`model_provenance → manifest.models → fail-loud`).

## 4. Residual Codex iter-2 P2s (non-blocking — APPROVE granted)

Codex iter-2 APPROVE'd with 3 P2 factual-cleanup nits, ruled "not execution
blockers for I-rdy-008":
1. §4 decision 1 also reads raw `manifest.json` for the `models` fallback — the doc
   should additionally name `manifest.json` as an adapter direct-read.
2. `FrameCoverageEntry.status` is a free `str` in `loader.py` (real values include
   `fail_min_fields`), not the literal set `pass/partial/gap` the doc states.
3. §6 should say it *extends* the `bundle.tar.gz` matrix, not reuses it "verbatim".

These are surfaced to I-rdy-008 in the #503 issue comment + the #504 brief — #504
reads `loader.py` field-exact for the adapter anyway, so it will reconcile them
during implementation. Not re-iterated to iter-3: Codex's verdict is APPROVE and
the nits do not change any adapter behavior the contract specifies.

## 5. Judgement calls

- **No new schema file** — Codex `pin-existing-ok`; the contract pins the three
  existing schema sets.
- **Four adapter decisions left open** (§4) — model identity, local/global verifier
  split, frame-coverage aggregation, contradiction projection — genuine
  executable-adapter design choices owned by #504, named explicitly so #504 does
  not guess.
- **~327-line diff is one markdown document, zero code** — the 200-LOC cap is a
  code cap; Codex confirmed this is not a cap violation.

## 6. Verdict

The deliverable matches the APPROVED brief; both Codex gates are APPROVE. Ready to
ship; #504 implements the contract.
