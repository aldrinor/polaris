export const meta = {
  name: 'sol-v4-beat-sota',
  description: 'GPT-5.6 Sol designs the single full plan to BEAT 0.5578 — retrieval at the root, corrected faithfulness line, cellcog architecture',
  phases: [
    { title: 'Design', detail: 'Sol writes the complete plan' },
    { title: 'Attack', detail: 'skeptics attack every lever incl. bar-lowering' },
    { title: 'Final', detail: 'hardened single plan' },
  ],
}

const PP = '/home/polaris/polaris_project'
const BRIEF = `${PP}/SOTA_BRIEF_V4.md`
const BOARD = `${PP}/drb_corpus/gpt55_board`
const FW = '/home/polaris/wt/flywheel'

const PLAN = {
  type: 'object',
  required: ['diagnosis', 'retrieval', 'evidence_layer', 'synthesis_lane', 'composer', 'rules_to_drop', 'the_wheel', 'expected_total', 'ceiling_honesty', 'kill_rule'],
  properties: {
    diagnosis: { type: 'string' },
    retrieval: { type: 'string', description: 'Query generation -> search -> fetch -> select -> weight -> dedup -> consolidate. Journal-first, citation-graph expansion, COVERAGE MATRIX as the stopping condition. How many papers and how do we know when we have enough? Name files/lines.' },
    evidence_layer: { type: 'string', description: 'Cards: verbatim spans + declared fields (level/horizon/method/mechanism), canonical dedup, quality weighting.' },
    synthesis_lane: { type: 'string', description: 'The CORRECTED faithfulness line (a mechanism may be asserted if ANY cited source states it). What exactly may a sentence assert? What is still deleted?' },
    composer: { type: 'string', description: 'cellcog architecture: H2/H3/H4, ~100w paragraphs, in-prose journal-named attribution, epistemic labels, structured abstract, Scope-and-Methods, 4IR spine, industry coverage.' },
    rules_to_drop: { type: 'array', items: { type: 'object', properties: { rule: { type: 'string' }, where: { type: 'string' }, evidence_it_costs_score: { type: 'string' } } } },
    the_wheel: { type: 'string', description: 'fix -> compose -> score k=5 -> read prose line-by-line -> fix. The loop and its stopping condition.' },
    expected_total: { type: 'string', description: 'Honest sum from 0.4382. Does it BEAT 0.5578? If not, say so and name what is missing.' },
    ceiling_honesty: { type: 'string' },
    kill_rule: { type: 'string' },
  },
}

phase('Design')
const design = await agent(
  `Read ${BRIEF} IN FULL. It is the complete measured record. Then design ONE SINGLE COMPLETE PLAN to **BEAT 0.5578**.

THE OPERATOR'S DIRECTION, VERBATIM: "Why stick with bodhi class? Why not the top one? ... If we have any old rules
that hurt us from score, just drop it. If we don't have enough corpus to make us SOTA, then kick on the agentic
outline search, or we do better at the early query generation + search + fetch + select + weight + dedup +
consolidate, make them much much much better and richer so we are SOTA. Don't stuck with anything. I need one
single solid plan, unleash the full power at the beginning, then keep the hamster wheel running till we match SOTA
and beat SOTA."

**EVERY PREVIOUS PLAN — INCLUDING YOURS — QUIETLY LOWERED THE BAR TO MATCH WHAT HAD ALREADY BEEN BUILT.** Your v2
plan capped at 0.535-0.552 and declared 0.5578 "aggressive". Fable's capped at 0.48. Opus rationalised a 45-paper
corpus as "bodhi-class" because bodhi wins with 33. **THAT IS THE FAILURE MODE. DESIGN FOR #1.**

THE TWO CORRECTIONS THAT UNLOCK THIS:
1. **THE FAITHFULNESS LINE WAS DRAWN WRONG** (brief §3). bodhi's winning sentence CITES TWO SOURCES — an empirical
   null from one paper and a diffusion-lag MECHANISM stated by another. It is not fabricating; it is citing a theory
   paper for the mechanism and an empirical paper for the finding. **Our gate kills it because it checks the UNION
   of spans for literal presence.** The corrected line: a mechanism may be asserted if ANY cited source states it.
   Fabricating facts/numbers/attributions stays forbidden forever.
2. **OUR RETRIEVAL IS AIMED WRONG, NOT SHALLOW.** 997 rows / 919 URLs — but only 17 on-topic journal articles; the
   enriched corpus contains ResNet, the BMJ PRISMA checklist, and a 1974 Cognitive Psychology paper on reading.
   **We have an agentic retrieval loop (PG_AGENTIC_*, outline_agent) that was never pointed at this.** And keyword
   search PROVABLY cannot find this literature (Autor-Levy-Murnane, the field's most important paper, contains
   neither "AI" nor "labor market" in its title). **Citation-graph expansion does.**

Design the whole thing: retrieval at the root, the evidence layer, the synthesis lane, the composer, the rules to
DROP, and the wheel that runs until we beat 0.5578. Ground everything in the rubric text or a measured artifact.
Read the winners' artifacts at ${BOARD} and our code at ${FW}. Be honest about the ceiling — but do not lower the bar.`,
  { effort: 'max', label: 'sol:design-v4', phase: 'Design' }
)

phase('Attack')
const V = { type: 'object', required: ['refuted', 'reasoning'], properties: { refuted: { type: 'boolean' }, reasoning: { type: 'string' }, fix: { type: 'string' } } }
const LENSES = [
  'BAR-LOWERING: does this plan actually aim at BEATING 0.5578, or has it quietly retreated to parity / bodhi / "a good improvement"? Every previous plan did exactly that. Quote the place where it settles for less, or confirm it does not.',
  'FABRICATION: with the corrected faithfulness line (mechanism allowed if ANY cited source states it), trace a concrete path by which a FALSE claim now reaches the page. Inventing facts/numbers/attributions must remain impossible. If it leaks, the plan is unshippable.',
  'JUDGE-INVISIBILITY: RACE deletes all [n] markers and the bibliography, then scores our report side-by-side against a 0.5102 reference in ONE call. Would the judge SEE this lever, and would it push a criterion into the top band?',
  'RETRIEVAL REALITY: can the proposed retrieval ACTUALLY reach ~100 on-topic canonical journal articles with usable full text? We measured: keyword search returns junk, OpenAlex 429s our IP, half of paywalled papers have no OA copy. Is the plan\'s corpus target achievable, or is it a wish?',
]
const attacked = await parallel(LENSES.map((lens, j) => () =>
  agent(`Try HARD to REFUTE this plan through ONE lens. Default refuted=true if uncertain. Check ${BOARD} and ${FW}.

PLAN DIAGNOSIS: ${design?.diagnosis}
RETRIEVAL: ${design?.retrieval}
SYNTHESIS LANE: ${design?.synthesis_lane}
COMPOSER: ${design?.composer}
EXPECTED: ${design?.expected_total}

LENS:
${lens}`,
    { schema: V, effort: 'high', label: `refute:${j + 1}`, phase: 'Attack' })
))
log(`attack: ${attacked.filter(Boolean).filter(a => a.refuted).length}/4 lenses refuted the plan`)

phase('Final')
const final = await agent(
  `Your plan was attacked on four lenses — including BAR-LOWERING, the failure mode that caught every previous plan.

${JSON.stringify(attacked.filter(Boolean), null, 1).slice(0, 30000)}

Write the FINAL SINGLE PLAN to BEAT 0.5578. Rebut or fix every refutation with evidence (quote the artifact or the
code). Do NOT retreat to parity. If after honest analysis the plan lands below 0.5578, say EXACTLY where it falls
short and what would be required to close it — but do not silently re-target.`,
  { schema: PLAN, effort: 'max', label: 'sol:final-v4', phase: 'Final' }
)
return { design_v1: design, attack: attacked.filter(Boolean), final }
