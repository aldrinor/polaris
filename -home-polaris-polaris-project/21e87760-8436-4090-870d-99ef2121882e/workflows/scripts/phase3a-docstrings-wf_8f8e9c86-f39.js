export const meta = {
  name: 'phase3a-docstrings',
  description: 'Fill missing docstrings on contract/API files (pure text); prove no logic changed via docstring-stripped AST equivalence + oracle SHA unchanged',
  phases: [
    { title: 'Setup', detail: 'worktree + identify contract/API files with missing docstrings + baseline' },
    { title: 'Document', detail: 'add docstrings (no logic changes)' },
    { title: 'Validate', detail: 'docstring-stripped AST identical + oracle SHA unchanged + collection unchanged' },
    { title: 'Codex-Gate', detail: 'codex confirms only docstrings/comments changed' },
    { title: 'Record', detail: 'commit + push + PR' },
  ],
}
const PY = '/home/polaris/pipeline-env/bin/python'
const GOLDEN = '9c0a3d438da943242c98e2fe714494c342d42d02102202d75a61a4554339db98'
const WT = '/home/polaris/wt/phase3a'

phase('Setup')
const setup = await agent(
  `Set up Phase 3A (docstrings) for a research pipeline.
1. cd /workspace/POLARIS && git worktree remove ${WT} --force 2>/dev/null; git branch -D chore/review-readiness-phase3a 2>/dev/null; git worktree add ${WT} -b chore/review-readiness-phase3a chore/review-readiness-phase1.
2. Overlay oracle: cd ${WT} && git checkout chore/review-readiness-phase0 -- tests/oracle/ 2>/dev/null; cp -n /home/polaris/wt/phase0/tests/oracle/cassettes/*.jsonl /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_golden.json ${WT}/tests/oracle/cassettes/ 2>/dev/null.
3. Identify the CONTRACT/API files a reviewer cares about most that have MISSING docstrings: focus on src/polaris_graph/api/**, public interface modules, contracts/schema modules, and the main entrypoints. Use a script to find public functions/classes/modules WITHOUT a docstring (ast.get_docstring is None) in those priority areas. Rank by importance (API routes + public contracts first). Report the top ~40-60 highest-value targets (file + symbol) — do NOT try to do all ~530 at once; a focused, high-quality first batch on the contract/API surface is the deliverable.
4. Baseline: '${PY} -m pytest tests/ --collect-only -q 2>&1 | tail -1' (expect 16738/11).
Return the prioritized target list (file:symbol) + counts + baseline.`,
  { label: 'setup', phase: 'Setup', schema: { type:'object', additionalProperties:false, required:['targets','target_count','baseline'], properties:{ targets:{type:'array',items:{type:'object',additionalProperties:true}}, target_count:{type:'integer'}, baseline:{type:'string'} } } })

phase('Document')
const doc = await agent(
  `Add high-quality docstrings to the missing-docstring targets in ${WT}. Targets: ${JSON.stringify(setup.targets)}.
RULES (hard):
1. Add ONLY docstrings (module/class/function) and, where genuinely helpful, brief comments. Change NO logic — no renamed vars, no reordered statements, no changed signatures, no new imports (except 'from __future__ import annotations' is forbidden too — add nothing executable).
2. Each docstring: one-line summary + (for functions) Args/Returns/Raises where non-obvious; describe the CONTRACT (what it guarantees), not the implementation line-by-line. Match the house style of existing docstrings in the file.
3. A docstring is the FIRST statement in the def/class/module body — insert it there, correctly indented. Do not displace an existing docstring; only fill MISSING ones.
Work through the batch; after every ~15 files run '${PY} -m pytest tests/ --collect-only -q | tail -1' and keep it at baseline (${setup.baseline}). py_compile each changed file; revert any that fail.
Return: how many docstrings added across how many files, and confirm no logic was changed.`,
  { label: 'document', phase: 'Document', schema: { type:'object', additionalProperties:false, required:['docstrings_added','files_changed','collection_after','logic_unchanged_claim'], properties:{ docstrings_added:{type:'integer'}, files_changed:{type:'integer'}, collection_after:{type:'string'}, logic_unchanged_claim:{type:'boolean'} } } })

phase('Validate')
const validate = await agent(
  `Validate the Phase 3A docstring changes in ${WT} changed ONLY docstrings — no logic.
1. DOCSTRING-STRIPPED AST EQUIVALENCE (the key proof): for every changed .py file, compare git HEAD version vs working version with all docstrings stripped. Write a script that, for each changed file: parses both versions with ast, removes docstrings (the first Expr(Constant str) in every module/class/function body), unparses (ast.unparse), and asserts the stripped sources are IDENTICAL. Any file whose docstring-stripped AST differs = a logic change = FAIL (name it). Report how many files pass this equivalence.
2. Oracle replay: 'cd ${WT} && PG_OUTLINE_AGENT_MAX_TURNS=3 ${PY} tests/oracle/acceptance_portable.py --replay 2>&1 | tail -12' — SHA must equal ${GOLDEN}, controls pass.
3. Collection unchanged: '${PY} -m pytest tests/ --collect-only -q | tail -1' == ${setup.baseline}.
Return: ast_equivalence_all_pass (+ any failing file), oracle SHA + match, collection ok.`,
  { label: 'validate', phase: 'Validate', schema: { type:'object', additionalProperties:false, required:['ast_equivalence_all_pass','ast_failures','oracle_sha','oracle_matches','collection_ok'], properties:{ ast_equivalence_all_pass:{type:'boolean'}, ast_failures:{type:'array',items:{type:'string'}}, oracle_sha:{type:'string'}, oracle_matches:{type:'boolean'}, collection_ok:{type:'boolean'} } } })

phase('Codex-Gate')
const gate = await agent(
  `Run CODEX (GPT-5.6) to gate Phase 3A docstrings. Write /tmp/doc_gate.md then 'cd /tmp && timeout 200 codex exec --skip-git-repo-check - < /tmp/doc_gate.md 2>&1 | tail -25' (embed evidence inline; medium effort; no sandbox flags).
Context: added ${JSON.stringify(doc)} docstrings. Validation: ${JSON.stringify(validate)} — including a docstring-stripped AST-equivalence check across all changed files (identical stripped AST == only docstrings changed) and oracle byte-identical (${GOLDEN}).
Ask codex: "Given every changed file's docstring-stripped AST is identical to HEAD and the oracle replay is byte-identical, is this provably a docstrings-only change (zero logic/behavior change), safe to ship? Any hole in the AST-equivalence argument (e.g., a docstring that is actually load-bearing — used as __doc__ at runtime by help()/argparse/pydantic)? End with: DOCS-SAFE or DOCS-REVISE."
Return verdict + points.`,
  { label: 'codex-gate', phase: 'Codex-Gate', schema: { type:'object', additionalProperties:false, required:['verdict','codex_points'], properties:{ verdict:{type:'string'}, codex_points:{type:'array',items:{type:'string'}} } } })

phase('Record')
const rec = await agent(
  `Record Phase 3A. Worktree ${WT} (branch chore/review-readiness-phase3a).
Only commit if validate passed (ast_equivalence_all_pass=${validate.ast_equivalence_all_pass}, oracle_matches=${validate.oracle_matches}, collection_ok=${validate.collection_ok}) and codex=DOCS-SAFE (${gate.verdict}). Else commit nothing, report blocker.
1. Stage src/ docstring changes (NOT the overlaid tests/oracle/*). Grep-check no secret.
2. Write docs/review_readiness/phase3a_docstrings.md: how many docstrings added on which contract/API areas, the AST-equivalence proof, oracle SHA, codex verdict.
3. Commit ("Phase 3A: fill contract/API docstrings (docstrings-only, AST-equivalent, oracle byte-identical)") with trailers:
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TLpJSqNfJVSP1UGdtk89nA
4. Push -u origin; open PR base gate-inversion: '/home/polaris/.local/bin/gh pr create --repo aldrinor/deep-cove-research --base gate-inversion --head chore/review-readiness-phase3a --title "Code-review readiness: Phase 3A contract/API docstrings" --body "Docstrings-only fill on the contract/API surface; docstring-stripped ASTs identical to HEAD (zero logic change), oracle replay byte-identical 9c0a3d43, codex DOCS-SAFE. 🤖 Generated with [Claude Code](https://claude.com/claude-code)"'.
Return {commit_sha, pushed, pr_url, committed_or_blocked}.`,
  { label: 'record', phase: 'Record', schema: { type:'object', additionalProperties:false, required:['commit_sha','pushed','pr_url','committed_or_blocked'], properties:{ commit_sha:{type:'string'}, pushed:{type:'boolean'}, pr_url:{type:'string'}, committed_or_blocked:{type:'string'} } } })

return { setup: { target_count: setup.target_count }, doc, validate, gate, record: rec }
