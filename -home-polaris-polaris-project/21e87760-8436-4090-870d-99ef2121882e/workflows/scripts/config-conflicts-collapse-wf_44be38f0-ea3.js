export const meta = {
  name: 'config-conflicts-collapse',
  description: 'Collapse the 20 conflicting-default config keys to each key\'s authoritative runtime value, byte-safe, never weakening faithfulness; oracle+codex gated',
  phases: [
    { title: 'Investigate', detail: 'for each of 20 keys find the authoritative value (.env override / primary path / git history)' },
    { title: 'Collapse', detail: 'align all call sites + registry to the authoritative value (skip genuinely behavior-changing)' },
    { title: 'Verify', detail: 'oracle SHA + collection + characterization unchanged' },
    { title: 'Codex-Gate', detail: 'codex confirms each collapse byte-safe + faithfulness never weakened' },
    { title: 'Record', detail: 'commit + push + PR; flag the un-collapsible for the owner' },
  ],
}
const PY = '/home/polaris/pipeline-env/bin/python'
const GOLDEN = '9c0a3d438da943242c98e2fe714494c342d42d02102202d75a61a4554339db98'
const WT = '/home/polaris/wt/phase-cfg'

phase('Investigate')
const inv = await agent(
  `Set up + investigate the 20 conflicting-default config keys (documented in docs/review_readiness/config_conflicts.md on the phase1 branch). These are PG_ env vars read with DIFFERENT hardcoded fallback defaults at different call sites (a latent bug).
1. cd /workspace/POLARIS && git worktree remove ${WT} --force 2>/dev/null; git branch -D chore/review-readiness-config 2>/dev/null; git worktree add ${WT} -b chore/review-readiness-config chore/review-readiness-phase1.
2. Overlay oracle by COPY: cp -n /home/polaris/wt/phase0/tests/oracle/*.py ${WT}/tests/oracle/ 2>/dev/null; cp -n /home/polaris/wt/phase0/tests/oracle/cassettes/* ${WT}/tests/oracle/cassettes/ 2>/dev/null.
3. Read ${WT}/docs/review_readiness/config_conflicts.md for the 20 keys + their conflicting values (e.g. PG_FAITHFULNESS_NLI_THRESHOLD 0.65 vs 0.75, PG_MIN_EVIDENCE_PER_SECTION 3/5/8, PG_TARGET_TOTAL_WORDS 8000/12000, etc.).
4. For EACH key determine the AUTHORITATIVE runtime value, in priority order:
   (a) Is it set in the .env? Check /workspace/POLARIS/.env for the key. If SET, the env value WINS at runtime (os.getenv returns it regardless of default) => the authoritative value is the env value, and aligning all code defaults to it is BYTE-IDENTICAL. Record the env value.
   (b) If NOT in .env: which call site is on the PRIMARY/governing runtime path (the honest/main pipeline that actually runs, vs a dead/legacy/test path)? Inspect the call sites (grep the key). Record which value the primary path uses.
   (c) FAITHFULNESS RULE: for any faithfulness/verification/evidence-gate key (PG_FAITHFULNESS_NLI_THRESHOLD, PG_MIN_EVIDENCE_*, PG_MIN_EVIDENCE_UTILIZATION, PG_FAITHFULNESS_*, thresholds), NEVER pick a value that WEAKENS faithfulness (never lower a threshold / evidence floor) unless the env explicitly sets the lower value. If collapsing would weaken faithfulness on any path and env doesn't decide it, mark it UNSAFE-DEFER.
5. Classify each key: BYTE-SAFE (env-set, align to env), SAFE-PRIMARY (not in env, collapse to primary-path value, no weakening), or DEFER (genuine behavior change / would weaken faithfulness / ambiguous — leave for owner).
Return per-key: {key, values_seen, env_set, env_value, chosen_value, classification, reason}, plus the baseline collection (16738/11).`,
  { label: 'investigate', phase: 'Investigate', schema: { type:'object', additionalProperties:false, required:['keys','byte_safe_count','defer_count','baseline'], properties:{ keys:{type:'array',items:{type:'object',additionalProperties:true}}, byte_safe_count:{type:'integer'}, defer_count:{type:'integer'}, baseline:{type:'string'} } } })

phase('Collapse')
const collapse = await agent(
  `In ${WT}, collapse the config conflicts classified BYTE-SAFE or SAFE-PRIMARY (NOT the DEFER ones). Per-key data: ${JSON.stringify(inv.keys)}.
For each non-DEFER key: change EVERY call site's fallback default (and the config_defaults.py registry entry) to the chosen authoritative value, so all sites agree. Do NOT change any DEFER key. Do NOT touch the env-var string name. After each ~5 keys run collection ('${PY} -m pytest tests/ --collect-only -q | tail -1') = baseline (${inv.baseline}); py_compile changed files.
For BYTE-SAFE (env-set) keys: the change is provably byte-identical (env wins at runtime; only the unused fallback changes). For SAFE-PRIMARY keys: the primary path's value is unchanged, only the divergent secondary path is aligned up to it.
Return: keys_collapsed, keys_deferred (list), files_changed, collection_after, and confirm no DEFER key was touched.`,
  { label: 'collapse', phase: 'Collapse', schema: { type:'object', additionalProperties:false, required:['keys_collapsed','keys_deferred','files_changed','collection_after'], properties:{ keys_collapsed:{type:'integer'}, keys_deferred:{type:'array',items:{type:'string'}}, files_changed:{type:'integer'}, collection_after:{type:'string'} } } })

phase('Verify')
const verify = await agent(
  `Verify the config-conflict collapse in ${WT} is score-safe.
1. Oracle replay: 'cd ${WT} && PG_OUTLINE_AGENT_MAX_TURNS=3 ${PY} tests/oracle/acceptance_portable.py --replay 2>&1 | tail -10' — SHA==${GOLDEN}, controls pass. (Proves the outline-path config reads are unchanged.)
2. Collection == ${inv.baseline}.
3. Config characterization: '${PY} -m pytest tests/test_config_registry.py tests/test_settings_models.py -q | tail -1'. NOTE: if a collapsed key's registry default changed, test_config_registry (which asserts resolve==os.getenv(key,default)) should STILL pass because it reads the registry default dynamically — confirm it passes; if it hard-codes an old default, update the test to the new registry value and note it.
Return oracle_matches, oracle_sha, collection_ok, characterization_ok, notes.`,
  { label: 'verify', phase: 'Verify', schema: { type:'object', additionalProperties:false, required:['oracle_matches','oracle_sha','collection_ok','characterization_ok','notes'], properties:{ oracle_matches:{type:'boolean'}, oracle_sha:{type:'string'}, collection_ok:{type:'boolean'}, characterization_ok:{type:'boolean'}, notes:{type:'string'} } } })

phase('Codex-Gate')
const gate = await agent(
  `Run CODEX (GPT-5.6) to gate the config-conflict collapse. Write /tmp/cfg_gate.md then 'cd /tmp && timeout 240 codex exec --skip-git-repo-check - < /tmp/cfg_gate.md 2>&1 | tail -30' (embed inline; medium effort; no sandbox flags).
Context: 20 PG_ keys had conflicting fallback defaults. We collapsed the BYTE-SAFE (env-set: env wins, only unused fallback changed) and SAFE-PRIMARY (primary-path value kept, secondary aligned up, no faithfulness weakening) keys; DEFERRED the rest. Investigation: ${JSON.stringify(inv.keys)}. Collapse: ${JSON.stringify(collapse)}. Verify: ${JSON.stringify(verify)} (oracle byte-identical ${GOLDEN}).
Ask codex: "For each collapsed key, is the change byte-safe (env-set => env wins so runtime unchanged; or primary-path value preserved)? Did any collapse WEAKEN faithfulness (lower a threshold/evidence floor on a live path)? Are the DEFER classifications correct (genuinely behavior-changing / ambiguous left for the owner)? End with CONFIG-COLLAPSE-SAFE or CONFIG-COLLAPSE-REVISE (+ any key that must move to DEFER)."
Return verdict + points.`,
  { label: 'codex-gate', phase: 'Codex-Gate', schema: { type:'object', additionalProperties:false, required:['verdict','codex_points'], properties:{ verdict:{type:'string'}, codex_points:{type:'array',items:{type:'string'}} } } })

phase('Record')
const rec = await agent(
  `Record the config-conflict collapse in ${WT} (branch chore/review-readiness-config).
Only commit the collapse if verify passed (oracle_matches=${verify.oracle_matches}, collection_ok=${verify.collection_ok}) and codex=CONFIG-COLLAPSE-SAFE (${gate.verdict}); if codex flagged a key to DEFER, revert that key first. Else if unsafe, commit nothing + report.
1. Update docs/review_readiness/config_conflicts.md: mark each key RESOLVED (to which value, why byte-safe) or DEFERRED (needs owner decision, incl PG_FAITHFULNESS_NLI_THRESHOLD if it landed in DEFER — state the 0.65-vs-0.75 divergence + that frozen-faithfulness forbids auto-weakening).
2. Stage EXPLICIT paths: git add src/ docs/ (guard 0 tests/oracle staged). Commit ("Config: collapse N conflicting-default keys to authoritative values (byte-safe, faithfulness preserved); M deferred to owner") with standard trailers.
3. Push -u origin; PR base gate-inversion (title "Code-review readiness: collapse conflicting config defaults", body describing collapsed vs deferred, oracle byte-identical, codex-gated).
Return {commit_sha, pushed, pr_url, collapsed, deferred}.`,
  { label: 'record', phase: 'Record', schema: { type:'object', additionalProperties:false, required:['commit_sha','pushed','pr_url','collapsed','deferred'], properties:{ commit_sha:{type:'string'}, pushed:{type:'boolean'}, pr_url:{type:'string'}, collapsed:{type:'integer'}, deferred:{type:'array',items:{type:'string'}} } } })

return { inv: { byte_safe_count: inv.byte_safe_count, defer_count: inv.defer_count }, collapse, verify, gate, record: rec }
