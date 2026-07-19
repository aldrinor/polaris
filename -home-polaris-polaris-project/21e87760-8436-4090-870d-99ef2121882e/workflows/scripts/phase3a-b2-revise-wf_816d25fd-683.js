export const meta = {
  name: 'phase3a-b2-revise',
  description: 'Close batch-2 DOCS-REVISE: dedicated independent exhaustive __doc__-consumer audit + independent Raises/return-shape verification, then ship',
  phases: [
    { title: 'IndependentAudit', detail: 'exhaustive __doc__-consumer sweep + independent accuracy check per claim; revert any load-bearing/inaccurate' },
    { title: 'Validate', detail: 'AST-equivalence + oracle SHA + collection' },
    { title: 'Codex-Gate', detail: 'codex DOCS-SAFE' },
    { title: 'Record', detail: 'overlay-safe explicit-path commit + PR' },
  ],
}
const PY = '/home/polaris/pipeline-env/bin/python'
const GOLDEN = '9c0a3d438da943242c98e2fe714494c342d42d02102202d75a61a4554339db98'
const WT = '/home/polaris/wt/phase3ab2'   // 51 docstrings across 14 files, held back (uncommitted)

phase('IndependentAudit')
const audit = await agent(
  `In ${WT} (branch chore/review-readiness-phase3a-b2) there are 51 newly-added docstrings across ~14 files (uncommitted, held back after codex DOCS-REVISE). Codex's blocking item: an EXHAUSTIVE INDEPENDENT audit of dynamic/unexercised __doc__ consumers AND independent validation of every Raises:/return-shape docstring claim — not agent self-report.
Do BOTH rigorously and show your work:
A) __doc__-CONSUMER SWEEP (exhaustive, repo-wide, not just changed files): grep the ENTIRE repo (src/, scripts/, tests/, web/) for every pattern that could read a docstring at runtime: '.__doc__', 'getattr(*, "__doc__"', 'inspect.getdoc', 'pydoc', 'help(', doctest usage ('>>>' in the ADDED docstrings, 'doctest' config in pytest.ini/setup.cfg/pyproject/conftest), pydantic (does any changed CLASS subclass BaseModel and could its docstring become a schema description?), FastAPI (is any changed FUNCTION a route handler whose docstring feeds OpenAPI?), click/typer/argparse (docstring -> help). For EACH of the 51 docstringed symbols, state whether ANY consumer reads its __doc__. If yes for any -> REVERT that docstring and record it.
B) ACCURACY RE-VERIFICATION (independent): for EVERY docstring that makes a behavioral claim (Raises: X, returns shape Y, "returns None when..."), open the actual function body and CONFIRM the claim matches the code (the exception is actually raised on that condition; the return shape/type matches). For any claim that does NOT match the code -> either correct the docstring to match, or REVERT it. List each claim checked + verdict.
After any reverts: py_compile + collection at baseline (16738/11).
Return: kept, reverted (with reasons), the __doc__-sweep result (patterns searched + count found), the per-claim accuracy table (claim -> matches code?), and an explicit statement that every kept docstring is (1) non-load-bearing and (2) accurate.`,
  { label: 'independent-audit', phase: 'IndependentAudit', schema: { type:'object', additionalProperties:false, required:['kept','reverted','reverted_detail','doc_consumers_found','claims_verified','all_accurate_and_inert','collection'], properties:{ kept:{type:'integer'}, reverted:{type:'integer'}, reverted_detail:{type:'array',items:{type:'string'}}, doc_consumers_found:{type:'integer'}, claims_verified:{type:'integer'}, all_accurate_and_inert:{type:'boolean'}, collection:{type:'string'} } } })

phase('Validate')
const validate = await agent(
  `Re-validate the batch-2 docstrings in ${WT} after the independent audit.
1. Ensure oracle overlay present by COPY (untracked): cp -n /home/polaris/wt/phase0/tests/oracle/*.py ${WT}/tests/oracle/ 2>/dev/null; cp -n /home/polaris/wt/phase0/tests/oracle/cassettes/* ${WT}/tests/oracle/cassettes/ 2>/dev/null.
2. DOCSTRING-STRIPPED AST EQUIVALENCE across all changed src/ files (strip docstrings, ast.unparse, assert identical to HEAD). Report pass + failures.
3. Oracle replay: 'cd ${WT} && PG_OUTLINE_AGENT_MAX_TURNS=3 ${PY} tests/oracle/acceptance_portable.py --replay 2>&1 | tail -12' — SHA==${GOLDEN}, controls pass.
4. Collection == 16738/11.
Return ast_equivalence_all_pass (+failures), oracle_matches, oracle_sha, collection_ok.`,
  { label: 'validate', phase: 'Validate', schema: { type:'object', additionalProperties:false, required:['ast_equivalence_all_pass','ast_failures','oracle_matches','oracle_sha','collection_ok'], properties:{ ast_equivalence_all_pass:{type:'boolean'}, ast_failures:{type:'array',items:{type:'string'}}, oracle_matches:{type:'boolean'}, oracle_sha:{type:'string'}, collection_ok:{type:'boolean'} } } })

phase('Codex-Gate')
const gate = await agent(
  `Run CODEX (GPT-5.6) to re-gate batch-2 docstrings after the dedicated independent audit. Write /tmp/b2_regate.md then 'cd /tmp && timeout 200 codex exec --skip-git-repo-check - < /tmp/b2_regate.md 2>&1 | tail -25' (embed inline; medium effort; no sandbox flags).
Prior verdict DOCS-REVISE demanded: (1) exhaustive INDEPENDENT __doc__-consumer audit, (2) independent Raises/return-shape validation. Now provided:
- Independent audit: ${JSON.stringify(audit)}
- Validation: ${JSON.stringify(validate)} (docstring-stripped ASTs identical + oracle byte-identical)
Give codex the audit's __doc__-sweep result (patterns searched, 0 consumers) and the per-claim accuracy table. Ask: "The independent exhaustive __doc__-consumer sweep found ${audit.doc_consumers_found} consumers among the kept docstrings, every behavioral claim was independently checked against code (${audit.claims_verified} verified), AST is docstring-only, oracle byte-identical. Is this now provably safe to ship? End with DOCS-SAFE or DOCS-REVISE (+ the one remaining item if REVISE)."
Return verdict + points.`,
  { label: 'codex-gate', phase: 'Codex-Gate', schema: { type:'object', additionalProperties:false, required:['verdict','codex_points'], properties:{ verdict:{type:'string'}, codex_points:{type:'array',items:{type:'string'}} } } })

phase('Record')
const rec = await agent(
  `Record batch-2 docstrings. Worktree ${WT} (branch chore/review-readiness-phase3a-b2).
Only commit if validate passed (ast_equivalence_all_pass=${validate.ast_equivalence_all_pass}, oracle_matches=${validate.oracle_matches}, collection_ok=${validate.collection_ok}) and codex=DOCS-SAFE (${gate.verdict}). Else commit nothing, report blocker.
OVERLAY-SAFE STAGING (mandatory): stage EXPLICIT paths only — 'git add src/' then 'git add docs/review_readiness/phase3a_docstrings_b2.md'. GUARD: 'git diff --cached --name-only | grep -c "tests/oracle"' MUST be 0; if not, 'git restore --staged tests/oracle/' and recheck. Never 'git add .'/'git add -A'. No-secret grep.
1. Write docs/review_readiness/phase3a_docstrings_b2.md (count kept, any reverted, the independent __doc__-sweep + accuracy table summary, AST + oracle proof, codex verdict).
2. Commit ("Phase 3A batch 2: contract/API/public docstrings (independent __doc__-audit + accuracy-verified, AST-equivalent, oracle byte-identical)") with trailers:
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TLpJSqNfJVSP1UGdtk89nA
3. Push -u origin; PR base gate-inversion: '/home/polaris/.local/bin/gh pr create --repo aldrinor/deep-cove-research --base gate-inversion --head chore/review-readiness-phase3a-b2 --title "Code-review readiness: Phase 3A docstrings batch 2" --body "Next batch of contract/API/public docstrings. Independent exhaustive __doc__-consumer audit (0 load-bearing) + per-claim accuracy verification, docstring-stripped ASTs identical to HEAD, oracle byte-identical 9c0a3d43, codex DOCS-SAFE. 🤖 Generated with [Claude Code](https://claude.com/claude-code)"'.
Return {commit_sha, pushed, pr_url, committed_or_blocked, oracle_files_staged}.`,
  { label: 'record', phase: 'Record', schema: { type:'object', additionalProperties:false, required:['commit_sha','pushed','pr_url','committed_or_blocked','oracle_files_staged'], properties:{ commit_sha:{type:'string'}, pushed:{type:'boolean'}, pr_url:{type:'string'}, committed_or_blocked:{type:'string'}, oracle_files_staged:{type:'integer'} } } })

return { audit, validate, gate, record: rec }
