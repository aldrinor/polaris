# Codex review of M-6

## Verdict
PARTIAL

## FINAL_PLAN compliance
- Covered: model versions are surfaced via `model_provenance` and rule checks; a reproducibility hash is surfaced as `protocol_sha256`; one-click export exists.
- Missing / partial: the shipped surface does not fully match `FINAL_PLAN.md:70`.
- "Run hash" is not present as a first-class field in the IR; View 4 shows `run_id` instead (`src/polaris_graph/audit_ir/loader.py:339-359`, `scripts/static/inspector/inspector.js:1097-1100`).
- "Retrieval queries" are not persisted in the IR. `RetrievalStats` only carries counts by provider, and the view only renders those counts (`src/polaris_graph/audit_ir/loader.py:323-330`, `src/polaris_graph/audit_ir/loader.py:647-664`, `scripts/static/inspector/inspector.js:1149-1165`).
- "Abort gates" are only partially surfaced. View 4 renders the evaluator gate, but not corpus adequacy / corpus approval gate detail as structured UI (`scripts/static/inspector/inspector.js:1167-1182`, `src/polaris_graph/audit_ir/loader.py:366-388`, `src/polaris_graph/audit_ir/loader.py:889-952`).
- "One-click PDF audit-bundle export" is not what shipped. The control and endpoint are ZIP-only (`outputs/codex_findings/v30_final_plan/FINAL_PLAN.md:70`, `scripts/static/inspector/inspector.js:1088`, `src/polaris_graph/audit_ir/inspector_router.py:99-182`).

## Audit-bundle endpoint
- Phase A pattern is acceptable for run-14-size artifacts, but this is not true streaming. The endpoint builds the full ZIP in RAM and then emits `buf.getvalue()` (`src/polaris_graph/audit_ir/inspector_router.py:137-180`). Fine now; cache/seal per run once this is not a single-lane demo.
- `INDEX.txt` is too thin for procurement. It omits explicit `protocol_sha256`, model IDs, gate decisions, and any per-file digests even though the docstring promises "run hashes" (`src/polaris_graph/audit_ir/inspector_router.py:103-106`, `src/polaris_graph/audit_ir/inspector_router.py:140-165`).
- Files to add: `run_log.txt` for scope SHA + stage trail, `live_corpus_dump.json` for corpus/tier provenance, and optionally `cost_ledger.jsonl` if cost audit matters (`docs/pipeline_audit_context/16_pass_9_sweep_content_audit.md:28-40`, `docs/pipeline_audit_context/03_json_contracts.md:210-223`).
- Files to remove: none of the current 12 look wrong. `completeness.json`, `corpus_adequacy.json`, `corpus_approval.json`, and `human_gap_tasks.json` belong here.
- I would not use HMAC as the procurement-facing tamper-evidence mechanism. Prefer a detached signature or at minimum a `MANIFEST.SHA256`; HMAC is symmetric and not independently verifiable by third parties.

## Specific issues
- Medium: `scripts/static/inspector/inspector.js:1228-1245` has tier-band edge bugs. `Number(exp.max_fraction || 1)` converts an explicit `0` max to `1`, so a forbidden tier would always render in-band. The loop also ignores actual tiers absent from `expected_tier_distribution`, so unexpected `UNKNOWN` drift is silent.
- Medium: `src/polaris_graph/audit_ir/inspector_router.py:154-170` silently skips missing bundle files and still returns `200`. For an audit bundle, missing canonical artifacts should fail loud or be explicitly called out.
- Low: `scripts/static/inspector/inspector.js:1053-1070` suppresses the invariant banner entirely when `model_provenance` is absent. That should be a warning state, not silence.
- Low: `scripts/static/inspector/inspector.js:1056-1058` emits `methods-two-family-banner-violation`, but `scripts/static/inspector/inspector.css:1277-1295` defines no distinct violation style.
- Low: `src/polaris_graph/audit_ir/inspector_router.py:101-109` says the endpoint streams a ZIP and includes run hashes / extracted frame coverage. The implementation buffers in memory and includes no explicit hash lines or extracted `frame_coverage_report` artifact.

## Recommended changes
- Decide the contract: either add a PDF bundle renderer, or update `FINAL_PLAN.md` / UI copy so Phase A explicitly promises ZIP, not PDF.
- Extend the IR or a companion endpoint so View 4 can show retrieval queries and non-evaluator gates. Right now the schema only supports retrieval counts plus evaluator gate.
- Harden the bundle: include full hash lines in `INDEX.txt`, add `run_log.txt` + `live_corpus_dump.json` (+ `cost_ledger.jsonl` if desired), and fail loud on missing expected files.
- Fix the tier-band logic with nullish-safe parsing and add a residual row for unexpected actual tiers.
- Add warning/violation states and tests for `model_provenance == null` and same-family pairs.

## M-7 readiness
The IR is ready enough for the aggregate Source Tier Mix view: `tier_mix.fractions`, `tier_mix.corpus_count`, `tier_mix.approved/material_deviation`, and `protocol.expected_tier_distribution` are already loaded (`src/polaris_graph/audit_ir/loader.py:288-330`, `src/polaris_graph/audit_ir/loader.py:859-872`). If M-7 wants corpus-member drilldown, add `live_corpus_dump.json` ingestion soon.

## Final word
PARTIAL with edits. I would not GREEN-lock M-6 against `FINAL_PLAN.md` as written, mainly because the shipped surface is ZIP-not-PDF and it still lacks run-hash, retrieval-query, and full abort-gate coverage.
