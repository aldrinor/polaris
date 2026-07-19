export const meta = {
  name: 'phase3a-docstrings-revise',
  description: 'Close codex DOCS-REVISE: prove none of the added docstrings are load-bearing via __doc__ (argparse/pydantic/doctest/getdoc), then ship',
  phases: [
    { title: 'DocSafety', detail: 'check each docstringed symbol for a runtime __doc__ consumer; revert any that are load-bearing' },
    { title: 'Validate', detail: 'AST-equivalence + oracle SHA + collection unchanged' },
    { title: 'Codex-Gate', detail: 'codex confirms docstrings-only AND no __doc__ consumer' },
    { title: 'Record', detail: 'commit + push + PR' },
  ],
}
const PY = '/home/polaris/pipeline-env/bin/python'
const GOLDEN = '9c0a3d438da943242c98e2fe714494c342d42d02102202d75a61a4554339db98'
const WT = '/home/polaris/wt/phase3a'   // docstring work already in tree (21 files, held back)

phase('DocSafety')
const safety = await agent(
  `In ${WT} (branch chore/review-readiness-phase3a) there are ~21 files with newly-ADDED docstrings (uncommitted, held back after codex DOCS-REVISE). Codex's concern: a docstring can be load-bearing at runtime via __doc__ (argparse/click/typer help built from __doc__, pydantic/FastAPI schema descriptions, doctest, inspect.getdoc(), or code asserting __doc__ is None). Prove none of the added docstrings are load-bearing, or revert the ones that are.
1. From 'git diff' in ${WT}, enumerate every symbol (module/class/function) that received a NEW docstring.
2. For EACH, check for a runtime __doc__ consumer:
   - grep the repo for '<symbol>.__doc__', 'getdoc(<symbol>', 'inspect.getdoc'; 
   - is the symbol a pydantic BaseModel / Field / a FastAPI route handler (docstring -> OpenAPI description)? a click/typer command or argparse (docstring -> --help)? 
   - does the new docstring contain a doctest ('>>>')? (it should not — if any does, that's a new collected test.)
   - does any test assert the symbol's __doc__ is None / empty, or assert an exact schema/help string?
3. For any docstring that IS load-bearing (a real __doc__ consumer whose output a test or contract depends on): REVERT just that one docstring (restore the file's HEAD version for that symbol) and record it as deferred.
4. Re-confirm py_compile + collection at baseline (16738/11) after any reverts.
Return: total docstrings kept, how many reverted (with which symbols + why), and an explicit statement that every KEPT docstring has NO behavior-affecting __doc__ consumer (with the evidence: grep found none / consumer exists but no test/contract depends on the text).`,
  { label: 'doc-safety', phase: 'DocSafety', schema: { type:'object', additionalProperties:false, required:['kept','reverted','reverted_detail','no_loadbearing_doc_confirmed','collection'], properties:{ kept:{type:'integer'}, reverted:{type:'integer'}, reverted_detail:{type:'array',items:{type:'string'}}, no_loadbearing_doc_confirmed:{type:'boolean'}, collection:{type:'string'} } } })

phase('Validate')
const validate = await agent(
  `Re-validate the docstring batch in ${WT} after the __doc__-safety pass.
1. Ensure oracle overlay present (cp -n /home/polaris/wt/phase0/tests/oracle/cassettes/*.jsonl /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_golden.json ${WT}/tests/oracle/cassettes/ 2>/dev/null).
2. DOCSTRING-STRIPPED AST EQUIVALENCE across all changed src/ files (parse HEAD vs working, strip docstrings, ast.unparse, assert identical) — report pass + any failure.
3. Oracle replay: 'cd ${WT} && PG_OUTLINE_AGENT_MAX_TURNS=3 ${PY} tests/oracle/acceptance_portable.py --replay 2>&1 | tail -12' — SHA==${GOLDEN}, controls pass.
4. Collection: '${PY} -m pytest tests/ --collect-only -q | tail -1' == 16738/11.
Return ast_equivalence_all_pass (+ failures), oracle sha + match, collection ok.`,
  { label: 'validate', phase: 'Validate', schema: { type:'object', additionalProperties:false, required:['ast_equivalence_all_pass','ast_failures','oracle_matches','oracle_sha','collection_ok'], properties:{ ast_equivalence_all_pass:{type:'boolean'}, ast_failures:{type:'array',items:{type:'string'}}, oracle_matches:{type:'boolean'}, oracle_sha:{type:'string'}, collection_ok:{type:'boolean'} } } })

phase('Codex-Gate')
const gate = await agent(
  `Run CODEX (GPT-5.6) to re-gate Phase 3A docstrings after the __doc__-safety pass. Write /tmp/doc_regate.md then 'cd /tmp && timeout 200 codex exec --skip-git-repo-check - < /tmp/doc_regate.md 2>&1 | tail -25' (embed inline; medium effort; no sandbox flags).
Prior verdict was DOCS-REVISE because __doc__ could be load-bearing (argparse/pydantic/doctest/getdoc) and that wasn't proven absent. Now: DocSafety pass = ${JSON.stringify(safety)}. Validation = ${JSON.stringify(validate)} (docstring-stripped ASTs identical + oracle byte-identical).
Ask codex: "Every changed file's docstring-stripped AST is identical to HEAD (source-level docstrings-only), the oracle replay is byte-identical, AND a per-symbol __doc__-consumer audit found no load-bearing docstring among those kept (load-bearing ones were reverted). Is this now provably a zero-behavior-change docs batch, safe to ship? End with: DOCS-SAFE or DOCS-REVISE (and the one remaining hole if REVISE)."
Return verdict + points.`,
  { label: 'codex-gate', phase: 'Codex-Gate', schema: { type:'object', additionalProperties:false, required:['verdict','codex_points'], properties:{ verdict:{type:'string'}, codex_points:{type:'array',items:{type:'string'}} } } })

phase('Record')
const rec = await agent(
  `Record Phase 3A docstrings. Worktree ${WT} (branch chore/review-readiness-phase3a).
Only commit if validate passed (ast_equivalence_all_pass=${validate.ast_equivalence_all_pass}, oracle_matches=${validate.oracle_matches}, collection_ok=${validate.collection_ok}) and codex=DOCS-SAFE (${gate.verdict}). Else commit nothing, report blocker.
1. Stage src/ docstring changes only (NOT tests/oracle/*). Grep-check no secret.
2. Write docs/review_readiness/phase3a_docstrings.md: docstrings kept (${safety.kept}), any reverted as load-bearing (${JSON.stringify(safety.reverted_detail)}), the AST-equivalence + __doc__-audit + oracle proof, codex verdict.
3. Commit ("Phase 3A: fill contract/API docstrings (docstrings-only, no load-bearing __doc__, oracle byte-identical)") with trailers:
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TLpJSqNfJVSP1UGdtk89nA
4. Push -u origin; PR base gate-inversion: '/home/polaris/.local/bin/gh pr create --repo aldrinor/deep-cove-research --base gate-inversion --head chore/review-readiness-phase3a --title "Code-review readiness: Phase 3A contract/API docstrings" --body "Docstrings-only on the contract/API surface; docstring-stripped ASTs identical to HEAD, no load-bearing __doc__ consumers (audited per-symbol), oracle replay byte-identical 9c0a3d43, codex DOCS-SAFE. 🤖 Generated with [Claude Code](https://claude.com/claude-code)"'.
Return {commit_sha, pushed, pr_url, committed_or_blocked}.`,
  { label: 'record', phase: 'Record', schema: { type:'object', additionalProperties:false, required:['commit_sha','pushed','pr_url','committed_or_blocked'], properties:{ commit_sha:{type:'string'}, pushed:{type:'boolean'}, pr_url:{type:'string'}, committed_or_blocked:{type:'string'} } } })

return { safety, validate, gate, record: rec }
