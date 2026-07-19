export const meta = {
  name: 'codex-q2q3-config-rename',
  description: 'Execute codex Q2 (PG_GENERATOR_MODEL default → empty-string sentinel, byte-safe) + Q3 (lethal_retrieve → high_recall_retrieve if accurate+unreferenced)',
  phases: [
    { title: 'Execute', detail: 'collapse PG_GENERATOR_MODEL to "" everywhere + rename lethal_retrieve' },
    { title: 'Verify', detail: 'collection + oracle byte-identical + rename reference-complete' },
    { title: 'Codex-Gate', detail: 'codex confirms byte-safe' },
    { title: 'Record', detail: 'commit + push + PR' },
  ],
}
const PY = '/home/polaris/pipeline-env/bin/python'
const GOLDEN = '9c0a3d438da943242c98e2fe714494c342d42d02102202d75a61a4554339db98'
const WT = '/home/polaris/wt/phase-q2q3'

phase('Execute')
const exec = await agent(
  `Execute two codex-decided changes in a fresh worktree.
1. cd /workspace/POLARIS && git worktree remove ${WT} --force 2>/dev/null; git branch -D chore/review-readiness-q2q3 2>/dev/null; git worktree add ${WT} -b chore/review-readiness-q2q3 chore/review-readiness-phase1.
2. Force-copy phase0 oracle harness (unstaged): cp /home/polaris/wt/phase0/tests/oracle/*.py ${WT}/tests/oracle/ ; cp /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_golden.json /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_llm.jsonl /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_retrieval.jsonl ${WT}/tests/oracle/cassettes/.
3. Q2 — PG_GENERATOR_MODEL: it is read with conflicting fallbacks ('' vs a deepseek default) at different call sites and IS set in .env (=z-ai/glm-5.2, so env wins → byte-identical at runtime). Codex decision: standardize the code fallback to '' (empty-string sentinel) at ALL call sites + the config_defaults.py registry entry. grep for every os.getenv('PG_GENERATOR_MODEL'... and resolve('PG_GENERATOR_MODEL') site, set the default to '' uniformly. (Runtime unchanged because env supplies the value.)
4. Q3 — lethal_retrieve: codex decision rename lethal_retrieve → high_recall_retrieve ONLY IF (a) that name is mechanically accurate to what the function does, and (b) it is not referenced as a CLI entry point / fixture path / import / persisted label elsewhere. FIRST grep the whole repo for 'lethal_retrieve' — it is at scripts/_retired_2026_06_14/pg_mesh_preflight.py:28 (a RETIRED script). Inspect the function: if it's a high-recall retrieval helper, rename it + fix any importers. If the name is NOT mechanically accurate, or it's referenced dynamically, SKIP + document. (It's in a retired dir, so low risk.)
After each: py_compile + collection == 16738/11.
Return: q2_sites_changed, q3_renamed (bool), q3_skip_reason (if skipped), collection_after.`,
  { label: 'execute', phase: 'Execute', schema: { type:'object', additionalProperties:false, required:['q2_sites_changed','q3_renamed','q3_skip_reason','collection_after'], properties:{ q2_sites_changed:{type:'integer'}, q3_renamed:{type:'boolean'}, q3_skip_reason:{type:'string'}, collection_after:{type:'string'} } } })

phase('Verify')
const verify = await agent(
  `Verify the Q2/Q3 changes in ${WT}. 1. Collection == 16738/11: '${PY} -m pytest tests/ --collect-only -q | tail -1'. 2. Oracle: 'cd ${WT} && PG_OUTLINE_AGENT_MAX_TURNS=3 ${PY} tests/oracle/acceptance_portable.py --replay 2>&1 | tail -6' SHA==${GOLDEN}. 3. Config characterization: '${PY} -m pytest tests/test_config_registry.py tests/test_settings_models.py -q | tail -1'. 4. If lethal_retrieve renamed: grep 'lethal_retrieve' repo-wide = 0 stale refs. Return collection_ok, oracle_matches, oracle_sha, characterization_ok, no_stale_refs.`,
  { label: 'verify', phase: 'Verify', schema: { type:'object', additionalProperties:false, required:['collection_ok','oracle_matches','oracle_sha','characterization_ok','no_stale_refs'], properties:{ collection_ok:{type:'boolean'}, oracle_matches:{type:'boolean'}, oracle_sha:{type:'string'}, characterization_ok:{type:'boolean'}, no_stale_refs:{type:'boolean'} } } })

phase('Codex-Gate')
const gate = await agent(
  `Run CODEX (GPT-5.6) to gate the Q2/Q3 changes. Write /tmp/q2q3_gate.md then 'cd /tmp && timeout 200 codex exec --skip-git-repo-check - < /tmp/q2q3_gate.md 2>&1 | tail -20' (embed inline; medium; no sandbox flags).
Context: Q2 = PG_GENERATOR_MODEL code fallback standardized to '' at all sites (env sets it to glm-5.2 so runtime byte-identical); Q3 = lethal_retrieve rename per prior codex decision. Result: ${JSON.stringify(exec)}. Verify: ${JSON.stringify(verify)} (oracle byte-identical ${GOLDEN}).
Ask codex: "Is the PG_GENERATOR_MODEL '' standardization byte-safe (env-dominated), and is the lethal_retrieve rename reference-complete (or correctly skipped)? End with Q2Q3-SAFE or Q2Q3-REVISE."
Return verdict + points.`,
  { label: 'codex-gate', phase: 'Codex-Gate', schema: { type:'object', additionalProperties:false, required:['verdict','codex_points'], properties:{ verdict:{type:'string'}, codex_points:{type:'array',items:{type:'string'}} } } })

phase('Record')
const rec = await agent(
  `Record in ${WT} (branch chore/review-readiness-q2q3). Commit if verify passed (collection_ok, oracle_matches) and codex=Q2Q3-SAFE (${gate.verdict}). Stage explicit 'git add src/ scripts/' + a short docs/review_readiness/codex_q2_q3.md; GUARD 'git diff --cached --name-only | grep -c tests/oracle' == 0 (else git restore --staged tests/oracle/). Commit ("Config/rename per codex: PG_GENERATOR_MODEL default -> '' (byte-safe, env-authoritative); lethal_retrieve -> high_recall_retrieve") std trailers. Push -u origin; PR base gate-inversion.
Return {commit_sha, pushed, pr_url, committed_or_blocked}.`,
  { label: 'record', phase: 'Record', schema: { type:'object', additionalProperties:false, required:['commit_sha','pushed','pr_url','committed_or_blocked'], properties:{ commit_sha:{type:'string'}, pushed:{type:'boolean'}, pr_url:{type:'string'}, committed_or_blocked:{type:'string'} } } })

return { exec, verify, gate, record: rec }
