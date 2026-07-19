export const meta = {
  name: 'phase1b-revise',
  description: 'Close 1B-REVISE: add .env-precedence + ModelSettings-empty + resolve-key-case axes to the characterization matrix, re-gate, commit',
  phases: [
    { title: 'AddAxes', detail: 'add the 3 missing-axis tests to the existing matrix file' },
    { title: 'Codex-Gate', detail: 'codex confirms 1B-OK' },
    { title: 'Record', detail: 'commit + push + PR' },
  ],
}
const PY = '/home/polaris/pipeline-env/bin/python'
const GOLDEN = '9c0a3d438da943242c98e2fe714494c342d42d02102202d75a61a4554339db98'
const WT = '/home/polaris/wt/phase-1b'

phase('AddAxes')
const add = await agent(
  `Extend the existing characterization matrix at ${WT}/tests/test_config_characterization_matrix.py (branch chore/review-readiness-1b, has 118 passing tests) with the 3 axes codex flagged:
1. .env PRECEDENCE TIER: prove the layering .env-beats-registry-default AND process-env-beats-.env. The config uses load_dotenv(override=False). Write hermetic tests (monkeypatch + a temp .env file, or monkeypatch the dotenv-loaded values) asserting: (a) a key ONLY in .env (not process env) resolves to the .env value over the registry default; (b) a key in BOTH process-env and .env resolves to the PROCESS-ENV value (because override=False means real env wins). Characterize whatever the code ACTUALLY does — if the config layer reads only os.getenv (so .env must already be loaded into os.environ at import), assert that reality precisely and document it.
2. ModelSettings EMPTY-VALUE: for a model key, set the env var to '' and assert exactly what get_model_settings().field returns (empty string stays '', or becomes None, or is ignored — assert the ACTUAL behaviour). Also assert a malformed-looking string value is preserved verbatim (or mark malformed N/A for unconstrained str with a comment).
3. resolve()-LAYER KEY-CASE: assert the registry/resolve path is case-sensitive — set a LOWERCASE form of a registered key in env and assert resolve(CORRECT_CASE) still returns the registry default (the lowercase env var does NOT override), and resolve(lowercase) raises KeyError (not registered).
Run '${PY} -m pytest tests/test_config_characterization_matrix.py -q | tail -2' — all must pass (characterization of current behaviour). Report new test count + total + all_pass. Do NOT change src/.`,
  { label: 'add-axes', phase: 'AddAxes', schema: { type:'object', additionalProperties:false, required:['new_tests','total_tests','all_pass','notes'], properties:{ new_tests:{type:'integer'}, total_tests:{type:'integer'}, all_pass:{type:'boolean'}, notes:{type:'string'} } } })

phase('Codex-Gate')
const gate = await agent(
  `Run CODEX (GPT-5.6) to re-gate 1B after adding the 3 axes. Write /tmp/onebe_regate.md then 'cd /tmp && timeout 200 codex exec --skip-git-repo-check - < /tmp/onebe_regate.md 2>&1 | tail -20' (embed inline; medium; no sandbox flags).
Prior 1B-REVISE demanded 3 axes: (1) .env precedence tier (.env-beats-registry + process-env-beats-.env), (2) ModelSettings empty/pass-through value-state, (3) resolve-layer key-case sensitivity. Now added: ${JSON.stringify(add)}. The suite is characterization (locks current behaviour); prior 118 tests already accepted as genuine; oracle replay is byte-identical with the correct harness (the test file is inert).
Ask codex: "Are the 3 previously-missing axes now covered as genuine characterization? End with 1B-OK or 1B-REVISE (+ any still-missing axis)."
Return verdict + points.`,
  { label: 'codex-gate', phase: 'Codex-Gate', schema: { type:'object', additionalProperties:false, required:['verdict','codex_points'], properties:{ verdict:{type:'string'}, codex_points:{type:'array',items:{type:'string'}} } } })

phase('Record')
const rec = await agent(
  `Record 1B in ${WT} (branch chore/review-readiness-1b). Commit if codex=1B-OK (${gate.verdict}) and tests pass (${add.all_pass}). Also re-confirm oracle byte-identical with the CORRECT harness first: cp /home/polaris/wt/phase0/tests/oracle/*.py ${WT}/tests/oracle/ ; cp /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_golden.json /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_llm.jsonl /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_retrieval.jsonl ${WT}/tests/oracle/cassettes/ ; cd ${WT} && PG_OUTLINE_AGENT_MAX_TURNS=3 ${PY} tests/oracle/acceptance_portable.py --replay 2>&1 | tail -3 (SHA must == ${GOLDEN}).
Stage EXPLICIT: 'git add tests/test_config_characterization_matrix.py' + write+add docs/review_readiness/phase1b_characterization.md (matrix axes covered, total test count, codex 1B-OK, oracle byte-identical). GUARD 'git diff --cached --name-only | grep -c tests/oracle' == 0 (else git restore --staged tests/oracle/). Commit ("Phase 1B: full-behaviour config characterization matrix — value-state x precedence(.env/process) x case x timing x type") with standard trailers. Push -u origin; PR base gate-inversion.
Return {commit_sha, pushed, pr_url, oracle_sha, committed_or_blocked}.`,
  { label: 'record', phase: 'Record', schema: { type:'object', additionalProperties:false, required:['commit_sha','pushed','pr_url','oracle_sha','committed_or_blocked'], properties:{ commit_sha:{type:'string'}, pushed:{type:'boolean'}, pr_url:{type:'string'}, oracle_sha:{type:'string'}, committed_or_blocked:{type:'string'} } } })

return { add, gate, record: rec }
