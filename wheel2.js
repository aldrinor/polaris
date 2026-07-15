export const meta = {
  name: 'wheel2',
  description: 'Opus-grinds / Fable-scalpel wheel: Opus does ALL hard work (read, search, build, fix, measure) toward a benchmark target; Fable is called ONCE per round for a precise deep-think gate only — never for hard read/search. Loops until Fable gates it top.',
  phases: [
    { title: 'Work', detail: 'Opus: read the named files, apply the next concrete step, exercise it, commit, MEASURE the benchmark' },
    { title: 'Gate', detail: 'Fable: precise deep-think on the diff + measurement — correct? faithfulness-safe? top yet? exact next step', model: 'fable' },
  ],
}

// ---- fail-fast arg validation ----
const REQUIRED = ['wheel', 'worktree', 'branch', 'progress_file', 'mission', 'state', 'next_actions', 'success_metric']
function validate(raw) {
  let a = raw
  if (typeof a === 'string') { try { a = JSON.parse(a) } catch (e) { return { ok: false, missing: REQUIRED.slice(), reason: `args non-JSON: ${e.message}` } } }
  if (a === null || typeof a !== 'object') return { ok: false, missing: REQUIRED.slice(), reason: `args is ${a === null ? 'null' : typeof a}` }
  const missing = REQUIRED.filter(k => typeof a[k] !== 'string' || !a[k].trim() || a[k] === 'undefined')
  return { ok: missing.length === 0, missing, args: a }
}
const _v = validate(args)
if (!_v.ok) { log(`[wheel2] FATAL: bad args, missing [${_v.missing.join(', ')}]${_v.reason ? ' — ' + _v.reason : ''}`); return { fatal: 'bad args', missing: _v.missing } }
const W = _v.args

const MAX_ROUNDS = Number.isFinite(+W.max_rounds) ? +W.max_rounds : 10

const FENCE = `
FENCE (military discipline — no exceptions):
- Work ONLY inside ${W.worktree} (branch ${W.branch}). NEVER touch another worktree.
- NEVER edit anything under /home/polaris/polaris_project (operator's monitoring dir — deck.sh, wheel*.js, wheels.py).
  If you catch yourself editing a monitoring script or a workflow .js, you have DRIFTED — stop.
- Report REAL output only. Never invent, never claim a pass you did not observe, never fake a benchmark number.
- Commit every landed step in ${W.worktree}; append one dated line to ${W.progress_file}.
`
const MISSION = `
POLARIS MISSION (this wheel): ${W.mission}
SUCCESS IS MEASURED BY: ${W.success_metric}
The bar is not "bug fixed" — it is the benchmark number at the top, VERIFIED. Keep going until the
measurement says top (or you hit a hard external blocker you must report honestly).
${FENCE}`

const WORK_SCHEMA = {
  type: 'object', required: ['did', 'commits', 'measurement', 'status'],
  properties: {
    did: { type: 'array', items: { type: 'string' }, description: 'concrete steps actually completed' },
    commits: { type: 'array', items: { type: 'string' }, description: 'commit shas landed this round' },
    files_touched: { type: 'array', items: { type: 'string' } },
    measurement: { type: 'string', description: 'the REAL benchmark/observable measured this round (number + how obtained), or why not measurable yet' },
    exercised: { type: 'string', description: 'how each change was actually run/proven (not py_compile)' },
    open: { type: 'array', items: { type: 'string' }, description: 'what is still not done, honestly' },
    needs_fable: { type: 'string', description: 'the ONE precise question for Fable to deep-think this round — a decision, correctness/faithfulness judgment, or gap-to-top; NOT a request to read the codebase' },
    status: { enum: ['PROGRESS', 'BLOCKED', 'BELIEVE_TOP'] },
    blockers: { type: 'array', items: { type: 'string' } },
  },
}
const GATE_SCHEMA = {
  type: 'object', required: ['at_top', 'correct', 'faithfulness_safe', 'verdict', 'next_step'],
  properties: {
    at_top: { type: 'boolean', description: 'does the REAL measurement show this wheel at top benchmark performance' },
    correct: { type: 'boolean', description: 'is the applied diff actually correct for what it claims' },
    faithfulness_safe: { type: 'boolean', description: 'does it preserve the faithfulness invariants (no unverified/derived number can render; fold-in seam intact)' },
    verdict: { enum: ['SIGN_OFF', 'CONTINUE', 'FIX_REGRESSION'] },
    reason: { type: 'string' },
    gap_to_top: { type: 'string', description: 'the concrete remaining gap, or why we are already top' },
    next_step: { type: 'string', description: 'the single most important next action for Opus — precise, file:line where possible' },
  },
}

log(`[${W.wheel}] wheel2 (Opus-grinds/Fable-scalpel) starting — ${W.worktree}`)
const history = []
let signedOff = false
let carry = W.next_actions // what Opus should do this round; updated by Fable's next_step each loop

for (let round = 1; round <= MAX_ROUNDS; round++) {
  if (budget.total && budget.remaining() < 80_000) { log(`[${W.wheel}] stop: budget low`); break }

  // ---------- WORK: Opus does ALL the hard work ----------
  phase('Work')
  const work = await agent(
    `${MISSION}

YOU ARE OPUS — the hands AND the eyes. Do the hard work yourself: read the exact files named, search
where needed, build, fix, run, MEASURE. Do not wait for anyone to read the code for you.

CURRENT STATE (accurate as of wheel start — verify, don't assume):
${W.state}

YOUR ACTIONS THIS ROUND (precise; do these, in order, then MEASURE):
${round === 1 ? W.next_actions : carry}

RULES:
- PACE — GO HARD, DO MORE PER ROUND: attempt MULTIPLE high-value items this round, not one. Batch
  aggressively, commit several times, push as far as you safely can. Do NOT squeeze one tiny change
  and stop ("no toothpaste"). Only end a round when you genuinely need Fable's judgment or you have
  measured the metric. Faster, harder, sharper.
- Actually EXERCISE every change (run it; a heartbeat/concurrency probe, a real test, a real score —
  py_compile is NOT proof). Commit what passes.
- MEASURE the success metric (${W.success_metric}) with a real number this round if at all possible.
- End by writing ONE precise question for Fable in "needs_fable" — a decision or a
  correctness/faithfulness/gap-to-top judgment. Do NOT ask Fable to read or search the codebase; you
  already did that. Give Fable the diff summary + the measurement, not a reading assignment.`,
    { label: `${W.wheel}:work:r${round}`, phase: 'Work', schema: WORK_SCHEMA },
  )
  if (!work) { log(`[${W.wheel}] r${round}: work agent died`); break }
  log(`[${W.wheel}] r${round} WORK: ${work.status} | commits=${(work.commits || []).join(',') || 'none'} | ${(work.measurement || '').slice(0, 90)}`)

  // ---------- GATE: Fable, precise deep-think ONLY (short input, no codebase crawl) ----------
  phase('Gate')
  const gate = await agent(
    `${MISSION}

YOU ARE FABLE — the scalpel. You are NOT here to read or search the codebase; Opus already did the
hard reading. You are here for ONE precise deep-think: judge what Opus did and decide the next step.

WHAT OPUS DID THIS ROUND:
${JSON.stringify({ did: work.did, commits: work.commits, files: work.files_touched, exercised: work.exercised, measurement: work.measurement, open: work.open, status: work.status, blockers: work.blockers }, null, 2)}

OPUS'S PRECISE QUESTION FOR YOU:
${work.needs_fable || '(none given — judge correctness + gap-to-top from the above)'}

${history.length ? `PRIOR ROUNDS (for continuity):\n${JSON.stringify(history.map(h => ({ r: h.round, meas: h.work?.measurement, verdict: h.gate?.verdict, next: h.gate?.next_step })), null, 2)}` : ''}

DECIDE, precisely:
1. at_top: does the REAL measurement show top benchmark performance? (${W.success_metric})
2. correct: is the diff correct for what it claims?
3. faithfulness_safe: are the invariants intact (no derived/unverified number can render; fold-in seam intact)?
4. verdict: SIGN_OFF only if at_top AND correct AND faithfulness_safe. Else CONTINUE (or FIX_REGRESSION if
   Opus broke something). NEVER force-approve. A measurement Opus could not take is NOT a sign-off.
5. next_step: the single most important next action for Opus — precise, file:line where you can.
Think deeply here; this is the one place the wheel spends deep reasoning. Keep it tight and decisive.`,
    { label: `${W.wheel}:gate:r${round}`, phase: 'Gate', model: 'fable', schema: GATE_SCHEMA, effort: 'high' },
  )
  if (!gate) { log(`[${W.wheel}] r${round}: gate died`); history.push({ round, work, gate: null }); break }
  log(`[${W.wheel}] r${round} GATE: ${gate.verdict} | at_top=${gate.at_top} | ${(gate.next_step || '').slice(0, 90)}`)
  history.push({ round, work, gate })

  if (gate.verdict === 'SIGN_OFF' && gate.at_top) { signedOff = true; log(`[${W.wheel}] *** SIGNED OFF — TOP at round ${round} ***`); break }
  carry = `Fable's gate verdict was ${gate.verdict}. Reason: ${gate.reason}\nDO THIS NEXT (precise): ${gate.next_step}\nGap to top: ${gate.gap_to_top}`
}

const last = history[history.length - 1]
log(`[${W.wheel}] done — ${history.length} round(s), signed_off=${signedOff}`)
return {
  wheel: W.wheel, worktree: W.worktree, branch: W.branch, signed_off: signedOff, rounds: history.length,
  at_top: last?.gate?.at_top ?? false,
  gap_to_top: last?.gate?.gap_to_top ?? null,
  last_measurement: last?.work?.measurement ?? null,
  timeline: history.map(h => ({ round: h.round, status: h.work?.status, commits: h.work?.commits, measurement: h.work?.measurement, verdict: h.gate?.verdict, at_top: h.gate?.at_top, next: h.gate?.next_step })),
}
