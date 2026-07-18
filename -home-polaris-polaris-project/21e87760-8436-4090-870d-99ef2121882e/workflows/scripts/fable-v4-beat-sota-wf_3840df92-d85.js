export const meta = {
  name: 'fable-v4-beat-sota',
  description: 'Fable designs the single full plan to BEAT 0.5578 — retrieval at the root, corrected faithfulness line, cellcog architecture, adversarially hardened',
  phases: [
    { title: 'Ground', detail: 'independently verify the brief + read cellcog end to end' },
    { title: 'Design', detail: 'the complete plan to beat #1' },
    { title: 'Attack', detail: 'skeptics attack, incl. the bar-lowering lens' },
    { title: 'Final', detail: 'hardened single plan' },
  ],
}

const PP = '/home/polaris/polaris_project'
const BRIEF = `${PP}/SOTA_BRIEF_V4.md`
const BOARD = `${PP}/drb_corpus/gpt55_board`
const FW = '/home/polaris/wt/flywheel'

const G = {
  type: 'object',
  required: ['confirmed', 'refuted', 'missed'],
  properties: {
    confirmed: { type: 'array', items: { type: 'string' } },
    refuted: { type: 'array', items: { type: 'string' }, description: 'Claims in BRIEF V4 that are WRONG. Most valuable output.' },
    missed: { type: 'array', items: { type: 'string' }, description: 'What cellcog does that NOBODY has named yet — especially anything that explains 0.5578 vs the 0.54 pack.' },
  },
}

phase('Ground')
const ground = await parallel([
  () => agent(`Read ${BRIEF}. DO NOT TRUST IT — re-derive its load-bearing claims from the artifacts.

Specifically verify, from ${BOARD}/cellcog-max.jsonl (id=72) and ${FW}/outputs/rank10_sections_compose/report.md:
  1. Is the FAITHFULNESS CORRECTION in brief §3 right? Find bodhi's (and cellcog's) cross-source inference sentences
     in the raw text. **Do they cite BOTH the finding AND the mechanism?** Or do they genuinely assert mechanisms no
     source states? Quote 5+ examples verbatim. THIS IS THE LOAD-BEARING CLAIM OF THE WHOLE PLAN — if cellcog/bodhi
     really do fabricate mechanisms, we must know, because then matching them means fabricating.
  2. cellcog's actual source count, structure (H2/H3/H4), median paragraph, in-prose attribution counts, epistemic
     labels, structured abstract, Scope-and-Methods section. Confirm or correct every number.
  3. Our corpus: 997 rows / 919 URLs / 206 DOIs / only 17 ON-TOPIC journal works after enrichment. Verify.
Report anything the brief gets WRONG.`,
    { schema: G, model: 'fable', effort: 'max', label: 'ground:faithfulness-claim', phase: 'Ground' }),

  () => agent(`Read ${BRIEF}, then read cellcog-max task 72 (${BOARD}/cellcog-max.jsonl id=72) END TO END, and at
least two of {bodhi, lunon, WhaleCloud} for contrast.

**THE QUESTION: cellcog scores 0.5578. bodhi/lunon/WhaleCloud sit at 0.54. WHAT DOES cellcog DO THAT THEY DO NOT?**
That delta is the difference between #1 and the pack, and it is what we must copy AND EXCEED.

We already know: epistemic labels, Scope-and-Methods section, structured abstract, 31 H3 + 8 H4, ~100w paragraphs,
in-prose journal attribution, adjudication prose. **DO NOT re-report those. Find what is STILL invisible.**
Read its OPENING and CLOSING with special care (the judge reads those hardest). Look at how it handles the task's
explicit instructions (4IR, "various industries", "journal articles only"). Look for rhetorical moves, organising
principles, or evidence-presentation patterns nobody has named. Quote verbatim. Surprise me.`,
    { schema: G, model: 'fable', effort: 'max', label: 'ground:what-makes-cellcog-1', phase: 'Ground' }),
])
const GR = ground.filter(Boolean)
log(`ground: ${GR.flatMap(g => g.refuted ?? []).length} brief claims refuted | ${GR.flatMap(g => g.missed ?? []).length} new findings`)

const PLAN = {
  type: 'object',
  required: ['diagnosis', 'retrieval', 'evidence_layer', 'synthesis_lane', 'composer', 'rules_to_drop', 'the_wheel', 'expected_total', 'ceiling_honesty', 'kill_rule'],
  properties: {
    diagnosis: { type: 'string' },
    retrieval: { type: 'string', description: 'query-gen -> search -> fetch -> select -> weight -> dedup -> consolidate. Journal-first + citation-graph expansion. COVERAGE MATRIX as stopping condition. file:line.' },
    evidence_layer: { type: 'string' },
    synthesis_lane: { type: 'string', description: 'The CORRECTED faithfulness line. What may a sentence assert? What is still deleted?' },
    composer: { type: 'string' },
    rules_to_drop: { type: 'array', items: { type: 'object', properties: { rule: { type: 'string' }, where: { type: 'string' }, evidence_it_costs_score: { type: 'string' } } } },
    the_wheel: { type: 'string' },
    expected_total: { type: 'string', description: 'Honest sum from 0.4382. Does it BEAT 0.5578?' },
    ceiling_honesty: { type: 'string' },
    kill_rule: { type: 'string' },
  },
}

phase('Design')
const design = await agent(
  `Design ONE SINGLE COMPLETE PLAN to **BEAT 0.5578** (cellcog-max, #1). Read ${BRIEF} in full first.

INDEPENDENT GROUNDING (agents just re-derived the brief's claims — the brief may be WRONG):
${JSON.stringify(GR, null, 1).slice(0, 40000)}

THE OPERATOR: "Why stick with bodhi class? Why not the top one? ... If we have any old rules that hurt us from
score, just drop it. If we don't have enough corpus to make us SOTA, then kick on the agentic outline search, or we
do better at the early query generation + search + fetch + select + weight + dedup + consolidate... Don't stuck with
anything. Unleash the full power at the beginning, then keep the hamster wheel running till we match SOTA and beat SOTA."

**EVERY PREVIOUS PLAN — INCLUDING YOURS — LOWERED THE BAR.** Your last one capped at ~0.48 and called 0.54
unreachable, having silently assumed the banked report was the substrate. **DESIGN FOR #1. You may change ANYTHING:
retrieval, the composer, the entailment gate, the corpus, the rules.**

THE TWO UNLOCKS:
1. **THE FAITHFULNESS LINE WAS DRAWN WRONG.** bodhi's winning sentence cites TWO sources — an empirical null from
   one paper, a diffusion-lag MECHANISM stated by another. It is CITING a theory paper for the mechanism. That is
   scholarship, not fabrication. Our gate kills it because it checks the UNION of spans for literal presence.
   **Corrected line: a mechanism may be asserted if ANY cited source states it.** Fabricating facts/numbers/
   attributions stays forbidden. (${FW}/scripts/synthesis_contract.py currently requires the mechanism to come from
   the two papers being compared — TOO STRICT. Fix it.)
2. **RETRIEVAL IS AIMED WRONG, NOT SHALLOW.** 997 rows, 919 URLs — but only 17 on-topic journal articles. The
   corpus contains ResNet and a 1974 paper on reading automaticity. We have an agentic loop (PG_AGENTIC_*,
   outline_agent) never pointed at this. And keyword search PROVABLY cannot find this literature
   (Autor-Levy-Murnane: no "AI", no "labor market" in the title). Citation-graph expansion can.

Also design HOW WE BEAT cellcog rather than match it: its claims are ASSERTED; ours can be VERIFIED. The rubric
grades "Data and Factual Support" and "Depth and Representativeness of Literature Synthesized". **That is a
criterion we can OUT-SCORE it on.**

No proxies. Ground every lever in rubric text or a measured artifact.`,
  { schema: PLAN, model: 'fable', effort: 'max', label: 'fable:design-v4', phase: 'Design' }
)

phase('Attack')
const V = { type: 'object', required: ['refuted', 'reasoning'], properties: { refuted: { type: 'boolean' }, reasoning: { type: 'string' }, fix: { type: 'string' } } }
const LENSES = [
  'BAR-LOWERING (the lens that caught every previous plan, including yours): does this plan actually aim at BEATING 0.5578, or has it retreated to parity/bodhi/"a solid improvement"? Quote where it settles, or confirm it does not.',
  'FABRICATION: with the corrected line (mechanism allowed if ANY cited source states it), trace a concrete path by which a FALSE claim reaches the page. Fabricated facts/numbers/attributions must remain impossible.',
  'JUDGE-INVISIBILITY: RACE deletes all [n] markers and the bibliography, then scores us side-by-side against the 0.5102 reference in ONE call. Would the judge SEE each lever, and would it move a criterion into the top band?',
  'RETRIEVAL REALITY: can this ACTUALLY reach ~100 on-topic canonical journal articles WITH usable text? Measured: keyword search returns junk; OpenAlex 429s our IP; ~half of paywalled papers have no OA copy (we recovered only 36/70). Is the corpus target achievable or a wish?',
]
const attacked = await parallel(LENSES.map((lens, j) => () =>
  agent(`Try HARD to REFUTE this plan through ONE lens. Default refuted=true if uncertain. Check ${BOARD} and ${FW}.

DIAGNOSIS: ${design?.diagnosis}
RETRIEVAL: ${design?.retrieval}
SYNTHESIS: ${design?.synthesis_lane}
COMPOSER: ${design?.composer}
EXPECTED: ${design?.expected_total}
CEILING: ${design?.ceiling_honesty}

LENS:
${lens}`,
    { schema: V, effort: 'high', label: `refute:${j + 1}`, phase: 'Attack' })
))
log(`attack: ${attacked.filter(Boolean).filter(a => a.refuted).length}/4 refuted`)

phase('Final')
const final = await agent(
  `Your plan was attacked on four lenses — including BAR-LOWERING, which caught every previous plan.

${JSON.stringify(attacked.filter(Boolean), null, 1).slice(0, 30000)}

Write the FINAL SINGLE PLAN to BEAT 0.5578. Rebut or fix every refutation with evidence. Do NOT retreat.
If it honestly lands below 0.5578, say exactly where it falls short and what would close it — but do not silently
re-target. And state plainly: what assumption is this plan STILL making that we have not tested?`,
  { schema: PLAN, model: 'fable', effort: 'max', label: 'fable:final-v4', phase: 'Final' }
)
return { ground: GR, design_v1: design, attack: attacked.filter(Boolean), final }
