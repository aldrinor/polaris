export const meta = {
  name: 'fable-cellcog-plan-v3',
  description: 'Fable designs the path to the CELLCOG profile (0.5578) — debiased, free to change composer/retrieval, adversarially attacked including for its own prior tunnel vision',
  phases: [
    { title: 'Recheck', detail: 'independently re-derive the brief\'s claims — it may be wrong' },
    { title: 'Design', detail: 'the path to the cellcog profile, composer/retrieval changes allowed' },
    { title: 'Attack', detail: 'skeptics attack, including an explicit anti-tunnel-vision lens' },
    { title: 'Final', detail: 'hardened plan + kill rules' },
  ],
}

const PP = '/home/polaris/polaris_project'
const BRIEF = `${PP}/SOTA_BRIEF_V3.md`
const BOARD = `${PP}/drb_corpus/gpt55_board`
const FW = '/home/polaris/wt/flywheel'
const OURS = `${FW}/outputs/rank10_sections_compose/report.md`

const CHK = {
  type: 'object',
  required: ['confirmed', 'refuted', 'missed'],
  properties: {
    confirmed: { type: 'array', items: { type: 'string' } },
    refuted: { type: 'array', items: { type: 'string' }, description: 'Claims in BRIEF V3 that are WRONG. Say so — this is the most valuable output.' },
    missed: { type: 'array', items: { type: 'string' }, description: 'Things in the artifacts that NOBODY has noticed yet.' },
  },
}

phase('Recheck')
const recheck = await parallel([
  () => agent(`Read ${BRIEF}. **DO NOT TRUST IT.** Independently re-derive its central factual claims from the raw artifacts.

The operator caught BOTH designers (you included) in tunnel vision last round, and one of your own measurements was
WRONG (you called cellcog "92% uncited" — it is not uncited, it cites IN PROSE with author-year). So: verify.

CHECK, from ${BOARD}/cellcog-max.jsonl (id=72) and ${OURS} (body only — split at '## References'):
  1. cellcog: 98 sources, 13,580 body words, 31 H3, 75w median paragraph, 133 in-prose author-year attributions,
     65 journal names, ZERO [n] markers. TRUE?
  2. POLARIS: 97 sources, 7,742 words, 0 H3, 677w median paragraph, 10 author-year, 1 journal name, 240 [n] markers. TRUE?
  3. THE BIG CLAIM: RACE's ArticleCleaner (${FW}/third_party/deep_research_bench/utils/clean_article.py) deletes
     [n] markers and the reference list, but CANNOT delete "Acemoglu and Restrepo (2018)" because it is ordinary prose.
     **ACTUALLY RUN THE CLEANER** on cellcog-max's task-72 article and on ours. Count what survives in each.
     Does cellcog's attribution really survive? Does ours really vanish? THIS IS THE LOAD-BEARING CLAIM OF THE WHOLE PLAN.
  4. What fraction of cellcog's sentences are ANALYSIS (no source attached at all) vs GROUNDED (attached to a named
     study)? Do it properly this time — author-year in prose COUNTS as grounded.
Report anything the brief gets WRONG. That is the most valuable thing you can produce.`,
    { schema: CHK, effort: 'max', label: 'recheck:the-attribution-claim', phase: 'Recheck' }),

  () => agent(`Read ${BRIEF}. Then find what EVERYONE has missed — including the operator and me.

Read cellcog-max (${BOARD}/cellcog-max.jsonl id=72, the 0.5578 #1) and at least 2 other >0.52 systems
(bodhi 0.5441, WhaleCloud 0.5396, lunon 0.5406, dalpha 0.5252) on task 72, END TO END. Compare to ${OURS}.

We have already noticed: structure (H3s, short paragraphs), in-prose attribution, adjudication/synthesis prose,
the false "sources vs thinking" trade-off. **DO NOT re-report those.**

FIND WHAT IS STILL INVISIBLE TO US:
  - What do the winners do that we have not named at all?
  - Read their OPENINGS and their CLOSINGS specifically — the judge reads those first and last.
  - How do they handle the task's explicit instructions (4IR framing, "various industries", "journal articles only")?
  - Is there a rhetorical move, an organising principle, or an argumentative structure we have not spotted?
  - Look for what is ABSENT from their reports that is PRESENT in ours (and hurting us).
Quote verbatim. Be specific. Surprise me.`,
    { schema: CHK, effort: 'max', label: 'recheck:what-is-still-missed', phase: 'Recheck' }),
])
const R = recheck.filter(Boolean)
log(`recheck: ${R.flatMap(r => r.refuted ?? []).length} brief claims REFUTED | ${R.flatMap(r => r.missed ?? []).length} new findings`)

const PLAN = {
  type: 'object',
  required: ['diagnosis', 'faithfulness_contract', 'levers', 'expected_total', 'ceiling_honesty', 'kill_rule'],
  properties: {
    diagnosis: { type: 'string' },
    faithfulness_contract: { type: 'string', description: 'Must admit cellcog-style adjudication (which adds NO new facts) while guaranteeing zero fabrication.' },
    levers: { type: 'array', items: { type: 'object', required: ['id', 'name', 'rubric_criterion', 'change', 'where', 'expected_points', 'how_it_fails', 'cheap_test', 'effort'], properties: {
      id: { type: 'string' }, name: { type: 'string' },
      rubric_criterion: { type: 'string' },
      change: { type: 'string' },
      where: { type: 'string', description: 'file:line — composer, retrieval, or post-pass. You are FREE to change the composer.' },
      expected_points: { type: 'string' }, how_it_fails: { type: 'string' }, cheap_test: { type: 'string' },
      effort: { type: 'string', enum: ['small', 'medium', 'large'] },
    } } },
    expected_total: { type: 'string', description: 'Honest sum from 0.4382. Does it reach 0.5441 (bodhi) / 0.5578 (cellcog)?' },
    ceiling_honesty: { type: 'string' },
    kill_rule: { type: 'string' },
  },
}

phase('Design')
const design = await agent(
  `Design POLARIS's path to the **CELLCOG PROFILE (0.5578)**. Read ${BRIEF} in full — INCLUDING §0, which documents how
your last plan was tunnel-visioned.

INDEPENDENT RECHECK OF THE BRIEF (just completed — the brief may be WRONG, these agents checked it):
${JSON.stringify(R, null, 1).slice(0, 40000)}

THE FRAME YOU MUST NOT REPEAT:
- Last time you anchored on "rewrite the banked report" and concluded 0.54 was unreachable. **That was a fact about your
  framing, not about the world.** You are now FREE to change the COMPOSER and the RETRIEVAL. A 65-minute compose is an
  acceptable cost. Name file:line.
- Last time you accepted a "sources vs thinking" trade-off and proposed DELETING words. **cellcog has 98 sources (we have
  97), writes 13,580 words, and is mostly analysis. There is no trade-off.** Design for BOTH.
- **The cheapest lever on the board, which you walked straight past:** we put 240 [n] markers in the text and RACE
  DELETES ALL OF THEM. cellcog writes "Acemoglu and Restrepo (2018, *American Economic Review*)" — ordinary prose the
  cleaner cannot touch. The judge sees cellcog as rigorously sourced and sees US as having NO SOURCES AT ALL, on a task
  that demands "only high-quality journal articles". We already hold authors+venues in bibliography.json.

THE REAL BOTTLENECK: our entailment gate (entailment_judge.py:588 NEUTRAL clause) deletes any sentence introducing "a
mechanism not present in the SPAN" — i.e. every cross-source inference. **That is why we run out of things to say at
7,742 words.** cellcog writes 13,580 off the same evidence because it can REASON over it.
BUT: cellcog's synthesis prose adds NO new facts (see §3 of the brief for a verbatim example — it RANKS AND RELATES
ideas already on the page). **The moat and the target are compatible. Design the contract that admits exactly that.**

Ground every lever in a verbatim rubric criterion or a measured artifact. Where uncertain, SEARCH.`,
  { schema: PLAN, model: 'fable', effort: 'max', label: 'fable:design-v3', phase: 'Design' }
)

phase('Attack')
const V = { type: 'object', required: ['refuted', 'reasoning'], properties: { refuted: { type: 'boolean' }, reasoning: { type: 'string' }, fix: { type: 'string' } } }
const LENSES = [
  'FABRICATION: trace a concrete path by which an ungrounded fact, number, entity or attribution reaches the page. The moat is not for sale — a lever that leaks is unshippable at ANY score.',
  'JUDGE-INVISIBILITY: RACE deletes all [n] markers and the reference list, then scores our report SIDE BY SIDE against a 0.5102 reference in ONE call. Would the judge SEE this, and would it push a criterion from the "6-8 Good" band into "8-10 Excellent"? There is no credit for being a better 7.',
  'PROXY RELAPSE / SURFACE MIMICRY: is this lever a proxy (word count, source count, H3 count, "density") dressed as a rubric target? Or is it copying a winner\'s SURFACE rather than its SUBSTANCE? Note bodhi wins with 33 sources and cellcog with 98 — surface features are NOT the lever.',
  'TUNNEL VISION (the lens that caught you last time): is this plan silently CONSTRAINED by an assumption nobody tested? Specifically: does it assume the banked artifact is the substrate? does it assume a length cap? does it assume a breadth-vs-depth trade-off? does it assume our current retrieval is what we must write from? **Name the assumption the plan does not know it is making.**',
]
const attacked = await parallel((design?.levers ?? []).map(l => () =>
  parallel(LENSES.map((lens, j) => () =>
    agent(`Try HARD to REFUTE this lever. Default refuted=true if uncertain. Check the artifacts at ${BOARD} and the code at ${FW}.

LEVER: ${l.name} (${l.id})
RUBRIC CRITERION: ${l.rubric_criterion}
CHANGE: ${l.change}
WHERE: ${l.where}
CLAIMED: ${l.expected_points}
ADMITTED FAILURE: ${l.how_it_fails}
CONTRACT: ${design.faithfulness_contract}

ATTACK THROUGH THIS LENS:
${lens}`,
      { schema: V, effort: 'high', label: `refute:${l.id}#${j + 1}`, phase: 'Attack' })
  )).then(vs => {
    const v = vs.filter(Boolean); const r = v.filter(x => x.refuted).length
    return { lever: l, refuted: r, total: v.length, survives: r < 2, objections: v }
  })
))
const A = attacked.filter(Boolean)
log(`levers: ${design?.levers?.length ?? 0} | survived: ${A.filter(a => a.survives).length} | refuted: ${A.filter(a => !a.survives).length}`)

phase('Final')
const final = await agent(
  `Your plan was attacked on four lenses — including TUNNEL VISION, the one that caught you last round.

${JSON.stringify(A.map(a => ({ lever: a.lever.name, id: a.lever.id, survives: a.survives, votes: `${a.refuted}/${a.total}`, objections: a.objections.map(o => ({ refuted: o.refuted, why: o.reasoning, fix: o.fix })) })), null, 1).slice(0, 40000)}

Write the FINAL plan to the CELLCOG PROFILE (0.5578).
- DROP what was refuted unless you can rebut with artifact/code evidence (quote it).
- ORDER it: what runs FIRST (cheapest, most diagnostic), and what the FIRST COMPOSE-LEVEL arm is.
- The faithfulness contract must be AIRTIGHT and must admit cellcog-style adjudication (no new facts, ranks and relates
  what is already on the page).
- HONEST TOTAL from 0.4382. Does it reach 0.5441 (bodhi) or 0.5578 (cellcog)? If not, name the residual precisely.
- KILL RULE that stops us building on a dead thesis.
- And state explicitly: **what assumption is this final plan still making that we have not tested?**`,
  { schema: PLAN, model: 'fable', effort: 'max', label: 'fable:final-v3', phase: 'Final' }
)
return { recheck: R, design_v1: design, attack: A.map(a => ({ lever: a.lever.name, survives: a.survives, votes: `${a.refuted}/${a.total}` })), final }
