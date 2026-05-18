# Codex BRIEF review — I-rdy-007 / GH #503: define the live-run artifact contract

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 0. Stage

Pre-implementation **brief** review — you are reviewing the *plan* (acceptance-criteria correctness + scope), NOT a diff. No code/doc is written yet. The diff review is a separate later Codex call.

## 0.1 Iter-1 findings folded in

- **P1-001** — the contract/schema uses the **code-defined** pipeline-status set
  (`src/polaris_v6/schemas/run_status.py` PipelineStatus + `scripts/run_honest_sweep_r3.py`
  UNIFIED_STATUS_VALUES — currently 14 values incl. `partial_outline_fallback`,
  `partial_evaluator_advisory`, `partial_qwen_advisory`, `abort_evaluator_critical`),
  NOT the stale 10-value list in `03_json_contracts.md`. The doc explicitly
  flags `03_json_contracts.md` as stale on this point.
- **P1-002** — `verification_details.json` is included: `load_audit_ir()` loads
  it as a required file and the bridge depends on it for VerifiedReport /
  per-sentence provenance. Both the contract doc and the JSON schema cover it.
- **P2-001** — the provenance-file specifics are documented (see §3).
- **P2-002** — schema validation IS run at implement time (see §6) — the brief
  no longer claims "no test."
- **P2-003** — the bundle surface's two distinct routes are both named (§3).

## 1. Issue

GH #503 (I-rdy-007) — Phase 3.4 of the Carney readiness chain: **"Define the
contract mapping a completed run's artifacts to what the inspector, charts,
follow-up, compare, pin replay, memory, and bundle each consume. This is the
root fix for the fixture-bound rich surfaces."**
Acceptance: *contract documented + schema'd; Codex APPROVE.* Depends on
I-rdy-003 (#499, closed).

This is a **definition** issue — it produces a documentation + schema artifact.
It does NOT wire any consumer to live runs — that is #504 (I-rdy-008), which
`depends on: I-rdy-007`. #506 and #508 also depend on #503. #503 is the
linchpin: three downstream issues consume this contract, so grounding accuracy
matters.

## 2. Grounded scan already done (the producer → consumer chain)

- **Producer:** v6 `src/polaris_v6/queue/run_store.py` — the `runs` SQLite table
  (`run_id`, `template`, `question`, `lifecycle_status`, `pipeline_status`,
  `manifest_run_id`, `artifact_dir`, `cost_usd`, `result_json`, timestamps).
  A completed run's `artifact_dir` holds the pipeline-A artifact set.
- **`pipeline_status` value set:** the AUTHORITATIVE source is the code —
  `src/polaris_v6/schemas/run_status.py` + `scripts/run_honest_sweep_r3.py`
  `UNIFIED_STATUS_VALUES` (14 values). `docs/pipeline_audit_context/03_json_contracts.md`
  lists only 10 and is **stale** — the new contract supersedes it.
- **Artifact set in `artifact_dir`:** `manifest.json` (verdict + adequacy/
  corpus/generator/evaluator blocks), `report.md` (2 shapes — success vs
  abort), `bibliography.json`, `verification_details.json` (**loader-required**
  — per-sentence verify detail), `contradictions.json`, `corpus_approval.json`,
  `protocol.json` (the scope template — feeds tier-expectation metadata),
  `evidence_pool.json` / `live_corpus_dump.json`, `evaluator_rule_checks.json`
  (pairs with `judge_output.json` / legacy `qwen_judge_output.json`),
  `reasoning_trace.jsonl` (present for V4-Pro reasoning runs; included by the
  live tar.gz bundle when present), `run_log.txt`.
- **Loader:** `src/polaris_graph/audit_ir/loader.py` `load_audit_ir(artifact_dir)`
  → canonical `AuditIR` (BibliographyEntry, ReportSentence, ReportSection,
  VerifiedReport, ContradictionCluster, RetrievalAttempt, FrameCoverageReport).
  `verification_details.json` is a required input.
- **Bridge:** `src/polaris_v6/api/artifact_to_slice_chain.py` (I-arch-001d) —
  `AuditIR` → slice-chain Pydantic (ScopeDecision, EvidencePool, VerifiedReport).
- **Consumer API routes:** `src/polaris_v6/api/{runs,stream,charts,compare,followup,memory,bundle}.py`.
- **Consumer web surfaces:** `web/app/{inspector,runs,charts_test,pin_replay,memory,audit_live,contracts}/`.
- **Prior art (do not collide):** `web/lib/contracts.ts` is the *EvidenceContract*
  (I-ecg-003, the PRE-run expected-claims contract), NOT the live-run artifact
  contract; #503's artifact is new and distinctly named.

## 3. The plan — 2 deliverables, definition only

1. **`docs/live_run_artifact_contract.md`** — the contract document. Sections:
   - Producer: a completed v6 run, its `run_store` row, the `artifact_dir`
     file set; `manifest.status` (the **code-defined 14-value** set) as the
     single authoritative verdict; the success-vs-abort `report.md` shape split.
   - Canonical-IR layer: `load_audit_ir()` → `AuditIR`, the one loader all rich
     surfaces resolve a run through; `verification_details.json` required.
   - **Per-consumer mapping table** — for each surface: the v6 API route(s)
     serving it, the `AuditIR`/artifact fields it requires, current state
     (live-capable vs fixture-bound). The **bundle** row names BOTH routes:
     `/runs/{id}/bundle` (today still golden EvidenceContract JSON) and
     `/runs/{id}/bundle.tar.gz` (live `artifact_dir`-backed) — so #504 does not
     treat bundle as already fully live.
   - Explicit **gap list**: every surface that today only works on golden
     fixtures, named as concrete wiring work for #504.
2. **`docs/schemas/live_run_artifact_contract.schema.json`** — a JSON Schema
   (draft 2020-12) for the artifact-dir JSON files: `manifest.json` (with the
   14-value `status` enum from the code), `bibliography.json`,
   `verification_details.json`, `contradictions.json`, `corpus_approval.json`,
   `evidence_pool.json`. `protocol.json`, `evaluator_rule_checks.json`,
   `judge_output.json` and `reasoning_trace.jsonl` are documented in the
   contract doc as optional/conditional and schema'd where their shape is
   stable. `docs/schemas/` is already a tracked directory.

**Grounding rule (per the "verify against the running system, not docs"
standard):** the contract is authored by reading `run_status.py`,
`run_honest_sweep_r3.py` (status set), `loader.py`, `artifact_to_slice_chain.py`,
and each consumer API route IN FULL at implement time, plus a real artifact dir
under `outputs/honest_sweep_r3/`. The doc states what the code *actually* does
and flags every divergence from `03_json_contracts.md` (which is stale on the
status count) rather than restating it.

## 4. Scope boundary

- IN: the contract doc + the JSON schema. Pure documentation/schema artifacts.
- OUT: wiring any consumer to live runs (#504); changing any producer, loader,
  bridge, or API code (zero `src/` or `web/` change in #503); the
  EvidenceContract in `web/lib/contracts.ts` (unrelated, untouched).

## 5. Files I have ALSO checked and they're clean

- `docs/pipeline_audit_context/03_json_contracts.md` + `04_sample_run_artifacts.md`
  — existing prose contract; the new doc references them and flags the stale
  10-value status list; does not modify them.
- `web/lib/contracts.ts` — the I-ecg-003 EvidenceContract; distinct name, no
  collision; untouched.
- `.github/workflows/codex-required.yml` — the canonical-diff gate excludes
  `.codex/I-rdy-007/` + `outputs/audits/I-rdy-007/`; the diff is `docs/` only.

## 6. Acceptance criteria for THIS PR

1. `docs/live_run_artifact_contract.md` — producer → AuditIR → per-consumer
   mapping for all 7 surfaces (bundle row names both routes) + the explicit
   fixture-bound gap list; `manifest.status` uses the code-defined 14-value set.
2. `docs/schemas/live_run_artifact_contract.schema.json` — valid draft-2020-12
   JSON Schema covering `manifest.json` / `bibliography.json` /
   `verification_details.json` / `contradictions.json` / `corpus_approval.json`
   / `evidence_pool.json`.
3. **Schema validation RUN at implement time** (recorded in `claude_audit.md`):
   `jsonschema.Draft202012Validator.check_schema(...)` passes; AND the schema
   validates cleanly against one real `status=success` artifact dir and one
   real `abort_*` artifact dir from `outputs/honest_sweep_r3/`.
4. The contract is grounded in actual `run_status.py` / `loader.py` / bridge /
   API code; divergences from `03_json_contracts.md` flagged.
5. No `src/` / `web/` / config / test change.

## 7. Required output schema (§8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

Loose verdict prose is rejected — emit the schema.
