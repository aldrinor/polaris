export const meta = {
  name: 'opus-general-architecture-v2',
  description: 'Six Opus architects build ON Sol + Fable + the operator fixes to design a GENERAL research system that beats SOTA on any query',
  phases: [
    { title: 'Architect', detail: 'six independent deep designs, different angles, built on the foundation' },
    { title: 'Attack', detail: 'overfit / fabrication / judge-value / feasibility' },
    { title: 'Synthesise', detail: 'one plan' },
  ],
}

const PP = '/home/polaris/polaris_project'
const FW = '/home/polaris/wt/flywheel'
const BOARD = `${PP}/drb_corpus/gpt55_board`
const FOUND = `${PP}/sota_review/foundation`

const READ_FIRST = `
# READ THESE THREE FILES FIRST, IN FULL. THEY ARE YOUR FOUNDATION — BUILD ON THEM, DO NOT RE-DERIVE THEM.
1. ${FOUND}/SOL_PLAN_V4.md      — GPT-5.6 Sol's complete plan (coverage matrix, retrieval chain, working-paper
                                  text lane, the arithmetic: we need 1.62x the judge's points, INSIGHT alone
                                  needs 1.81x; the wheel; kill rules; three real bugs in our code).
2. ${FOUND}/FABLE_PLAN_V4.md    — Fable's complete plan (four sentence classes; mechanism-pool scoping; corpus-
                                  scoped gap claims; integrity gates) **PLUS ITS VERBATIM DECODE OF cellcog, the
                                  #1 system — the most valuable artifact we have.**
3. ${FOUND}/OPERATOR_FIXES.md   — **SEVEN CORRECTIONS NEITHER DESIGNER FOUND. NOT OPTIONAL.** The recency fix
                                  (date-filtered search — retires Sol's biggest risk); SELECT is the broken stage;
                                  scope must be DERIVED from the prompt; **BOTH PLANS ARE OVERFIT**; the
                                  faithfulness line; the load-bearing unknown; three critical code bugs.

Also available: ${PP}/SOTA_BRIEF_V4.md (all measurements), the winners' artifacts at ${BOARD},
our code at ${FW}, and the grader's own source at ${FW}/third_party/deep_research_bench/.
`;

const FRAME = `
# THE MISSION
Build a **research system that beats the state of the art on ANY question** — not a machine that answers task 72.
POLARIS = 0.4382. Highest KNOWN task-72 score = bodhi 0.5441. cellcog is #1 corpus-wide at 0.5578 (its task-72
score is unpublished; regression estimates ~0.556 +/- 0.019). Weights: INSIGHT .32 | COMPREH .29 | INSTR .25 | READ .14.
Judge noise SD 0.0074 => k=5 paired resolves +0.0094. NEVER score n=1.

# THE THREE HARD CONSTRAINTS ON YOUR DESIGN
1. **NOT OVERFIT.** Sol and Fable BOTH hardcode 15 anchor papers, a 10-section outline, an 8x10 coverage matrix
   and a topic regex — all specific to AI-and-labour. The operator caught it. **A system that answers one question
   is a demo.** Every constant must be DERIVED FROM THE PROMPT at runtime.
   **KEYSTONE INSIGHT: RACE's own judge GENERATES its 25 grading criteria from the task prompt
   (third_party/deep_research_bench/prompt/criteria_prompt_en.py — the generator is handed only the task text).
   We can generate our COVERAGE MATRIX the same way, from the same prompt.**
2. **FAITHFULNESS IS ON THE TABLE — the operator has authorised relaxing it.** But get the line right:
   fabrication (putting words in a source's mouth) must stay impossible; the reviewer's own reasoning, MARKED AS
   SUCH, is what every literature review does and what the #1 system does constantly (71% of its sentences carry
   no citation). **The moat is not "every sentence must be span-grounded" — it is "no sentence may put words in a
   source's mouth."** Keep Fable's refinements (mechanism pool = the sentence's OWN cited cards; hedge+tag alone
   is costume; gap claims must be corpus-scoped).
3. **ADDRESS EVERY GAP AT ONCE** — retrieval, select, reasoning, composition, measurement — and be HONEST about
   the load-bearing unknown: **we have proven the judge can SEE our scholarship. We have NOT proven it PAYS for it.**
`;

const DESIGN = {
  type: 'object',
  required: ['thesis', 'design', 'why_general', 'faithfulness_position', 'builds_on', 'what_to_drop', 'expected_gain', 'honest_risks'],
  properties: {
    thesis: { type: 'string', description: 'The ONE central idea, in two sentences.' },
    design: { type: 'string', description: 'The architecture, concretely, with file:line where it touches our code. Be long and specific. This is the substance.' },
    why_general: { type: 'string', description: 'PROVE it is not overfit: walk it through TWO completely different queries — a clinical one ("CAR-T vs bispecific antibodies in relapsed myeloma") and a historical one ("what caused the 2008 financial crisis"). What is DERIVED vs HARDCODED? If anything is hardcoded to a domain, you have failed.' },
    faithfulness_position: { type: 'string', description: 'Exactly what we keep and what we drop, and why. What protects a research product people TRUST, vs what merely costs score?' },
    builds_on: { type: 'string', description: 'What you TOOK from Sol and Fable, and what you REJECTED from them, and why. Do not re-derive their work — improve it.' },
    what_to_drop: { type: 'array', items: { type: 'string' } },
    expected_gain: { type: 'string' },
    honest_risks: { type: 'array', items: { type: 'string' } },
  },
}

phase('Architect')
const ANGLES = [
  { k: 'blank-sheet', q: `**BLANK SHEET, THEN MAP BACK.** Read the foundation. Then set it aside and ask: if you were building a deep-research system today, from nothing, to beat every system on DeepResearch Bench ACROSS ALL 100 TASKS — what is its architecture? THEN map it back: what of Sol/Fable/our code survives, what dies, what must be built. The operator has authorised dropping ANY existing rule. Be radical where radical is right, and say so where it is not.` },
  { k: 'derivation', q: `**THE DERIVATION LAYER — THE ANTI-OVERFIT KEYSTONE. This is the single most important angle.** Sol and Fable hardcode anchors, outline, matrix and topic gate. Design the layer that DERIVES all of them FROM THE PROMPT at runtime. RACE's own judge generates its grading criteria from the prompt text alone — study criteria_prompt_en.py and do the same for our coverage matrix. What exactly is derived: scope (topic / recency window / venue class / language)? the matrix? the anchors? the outline? the thesis? the stopping condition? SHOW IT WORKING on three wildly different prompts, concretely. If this layer is weak, the whole plan is a demo.` },
  { k: 'retrieval', q: `**RETRIEVAL AT THE ROOT.** Take Sol's chain and fix what the operator found: (a) SELECT is the broken stage, not search — our corpus holds ResNet, a BMJ checklist and a 1974 reading-psychology paper; (b) recency comes from DATE-FILTERED SEARCH, which WORKS (344k journal articles 2024-2026 via Crossref), not from forward-citation traversal, which is DEAD on this box — this retires Sol's own 35% risk; (c) citation-graph expansion is essential and general (keyword search cannot find Autor-Levy-Murnane); (d) SELECT must be an LLM relevance judge against the actual question. Design the whole chain — query-gen -> search -> fetch -> select -> weight -> dedup -> consolidate — scope-driven and domain-agnostic, and say when it STOPS.` },
  { k: 'reasoning', q: `**THE REASONING LAYER AND THE FAITHFULNESS CONTRACT.** INSIGHT is the heaviest weight (0.32) and our worst dimension. #1 wins with a DEDICATED SECTION of original syntheses no paper states, kept honest by graded epistemic tags + hedged verbs + explicit gap declarations. Our gate deletes all of it. Faithfulness is authorised to be relaxed. Take Fable's four sentence classes and its mechanism-pool scoping (which are RIGHT and which caught a real hole in the operator's first formulation) and build the full reasoning architecture on top. **Then ask the deeper question: is span-grounding even the right primitive?** What would you replace it with?` },
  { k: 'composer', q: `**THE COMPOSER — WRITING A MONOGRAPH, NOT A REPORT.** #1 has a THESIS (institutional mediation at five named levels) that resolves every contradiction in the literature; an opening puzzle its conclusion answers; 32 internal cross-references; insight sold in eight branded, numbered units; epigrammatic paragraph closes; a graded epistemic taxonomy. We produce 12 walls of 677 words opening with meta-commentary about ourselves. **THE HARD PROBLEM: how is a THESIS DERIVED FROM A CORPUS, for any question?** That is the crux of this angle — answer it properly, and the rest follows.` },
  { k: 'measurement', q: `**MEASUREMENT, GENERALITY, AND THE WHEEL.** The load-bearing unknown: we have proven the judge can SEE our scholarship post-cleaner (feature VISIBILITY); we have NOT proven it PAYS for it (feature VALUE). Design (a) the CHEAPEST experiment that measures visibility-to-value FIRST, before we build everything — what is the smallest artifact that would tell us the thesis is wrong? (b) how we prove GENERALITY across many tasks, not one (the benchmark has 100; overfitting to task 72 is worthless — and we can score ANY of the 100 tasks, since we hold the whole benchmark); (c) the fix->compose->score->read->fix wheel with pre-registered kill rules.` },
]

const designs = await parallel(ANGLES.map(a => () =>
  agent(`${READ_FIRST}

${FRAME}

# YOUR ANGLE
${a.q}

# RULES
- **THINK DEEPLY.** This is the most important design work in the project. Take the time you need.
- **BUILD ON THE FOUNDATION.** Sol and Fable did real work — take it, improve it, and say what you rejected.
  Do not re-derive what they already established.
- **VERIFY anything load-bearing.** Every brief in this project has been wrong at least once, including mine.
- **NO PROXIES.** We lost a full night to metrics that moved while the mechanism never fired.`,
    { schema: DESIGN, effort: 'max', label: `arch:${a.k}`, phase: 'Architect' })
))
const D = designs.filter(Boolean)
log(`architects: ${D.length}/6 returned`)

phase('Attack')
const V = { type: 'object', required: ['refuted', 'reasoning'], properties: { refuted: { type: 'boolean' }, reasoning: { type: 'string' }, fix: { type: 'string' } } }
const LENSES = [
  'OVERFIT (the lens that caught both prior designers): walk this design through "what caused the 2008 financial crisis" and "CAR-T vs bispecific antibodies in relapsed myeloma". Does it still work? Or does it silently depend on something task-72-specific — a hardcoded anchor, a hand-built matrix, a topic regex, a domain assumption, an outline written by an engineer? NAME the hardcoded thing, or confirm there is none.',
  'FABRICATION: faithfulness has been relaxed. Trace the CONCRETE path by which a FALSE claim reaches the page. The product is a research tool people TRUST — a high score obtained by inventing facts is a LOSS. But judge BOTH failure modes: does this design also OVER-correct and ban the legitimate scholarly inference that the #1 system makes constantly and honestly?',
  'JUDGE-VALUE (the load-bearing unknown): we proved the judge can SEE our scholarship post-cleaner. We have NOT proven it PAYS for it. Does this design rest on an unmeasured assumption about what the judge rewards? What is the cheapest experiment that would falsify it — and does the plan run that experiment FIRST?',
  'FEASIBILITY on THIS box: OpenAlex 429s our IP. Semantic Scholar 404s. ~50% of paywalled papers have no OA full text (we recovered 36/70; real quotable full text is ~10). A full compose is ~65 minutes. Judge SD is 0.0074. Is this plan a wish?',
]
const attacked = await parallel(D.map((d, i) => () =>
  parallel(LENSES.map((lens, j) => () =>
    agent(`Try HARD to REFUTE this architecture through ONE lens. Default refuted=true if uncertain. Check ${FW}, ${BOARD}, and ${FOUND} if needed.

THESIS: ${d.thesis}
DESIGN: ${String(d.design).slice(0, 6000)}
WHY GENERAL: ${String(d.why_general).slice(0, 3000)}
FAITHFULNESS: ${String(d.faithfulness_position).slice(0, 2500)}

LENS:
${lens}`,
      { schema: V, effort: 'high', label: `refute:${ANGLES[i].k}#${j + 1}`, phase: 'Attack' })
  )).then(vs => ({ angle: ANGLES[i].k, design: d, verdicts: vs.filter(Boolean) }))
))
const A = attacked.filter(Boolean)
log(`attack: ${A.reduce((n, a) => n + a.verdicts.filter(v => v.refuted).length, 0)} refutations across ${A.length} designs`)

const FINAL = {
  type: 'object',
  required: ['thesis', 'the_plan', 'derivation_layer', 'retrieval', 'reasoning_and_faithfulness', 'composer', 'measurement', 'what_we_drop', 'phasing', 'expected', 'honest_unknowns', 'kill_rules'],
  properties: {
    thesis: { type: 'string', description: 'The central idea, in plain English, in three sentences.' },
    the_plan: { type: 'string', description: 'The whole architecture end to end. Long, concrete, executable.' },
    derivation_layer: { type: 'string', description: 'How EVERYTHING is derived from the prompt. The anti-overfit keystone.' },
    retrieval: { type: 'string' },
    reasoning_and_faithfulness: { type: 'string' },
    composer: { type: 'string' },
    measurement: { type: 'string', description: 'Including the CHEAPEST falsifying experiment, run FIRST.' },
    what_we_drop: { type: 'array', items: { type: 'object', properties: { rule: { type: 'string' }, why: { type: 'string' } } } },
    phasing: { type: 'string', description: 'Build order. What runs in parallel. The FASTEST path to a real k=5 score.' },
    expected: { type: 'string', description: 'Honest. Does it beat SOTA on task 72? Across the 100 tasks?' },
    honest_unknowns: { type: 'array', items: { type: 'string' } },
    kill_rules: { type: 'string' },
  },
}

phase('Synthesise')
const final = await agent(
  `Six Opus architects each designed POLARIS's path to beating SOTA on ANY query, building on Sol's plan, Fable's
plan, Fable's cellcog decode, and the operator's seven fixes. Each was attacked on four lenses.

${READ_FIRST}

${FRAME}

# THE SIX DESIGNS AND THEIR ATTACKS
${JSON.stringify(A.map(a => ({
    angle: a.angle,
    thesis: a.design.thesis,
    design: String(a.design.design).slice(0, 6000),
    why_general: String(a.design.why_general).slice(0, 2000),
    faithfulness: String(a.design.faithfulness_position).slice(0, 1800),
    builds_on: String(a.design.builds_on).slice(0, 1200),
    drop: a.design.what_to_drop,
    risks: a.design.honest_risks,
    attacks: a.verdicts.map(v => ({ refuted: v.refuted, why: String(v.reasoning).slice(0, 1000), fix: v.fix })),
  })), null, 1).slice(0, 140000)}

# YOUR JOB — WRITE **ONE PLAN**
Not a survey. A DECISION. Where architects disagree, PICK and justify. Where an attack landed, FIX or DROP.
Where they converge, that is the spine.

The plan must:
- **BEAT THE STATE OF THE ART**, and be honest about whether it does — on task 72 AND across the 100-task benchmark.
- **BE GENERAL.** Nothing hardcoded to AI-and-labour. Prove it by walking through a clinical question and a
  historical one. **The derivation layer is the keystone — if it is weak, the whole plan is a demo.**
- **RESOLVE FAITHFULNESS EXPLICITLY.** State what survives and why. Both over-strictness and under-strictness are
  failures. Fabrication must stay impossible; scholarly inference, marked as such, must be possible.
- **ADDRESS EVERY GAP AT ONCE** — retrieval, select, reasoning, composition, measurement.
- **BE PHASED AND EXECUTABLE.** What is built FIRST? What runs in parallel? **What is the fastest path to a real
  k=5 score, and what is the CHEAPEST experiment that could prove the whole thesis WRONG — and does it run first?**

Be honest about what you do not know.`,
  { schema: FINAL, effort: 'max', label: 'synthesise:one-plan', phase: 'Synthesise' }
)

return { designs: D.map(d => ({ thesis: d.thesis, builds_on: d.builds_on, drop: d.what_to_drop })), attacks: A.map(a => ({ angle: a.angle, refuted: a.verdicts.filter(v => v.refuted).length, total: a.verdicts.length })), final }
