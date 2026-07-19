export const meta = {
  name: 'codex-q6-launcher',
  description: 'Execute codex Q6: consolidate run_full_scale_v10..v30 into one parameterized launcher + call-through shims (behavior-preserving, byte-identical env profiles)',
  phases: [
    { title: 'Build', detail: 'one run_full_scale.py + per-variant shims delegating to it' },
    { title: 'Verify', detail: 'env profiles byte-identical to originals + collection + oracle' },
    { title: 'Codex-Gate', detail: 'codex confirms behavior-preserving' },
    { title: 'Record', detail: 'commit + push + PR' },
  ],
}
const PY = '/home/polaris/pipeline-env/bin/python'
const GOLDEN = '9c0a3d438da943242c98e2fe714494c342d42d02102202d75a61a4554339db98'
const WT = '/home/polaris/wt/phase-launcher'

phase('Build')
const build = await agent(
  `Execute codex's Q6 launcher consolidation: merge the near-duplicate run_full_scale_v10..v30 scripts into ONE parameterized launcher + thin call-through shims. Behavior-preserving (each old script must still run identically).
1. cd /workspace/POLARIS && git worktree remove ${WT} --force 2>/dev/null; git branch -D chore/review-readiness-launcher 2>/dev/null; git worktree add ${WT} -b chore/review-readiness-launcher chore/review-readiness-phase1.
2. Force-copy phase0 harness (unstaged): cp /home/polaris/wt/phase0/tests/oracle/*.py ${WT}/tests/oracle/ ; cp /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_golden.json /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_llm.jsonl /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_retrieval.jsonl ${WT}/tests/oracle/cassettes/.
3. Find the run_full_scale_v*.py scripts (scripts/). Read each — they differ only by a VARIANT (version + an env-profile dict + a couple of args). Create scripts/run_full_scale.py exposing run(variant, argv) with a VARIANT_ENV table reproducing EACH script's env dict BYTE-FOR-BYTE (verify each variant's dict equals the original's). Then replace each run_full_scale_vNN.py with a thin call-through shim (e.g. 'from run_full_scale import run; import sys; run("vNN", sys.argv[1:])') — do NOT delete the old filenames (some are referenced), keep them as shims. Preserve env precedence (override=False), --only/--out-root injection only when absent, verbatim arg forwarding.
   IMPORTANT: if a v*.py is referenced by string/importlib/by-path (grep first), keep its shim byte-runnable. run_full_scale_v30_phase2.py is a KNOWN dynamic-ref (by-path load + filename test assertion) — leave it or shim it carefully so the by-path load + assertion still pass.
py_compile all; collection == 16738/11.
Return: launcher_created, variants_consolidated, shims_written, env_dicts_byte_identical (bool), skipped (list), collection_after.`,
  { label: 'build', phase: 'Build', schema: { type:'object', additionalProperties:false, required:['launcher_created','variants_consolidated','shims_written','env_dicts_byte_identical','skipped','collection_after'], properties:{ launcher_created:{type:'boolean'}, variants_consolidated:{type:'integer'}, shims_written:{type:'integer'}, env_dicts_byte_identical:{type:'boolean'}, skipped:{type:'array',items:{type:'string'}}, collection_after:{type:'string'} } } })

phase('Verify')
const verify = await agent(
  `Verify Q6 launcher in ${WT}. 1. Collection == 16738/11. 2. Oracle 'cd ${WT} && PG_OUTLINE_AGENT_MAX_TURNS=3 ${PY} tests/oracle/acceptance_portable.py --replay 2>&1 | tail -4' SHA==${GOLDEN} (launcher is scripts-only, should be trivially unaffected). 3. For 2-3 variants, PROVE the shim reproduces the original: compare the launcher's VARIANT_ENV[vNN] dict against the git-HEAD original script's env dict (assert equal); import each shim + confirm it delegates. 4. Confirm no v*.py referenced by string/by-path was broken (grep + the run_full_scale_v30_phase2 by-path load still resolvable). Return collection_ok, oracle_matches, oracle_sha, variants_verified_identical, dynamic_refs_intact.`,
  { label: 'verify', phase: 'Verify', schema: { type:'object', additionalProperties:false, required:['collection_ok','oracle_matches','oracle_sha','variants_verified_identical','dynamic_refs_intact'], properties:{ collection_ok:{type:'boolean'}, oracle_matches:{type:'boolean'}, oracle_sha:{type:'string'}, variants_verified_identical:{type:'integer'}, dynamic_refs_intact:{type:'boolean'} } } })

phase('Codex-Gate')
const gate = await agent(
  `Run CODEX (GPT-5.6) to gate the Q6 launcher consolidation. Write /tmp/q6l_gate.md then 'cd /tmp && timeout 200 codex exec --skip-git-repo-check - < /tmp/q6l_gate.md 2>&1 | tail -22' (embed inline; medium; no sandbox flags).
Evidence: build=${JSON.stringify(build)}, verify=${JSON.stringify(verify)} (env dicts byte-identical, oracle byte-identical ${GOLDEN}, dynamic refs intact).
Ask codex: "Is the run_full_scale consolidation behaviour-preserving (each old script still runs identically via a call-through shim, env profiles byte-identical, dynamic/by-path refs intact, no deleted-in-use file)? End with LAUNCHER-SAFE or LAUNCHER-REVISE."
Return verdict + points.`,
  { label: 'codex-gate', phase: 'Codex-Gate', schema: { type:'object', additionalProperties:false, required:['verdict','codex_points'], properties:{ verdict:{type:'string'}, codex_points:{type:'array',items:{type:'string'}} } } })

phase('Record')
const rec = await agent(
  `Record Q6 launcher in ${WT} (branch chore/review-readiness-launcher). Commit if verify passed (collection_ok, oracle_matches, dynamic_refs_intact) and codex=LAUNCHER-SAFE (${gate.verdict}). Stage explicit 'git add scripts/' + docs/review_readiness/codex_q6_launcher.md; GUARD 'git diff --cached --name-only | grep -c tests/oracle' == 0. Commit ("Phase 2 per codex: consolidate run_full_scale_v10..v30 into one parameterized launcher + call-through shims (behavior-preserving)") std trailers. Push -u origin; PR base gate-inversion.
Return {commit_sha, pushed, pr_url, committed_or_blocked}.`,
  { label: 'record', phase: 'Record', schema: { type:'object', additionalProperties:false, required:['commit_sha','pushed','pr_url','committed_or_blocked'], properties:{ commit_sha:{type:'string'}, pushed:{type:'boolean'}, pr_url:{type:'string'}, committed_or_blocked:{type:'string'} } } })

return { build, verify, gate, record: rec }
