export const meta = {
  name: 'docstrings-b3-nonapi',
  description: 'Docstring batch 3: next ~50 docstrings on NON-API public modules (generation/retrieval/synthesis/orchestration) — no OpenAPI surface; AST-equivalence + __doc__-audit + oracle gated',
  phases: [
    { title: 'Setup', detail: 'worktree from b2 + correct harness + find non-API targets' },
    { title: 'Document', detail: 'add docstrings to non-API public symbols, accurate claims' },
    { title: 'Validate', detail: 'AST-equivalence + __doc__-audit + oracle + collection' },
    { title: 'Codex-Gate', detail: 'codex DOCS-SAFE' },
    { title: 'Record', detail: 'commit + push + PR' },
  ],
}
const PY = '/home/polaris/pipeline-env/bin/python'
const GOLDEN = '9c0a3d438da943242c98e2fe714494c342d42d02102202d75a61a4554339db98'
const WT = '/home/polaris/wt/phase3ab3'

phase('Setup')
const setup = await agent(
  `Set up docstring batch 3 (builds on batches 1+2 at chore/review-readiness-phase3a-b2).
1. cd /workspace/POLARIS && git worktree remove ${WT} --force 2>/dev/null; git branch -D chore/review-readiness-phase3a-b3 2>/dev/null; git worktree add ${WT} -b chore/review-readiness-phase3a-b3 chore/review-readiness-phase3a-b2.
2. Force-copy phase0 oracle harness (unstaged, for validation): cp /home/polaris/wt/phase0/tests/oracle/*.py ${WT}/tests/oracle/ ; cp /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_golden.json /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_llm.jsonl /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_retrieval.jsonl ${WT}/tests/oracle/cassettes/.
3. Find the next ~50 highest-value public functions/classes/modules WITHOUT a docstring, EXCLUDING anything under an api/ package or any FastAPI-decorated function or pydantic BaseModel used as a response/request model (avoid the OpenAPI surface entirely — those are handled). Prioritize NON-API public modules: src/polaris_graph/generator/**, retrieval/**, synthesis/**, agents/**, roles/**, orchestration internals. Skip private (_) unless a key public contract. Exclude files batches 1+2 already documented.
4. Baseline collection: '${PY} -m pytest tests/ --collect-only -q | tail -1' (16738/11).
Return targets (file:symbol), count, baseline, and confirm none are FastAPI/pydantic-model/api-package symbols.`,
  { label: 'setup', phase: 'Setup', schema: { type:'object', additionalProperties:false, required:['targets','target_count','baseline','no_api_surface'], properties:{ targets:{type:'array',items:{type:'object',additionalProperties:true}}, target_count:{type:'integer'}, baseline:{type:'string'}, no_api_surface:{type:'boolean'} } } })

phase('Document')
const doc = await agent(
  `Add docstrings to the non-API targets in ${WT}. Targets: ${JSON.stringify(setup.targets)}.
RULES: docstrings only (first statement of module/class/function) — no logic/signature/import changes. Accurate Raises/return claims (verify against the code before documenting). Skip any symbol whose __doc__ is consumed at runtime (getdoc/help/pydoc/doctest/argparse) — record it. After ~15 files run collection = ${setup.baseline}; py_compile; revert failures.
Return docstrings_added, files_changed, skipped_loadbearing, collection_after, claims_accurate.`,
  { label: 'document', phase: 'Document', schema: { type:'object', additionalProperties:false, required:['docstrings_added','files_changed','skipped_loadbearing','collection_after','claims_accurate'], properties:{ docstrings_added:{type:'integer'}, files_changed:{type:'integer'}, skipped_loadbearing:{type:'array',items:{type:'string'}}, collection_after:{type:'string'}, claims_accurate:{type:'boolean'} } } })

phase('Validate')
const validate = await agent(
  `Validate batch-3 docstrings in ${WT}. 1. Docstring-stripped AST equivalence across all changed src/ files (strip docstrings, ast.unparse, assert identical to HEAD) — report pass + failures. 2. __doc__-consumer audit: confirm 0 load-bearing among added (grep getdoc/help/pydoc/doctest/fastapi/pydantic on the changed symbols). 3. Oracle replay: 'cd ${WT} && PG_OUTLINE_AGENT_MAX_TURNS=3 ${PY} tests/oracle/acceptance_portable.py --replay 2>&1 | tail -8' SHA==${GOLDEN}. 4. Collection == ${setup.baseline}. Return ast_equivalence_all_pass (+failures), no_loadbearing, oracle_matches, oracle_sha, collection_ok.`,
  { label: 'validate', phase: 'Validate', schema: { type:'object', additionalProperties:false, required:['ast_equivalence_all_pass','ast_failures','no_loadbearing','oracle_matches','oracle_sha','collection_ok'], properties:{ ast_equivalence_all_pass:{type:'boolean'}, ast_failures:{type:'array',items:{type:'string'}}, no_loadbearing:{type:'boolean'}, oracle_matches:{type:'boolean'}, oracle_sha:{type:'string'}, collection_ok:{type:'boolean'} } } })

phase('Codex-Gate')
const gate = await agent(
  `Run CODEX (GPT-5.6) to gate batch-3 docstrings. Write /tmp/b3_gate.md then 'cd /tmp && timeout 200 codex exec --skip-git-repo-check - < /tmp/b3_gate.md 2>&1 | tail -22' (embed inline; medium; no sandbox flags).
These are NON-API-surface docstrings (no FastAPI/pydantic-model symbols). Evidence: doc=${JSON.stringify(doc)}, validate=${JSON.stringify(validate)} (AST docstrings-only, 0 load-bearing __doc__, oracle byte-identical ${GOLDEN}, collection baseline).
Ask codex: "Provably zero-behaviour-change docstrings-only batch on non-API modules (no OpenAPI surface, no load-bearing __doc__, accurate claims)? End with DOCS-SAFE or DOCS-REVISE."
Return verdict + points.`,
  { label: 'codex-gate', phase: 'Codex-Gate', schema: { type:'object', additionalProperties:false, required:['verdict','codex_points'], properties:{ verdict:{type:'string'}, codex_points:{type:'array',items:{type:'string'}} } } })

phase('Record')
const rec = await agent(
  `Record batch-3 in ${WT} (branch chore/review-readiness-phase3a-b3). Commit if validate passed (ast_equivalence_all_pass, oracle_matches, collection_ok) and codex=DOCS-SAFE (${gate.verdict}). Stage EXPLICIT 'git add src/' + a short docs/review_readiness/phase3a_docstrings_b3.md; GUARD 'git diff --cached --name-only | grep -c tests/oracle' == 0 (else git restore --staged tests/oracle/). Commit ("Phase 3A batch 3: non-API public docstrings (docstrings-only, oracle byte-identical)") with standard trailers. Push -u origin; PR base gate-inversion.
Return {commit_sha, pushed, pr_url, committed_or_blocked, oracle_files_staged}.`,
  { label: 'record', phase: 'Record', schema: { type:'object', additionalProperties:false, required:['commit_sha','pushed','pr_url','committed_or_blocked','oracle_files_staged'], properties:{ commit_sha:{type:'string'}, pushed:{type:'boolean'}, pr_url:{type:'string'}, committed_or_blocked:{type:'string'}, oracle_files_staged:{type:'integer'} } } })

return { setup: { target_count: setup.target_count }, doc, validate, gate, record: rec }
