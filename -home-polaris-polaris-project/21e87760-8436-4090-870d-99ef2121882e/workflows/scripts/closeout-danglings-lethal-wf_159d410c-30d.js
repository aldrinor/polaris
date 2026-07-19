export const meta = {
  name: 'closeout-danglings-lethal',
  description: 'Close codex readiness blockers: repair 2 dead-script dangling imports + lethal_retrieve canonical rename with compat alias (has active test imports)',
  phases: [
    { title: 'Fix', detail: 'repair 2 dangling imports + rename lethal_retrieve with backward-compat alias' },
    { title: 'Verify', detail: 'collection + oracle + old refs resolve' },
    { title: 'Codex-Gate', detail: 'codex confirms both closed, byte-safe' },
    { title: 'Record', detail: 'commit + push + PR' },
  ],
}
const PY = '/home/polaris/pipeline-env/bin/python'
const GOLDEN = '9c0a3d438da943242c98e2fe714494c342d42d02102202d75a61a4554339db98'
const WT = '/home/polaris/wt/phase-closeout'

phase('Fix')
const fix = await agent(
  `Close two codex-identified readiness blockers. Fresh worktree from the FILE-RENAME branch (so the dangling imports exist there):
1. cd /workspace/POLARIS && git worktree remove ${WT} --force 2>/dev/null; git branch -D chore/review-readiness-closeout 2>/dev/null; git worktree add ${WT} -b chore/review-readiness-closeout chore/review-readiness-filerename.
2. Force-copy phase0 harness (unstaged): cp /home/polaris/wt/phase0/tests/oracle/*.py ${WT}/tests/oracle/ ; cp /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_golden.json /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_llm.jsonl /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_retrieval.jsonl ${WT}/tests/oracle/cassettes/.
3. DANGLING IMPORTS: two retired scripts import a moved module via a nonexistent leading-underscore package path: scripts/_retired_2026_06_14/pg_geval_openai.py:29 and scripts/_retired_2026_06_14/pg_compose_production_scale.py:45, both 'from archive._2026_06_14_retired_scripts.pg_compose_openai_validation import OpenAIShimClient'. The real file lives at archive/2026_06_14_retired_scripts/ (no leading underscore, no __init__.py). FIX by rewriting both import lines to the real resolvable path 'archive.2026_06_14_retired_scripts.pg_compose_openai_validation' AND ensure it's importable: add archive/__init__.py + archive/2026_06_14_retired_scripts/__init__.py if missing (empty files). Verify: python -c "import archive.2026_06_14_retired_scripts.pg_compose_openai_validation" resolves (or the module compiles). If adding __init__.py risks unintended package-discovery side effects, INSTEAD just delete the two dead retired scripts (they are already-dead, zero external importers) — pick whichever is cleaner + document.
4. lethal_retrieve: it's a LIVE function at src/polaris_graph/wiki/mesh/retrieve/lethal.py:95, imported by tests/integration/test_mesh_e2e.py + tests/unit/test_mesh_lethal_retrieve.py + scripts/_retired.../pg_mesh_preflight.py. Rename the function to high_recall_retrieve (IF that's mechanically accurate — inspect it first; if not accurate pick a precise descriptive name), and add a backward-compat alias 'lethal_retrieve = high_recall_retrieve' in the same module (same object) so the active test imports still resolve WITHOUT editing the tests. Do NOT rename the test file. If the function's behavior is NOT high-recall (verify), choose an accurate name; if genuinely un-renameable, skip+document.
py_compile; collection stays at baseline (report the number).
Return: danglings_fixed (int), dangling_method (fix-import|delete-scripts), lethal_renamed (bool), lethal_new_name, collection_after.`,
  { label: 'fix', phase: 'Fix', schema: { type:'object', additionalProperties:false, required:['danglings_fixed','dangling_method','lethal_renamed','lethal_new_name','collection_after'], properties:{ danglings_fixed:{type:'integer'}, dangling_method:{type:'string'}, lethal_renamed:{type:'boolean'}, lethal_new_name:{type:'string'}, collection_after:{type:'string'} } } })

phase('Verify')
const verify = await agent(
  `Verify ${WT}. 1. Collection (report vs the FILE-RENAME baseline). 2. Oracle 'cd ${WT} && PG_OUTLINE_AGENT_MAX_TURNS=3 ${PY} tests/oracle/acceptance_portable.py --replay 2>&1 | tail -5' SHA==${GOLDEN}. 3. NO dangling refs remain: grep -rn 'archive._2026_06_14_retired_scripts' repo = 0. 4. lethal: if renamed, old name 'lethal_retrieve' still importable (alias, same object) — python -c import check; the two active test files still collect. Return collection_ok, oracle_matches, oracle_sha, no_danglings, lethal_old_ref_resolves.`,
  { label: 'verify', phase: 'Verify', schema: { type:'object', additionalProperties:false, required:['collection_ok','oracle_matches','oracle_sha','no_danglings','lethal_old_ref_resolves'], properties:{ collection_ok:{type:'boolean'}, oracle_matches:{type:'boolean'}, oracle_sha:{type:'string'}, no_danglings:{type:'boolean'}, lethal_old_ref_resolves:{type:'boolean'} } } })

phase('Codex-Gate')
const gate = await agent(
  `Run CODEX to gate the closeout. Write /tmp/closeout_gate.md then 'cd /tmp && timeout 180 codex exec --skip-git-repo-check - < /tmp/closeout_gate.md 2>&1 | tail -18' (embed inline; medium; no sandbox flags). Codex earlier flagged: 2 dangling retired-script imports + lethal_retrieve unrenamed. Fix: ${JSON.stringify(fix)}. Verify: ${JSON.stringify(verify)} (oracle ${GOLDEN}). Ask: "Are the 2 dangling imports resolved and lethal_retrieve renamed-with-compat-alias (old imports still resolve, same object) — byte-safe, oracle unchanged, no dangling refs? End CLOSEOUT-SAFE or CLOSEOUT-REVISE." Return verdict + points.`,
  { label: 'codex-gate', phase: 'Codex-Gate', schema: { type:'object', additionalProperties:false, required:['verdict','codex_points'], properties:{ verdict:{type:'string'}, codex_points:{type:'array',items:{type:'string'}} } } })

phase('Record')
const rec = await agent(
  `Record in ${WT} (branch chore/review-readiness-closeout). Commit if verify passed (collection_ok, oracle_matches, no_danglings) and codex=CLOSEOUT-SAFE (${gate.verdict}). Stage explicit 'git add src/ scripts/ archive/ tests/' + docs/review_readiness/codex_closeout.md; GUARD grep -c tests/oracle==0 (else git restore --staged tests/oracle/). Commit ("Closeout per codex: repair 2 dangling retired-script imports + lethal_retrieve->${fix.lethal_new_name} with compat alias (byte-safe, oracle byte-identical)") std trailers. Push -u origin; PR base gate-inversion. Return {commit_sha, pushed, pr_url, committed_or_blocked}.`,
  { label: 'record', phase: 'Record', schema: { type:'object', additionalProperties:false, required:['commit_sha','pushed','pr_url','committed_or_blocked'], properties:{ commit_sha:{type:'string'}, pushed:{type:'boolean'}, pr_url:{type:'string'}, committed_or_blocked:{type:'string'} } } })

return { fix, verify, gate, record: rec }
