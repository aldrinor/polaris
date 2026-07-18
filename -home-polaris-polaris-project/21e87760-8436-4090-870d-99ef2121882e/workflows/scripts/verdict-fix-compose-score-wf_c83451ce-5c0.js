export const meta = {
  name: 'verdict-fix-compose-score',
  description: "Execute Sol's verdict-placement fix, then dry-gate -> compose -> RACE score, each phase gated",
  phases: [
    { title: 'P1 fix', detail: 'wire IDENTITY_PROVEN into report_ast source policy + _index_person + facet contract' },
    { title: 'P2 tests', detail: 'repair/extend the acceptance suite' },
    { title: 'P3 pin corpus', detail: 'pin the 838-card curated corpus with sha' },
    { title: 'P4 dry-gate', detail: 'dry run — verdicts placed MUST be > 0' },
    { title: 'P5 compose', detail: 'full --write render to outputs/release/report.md' },
    { title: 'P6 score', detail: 'RACE score vs 0.5603' },
  ],
}

const PLAN = '/home/polaris/wt/flywheel/sota_review/foundation/SOL_VERDICT_FIX_PLAN.md'
const SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['phase', 'done', 'gate_passed', 'summary'],
  properties: {
    phase: { type: 'string' }, done: { type: 'boolean' }, gate_passed: { type: 'boolean' },
    key_number: { type: 'string', description: 'the gate metric: verdicts placed / test pass count / RACE score' },
    files_changed: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' }, blocker: { type: 'string' },
  },
}
const PHASES = [
  { id: 'P1', title: 'P1 fix', name: "Phase 1 — repair verdict placement without weakening identity (§1.1 wire att.identity_verdict in event_ledger.IDENTITY_PROVEN into report_ast's source policy — import the canonical allowlist, do NOT copy it, do NOT add a venue allowlist; §1.2 fix CardBundle._index_person poisoned source-name index at report_ast.py:329; §1.3 unify the facet contract between report_ast.py:1468 and cellcog_composer.py:98; §1.4 proof-carrying deterministic verdict type)",
    gate: "report_ast imports cleanly AND the existing binding-gate acceptance + cohort tests still pass (fabrication hole NOT reopened)" },
  { id: 'P3', title: 'P3 pin corpus', name: "Phase 3 — pin the 838-card curated corpus: copy scratchpad/cards_curated.json to outputs/compose_inputs/task72_cards_curated.json and verify sha256 a8a06549710525886f2d359acf918fd0c6676639617ce5f1b30f1efd06f91fb4",
    gate: "the pinned file exists and its sha256 matches exactly" },
  { id: 'P4', title: 'P4 dry-gate', name: "Phase 4 preflight — run cellcog_composer.py --dry per the plan's exact command/env (PG_GLM5_MIN_MAX_TOKENS=32000 etc.) and grep 'sound cross-source verdicts placed'",
    gate: "sound cross-source verdicts placed > 0 (ZERO IS A FAILED BUILD — halt, do not proceed to render; the fix did not work)" },
  { id: 'P5', title: 'P5 compose', name: "Phase 4 compose — run cellcog_composer.py --write per the plan's exact command (with --expect-cards-sha). This is a long render (~30-50 min); run it and WAIT for it to finish and publish",
    gate: "outputs/release/report.md exists, placed-verdict count is positive, AST has zero unlawful nodes, report has attributed findings AND owned analytical verdicts, no second writer running" },
  { id: 'P6', title: 'P6 score', name: "Phase 4 score — run score_report_race.py per the plan (task-id 72, race-model openai/gpt-5.5) and read the Overall Score",
    gate: "report the Overall Score; success = Overall > 0.5603" },
]

const done = []
for (const ph of PHASES) {
  phase(ph.title)
  const prompt = `You are an OPUS engineer executing ONE phase of Sol's authoritative verdict-fix + compose + score plan. This is the critical path to POLARIS's SOTA score tonight.

PLAN FILE (read the whole thing, it has exact file:line edits + commands + env): ${PLAN}
YOUR PHASE: ${ph.id} — ${ph.name}
GATE (must pass to advance): ${ph.gate}
ALREADY DONE: ${done.length ? done.join(', ') : 'none'}
REPO: /home/polaris/wt/flywheel

RULES:
- Implement Sol's spec EXACTLY. Do not improvise, especially on identity/source-policy: reuse event_ledger.IDENTITY_PROVEN (the canonical allowlist), never a venue allowlist, never let a model type its own attribution. Do NOT reopen the fabrication hole — the binding-gate acceptance + cohort tests must still pass after your change.
- Run this phase's command(s) from the plan with its exact env (PYTHONPATH=scripts:src, PG_MAX_COST_PER_RUN=100000, PG_GLM5_MIN_MAX_TOKENS=32000, source .env, PG_RESEARCH_QUESTION from /home/polaris/polaris_project/task72_prompt.txt).
- Evaluate YOUR GATE. If it fails, do NOT proceed — report gate_passed=false with the blocker and the exact failing output. For P4: if verdicts placed == 0, that is a FAILED fix — halt and report, do not render.
- For P5 (compose): it is a LONG render. Launch it and wait for it to finish + publish to outputs/release/report.md. Ensure no second cellcog writer runs concurrently.
- Do NOT git commit. Do NOT touch outputs/blobs or the ledger except as the plan's read inputs.

Return the schema: done, gate_passed, key_number (the gate metric — verdicts placed / tests passed / RACE Overall), files_changed, one-paragraph summary, blocker (empty if none).`
  const r = await agent(prompt, { schema: SCHEMA, phase: ph.title, label: ph.id })
  if (!r || !r.gate_passed) {
    log(`HALT at ${ph.id}: ${r ? (r.blocker || 'gate failed') : 'no result'} | key=${r?.key_number || '?'}`)
    return { halted_at: ph.id, phases_done: done, failed: r || null }
  }
  done.push(ph.id)
  log(`${ph.id} PASSED — ${r.key_number || ''} — ${r.summary ? r.summary.slice(0, 120) : ''}`)
}
return { status: 'SCORED', phases_done: done }
