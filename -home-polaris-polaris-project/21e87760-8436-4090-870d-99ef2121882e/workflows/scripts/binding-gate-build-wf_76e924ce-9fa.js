export const meta = {
  name: 'binding-gate-build',
  description: "Execute Sol's 8-phase binding-gate build plan; each phase gated on its own acceptance test passing before the next starts",
  phases: [
    { title: 'P1 foundation', detail: 'harden the six foundation edits' },
    { title: 'P1S prompt-policy', detail: 'derive adjustable source policy from prompt' },
    { title: 'P2 version-unify', detail: 'one version reducer + conflict table' },
    { title: 'P3 correspondence', detail: 'semantic identity in correspondence' },
    { title: 'P4 mining-preskip', detail: 'pre-skip identity failures before LLM' },
    { title: 'P5 salvage', detail: 'positive metadata salvage of unresolved' },
    { title: 'P6 battery', detail: '12-vector battery + cohort regression' },
    { title: 'P7 adversary', detail: 'independent adversary pass' },
  ],
}

const PLAN = '/home/polaris/wt/flywheel/sota_review/foundation/SOL_BUILD_PLAN.md'

const SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['phase', 'implemented', 'acceptance_passed', 'test_command', 'summary'],
  properties: {
    phase: { type: 'string' },
    implemented: { type: 'boolean' },
    acceptance_passed: { type: 'boolean' },
    test_command: { type: 'string' },
    test_output_tail: { type: 'string' },
    files_changed: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
    blocker: { type: 'string' },
  },
}

const PHASES = [
  { id: 'P1', title: 'P1 foundation', name: 'Finish and harden the six foundation edits' },
  { id: 'P1S', title: 'P1S prompt-policy', name: 'Infer the adjustable source policy from the original prompt' },
  { id: 'P2', title: 'P2 version-unify', name: 'Unify version derivation and quarantine impossible pairs' },
  { id: 'P3', title: 'P3 correspondence', name: 'Make correspondence use semantic identity' },
  { id: 'P4', title: 'P4 mining-preskip', name: 'Pre-skip identity failures before LLM mining' },
  { id: 'P5', title: 'P5 salvage', name: 'Positive machine-metadata salvage for unresolved manifestations' },
  { id: 'P6', title: 'P6 battery', name: 'Real-chain 12-vector acceptance battery and cohort regression' },
  { id: 'P7', title: 'P7 adversary', name: 'Independent adversary pass' },
]

const done = []
for (const ph of PHASES) {
  phase(ph.title)
  const prompt = `You are an OPUS BUILDER executing ONE phase of Sol's authoritative build plan for POLARIS's fabrication-safety validator.

PLAN FILE (read it first): ${PLAN}
YOUR PHASE: ${ph.id} — "${ph.name}"
ALREADY-LANDED PHASES (do not redo): ${done.length ? done.join(', ') : 'none yet'}
REPO: /home/polaris/wt/flywheel

DO EXACTLY THIS:
1. Read ${PLAN}. Find the section for phase ${ph.id}, and also read "## Global rules for every phase".
2. Implement the phase's EXACT edits in the files it names. Follow Sol's spec PRECISELY — do NOT invent mechanisms or substitute your own design. If the plan says "one reducer", unify to one; if it says "declarative table", use a table; there is NO rank scheme. 
3. Honor the GLOBAL RULES: generality (NO task-72 / no DOI, title, author, journal, or subject literals in any rule — rules fire by structural/typed signal only), positive-proof only (a gate may reject on absence but ADMIT only on positive evidence), and add the phase's required metamorphic/generality test.
4. Run the phase's ACCEPTANCE TEST exactly as the plan specifies. It MUST exit 0.
5. If it fails, FIX your implementation until the acceptance test passes — do NOT weaken or delete the test to make it pass. If you truly cannot make it pass, stop and report the blocker with the failing output.
6. Do NOT git commit. Do NOT work on other phases. Do NOT disturb outputs/ blobs, the ledger, or launch any long-running/LLM process.

SAFETY (paramount): this code decides whether 3.5M words of new corpus can be cited without fabrication. NEVER make a change that could let a DIFFERENT_WORK or UNRESOLVED_BINDING manifestation be attributed to a claimed source, or let a preprint/working-paper be cited as the journal. When uncertain, quarantine / fail closed. A prior session already hand-made partial "foundation" edits (identity gate in resolve_attribution, from_json re-derivation, evidence_miner ~line 1401 fixed to resolve_attribution(binding,policy), factored derive_binding_core, IDENTITY_PROVEN allowlist) — P1 hardens/verifies these; later phases build on them.

Return the schema: implemented (bool), acceptance_passed (did the test exit 0), the exact test_command, test_output_tail (~last 20 lines), files_changed, a one-paragraph summary, and blocker (empty string if none).`

  const r = await agent(prompt, { schema: SCHEMA, phase: ph.title, label: ph.id })
  if (!r || !r.acceptance_passed) {
    log(`HALT at ${ph.id}: ${r ? (r.blocker || 'acceptance test did not pass') : 'agent returned nothing'}`)
    return { halted_at: ph.id, phases_done: done, failed_phase: r || null }
  }
  done.push(ph.id)
  log(`${ph.id} PASSED — ${r.summary ? r.summary.slice(0, 140) : ''}`)
}
return { status: 'ALL_PHASES_PASSED', phases_done: done }
