export const meta = {
  name: 'phase3a-docstrings-b2',
  description: 'Phase 3A batch 2: next ~50 contract/API/public docstrings, inline __doc__-audit, AST-equivalence + oracle gated, overlay-safe Record',
  phases: [
    { title: 'Setup', detail: 'branch from batch1 + cp oracle overlay (untracked) + find next targets' },
    { title: 'Document', detail: 'add docstrings, avoiding load-bearing __doc__ symbols' },
    { title: 'Validate', detail: 'AST-equivalence + __doc__-audit + oracle SHA + collection' },
    { title: 'Codex-Gate', detail: 'codex DOCS-SAFE' },
    { title: 'Record', detail: 'stage explicit src/ paths only; commit + push + PR' },
  ],
}
const PY = '/home/polaris/pipeline-env/bin/python'
const GOLDEN = '9c0a3d438da943242c98e2fe714494c342d42d02102202d75a61a4554339db98'
const WT = '/home/polaris/wt/phase3ab2'

phase('Setup')
const setup = await agent(
  `Set up Phase 3A docstrings batch 2 (batch 1 = 62 docstrings already shipped on chore/review-readiness-phase3a).
1. cd /workspace/POLARIS && git worktree remove ${WT} --force 2>/dev/null; git branch -D chore/review-readiness-phase3a-b2 2>/dev/null; git worktree add ${WT} -b chore/review-readiness-phase3a-b2 chore/review-readiness-phase3a  (builds on batch 1).
2. OVERLAY the oracle by COPY (not git checkout — copy keeps them UNTRACKED so they can never be accidentally staged/committed): mkdir -p ${WT}/tests/oracle/cassettes; cp /home/polaris/wt/phase0/tests/oracle/*.py ${WT}/tests/oracle/ 2>/dev/null; cp /home/polaris/wt/phase0/tests/oracle/cassettes/* ${WT}/tests/oracle/cassettes/ 2>/dev/null; ls ${WT}/tests/oracle/cassettes/. Confirm 'git status --short tests/oracle | head' shows them as untracked (??), NOT staged.
3. Find the NEXT ~50 highest-value public functions/classes/modules WITHOUT a docstring (ast.get_docstring is None), EXCLUDING the files batch 1 already documented. Prioritize: remaining src/polaris_v6/** and src/polaris_graph/api/**, then public contract/schema/orchestration modules (graph.py, honest_pipeline.py public funcs, retrieval public API). Skip private (_-prefixed) unless they're a key public contract.
4. Baseline: '${PY} -m pytest tests/ --collect-only -q 2>&1 | tail -1' (expect 16738/11).
Return the prioritized targets (file:symbol), count, and baseline. Confirm tests/oracle is UNTRACKED.`,
  { label: 'setup', phase: 'Setup', schema: { type:'object', additionalProperties:false, required:['targets','target_count','baseline','oracle_untracked'], properties:{ targets:{type:'array',items:{type:'object',additionalProperties:true}}, target_count:{type:'integer'}, baseline:{type:'string'}, oracle_untracked:{type:'boolean'} } } })

phase('Document')
const doc = await agent(
  `Add high-quality docstrings to the batch-2 targets in ${WT}. Targets: ${JSON.stringify(setup.targets)}.
RULES (hard): add ONLY docstrings (module/class/function first statement) — change NO logic, no signatures, no imports. Match house style: one-line summary + Args/Returns/Raises where non-obvious; describe the CONTRACT not the implementation. Make Raises/return-shape claims ACCURATE against the actual code (verify the guard/return before documenting it — a docstring that mis-states behavior is a defect).
INLINE __doc__-SAFETY: as you go, if a target symbol's __doc__ is consumed at runtime (pydantic/FastAPI schema description, argparse/click/typer help, doctest, inspect.getdoc, or a test asserting __doc__), SKIP it (don't add a docstring there) and note it — do not create a load-bearing docstring.
After every ~15 files: '${PY} -m pytest tests/ --collect-only -q | tail -1' must stay at ${setup.baseline}; py_compile each changed file, revert failures.
Return docstrings_added, files_changed, skipped_loadbearing (list), collection_after, and confirm all Raises/return claims verified accurate.`,
  { label: 'document', phase: 'Document', schema: { type:'object', additionalProperties:false, required:['docstrings_added','files_changed','skipped_loadbearing','collection_after','claims_accurate'], properties:{ docstrings_added:{type:'integer'}, files_changed:{type:'integer'}, skipped_loadbearing:{type:'array',items:{type:'string'}}, collection_after:{type:'string'}, claims_accurate:{type:'boolean'} } } })

phase('Validate')
const validate = await agent(
  `Validate batch-2 docstrings in ${WT} are docstrings-only + accurate + score-safe.
1. DOCSTRING-STRIPPED AST EQUIVALENCE across all changed src/ files (parse HEAD vs working, strip docstrings, ast.unparse, assert identical). Report pass + any failure (a failure = logic change).
2. __doc__-CONSUMER AUDIT: for every symbol that got a docstring, grep for a runtime __doc__ consumer; confirm 0 load-bearing (or that the Document phase already skipped them).
3. Oracle replay: 'cd ${WT} && PG_OUTLINE_AGENT_MAX_TURNS=3 ${PY} tests/oracle/acceptance_portable.py --replay 2>&1 | tail -12' — SHA==${GOLDEN}, controls pass.
4. Collection == ${setup.baseline}.
Return ast_equivalence_all_pass (+failures), no_loadbearing_confirmed, oracle_matches, oracle_sha, collection_ok.`,
  { label: 'validate', phase: 'Validate', schema: { type:'object', additionalProperties:false, required:['ast_equivalence_all_pass','ast_failures','no_loadbearing_confirmed','oracle_matches','oracle_sha','collection_ok'], properties:{ ast_equivalence_all_pass:{type:'boolean'}, ast_failures:{type:'array',items:{type:'string'}}, no_loadbearing_confirmed:{type:'boolean'}, oracle_matches:{type:'boolean'}, oracle_sha:{type:'string'}, collection_ok:{type:'boolean'} } } })

phase('Codex-Gate')
const gate = await agent(
  `Run CODEX (GPT-5.6) to gate Phase 3A batch-2 docstrings. Write /tmp/doc_b2_gate.md then 'cd /tmp && timeout 200 codex exec --skip-git-repo-check - < /tmp/doc_b2_gate.md 2>&1 | tail -25' (embed inline; medium effort; no sandbox flags).
Evidence: doc=${JSON.stringify(doc)}; validate=${JSON.stringify(validate)}. Claims: docstring-stripped ASTs identical to HEAD (docstrings-only), per-symbol __doc__-audit finds no load-bearing docstring, oracle replay byte-identical (${GOLDEN}), all Raises/return claims verified accurate.
Ask codex: "Is this a provably zero-behavior-change docstrings-only batch, safe to ship? Any inaccurate Raises/return-shape claim, or any load-bearing __doc__ among those added? End with DOCS-SAFE or DOCS-REVISE (+ the one blocking item if REVISE)."
Return verdict + points.`,
  { label: 'codex-gate', phase: 'Codex-Gate', schema: { type:'object', additionalProperties:false, required:['verdict','codex_points'], properties:{ verdict:{type:'string'}, codex_points:{type:'array',items:{type:'string'}} } } })

phase('Record')
const rec = await agent(
  `Record Phase 3A batch 2. Worktree ${WT} (branch chore/review-readiness-phase3a-b2).
Only commit if validate passed (ast_equivalence_all_pass=${validate.ast_equivalence_all_pass}, oracle_matches=${validate.oracle_matches}, collection_ok=${validate.collection_ok}, no_loadbearing_confirmed=${validate.no_loadbearing_confirmed}) and codex=DOCS-SAFE (${gate.verdict}). Else commit nothing, report blocker.
CRITICAL (avoid the batch-1 overlay-bundling defect): stage with EXPLICIT PATHS ONLY. Run 'git add src/' then 'git add docs/review_readiness/phase3a_docstrings_b2.md'. Then RUN A GUARD: 'git diff --cached --name-only | grep -c "tests/oracle"' MUST be 0 — if not, 'git restore --staged tests/oracle/' and re-check. Never 'git add .' or 'git add -A'. Grep-check no secret in staged.
1. Write docs/review_readiness/phase3a_docstrings_b2.md summarizing batch 2 (count, files, the AST/__doc__/oracle proofs, any skipped load-bearing, codex verdict).
2. Commit ("Phase 3A batch 2: fill contract/API/public docstrings (docstrings-only, AST-equivalent, oracle byte-identical)") with trailers:
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TLpJSqNfJVSP1UGdtk89nA
3. Push -u origin; PR base gate-inversion: '/home/polaris/.local/bin/gh pr create --repo aldrinor/deep-cove-research --base gate-inversion --head chore/review-readiness-phase3a-b2 --title "Code-review readiness: Phase 3A docstrings batch 2" --body "Next batch of contract/API/public docstrings. Docstrings-only (docstring-stripped ASTs identical to HEAD), no load-bearing __doc__ (audited), oracle byte-identical 9c0a3d43, codex DOCS-SAFE. Builds on batch 1 (PR #1386). 🤖 Generated with [Claude Code](https://claude.com/claude-code)"'.
Return {commit_sha, pushed, pr_url, committed_or_blocked, oracle_files_staged}.`,
  { label: 'record', phase: 'Record', schema: { type:'object', additionalProperties:false, required:['commit_sha','pushed','pr_url','committed_or_blocked','oracle_files_staged'], properties:{ commit_sha:{type:'string'}, pushed:{type:'boolean'}, pr_url:{type:'string'}, committed_or_blocked:{type:'string'}, oracle_files_staged:{type:'integer'} } } })

return { setup: { target_count: setup.target_count, oracle_untracked: setup.oracle_untracked }, doc, validate, gate, record: rec }
