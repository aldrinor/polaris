export const meta = {
  name: 'card-audit-build',
  description: "Build & validate Sol's evidence-card audit tooling now (in parallel with the mine) so it runs instantly at mine-end",
  phases: [
    { title: 'T0 deterministic screen', detail: 'per-card deterministic verification (faithfulness/numeric/structure/binding)' },
    { title: 'Opus audit harness', detail: 'Tier1/2/3 opus passes + dimensions from the plan' },
    { title: 'Dispositions', detail: 'keep/repair/rebase/demote/quarantine logic' },
    { title: 'Adversary + validate', detail: 'seed known-bad cards; validate on recovered + stale cards' },
  ],
}

const PLAN = '/home/polaris/wt/flywheel/sota_review/foundation/SOL_CARD_AUDIT_PLAN.md'

const SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['phase', 'built', 'acceptance_passed', 'summary'],
  properties: {
    phase: { type: 'string' },
    built: { type: 'boolean' },
    acceptance_passed: { type: 'boolean' },
    test_command: { type: 'string' },
    files_changed: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
    blocker: { type: 'string' },
  },
}

const PHASES = [
  { id: 'T0', title: 'T0 deterministic screen', name: 'the Tier-0 deterministic per-card screen (all dimensions that need no LLM): structure/binding verify_span, numeric-token extraction, CoT-contamination structural test, facet presence' },
  { id: 'HARNESS', title: 'Opus audit harness', name: 'the Opus audit harness — Tier-1 first pass, Tier-2 independent second pass, Tier-3 adjudication, each dimension per the plan (faithfulness via report_ast entailment, numeric fidelity, relevance, voice); --model opus, no cheaper fallback' },
  { id: 'DISPOSITION', title: 'Dispositions', name: 'the disposition engine: KEEP_UNCHANGED / REPAIR_TIGHTEN / REBASE_TO_VALID_SUPPORT / REMOVE_BAD_SUPPORT_EDGE / DEMOTE_TO_OWNED_SUGGESTION / QUARANTINE, each with its rule; re-run deterministic dims after any repair; nothing silently dropped' },
  { id: 'ADVERSARY', title: 'Adversary + validate', name: 'seed KNOWN-BAD cards (fabricated binding, CoT-contaminated claim, flipped numeric sign, off-topic) and assert the audit CATCHES each; then validate the whole pipeline end-to-end on the cards available NOW (outputs/recovered_table_cards.json if present, and a sample of outputs/evidence_cards_v2.json) — do a SMALL real opus run (a few cards) to prove the opus path works, then STOP (do not audit the full set — the real cards are still being mined)' },
]

const done = []
for (const ph of PHASES) {
  phase(ph.title)
  const prompt = `You are an OPUS BUILDER creating (not yet fully running) the evidence-card quality AUDIT tool, per Sol's authoritative plan. A mine is running concurrently and will write the real cards (outputs/evidence_cards_v2.json) in ~40 min; your job is to BUILD + VALIDATE the audit so it launches instantly at mine-end.

PLAN FILE (read it first): ${PLAN}
YOUR PHASE: ${ph.id} — build ${ph.name}
ALREADY-BUILT PHASES: ${done.length ? done.join(', ') : 'none yet'}
REPO: /home/polaris/wt/flywheel

DO EXACTLY THIS:
1. Read ${PLAN} fully. Build your phase's component exactly to Sol's spec — reuse report_ast/the entailment judge for faithfulness (do NOT reinvent), do NOT use the legacy scripts/quarantine.py (Sol forbids it — hardcodes journal-only). Put the audit code in a clear new module (e.g. scripts/card_audit/ or scripts/card_audit.py) — do NOT modify evidence_miner.py, provenance.py, event_ledger.py, report_ast.py, or the running mine.
2. Honor GENERALITY: no task-72 / no DOI/title/subject literals; rules fire on structure. Add the phase's test.
3. Run your phase's acceptance test; it must pass.
4. For the ADVERSARY phase: you MAY make a SMALL real opus call batch (a handful of cards) to prove the opus audit path works — but do NOT run the full audit; the real card set is still being mined.

HARD CONSTRAINTS:
- The mine (python evidence_miner.py --workers 24) and the recovery (recover_truncated_tables.py) are RUNNING. Do NOT touch them, their outputs (evidence_cards_v2.json, recovered_table_cards.json — you may READ these), outputs/blobs, or the ledger. Do NOT kill any process.
- The audit uses opus (Anthropic) — fine, different pool from the mine's OpenRouter. Set PYTHONPATH=scripts:src.
- Do NOT git commit.

Return the schema: built (bool), acceptance_passed (test exit 0), test_command, files_changed, one-paragraph summary, blocker (empty if none).`

  const r = await agent(prompt, { schema: SCHEMA, phase: ph.title, label: ph.id })
  if (!r || !r.acceptance_passed) {
    log(`HALT at ${ph.id}: ${r ? (r.blocker || 'acceptance test did not pass') : 'agent returned nothing'}`)
    return { halted_at: ph.id, phases_done: done, failed_phase: r || null }
  }
  done.push(ph.id)
  log(`${ph.id} BUILT — ${r.summary ? r.summary.slice(0, 140) : ''}`)
}
return { status: 'AUDIT_TOOL_READY', phases_done: done }
