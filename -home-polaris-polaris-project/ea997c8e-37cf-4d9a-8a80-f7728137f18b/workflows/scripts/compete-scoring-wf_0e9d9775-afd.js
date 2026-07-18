export const meta = {
  name: 'compete-scoring',
  description: 'Score POLARIS vs ChatGPT/Gemini on deep-research reports. Settle RACE-vs-DeepTRACE, run the scorer on EXISTING reports, produce an honest head-to-head table. NOT a test-fix loop.',
  phases: [
    { title: 'Settle', detail: 'RACE vs DeepTRACE — which exists, which the mission needs' },
    { title: 'Score', detail: 'run the scorer on existing POLARIS + competitor reports' },
    { title: 'Judge', detail: 'Fable: is the scoreboard honest, do we win or lose', model: 'fable' },
  ],
}

const RULES = `
POLARIS mission: beat ChatGPT + Gemini + FS-Researcher on deep-research reports.
WORK ONLY IN /home/polaris/wt/compete. NEVER cd into /home/polaris/wt/tooluse or run outline pytest —
that is a DIFFERENT wheel's job. You are NOT here to run unit tests. You are here to SCORE REPORTS.

Reference (read-only): /workspace/POLARIS. Competitor artifacts: /workspace/POLARIS/competitors/*.md
(ONLY ChatGPT_Scoped, ChatGPT_Unscoped, Gemini_Scoped, Gemini_Unscoped exist — there is NO
FS-Researcher artifact; report that gap, do not fake a third column).
Existing rendered POLARIS reports to score: find /workspace/POLARIS/outputs -name report.md
Scorer in tree: scripts/dr_benchmark/deeptrace_scorer.py, deeptrace_judge_preflight.py,
config/benchmark/deeptrace_judge_lock.yaml. Mission says RACE (DeepResearch Bench:
comprehensiveness/insight/instruction-following/readability). DeepTRACE (citation auditing) != RACE.

HONESTY IS THE ENTIRE POINT: if POLARIS loses, say so and by how much. Never tune the judge to win.
Do NOT burn a fresh 346-basket render — score reports that already exist. Uses OpenRouter (shared
account); if you see 429, say so, do not silently retry forever. Never print the API key.
`

const SETTLE_SCHEMA = {
  type: 'object',
  required: ['scorer_exists', 'is_it_RACE', 'what_mission_needs', 'recommendation'],
  properties: {
    scorer_exists: { type: 'boolean' },
    is_it_RACE: { enum: ['it_is_RACE', 'it_is_DEEPTRACE', 'it_is_BOTH', 'neither'] },
    scorer_details: { type: 'string', description: 'what the scorer actually measures: dimensions, judge model, reference-based?' },
    what_mission_needs: { type: 'string' },
    gap: { type: 'string', description: 'the honest gap between what exists and what the mission asks for' },
    recommendation: { type: 'string', description: 'use DeepTRACE as-is / build RACE / adapt — with why' },
    fsr_missing: { type: 'boolean', description: 'true = no FS-Researcher artifact to score against' },
  },
}

const SCORE_SCHEMA = {
  type: 'object',
  required: ['ran', 'scored', 'table'],
  properties: {
    ran: { type: 'boolean' },
    command: { type: 'string' },
    scored: { type: 'array', items: { type: 'string' }, description: 'which reports were actually scored' },
    table: { type: 'string', description: 'the REAL head-to-head score table, per dimension, POLARIS vs each competitor' },
    polaris_wins: { type: 'boolean' },
    loss_margins: { type: 'string', description: 'per dimension where POLARIS loses, by how much' },
    blockers: { type: 'array', items: { type: 'string' } },
    raw: { type: 'string' },
  },
}

phase('Settle')
const settle = await agent(
  `${RULES}

STEP 1 — settle RACE vs DeepTRACE. Read scripts/dr_benchmark/deeptrace_scorer.py and the judge lock
config. Determine EXACTLY what it scores. Is it RACE (4 DeepResearch-Bench dimensions, reference-based
LLM judge) or DeepTRACE (citation/faithfulness auditing) or both? Then state what the mission actually
needs and the honest gap. Do NOT relabel DeepTRACE as RACE to look done. Also confirm the
FS-Researcher artifact is genuinely absent from competitors/.`,
  { label: 'compete:settle-race-vs-deeptrace', phase: 'Settle', schema: SETTLE_SCHEMA },
)

phase('Score')
const score = await agent(
  `${RULES}

STEP 2 — SCORE. Given what STEP 1 found:
${JSON.stringify(settle, null, 2)}

Run the scorer that ACTUALLY exists against EXISTING reports (do not build a fresh render). Score at
least one real POLARIS report (find /workspace/POLARIS/outputs -name report.md — pick a substantive
recent one) against the 4 competitor artifacts. Produce a REAL head-to-head table per dimension.
If the scorer needs a reference/question to score against, find the matching one in the repo. If you
genuinely cannot run it end-to-end, say exactly why in blockers — do NOT fabricate a table.
Report whether POLARIS wins or loses, per dimension, with margins. A loss reported honestly is the
whole point of this wheel.`,
  { label: 'compete:score-head-to-head', phase: 'Score', schema: SCORE_SCHEMA },
)

phase('Judge')
const judge = await agent(
  `${RULES}

YOU ARE FABLE, THE INDEPENDENT GATE. Assess the scoreboard for HONESTY, not for whether we win.

SETTLE: ${JSON.stringify(settle, null, 2)}
SCORE:  ${JSON.stringify(score, null, 2)}

Answer: (1) Is the scorer the RIGHT instrument for the mission, or is it measuring the wrong thing?
(2) Is the table REAL (actually computed) or fabricated/hand-wavy? (3) Does POLARIS actually beat
ChatGPT and Gemini on this evidence — yes or no, per dimension? (4) What is the honest state of the
FS-Researcher comparison (we have no artifact)? (5) The single most important next action to make
this a trustworthy SOTA claim. Be blunt. The operator has been burned by a confident wrong thesis
before; do not add another.`,
  { label: 'compete:fable-honesty-judge', phase: 'Judge', model: 'fable', effort: 'high' },
)

log(`COMPETE: scorer=${settle?.is_it_RACE} | polaris_wins=${score?.polaris_wins} | fsr_missing=${settle?.fsr_missing}`)
return { settle, score, judge }
