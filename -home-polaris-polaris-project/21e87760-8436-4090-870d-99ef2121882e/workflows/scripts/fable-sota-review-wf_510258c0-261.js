export const meta = {
  name: 'fable-sota-review',
  description: 'Fable reads the full report + reference line-by-line, plans the climb to SOTA 0.5265, then adversarially verifies its own plan',
  phases: [
    { title: 'Deep read', detail: 'Fable reads BOTH full documents end to end and drafts the SOTA plan' },
    { title: 'Attack', detail: 'independent skeptics try to refute each lever' },
    { title: 'Harden', detail: 'Fable rewrites the plan keeping only what survived' },
  ],
}

const BRIEF = '/home/polaris/polaris_project/SOTA_REVIEW_BRIEF.md'
const OURS  = '/home/polaris/wt/flywheel/outputs/rank10_sections_compose/report.md'
const REF   = '/home/polaris/polaris_project/RACE_REFERENCE_task72.md'
const CRIT  = '/home/polaris/polaris_project/race_task72_criteria.txt'

const PLAN_SCHEMA = {
  type: 'object',
  required: ['reference_vs_us', 'levers', 'exhausted', 'headline'],
  properties: {
    headline: { type: 'string', description: 'One paragraph: the single most important thing standing between us and SOTA.' },
    reference_vs_us: {
      type: 'array', description: 'What the REFERENCE report does that OUR report does not. Concrete, quoted, line-level.',
      items: {
        type: 'object', required: ['what_reference_does', 'what_we_do', 'evidence', 'dimension'],
        properties: {
          what_reference_does: { type: 'string' },
          what_we_do: { type: 'string' },
          evidence: { type: 'string', description: 'Quote both. Real lines from both files.' },
          dimension: { type: 'string' },
        },
      },
    },
    levers: {
      type: 'array', description: 'Ordered plan, highest points-per-effort first.',
      items: {
        type: 'object',
        required: ['name', 'dimension', 'criterion', 'weight', 'change', 'expected_points', 'why', 'how_it_fails', 'how_to_measure', 'effort'],
        properties: {
          name: { type: 'string' },
          dimension: { type: 'string', description: 'insight (0.32) | comprehensiveness (0.29) | instruction_following (0.25) | readability (0.14)' },
          criterion: { type: 'string', description: 'the exact weighted sub-criterion from the criteria file' },
          weight: { type: 'number' },
          change: { type: 'string', description: 'The concrete code/prompt change. Name files or prompt rules where possible.' },
          expected_points: { type: 'string', description: 'Expected RACE gain, vs a +/-0.016 noise floor.' },
          why: { type: 'string' },
          how_it_fails: { type: 'string', description: 'The honest failure/backfire mode.' },
          how_to_measure: { type: 'string' },
          effort: { type: 'string', enum: ['small', 'medium', 'large'] },
        },
      },
    },
    exhausted: { type: 'array', items: { type: 'string' }, description: 'Levers that are DEAD. Say so plainly.' },
  },
}

const VERDICT_SCHEMA = {
  type: 'object',
  required: ['lever', 'refuted', 'reasoning'],
  properties: {
    lever: { type: 'string' },
    refuted: { type: 'boolean', description: 'true if this lever will NOT deliver the claimed points' },
    reasoning: { type: 'string' },
    salvage: { type: 'string', description: 'If refuted, what (if anything) survives.' },
  },
}

phase('Deep read')
const plan = await agent(
  `You are the deep-thinking gate for the POLARIS research pipeline. We are chasing SOTA on DeepResearch Bench (RACE).

READ, IN FULL, END TO END — every single line, no skimming, no sampling, no "representative excerpts":
1. ${BRIEF}   (the brief. It contains a CORRECTED claim — treat every claim in it as a HYPOTHESIS to verify, not fact. It has been wrong once already tonight.)
2. ${OURS}    (OUR report, Rank10 — the arm that actually scored 0.4313)
3. ${REF}     (the HUMAN REFERENCE report — 9,029 words. This is what RACE scores us AGAINST. Read it as carefully as our own.)
4. ${CRIT}    (the full weighted grading criteria)

CRITICAL METHOD NOTE: our report ENDS with a numbered "## References" bibliography. Any count you make over the whole file will silently re-read the bibliography as prose. This has already produced TWO false findings tonight. Split body from references before you count anything, and say which you counted.

The scoreboard: we are at 0.4313. The human reference = 0.5000. SOTA (ADORE) = 0.5265. Judge noise = +/-0.016.
Dimension weights: insight 0.32, comprehensiveness 0.29, instruction_following 0.25, readability 0.14.
Length is CLOSED: reference is 9,029 words, we are 9,194. More words cannot help.

We spent all night optimising proxies (word count, verified sentences, distinct works, density) and the RACE score barely moved. DO NOT hand us another proxy. Every lever must name the weighted criterion it moves and how it would be falsified.

The highest-value thing you can produce: a precise, quoted, line-level account of what the REFERENCE does that WE DO NOT — especially on INSIGHT (0.32, our worst dimension and the heaviest). Our pipeline guarantees every sentence is GROUNDED (strict_verify) but nothing rewards SYNTHESIS, contrast of competing findings, or a thesis. Test that hypothesis against the two texts.`,
  { schema: PLAN_SCHEMA, model: 'fable', effort: 'max', label: 'fable:deep-read', phase: 'Deep read' }
)

phase('Attack')
const LENSES = [
  'MEASUREMENT: would this lever actually move the RACE judge, or only an internal proxy? Recall RACE is reference-based: Overall = target/(target+reference). A change that improves our report but that the JUDGE cannot see, or that the reference ALSO does well, yields ~0 points.',
  'BACKFIRE: could this lever LOWER another dimension? Depth levers already cost us readability. Weights: insight .32, comprehensiveness .29, instruction_following .25, readability .14.',
  'NOISE: is the claimed gain distinguishable from the measured +/-0.016 noise floor on a single task? If not, it is unfalsifiable as specified.',
]
const attacked = await parallel((plan?.levers ?? []).map((lv, i) => () =>
  parallel(LENSES.map((lens, j) => () =>
    agent(
      `Try HARD to REFUTE this proposed lever for improving a RACE score. Default to refuted=true when uncertain.

LEVER: ${lv.name}
TARGETS: ${lv.dimension} / ${lv.criterion} (weight ${lv.weight})
CHANGE: ${lv.change}
CLAIMED GAIN: ${lv.expected_points}
CLAIMED FAILURE MODE: ${lv.how_it_fails}

ATTACK IT THROUGH THIS LENS:
${lens}

Context: our report ${OURS} scored 0.4313. Reference ${REF} = 0.5000 by definition. SOTA = 0.5265.
Read the files if you need to check a claim. Be adversarial, concrete, and brief.`,
      { schema: VERDICT_SCHEMA, effort: 'high', label: `refute:${lv.name.slice(0, 28)}#${j + 1}`, phase: 'Attack' }
    )
  )).then(vs => {
    const votes = vs.filter(Boolean)
    const refuted = votes.filter(v => v.refuted).length
    return { lever: lv, refuted_votes: refuted, total_votes: votes.length, survives: refuted < 2, verdicts: votes }
  })
))

const survivors = attacked.filter(Boolean).filter(a => a.survives)
const killed    = attacked.filter(Boolean).filter(a => !a.survives)
log(`levers proposed: ${plan?.levers?.length ?? 0} | survived attack: ${survivors.length} | refuted: ${killed.length}`)

phase('Harden')
const hardened = await agent(
  `You proposed a plan to take POLARIS from RACE 0.4313 to SOTA 0.5265. Independent skeptics then attacked every lever through three lenses (can the JUDGE see it / does it BACKFIRE on another dimension / is it above the +/-0.016 NOISE floor).

SURVIVED (majority of skeptics could not refute):
${JSON.stringify(survivors.map(s => ({ lever: s.lever.name, change: s.lever.change, expected: s.lever.expected_points, refuted_votes: `${s.refuted_votes}/${s.total_votes}`, objections: s.verdicts.map(v => v.reasoning) })), null, 1)}

REFUTED (majority of skeptics killed it):
${JSON.stringify(killed.map(s => ({ lever: s.lever.name, refuted_votes: `${s.refuted_votes}/${s.total_votes}`, why: s.verdicts.filter(v => v.refuted).map(v => v.reasoning), salvage: s.verdicts.map(v => v.salvage).filter(Boolean) })), null, 1)}

Now rewrite the plan HONESTLY:
- DROP what was refuted, unless you can rebut the skeptic with evidence from the actual files (quote it).
- KEEP survivors, but fold in the objections raised against them — tighten the expected gain if a skeptic was partly right.
- The plan must ADD UP: state the realistic total expected gain from 0.4313 and say plainly whether it reaches 0.5265, or how far short it lands. If the levers do not sum to SOTA, SAY SO — that is a finding, not a failure.
- State what you would run FIRST tomorrow morning, and the single measurement that would prove or kill it.`,
  { schema: PLAN_SCHEMA, model: 'fable', effort: 'max', label: 'fable:harden', phase: 'Harden' }
)

return { plan_v1: plan, attack: attacked.filter(Boolean).map(a => ({ lever: a.lever.name, survives: a.survives, refuted_votes: `${a.refuted_votes}/${a.total_votes}` })), plan_final: hardened }
