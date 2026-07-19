export const meta = {
  name: 'docstring-A-finalize',
  description: 'Decision A: reframe docstring PR claims to accurate wording + restore the 4 over-reverted API-model docstrings, oracle+collection re-checked',
  phases: [
    { title: 'Reframe', detail: 'edit PR bodies + docs to "pipeline byte-identical; API docs improved (OpenAPI descriptions added)"' },
    { title: 'Restore', detail: 'restore the 4 reverted class docstrings on phase3a-b2' },
    { title: 'Verify', detail: 'oracle SHA + collection unchanged' },
    { title: 'Record', detail: 'commit + push' },
  ],
}
const PY = '/home/polaris/pipeline-env/bin/python'
const GOLDEN = '9c0a3d438da943242c98e2fe714494c342d42d02102202d75a61a4554339db98'
const GH = '/home/polaris/.local/bin/gh'

phase('Reframe')
const reframe = await agent(
  `Decision A on the docstring PRs: the docstrings improve API docs but change the OpenAPI schema descriptions; correct the over-broad "byte-identical" claim to accurate wording. Do:
1. Edit the two docstring docs in their worktrees to add an honest 'Scope of "byte-identical"' note: pipeline behaviour (RACE, faithfulness, data I/O) is byte-identical and oracle-proven (9c0a3d43); the API's OpenAPI schema GAINS documentation descriptions (operation + model descriptions) — an INTENDED improvement (Plan V4 concern #5), and no test/committed artifact depends on the prior empty descriptions (collection unchanged 16738/11). Files: /home/polaris/wt/phase3a/docs/review_readiness/phase3a_docstrings.md (branch chore/review-readiness-phase3a) and /home/polaris/wt/phase3ab2/docs/review_readiness/phase3a_docstrings_b2.md (branch chore/review-readiness-phase3a-b2). Commit+push each (explicit path stage; guard 0 tests/oracle staged).
2. Update the PR descriptions via gh: '${GH} pr edit 1386 --repo aldrinor/deep-cove-research --body "..."' and '${GH} pr edit 1387 --repo aldrinor/deep-cove-research --body "..."' with the accurate framing (pipeline byte-identical / oracle-proven; API OpenAPI schema gains documentation descriptions — intended, no consumer depends on prior schema).
Return what you edited + confirmation both PR bodies updated.`,
  { label: 'reframe', phase: 'Reframe', schema: { type:'object', additionalProperties:false, required:['docs_edited','pr_bodies_updated','notes'], properties:{ docs_edited:{type:'array',items:{type:'string'}}, pr_bodies_updated:{type:'boolean'}, notes:{type:'string'} } } })

phase('Restore')
const restore = await agent(
  `On branch chore/review-readiness-phase3a-b2 (worktree /home/polaris/wt/phase3ab2), the batch-2 audit REVERTED 4 pydantic-model docstrings because they feed OpenAPI schema descriptions: FollowUpAnswer (src/polaris_v6/followup/schema.py), ScopeDecision (src/polaris_v6/scope/decision.py), TemplateContent + FrameDefinition (src/polaris_v6/templates/registry.py). Under Decision A (API docs are a desired improvement), RESTORE accurate one-line class docstrings on these 4 classes (documenting the model's contract). Make each docstring ACCURATE to the class fields. py_compile; keep collection at baseline (16738/11). Return the 4 docstrings added + confirm accurate.`,
  { label: 'restore', phase: 'Restore', schema: { type:'object', additionalProperties:false, required:['restored','collection','accurate'], properties:{ restored:{type:'integer'}, collection:{type:'string'}, accurate:{type:'boolean'} } } })

phase('Verify')
const verify = await agent(
  `Verify the docstring-A changes on /home/polaris/wt/phase3ab2 (branch chore/review-readiness-phase3a-b2) are still pipeline-safe.
1. Overlay oracle by COPY: cp -n /home/polaris/wt/phase0/tests/oracle/*.py /home/polaris/wt/phase3ab2/tests/oracle/ 2>/dev/null; cp -n /home/polaris/wt/phase0/tests/oracle/cassettes/* /home/polaris/wt/phase3ab2/tests/oracle/cassettes/ 2>/dev/null.
2. Oracle replay: 'cd /home/polaris/wt/phase3ab2 && PG_OUTLINE_AGENT_MAX_TURNS=3 ${PY} tests/oracle/acceptance_portable.py --replay 2>&1 | tail -10' — SHA==${GOLDEN}, controls pass.
3. Collection == 16738/11.
Return oracle_matches, oracle_sha, collection_ok.`,
  { label: 'verify', phase: 'Verify', schema: { type:'object', additionalProperties:false, required:['oracle_matches','oracle_sha','collection_ok'], properties:{ oracle_matches:{type:'boolean'}, oracle_sha:{type:'string'}, collection_ok:{type:'boolean'} } } })

phase('Record')
const rec = await agent(
  `Record the restored 4 docstrings on /home/polaris/wt/phase3ab2 (branch chore/review-readiness-phase3a-b2) if verify passed (oracle_matches=${verify.oracle_matches}, collection_ok=${verify.collection_ok}).
Stage EXPLICIT paths only: 'git add src/' (guard: 'git diff --cached --name-only | grep -c tests/oracle' MUST be 0; if not, git restore --staged tests/oracle/). Commit ("Phase 3A batch 2: restore 4 API-model docstrings under decision A (API docs intended; pipeline byte-identical)") with the standard Co-Authored-By/Claude-Session trailers. Push (updates PR #1387).
Return {commit_sha, pushed}.`,
  { label: 'record', phase: 'Record', schema: { type:'object', additionalProperties:false, required:['commit_sha','pushed'], properties:{ commit_sha:{type:'string'}, pushed:{type:'boolean'} } } })

return { reframe, restore, verify, record: rec }
