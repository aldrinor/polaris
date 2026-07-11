export const meta = {
  name: 'hamster-wheel',
  description: 'POLARIS hamster wheel: Opus tests real output -> Fable root-causes + fix plan + SOTA verdict -> Opus builds -> Opus re-tests. Loops until Fable signs off.',
  phases: [
    { title: 'Test', detail: 'Opus runs the REAL entrypoint, reads output line-by-line' },
    { title: 'Fable gate', detail: 'Fresh Fable: root cause, fix plan, SOTA assessment, sign-off', model: 'fable' },
    { title: 'Build', detail: 'Opus applies the Fable plan, commits' },
  ],
}

// ---- fail-fast arg validation ----
// P1 regression this guards: a missing/empty payload used to leave every `${W.*}` as the
// literal string 'undefined', so the wheel spawned a tester AND a builder with the
// unexecutable task 'cd undefined' — burning rounds and risking a skip-permissions builder
// clobbering another wheel. Abort in one line BEFORE any agent spawns instead.
const REQUIRED_KEYS = ['wheel', 'worktree', 'branch', 'focus', 'progress_file']

function validateWheelArgs(raw) {
  let a = raw
  if (typeof a === 'string') {
    try { a = JSON.parse(a) }
    catch (e) { return { ok: false, missing: REQUIRED_KEYS.slice(), reason: `args is a non-JSON string: ${e.message}` } }
  }
  if (a === null || typeof a !== 'object') {
    return { ok: false, missing: REQUIRED_KEYS.slice(), reason: `args is ${a === null ? 'null' : typeof a}, expected an object` }
  }
  const missing = []
  for (const k of REQUIRED_KEYS) {
    const v = a[k]
    // reject absent, non-string, empty, and the literal 'undefined'/'null' that caused the regression
    if (typeof v !== 'string' || v.trim() === '' || v === 'undefined' || v === 'null') missing.push(k)
  }
  return { ok: missing.length === 0, missing, args: a }
}

const _validated = validateWheelArgs(args)
if (!_validated.ok) {
  const detail = _validated.reason ? ` (${_validated.reason})` : ''
  log(`[wheel] FATAL: missing/invalid wheel args — absent keys: [${_validated.missing.join(', ')}]${detail}. Aborting before any agent spawns.`)
  return { signed_off: false, fatal: 'missing wheel args', missing_keys: _validated.missing }
}
const W = _validated.args // {wheel, worktree, branch, focus, entrypoint_hint, progress_file}

// Verify the worktree actually exists before spawning agents that would `cd` into it.
// Guarded so a harness without node:fs degrades to key-validation only rather than throwing.
try {
  const { existsSync } = await import('node:fs')
  if (!existsSync(W.worktree)) {
    log(`[${W.wheel}] FATAL: worktree path does not exist: ${W.worktree}. Aborting before any agent spawns.`)
    return { signed_off: false, fatal: 'worktree missing', worktree: W.worktree }
  }
} catch (e) {
  log(`[${W.wheel}] warn: could not verify worktree existence (${e.message}); proceeding on key-validation only.`)
}

const MAX_ROUNDS = 8

// ---- shared context every subagent needs (they start fresh, so this must be self-contained)
const MISSION = `
POLARIS MISSION: beat ChatGPT + Gemini + FS-Researcher on deep-research reports.
  DEPTH       = process ALL 346 baskets from the outline (NOT one context window).
  FAITHFULNESS= context NLI entailment + STRICT numbers.

BINDING INVARIANTS (from docs/agentic_outline_redesign.md, non-negotiable):
- The faithfulness engine (strict_verify + NLI + numeric + provenance) is the ONLY hard gate.
- No tool result renders directly. External content re-enters ONLY through the fold-in seam
  (_offset_renumber outline_agent.py:610 + _stamp_and_delete :792).
- Computed numbers render ONLY through the verified lane (tradeoff_modeler ModelSpec / [#calc:]).
  Exploratory execute_python output is BARRED from rendering.
- WEIGHT-AND-CONSOLIDATE, never filter/cap. LAW VI: every knob env-tunable.

HARD RULES FOR YOU:
- Work ONLY inside ${W.worktree} (branch ${W.branch}). NEVER touch another wheel's worktree.
- Report REAL output only. Never invent, never round up, never claim a pass you did not observe.
- If something fails, say it failed and paste the real lines.
`

const TEST_SCHEMA = {
  type: 'object',
  required: ['ran', 'command', 'verdict', 'real_output', 'failures'],
  properties: {
    ran: { type: 'boolean', description: 'did a real command actually execute' },
    command: { type: 'string' },
    verdict: { enum: ['PASS', 'FAIL', 'BLOCKED', 'PARTIAL'] },
    real_output: { type: 'string', description: 'verbatim excerpt of the REAL output, incl. errors' },
    metrics: { type: 'object', description: 'measured numbers (timings, counts, pass/fail tallies)' },
    failures: {
      type: 'array',
      items: {
        type: 'object',
        required: ['symptom', 'evidence'],
        properties: {
          symptom: { type: 'string' },
          evidence: { type: 'string', description: 'file:line or verbatim output line' },
          suspected_component: { type: 'string' },
        },
      },
    },
    blockers: { type: 'array', items: { type: 'string' } },
  },
}

const PLAN_SCHEMA = {
  type: 'object',
  required: ['sign_off', 'sota', 'root_causes', 'fix_plan'],
  properties: {
    sign_off: { type: 'boolean', description: 'TRUE only if 0 P0 and 0 P1 remain. Never force-approve.' },
    sign_off_reason: { type: 'string' },
    sota: {
      type: 'object',
      required: ['at_sota', 'gap'],
      properties: {
        at_sota: { type: 'boolean', description: 'does this wheel genuinely beat ChatGPT/Gemini/FS-Researcher on its axis' },
        gap: { type: 'string', description: 'the concrete remaining gap to SOTA, or why we are already past it' },
      },
    },
    root_causes: {
      type: 'array',
      items: {
        type: 'object',
        required: ['severity', 'file', 'why'],
        properties: {
          severity: { enum: ['P0', 'P1', 'P2'] },
          file: { type: 'string', description: 'file:line' },
          why: { type: 'string', description: 'the actual mechanism, not a symptom restatement' },
        },
      },
    },
    fix_plan: {
      type: 'array',
      items: {
        type: 'object',
        required: ['step', 'file', 'change', 'acceptance'],
        properties: {
          step: { type: 'integer' },
          file: { type: 'string' },
          change: { type: 'string', description: 'concrete, file:line specific' },
          acceptance: { type: 'string', description: 'the OBSERVABLE that proves it worked' },
        },
      },
    },
  },
}

const BUILD_SCHEMA = {
  type: 'object',
  required: ['applied', 'commit_sha', 'honest_status'],
  properties: {
    applied: { type: 'array', items: { type: 'string' } },
    skipped: { type: 'array', items: { type: 'string' }, description: 'plan steps NOT done, and why' },
    commit_sha: { type: 'string' },
    files_changed: { type: 'array', items: { type: 'string' } },
    honest_status: { type: 'string', description: 'what actually landed vs what the plan asked for' },
  },
}

log(`[${W.wheel}] hamster wheel starting — worktree ${W.worktree}, branch ${W.branch}`)

const history = []
let signedOff = false

for (let round = 1; round <= MAX_ROUNDS; round++) {
  if (budget.total && budget.remaining() < 60_000) {
    log(`[${W.wheel}] stopping: token budget nearly spent`)
    break
  }

  // ---------- 1. TEST: run the real thing, read the real output ----------
  phase('Test')
  const test = await agent(
    `${MISSION}

YOU ARE THE TESTER for the POLARIS "${W.wheel}" wheel. Round ${round}.

FOCUS OF THIS WHEEL: ${W.focus}

${round > 1 ? `PREVIOUS ROUND: the builder applied a fix. Here is what it claims it did:\n${JSON.stringify(history[history.length - 1]?.build ?? {}, null, 2)}\n\nYour job is to find out whether that is TRUE by running the code.` : ''}

DO THIS:
0. GUARD: If ${W.worktree} does not exist or is not a git worktree on branch ${W.branch},
   STOP immediately and report BLOCKED (verdict BLOCKED, say why in blockers). NEVER cd into
   or modify any other worktree.
1. cd ${W.worktree}. Read OVERNIGHT_PROGRESS.md and ${W.progress_file} (if it exists) for state.
2. Find and RUN the real entrypoint for this wheel. ${W.entrypoint_hint}
   - Run it FOREGROUND with a HARD timeout (e.g. \`timeout 900 python ...\`). NEVER nohup+tail -f.
   - Prefer the cheapest run that still exercises the REAL path. A unit test that mocks the
     thing under test proves nothing — drive the actual code.
3. READ THE OUTPUT LINE BY LINE. Do not skim. Do not trust a green checkmark; check that the
   assertion actually asserted something real.
4. Report VERBATIM output, including failures. If it is blocked, say BLOCKED and why.

RESOURCE DISCIPLINE: one heavy run at a time. Other wheels are running in parallel and share
the OpenRouter rate limit — if you see HTTP 429, SAY SO in blockers, do not silently retry forever.`,
    { label: `${W.wheel}:test:r${round}`, phase: 'Test', schema: TEST_SCHEMA },
  )

  if (!test) {
    log(`[${W.wheel}] r${round}: tester died, aborting wheel`)
    break
  }
  log(`[${W.wheel}] r${round} TEST -> ${test.verdict} (${test.failures?.length ?? 0} failures)`)

  // ---------- 2. FABLE GATE: root cause + fix plan + SOTA verdict ----------
  phase('Fable gate')
  const plan = await agent(
    `${MISSION}

YOU ARE THE INDEPENDENT GATE (Fable) for the POLARIS "${W.wheel}" wheel. Round ${round}.
You did NOT build this. A builder never grades its own homework. Be adversarial.

FOCUS OF THIS WHEEL: ${W.focus}

THE TESTER JUST RAN THE REAL CODE AND REPORTED:
${JSON.stringify(test, null, 2)}

${history.length ? `PRIOR ROUNDS (what was tried, and whether it worked):\n${JSON.stringify(history.map(h => ({ round: h.round, verdict: h.test.verdict, signed: h.plan?.sign_off, built: h.build?.honest_status })), null, 2)}` : ''}

DO THIS — and READ THE REAL CODE in ${W.worktree}, do not reason from the summary alone:
1. LINE-BY-LINE READ of the real output above against the real source. Verify the tester's
   claims. Testers are wrong sometimes; a PASS that asserts nothing is a FAIL.
2. ROOT-CAUSE each failure to a MECHANISM at file:line. "It errors" is not a root cause.
   Severity: P0 = faithfulness breach (unsupported number rendered as verified, injection
   obeyed, silent wrong answer). P1 = wrong/unreachable result, undisclosed. P2 = cosmetic.
3. SOTA ASSESSMENT — the honest one. Does this wheel, AS IT ACTUALLY IS RIGHT NOW, beat
   ChatGPT + Gemini + FS-Researcher on its axis? What is the concrete remaining gap?
   Do not flatter. If we are behind, say we are behind and by what.
4. FIX PLAN: concrete, file:line, front-loaded (most important first). Every step needs an
   ACCEPTANCE OBSERVABLE — the thing the next test run must SEE to prove the fix took.
5. SIGN_OFF: true ONLY if 0 P0 and 0 P1. NEVER force-approve. If the tester was BLOCKED and
   you cannot see real evidence, that is NOT a sign-off.`,
    { label: `${W.wheel}:fable-gate:r${round}`, phase: 'Fable gate', model: 'fable', schema: PLAN_SCHEMA, effort: 'high' },
  )

  if (!plan) {
    log(`[${W.wheel}] r${round}: Fable gate died, aborting wheel`)
    break
  }

  const p0p1 = (plan.root_causes ?? []).filter(r => r.severity === 'P0' || r.severity === 'P1').length
  log(`[${W.wheel}] r${round} FABLE -> sign_off=${plan.sign_off} | P0/P1=${p0p1} | SOTA=${plan.sota?.at_sota} | ${plan.sota?.gap?.slice(0, 90) ?? ''}`)

  if (plan.sign_off) {
    history.push({ round, test, plan, build: null })
    signedOff = true
    log(`[${W.wheel}] *** SIGNED OFF at round ${round} ***`)
    break
  }

  // ---------- 3. BUILD: apply the Fable plan ----------
  phase('Build')
  const build = await agent(
    `${MISSION}

YOU ARE THE BUILDER for the POLARIS "${W.wheel}" wheel. Round ${round}.

The independent Fable gate REJECTED the current state and produced this plan.
Execute it. Do not freelance; if you disagree with a step, do it anyway OR skip it and say why
in "skipped" — never silently deviate.

FABLE'S ROOT CAUSES + FIX PLAN:
${JSON.stringify({ root_causes: plan.root_causes, fix_plan: plan.fix_plan, sota: plan.sota }, null, 2)}

THE REAL TEST OUTPUT THAT TRIGGERED THIS:
${test.real_output?.slice(0, 4000) ?? '(none)'}

DO THIS:
0. GUARD: If ${W.worktree} does not exist or is not a git worktree on branch ${W.branch},
   STOP immediately and report BLOCKED (honest_status=BLOCKED, empty commit_sha). NEVER cd
   into or modify any other worktree.
1. cd ${W.worktree}. Apply the fix plan, top-down (it is front-loaded).
2. EXERCISE EVERY PATH YOU TOUCH before committing. py_compile is NOT enough — the last driver
   shipped a fix whose error path would have TypeError'd at runtime because it only compiled it.
   Actually call the function on the failure path it handles.
3. git commit in ${W.worktree} with an HONEST message. If the fix is partial, the commit message
   must say PARTIAL and what is still open.
4. Append a dated one-line status to ${W.progress_file}.
5. Report honestly what landed vs what the plan asked for. A skipped step reported is fine.
   A skipped step hidden is not.`,
    { label: `${W.wheel}:build:r${round}`, phase: 'Build', schema: BUILD_SCHEMA },
  )

  if (!build) {
    log(`[${W.wheel}] r${round}: builder died, aborting wheel`)
    history.push({ round, test, plan, build: null })
    break
  }
  log(`[${W.wheel}] r${round} BUILD -> ${build.commit_sha ?? 'no commit'} | ${build.honest_status?.slice(0, 100) ?? ''}`)

  history.push({ round, test, plan, build })
}

const last = history[history.length - 1]
log(`[${W.wheel}] wheel done — ${history.length} round(s), signed_off=${signedOff}`)

return {
  wheel: W.wheel,
  worktree: W.worktree,
  branch: W.branch,
  signed_off: signedOff,
  rounds: history.length,
  final_sota: last?.plan?.sota ?? null,
  final_verdict: last?.test?.verdict ?? null,
  open_p0p1: (last?.plan?.root_causes ?? []).filter(r => r.severity !== 'P2'),
  timeline: history.map(h => ({
    round: h.round,
    test: h.test?.verdict,
    metrics: h.test?.metrics,
    sign_off: h.plan?.sign_off,
    at_sota: h.plan?.sota?.at_sota,
    gap: h.plan?.sota?.gap,
    commit: h.build?.commit_sha,
    landed: h.build?.honest_status,
  })),
}
