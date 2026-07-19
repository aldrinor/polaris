export const meta = {
  name: 'phase2-needs-alias',
  description: 'Rename NEEDS-ALIAS symbols while keeping old strings working via backward-compat aliases; skip+document intractable ones',
  phases: [
    { title: 'Setup', detail: 'gather NEEDS-ALIAS rows (worklist 32 + 16 reclassified from 2B) + baseline' },
    { title: 'AliasRename', detail: 'rename symbol + add alias; verify old reference still resolves; skip intractable' },
    { title: 'Validate', detail: 'collection + characterization + oracle SHA + alias-resolves checks' },
    { title: 'Codex-Gate', detail: 'codex confirms aliases preserve every old reference + score-safe' },
    { title: 'Record', detail: 'commit + push (extends PR #1384)' },
  ],
}
const PY = '/home/polaris/pipeline-env/bin/python'
const GOLDEN = '9c0a3d438da943242c98e2fe714494c342d42d02102202d75a61a4554339db98'
const WORKLIST = '/home/polaris/polaris_project/NAME_RENAME_WORKLIST_validated.tsv'
const WT = '/home/polaris/wt/phase2'   // already has the 95 SAFE renames (commit 19e32a0)

phase('Setup')
const setup = await agent(
  `Prepare the NEEDS-ALIAS rename batch in ${WT} (branch chore/review-readiness-phase2, which already contains 95 committed SAFE renames at HEAD 19e32a0).
1. Ensure the oracle overlay is present for validation: 'cd ${WT} && git checkout chore/review-readiness-phase0 -- tests/oracle/ 2>/dev/null; cp -n /home/polaris/wt/phase0/tests/oracle/cassettes/*.jsonl /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_golden.json ${WT}/tests/oracle/cassettes/ 2>/dev/null; ls ${WT}/tests/oracle/cassettes/'.
2. Parse ${WORKLIST}: extract the rows whose class is NEEDS-ALIAS (control-surface / persisted strings / env-vars / enum literals — the plan expects ~32). For each: old_name, new_name, location, and the REFERENCE TYPE (env-var literal? monkeypatch string target? string dict key? source-grep harness assertion? public re-export?).
3. Also note: the prior SAFE batch (commit 19e32a0) SKIPPED 16 rows that were mis-classified SAFE but are really NEEDS-ALIAS (documented in that commit / the workflow result). Re-derive them by checking which SKIP-worthy dynamic references exist. Fold them into this batch.
4. Baseline: 'cd ${WT} && timeout 200 ${PY} -m pytest tests/ --collect-only -q 2>&1 | tail -1' (expect 16738 / 11).
Return the NEEDS-ALIAS rows with reference types + baseline.`,
  { label: 'setup', phase: 'Setup', schema: { type:'object', additionalProperties:false, required:['alias_rows','count','baseline'], properties:{ alias_rows:{type:'array',items:{type:'object',additionalProperties:true}}, count:{type:'integer'}, baseline:{type:'string'} } } })

phase('AliasRename')
const aliased = await agent(
  `Execute NEEDS-ALIAS renames in ${WT}. Rows: ${JSON.stringify(setup.alias_rows)}. Baseline to preserve: ${setup.baseline}.
The RULE (Plan V4 rule 4): rename the SYMBOL to the new name, but keep EVERY old reference working via a backward-compatible ALIAS — never a naive rename that would orphan a control-surface string.
Alias strategy by reference type:
- Symbol referenced by STRING via getattr/monkeypatch/namespace lookup: rename the def to new_name, then add a module-level 'old_name = new_name' alias so string lookups still resolve. Verify: the old name is still importable/getattr-able.
- Env-var / PG_ key literal: do NOT rename the string key (that IS the control surface); if the worklist wants a clearer symbol, rename the Python variable but keep reading the SAME env-var string. Old operator setting must still work.
- String DICT KEY / persisted data-contract key: keep the old string key working — add the new key as an alias or keep old and add a comment; do NOT break the persisted contract.
- SOURCE-GREP harness assertion (a test asserts "def old_name(" appears in source text): an alias does NOT satisfy a source-text assertion. SKIP these and document — they need the test updated by a human, out of scope here.
- CONFLICTING worklist targets (re-export vs definition disagree): SKIP and document — needs human reconciliation of the canonical name.
Process in small batches; after each, run collection ('${PY} -m pytest tests/ --collect-only -q | tail -1') and keep it at baseline. py_compile changed files; revert any that fail. For each APPLIED alias, add a quick assertion that the OLD reference still resolves (e.g. python -c "import module; assert hasattr(module,'old_name')").
Be conservative: skip + document anything you cannot make an old-reference-preserving alias for. Return applied count, skipped list w/ reasons, and collection_after.`,
  { label: 'alias-rename', phase: 'AliasRename', schema: { type:'object', additionalProperties:false, required:['applied','skipped','collection_after','aliases_verified'], properties:{ applied:{type:'integer'}, skipped:{type:'array',items:{type:'string'}}, collection_after:{type:'string'}, aliases_verified:{type:'boolean'} } } })

phase('Validate')
const validate = await agent(
  `Validate the NEEDS-ALIAS renames in ${WT} are score-safe AND preserve old references.
1. Collection unchanged: '${PY} -m pytest tests/ --collect-only -q | tail -1' == baseline (${setup.baseline}).
2. Config characterization: '${PY} -m pytest tests/test_config_registry.py tests/test_settings_models.py -q | tail -1'.
3. Oracle replay: 'cd ${WT} && PG_OUTLINE_AGENT_MAX_TURNS=3 ${PY} tests/oracle/acceptance_portable.py --replay 2>&1 | tail -15' — artifact SHA must equal ${GOLDEN}, both controls pass.
4. ALIAS RESOLUTION: for each applied alias, confirm the OLD name still resolves (import + hasattr, or the env var still read). Report any alias that does NOT preserve the old reference.
Return all gate results + oracle SHA.`,
  { label: 'validate', phase: 'Validate', schema: { type:'object', additionalProperties:false, required:['collection_ok','characterization_ok','oracle_matches','oracle_sha','aliases_all_resolve','notes'], properties:{ collection_ok:{type:'boolean'}, characterization_ok:{type:'boolean'}, oracle_matches:{type:'boolean'}, oracle_sha:{type:'string'}, aliases_all_resolve:{type:'boolean'}, notes:{type:'string'} } } })

phase('Codex-Gate')
const gate = await agent(
  `Run CODEX (GPT-5.6) to gate NEEDS-ALIAS renames. Write /tmp/alias_gate.md then 'cd /tmp && timeout 240 codex exec --skip-git-repo-check - < /tmp/alias_gate.md 2>&1 | tail -30' (embed evidence inline; medium effort; no sandbox flags; bubblewrap warning fine).
Context: renamed control-surface symbols while adding backward-compat aliases so old strings/monkeypatch-targets/env-vars still work. Result: ${JSON.stringify(aliased)}. Validation: ${JSON.stringify(validate)}. Gates required: collection unchanged, oracle byte-identical (${GOLDEN}), and every OLD reference still resolves via its alias.
Ask codex: "Do these aliases preserve EVERY old reference (env-var strings, monkeypatch targets, string dict keys, re-exports) so no operator setting or persisted contract breaks? Is it score-safe (collection + oracle unchanged)? Any alias that is cosmetic-only and doesn't actually preserve the old reference? End with: ALIASES-SAFE or ALIASES-REVISE."
Return verdict + points.`,
  { label: 'codex-gate', phase: 'Codex-Gate', schema: { type:'object', additionalProperties:false, required:['verdict','codex_points'], properties:{ verdict:{type:'string'}, codex_points:{type:'array',items:{type:'string'}} } } })

phase('Record')
const rec = await agent(
  `Record the NEEDS-ALIAS renames. Worktree ${WT} (branch chore/review-readiness-phase2, PR #1384 exists to base gate-inversion).
Only commit if validate gates passed (collection_ok=${validate.collection_ok}, oracle_matches=${validate.oracle_matches}, aliases_all_resolve=${validate.aliases_all_resolve}) and codex=ALIASES-SAFE (${gate.verdict}). Else commit nothing, report blocker.
1. Stage only src/ + scripts/ + tests/ changes (NOT the overlaid tests/oracle/*). Grep-check no secret.
2. Append to docs/review_readiness/phase2_renames_applied.md: the NEEDS-ALIAS batch — applied count, aliases added, skipped (source-grep/conflicting) for human review, gates passed.
3. Commit ("Phase 2: NEEDS-ALIAS renames with backward-compat aliases (score-safe, oracle-validated)") with trailers:
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TLpJSqNfJVSP1UGdtk89nA
4. Push (updates PR #1384): 'cd ${WT} && git push'.
Return {commit_sha, pushed, committed_or_blocked}.`,
  { label: 'record', phase: 'Record', schema: { type:'object', additionalProperties:false, required:['commit_sha','pushed','committed_or_blocked'], properties:{ commit_sha:{type:'string'}, pushed:{type:'boolean'}, committed_or_blocked:{type:'string'} } } })

return { setup: { count: setup.count, baseline: setup.baseline }, aliased, validate, gate, record: rec }
