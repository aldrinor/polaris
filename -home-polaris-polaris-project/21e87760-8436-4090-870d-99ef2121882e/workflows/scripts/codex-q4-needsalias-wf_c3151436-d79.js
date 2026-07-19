export const meta = {
  name: 'codex-q4-needsalias',
  description: 'Execute codex Q4: rename NEEDS-ALIAS symbols to codex canonical names (V30ClinicalSweepJobRunner / is_row_content_integrity_violation / content_integrity_deletion_gate) + backward-compat aliases for every control-surface/persisted rename (old+new resolve to same object)',
  phases: [
    { title: 'Rename', detail: 'apply canonical renames + robust aliases (module __getattr__/re-export; same-object for monkeypatch)' },
    { title: 'Verify', detail: 'collection + oracle + every OLD reference still resolves (import + monkeypatch + string)' },
    { title: 'Codex-Gate', detail: 'codex confirms aliases preserve behavior' },
    { title: 'Record', detail: 'commit + push + PR' },
  ],
}
const PY = '/home/polaris/pipeline-env/bin/python'
const GOLDEN = '9c0a3d438da943242c98e2fe714494c342d42d02102202d75a61a4554339db98'
const WT = '/home/polaris/wt/phase-q4'

phase('Rename')
const rn = await agent(
  `Execute codex's Q4 canonical NEEDS-ALIAS renames in a fresh worktree, with backward-compat aliases for EVERY control-surface/persisted rename (codex policy: preserve compatibility by default; old imports re-exported; old env/CLI/persisted strings still accepted; remove aliases only after owner deprecation — not now).
1. cd /workspace/POLARIS && git worktree remove ${WT} --force 2>/dev/null; git branch -D chore/review-readiness-q4 2>/dev/null; git worktree add ${WT} -b chore/review-readiness-q4 chore/review-readiness-phase1.
2. Force-copy phase0 harness (unstaged): cp /home/polaris/wt/phase0/tests/oracle/*.py ${WT}/tests/oracle/ ; cp /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_golden.json /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_llm.jsonl /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_retrieval.jsonl ${WT}/tests/oracle/cassettes/.
3. Apply these CODEX-DECIDED canonical renames + aliases:
   (a) class HonestSweepJobRunner -> V30ClinicalSweepJobRunner; HonestSweepJobRunnerConfig -> V30ClinicalSweepJobRunnerConfig; make_default_honest_sweep_job_runner -> make_default_v30_clinical_sweep_job_runner. Rename the DEFINITIONS in src/polaris_graph/audit_ir/honest_sweep_job_runner.py, then in the same module add module-level aliases: HonestSweepJobRunner = V30ClinicalSweepJobRunner (etc.) so old imports AND monkeypatch.setattr on the old name work (same object). Update the __init__.py re-exports to export BOTH names.
   (b) func is_row_content_junk -> is_row_content_integrity_violation (in generator/junk_deletion_gate.py). Keep is_row_content_junk = is_row_content_integrity_violation as a module alias.
   (c) file junk_deletion_gate.py -> content_integrity_deletion_gate.py (git mv), fix static importers; ADD a shim module junk_deletion_gate.py that does 'from .content_integrity_deletion_gate import *' + re-exports the key names, so old 'import ...junk_deletion_gate' still works (the file's basename is referenced as a string in some places per prior analysis — keep the old module importable).
4. For any symbol a test monkeypatches by the OLD name: ensure old and new refer to the SAME object in the SAME module namespace (module-level alias), so patching either name is observed (codex's same-object requirement).
5. Skip + document anything where an alias genuinely cannot preserve behavior (e.g. a source-grep test asserting the exact old def-name text) — those need a test update (out of scope).
py_compile; collection == 16738/11 after.
Return: renames_applied, aliases_added, skipped (list+reason), collection_after.`,
  { label: 'rename', phase: 'Rename', schema: { type:'object', additionalProperties:false, required:['renames_applied','aliases_added','skipped','collection_after'], properties:{ renames_applied:{type:'integer'}, aliases_added:{type:'integer'}, skipped:{type:'array',items:{type:'string'}}, collection_after:{type:'string'} } } })

phase('Verify')
const verify = await agent(
  `Verify Q4 in ${WT}. 1. Collection == 16738/11. 2. Oracle 'cd ${WT} && PG_OUTLINE_AGENT_MAX_TURNS=3 ${PY} tests/oracle/acceptance_portable.py --replay 2>&1 | tail -6' SHA==${GOLDEN}. 3. ALIAS RESOLUTION (behavioral, per codex): python-c import checks that BOTH old and new names resolve to the SAME object: e.g. 'from src.polaris_graph.audit_ir.honest_sweep_job_runner import HonestSweepJobRunner, V30ClinicalSweepJobRunner; assert HonestSweepJobRunner is V30ClinicalSweepJobRunner'; old module 'import src.polaris_graph.generator.junk_deletion_gate' still imports; is_row_content_junk still importable and is the new func. Report each alias check pass/fail. 4. Run any test that monkeypatches/imports the old names ('${PY} -m pytest tests/polaris_graph -k "honest_sweep or junk or content_integrity" -q --no-header 2>&1 | tail -5') — compare to pre-change baseline (stash+run if a failure appears, to prove pre-existing). Return collection_ok, oracle_matches, oracle_sha, aliases_all_same_object, related_tests_ok.`,
  { label: 'verify', phase: 'Verify', schema: { type:'object', additionalProperties:false, required:['collection_ok','oracle_matches','oracle_sha','aliases_all_same_object','related_tests_ok','notes'], properties:{ collection_ok:{type:'boolean'}, oracle_matches:{type:'boolean'}, oracle_sha:{type:'string'}, aliases_all_same_object:{type:'boolean'}, related_tests_ok:{type:'boolean'}, notes:{type:'string'} } } })

phase('Codex-Gate')
const gate = await agent(
  `Run CODEX (GPT-5.6) to gate Q4 renames+aliases. Write /tmp/q4_gate.md then 'cd /tmp && timeout 220 codex exec --skip-git-repo-check - < /tmp/q4_gate.md 2>&1 | tail -25' (embed inline; medium; no sandbox flags).
Codex previously decided the canonical names (V30ClinicalSweepJobRunner, is_row_content_integrity_violation, content_integrity_deletion_gate) + alias-all policy with old+new resolving to the SAME object for monkeypatch compatibility. Result: ${JSON.stringify(rn)}. Verify: ${JSON.stringify(verify)} (oracle byte-identical ${GOLDEN}; aliases_all_same_object=${verify.aliases_all_same_object}).
Ask codex: "Do the aliases preserve EVERY old reference (imports, monkeypatch targets via same-object, string module names, persisted keys) with no behavior change (collection + oracle unchanged)? Any cosmetic-only alias that fails the same-object/monkeypatch requirement? End with Q4-SAFE or Q4-REVISE."
Return verdict + points.`,
  { label: 'codex-gate', phase: 'Codex-Gate', schema: { type:'object', additionalProperties:false, required:['verdict','codex_points'], properties:{ verdict:{type:'string'}, codex_points:{type:'array',items:{type:'string'}} } } })

phase('Record')
const rec = await agent(
  `Record Q4 in ${WT} (branch chore/review-readiness-q4). Commit if verify passed (collection_ok, oracle_matches, aliases_all_same_object) and codex=Q4-SAFE (${gate.verdict}). Stage explicit 'git add src/ scripts/ tests/' (git mv changes staged) + docs/review_readiness/codex_q4_needs_alias.md; GUARD 'git diff --cached --name-only | grep -c tests/oracle' == 0 (else git restore --staged tests/oracle/). Commit ("Phase 2 NEEDS-ALIAS per codex: V30ClinicalSweepJobRunner / is_row_content_integrity_violation / content_integrity_deletion_gate + backward-compat aliases (same-object, oracle byte-identical)") std trailers. Push -u origin; PR base gate-inversion.
Return {commit_sha, pushed, pr_url, committed_or_blocked}.`,
  { label: 'record', phase: 'Record', schema: { type:'object', additionalProperties:false, required:['commit_sha','pushed','pr_url','committed_or_blocked'], properties:{ commit_sha:{type:'string'}, pushed:{type:'boolean'}, pr_url:{type:'string'}, committed_or_blocked:{type:'string'} } } })

return { rn, verify, gate, record: rec }
