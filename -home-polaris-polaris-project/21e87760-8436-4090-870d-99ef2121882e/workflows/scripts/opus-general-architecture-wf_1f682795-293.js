export const meta = {
  name: 'opus-general-architecture',
  description: 'Six independent Opus architects design a GENERAL research system that beats SOTA on any query — then adversarial attack, then one consolidated plan',
  phases: [
    { title: 'Architect', detail: 'six independent deep designs, different angles' },
    { title: 'Attack', detail: 'attack each on overfit, fabrication, judge-value, feasibility' },
    { title: 'Synthesise', detail: 'one plan' },
  ],
}

const PP = '/home/polaris/polaris_project'
const FW = '/home/polaris/wt/flywheel'
const BOARD = `${PP}/drb_corpus/gpt55_board`

// ---------------------------------------------------------------- the shared ground truth
const GROUND = `
# WHAT WE KNOW (all measured tonight; do not re-litigate, but DO verify anything load-bearing)

## THE SCOREBOARD (RACE, GPT-5.5 judge)
POLARIS 0.4382 on task 72 (comp .4549 | INSIGHT .4238 | instr-follow .4409 | READABILITY .3774 = worst on the board).
Highest KNOWN task-72 score: bodhi 0.5441. cellcog is #1 corpus-wide at 0.5578 but publishes NO per-task score
(a regression across the 9 systems that have both estimates its task-72 at ~0.556 +/- 0.019).
Reference (parity) = gemini-2.5-pro-DR at 0.5102. Weights: INSIGHT .32 | COMPREH .29 | INSTR .25 | READ .14.
RACE = target/(target+reference). ONE LLM call scores both reports SIDE BY SIDE, writing a comparative analysis
BEFORE the numbers, all ~25 criteria in ONE context => cross-dimension bleed is real.
Judge noise SD 0.0074; k=5 paired resolves +0.0094. NEVER score n=1.

## THE THREE MEASURED CAUSES OF OUR GAP
A. THE JUDGE CANNOT SEE OUR SOURCES. RACE runs an LLM cleaner that deletes every [n] marker and the whole
   reference list before judging. Measured on 12 facts x 5 formats through the PRODUCTION cleaner:
   [n] markers -> 0/12 authors survive. "(Author, Year)" -> 0/12. Narrative-with-journal -> 10-12/12.
   So the judge reads "About 47 percent of US employment is at risk of computerisation." as an UNSOURCED
   ASSERTION. That is Frey & Osborne, 5,223 citations. All 240 of our citations are invisible.
B. WE CANNOT REASON ACROSS SOURCES. entailment_judge.py NEUTRAL clause deletes any sentence introducing
   "a fact, entity, MECHANISM ... NOT present in the SPAN". 98% of our sentences are bare facts.
   INSIGHT is the heaviest weight (0.32) and our worst dimension.
C. UNREADABLE. 12 paragraphs, median 677 words, ZERO H3. Every other system: 38-170 w/paragraph.

## HOW #1 ACTUALLY WINS (decoded from cellcog's task-72 artifact, verbatim)
- **A DEDICATED SECTION FOR CLAIMS NO SOURCE MAKES.** §5 "Contested Debates and Novel Insights" opens:
  "The heterogeneous evidence assembled in Sections 3 and 4 invites syntheses that NO SINGLE PAPER IN THE
  PEER-REVIEWED LITERATURE ARTICULATES. This section develops eight such syntheses. Each is epistemically
  tagged to distinguish what the evidence has established from what it suggests and from what we ourselves argue."
  **71% of cellcog's 504 body sentences carry NO citation at all.** INSIGHT is its best dimension (0.5708).
  THIS IS THE MOST LIKELY SINGLE EXPLANATION FOR 0.5578 vs THE 0.54 PACK.
- HOW IT STAYS HONEST: (1) a GRADED EPISTEMIC TAG (6 types: [Established Finding] / [Emerging Pattern] /
  [Conceptual Argument] / [Analytical Hypothesis] / [Our Synthesis] / combinations); (2) HEDGED verbs
  ("we propose, as analytical synthesis"); (3) AN EXPLICIT GAP DECLARATION ("No peer-reviewed study has yet
  measured X"). It asserts an original mechanism AND TELLS THE JUDGE IT IS ORIGINAL AND UNTESTED.
- IT HAS A THESIS: institutional mediation at five named levels. Every contradiction in the literature resolves
  through that one master variable. Its headline is a NEGATIVE result ("Heterogeneity, not displacement, is the
  central peer-reviewed finding"). We open with meta-commentary about our own organisation.
- INSIGHT SOLD IN COUNTABLE, BRANDED UNITS: "eight original syntheses", each with a coined name (the informality
  buffer, the jagged frontier, the Turing Trap). The judge grading INSIGHT is handed a numbered inventory.
- MONOGRAPH WIRING: 32 internal cross-references ("a tension addressed in Section 3.3.4"). bodhi: zero.
- AN OPENING PUZZLE THE CONCLUSION RESOLVES — a matched pair across the two passages the judge reads hardest.
- EPIGRAMMATIC PARAGRAPH CLOSES: every ~100w paragraph ends on a citation-free abstraction.
- RECENCY DOMINANCE: 41 of its 104 references are 2024-2026. OUR CORPUS HAS ZERO PAPERS AFTER 2023.
- CITATION FORM: "Giuntella, Lu, and Wang (2025), in the *Economic Journal*, find that..." (author + year + journal
  in ONE clause). NOTE: an attack agent MEASURED post-cleaner survival of parenthetical years at 0/12 — only
  "In their 2025 Economic Journal article, X and Y find..." delivers the year. VERIFY THIS YOURSELF.
- SCALE: 13,580 body words at ~100w/paragraph, 104 journal references, 31 H3 + 8 H4.

## OUR PIPELINE'S REAL STATE
- Corpus: 997 evidence rows, 919 URLs, 206 DOIs, EVERY row already has a direct quote — but only 5 rows had
  AUTHOR NAMES, and after enrichment only 17 of 120 journal works are ON-TOPIC. The corpus contains ResNet,
  the BMJ PRISMA checklist, and a 1974 Cognitive Psychology paper on reading. **RETRIEVAL WAS NEVER SHALLOW —
  IT WAS AIMED WRONG. SELECT IS THE BROKEN STAGE.**
- Keyword search PROVABLY cannot find this literature: Autor-Levy-Murnane (2003, QJE, 4,743 cites) is the field's
  most important paper and its title contains neither "AI" nor "labor market". CITATION-GRAPH EXPANSION finds it.
- Forward citation traversal (to reach 2024+ papers) is DEAD on this box: OpenAlex 429s our IP, S2 404s.
  **BUT THE OPERATOR FOUND THE FIX: Crossref DATE-FILTERED SEARCH WORKS — 344,623 journal articles 2024-2026,
  including Babina & Fedyk (2024, Journal of Financial Economics). WE DO NOT NEED FORWARD TRAVERSAL. WE CAN
  ASK FOR RECENT PAPERS BY DATE.** Both prior designers missed this entirely.
- We have an AGENTIC RETRIEVAL LOOP (PG_AGENTIC_*, outline_agent) that was NEVER pointed at this problem.
- Built and working: Crossref/Unpaywall enrichment, citation-graph expansion, the cleaner-survival test,
  a typed synthesis contract (14/14, zero false admissions) — BUT its validate() is imported and NEVER CALLED,
  its mechanism field is NOT span-checked (a hallucinated mechanism becomes a global citation license), and its
  fulltext detector accepted a 548-word landing page as Frey & Osborne's full text.

## WHAT THE OPERATOR HAS CORRECTED US ON, REPEATEDLY (and was right every time)
1. "Why not do BOTH more sources and more thinking?" -> the sources-vs-thinking trade-off was FALSE.
2. "Why stick with bodhi class? Why not the top?" -> every plan quietly retreated to what had already been built.
3. "Just search by date." -> dissolved the biggest risk in both prior plans, which neither had seen.
4. "Are you overfitting?" -> YES. The prior plans hardcode 15 anchor papers, a 10-section outline, an
   8x10 coverage matrix and a topic regex — ALL SPECIFIC TO AI-AND-LABOUR. That is not a research system;
   it is an expensive way to answer one question.
5. "Relax faithfulness if it is a ghost." -> Our gate blocks BOTH fabrication AND legitimate scholarly inference.
   #1 asserts original mechanisms constantly, and stays honest by LABELLING them, not by refusing to think.
`;

const DESIGN = {
  type: 'object',
  required: ['thesis', 'design', 'why_general', 'faithfulness_position', 'what_to_drop', 'expected_gain', 'honest_risks'],
  properties: {
    thesis: { type: 'string', description: 'The ONE central idea of your design, in two sentences.' },
    design: { type: 'string', description: 'The architecture, concretely. file:line where it touches our code. This is the substance — be long and specific.' },
    why_general: { type: 'string', description: 'PROVE it is not overfit: walk it through a COMPLETELY DIFFERENT query (e.g. "compare CAR-T vs bispecific antibodies for relapsed myeloma", or "what caused the 2008 financial crisis"). What is DERIVED vs HARDCODED?' },
    faithfulness_position: { type: 'string', description: 'Exactly what we keep and what we drop, and WHY. The operator has authorised relaxing it. What ACTUALLY protects the product, vs what merely costs score?' },
    what_to_drop: { type: 'array', items: { type: 'string' } },
    expected_gain: { type: 'string', description: 'Honest. Which dimension, how much, and on what basis.' },
    honest_risks: { type: 'array', items: { type: 'string' } },
  },
}

phase('Architect')
const ANGLES = [
  { k: 'blank-sheet', q: `**BLANK SHEET.** Forget our pipeline entirely. If you were building a deep-research system TODAY, from nothing, whose only goal is to beat every system on DeepResearch Bench ACROSS ALL 100 TASKS — what is its architecture? Then, and only then, map it back onto what we have: what survives, what dies, what must be built. Do not be constrained by our sunk code. The operator has explicitly authorised dropping ANY existing rule.` },
  { k: 'derivation-layer', q: `**THE GENERALISATION KEYSTONE.** Every prior plan hardcoded: 15 anchor papers, a 10-section outline, an 8x10 coverage matrix, a topic regex — all specific to AI-and-labour. Design the DERIVATION LAYER that produces all of these FROM THE PROMPT ITSELF, at runtime, for ANY question. Note: RACE's own judge GENERATES its 25 grading criteria from the task prompt (see third_party/deep_research_bench/prompt/criteria_prompt_en.py) — **we can generate our coverage matrix the same way, from the same prompt.** What exactly is derived? Scope (topic/recency window/venue class/language)? The matrix? The anchors? The outline? The stopping condition? Show it working on three wildly different prompts.` },
  { k: 'retrieval', q: `**RETRIEVAL AT THE ROOT — query-gen -> search -> fetch -> select -> weight -> dedup -> consolidate.** Our corpus has 997 rows and 919 URLs and is FULL OF JUNK (ResNet, a 1974 reading-psychology paper). Retrieval was never shallow — SELECT is the broken stage. Design the whole chain so it is (a) scope-driven, (b) recency-aware BY DATE-FILTERED SEARCH (the operator's fix — Crossref date filtering WORKS; forward-citation traversal is dead on this box), (c) uses citation-graph expansion for the canon (keyword search cannot find Autor-Levy-Murnane), (d) has an LLM relevance judge in SELECT, not a regex, and (e) knows when to STOP. And it must work for a clinical question, a financial one, a historical one.` },
  { k: 'reasoning', q: `**THE REASONING ARCHITECTURE + THE FAITHFULNESS QUESTION.** This is the heaviest dimension (INSIGHT 0.32) and our worst. #1 wins with a DEDICATED SECTION of original syntheses that NO paper states, kept honest by graded epistemic tags + hedged verbs + explicit gap declarations. Our gate deletes all of it. **The operator has authorised relaxing faithfulness.** So: what rule ACTUALLY protects the product (a research tool nobody can trust is worthless), and what merely costs us score while protecting nothing? Design the reasoning layer AND the exact contract. Be precise about what may be asserted, by whom, marked how. Consider: is span-grounding even the right primitive?` },
  { k: 'composer', q: `**THE COMPOSER.** #1 is a MONOGRAPH: a thesis (institutional mediation at five levels) that resolves every contradiction; an opening puzzle the conclusion answers; 32 internal cross-references; insight sold in eight branded, numbered units; epigrammatic paragraph closes; a graded epistemic taxonomy; 13.5k words at ~100w/paragraph; 31 H3 + 8 H4. We produce 12 walls of 677 words that open with meta-commentary about ourselves. Design the composer that writes a MONOGRAPH — for ANY question, deriving its thesis and structure from the evidence, not from a hardcoded outline. How is a THESIS derived from a corpus? That is the hard part — answer it.` },
  { k: 'measurement', q: `**MEASUREMENT AND THE WHEEL — and the load-bearing unknown.** Fable's honest sentence: "Everything measured so far is about what SURVIVES the cleaner — feature VISIBILITY — not about what the judge PAYS for those features — feature VALUE. We have never composed one full report in this architecture and scored it k=5." Design the measurement programme that (a) measures visibility-to-value conversion FIRST, cheaply, before we build everything; (b) proves generality across MANY tasks, not one (the benchmark has 100 — overfitting to task 72 is worthless); (c) runs the fix->compose->score->read->fix wheel with pre-registered kill rules. What is the CHEAPEST experiment that would tell us the whole thesis is wrong?` },
]

const designs = await parallel(ANGLES.map(a => () =>
  agent(`You are designing POLARIS's architecture to BEAT the state of the art on DeepResearch Bench — **on any query, not just task 72.**

${GROUND}

# YOUR ANGLE
${a.q}

# RULES
- **THINK DEEPLY. This is the most important design work in the project.** Take the time.
- **DO NOT OVERFIT.** The operator caught every prior plan hardcoding task-72 specifics. A system that answers one
  question is a demo, not a product. Every constant must be DERIVED from the prompt.
- **FAITHFULNESS IS ON THE TABLE.** The operator has authorised relaxing it. But be precise: what protects a
  research product people can trust, and what is merely a rule that costs score and protects nothing?
- Ground every claim in the rubric text, our code, or a measured artifact. Read the winners at ${BOARD} and our
  code at ${FW} if you need to. **VERIFY anything load-bearing — the brief above has been wrong before.**
- No proxies. We lost a full night to metrics that moved while the mechanism never fired.`,
    { schema: DESIGN, effort: 'max', label: `arch:${a.k}`, phase: 'Architect' })
))
const D = designs.filter(Boolean)
log(`architects: ${D.length}/6 returned`)

phase('Attack')
const V = { type: 'object', required: ['refuted', 'reasoning'], properties: { refuted: { type: 'boolean' }, reasoning: { type: 'string' }, fix: { type: 'string' } } }
const LENSES = [
  'OVERFIT: walk this design through a COMPLETELY different query — "what caused the 2008 financial crisis" or "CAR-T vs bispecific antibodies in relapsed myeloma". Does it still work, or does it silently depend on something task-72-specific (a hardcoded anchor, a hand-built matrix, a topic regex, a domain assumption)? Name the hardcoded thing or confirm there is none.',
  'FABRICATION: faithfulness has been relaxed. Trace the CONCRETE path by which a FALSE claim now reaches the page. Remember the goal is a research product people TRUST — a high score obtained by inventing facts is a loss, not a win. But also: does this design over-correct and ban legitimate scholarly inference (which is what #1 does constantly and honestly)? Judge BOTH failure modes.',
  'JUDGE-VALUE (the load-bearing unknown): we have proven the judge can SEE our scholarship post-cleaner. We have NOT proven it PAYS for it. Does this design rest on an unmeasured assumption about what the judge rewards? What is the cheapest experiment that would falsify it?',
  'FEASIBILITY: can this actually be built and run on THIS box? Measured constraints: OpenAlex 429s our IP, Semantic Scholar 404s, ~50% of paywalled papers have no OA full text, a full compose takes ~65 minutes, judge SD is 0.0074. Is the plan a wish?',
]
const attacked = await parallel(D.map((d, i) => () =>
  parallel(LENSES.map((lens, j) => () =>
    agent(`Try HARD to REFUTE this architecture through ONE lens. Default refuted=true if uncertain.

THESIS: ${d.thesis}
DESIGN: ${String(d.design).slice(0, 6000)}
WHY GENERAL: ${String(d.why_general).slice(0, 2500)}
FAITHFULNESS: ${String(d.faithfulness_position).slice(0, 2500)}

LENS:
${lens}`,
      { schema: V, effort: 'high', label: `refute:${ANGLES[i].k}#${j + 1}`, phase: 'Attack' })
  )).then(vs => ({ angle: ANGLES[i].k, design: d, verdicts: vs.filter(Boolean) }))
))
const A = attacked.filter(Boolean)
log(`attack complete: ${A.reduce((n, a) => n + a.verdicts.filter(v => v.refuted).length, 0)} refutations across ${A.length} designs`)

const FINAL = {
  type: 'object',
  required: ['thesis', 'the_plan', 'derivation_layer', 'retrieval', 'reasoning_and_faithfulness', 'composer', 'measurement', 'what_we_drop', 'phasing', 'expected', 'honest_unknowns', 'kill_rules'],
  properties: {
    thesis: { type: 'string', description: 'The central idea, in plain English, in three sentences.' },
    the_plan: { type: 'string', description: 'The whole architecture, end to end. Long and concrete.' },
    derivation_layer: { type: 'string', description: 'How EVERYTHING is derived from the prompt. The anti-overfit keystone.' },
    retrieval: { type: 'string' },
    reasoning_and_faithfulness: { type: 'string', description: 'The reasoning layer AND the exact contract. What is protected, what is dropped, why.' },
    composer: { type: 'string' },
    measurement: { type: 'string', description: 'Including the CHEAPEST experiment that could falsify the whole thesis, run FIRST.' },
    what_we_drop: { type: 'array', items: { type: 'object', properties: { rule: { type: 'string' }, why: { type: 'string' } } } },
    phasing: { type: 'string', description: 'What we build FIRST, second, third. What can run in parallel. What is the fastest path to a real SCORE?' },
    expected: { type: 'string', description: 'Honest. Does it beat SOTA? On task 72? Across 100 tasks?' },
    honest_unknowns: { type: 'array', items: { type: 'string' } },
    kill_rules: { type: 'string' },
  },
}

phase('Synthesise')
const final = await agent(
  `Six independent architects designed POLARIS's path to beating SOTA on ANY query. Each was then attacked on four
lenses: OVERFIT, FABRICATION, JUDGE-VALUE, FEASIBILITY.

${GROUND}

# THE SIX DESIGNS AND THEIR ATTACKS
${JSON.stringify(A.map(a => ({
    angle: a.angle,
    thesis: a.design.thesis,
    design: String(a.design.design).slice(0, 5000),
    why_general: String(a.design.why_general).slice(0, 1800),
    faithfulness: String(a.design.faithfulness_position).slice(0, 1800),
    drop: a.design.what_to_drop,
    risks: a.design.honest_risks,
    attacks: a.verdicts.map(v => ({ refuted: v.refuted, why: String(v.reasoning).slice(0, 900), fix: v.fix })),
  })), null, 1).slice(0, 120000)}

# YOUR JOB
Write **ONE PLAN**. Not a survey — a decision. Where the architects disagree, PICK, and say why. Where an attack
landed, FIX IT or DROP the lever. Where they converge, that is your spine.

It must:
- **BEAT THE STATE OF THE ART** — and be honest about whether it does, on task 72 AND across the 100-task benchmark.
- **BE GENERAL.** Nothing hardcoded to AI-and-labour. Prove it by walking the plan through a clinical question and a
  historical one. The derivation layer is the keystone — if it is weak, the whole plan is a demo.
- **RESOLVE FAITHFULNESS EXPLICITLY.** The operator authorised relaxing it. State exactly what survives and why: what
  protects a research product people can TRUST, versus what merely costs score. Both over-strictness and
  under-strictness are failures.
- **ADDRESS EVERY GAP AT ONCE** — retrieval, select, reasoning, composition, measurement.
- **BE PHASED AND EXECUTABLE.** What do we build FIRST? What is the fastest path to a real k=5 score? What is the
  cheapest experiment that could prove the whole thesis WRONG — and can we run it before building everything?

Be honest about what you do not know. The load-bearing unknown is stated in the brief: we have proven the judge can
SEE our scholarship; we have NOT proven it PAYS for it.`,
  { schema: FINAL, effort: 'max', label: 'synthesise:one-plan', phase: 'Synthesise' }
)

return { designs: D.map(d => ({ thesis: d.thesis, drop: d.what_to_drop, risks: d.honest_risks })), attacks: A.map(a => ({ angle: a.angle, refuted: a.verdicts.filter(v => v.refuted).length, total: a.verdicts.length })), final }
