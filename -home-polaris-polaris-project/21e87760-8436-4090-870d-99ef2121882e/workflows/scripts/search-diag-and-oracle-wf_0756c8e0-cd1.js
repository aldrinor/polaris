export const meta = {
  name: 'search-diag-and-oracle',
  description: 'Diagnose why the acceptance positive-control fired 0 searches, design a deterministic regression oracle, fix the harness portability bug, install browser, re-run',
  phases: [
    { title: 'Diagnose', detail: '4 parallel read-only investigators' },
    { title: 'Synthesize', detail: 'root-cause verdict + oracle design + fix spec' },
    { title: 'Fix+Rerun', detail: 'portable harness fix, playwright install, live re-run' },
  ],
}

const REPO = '/home/polaris/wt/outline_agent'
const OUT = '/tmp/claude-1000/-home-polaris-polaris-project/21e87760-8436-4090-870d-99ef2121882e/scratchpad/search_diag'

const DIAG = [
  { key: 'instrumentation', q: `How is the \`search_more_evidence\` tool invoked and COUNTED in the outline-agent loop? Read ${REPO}/src/polaris_graph/outline/outline_agent.py and the tool-call plumbing. Determine: does the search counter observe ATTEMPTED vs SUCCESSFUL vs FAILED calls? Could the counter read 0 while calls actually happen (broken instrumentation), or is search genuinely never invoked? Quote the exact counter/increment code with file:line.` },
  { key: 'thin_seed', q: `In ${REPO}/acceptance_outline_agent.py, what seed evidence does the THIN scenario inject, and does it genuinely cover ONLY 'efficacy' while the QUESTION also asks about long-term cardiovascular safety? Quote the THIN seed setup + question with file:line. Is the test premise actually valid (a real uncovered gap exists)?` },
  { key: 'gap_detection', q: `Where is the "checklist" / gap-ledger logic that decides "grounded deficiencies" in the outline agent? Read it in ${REPO}/src/polaris_graph/outline/. Why would it return "NONE (no grounded deficiencies)" for a genuine CV-safety coverage gap? Quote the decision logic with file:line and give the most likely reason it under-detected.` },
  { key: 'global_gating', q: `What env flags or tool-registration gate \`search_more_evidence\`? Search ${REPO}/src/polaris_graph/outline/ and the outline-agent tool registration for any PG_* flag or condition that could globally DISABLE or fail to register the search tool. Is search reachable at all in the acceptance config? Quote with file:line.` },
]

phase('Diagnose')
const findings = await parallel(DIAG.map((d) => () =>
  agent(
    `You are diagnosing a real bug for a careful refactor. Tools: Bash, Read, Grep. Work in ${REPO}.\n\nQUESTION: ${d.q}\n\nActually READ the code (don't guess). Write your findings to ${OUT}/${d.key}.md (concrete, with file:line quotes + a clear conclusion). Reply ONLY: "${d.key}: <one-line conclusion>".`,
    { label: `diag:${d.key}`, phase: 'Diagnose' }
  ).catch((e) => `${d.key}: FAILED ${String(e).slice(0,80)}`)
))

phase('Synthesize')
const synth = await agent(
  `You are the lead engineer. Four diagnostic reports are in ${OUT}/ (instrumentation.md, thin_seed.md, gap_detection.md, global_gating.md) — READ all four (Bash/Read). Then produce ${OUT}/SYNTHESIS.md with:\n1. VERDICT: is the outline-agent search path genuinely BROKEN/DISABLED, or is the 0-searches a test-premise / instrumentation artifact? State confidence.\n2. ROOT CAUSE with file:line.\n3. Whether the SATURATED negative control is vacuous (given THIN also read 0).\n4. The EXACT, minimal fix for the harness PORTABILITY bug: (a) make the hardcoded '/workspace/outline_agent_wt/acceptance_result.json' output path portable/configurable, (b) make semantic assertion pass/fail determine exit status INDEPENDENT of the result-file write. Give the precise edit for ${REPO}/acceptance_outline_agent.py.\n5. DESIGN of a DETERMINISTIC regression oracle (frozen provider inputs/responses via record/replay, pinned model/tool/browser versions, byte-level artifact diff) that could arbitrate a byte-identical refactor where the live harness cannot. 1-2 pages.\nReply ONLY: "SYNTHESIS: <one-line verdict on whether search is broken>".`,
  { label: 'synthesize', phase: 'Synthesize' }
)

phase('Fix+Rerun')
const fixrun = await agent(
  `You are applying a SAFE fix to test tooling, then re-running. Tools: Bash, Read, Edit. Work in ${REPO}.\n\n1. Read ${OUT}/SYNTHESIS.md section 4 (the harness portability fix spec).\n2. Apply that minimal fix to ${REPO}/acceptance_outline_agent.py: make the output path portable (e.g. an env-overridable path defaulting to a dir that exists, created with os.makedirs(exist_ok=True)), and ensure a SEMANTIC acceptance failure sets a nonzero exit independently of the result-file write. Do NOT change any pipeline runtime code — only the harness. Show the diff.\n3. Install the Playwright browser: run \`/opt/conda/bin/python -m playwright install chromium\` (or \`playwright install chromium\`). Report success/failure.\n4. Re-run the fixed harness: \`cd ${REPO} && HOME=/home/polaris /opt/conda/bin/python acceptance_outline_agent.py\` with a 1500s timeout; save full output to ${OUT}/rerun.log.\n5. Report to ${OUT}/FIXRUN.md: the diff applied, browser-install result, and the KEY re-run outcome — did THIN fire a search this time (search_more_evidence_calls > 0)? did SATURATED stay at 0? did the process exit cleanly?\nReply ONLY: "FIXRUN: THIN searches=<n>, SATURATED searches=<n>, exit=<code>".`,
  { label: 'fix+rerun', phase: 'Fix+Rerun' }
)

return { findings, synth, fixrun }
