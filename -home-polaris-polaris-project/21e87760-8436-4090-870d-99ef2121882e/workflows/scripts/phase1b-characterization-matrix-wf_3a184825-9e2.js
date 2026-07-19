export const meta = {
  name: 'phase1b-characterization-matrix',
  description: '1B full-behaviour characterization tests: exercise the config resolution matrix {unset/empty/valid/malformed}x{default/.env/process/CLI precedence}x{case}x{timing}x{type incl SecretStr} for representative keys per type',
  phases: [
    { title: 'Design', detail: 'classify config keys by type + pick representatives per axis' },
    { title: 'Write', detail: 'parametrized characterization tests over the full matrix' },
    { title: 'Verify', detail: 'tests pass + collection up by exactly the new tests + oracle unchanged' },
    { title: 'Codex-Gate', detail: 'codex checks the matrix genuinely covers the 1B axes' },
    { title: 'Record', detail: 'commit + push + PR' },
  ],
}
const PY = '/home/polaris/pipeline-env/bin/python'
const GOLDEN = '9c0a3d438da943242c98e2fe714494c342d42d02102202d75a61a4554339db98'
const WT = '/home/polaris/wt/phase-1b'

phase('Design')
const design = await agent(
  `Set up Plan V4 1B (full-behaviour config characterization tests).
1. cd /workspace/POLARIS && git worktree remove ${WT} --force 2>/dev/null; git branch -D chore/review-readiness-1b 2>/dev/null; git worktree add ${WT} -b chore/review-readiness-1b chore/review-readiness-phase1.
2. Overlay oracle by COPY: cp -n /home/polaris/wt/phase0/tests/oracle/*.py ${WT}/tests/oracle/ 2>/dev/null; cp -n /home/polaris/wt/phase0/tests/oracle/cassettes/* ${WT}/tests/oracle/cassettes/ 2>/dev/null.
3. Study the config layer: ${WT}/src/polaris_graph/settings.py (resolve(), get_model_settings(), CONFIG_DEFAULTS, ModelSettings). Understand how a key resolves: os.getenv(key, default) via resolve(); pydantic ModelSettings for the 12 model keys; are there any keys read with int()/float()/=='1' COERCION at call sites? any .env / process-env / CLI precedence layering? any SecretStr?
4. Classify representative keys by TYPE for the matrix: (a) plain-str key, (b) int-coerced key (read via int(resolve(...))), (c) float-coerced (threshold), (d) bool key (==\"1\"), (e) model key (ModelSettings field), (f) secret-shaped key (KEY/TOKEN/SECRET), (g) a key with an empty-string default, (h) a key unset in registry. Pick 1-3 real keys per type from config_defaults.py.
5. Determine which axes actually APPLY to this codebase: {unset, empty, valid, malformed} value states; {registry-default vs process-env override} precedence (is there also a .env-load and CLI layer? document whether they exist); key-case sensitivity (settings.py uses case_sensitive=True); read-timing (resolve reads live env each call vs a snapshot); runtime-type (str vs coerced-at-callsite vs SecretStr).
Return the per-type representative keys + which axes apply + the baseline collection (16738/11).`,
  { label: 'design', phase: 'Design', schema: { type:'object', additionalProperties:false, required:['type_reps','axes_applicable','coercion_sites_exist','secretstr_exists','baseline'], properties:{ type_reps:{type:'array',items:{type:'object',additionalProperties:true}}, axes_applicable:{type:'array',items:{type:'string'}}, coercion_sites_exist:{type:'boolean'}, secretstr_exists:{type:'boolean'}, baseline:{type:'string'} } } })

phase('Write')
const write = await agent(
  `Write the 1B characterization tests in ${WT} as ${WT}/tests/test_config_characterization_matrix.py. Representatives + axes: ${JSON.stringify(design.type_reps)} / ${JSON.stringify(design.axes_applicable)}.
The tests must LOCK today's behaviour (characterization — assert what the code CURRENTLY does, not what it should) across the applicable matrix:
- For each representative key x {unset, empty, valid, malformed} x {registry-default, process-env override via monkeypatch.setenv}: assert resolve(key) (and get_model_settings().field for model keys) returns EXACTLY os.getenv(key, CONFIG_DEFAULTS[key]) — including the empty-string and malformed cases (document what malformed does: e.g. a non-int value for an int-coerced key raises ValueError at the CALL SITE, not in resolve()).
- Key-case: assert resolve is case-sensitive (settings.py case_sensitive=True) — a differently-cased env var does NOT override.
- Read-timing: assert resolve reads LIVE env (set env after import, resolve sees it) — the freshness contract.
- Coercion: for int/float/bool keys, characterize the call-site coercion (int(resolve(k)), float(...), ==\"1\") for valid + malformed inputs.
- SecretStr: if any exists, characterize it; if not, add a test asserting secrets are currently plain str (documents the pre-SecretStr state for the future SecretStr pass).
Keep tests hermetic (monkeypatch env, no network). Run them: '${PY} -m pytest tests/test_config_characterization_matrix.py -q | tail -3' — all must PASS (they characterize current behaviour). Report test count + pass.`,
  { label: 'write', phase: 'Write', schema: { type:'object', additionalProperties:false, required:['tests_added','all_pass','matrix_cells_covered','notes'], properties:{ tests_added:{type:'integer'}, all_pass:{type:'boolean'}, matrix_cells_covered:{type:'integer'}, notes:{type:'string'} } } })

phase('Verify')
const verify = await agent(
  `Verify 1B tests in ${WT}. 1. New tests pass: '${PY} -m pytest tests/test_config_characterization_matrix.py -q | tail -2'. 2. Full collection = baseline count + the new tests, errors still 11: '${PY} -m pytest tests/ --collect-only -q | tail -1' (should be 16738 + tests_added, 11 errors). 3. Oracle replay unchanged (the new test file is inert to runtime): 'cd ${WT} && PG_OUTLINE_AGENT_MAX_TURNS=3 ${PY} tests/oracle/acceptance_portable.py --replay 2>&1 | tail -8' — SHA==${GOLDEN}. Return new_tests_pass, collection_delta_ok, oracle_matches, oracle_sha.`,
  { label: 'verify', phase: 'Verify', schema: { type:'object', additionalProperties:false, required:['new_tests_pass','collection_delta_ok','oracle_matches','oracle_sha'], properties:{ new_tests_pass:{type:'boolean'}, collection_delta_ok:{type:'boolean'}, oracle_matches:{type:'boolean'}, oracle_sha:{type:'string'} } } })

phase('Codex-Gate')
const gate = await agent(
  `Run CODEX (GPT-5.6) to gate the 1B characterization matrix. Write /tmp/onebe_gate.md then 'cd /tmp && timeout 200 codex exec --skip-git-repo-check - < /tmp/onebe_gate.md 2>&1 | tail -25' (embed inline; medium; no sandbox flags).
Plan V4 1B: lock today's config behaviour across {unset,empty,valid,malformed}x{default/.env/process-env/CLI precedence}x{key-case}x{read-timing lazy vs snapshot}x{runtime type str/coerced/SecretStr} — the real 'byte-identical' proof. Evidence: design=${JSON.stringify(design)}, write=${JSON.stringify(write)}, verify=${JSON.stringify(verify)}.
Ask codex: "Do these characterization tests genuinely cover the 1B axes that APPLY to this codebase (value-state, precedence, case, timing, coercion/type, SecretStr-or-its-absence), for a representative key per type? Are they true characterization (asserting current behaviour) rather than aspirational? Any axis that applies but is untested? End with 1B-OK or 1B-REVISE (+ the missing axis)."
Return verdict + points.`,
  { label: 'codex-gate', phase: 'Codex-Gate', schema: { type:'object', additionalProperties:false, required:['verdict','codex_points'], properties:{ verdict:{type:'string'}, codex_points:{type:'array',items:{type:'string'}} } } })

phase('Record')
const rec = await agent(
  `Record 1B in ${WT} (branch chore/review-readiness-1b). Commit only if verify passed (new_tests_pass, collection_delta_ok, oracle_matches) and codex=1B-OK (${gate.verdict}); if REVISE on a missing axis, add that axis's tests then commit.
Stage explicit: 'git add tests/test_config_characterization_matrix.py' + a short docs/review_readiness/phase1b_characterization.md (matrix covered, axes, codex verdict). Guard 0 tests/oracle staged. Commit ("Phase 1B: full-behaviour config characterization matrix (value-state x precedence x case x timing x type)") with standard trailers. Push -u origin; PR base gate-inversion.
Return {commit_sha, pushed, pr_url, committed_or_blocked}.`,
  { label: 'record', phase: 'Record', schema: { type:'object', additionalProperties:false, required:['commit_sha','pushed','pr_url','committed_or_blocked'], properties:{ commit_sha:{type:'string'}, pushed:{type:'boolean'}, pr_url:{type:'string'}, committed_or_blocked:{type:'string'} } } })

return { design, write, verify, gate, record: rec }
