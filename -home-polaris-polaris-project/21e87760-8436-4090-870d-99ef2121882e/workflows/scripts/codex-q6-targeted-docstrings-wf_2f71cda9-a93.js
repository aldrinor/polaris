export const meta = {
  name: 'codex-q6-targeted-docstrings',
  description: 'Execute codex Q6 docstrings: targeted docstrings on public API/state-transitions/safety-gates/non-obvious logic only (reject the ~530 quota); non-API; AST-equiv + __doc__-audit + oracle gated',
  phases: [
    { title: 'Setup', detail: 'worktree from b3 + harness + pick high-value targets (state/gates/non-obvious)' },
    { title: 'Document', detail: 'docstrings on those targets, accurate claims' },
    { title: 'Validate', detail: 'AST-equiv + __doc__-audit + oracle + collection' },
    { title: 'Codex-Gate', detail: 'codex DOCS-SAFE' },
    { title: 'Record', detail: 'commit + push + PR' },
  ],
}
const PY = '/home/polaris/pipeline-env/bin/python'
const GOLDEN = '9c0a3d438da943242c98e2fe714494c342d42d02102202d75a61a4554339db98'
const WT = '/home/polaris/wt/phase3ab4'

phase('Setup')
const setup = await agent(
  `Set up codex-Q6 TARGETED docstrings (codex: public API/state-transitions/safety-gates/non-obvious ONLY — reject numeric quotas).
1. cd /workspace/POLARIS && git worktree remove ${WT} --force 2>/dev/null; git branch -D chore/review-readiness-phase3a-b4 2>/dev/null; git worktree add ${WT} -b chore/review-readiness-phase3a-b4 chore/review-readiness-phase3a-b3.
2. Force-copy phase0 harness (unstaged): cp /home/polaris/wt/phase0/tests/oracle/*.py ${WT}/tests/oracle/ ; cp /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_golden.json /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_llm.jsonl /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_retrieval.jsonl ${WT}/tests/oracle/cassettes/.
3. Find ~30-40 HIGH-VALUE undocumented targets (ast.get_docstring None), NON-API (no FastAPI/pydantic-model/api-package), prioritizing: SAFETY GATES (strict_verify, faithfulness, evidence gates, deletion gates), STATE TRANSITIONS / TypedDict state helpers, and genuinely NON-OBVIOUS public functions. Skip trivial getters/one-liners and anything batches 1-3 already did. Quality over count.
4. Baseline: '${PY} -m pytest tests/ --collect-only -q | tail -1'.
Return targets (file:symbol + why-high-value), count, baseline.`,
  { label: 'setup', phase: 'Setup', schema: { type:'object', additionalProperties:false, required:['targets','count','baseline'], properties:{ targets:{type:'array',items:{type:'object',additionalProperties:true}}, count:{type:'integer'}, baseline:{type:'string'} } } })

phase('Document')
const doc = await agent(
  `Add docstrings to the targeted high-value symbols in ${WT}. Targets: ${JSON.stringify(setup.targets)}. Docstrings only, no logic. Accurate Raises/return (verify vs code). Skip load-bearing __doc__ (getdoc/help/doctest/fastapi/pydantic). For safety gates + state transitions, document the CONTRACT (what invariant it enforces, what it raises/returns). Keep collection at ${setup.baseline}; py_compile. Return docstrings_added, files_changed, skipped_loadbearing, collection_after.`,
  { label: 'document', phase: 'Document', schema: { type:'object', additionalProperties:false, required:['docstrings_added','files_changed','skipped_loadbearing','collection_after'], properties:{ docstrings_added:{type:'integer'}, files_changed:{type:'integer'}, skipped_loadbearing:{type:'array',items:{type:'string'}}, collection_after:{type:'string'} } } })

phase('Validate')
const validate = await agent(
  `Validate ${WT}: 1. docstring-stripped AST equivalence all changed src files (identical to HEAD). 2. __doc__-audit: 0 load-bearing among added. 3. Oracle 'cd ${WT} && PG_OUTLINE_AGENT_MAX_TURNS=3 ${PY} tests/oracle/acceptance_portable.py --replay 2>&1 | tail -6' SHA==${GOLDEN}. 4. Collection == ${setup.baseline}. Return ast_equivalence_all_pass, ast_failures, no_loadbearing, oracle_matches, oracle_sha, collection_ok.`,
  { label: 'validate', phase: 'Validate', schema: { type:'object', additionalProperties:false, required:['ast_equivalence_all_pass','ast_failures','no_loadbearing','oracle_matches','oracle_sha','collection_ok'], properties:{ ast_equivalence_all_pass:{type:'boolean'}, ast_failures:{type:'array',items:{type:'string'}}, no_loadbearing:{type:'boolean'}, oracle_matches:{type:'boolean'}, oracle_sha:{type:'string'}, collection_ok:{type:'boolean'} } } })

phase('Codex-Gate')
const gate = await agent(
  `Run CODEX to gate targeted docstrings. Write /tmp/q6d_gate.md then 'cd /tmp && timeout 200 codex exec --skip-git-repo-check - < /tmp/q6d_gate.md 2>&1 | tail -18' (embed inline; medium; no sandbox flags). Evidence: doc=${JSON.stringify(doc)}, validate=${JSON.stringify(validate)}. These are targeted safety-gate/state/non-obvious NON-API docstrings (codex's Q6 scope). Ask: "Provably docstrings-only (AST-equiv), no load-bearing __doc__, oracle byte-identical, accurate — and appropriately scoped to high-value symbols (not quota-padding)? End DOCS-SAFE or DOCS-REVISE." Return verdict + points.`,
  { label: 'codex-gate', phase: 'Codex-Gate', schema: { type:'object', additionalProperties:false, required:['verdict','codex_points'], properties:{ verdict:{type:'string'}, codex_points:{type:'array',items:{type:'string'}} } } })

phase('Record')
const rec = await agent(
  `Record in ${WT} (branch chore/review-readiness-phase3a-b4). Commit if validate passed + codex DOCS-SAFE (${gate.verdict}). Stage explicit 'git add src/' + docs/review_readiness/phase3a_docstrings_b4.md; GUARD grep -c tests/oracle==0 (else git restore --staged tests/oracle/). Commit ("Phase 3A per codex Q6: targeted docstrings on safety-gates/state/non-obvious (docs-only, oracle byte-identical)") std trailers. Push -u origin; PR base gate-inversion. Return {commit_sha, pushed, pr_url, committed_or_blocked, oracle_files_staged}.`,
  { label: 'record', phase: 'Record', schema: { type:'object', additionalProperties:false, required:['commit_sha','pushed','pr_url','committed_or_blocked','oracle_files_staged'], properties:{ commit_sha:{type:'string'}, pushed:{type:'boolean'}, pr_url:{type:'string'}, committed_or_blocked:{type:'string'}, oracle_files_staged:{type:'integer'} } } })

return { setup: { count: setup.count }, doc, validate, gate, record: rec }
