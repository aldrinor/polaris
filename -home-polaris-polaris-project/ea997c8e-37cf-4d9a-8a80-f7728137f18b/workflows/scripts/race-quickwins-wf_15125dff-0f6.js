export const meta = {
  name: 'race-quickwins',
  description: 'Climb RACE toward SOTA by fixing the report-shape BUGS Fable found: kill clinical headers, strip pipeline-internals dump, add tables, journal-only sources, compose to the ACTUAL prompt, expand+synthesize. Re-score to prove the climb.',
  phases: [
    { title: 'Fix shape', detail: 'Opus: kill clinical headers, strip internals block, add table, journal filter, prompt-align' },
    { title: 'Deepen', detail: 'Opus: expand length ~4x + synthesis paragraphs (insight)' },
    { title: 'Re-score', detail: 'RACE on task 72 (+2 more); did overall climb from 0.30?' },
  ],
}

const CTX = `
GOAL: climb RACE (DeepResearch Bench) from best-current 0.3023 toward SOTA ~0.48. Fable's verified
diagnosis (task 72): report is 1,655 words / 8 headings / 0 tables = 18% of the 9,029-word reference.
Lost points ranked: insight 0.24 > comprehensiveness 0.21 > instruction-following 0.19 > readability 0.10.
Best compose (compose_fix iter4, glm-5.2 16-way) = 0.3023, improved by LENGTH (5,482 words).

BEST COMPOSE worktree: /home/polaris/wt/compose_fix. RACE harness + scorer + reference data live in
/home/polaris/wt/outline_agent/third_party/deep_research_bench (score_report_race.py, results/race/,
data/criteria_data/criteria.jsonl, data/test_data). Agentic corpus: cp4_corpus_s3gear_329.json.
Source the key: set -a; . /workspace/POLARIS/.env; set +a (never print it). Judge = openai/gpt-5.5.

THE SIX FIXES (highest leverage first), all measured by RE-SCORING, never asserted:
1. KILL the clinical-trial section headers (Efficacy/Safety/Comparative/Long-term Outcomes) — use
   topic-shaped sections fit to the actual question (Intro+framing, Theoretical frameworks, Empirical
   findings, Sectoral disruptions, Wages/inequality/skills, Policy, Conclusion+research-gaps).
2. STRIP the pipeline-internals Methods/Limitations block (corpus filename, tier %, telemetry,
   glm-5.2) — a literature review must contain ZERO tool meta-commentary.
3. COMPOSE AGAINST THE EXACT task-72 prompt (not POLARIS's own different query) — a mismatched query
   structurally caps instruction-following.
4. ADD 1-2 structured summary tables (the reference has two; the prompt mandated one).
5. JOURNAL-ONLY source filtering for this task (drop MIT Sloan/Wharton/advisor blogs, org working
   papers of tier UNKNOWN/T3/T4) — task-72 constraint is 'high-quality English-language journal articles'.
6. EXPAND ~4-5x (target ~7-9k words) + add a SYNTHESIS paragraph after each evidence cluster (name the
   mechanism, reconcile contradictory findings, state implications) — this is the insight lever.

HARD RULES: faithfulness gate stays the ONLY hard gate — no unverified/derived number may render via
[CITE:ev_xxx]; computed numbers only via [#calc:]. Report REAL re-scored numbers; if a fix does NOT
move the score, say so honestly. Never tune the judge. Work in compose_fix; commit each fix.
`

const FIX_SCHEMA = {
  type: 'object', required: ['applied', 'before_after'],
  properties: {
    applied: { type: 'array', items: { type: 'string' } },
    skipped: { type: 'array', items: { type: 'string' } },
    before_after: { type: 'string', description: 'RACE overall + per-dim before vs after, REAL re-scored numbers' },
    commits: { type: 'array', items: { type: 'string' } },
    honest_status: { type: 'string' },
  },
}
const SCORE_SCHEMA = {
  type: 'object', required: ['overall', 'moved'],
  properties: {
    overall: { type: 'string', description: 'new RACE overall on task 72 (+ any other tasks), REAL' },
    per_dim: { type: 'object' },
    moved: { type: 'string', description: 'delta vs the 0.3023 best-compose baseline — up, flat, or down' },
    word_count: { type: 'string' },
    notes: { type: 'string' },
  },
}

phase('Fix shape')
const shape = await agent(
  `${CTX}\n\nPHASE 1 — the structural/bug fixes (1-5 above), the cheapest big wins. Work in compose_fix.
Find where section headers are chosen (the clinical-template selection), where the Methods/Limitations
internals block is appended, where the task prompt/query is set, table emission, and source-tier
filtering. Apply fixes 1-5. Render task 72 with the best compose against the ACTUAL task-72 prompt and
RE-SCORE with score_report_race.py. Report before/after REAL numbers. Commit each fix.`,
  { label: 'quickwins:fix-shape', phase: 'Fix shape', schema: FIX_SCHEMA },
)

phase('Deepen')
const deep = await agent(
  `${CTX}\n\nPHASE 2 — the INSIGHT lever (fix 6), the highest-weight dimension (0.32). Building on phase 1:
${JSON.stringify(shape, null, 2)}
Expand the report toward ~7-9k words and add a SYNTHESIS paragraph after each evidence cluster that
names the mechanism, reconciles contradictory findings, and states implications — WITHOUT breaking the
faithfulness gate (synthesis sentences must still verify, or be clearly framed as analysis over cited
evidence). Re-render task 72, re-score. Report REAL before/after. Commit.`,
  { label: 'quickwins:deepen', phase: 'Deepen', schema: FIX_SCHEMA },
)

phase('Re-score')
const final = await agent(
  `${CTX}\n\nPHASE 3 — prove the climb. Re-score the improved compose on task 72 AND 2 more tasks
(75, 90) with score_report_race.py, gpt-5.5 judge. Report the NEW overall + per-dimension vs the 0.3023
best-compose baseline and the 0.263 mean. Was the climb real, and how far to SOTA (~0.48) now?
Phases 1-2: ${JSON.stringify({ shape: shape?.before_after, deep: deep?.before_after }, null, 2)}`,
  { label: 'quickwins:re-score', phase: 'Re-score', schema: SCORE_SCHEMA },
)

log(`RACE quick-wins: new overall=${final?.overall} moved=${final?.moved} (from 0.3023, SOTA ~0.48)`)
return { shape, deep, final }
