export const meta = {
  name: 'race-sota-push',
  description: 'Close the RACE gap to SOTA: diagnose per-dimension where POLARIS loses (current 0.2685 vs ~0.48 frontier), re-score with best compose + multi-task, target the weakest dimension. Honest, measured.',
  phases: [
    { title: 'Diagnose', detail: 'per-dimension breakdown of the 0.2685 + what the reference does better' },
    { title: 'True number', detail: 'best-compose re-render + 3 more DRB tasks for a real average' },
    { title: 'Target', detail: 'Fable: the single highest-leverage fix to climb toward SOTA', model: 'fable' },
  ],
}

const CTX = `
POLARIS must hit SOTA on RACE (DeepResearch Bench, github.com/Ayanami0730/deep_research_bench).
RACE = reference-based LLM judge (openai/gpt-5.5), 4 DIMENSIONS with per-task dynamic weights:
Comprehensiveness, Insight/Depth, Instruction-Following, Readability. Frontier systems (ChatGPT/Gemini
deep research, FS-Researcher arXiv 2602.01566) score ~0.45-0.50. POLARIS's FIRST real number:
DRB task72 overall = 0.2685 (faithfulness PASS) — WELL BELOW SOTA. That report was composed by the
OUTLINE wheel's OWN compose, NOT the improved compose_fix (16-way concurrency). Proof artifacts +
scorer live in /home/polaris/wt/outline_agent (outputs/, scripts/score_report_race.py); the agentic
corpus is data/cp4_corpus_s3gear_329.json (329 baskets, 'Generative AI's Impact on Employment').
Best compose = /home/polaris/wt/compose_fix (sharded, judge/writer 16-way, glm-5.2 max tokens).

HONESTY: report the REAL per-dimension numbers. If a dimension is genuinely weak, say so. Do NOT tune
the judge to inflate the score. The goal is a TRUE climb toward 0.48, not a flattering number.
Source the OpenRouter key: set -a; . /workspace/POLARIS/.env; set +a  (never print it). Watch cost —
score EXISTING renders where possible; a full new render only when needed. If 429/hang, say so.
`

const DIM_SCHEMA = {
  type: 'object', required: ['dimensions', 'weakest', 'why'],
  properties: {
    overall: { type: 'string' },
    dimensions: { type: 'object', description: 'comprehensiveness/insight/instruction_following/readability -> score + weight, REAL numbers' },
    weakest: { type: 'string', description: 'the dimension where POLARIS loses the most points (score x weight gap)' },
    why: { type: 'string', description: 'concretely, what the reference report does that POLARIS does not — read both' },
    quick_wins: { type: 'array', items: { type: 'string' } },
  },
}
const NUM_SCHEMA = {
  type: 'object', required: ['scores', 'mean'],
  properties: {
    scores: { type: 'array', items: { type: 'object', properties: { task: { type: 'string' }, overall: { type: 'string' }, compose: { type: 'string', description: 'best or outline-own' } } } },
    mean: { type: 'string', description: 'mean RACE overall across the tasks scored' },
    best_vs_own_compose: { type: 'string', description: 'did the best compose (compose_fix) score higher than the outline-own compose on the same task?' },
    notes: { type: 'string' },
  },
}

phase('Diagnose')
const dim = await agent(
  `${CTX}\n\nDIAGNOSE the 0.2685. Find the RACE result JSON for DRB task72 under
/home/polaris/wt/outline_agent/outputs (score_report_race.py output). Extract the PER-DIMENSION
scores + weights (comprehensiveness, insight, instruction-following, readability). Identify the
WEAKEST dimension by lost points (weight x (1 - score)). Then READ both the POLARIS report AND the
task72 REFERENCE report and say concretely what the reference does that POLARIS does not (depth?
coverage? structure? specific analysis?). Give real numbers.`,
  { label: 'race:diagnose-dimensions', phase: 'Diagnose', schema: DIM_SCHEMA },
)

phase('True number')
const num = await agent(
  `${CTX}\n\nGet the TRUE current number, two ways:
(1) MULTI-TASK: one task is noise. Score POLARIS on 2-3 MORE DRB tasks (pick tasks whose topic the
329-basket AI corpus can actually answer, or the nearest reference tasks the harness supports) with
score_report_race.py, same gpt-5.5 judge, to get a MEAN, not a single point.
(2) BEST-COMPOSE: the 0.2685 used the outline's own compose. If feasible without a huge spend, render
the SAME task72 outline through the best compose (compose_fix, 16-way) and re-score — does the best
compose lift the number? If a full re-render is too costly right now, say so and skip, don't fake it.
Report the scores, the mean, and whether best-compose beats outline-own-compose. Diagnosis context:
${JSON.stringify(dim, null, 2)}`,
  { label: 'race:true-number', phase: 'True number', schema: NUM_SCHEMA },
)

phase('Target')
const plan = await agent(
  `${CTX}\n\nYOU ARE FABLE. Given the REAL per-dimension diagnosis and the multi-task number, decide the
SINGLE highest-leverage move to climb toward SOTA (0.48). Be concrete and honest.

DIAGNOSIS: ${JSON.stringify(dim, null, 2)}
TRUE NUMBER: ${JSON.stringify(num, null, 2)}

Answer: (1) What is our HONEST current RACE standing (mean, per dimension) vs the ~0.48 frontier?
(2) Which ONE dimension, fixed, moves the overall the most — and is that a compose problem (rendering
depth/readability), an outline problem (coverage/structure), a corpus problem (weak sourcing), or a
scorer artifact? (3) The concrete next action for the relevant wheel, file/knob-specific where you can.
(4) Is SOTA realistically reachable with the current corpus+pipeline, or is there a structural ceiling
we must name? Do not flatter — the operator wants the truth about the gap and the real path to close it.`,
  { label: 'race:fable-target', phase: 'Target', model: 'fable', effort: 'high' },
)

log(`RACE SOTA: weakest=${dim?.weakest} | mean=${num?.mean} vs SOTA ~0.48`)
return { dim, num, plan }
