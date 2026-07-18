export const meta = {
  name: 'fable-architecture-build-plan',
  description: 'Fable turns the two-tier-claim / comparison-matrix / document-architecture thesis into a concrete, code-level, buildable plan against the real POLARIS source',
  phases: [
    { title: 'Recon', detail: 'read the actual writer + strict_verify code to find the real seams' },
    { title: 'Design', detail: 'Fable designs the two-tier claim contract + comparison matrix + doc architecture' },
    { title: 'Attack', detail: 'skeptics attack the design for faithfulness holes and score-invisibility' },
    { title: 'Build plan', detail: 'final ordered, file-level build plan with kill rules' },
  ],
}

const FW = '/home/polaris/wt/flywheel'

const RECON_SCHEMA = {
  type: 'object',
  required: ['seams', 'notes'],
  properties: {
    seams: {
      type: 'array',
      items: {
        type: 'object',
        required: ['concern', 'file', 'symbol', 'lines', 'what_it_does', 'how_it_blocks_synthesis'],
        properties: {
          concern: { type: 'string', description: 'e.g. strict_verify gate | writer prompt | outline/section structure | evidence assignment | dedup' },
          file: { type: 'string' }, symbol: { type: 'string' }, lines: { type: 'string' },
          what_it_does: { type: 'string' },
          how_it_blocks_synthesis: { type: 'string', description: 'Concretely: would an interpretive sentence ("this discrepancy may reflect adoption lags") survive this code? Why/why not?' },
        },
      },
    },
    notes: { type: 'string' },
  },
}

phase('Recon')
const RECON = [
  { k: 'strict_verify', q: `Find the EXACT code path that verifies a generated sentence against evidence spans and DROPS it if unsupported (strict_verify / B11 / span-grounding / kept_fraction / no_provenance_token). Read it properly. Report: where a sentence is admitted or killed, what the admission predicate is, and precisely what happens to a sentence that is an INFERENCE ACROSS TWO SOURCES (no single span supports it). Quote the predicate.` },
  { k: 'writer_prompt', q: `Find the section-writer prompt(s) — the rules the model is given (rule #8 sentence target, rule #9 distinct sources, the mechanism rule, PG_SECTION_SENTENCE_TARGET / PG_SECTION_DISTINCT_SOURCES / PG_WRITER_TOPN_EV_PER_SECTION selector seam). Quote the actual rule text. Report where paragraphing/structure is (or is not) specified, and whether the writer is EVER told to compare or interpret sources rather than report them.` },
  { k: 'structure', q: `Find where the report's document structure is produced: outline -> sections -> markdown rendering (multi_section, section headings, how paragraphs are emitted, whether H3/subsections/tables/bullets are possible at all). Report the exact seam where we could emit H3 subsections, ~150-word topic-sentence paragraphs, and a markdown comparison table.` },
  { k: 'evidence_assign', q: `Find how evidence rows are assigned to sections and handed to the writer (the "menu"/basket/ev_id assignment, global evidence assignment, topic judge dispositions). Report the exact structure of an evidence row (its fields) — we need to know what metadata exists per finding (technology? unit of analysis? outcome? method? industry? geography?) to build a comparison matrix, and what would have to be DERIVED because it is not stored.` },
]
const recon = await parallel(RECON.map(r => () =>
  agent(`You are reading the REAL POLARIS codebase at ${FW}. Do not speculate — open the files and quote them.

${r.q}

Ground everything in file:line. If something does not exist, say so plainly — that is a finding.`,
    { schema: RECON_SCHEMA, effort: 'high', label: `recon:${r.k}`, phase: 'Recon' })
))
const recon_ok = recon.filter(Boolean)
log(`recon complete: ${recon_ok.reduce((n, r) => n + (r.seams?.length ?? 0), 0)} seams located`)

const DESIGN_SCHEMA = {
  type: 'object',
  required: ['thesis', 'changes', 'faithfulness_contract', 'expected_gain', 'kill_rule'],
  properties: {
    thesis: { type: 'string' },
    faithfulness_contract: { type: 'string', description: 'The NEW verification contract, stated precisely enough to implement. What makes an inference sentence legal? What still gets killed? How do we guarantee we have not opened a hallucination hole?' },
    changes: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'name', 'file', 'seam', 'change', 'dimension', 'weight', 'expected_points', 'how_it_fails', 'test'],
        properties: {
          id: { type: 'string' }, name: { type: 'string' },
          file: { type: 'string', description: 'real file:line from recon' },
          seam: { type: 'string' },
          change: { type: 'string', description: 'concrete: what code/prompt changes, and how it is gated (env flag, default-off)' },
          dimension: { type: 'string' }, weight: { type: 'number' },
          expected_points: { type: 'string' },
          how_it_fails: { type: 'string' },
          test: { type: 'string', description: 'the cheap test that proves it fired BEFORE we pay for a full compose+score' },
        },
      },
    },
    expected_gain: { type: 'string', description: 'Honest total from 0.42. Does it reach 0.5265? If not, say how short and what the residual is.' },
    kill_rule: { type: 'string' },
  },
}

phase('Design')
const design = await agent(
  `You are the architect for POLARIS's push to SOTA on DeepResearch Bench (RACE). Read /home/polaris/polaris_project/SOTA_REVIEW_BRIEF.md first, then design.

MEASURED GROUND TRUTH (all verified tonight, do not re-litigate):
- Every depth arm scored: baseline 0.4052, Rank7 0.4041, Rank8 0.3957, Rank9 0.4155, Rank10 0.4313, Rank11 0.4133.
  Rank9/Rank10 are the SAME config => 0.0158 IS the noise floor. Ranks 9/10/11 are indistinguishable (~0.42).
  The whole night's 2.7x depth push bought ~ONE noise width. LENGTH AND DEPTH ARE DEAD.
- SOTA = 0.5265 (ADORE). Human reference = 0.5000. We are at ~0.42. Gap ~10 points.
- **RACE DELETES THE BIBLIOGRAPHY AND EVERY [n] CITATION MARKER BEFORE JUDGING** (utils/clean_article.ArticleCleaner).
  VERIFIED: our 9,300-word submission became 7,692 words; 345 [n] markers -> 0; 105-entry bibliography -> deleted;
  "(also mirrored)" 25 -> 0; "(tier T6)" labels 105 -> 0.
  => ALL bibliography-side work scores ZERO. Source compliance can ONLY be reached via VENUE NAMES IN THE RUNNING PROSE.
- Judge-visible structure, ours vs the 0.5000 reference:
  OURS: 7,692 words, 12 body paragraphs, avg 633 words/para, 0 H3, 0 tables, 0 bullets.
  REFERENCE: 9,029 words, 59 paragraphs, avg 142 words/para, 24 H3, 10 tables, 91 bullets.
- Dimension weights: INSIGHT 0.32 (our worst, ~0.42), comprehensiveness 0.29, instruction_following 0.25, readability 0.14.
- Our report literally ships, inside the section graded for critical synthesis: "No contradictions were detected by the pipeline."
- PRIOR NEGATIVE, RESPECT IT: the one previous "insight directive" A/B scored 0.4094 vs a 0.4447 control. It made things WORSE.

THE THESIS TO MAKE BUILDABLE:
POLARIS is an extraction-grounded FACT CONVEYOR. strict_verify requires every sentence to be span-grounded in ONE source,
which STRUCTURALLY FORBIDS the sentence that earns insight — the cross-source inference ("this discrepancy may reflect
implementation lags inherent to general-purpose technologies"). We did not fail to write synthesis; we built a machine
that CANNOT. Design the fix:
  (1) TWO-TIER CLAIM SYSTEM: FACT (span-grounded, unchanged) vs INFERENCE (premises each grounded; the inference itself
      is licensed by its premises, not by a span; phrased as interpretation). Faithfulness must NOT weaken — no ungrounded
      assertion may enter. State the contract precisely enough to implement and to audit.
  (2) EVIDENCE COMPARISON MATRIX: normalise findings by technology / mechanism / UNIT OF ANALYSIS / outcome / horizon /
      industry / geography / method, then generate paragraphs from COMPARISON BUNDLES rather than single source cards.
  (3) DOCUMENT ARCHITECTURE: H3 subsections, ~150-word topic-sentence-first paragraphs, a study-comparison table, bullets.
  (4) A SECTORAL section (comprehensiveness "industry scope" = 0.25 weight; we currently have ZERO industry-organised content).

THE REAL SEAMS IN THE CODE (from recon of the actual repo — build against THESE, quote file:line):
${JSON.stringify(recon_ok, null, 1).slice(0, 26000)}

Every change must be ENV-GATED and DEFAULT-OFF (house rule; the codebase's biggest wins were dark flags).
Every change needs a CHEAP TEST that proves the mechanism FIRED before we pay for a ~65-minute compose + score.
Be honest in expected_gain: if this does not reach 0.5265, say so and name the residual.`,
  { schema: DESIGN_SCHEMA, model: 'fable', effort: 'max', label: 'fable:architect', phase: 'Design' }
)

phase('Attack')
const V = {
  type: 'object', required: ['refuted', 'reasoning'],
  properties: { refuted: { type: 'boolean' }, reasoning: { type: 'string' }, fix: { type: 'string' } },
}
const LENSES = [
  'HALLUCINATION HOLE: the two-tier contract exempts inference sentences from span-grounding. Show the concrete path by which an UNGROUNDED or FALSE claim now reaches the report. If faithfulness can regress, this design is unshippable — POLARIS\'s whole moat is that it does not hallucinate. Be specific.',
  'SCORE-INVISIBILITY: RACE strips citations and the bibliography, and judges the CLEANED prose against a reference that scores 0.5000. Would the judge actually SEE and REWARD this change? Recall the prior insight-directive A/B went the WRONG way (0.4094 vs 0.4447 control) — explain why this would not repeat.',
  'THE PRIOR NEGATIVE + NOISE: effect must exceed a +/-0.016 noise floor at n=1. Is the claimed gain distinguishable? And is this genuinely different from the STEP-3 insight directive that already failed, or is it the same idea with new words?',
]
const attacked = await parallel((design?.changes ?? []).map(c => () =>
  parallel(LENSES.map((lens, j) => () =>
    agent(`Try HARD to REFUTE this proposed change to the POLARIS pipeline. Default refuted=true if uncertain. Read code at ${FW} if needed.

CHANGE: ${c.name} (${c.id})
FILE/SEAM: ${c.file} :: ${c.seam}
WHAT: ${c.change}
CLAIMS: ${c.expected_points} on ${c.dimension} (w=${c.weight})
FAILURE MODE THEY ADMIT: ${c.how_it_fails}
NEW FAITHFULNESS CONTRACT: ${design.faithfulness_contract}

ATTACK THROUGH THIS LENS:
${lens}`,
      { schema: V, effort: 'high', label: `refute:${c.id}#${j + 1}`, phase: 'Attack' })
  )).then(vs => {
    const v = vs.filter(Boolean)
    const r = v.filter(x => x.refuted).length
    return { change: c, refuted_votes: r, total: v.length, survives: r < 2, objections: v.map(x => ({ refuted: x.refuted, reasoning: x.reasoning, fix: x.fix })) }
  })
))
const A = attacked.filter(Boolean)
log(`design: ${design?.changes?.length ?? 0} changes | survived: ${A.filter(a => a.survives).length} | refuted: ${A.filter(a => !a.survives).length}`)

phase('Build plan')
const final = await agent(
  `Your architecture was attacked by independent skeptics on three lenses: (1) does it open a HALLUCINATION hole, (2) can the RACE judge actually SEE it, (3) is it above the noise floor / is it just the failed STEP-3 insight directive again.

RESULTS:
${JSON.stringify(A.map(a => ({ change: a.change.name, id: a.change.id, survives: a.survives, refuted_votes: `${a.refuted_votes}/${a.total}`, objections: a.objections })), null, 1).slice(0, 30000)}

Produce the FINAL BUILD PLAN. Rules:
- DROP anything refuted unless you can rebut with code evidence (quote file:line).
- The faithfulness contract must be AIRTIGHT. If the skeptics found a hallucination path, close it explicitly or drop the tier.
- Order by: what we build FIRST tomorrow, as a single bundled arm (structure + prose-mode together — they touch the same writer seam and individually sit under the noise floor).
- Give the CHEAP MECHANISM TESTS that prove each change fired, BEFORE any 65-minute compose.
- State the honest expected total from ~0.42, and whether it reaches 0.5265. If it does not, name exactly what the residual is and what a SECOND wave would have to do.
- Give the KILL RULE that stops us building on a dead thesis for weeks.`,
  { schema: DESIGN_SCHEMA, model: 'fable', effort: 'max', label: 'fable:build-plan', phase: 'Build plan' }
)

return { recon: recon_ok, design_v1: design, attack: A.map(a => ({ change: a.change.name, survives: a.survives, votes: `${a.refuted_votes}/${a.total}` })), build_plan: final }
