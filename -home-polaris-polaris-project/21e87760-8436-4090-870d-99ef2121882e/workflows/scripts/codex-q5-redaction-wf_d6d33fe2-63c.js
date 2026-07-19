export const meta = {
  name: 'codex-q5-redaction',
  description: 'Execute codex Q5: centralized secret redaction at config-serialization/logging/exception/diagnostic boundaries + canary-secret tests (skip SecretStr)',
  phases: [
    { title: 'Harden', detail: 'centralized redaction helper + wire at secret-leak boundaries' },
    { title: 'Verify', detail: 'canary-secret tests + collection + oracle byte-identical' },
    { title: 'Codex-Gate', detail: 'codex Q5-OK' },
    { title: 'Record', detail: 'commit + push + PR' },
  ],
}
const PY = '/home/polaris/pipeline-env/bin/python'
const GOLDEN = '9c0a3d438da943242c98e2fe714494c342d42d02102202d75a61a4554339db98'
const WT = '/home/polaris/wt/phase-q5'

phase('Harden')
const harden = await agent(
  `Execute codex's Q5 decision: SKIP the SecretStr conversion; instead add CENTRALIZED secret redaction at the boundaries where a secret value could leak, + canary-secret tests. Minimal + behavior-neutral (must keep the oracle byte-identical — the redaction only affects log/serialization OUTPUT, not pipeline data/results).
1. cd /workspace/POLARIS && git worktree remove ${WT} --force 2>/dev/null; git branch -D chore/review-readiness-q5 2>/dev/null; git worktree add ${WT} -b chore/review-readiness-q5 chore/review-readiness-phase1.
2. Force-copy phase0 harness (unstaged): cp /home/polaris/wt/phase0/tests/oracle/*.py ${WT}/tests/oracle/ ; cp /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_golden.json /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_llm.jsonl /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_retrieval.jsonl ${WT}/tests/oracle/cassettes/.
3. INVESTIGATE current secret handling: is there an existing redaction/scrubber util? (grep redact/mask/scrub/sanitize). Where might a secret VALUE leak: config serialization / a settings dump / __repr__ of a config object / exception messages that interpolate os.environ / a diagnostic 'dump env' path / structured logging of headers. The S4 threat model already found keys are NOT logged as values today — so this is DEFENSE-IN-DEPTH, not fixing an active leak.
4. ADD a single centralized redaction helper (e.g. src/polaris_graph/util/secret_redaction.py: redact(text_or_mapping) that masks any value whose KEY matches KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL, or any known-secret substring, to '***REDACTED***'; and a safe_repr for config objects). WIRE it ONLY at the genuine leak boundaries you found (config serialize/dump, exception context that includes env, any 'log the settings' path) — do NOT touch hot-path pipeline code, do NOT change any data value that flows into results (that would break the oracle). If no leak boundary exists, still add the helper + a test proving the config-dump path is redacted (defense-in-depth), and document that current logging is already clean.
py_compile; collection == 16738/11.
Return: helper_added (bool), boundaries_wired (list), existing_redaction (str), collection_after, no_hotpath_change (bool).`,
  { label: 'harden', phase: 'Harden', schema: { type:'object', additionalProperties:false, required:['helper_added','boundaries_wired','existing_redaction','collection_after','no_hotpath_change'], properties:{ helper_added:{type:'boolean'}, boundaries_wired:{type:'array',items:{type:'string'}}, existing_redaction:{type:'string'}, collection_after:{type:'string'}, no_hotpath_change:{type:'boolean'} } } })

phase('Verify')
const verify = await agent(
  `Verify Q5 in ${WT}. 1. Write + run canary-secret tests (tests/test_secret_redaction.py): set a recognizable canary secret (e.g. OPENROUTER_API_KEY='sk-CANARY-LEAK-TEST-123'), exercise the redaction helper + each wired boundary (config dump/serialize/repr/exception), assert the canary NEVER appears in the output and '***REDACTED***' does. Run '${PY} -m pytest tests/test_secret_redaction.py -q | tail -2' — all pass. 2. Collection == 16738/11. 3. Oracle 'cd ${WT} && PG_OUTLINE_AGENT_MAX_TURNS=3 ${PY} tests/oracle/acceptance_portable.py --replay 2>&1 | tail -5' SHA==${GOLDEN} (redaction must not change the pipeline artifact). Return canary_tests_pass, collection_ok, oracle_matches, oracle_sha.`,
  { label: 'verify', phase: 'Verify', schema: { type:'object', additionalProperties:false, required:['canary_tests_pass','collection_ok','oracle_matches','oracle_sha'], properties:{ canary_tests_pass:{type:'boolean'}, collection_ok:{type:'boolean'}, oracle_matches:{type:'boolean'}, oracle_sha:{type:'string'} } } })

phase('Codex-Gate')
const gate = await agent(
  `Run CODEX (GPT-5.6) to gate Q5. Write /tmp/q5_gate.md then 'cd /tmp && timeout 180 codex exec --skip-git-repo-check - < /tmp/q5_gate.md 2>&1 | tail -18' (embed inline; medium; no sandbox flags).
Codex's Q5 decision: skip SecretStr, add centralized redaction at serialization/logging/exception/diagnostic boundaries + canary tests, keep secrets out of repr/validation errors. Result: ${JSON.stringify(harden)}. Verify: ${JSON.stringify(verify)} (oracle byte-identical ${GOLDEN}, canary tests pass).
Ask codex: "Does this centralized redaction + canary tests implement the Q5 decision (no secret value can leak at the wired boundaries), with NO hot-path/data change (oracle byte-identical)? End with Q5-OK or Q5-REVISE."
Return verdict + points.`,
  { label: 'codex-gate', phase: 'Codex-Gate', schema: { type:'object', additionalProperties:false, required:['verdict','codex_points'], properties:{ verdict:{type:'string'}, codex_points:{type:'array',items:{type:'string'}} } } })

phase('Record')
const rec = await agent(
  `Record Q5 in ${WT} (branch chore/review-readiness-q5). Commit if verify passed (canary_tests_pass, collection_ok, oracle_matches) and codex=Q5-OK (${gate.verdict}). Stage explicit 'git add src/ tests/test_secret_redaction.py' + docs/review_readiness/codex_q5_redaction.md; GUARD 'git diff --cached --name-only | grep -c tests/oracle' == 0 (else git restore --staged tests/oracle/). Commit ("Security per codex Q5: centralized secret redaction at serialize/log/exception boundaries + canary tests (SecretStr skipped; oracle byte-identical)") std trailers. Push -u origin; PR base gate-inversion.
Return {commit_sha, pushed, pr_url, committed_or_blocked}.`,
  { label: 'record', phase: 'Record', schema: { type:'object', additionalProperties:false, required:['commit_sha','pushed','pr_url','committed_or_blocked'], properties:{ commit_sha:{type:'string'}, pushed:{type:'boolean'}, pr_url:{type:'string'}, committed_or_blocked:{type:'string'} } } })

return { harden, verify, gate, record: rec }
