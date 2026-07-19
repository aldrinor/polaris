export const meta = {
  name: 'phase0a5-graph-fixtures',
  description: '0A-5: attempt deterministic replay fixtures for each PG_GRAPH_VERSION selector (v4 prod / v3 / v2 / v1) via the cassette machinery; honestly report which pin byte-identical vs which need the deferred 3C effort',
  phases: [
    { title: 'Map', detail: 'entrypoints + fixed inputs per selector + the cassette machinery' },
    { title: 'Pin', detail: 'attempt record+replay byte-identical fixture per selector (start v4 prod)' },
    { title: 'Codex-Gate', detail: 'codex rules whether achieved fixtures satisfy 0A-5 for review' },
    { title: 'Record', detail: 'commit achieved fixtures + honest 0A-5 status doc' },
  ],
}
const PY = '/home/polaris/pipeline-env/bin/python'
const WT = '/home/polaris/wt/phase0a5'

phase('Map')
const map = await agent(
  `Set up Plan V4 0A-5: characterize the PG_GRAPH_VERSION graph selectors as deterministic REPLAY FIXTURES (the "before" for each, precondition for the deferred 3C deletion). Inventory (from #1395): PRODUCTION selector at scripts/live_server.py routes PG_GRAPH_VERSION: v4(default)->pipeline_a_ui_adapter.build_and_run_v4->run_honest_sweep_r3.run_one_query; v3->graph_v3.build_and_run_v3; v2->graph_v2.build_and_run; v1->graph.build_and_run. NO non-default selector is used at runtime anywhere (dormant).
1. cd /workspace/POLARIS && git worktree remove ${WT} --force 2>/dev/null; git branch -D chore/review-readiness-0a5 2>/dev/null; git worktree add ${WT} -b chore/review-readiness-0a5 chore/review-readiness-phase0.  (phase0 has the trustworthy cassette machinery: tests/oracle/cassette.py, llm_cassette.py, retrieval_cassette.py, acceptance_portable.py.)
2. STUDY the existing deterministic-oracle machinery (tests/oracle/*.py) — it pins the OUTLINE-AGENT path by freezing OpenRouterClient.generate/generate_structured + run_live_retrieval and byte-comparing a canonical artifact. Understand how to reuse it for a FULL-GRAPH run.
3. For EACH selector (v4, v3, v2, v1), identify: the entrypoint function + signature, a small FIXED input (reuse the acceptance THIN research question if possible), and every non-determinism source (LLM calls, retrieval/browser, timestamps, RNG) that must be frozen. Assess feasibility of a deterministic byte-identical replay in THIS env (browser is broken: Playwright TargetClosedError; providers cost money; the outline oracle needed 4 non-determinism fixes).
4. Baseline collection.
Return: per-selector {version, entrypoint, fixed_input, nondeterminism_sources, feasibility_estimate}, and the baseline. Be honest about feasibility.`,
  { label: 'map', phase: 'Map', schema: { type:'object', additionalProperties:false, required:['selectors','machinery_reusable','baseline'], properties:{ selectors:{type:'array',items:{type:'object',additionalProperties:true}}, machinery_reusable:{type:'boolean'}, baseline:{type:'string'} } } })

phase('Pin')
const pin = await agent(
  `Attempt to build a DETERMINISTIC replay fixture for each graph selector in ${WT}, reusing the tests/oracle cassette machinery. Selectors: ${JSON.stringify(map.selectors)}.
Strategy per selector (start with v4 = production default, most important): wrap the entrypoint so retrieval is frozen (retrieval_cassette / inject frozen evidence from an existing artifact if a live crawl can't run) and LLM calls are frozen (llm_cassette records generate+generate_structured), then RECORD once + REPLAY twice, byte-comparing a canonical artifact (normalize timestamps/durations/RNG as the outline oracle does). A selector is PINNED if replay is byte-identical across 2+ runs.
Put fixtures under tests/oracle/graph_fixtures/ (e.g. tests/oracle/acceptance_graph.py + per-selector cassettes + goldens).
BE HONEST: if a selector's full pipeline cannot be pinned deterministically in this env (browser/provider/determinism walls), STOP on that selector, record WHY (the specific blocker), and mark it deferred-to-3C — do NOT fake a fixture. Report exactly which selectors achieved a byte-identical replay and which are blocked + why.
Keep collection at baseline. Return: pinned_selectors (list), blocked_selectors (list + reason), fixtures_written (paths), collection_after.`,
  { label: 'pin', phase: 'Pin', schema: { type:'object', additionalProperties:false, required:['pinned_selectors','blocked_selectors','fixtures_written','collection_after','notes'], properties:{ pinned_selectors:{type:'array',items:{type:'string'}}, blocked_selectors:{type:'array',items:{type:'object',additionalProperties:true}}, fixtures_written:{type:'array',items:{type:'string'}}, collection_after:{type:'string'}, notes:{type:'string'} } } })

phase('Codex-Gate')
const gate = await agent(
  `Run CODEX to gate 0A-5. Write /tmp/q0a5_gate.md then 'cd /tmp && timeout 220 codex exec --skip-git-repo-check -c model_reasoning_effort=high - < /tmp/q0a5_gate.md 2>&1 | tail -25' (embed inline; no sandbox flags).
0A-5 = deterministic replay fixtures for each PG_GRAPH_VERSION selector (v4 prod/v3/v2/v1), precondition for the DEFERRED 3C deletion. Map: ${JSON.stringify(map)}. Pin result: ${JSON.stringify(pin)}. Context: no non-default selector is used at runtime (dormant); the full-graph pipeline is much harder to pin deterministically than the already-pinned outline path (broken browser, provider costs).
Ask codex: "Given which selectors were pinned byte-identical vs blocked, does this SATISFY 0A-5 for THIS review (readiness), or is a specific additional selector fixture required now? Is it acceptable that any un-pinnable selector's full fixture rides with the deferred 3C effort (since 3C deletion is owner-deferred and no non-default selector runs in prod)? End with 0A5-SUFFICIENT or 0A5-INSUFFICIENT (+ what's minimally required if insufficient)." Return verdict + points.`,
  { label: 'codex-gate', phase: 'Codex-Gate', schema: { type:'object', additionalProperties:false, required:['verdict','codex_points'], properties:{ verdict:{type:'string'}, codex_points:{type:'array',items:{type:'string'}} } } })

phase('Record')
const rec = await agent(
  `Record 0A-5 in ${WT} (branch chore/review-readiness-0a5). Write docs/review_readiness/phase0a5_graph_fixtures.md: per-selector status (pinned byte-identical + fixture path, OR blocked + why + deferred-to-3C), the honest feasibility findings, codex verdict (${gate.verdict}). Stage explicit the fixtures under tests/oracle/graph_fixtures/ + the doc (NOT the base tests/oracle/*.py harness overlay — only NEW graph-fixture files); GUARD no secret staged. Commit ("Phase 0A-5: graph-selector replay fixtures — <N pinned / M deferred-to-3C> (honest determinism status)") std trailers. Push -u origin; PR base gate-inversion. Return {commit_sha, pushed, pr_url, committed_or_blocked}.`,
  { label: 'record', phase: 'Record', schema: { type:'object', additionalProperties:false, required:['commit_sha','pushed','pr_url','committed_or_blocked'], properties:{ commit_sha:{type:'string'}, pushed:{type:'boolean'}, pr_url:{type:'string'}, committed_or_blocked:{type:'string'} } } })

return { map: { n: map.selectors.length }, pin, gate, record: rec }
