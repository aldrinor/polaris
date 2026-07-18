export const meta = {
  name: 'attack-the-synthesis',
  description: 'Adversarially attack the Opus synthesis — its attack phase died to rate limits and its most explosive claims are unchallenged',
  phases: [
    { title: 'Attack', detail: 'six independent lenses, run SEQUENTIALLY to survive rate limits' },
    { title: 'Adjudicate', detail: 'what survives, what dies, what must be re-verified' },
  ],
}

const PP = '/home/polaris/polaris_project'
const FW = '/home/polaris/wt/flywheel'
const SYN = `${PP}/sota_review/foundation/OPUS_SYNTHESIS_V1.md`
const BOARD = `${PP}/drb_corpus/gpt55_board`

const CTX = `
# THE DOCUMENT UNDER ATTACK
${SYN} — an Opus synthesis of six architectures. **Its adversarial phase DIED to API rate limits, so it has
NEVER been challenged.** It makes claims that would invalidate months of work if true, and waste months if false.

# WHAT OPUS-4.8 HAS ALREADY VERIFIED ON DISK (do not waste effort re-checking; attack the INFERENCES)
- **THE 0.263 IS REAL.** \`third_party/deep_research_bench/results/race/polaris_vm_t{72,75,76,78,90}\` contain
  0.2530 / 0.2839 / 0.2646 / 0.2107 / 0.3026 — our END-TO-END SYSTEM on five real tasks. Mean 0.263.
  Our hand-iterated task-72 artifact (noise_r10_1..5) = 0.4396. **The hand-tuning gap (0.187) EXCEEDS the gap
  to bodhi (0.105).** \`WHEEL_PROGRESS.md:411\` already said "2ND-DRB-TASK GENERALITY GATE — BLOCKED".
- We scored **0.2107 on task 78** — a family asking about Parkinson's warning signs — reportedly because we
  shipped a literature review nobody asked for.

# WHAT THE JUDGE ITSELF SAYS (measured today with scripts/judge_feedback.py — the judge's OWN written critique)
POLARIS vs the reference, raw 0-10 per dimension:
  INSIGHT 6.45 vs 8.31 | COMPREHENSIVENESS 7.22 vs 8.08 | INSTRUCTION 6.11 vs 7.40 | **READABILITY 4.71 vs 8.42**
Judge, verbatim, on our biggest single loss (-4.7): *"Article 1 has weak paragraph cohesion. Many paragraphs are
extremely long and combine unrelated statistics, studies, countries, occupations, and time periods without
adequate transitions. The result is a fragmented narrative."*
And: *"Some claims are difficult to attribute because no formal citations are provided."*
bodhi (0.5441) and cellcog (0.5603, MEASURED today, not estimated) both beat the reference on EVERY dimension.
The judge's stated reasons they win: **+5.0 / +4.0 for "explicitly states an evidence constraint to cite only
journal articles"**; +2.6 to +3.1 for "compares seminal theory, causal studies, meta-analyses, field experiments,
administrative data, qualitative work"; **+2.8 for "eight tagged syntheses ... genuine synthesis beyond summary"**
(cellcog scored 9.8/10); +2.4 to +2.7 for "reconciling conflicting evidence".
**THE REFERENCE'S SCORE MOVES**: the same reference scores insight 8.31 against US and 7.28 against cellcog.
`;

const V = {
  type: 'object',
  required: ['verdict', 'reasoning', 'what_survives'],
  properties: {
    verdict: { type: 'string', enum: ['CONFIRMED', 'PARTIALLY_REFUTED', 'REFUTED'] },
    reasoning: { type: 'string', description: 'Show your work. Run the numbers. Read the code. Quote the artifacts.' },
    what_survives: { type: 'string', description: 'If refuted, what part of the claim is still true and usable?' },
    fix: { type: 'string' },
  },
}

phase('Attack')
const LENSES = [
  { k: 'shape-vs-judge', q: `**THE CENTRAL CONTRADICTION. Attack it hardest.**
The synthesis claims (F2): "DOCUMENT SHAPE IS WORTH APPROXIMATELY ZERO — under two-way task x system fixed effects
across 898 (article, score) pairs, section count beta=+0.00000 and log-words beta=+0.0069/SD."
**But the judge's OWN WRITTEN CRITIQUE scores us 4.71 vs 8.42 on readability and names our long paragraphs as the
single biggest loss (-4.7).** Both cannot be simply true.
RE-RUN THE REGRESSION YOURSELF from \`${BOARD}/*.jsonl\` (articles) and \`${BOARD}/scores/*/raw_results.jsonl\`
(scores). 9 systems x 100 tasks. Then adjudicate:
 - Is the fixed-effects null CORRECT, and if so, does it EXTRAPOLATE to our operating point (677-word median
   paragraphs = 99.7th percentile; only 3 of 898 articles exceed 400w)? The synthesis ADMITS it does not. Is that
   admission fatal to its own conclusion?
 - Is "two-way fixed effects" even the right control? If a system's QUALITY *is partly* its ability to structure a
   document, then absorbing system identity absorbs the very causal channel we care about. **Is F2 controlling away
   the treatment?**
 - The judge PENALISES our structure explicitly and in writing. Reconcile that with a null coefficient, or say which
   is wrong.` },
  { k: 'the-0263', q: `**THE 0.263 — attack the INFERENCE, not the number (the number is verified).**
The synthesis concludes: "we have a demo, not a system; every plan optimizes the artifact; the mission is the system."
Attack:
 - **Is polaris_vm_t72 (0.2530) really the same pipeline** that produced the 0.4396 artifact, or is it an OLD/BROKEN
   run from a different era of the code? Find out. Check dates, configs, git history. **If it is a stale artifact
   from a worse version of the pipeline, the entire thesis collapses.**
 - Is the 0.187 "hand-tuning gap" really hand-tuning — or is it the difference between a run WITH a curated corpus
   and a run WITHOUT one, i.e. a RETRIEVAL gap that the plan already addresses?
 - Does "the system scores 0.263" actually imply "stop optimizing the artifact"? Or is the artifact the correct
   vehicle for isolating COMPOSE quality while retrieval is fixed separately?` },
  { k: 'kill-rule-math', q: `**THE KILL-RULE CLAIM — verify the arithmetic.**
The synthesis claims BOTH foundation plans (Sol's and Fable's) have kill rules that are STATISTICALLY INCAPABLE of
resolving a single lever: "dS/dT = R/(T+R)^2 ~= 0.045 overall points per raw weighted point. A criterion of weight
0.0435 must move +4.8 points on the 0-10 scale to produce the +0.0094 both plans demand. **Both plans mandate
one-lever-at-a-time AND a kill rule that cannot see one lever. They would have killed every good lever they built.**"
And: "Sol's gate (0.5670) and Fable's (0.5672) require T/R = 1.31 — higher than ANY system has EVER achieved on ANY
dimension of this task (the frontier is 1.08-1.27; best single dimension ever = lunon's insight at 1.270)."
**DO THE MATHS YOURSELF from the raw scores.** Is this right? If it is, it is the most important methodological
finding in the project and it means we must measure at the CRITERION level, not the scalar. If it is wrong, say so.` },
  { k: 'overfit-in-code', q: `**"THE OVERFIT IS CHECKED INTO THE SYSTEM."**
The synthesis claims domain-specific vocabulary is hardcoded in **10+ live source files**: \`decomposer.py\`,
\`claim_atom_extractor.py\`, \`scope_classifier_llm.py\`, \`template_classifier.py\`, \`evidence_value_extractor.py\`,
\`domain_signal.py\` ("a GLP-1-flavoured clinical term list").
**GO AND LOOK.** Is this true? How deep does it go? Is it a few term lists (a day's work) or is the domain
assumption structural (a rewrite)? Quote file:line. This determines whether "make it general" is a week or a quarter.
Also verify the claim that we scored 0.2107 on task 78 **because we shipped a literature review to a family asking
about Parkinson's warning signs** — read our actual t78 output and the task-78 criteria.` },
  { k: 'fabrication', q: `**FABRICATION AND THE RELAXED CONTRACT.**
The synthesis relaxes faithfulness ("faithfulness is a property of NAMES, not sentences; fabrication is always the
introduction of a PARTICULAR"). It also reports that \`validate()\` is imported at \`cellcog_composer.py:49\` and
NEVER CALLED, and that the \`mechanisms\` field is copied unchecked from LLM output.
Trace the CONCRETE path by which a false claim reaches the page under the new contract. Is "no new particular" a
sufficient invariant, or can a fabrication be assembled entirely from existing particulars (e.g. binding a real
number to the wrong study, or asserting a relation between two real findings that neither supports)?
**Also judge the OPPOSITE failure: does the contract still ban the legitimate scholarship that the #1 system does
constantly (cellcog scored 9.8/10 for eight syntheses "no single paper articulates")?**` },
  { k: 'what-actually-wins', q: `**DOES THE PLAN AIM AT WHAT THE JUDGE ACTUALLY PAYS FOR?**
We now have the judge's OWN reasons (see context). It pays, in order: **declaring your evidence constraint (+5.0 /
+4.0)**; multidisciplinary + diverse EVIDENCE TYPES (+2.6/+3.1); **named, tagged original syntheses (+2.8, scored
9.8/10)**; reconciling conflicting evidence (+2.4/+2.7); a summary table (+2.4).
The synthesis's answer is "answer the actual question, with real evidence, and say something true" — and it books
document shape at ZERO.
**Does its plan actually service the five things the judge says it pays for?** Or has it over-rotated from
"cosmetics matter" to "cosmetics are worthless" and thrown out the declared-methodology lever — which is the SINGLE
BIGGEST measured win on the board and costs one paragraph to write? Be specific about what the plan MISSES.` },
]

// SEQUENTIAL — the last run lost 17 of 27 agents to rate limiting. Slow and complete beats fast and dead.
const verdicts = []
for (const L of LENSES) {
  const v = await agent(`${CTX}

# YOUR LENS
${L.q}

# RULES
- **VERIFY. Do not reason from the summary.** Open the files. Re-run the numbers. Read the code. Every brief in this
  project has been wrong at least once, including the one you are attacking and the one that wrote it.
- Default to REFUTED if you cannot confirm.
- If the claim survives, say so plainly — a confirmed claim is as valuable as a refuted one.`,
    { schema: V, effort: 'max', label: `attack:${L.k}`, phase: 'Attack' })
  if (v) {
    verdicts.push({ lens: L.k, ...v })
    log(`${L.k}: ${v.verdict}`)
  }
}

phase('Adjudicate')
const ADJ = {
  type: 'object',
  required: ['survives', 'dies', 'must_reverify', 'the_call'],
  properties: {
    survives: { type: 'array', items: { type: 'string' } },
    dies: { type: 'array', items: { type: 'string' } },
    must_reverify: { type: 'array', items: { type: 'string' } },
    the_call: { type: 'string', description: 'What do we ACTUALLY do first? Be decisive.' },
  },
}
const adj = await agent(
  `Six adversarial lenses attacked the Opus synthesis. Adjudicate.

${CTX}

# THE VERDICTS
${JSON.stringify(verdicts, null, 1).slice(0, 90000)}

Decide: what SURVIVES, what DIES, what must be RE-VERIFIED before we build on it.
Then make **THE CALL**: given everything, what do we actually do FIRST? Be decisive and honest.
The two things in tension: the judge says our structure is our biggest loss (-4.7, readability 4.71 vs 8.42);
the regression says document shape is worth zero. **Resolve it.**`,
  { schema: ADJ, effort: 'max', label: 'adjudicate', phase: 'Adjudicate' }
)
return { verdicts, adjudication: adj }
