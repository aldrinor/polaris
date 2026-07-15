export const meta = {
  name: 'wheel',
  description: 'Fable-finds-first hamster wheel: Fable diagnoses fast (parallel lenses) -> ranked concrete fix-list -> Opus EXECUTES each fix (no hunting) -> fast verify -> loop until Fable signs off.',
  phases: [
    { title: 'Diagnose', detail: 'Fable, parallel lenses: concrete problems at file:line, ranked', model: 'fable' },
    { title: 'Fix', detail: 'Opus applies each ranked fix at file:line, exercises it, commits' },
    { title: 'Verify', detail: 'run each fix acceptance observable; confirm it took' },
  ],
}

// ---- fail-fast arg validation (keeps the earlier hardening) ----
const REQUIRED_KEYS = ['wheel', 'worktree', 'branch', 'focus', 'progress_file']
function validateArgs(raw) {
  let a = raw
  if (typeof a === 'string') { try { a = JSON.parse(a) } catch (e) { return { ok: false, missing: REQUIRED_KEYS.slice(), reason: `args non-JSON string: ${e.message}` } } }
  if (a === null || typeof a !== 'object') return { ok: false, missing: REQUIRED_KEYS.slice(), reason: `args is ${a === null ? 'null' : typeof a}` }
  const missing = REQUIRED_KEYS.filter(k => typeof a[k] !== 'string' || !a[k].trim() || a[k] === 'undefined')
  return { ok: missing.length === 0, missing, args: a }
}
const _v = validateArgs(args)
if (!_v.ok) { log(`[wheel] FATAL: bad args, missing [${_v.missing.join(', ')}]${_v.reason ? ' — ' + _v.reason : ''}`); return { signed_off: false, fatal: 'bad args', missing: _v.missing } }
const W = _v.args // {wheel, worktree, branch, focus, progress_file, lenses?, seed_findings?, entrypoint_hint?}

const MAX_ROUNDS = 8
const LENSES = Array.isArray(W.lenses) && W.lenses.length ? W.lenses : [
  'correctness / logic bugs that produce a wrong or unsupported result',
  'the primary performance / serialization bottleneck on the hot path',
  'silent failures: errors swallowed, statuses that lie, dead/ignored config',
  'missing coverage: the load-bearing path with no test that would catch a regression',
]

const MISSION = `
POLARIS MISSION: beat ChatGPT + Gemini + FS-Researcher on deep-research reports.
  DEPTH = process ALL 346 baskets. FAITHFULNESS = context NLI + STRICT numbers.
BINDING INVARIANTS (docs/agentic_outline_redesign.md): faithfulness engine (strict_verify + NLI +
numeric + provenance) is the ONLY hard gate; external content re-enters ONLY via the fold-in seam;
computed numbers render ONLY via the verified [#calc:] lane (never [CITE:ev_xxx]); exploratory
execute_python is BARRED from rendering; weight-and-consolidate, never filter.
FENCE: work ONLY inside ${W.worktree} (branch ${W.branch}). NEVER touch another worktree or the
operator's /home/polaris/polaris_project monitoring dir. Report REAL output only; never fake a pass.
`

// ---------- schemas ----------
const FIND_SCHEMA = {
  type: 'object', required: ['findings'],
  properties: {
    findings: { type: 'array', items: {
      type: 'object', required: ['severity', 'file_line', 'problem', 'fix', 'acceptance'],
      properties: {
        severity: { enum: ['P0', 'P1', 'P2'] },
        file_line: { type: 'string', description: 'exact file:line' },
        problem: { type: 'string', description: 'the concrete mechanism, not a vibe' },
        fix: { type: 'string', description: 'the concrete change to make, specific enough for hands to apply' },
        acceptance: { type: 'string', description: 'the OBSERVABLE that proves the fix took (a command output, a value, a test)' },
        evidence: { type: 'string' },
      } } },
    nothing_found: { type: 'boolean' },
  },
}
const RANK_SCHEMA = {
  type: 'object', required: ['sign_off', 'ranked'],
  properties: {
    sign_off: { type: 'boolean', description: 'TRUE only if 0 P0 and 0 P1 remain after this round. Never force-approve.' },
    sign_off_reason: { type: 'string' },
    sota: { type: 'object', properties: { at_sota: { type: 'boolean' }, gap: { type: 'string' } } },
    ranked: { type: 'array', description: 'deduped, most-severe-first', items: {
      type: 'object', required: ['severity', 'file_line', 'fix', 'acceptance'],
      properties: {
        severity: { enum: ['P0', 'P1', 'P2'] },
        file_line: { type: 'string' },
        problem: { type: 'string' },
        fix: { type: 'string' },
        acceptance: { type: 'string' },
      } } },
  },
}
const FIXED_SCHEMA = {
  type: 'object', required: ['file', 'applied', 'commit_sha'],
  properties: {
    file: { type: 'string' },
    applied: { type: 'array', items: { type: 'string' } },
    skipped: { type: 'array', items: { type: 'string' } },
    exercised: { type: 'string', description: 'how each touched path was actually run before commit' },
    commit_sha: { type: 'string' },
    honest_status: { type: 'string' },
  },
}
const VERIFY_SCHEMA = {
  type: 'object', required: ['results'],
  properties: { results: { type: 'array', items: {
    type: 'object', required: ['file_line', 'passed'],
    properties: { file_line: { type: 'string' }, passed: { type: 'boolean' }, observed: { type: 'string' } } } } },
}

log(`[${W.wheel}] Fable-first wheel — worktree ${W.worktree}`)
const history = []
let signedOff = false

for (let round = 1; round <= MAX_ROUNDS; round++) {
  if (budget.total && budget.remaining() < 60_000) { log(`[${W.wheel}] stop: budget low`); break }

  // ---------- 1. DIAGNOSE — FABLE FINDS, FAST, IN PARALLEL ----------
  phase('Diagnose')
  let ranked
  if (round === 1 && W.seed_findings) {
    // A prior investigation already found the problems — go straight to ranking + fixing.
    ranked = await agent(
      `${MISSION}\n\nYOU ARE FABLE. A prior forensic investigation of the "${W.wheel}" wheel produced these findings.
Dedup, rank most-severe-first, and turn each into a CONCRETE fix with an ACCEPTANCE observable a
builder can verify. Set sign_off=false (we have not fixed anything yet). FOCUS: ${W.focus}

FINDINGS:\n${typeof W.seed_findings === 'string' ? W.seed_findings : JSON.stringify(W.seed_findings, null, 2)}`,
      { label: `${W.wheel}:rank-seed`, phase: 'Diagnose', model: 'fable', schema: RANK_SCHEMA, effort: 'high' },
    )
  } else {
    // Fable scans the code through several lenses AT ONCE — fast, targeted, no Opus wandering.
    const lensResults = await parallel(LENSES.map((lens, i) => () =>
      agent(
        `${MISSION}\n\nYOU ARE FABLE, diagnostic lens ${i + 1}. READ THE REAL CODE in ${W.worktree}.
Find concrete problems through ONE lens: ${lens}
FOCUS OF THIS WHEEL: ${W.focus}
${round > 1 ? `Round ${round}: prior fixes were applied. Find what is STILL wrong or newly broken.\nAlready addressed:\n${JSON.stringify(history[history.length - 1]?.verified ?? [], null, 2)}` : ''}
Every finding = a MECHANISM at file:line + the concrete fix + an acceptance observable. No vibes.
If your lens finds nothing, set nothing_found=true — a clean lens is a real result.`,
        { label: `${W.wheel}:lens${i + 1}`, phase: 'Diagnose', model: 'fable', schema: FIND_SCHEMA, effort: 'high' },
      )))
    const all = lensResults.filter(Boolean).flatMap(r => r.findings ?? [])
    ranked = await agent(
      `${MISSION}\n\nYOU ARE FABLE. ${LENSES.length} diagnostic lenses scanned "${W.wheel}". Dedup by file:line,
rank most-severe-first, keep each finding's fix + acceptance. Then decide sign_off: TRUE only if
0 P0 and 0 P1. Never force-approve. FOCUS: ${W.focus}\n\nRAW FINDINGS:\n${JSON.stringify(all, null, 2)}`,
      { label: `${W.wheel}:rank`, phase: 'Diagnose', model: 'fable', schema: RANK_SCHEMA, effort: 'high' },
    )
  }

  if (!ranked) { log(`[${W.wheel}] r${round}: diagnose died`); break }
  const actionable = (ranked.ranked ?? []).filter(f => f.severity === 'P0' || f.severity === 'P1')
  log(`[${W.wheel}] r${round} DIAGNOSE: ${actionable.length} P0/P1 | sign_off=${ranked.sign_off}`)

  if (ranked.sign_off || actionable.length === 0) {
    signedOff = !!ranked.sign_off
    history.push({ round, ranked, fixes: [], verified: [] })
    log(`[${W.wheel}] *** ${signedOff ? 'SIGNED OFF' : 'no P0/P1 left'} at round ${round} ***`)
    break
  }

  // ---------- 2. FIX — OPUS EXECUTES, one fixer per FILE (parallel across files, no same-file clobber) ----------
  phase('Fix')
  const byFile = {}
  for (const f of actionable) { const k = f.file_line.split(':')[0]; (byFile[k] ??= []).push(f) }
  const fixes = await parallel(Object.entries(byFile).map(([file, items]) => () =>
    agent(
      `${MISSION}\n\nYOU ARE THE BUILDER (Opus hands) for "${W.wheel}". Fable already found the problems and
told you EXACTLY what to change. DO NOT re-investigate, DO NOT hunt for an entrypoint, DO NOT wander.
Apply ONLY these fixes to ${file}, in order:\n${JSON.stringify(items, null, 2)}

For each: make the concrete change at the file:line; then ACTUALLY EXERCISE the touched path (run it,
py_compile is NOT enough — the acceptance observable tells you what to run); then git commit in
${W.worktree} with an honest message (say PARTIAL if partial). Append one dated line to
${W.progress_file}. Report what landed vs what Fable asked. A skipped fix reported is fine; hidden is not.`,
      { label: `${W.wheel}:fix:${file.split('/').pop()}`, phase: 'Fix', schema: FIXED_SCHEMA },
    ).then(r => r && { ...r, file })))
  const okFixes = fixes.filter(Boolean)
  log(`[${W.wheel}] r${round} FIX: ${okFixes.length} file(s) touched`)

  // ---------- 3. VERIFY — fresh eyes run the acceptance observables ----------
  phase('Verify')
  const verify = await agent(
    `${MISSION}\n\nYOU ARE THE VERIFIER for "${W.wheel}" (fresh — you did not build). For EACH fix Fable
asked for, RUN its acceptance observable in ${W.worktree} and report pass/fail with what you observed.
A fix that compiles but whose acceptance observable does not show the expected result is NOT passed.

FIXES FABLE ASKED FOR:\n${JSON.stringify(actionable, null, 2)}
WHAT THE BUILDER CLAIMS IT DID:\n${JSON.stringify(okFixes.map(f => ({ file: f.file, status: f.honest_status, sha: f.commit_sha })), null, 2)}`,
    { label: `${W.wheel}:verify:r${round}`, phase: 'Verify', schema: VERIFY_SCHEMA },
  )
  const verified = verify?.results ?? []
  const passed = verified.filter(v => v.passed).length
  log(`[${W.wheel}] r${round} VERIFY: ${passed}/${verified.length} fixes confirmed`)
  history.push({ round, ranked, fixes: okFixes, verified })
}

const last = history[history.length - 1]
log(`[${W.wheel}] done — ${history.length} round(s), signed_off=${signedOff}`)
return {
  wheel: W.wheel, worktree: W.worktree, branch: W.branch, signed_off: signedOff, rounds: history.length,
  final_sota: last?.ranked?.sota ?? null,
  open_p0p1: (last?.ranked?.ranked ?? []).filter(f => f.severity !== 'P2'),
  timeline: history.map(h => ({
    round: h.round, diagnosed: (h.ranked?.ranked ?? []).length, sign_off: h.ranked?.sign_off,
    fixed_files: h.fixes.map(f => f.commit_sha), verified_pass: h.verified.filter(v => v.passed).length,
  })),
}
