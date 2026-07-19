export const meta = {
  name: 'fix-harness-oracle',
  description: 'Make the acceptance harness a trustworthy deterministic oracle: add the missing positive-control assertion + wire it through the existing cassette layer for browser-free replay',
  phases: [
    { title: 'PositiveControl', detail: 'add the THIN search>=1 assertion + non-zero exit' },
    { title: 'Feasibility', detail: 'can a deterministic browser-free golden be built from existing artifacts + live OpenRouter?' },
    { title: 'Implement', detail: 'wire cassette (retrieval golden + LLM record) and prove deterministic replay' },
    { title: 'Codex-Gate', detail: 'codex verifies the harness is now a trustworthy oracle' },
    { title: 'Record', detail: 'commit + push to phase0 branch' },
  ],
}

const WT = '/home/polaris/wt/phase0'
const PORT = `${WT}/tests/oracle/acceptance_portable.py`
const PY = '/home/polaris/pipeline-env/bin/python'

phase('PositiveControl')
const pc = await agent(
  `In ${PORT} (a portable copy of an acceptance harness; do NOT touch the production acceptance_outline_agent.py), FIX the assertion-vacuous THIN positive control.
Currently run_thin() (around lines 149-165) only REPORTS metrics (search_more_evidence_calls, checklist_gap_events) and never asserts anything, so the harness exits 0 even if THIN fired 0 searches — the control cannot fail.
Add an enforceable pass gate for THIN: assert that search_calls >= 1 AND the outline was mutated (outline_mutated / the outline changed vs seed). Compute an explicit boolean like valid_positive_control (mirror how the SATURATED negative control computes valid_negative_control at ~line 260). Make main() exit NON-ZERO if either control (positive THIN or negative SATURATED) fails.
Keep it minimal and self-contained; do not change pipeline runtime behavior — this is harness/control logic only. Confirm by reading back the changed region.
Return the exact new assertion code and the line range.`,
  { label: 'pos-control', phase: 'PositiveControl', schema: { type:'object', additionalProperties:false, required:['assertion_code','line_range','exit_nonzero_wired'], properties:{ assertion_code:{type:'string'}, line_range:{type:'string'}, exit_nonzero_wired:{type:'boolean'} } } })

phase('Feasibility')
const feas = await agent(
  `Determine whether a DETERMINISTIC, BROWSER-FREE golden replay can be built for the acceptance harness in ${WT}, given this environment has NO working browser (Playwright/Chromium fails with TargetClosedError) but DOES have working HTTP APIs (OpenRouter LLM, Serper).
Investigate:
1. The existing deterministic oracle layer: ${WT}/tests/oracle/cassette.py (record/replay core) and ${WT}/tests/oracle/llm_cassette.py (monkeypatches OpenRouterClient.generate). Understand its record/replay API.
2. The retrieval boundary the harness uses: find run_live_retrieval (grep src/), its signature, and what it returns (evidence rows). This is the boundary that needs a browser at RECORD time.
3. Existing successful-run artifacts: find any committed/on-disk acceptance_result_thin.json / acceptance_result*.json (the harness historically wrote to /workspace/outline_agent_wt/; also search the repo). Does such an artifact contain the actual retrieval EVIDENCE (evidence_rows / fetched candidate text) — enough to SEED a frozen retrieval golden WITHOUT a fresh browser run?
4. Assess the strategy: (a) freeze the RETRIEVAL output by monkeypatching run_live_retrieval to return evidence reconstructed from an existing artifact (browser-free), then (b) run the outline agent LIVE so its LLM calls (OpenRouter, browser-free) are recorded via llm_cassette, then (c) replay both deterministically. 
Return: is this feasible with existing artifacts + live OpenRouter alone (no browser)? If YES, give the concrete implementation plan (which artifact seeds retrieval, which seam injects it, how LLM record/replay wraps the run). If NO, state the EXACT blocker and what environment/credential/box would be needed to record the golden once.`,
  { label: 'feasibility', phase: 'Feasibility', schema: { type:'object', additionalProperties:false, required:['feasible_browser_free','plan_or_blocker','seed_artifact','retrieval_seam','details'], properties:{ feasible_browser_free:{type:'boolean'}, plan_or_blocker:{type:'string'}, seed_artifact:{type:'string'}, retrieval_seam:{type:'string'}, details:{type:'string'} } } })

phase('Implement')
let impl = null
if (feas.feasible_browser_free) {
  impl = await agent(
    `Implement the deterministic browser-free golden for the acceptance harness in ${WT}, per this vetted plan:\n${feas.plan_or_blocker}\nSeed artifact: ${feas.seed_artifact}. Retrieval seam: ${feas.retrieval_seam}.
Steps:
1. Wire ${PORT} so that in a "record" mode it (a) injects a frozen retrieval result reconstructed from the seed artifact via the retrieval seam (no browser), and (b) records the outline agent's OpenRouter LLM calls through ${WT}/tests/oracle/llm_cassette.py to a cassette file under ${WT}/tests/oracle/cassettes/.
2. Run RECORD once: 'cd ${WT} && ${PY} tests/oracle/acceptance_portable.py --record' (or the equivalent you wire). This uses live OpenRouter (works) + frozen retrieval (no browser). Capture the golden result artifact + its SHA-256.
3. Run REPLAY: same command in replay mode, twice, and confirm the result artifact is BYTE-IDENTICAL across replays (same SHA-256) and that the THIN positive control (search>=1) PASSES and SATURATED negative control PASSES.
4. If live OpenRouter recording fails (rate limit/credential), report the precise error — do not fake a cassette.
Return: whether deterministic replay is proven (byte-identical across 2+ replays), the golden SHA-256, cassette path, and both control outcomes.`,
    { label: 'implement', phase: 'Implement', schema: { type:'object', additionalProperties:false, required:['deterministic_replay_proven','golden_sha256','cassette_path','positive_control_pass','negative_control_pass','notes'], properties:{ deterministic_replay_proven:{type:'boolean'}, golden_sha256:{type:'string'}, cassette_path:{type:'string'}, positive_control_pass:{type:'boolean'}, negative_control_pass:{type:'boolean'}, notes:{type:'string'} } } })
} else {
  log(`Feasibility: browser-free golden NOT feasible with existing artifacts. Blocker: ${feas.plan_or_blocker}`)
}

phase('Codex-Gate')
const gate = await agent(
  `Run CODEX (GPT-5.6) to gate whether the acceptance harness is now a TRUSTWORTHY governing oracle. Write /tmp/harness_gate.md then run 'cd /tmp && timeout 300 codex exec --skip-git-repo-check - < /tmp/harness_gate.md 2>&1 | tail -40' (bubblewrap warning fine; no sandbox flags).
Give codex:
- The 3 prior blockers: (1) assertion-vacuous THIN positive control, (2) non-deterministic live calls / no frozen trace, (3) not runnable-to-completion (no browser).
- Positive-control fix: ${JSON.stringify(pc)}
- Feasibility finding: ${JSON.stringify(feas)}
- Implementation result: ${JSON.stringify(impl)}
Ask: "Are all three oracle-trustworthiness blockers now resolved? Specifically: does the THIN positive control now enforceably fail on 0 searches, and is the harness now deterministic (byte-identical golden across replays) and runnable-to-completion browser-free? If the golden was seeded from an existing artifact rather than a fresh live browser run, is that acceptable for a REFACTOR-SAFETY oracle (which must detect code changes, not reproduce the original crawl)? Name any residual gap. End with: ORACLE-TRUSTWORTHY or ORACLE-STILL-BLOCKED, and if blocked, the single blocking item."
Return codex's verdict + points verbatim.`,
  { label: 'codex-gate', phase: 'Codex-Gate', schema: { type:'object', additionalProperties:false, required:['verdict','codex_points'], properties:{ verdict:{type:'string'}, codex_points:{type:'array',items:{type:'string'}} } } })

phase('Record')
const rec = await agent(
  `Record the harness-oracle work to branch chore/review-readiness-phase0 in ${WT}.
1. git add the changed portable harness (tests/oracle/acceptance_portable.py), any new cassette files under tests/oracle/cassettes/, and any golden artifact. Grep-check: NO plaintext secret in any staged file.
2. Write/append a short note to ${WT}/docs/review_readiness/oracle_status.md summarizing: the 3 blockers, the positive-control assertion fix, the cassette-based deterministic golden (or the exact remaining blocker if not achieved), and codex's verdict (${JSON.stringify(gate.verdict)}).
3. Commit (message describing the oracle-trustworthiness fixes) ending with:
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01TLpJSqNfJVSP1UGdtk89nA
4. Push. Return {commit_sha, pushed, files_committed}.`,
  { label: 'record', phase: 'Record', schema: { type:'object', additionalProperties:false, required:['commit_sha','pushed','files_committed'], properties:{ commit_sha:{type:'string'}, pushed:{type:'boolean'}, files_committed:{type:'array',items:{type:'string'}} } } })

return { pc, feas, impl, gate, record: rec }
