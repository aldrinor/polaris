# Codex DIFF review — I-rdy-007 / GH #503: define the live-run artifact contract

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 1. What you are reviewing

The commit-1 diff for #503 — `git diff origin/polaris...HEAD` excluding
`.codex/I-rdy-007/` and `outputs/audits/I-rdy-007/` (the canonical diff in
`.codex/I-rdy-007/codex_diff.patch`, sha256 trailer). It implements the
Codex-APPROVE'd brief `.codex/I-rdy-007/brief.md` (brief APPROVE iter 2).
**2 new files, +418, `docs/` only:**

- `docs/live_run_artifact_contract.md` — the contract document.
- `docs/schemas/live_run_artifact_contract.schema.json` — the JSON Schema.

#503 is a **definition** issue (Phase 3.4). It changes only `docs/` — no
`src/`, `web/`, config, or test code. Wiring consumers to live runs is #504.
Do NOT flag "the rich surfaces are still fixture-bound" as a finding — closing
that is #504's job; #503 only documents the contract + the gap list.

## 2. Verify against the brief + the running code

1. **Status taxonomy is the code-defined 14, not the stale 10.** The contract
   §3 + the schema `$defs.pipeline_status.enum` must list exactly the 14
   values in `src/polaris_v6/schemas/run_status.py` `PipelineStatus` /
   `scripts/run_honest_sweep_r3.py` `UNIFIED_STATUS_VALUES`. Confirm none
   missing/extra.
2. **`verification_details.json` is present** in both the contract's required-
   file set and the schema `$defs` — it is a `load_audit_ir()`-required file.
3. **Required-vs-optional file split** matches `loader.py` `load_audit_ir()`:
   5 required, `evaluator_rule_checks.json`+`judge_output.json` both-or-neither,
   `protocol.json` / `corpus_approval.json` optional.
4. **Status-conditional availability** (§2.3) — the contract states abort/error
   dirs are not AuditIR-loadable; the schema root `required` is `["manifest"]`
   only (verification_details / evidence_pool NOT root-required).
5. **The schema is valid + matches reality.** `Draft202012Validator.check_schema`
   passes; the schema validates a real success artifact + a real abort
   artifact (claude_audit.md §3 records the run). Confirm the schema is not
   over-strict (would reject real artifacts) nor vacuous.
6. **Bundle's two routes** are both named in the §6 mapping table.
7. **No overclaim / no idealized fields** — the contract documents what the
   code actually does; the two grounding findings (`dropped_due_to_failure`
   boolean typing; pre-taxonomy `status`-less manifests) are recorded honestly.

## 3. Files I have ALSO checked and they're clean

- `src/polaris_graph/audit_ir/loader.py` — the loader the contract is grounded
  in; read in full; NOT modified.
- `src/polaris_v6/schemas/run_status.py`, `scripts/run_honest_sweep_r3.py`
  (`UNIFIED_STATUS_VALUES`) — the status-taxonomy source; NOT modified.
- `src/polaris_v6/api/artifact_to_slice_chain.py` — the bridge; read for the
  bundle path; NOT modified.
- `web/lib/contracts.ts` — the I-ecg-003 EvidenceContract; explicitly
  distinguished in contract §8; NOT modified.
- `docs/pipeline_audit_context/03_json_contracts.md` — the stale prose
  contract; referenced + flagged stale; NOT modified.

## 4. Diff shape

The deliverable is in `docs/` (NOT under the CI-excluded `outputs/audits/I-rdy-007/`),
so the canonical diff contains the two real `docs/` files plus the
`state/polaris_restart/iteration_trajectory.md` append. No code — nothing to
smoke-test beyond the schema validation already run (claude_audit.md §3).

## 5. Required output schema (§8.3.9)

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
