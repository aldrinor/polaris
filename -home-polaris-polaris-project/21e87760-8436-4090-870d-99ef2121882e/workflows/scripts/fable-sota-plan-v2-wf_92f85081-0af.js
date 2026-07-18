export const meta = {
  name: 'fable-sota-plan-v2',
  description: 'Fable designs the plan to take POLARIS from 0.4382 to the top of the board (0.54+), grounded in the measured artifacts and the grader source, then survives adversarial attack',
  phases: [
    { title: 'Study', detail: 'read bodhi (the task-72 winner) and cellcog-max line by line against our report' },
    { title: 'Design', detail: 'Fable designs the plan' },
    { title: 'Attack', detail: 'skeptics attack every lever on 4 lenses' },
    { title: 'Final', detail: 'hardened plan with kill rules' },
  ],
}

const PP = '/home/polaris/polaris_project'
const BRIEF = `${PP}/SOTA_BRIEF_V2.md`
const BOARD = `${PP}/drb_corpus/gpt55_board`
const OURS = '/home/polaris/wt/flywheel/outputs/rank10_sections_compose/report.md'

const STUDY = {
  type: 'object',
  required: ['findings'],
  properties: {
    findings: { type: 'array', items: { type: 'object', required: ['what_they_do', 'what_we_do', 'quote_them', 'quote_us', 'criterion', 'why_it_scores'], properties: {
      what_they_do: { type: 'string' }, what_we_do: { type: 'string' },
      quote_them: { type: 'string', description: 'VERBATIM from the winner artifact' },
      quote_us: { type: 'string', description: 'VERBATIM from our report' },
      criterion: { type: 'string', description: 'the exact rubric criterion this moves' },
      why_it_scores: { type: 'string' },
    } } },
  },
}

phase('Study')
const study = await parallel([
  () => agent(`Read ${BRIEF} first. Then extract task 72 from ${BOARD}/bodhi.jsonl (id=72) and read it **LINE BY LINE, END TO END**.

**bodhi WINS TASK 72 at 0.5441 — with 4,361 words, 44% SHORTER than our 7,742-word report which scores 0.4382.**
It has 40 H3 subsections and 59-word paragraphs. We have 0 H3 and 677-word paragraphs.

Read OUR report too: ${OURS} (body only — split at '## References'; a whole-file read re-counts the bibliography as prose).

THE QUESTION: what is bodhi DOING, sentence by sentence, that earns +0.11 over us on LESS THAN HALF the words?
Focus on the sentence types. Quote both sides VERBATIM. Look specifically at:
  - how it opens a subsection (topic sentence? claim-first?)
  - how it handles CONFLICTING evidence — does it adjudicate, and in what words?
  - does it make claims no single source supports (cross-source inference)? QUOTE THEM. What fraction?
  - does it name authors/studies/venues IN PROSE (survives the cleaner) vs rely on citation markers (DELETED)?
  - does it state limitations, future directions, "what the evidence cannot resolve"?
  - what does a bodhi PARAGRAPH look like structurally vs one of our 677-word walls?`,
    { schema: STUDY, model: 'fable', effort: 'max', label: 'study:bodhi-vs-us', phase: 'Study' }),

  () => agent(`Read ${BRIEF} first. Then extract task 72 from ${BOARD}/cellcog-max.jsonl (id=72) — the corpus #1
(0.5578 overall) — and read it **LINE BY LINE, END TO END**. 16,334 words, 31 H3, 75-word paragraphs, 0 bullets.

Compare against OUR report ${OURS} (body only) AND against the reference ${BOARD}/gemini-2.5-pro-deepresearch.jsonl
(id=72, scores 0.5102 = parity — this is the article the judge scores us AGAINST, side by side, in the same call).

THE QUESTION: the grader is COMPARATIVE and writes its analysis BEFORE scoring. What would a judge WRITE when
comparing cellcog-max to the reference — and what would it write comparing US to the reference? Be concrete and
quote. Where exactly does our report hand the judge a reason to mark us down?
Also: cellcog-max is 2x the reference's length and still wins on every dimension. The rubric NEVER rewards length —
so what is the extra length BUYING? (comprehensiveness's "information depth and detail" + "data and factual support"?)
Quote the passages that would earn those criteria.`,
    { schema: STUDY, model: 'fable', effort: 'max', label: 'study:cellcog-vs-ref', phase: 'Study' }),
])
const S = study.filter(Boolean)
log(`study: ${S.reduce((n, s) => n + (s.findings?.length ?? 0), 0)} paired findings`)

const PLAN = {
  type: 'object',
  required: ['diagnosis', 'levers', 'faithfulness_contract', 'expected_total', 'kill_rule', 'ceiling_honesty'],
  properties: {
    diagnosis: { type: 'string', description: 'Why we score 0.4382 and bodhi scores 0.5441 on HALF the words. The real mechanism.' },
    faithfulness_contract: { type: 'string', description: 'The revised contract. NOTE: the rubric rewards ADJUDICATION, not HEDGING — our existing hedge-based class-I design is misaligned. Redesign it. No fabricated fact/number/entity may EVER ship.' },
    levers: { type: 'array', items: { type: 'object', required: ['id', 'name', 'rubric_criterion', 'dimension', 'change', 'expected_points', 'how_it_fails', 'cheap_test', 'effort'], properties: {
      id: { type: 'string' }, name: { type: 'string' },
      rubric_criterion: { type: 'string', description: 'the VERBATIM criterion from the scoring prompt' },
      dimension: { type: 'string' }, change: { type: 'string', description: 'concrete, file-level where possible' },
      expected_points: { type: 'string' }, how_it_fails: { type: 'string' },
      cheap_test: { type: 'string', description: 'proves the mechanism fired BEFORE a 65-min compose' },
      effort: { type: 'string', enum: ['small', 'medium', 'large'] },
    } } },
    expected_total: { type: 'string', description: 'Honest sum from 0.4382. Does it reach 0.54? If not, how short?' },
    ceiling_honesty: { type: 'string', description: 'What this plan CANNOT do, and why.' },
    kill_rule: { type: 'string' },
  },
}

phase('Design')
const design = await agent(
  `You are designing POLARIS's path to the TOP of the DeepResearch Bench board. Read ${BRIEF} in full first — every
number in it is measured from primary artifacts or read from the grader's source code.

LINE-BY-LINE STUDY OF THE WINNERS (just completed):
${JSON.stringify(S, null, 1).slice(0, 40000)}

THE FACTS THAT MUST SHAPE THE DESIGN:
- We are 0.4382. bodhi wins task 72 at 0.5441 **on 4,361 words — 44% SHORTER than us.** LENGTH IS DEAD.
- Our READABILITY (0.3774) is the WORST SCORE ON THE ENTIRE BOARD — below grok and perplexity, whom we outrank.
  Cause: 12 paragraphs, median 677 words, 0 subsections. Every other system: 38-170 word paragraphs.
- The judge scores ALL ~25 criteria in ONE call, ONE context, writing a comparative analysis BEFORE the numbers.
  **Cross-dimension bleed is real and uninstructed** — our readability disaster taxes the other 86% of the score.
- INSIGHT (0.32, our worst at 0.4238) is structurally FORBIDDEN by our own gate: the entailment judge kills any
  sentence introducing "a mechanism not present in the span" — i.e. every cross-source inference.
- **THE RUBRIC DOES NOT REWARD HEDGING. It rewards ADJUDICATION** ("Critical Evaluation of Evidence and Synthesis of
  Competing Theories"). Our existing class-I contract (scripts/reflow_report.py) was built around hedging. REDESIGN IT.
- The judge NEVER sees our citations or bibliography (stripped pre-judging). Source quality can ONLY be signalled by
  naming authors/venues IN PROSE.
- Measurement: judge SD 0.0074; k=5 paired resolves +0.0094 at 2 sigma. A report->report transform of a banked
  artifact has ZERO generation noise — cheapest, most sensitive arm available.

Design the plan. Ground EVERY lever in a verbatim rubric criterion or a measured artifact fact. We lost an entire
night to proxy metrics — do not hand us another. Where uncertain, SEARCH (papers, GitHub, the artifacts at ${BOARD}).`,
  { schema: PLAN, model: 'fable', effort: 'max', label: 'fable:design-v2', phase: 'Design' }
)

phase('Attack')
const V = { type: 'object', required: ['refuted', 'reasoning'], properties: { refuted: { type: 'boolean' }, reasoning: { type: 'string' }, fix: { type: 'string' } } }
const LENSES = [
  'FABRICATION: does this lever create ANY path for an ungrounded fact, number, entity or attribution to reach the page? The faithfulness moat is not for sale — a lever that leaks is unshippable at ANY score. Trace the concrete path.',
  'JUDGE-INVISIBILITY: RACE strips citations and the bibliography, and scores our report SIDE BY SIDE against a 0.5102 reference in ONE call. Would the judge actually SEE and REWARD this — and would it move a criterion from the "6-8 Good" band into "8-10 Excellent"? There is NO credit for being a better 7.',
  'PROXY RELAPSE: is this lever secretly a PROXY (word count, section count, citation count, "density") dressed up as a rubric target? We lost a night to exactly this. Also: does it just imitate a winner\'s SURFACE (bullets, tables, length) rather than the substance? Note sourcery ships 106 bullets and beats the reference; cellcog ships 0 — surface features are NOT the lever.',
  'THE PRIOR NEGATIVE + NOISE: our one previous "insight directive" A/B scored 0.4094 vs a 0.4447 control — it made things WORSE. Is this genuinely different, or the same idea in new clothes? And is the claimed gain above the +0.0094 resolvable floor?',
]
const attacked = await parallel((design?.levers ?? []).map(l => () =>
  parallel(LENSES.map((lens, j) => () =>
    agent(`Try HARD to REFUTE this lever. Default refuted=true if uncertain. Read ${BRIEF}, the artifacts at ${BOARD}, and the grader source if needed.

LEVER: ${l.name} (${l.id})
RUBRIC CRITERION CLAIMED: ${l.rubric_criterion} [${l.dimension}]
CHANGE: ${l.change}
CLAIMED: ${l.expected_points}
ADMITTED FAILURE MODE: ${l.how_it_fails}
FAITHFULNESS CONTRACT: ${design.faithfulness_contract}

ATTACK THROUGH THIS LENS:
${lens}`,
      { schema: V, effort: 'high', label: `refute:${l.id}#${j + 1}`, phase: 'Attack' })
  )).then(vs => {
    const v = vs.filter(Boolean); const r = v.filter(x => x.refuted).length
    return { lever: l, refuted: r, total: v.length, survives: r < 2, objections: v }
  })
))
const A = attacked.filter(Boolean)
log(`design: ${design?.levers?.length ?? 0} levers | survived: ${A.filter(a => a.survives).length} | refuted: ${A.filter(a => !a.survives).length}`)

phase('Final')
const final = await agent(
  `Your plan was attacked on four lenses: FABRICATION, JUDGE-INVISIBILITY, PROXY-RELAPSE, and PRIOR-NEGATIVE/NOISE.

${JSON.stringify(A.map(a => ({ lever: a.lever.name, id: a.lever.id, survives: a.survives, votes: `${a.refuted}/${a.total}`, objections: a.objections.map(o => ({ refuted: o.refuted, why: o.reasoning, fix: o.fix })) })), null, 1).slice(0, 40000)}

Rewrite the FINAL plan:
- DROP what was refuted unless you can rebut with evidence from the artifacts or the grader source (quote it).
- Order it: what do we build FIRST, and what is the single cheapest arm that tests the core thesis?
  (Remember: a report->report transform of the banked rank10 artifact costs ZERO compose runs and has ZERO
  generation noise. Prefer it for the first arm.)
- The faithfulness contract must be AIRTIGHT and must target ADJUDICATION, not hedging.
- Honest total from 0.4382. Does it reach 0.54? If not, name the residual and what a later wave must do.
- A KILL RULE that stops us building on a dead thesis.`,
  { schema: PLAN, model: 'fable', effort: 'max', label: 'fable:final-v2', phase: 'Final' }
)
return { study: S, design_v1: design, attack: A.map(a => ({ lever: a.lever.name, survives: a.survives, votes: `${a.refuted}/${a.total}` })), final }
