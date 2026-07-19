export const meta = {
  name: 'codex-q1-graphfork-freeze',
  description: 'Execute codex Q1: freeze the 3-way graph fork + usage inventory + ResearchStateV2 note + deprecation notice + removal-gates spec (NO deletion, NO behavior change)',
  phases: [
    { title: 'Inventory', detail: 'map PG_GRAPH_VERSION selectors + usage + external consumers' },
    { title: 'Document', detail: 'freeze/deprecation doc + removal-gates checklist' },
    { title: 'Verify', detail: 'collection + oracle unchanged (pure doc)' },
    { title: 'Codex-Gate', detail: 'codex confirms this is the correct 3C-for-review deliverable' },
    { title: 'Record', detail: 'commit + push + PR' },
  ],
}
const PY = '/home/polaris/pipeline-env/bin/python'
const GOLDEN = '9c0a3d438da943242c98e2fe714494c342d42d02102202d75a61a4554339db98'
const WT = '/home/polaris/wt/phase-q1'

phase('Inventory')
const inv = await agent(
  `Execute codex's Q1 decision: FREEZE + DOCUMENT the live 3-way graph fork (graph.py / graph_v2.py / graph_v3.py, selected by PG_GRAPH_VERSION) — do NOT delete anything, do NOT change any behavior. Pure inventory + docs.
1. cd /workspace/POLARIS && git worktree remove ${WT} --force 2>/dev/null; git branch -D chore/review-readiness-q1 2>/dev/null; git worktree add ${WT} -b chore/review-readiness-q1 chore/review-readiness-phase1.
2. Force-copy phase0 harness (unstaged): cp /home/polaris/wt/phase0/tests/oracle/*.py ${WT}/tests/oracle/ ; cp /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_golden.json /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_llm.jsonl /home/polaris/wt/phase0/tests/oracle/cassettes/acceptance_retrieval.jsonl ${WT}/tests/oracle/cassettes/.
3. INVENTORY (grep/read, no edits): (a) find the selector — where PG_GRAPH_VERSION is read + how it routes to graph.py/graph_v2/graph_v3 (likely src/polaris_graph/__init__.py); (b) the valid selector values (v1/v2/v3 / default / unset / invalid — what each does); (c) which graph is the DEFAULT/production one; (d) ResearchStateV2 (and any V3State) saved-state schema — where persisted; (e) real usage: grep prod/CI/scripts/docs for PG_GRAPH_VERSION and v2/v3 use — is any non-default selector actually used anywhere?; (f) external consumers of graph_v2/v3 symbols.
Return: selector_location, valid_values (list), default_version, state_classes (list), nondefault_usage_found (bool + where), notes. baseline collection 16738/11.`,
  { label: 'inventory', phase: 'Inventory', schema: { type:'object', additionalProperties:false, required:['selector_location','valid_values','default_version','state_classes','nondefault_usage_found','baseline','notes'], properties:{ selector_location:{type:'string'}, valid_values:{type:'array',items:{type:'string'}}, default_version:{type:'string'}, state_classes:{type:'array',items:{type:'string'}}, nondefault_usage_found:{type:'boolean'}, baseline:{type:'string'}, notes:{type:'string'} } } })

phase('Document')
const doc = await agent(
  `Write the graph-fork FREEZE + REMOVAL-GATES doc in ${WT} at docs/review_readiness/graph_fork_3c.md. Inventory: ${JSON.stringify(inv)}. NO code changes.
Content:
1. STATUS: the 3-way graph fork (graph.py/graph_v2/graph_v3 via PG_GRAPH_VERSION) is FROZEN for this review — documented, not deleted. Default = ${inv.default_version}; selectors = ${JSON.stringify(inv.valid_values)}.
2. USAGE INVENTORY: which selector is production, whether any non-default (v2/v3) is used anywhere (${inv.nondefault_usage_found}), the state classes ${JSON.stringify(inv.state_classes)}.
3. DEPRECATION NOTICE: mark the non-default forks deprecated; state removal is a SEPARATE owner-driven project (codex Q1 decision).
4. REMOVAL GATES (must ALL pass before any graph*.py deletion — codex-specified): (a) a full-graph deterministic oracle covering EVERY PG_GRAPH_VERSION selector incl. unset/invalid; (b) byte-identical RACE + faithfulness across repeated replays per selector; (c) ResearchStateV2/V3State saved-state migration + resume fixtures; (d) external-consumer/deployment inventory incl. env overrides; (e) defined replacement + deprecation window + rollback switch + owner sign-off; (f) shadow/canary replay evidence on representative persisted states.
5. Note the current oracle covers only the outline-agent path, NOT the graph path — hence deletion is out of scope for this review.
Optionally add a one-line deprecation code comment at the selector site (a comment only — no logic change) if it doesn't risk the oracle. Return: doc_path, comment_added (bool), no_runtime_change (bool).`,
  { label: 'document', phase: 'Document', schema: { type:'object', additionalProperties:false, required:['doc_path','comment_added','no_runtime_change'], properties:{ doc_path:{type:'string'}, comment_added:{type:'boolean'}, no_runtime_change:{type:'boolean'} } } })

phase('Verify')
const verify = await agent(
  `Verify Q1 in ${WT}: 1. collection == 16738/11 ('${PY} -m pytest tests/ --collect-only -q | tail -1'). 2. If any code comment was added at the selector site, run oracle 'cd ${WT} && PG_OUTLINE_AGENT_MAX_TURNS=3 ${PY} tests/oracle/acceptance_portable.py --replay 2>&1 | tail -4' SHA==${GOLDEN}; if doc-only, oracle trivially unaffected (still run it to confirm). 3. Confirm git status shows only docs/ (+ at most one comment-only src line). Return collection_ok, oracle_matches, oracle_sha, docs_only.`,
  { label: 'verify', phase: 'Verify', schema: { type:'object', additionalProperties:false, required:['collection_ok','oracle_matches','oracle_sha','docs_only'], properties:{ collection_ok:{type:'boolean'}, oracle_matches:{type:'boolean'}, oracle_sha:{type:'string'}, docs_only:{type:'boolean'} } } })

phase('Codex-Gate')
const gate = await agent(
  `Run CODEX (GPT-5.6) to gate Q1. Write /tmp/q1_gate.md then 'cd /tmp && timeout 180 codex exec --skip-git-repo-check - < /tmp/q1_gate.md 2>&1 | tail -18' (embed inline; medium; no sandbox flags).
Codex's own Q1 decision was: freeze+document+defer-deletion with a removal-gates checklist. Evidence: inventory=${JSON.stringify(inv)}, doc=${JSON.stringify(doc)}, verify=${JSON.stringify(verify)}.
Ask codex: "Does this freeze/inventory/deprecation doc + removal-gates checklist correctly discharge 3C for a code review (fork documented + frozen, deletion deferred with clear gates, no behavior change)? End with Q1-OK or Q1-REVISE."
Return verdict + points.`,
  { label: 'codex-gate', phase: 'Codex-Gate', schema: { type:'object', additionalProperties:false, required:['verdict','codex_points'], properties:{ verdict:{type:'string'}, codex_points:{type:'array',items:{type:'string'}} } } })

phase('Record')
const rec = await agent(
  `Record Q1 in ${WT} (branch chore/review-readiness-q1). Commit if verify passed (collection_ok, oracle_matches) and codex=Q1-OK (${gate.verdict}). Stage explicit 'git add docs/' (+ src/ only if a comment-only line was added); GUARD 'git diff --cached --name-only | grep -c tests/oracle' == 0. Commit ("Phase 3C per codex: freeze + document the graph fork + removal-gates spec (no deletion, no behavior change)") std trailers. Push -u origin; PR base gate-inversion.
Return {commit_sha, pushed, pr_url, committed_or_blocked}.`,
  { label: 'record', phase: 'Record', schema: { type:'object', additionalProperties:false, required:['commit_sha','pushed','pr_url','committed_or_blocked'], properties:{ commit_sha:{type:'string'}, pushed:{type:'boolean'}, pr_url:{type:'string'}, committed_or_blocked:{type:'string'} } } })

return { inv, doc, verify, gate, record: rec }
