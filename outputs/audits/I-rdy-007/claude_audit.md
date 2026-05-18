# Claude architect audit — I-rdy-007 (#503)

**Issue:** GH #503 (I-rdy-007) — Phase 3.4: define the live-run artifact
contract. The root fix for the fixture-bound rich surfaces.
**Branch:** `bot/I-rdy-007` off `polaris` HEAD `df7022b1`.
**Commit 1:** `9dc2ccde` — 2 files, +418 (`docs/live_run_artifact_contract.md`,
`docs/schemas/live_run_artifact_contract.schema.json`).
**Brief:** `.codex/I-rdy-007/brief.md` — Codex APPROVE iter 2 (iter 1
REQUEST_CHANGES, 2 P1 fixed — see §4).

## 1. What shipped — definition only

| File | Change |
|---|---|
| `docs/live_run_artifact_contract.md` | NEW — the contract: producer → `load_audit_ir()` → `AuditIR` → per-consumer mapping for all 7 rich surfaces + the fixture-bound gap list for #504. |
| `docs/schemas/live_run_artifact_contract.schema.json` | NEW — draft-2020-12 JSON Schema for the 6 artifact JSON files. |

No `src/` / `web/` / config / test change. #503 is a definition issue;
**wiring** consumers to live runs is #504 (I-rdy-008). Zero runtime risk.

## 2. Grounded in the running code (not in stale docs)

- The **14-value** pipeline-status taxonomy is taken from `PipelineStatus`
  (`src/polaris_v6/schemas/run_status.py`) + `UNIFIED_STATUS_VALUES`
  (`scripts/run_honest_sweep_r3.py`) — verified the two agree.
  `docs/pipeline_audit_context/03_json_contracts.md`'s 10-value list is
  flagged stale in the contract.
- The required-vs-optional artifact split is taken from
  `src/polaris_graph/audit_ir/loader.py` `load_audit_ir()`: 5 required
  (`manifest.json`, `report.md`, `bibliography.json`, `contradictions.json`,
  `verification_details.json`), optional `evaluator_rule_checks.json` +
  `judge_output.json` (both-or-neither), `protocol.json`, `corpus_approval.json`.
- The `AuditIR` field → consumer mapping is taken from the loader dataclass
  tree + the loader docstring's design rule ("AuditIR is the single source of
  truth for the Evidence Inspector and all derivative renderers").
- The per-consumer current-state column is the I-rdy-002 (#498) verification
  recorded in `docs/polaris_locked_scope.md` §3.1 — not re-derived.

## 3. Verification — schema validation RAN (acceptance criterion 3)

`jsonschema.Draft202012Validator.check_schema(...)` → **PASS** (valid
draft-2020-12 schema). Per-file validation against real artifact dirs:

- **success** — `outputs/honest_sweep_r3/clinical/clinical_tirzepatide_t2dm/`
  (`status=success`): manifest / bibliography / verification_details /
  contradictions / corpus_approval / evidence_pool → **all VALID**.
- **abort** — `outputs/honest_sweep_r6_validation/tech/tech_rag_architectures_2024/`
  (`status=abort_corpus_inadequate`): manifest VALID; the AuditIR-required
  files correctly absent (§2.3 of the contract — abort dirs are not
  AuditIR-loadable). **VALID.**

Both acceptance artifacts pass. Two grounding findings surfaced and were
captured rather than papered over:
- `verification_details.json` `dropped_due_to_failure` is producer-emitted as
  a boolean `false` for the zero case (not `0`); `loader.py` `int()`-coerces
  it. The schema accepts `["integer","boolean"]` with a comment; the doc
  flags the loose typing.
- A bonus 3rd dir (`honest_sweep_r6_validation/.../clinical_afib_anticoagulation`)
  has a `manifest.json` with NO `status` field — a pre-taxonomy artifact that
  `load_audit_ir()` itself rejects. Documented in contract §3 as a
  non-conformant legacy case; NOT a schema defect (the schema correctly
  requires `status`, matching the loader).

## 4. Codex iteration trail (brief)

- **iter 1 REQUEST_CHANGES** (2 P1, 3 P2): brief anchored on the stale
  10-value status list (real = 14); the schema plan omitted
  `verification_details.json` (a loader-required file). Both fixed in the
  iter-2 brief, plus the 3 P2 (provenance-file specifics, schema-validation
  requirement, bundle's two routes).
- **iter 2 APPROVE** (1 non-blocking P2): status-condition the AuditIR
  requirement — folded into the contract §2.3 and the schema (verification/
  evidence not in the root `required` list).

## 5. Scope + residuals

- #503 defines the contract; it does not wire any consumer — that is #504,
  which `depends on: I-rdy-007`. The contract's §7 gap list is the explicit
  #504 work item set.
- `evidence_pool.json` is schema'd permissively (`["array","object"]`) — its
  shape is run-dependent and the loader does not parse it directly (the
  bridge does). The contract doc describes it; tightening it is deferred to
  whenever its shape is frozen.

## 6. Verdict

Faithful to the iter-2 APPROVE'd brief; the contract is grounded in
`run_status.py` / `loader.py` / the bridge / the lock doc, not idealized;
schema validates clean against a real success + a real abort artifact; two
honest grounding findings captured. Ready for Codex diff review.
