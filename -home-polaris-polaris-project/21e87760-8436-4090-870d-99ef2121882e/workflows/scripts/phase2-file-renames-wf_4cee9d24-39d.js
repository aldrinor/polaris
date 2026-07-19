export const meta = {
  name: 'phase2-file-renames',
  description: 'Plan V4 FILE-RENAME class: consolidate run_full_scale_v10..v30 into one parameterized launcher + rename only static-safe files (skip+document dynamic-referenced); oracle+collection+codex gated',
  phases: [
    { title: 'Inventory', detail: 'worktree + correct harness + classify FILE-RENAME rows static-safe vs dynamic-referenced' },
    { title: 'Execute', detail: 'git mv static-safe files + fix importers; build the parameterized launcher' },
    { title: 'Verify', detail: 'collection unchanged + oracle byte-identical + old scripts still runnable' },
    { title: 'Codex-Gate', detail: 'codex confirms no importer/string/CLI reference broken' },
    { title: 'Record', detail: 'commit + push + PR; document skipped' },
  ],
}
const PY = '/home/polaris/pipeline-env/bin/python'
const GOLDEN = '9c0a3d438da943242c98e2fe714494c342d42d02102202d75a61a4554339db98'
const WORKLIST = '/home/polaris/polaris_project/NAME_RENAME_WORKLIST_validated.tsv'
const WT = '/home/polaris/wt/phase-file'

phase('Inventory')
const inv = await agent(
  `Set up the Plan V4 FILE-RENAME class (the ~45 file-rename rows) conservatively.
1. cd /workspace/POLARIS && git worktree remove ${WT} --force 2>/dev/null; git branch -D chore/review-readiness-filerename 2>/dev/null; git worktree add ${WT} -b chore/review-readiness-filerename chore/review-readiness-phase1.
2. FIX ORACLE HARNESS (phase1 base has the stale harness): force-copy phase0's trustworthy harness for validation: cp /home/polaris/wt/phase0/tests/oracle/*.py ${WT}/tests/oracle/ ; mkdir -p ${WT}/tests/oracle/cassettes ; cp /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_golden.json /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_llm.jsonl /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_retrieval.jsonl ${WT}/tests/oracle/cassettes/. (These stay UNSTAGED — never commit tests/oracle.)
3. Read ${WORKLIST}; extract the FILE-RENAME rows (~45): old filepath -> new filepath. Also identify the run_full_scale_v10..v30 near-duplicate scripts (Plan V4 wants these consolidated into ONE parameterized launcher).
4. For EACH file-rename target, classify SAFE-STATIC vs DYNAMIC-REF: grep the repo for the module/file basename as a STRING (importlib, spec_from_file_location, __import__, subprocess calling the script by path, CI/docs referencing the filename, source-grep test assertions). SAFE-STATIC = referenced only via normal python imports that can be mechanically fixed. DYNAMIC-REF = referenced by string/path/CLI/CI → SKIP + document (a file rename would break an untracked reference).
5. Baseline: '${PY} -m pytest tests/ --collect-only -q | tail -1' (16738/11), and confirm the corrected oracle replay works: 'cd ${WT} && PG_OUTLINE_AGENT_MAX_TURNS=3 ${PY} tests/oracle/acceptance_portable.py --replay 2>&1 | tail -3' (SHA==${GOLDEN}).
Return: safe_static (list old->new), dynamic_skip (list old->new + reason), the run_full_scale scripts found, baseline, oracle_ok.`,
  { label: 'inventory', phase: 'Inventory', schema: { type:'object', additionalProperties:false, required:['safe_static','dynamic_skip','run_full_scale_scripts','baseline','oracle_ok'], properties:{ safe_static:{type:'array',items:{type:'object',additionalProperties:true}}, dynamic_skip:{type:'array',items:{type:'object',additionalProperties:true}}, run_full_scale_scripts:{type:'array',items:{type:'string'}}, baseline:{type:'string'}, oracle_ok:{type:'boolean'} } } })

phase('Execute')
const exec = await agent(
  `Execute the SAFE-STATIC file renames + the launcher consolidation in ${WT}. SAFE-STATIC: ${JSON.stringify(inv.safe_static)}. run_full_scale scripts: ${JSON.stringify(inv.run_full_scale_scripts)}. Do NOT touch the DYNAMIC-REF skips.
1. For each SAFE-STATIC old->new: 'git mv old new' then fix EVERY importer (grep the module path, update 'from X import' / 'import X' to the new path). After each rename run '${PY} -m pytest tests/ --collect-only -q | tail -1' — must stay at ${inv.baseline}; if it errors, the rename broke an importer you missed → fix or 'git mv' back + skip+document.
2. LAUNCHER CONSOLIDATION: if the run_full_scale_v10..v30 scripts are genuine near-duplicates differing only by a version/param, create ONE parameterized launcher (e.g. scripts/run_full_scale.py --variant vNN) that reproduces each script's behaviour via a param, and replace the duplicates with thin shims OR keep them as deprecated wrappers that call the launcher (do NOT delete if any are referenced by CI/docs — make them call-through shims). If they are NOT true duplicates (real behavioural differences), do NOT force-merge — document why and skip.
py_compile changed files; keep collection at baseline.
Return: files_renamed (count), importers_fixed (count), launcher_created (bool), scripts_consolidated (count), skipped_during_exec (list), collection_after.`,
  { label: 'execute', phase: 'Execute', schema: { type:'object', additionalProperties:false, required:['files_renamed','importers_fixed','launcher_created','scripts_consolidated','skipped_during_exec','collection_after'], properties:{ files_renamed:{type:'integer'}, importers_fixed:{type:'integer'}, launcher_created:{type:'boolean'}, scripts_consolidated:{type:'integer'}, skipped_during_exec:{type:'array',items:{type:'string'}}, collection_after:{type:'string'} } } })

phase('Verify')
const verify = await agent(
  `Verify the file renames in ${WT} broke nothing.
1. Collection == ${inv.baseline}: '${PY} -m pytest tests/ --collect-only -q | tail -1'.
2. Oracle replay (harness already force-copied in Inventory; re-copy if missing): 'cd ${WT} && PG_OUTLINE_AGENT_MAX_TURNS=3 ${PY} tests/oracle/acceptance_portable.py --replay 2>&1 | tail -6' — SHA==${GOLDEN}, controls pass.
3. If a launcher was created: run it in --help / dry mode to confirm it imports + parses (do NOT run a full pipeline). Confirm any consolidated old script still works as a call-through (import it).
4. Grep the repo for any now-DANGLING import of a renamed module (old path still referenced anywhere): report any dangling references.
Return: collection_ok, oracle_matches, oracle_sha, launcher_ok, dangling_refs (list).`,
  { label: 'verify', phase: 'Verify', schema: { type:'object', additionalProperties:false, required:['collection_ok','oracle_matches','oracle_sha','launcher_ok','dangling_refs'], properties:{ collection_ok:{type:'boolean'}, oracle_matches:{type:'boolean'}, oracle_sha:{type:'string'}, launcher_ok:{type:'boolean'}, dangling_refs:{type:'array',items:{type:'string'}} } } })

phase('Codex-Gate')
const gate = await agent(
  `Run CODEX (GPT-5.6) to gate the file renames + launcher consolidation. Write /tmp/file_gate.md then 'cd /tmp && timeout 240 codex exec --skip-git-repo-check - < /tmp/file_gate.md 2>&1 | tail -30' (embed inline; medium; no sandbox flags).
Evidence: inventory=${JSON.stringify(inv)}, execute=${JSON.stringify(exec)}, verify=${JSON.stringify(verify)} (oracle byte-identical ${GOLDEN}, collection at baseline, ${verify.dangling_refs.length} dangling refs).
Ask codex: "Are all executed file renames reference-complete (every importer fixed, no dangling reference, no dynamic/string/CLI/CI reference to a renamed file left broken)? Is the launcher consolidation behaviour-preserving (old scripts still work as call-throughs, no behavioural drift)? Were the DYNAMIC-REF files correctly skipped? End with FILE-RENAME-SAFE or FILE-RENAME-REVISE (+ the specific broken reference)."
Return verdict + points.`,
  { label: 'codex-gate', phase: 'Codex-Gate', schema: { type:'object', additionalProperties:false, required:['verdict','codex_points'], properties:{ verdict:{type:'string'}, codex_points:{type:'array',items:{type:'string'}} } } })

phase('Record')
const rec = await agent(
  `Record the file renames in ${WT} (branch chore/review-readiness-filerename). Commit only if verify passed (collection_ok=${verify.collection_ok}, oracle_matches=${verify.oracle_matches}, dangling_refs empty) and codex=FILE-RENAME-SAFE (${gate.verdict}). Else commit only the safe subset / report blocker.
Stage explicit paths: 'git add src/ scripts/' (git mv changes are staged; guard 'git diff --cached --name-only | grep -c tests/oracle' == 0 — if not, git restore --staged tests/oracle/). Write docs/review_readiness/phase2_file_renames.md (renamed count, launcher consolidation, DYNAMIC-REF skipped for human review). Commit ("Phase 2 FILE-RENAME: rename N static-safe files + consolidate run_full_scale_v10..v30 launcher (oracle byte-identical)") with standard trailers. Push -u origin; PR base gate-inversion.
Return {commit_sha, pushed, pr_url, committed_or_blocked}.`,
  { label: 'record', phase: 'Record', schema: { type:'object', additionalProperties:false, required:['commit_sha','pushed','pr_url','committed_or_blocked'], properties:{ commit_sha:{type:'string'}, pushed:{type:'boolean'}, pr_url:{type:'string'}, committed_or_blocked:{type:'string'} } } })

return { inv: { safe_static_count: inv.safe_static.length, dynamic_skip_count: inv.dynamic_skip.length }, exec, verify, gate, record: rec }
