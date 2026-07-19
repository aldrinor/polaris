export const meta = {
  name: 'codex-q6-accessors',
  description: 'Execute codex Q6 accessors: typed accessors ONLY for computed-default config keys with real duplication/inconsistency across sites (not blanket 46); byte-identical, oracle+collection gated',
  phases: [
    { title: 'Find', detail: 'identify computed-default keys read+computed identically at 2+ sites' },
    { title: 'Extract', detail: 'add typed accessor for those; replace duplicated sites (byte-identical)' },
    { title: 'Verify', detail: 'collection + oracle + characterization' },
    { title: 'Codex-Gate', detail: 'codex ACCESSORS-OK' },
    { title: 'Record', detail: 'commit + push + PR (or record none-worth-doing)' },
  ],
}
const PY = '/home/polaris/pipeline-env/bin/python'
const GOLDEN = '9c0a3d438da943242c98e2fe714494c342d42d02102202d75a61a4554339db98'
const WT = '/home/polaris/wt/phase-acc'

phase('Find')
const find = await agent(
  `Execute codex's Q6 accessor decision: add typed accessors ONLY for computed-default config keys that show REAL duplication or inconsistency (NOT a blanket 46-key migration). First FIND the pain points.
1. cd /workspace/POLARIS && git worktree remove ${WT} --force 2>/dev/null; git branch -D chore/review-readiness-acc 2>/dev/null; git worktree add ${WT} -b chore/review-readiness-acc chore/review-readiness-phase1.
2. Force-copy phase0 harness (unstaged): cp /home/polaris/wt/phase0/tests/oracle/*.py ${WT}/tests/oracle/ ; cp /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_golden.json /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_llm.jsonl /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_retrieval.jsonl ${WT}/tests/oracle/cassettes/.
3. The ~46 computed/multiline-default config keys (docs/review_readiness/config_governance.md tail) are read with computed defaults. Find which are read + coerced with the SAME computed-default logic at 2+ DIFFERENT call sites (real duplication) — e.g. int(os.getenv('PG_X', str(SOME_CONST))) repeated, or a key read with an identical multi-step default in multiple modules. Those are the pain points worth a typed accessor. Keys read at only ONE site are NOT worth an accessor (codex: only proven duplication).
4. Baseline: '${PY} -m pytest tests/ --collect-only -q | tail -1'.
Return: duplicated_keys (list of {key, sites, computed_default}), single_site_keys_count, baseline. If ZERO keys have real cross-site duplication, say so (worth_doing=false).`,
  { label: 'find', phase: 'Find', schema: { type:'object', additionalProperties:false, required:['duplicated_keys','worth_doing','baseline'], properties:{ duplicated_keys:{type:'array',items:{type:'object',additionalProperties:true}}, worth_doing:{type:'boolean'}, baseline:{type:'string'} } } })

phase('Extract')
let extract = { accessors_added: 0, sites_updated: 0, collection_after: find.baseline, note: 'skipped — no duplication worth an accessor' }
if (find.worth_doing && find.duplicated_keys.length) {
  extract = await agent(
    `In ${WT}, add a typed accessor for EACH duplicated computed-default key, and replace the duplicated call sites with it — BYTE-IDENTICAL (the accessor must return exactly what the current computed default produces, same coercion, same env precedence os.getenv > default). Keys: ${JSON.stringify(find.duplicated_keys)}. Put accessors in src/polaris_graph/settings.py (or a config accessors module). After each, collection == ${find.baseline}; py_compile. Return accessors_added, sites_updated, collection_after, note.`,
    { label: 'extract', phase: 'Extract', schema: { type:'object', additionalProperties:false, required:['accessors_added','sites_updated','collection_after','note'], properties:{ accessors_added:{type:'integer'}, sites_updated:{type:'integer'}, collection_after:{type:'string'}, note:{type:'string'} } } })
} else { log('Q6 accessors: no computed-default keys have real cross-site duplication — nothing to do (codex: only proven pain points).') }

phase('Verify')
const verify = await agent(
  `Verify ${WT}. 1. Collection == ${find.baseline}. 2. Oracle 'cd ${WT} && PG_OUTLINE_AGENT_MAX_TURNS=3 ${PY} tests/oracle/acceptance_portable.py --replay 2>&1 | tail -5' SHA==${GOLDEN}. 3. Config characterization '${PY} -m pytest tests/test_config_registry.py tests/test_settings_models.py -q | tail -1'. If nothing was changed (accessors_added=${extract.accessors_added}), these are trivially green. Return collection_ok, oracle_matches, oracle_sha, characterization_ok, anything_changed.`,
  { label: 'verify', phase: 'Verify', schema: { type:'object', additionalProperties:false, required:['collection_ok','oracle_matches','oracle_sha','characterization_ok','anything_changed'], properties:{ collection_ok:{type:'boolean'}, oracle_matches:{type:'boolean'}, oracle_sha:{type:'string'}, characterization_ok:{type:'boolean'}, anything_changed:{type:'boolean'} } } })

phase('Codex-Gate')
const gate = await agent(
  `Run CODEX to gate Q6 accessors. Write /tmp/q6a_gate.md then 'cd /tmp && timeout 180 codex exec --skip-git-repo-check - < /tmp/q6a_gate.md 2>&1 | tail -16' (embed inline; medium; no sandbox flags). Codex Q6 decision: typed accessors ONLY for proven duplication, byte-identical. Find: ${JSON.stringify(find)}. Extract: ${JSON.stringify(extract)}. Verify: ${JSON.stringify(verify)} (oracle ${GOLDEN}). Ask: "Were accessors added only for genuinely-duplicated computed-defaults (byte-identical, oracle unchanged), OR correctly concluded none warrant one? End ACCESSORS-OK or ACCESSORS-REVISE." Return verdict + points.`,
  { label: 'codex-gate', phase: 'Codex-Gate', schema: { type:'object', additionalProperties:false, required:['verdict','codex_points'], properties:{ verdict:{type:'string'}, codex_points:{type:'array',items:{type:'string'}} } } })

phase('Record')
const rec = await agent(
  `Record in ${WT} (branch chore/review-readiness-acc). Write docs/review_readiness/codex_q6_accessors.md summarizing what was found + done (or that no key warranted an accessor per codex). If anything_changed (${verify.anything_changed}) commit only if verify passed + codex ACCESSORS-OK (${gate.verdict}): stage 'git add src/' + the doc, GUARD grep -c tests/oracle==0. If nothing changed, commit just the doc (the finding/decision record). Commit ("Config per codex Q6: typed accessors for duplicated computed-defaults [or: none warranted]") std trailers. Push -u origin; PR base gate-inversion. Return {commit_sha, pushed, pr_url, committed_or_blocked}.`,
  { label: 'record', phase: 'Record', schema: { type:'object', additionalProperties:false, required:['commit_sha','pushed','pr_url','committed_or_blocked'], properties:{ commit_sha:{type:'string'}, pushed:{type:'boolean'}, pr_url:{type:'string'}, committed_or_blocked:{type:'string'} } } })

return { find: { worth_doing: find.worth_doing, n: find.duplicated_keys.length }, extract, verify, gate, record: rec }
