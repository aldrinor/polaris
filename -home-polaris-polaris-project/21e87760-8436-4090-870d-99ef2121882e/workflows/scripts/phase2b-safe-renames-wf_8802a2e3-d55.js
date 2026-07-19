export const meta = {
  name: 'phase2b-safe-renames',
  description: 'Execute the low-risk Plan V4 renames (SAFE-static symbols + TEXT-ONLY), gated by test-collection + oracle SHA + codex',
  phases: [
    { title: 'Setup', detail: 'phase2 worktree + parse SAFE-static/TEXT-ONLY rows + overlay oracle' },
    { title: 'Rename', detail: 'execute renames with per-rename verify + revert-on-failure' },
    { title: 'Validate', detail: 'test collection unchanged + oracle replay SHA==golden' },
    { title: 'Codex-Gate', detail: 'codex confirms renames are reference-complete + score-safe' },
    { title: 'Record', detail: 'commit + open PR' },
  ],
}

const PY = '/home/polaris/pipeline-env/bin/python'
const GOLDEN = '9c0a3d438da943242c98e2fe714494c342d42d02102202d75a61a4554339db98'
const WORKLIST = '/home/polaris/polaris_project/NAME_RENAME_WORKLIST_validated.tsv'
const WT = '/home/polaris/wt/phase2'

phase('Setup')
const setup = await agent(
  `Set up a worktree to execute low-risk code renames for a code-review-readiness cleanup.
1. cd /workspace/POLARIS && git worktree remove ${WT} --force 2>/dev/null; git branch -D chore/review-readiness-phase2 2>/dev/null; git worktree add ${WT} -b chore/review-readiness-phase2 chore/review-readiness-phase1   (builds on the migrated Phase 1 code).
2. Overlay the pinned oracle for validation: cd ${WT} && git checkout chore/review-readiness-phase0 -- tests/oracle/ ; cp -n /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_llm.jsonl /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_retrieval.jsonl /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_golden.json ${WT}/tests/oracle/cassettes/ 2>/dev/null ; ls ${WT}/tests/oracle/cassettes/.
3. Parse ${WORKLIST}: identify the rows whose risk class is SAFE (pure code symbol renames) and TEXT-ONLY (docstring/log-tag jargon). For each, extract old_name, new_name, and location/file. Return the two lists (SAFE-static and TEXT-ONLY) as structured rows. Report the exact counts (expected ~105 SAFE + 12 TEXT-ONLY per the plan; report the actual numbers you find).
4. Establish the BASELINE: 'cd ${WT} && timeout 200 ${PY} -m pytest tests/ --collect-only -q 2>&1 | tail -1' — record the collected count + error count (this is the green baseline renames must not regress).
Return the parsed rows + baseline collection numbers.`,
  { label: 'setup', phase: 'Setup', schema: { type:'object', additionalProperties:false, required:['safe_rows','text_rows','safe_count','text_count','baseline_collection'], properties:{ safe_rows:{type:'array',items:{type:'object',additionalProperties:true}}, text_rows:{type:'array',items:{type:'object',additionalProperties:true}}, safe_count:{type:'integer'}, text_count:{type:'integer'}, baseline_collection:{type:'string'} } } })

phase('Rename')
const rename = await agent(
  `Execute low-risk renames in ${WT} (branch chore/review-readiness-phase2). You have these rows to rename (from the worklist):
TEXT-ONLY (docstring/log-tag edits only, zero runtime risk): ${JSON.stringify(setup.text_rows)}
SAFE-static (pure code symbols with static references only): ${JSON.stringify(setup.safe_rows)}
Baseline collection to preserve: ${setup.baseline_collection}
Method (mirror the proven config-migration discipline):
1. TEXT-ONLY: replace the old jargon token with the new one ONLY in docstrings/comments/log strings at the cited location. Do not touch identifiers.
2. SAFE-static symbols: for each old_name->new_name, rename the DEFINITION and ALL references within src/ (and scripts/tests if they reference it). Use word-boundary-aware replacement (\\b) so you never partial-match. NEVER rename inside string literals unless it is a TEXT-ONLY row. If a symbol's grep shows it is referenced as a STRING anywhere (dynamic), SKIP it and record it as skipped (it should have been NEEDS-ALIAS, not SAFE).
3. After EACH batch of ~10 renames: run 'cd ${WT} && timeout 200 ${PY} -m pytest tests/ --collect-only -q 2>&1 | tail -1'. If the error count rose above baseline, find the offending rename, REVERT just it (git diff to locate), and record it as skipped. Keep collection at baseline.
4. py_compile any changed file; revert any that fail to compile.
Be conservative: when unsure a rename is reference-complete, SKIP and record it rather than risk breakage. Return the counts applied vs skipped, and the list of skipped names with reasons.`,
  { label: 'rename', phase: 'Rename', schema: { type:'object', additionalProperties:false, required:['text_applied','safe_applied','skipped','collection_after'], properties:{ text_applied:{type:'integer'}, safe_applied:{type:'integer'}, skipped:{type:'array',items:{type:'string'}}, collection_after:{type:'string'} } } })

phase('Validate')
const validate = await agent(
  `Validate the renames in ${WT} are score-safe.
1. Full test COLLECTION unchanged: 'cd ${WT} && timeout 200 ${PY} -m pytest tests/ --collect-only -q 2>&1 | tail -1' — must match the baseline error count (${setup.baseline_collection}). Report it.
2. Config characterization still green: 'cd ${WT} && timeout 120 ${PY} -m pytest tests/test_config_registry.py tests/test_settings_models.py -q 2>&1 | tail -1'.
3. ORACLE replay on the covered path: 'cd ${WT} && PG_OUTLINE_AGENT_MAX_TURNS=3 ${PY} tests/oracle/acceptance_portable.py --replay 2>&1 | tail -20'. Confirm the artifact SHA still equals the golden ${GOLDEN} and both controls pass (this proves the renames didn't move behavior on the covered outline path). If the outline agent's own symbols were renamed and the oracle files reference old names, note that (the oracle path may need the same rename to stay consistent).
Return whether all three gates pass + the collection numbers + oracle SHA.`,
  { label: 'validate', phase: 'Validate', schema: { type:'object', additionalProperties:false, required:['collection_ok','characterization_ok','oracle_sha','oracle_matches','notes'], properties:{ collection_ok:{type:'boolean'}, characterization_ok:{type:'boolean'}, oracle_sha:{type:'string'}, oracle_matches:{type:'boolean'}, notes:{type:'string'} } } })

phase('Codex-Gate')
const gate = await agent(
  `Run CODEX (GPT-5.6) to gate a batch of low-risk code renames. Write /tmp/rename_gate.md then run 'cd /tmp && timeout 240 codex exec --skip-git-repo-check - < /tmp/rename_gate.md 2>&1 | tail -30' (bubblewrap warning fine; embed evidence inline; medium effort; no sandbox flags).
Context: We executed TEXT-ONLY + SAFE-static renames from a codex-pre-validated worklist. Rename result: ${JSON.stringify(rename)}. Validation: ${JSON.stringify(validate)}. The renames were required to keep pytest --collect-only at baseline error count and to keep the deterministic oracle replay byte-identical (golden ${GOLDEN}) on the covered path.
Ask codex: "Given test-collection is unchanged from baseline, config characterization passes, and the oracle replay is still byte-identical, are these SAFE-static + TEXT-ONLY renames reference-complete and score-safe to commit? Any residual risk (a symbol renamed but a dynamic/string reference missed)? End with: RENAMES-SAFE or RENAMES-REVISE."
Return codex's verdict + points.`,
  { label: 'codex-gate', phase: 'Codex-Gate', schema: { type:'object', additionalProperties:false, required:['verdict','codex_points'], properties:{ verdict:{type:'string'}, codex_points:{type:'array',items:{type:'string'}} } } })

phase('Record')
const rec = await agent(
  `Record the Phase 2B renames. Worktree ${WT} (branch chore/review-readiness-phase2).
Only proceed to commit if validation gates passed (collection_ok=${validate.collection_ok}, oracle_matches=${validate.oracle_matches}) and codex verdict was RENAMES-SAFE (${gate.verdict}). If not, commit nothing and report the blocker.
1. Remove the overlaid oracle tooling from staging if it wasn't already committed (we don't want to duplicate tests/oracle on this branch): check 'git status'; only stage src/ + scripts/ + tests/ rename changes, NOT the overlaid tests/oracle/* unless renames actually touched them. Grep-check no secret.
2. Write docs/review_readiness/phase2_renames_applied.md summarizing: which classes, counts applied/skipped, the gates that passed (collection, characterization, oracle SHA), codex verdict.
3. Commit ("Phase 2B: SAFE-static + TEXT-ONLY renames (score-safe, oracle-validated)") with trailers:
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TLpJSqNfJVSP1UGdtk89nA
4. Push -u origin chore/review-readiness-phase2 and open a PR to main via '/home/polaris/.local/bin/gh pr create --repo aldrinor/deep-cove-research --base main --head chore/review-readiness-phase2 --title "Code-review readiness: Phase 2B low-risk renames" --body "SAFE-static + TEXT-ONLY renames from the codex-validated worklist; test-collection unchanged, config characterization green, oracle replay byte-identical. 🤖 Generated with [Claude Code](https://claude.com/claude-code)"'.
Return {commit_sha, pushed, pr_url, committed_or_blocked}.`,
  { label: 'record', phase: 'Record', schema: { type:'object', additionalProperties:false, required:['commit_sha','pushed','pr_url','committed_or_blocked'], properties:{ commit_sha:{type:'string'}, pushed:{type:'boolean'}, pr_url:{type:'string'}, committed_or_blocked:{type:'string'} } } })

return { setup: { safe_count: setup.safe_count, text_count: setup.text_count, baseline: setup.baseline_collection }, rename, validate, gate, record: rec }
