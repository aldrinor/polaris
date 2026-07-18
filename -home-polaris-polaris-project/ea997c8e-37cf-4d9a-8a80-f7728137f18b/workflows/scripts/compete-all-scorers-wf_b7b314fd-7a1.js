export const meta = {
  name: 'compete-all-scorers',
  description: 'Beat competitors on ALL axes: DeepTRACE (faithfulness), RACE (quality), DRB-II (published rubric). Run what exists, build what does not, score POLARIS vs ChatGPT/Gemini on each. Honest scoreboard — win or lose stated per axis.',
  phases: [
    { title: 'DeepTRACE', detail: 'wire the key, run the faithfulness scorer that already exists' },
    { title: 'RACE', detail: 'build the 4-dim quality judge, score reports' },
    { title: 'DRB-II', detail: 'stand up the official rubric harness if fetchable' },
    { title: 'Judge', detail: 'Fable: honest multi-axis scoreboard, win/lose per axis', model: 'fable' },
  ],
}

const RULES = `
POLARIS mission: beat ChatGPT + Gemini + FS-Researcher on deep-research reports — on EVERY axis.
The operator's directive: use ALL scorers; we must win on all, not cherry-pick the one we pass.

WORK ONLY IN /home/polaris/wt/compete. Reference (read-only): /workspace/POLARIS.
Competitor artifacts: /workspace/POLARIS/competitors/*.md — ONLY ChatGPT_Scoped, ChatGPT_Unscoped,
Gemini_Scoped, Gemini_Unscoped exist. NO FS-Researcher artifact (a background search is hunting the
FS-Researcher paper+benchmark separately) — report FSR as an open gap, never fake a third column.
Existing rendered POLARIS reports to score: find /workspace/POLARIS/outputs -name report.md (~35 exist).

THE THREE AXES (orthogonal — a report can win one and lose another):
- DeepTRACE (EXISTS): scripts/dr_benchmark/deeptrace_scorer.py — 8 citation-faithfulness metrics.
  Judge lock config/benchmark/deeptrace_judge_lock.yaml (signed, judge=moonshotai/kimi-k2.6,
  self_rescore fairness policy). Preflight deeptrace_judge_preflight.py HARD-BLOCKS if OPENROUTER_API_KEY
  is unset or provider headroom < 8. The key IS available: source it with
  \`set -a; . /workspace/POLARIS/.env 2>/dev/null; set +a\` (NEVER print it).
- RACE (DOES NOT EXIST — must build): DeepResearch-Bench 4-dim reference-based LLM judge —
  Comprehensiveness, Insight/Depth, Instruction-Following, Readability, weighted by per-task criteria
  vs a reference answer. Build it honestly; do NOT relabel DeepTRACE as RACE.
- DRB-II (EXTERNAL): scripts/dr_benchmark/drbii_wrapper.py adapts the official DeepResearch-Bench-II
  rubric harness, but third_party/ is absent. Fetch it if fetchable; if not, say so plainly.

HARD HONESTY RULES:
- If POLARIS LOSES on an axis, say so and by how much. A flattering scoreboard is worse than none.
- Never tune a judge to make us win. Score every system with the SAME judge/tasks (self_rescore).
- Do NOT burn a fresh 346-basket render — score the ~35 reports that already exist.
- Cost/rate: paid judge calls on a SHARED OpenRouter account (~217 credits left). If you see HTTP 429,
  SAY SO in blockers; do not silently retry forever. Never print the API key.
`

const AXIS_SCHEMA = {
  type: 'object',
  required: ['axis', 'ran', 'polaris_score', 'competitor_scores', 'polaris_wins'],
  properties: {
    axis: { type: 'string' },
    ran: { type: 'boolean', description: 'did the scorer actually execute end-to-end on real reports' },
    built: { type: 'boolean', description: 'did you have to build the scorer (RACE)' },
    command: { type: 'string' },
    polaris_score: { type: 'string', description: 'REAL measured score, or "unmeasured" with why' },
    competitor_scores: { type: 'string', description: 'ChatGPT scoped/unscoped + Gemini scoped/unscoped, same judge' },
    polaris_wins: { enum: ['yes', 'no', 'partial', 'unmeasured'] },
    margins: { type: 'string', description: 'per dimension, POLARIS vs each competitor, with sign' },
    blockers: { type: 'array', items: { type: 'string' } },
    raw: { type: 'string' },
  },
}

// DeepTRACE first — it exists, just needs the key wired. Fastest real number.
phase('DeepTRACE')
const deeptrace = await agent(
  `${RULES}

AXIS 1 — DEEPTRACE (faithfulness), the one that already exists. Make it RUN.
1. Source the key: \`set -a; . /workspace/POLARIS/.env 2>/dev/null; set +a\` then run
   deeptrace_judge_preflight.py — confirm it now PASSES (it hard-blocked before only because the key
   was unset).
2. Score a substantive real POLARIS report (find /workspace/POLARIS/outputs -name report.md) AND all 4
   competitor artifacts with the SAME kimi-k2.6 judge (self_rescore). Watch cost — one report is
   ~178 support calls; start with ONE POLARIS + the 4 competitors, not all 35.
3. Report the 8-metric faithfulness scoreboard, POLARIS vs each competitor, and who wins per metric.
   If 429s appear, log them and stop rather than burning credits.`,
  { label: 'compete:deeptrace', phase: 'DeepTRACE', schema: AXIS_SCHEMA },
)

// RACE + DRB-II can proceed in parallel — independent axes, no shared writes to the same scorer.
phase('RACE')
const [race, drbii] = await parallel([
  () => agent(
    `${RULES}

AXIS 2 — RACE (quality). It does NOT exist; BUILD it, honestly.
Implement the DeepResearch-Bench RACE 4-dim reference-based judge (Comprehensiveness, Insight,
Instruction-Following, Readability) with per-task adaptive criteria vs a reference answer, judge via
OpenRouter (reuse the kimi-k2.6 judge lock discipline / self_rescore so it is comparable). Put it under
scripts/dr_benchmark/ in the compete worktree. Then score ONE real POLARIS report + the 4 competitor
artifacts with it. Need a reference/question per task — find the matching one in the repo (the report's
own cp-inputs or the drb task set). Report the 4-dim table, POLARIS vs each competitor, win/lose per
dim. If you cannot obtain reference answers, say so — a RACE score without a reference is not RACE.`,
    { label: 'compete:race-build', phase: 'RACE', schema: AXIS_SCHEMA },
  ),
  () => agent(
    `${RULES}

AXIS 3 — DRB-II (official published rubric). drbii_wrapper.py exists but third_party/ is absent.
Try to stand it up: locate/fetch the official DeepResearch-Bench-II harness + tasks_and_rubrics.jsonl
(check the wrapper for the expected path/URL; the repo may vendor or reference it). If you can fetch it,
run the rubric judge on one POLARIS report + competitors and report the rubric score. If third_party/
is genuinely unfetchable in this environment (no network / not vendored), say so plainly and report
what WOULD be needed — do NOT fabricate a rubric number.`,
    { label: 'compete:drbii', phase: 'DRB-II', schema: AXIS_SCHEMA },
  ),
])

phase('Judge')
const judge = await agent(
  `${RULES}

YOU ARE FABLE, THE INDEPENDENT GATE. Build the honest multi-axis scoreboard.

DEEPTRACE (faithfulness): ${JSON.stringify(deeptrace, null, 2)}
RACE (quality):          ${JSON.stringify(race, null, 2)}
DRB-II (rubric):         ${JSON.stringify(drbii, null, 2)}

Produce the operator's real answer:
1. A single scoreboard: for EACH axis (DeepTRACE, RACE, DRB-II), does POLARIS beat ChatGPT? beat
   Gemini? — yes / no / partial / unmeasured, with the margin. Mark clearly which numbers are REAL
   (actually computed) vs unmeasured/blocked.
2. The blunt bottom line: on how many of the three axes can we HONESTLY claim to beat both competitors
   right now? Where do we LOSE, and by how much?
3. FS-Researcher: state the gap honestly (no artifact yet).
4. The single highest-leverage next action to make "beats all, on all axes" a defensible claim.
Do not flatter. The operator has been burned by a confident wrong thesis before.`,
  { label: 'compete:fable-scoreboard', phase: 'Judge', model: 'fable', effort: 'high' },
)

log(`COMPETE all-axes: DeepTRACE=${deeptrace?.polaris_wins} RACE=${race?.polaris_wins} DRB-II=${drbii?.polaris_wins}`)
return { deeptrace, race, drbii, judge }
