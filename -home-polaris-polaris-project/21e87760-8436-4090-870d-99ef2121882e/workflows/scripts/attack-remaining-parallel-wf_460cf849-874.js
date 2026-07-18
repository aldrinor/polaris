export const meta = {
  name: 'attack-remaining-parallel',
  description: 'The 4 remaining adversarial lenses, run 4-wide (safe concurrency), then adjudicate',
  phases: [
    { title: 'Attack', detail: '4 lenses in parallel — well under the 24 that rate-limited' },
    { title: 'Adjudicate', detail: 'the final call, using all 6 verdicts' },
  ],
}

const PP = '/home/polaris/polaris_project'
const FW = '/home/polaris/wt/flywheel'
const SYN = `${PP}/sota_review/foundation/OPUS_SYNTHESIS_V1.md`
const BOARD = `${PP}/drb_corpus/gpt55_board`

const CTX = `
# THE DOCUMENT UNDER ATTACK
${SYN} — an Opus synthesis of six architectures whose own adversarial phase died to rate limits.

# WHAT TWO EARLIER LENSES ALREADY ESTABLISHED (build on these; do not redo them)
**LENS 1 (shape-vs-judge) — PARTIALLY REFUTED the synthesis.** It rebuilt the 898-row panel and found a UNITS ERROR:
the synthesis's "log-words = +0.0069/SD, below the resolvable effect" is per SD of the RESIDUALIZED regressor (a 31%
length wiggle) compared against an ABSOLUTE score threshold. Scaled to the real corpus spread:
**log(words) -> +0.0211/SD, t=5.0, CI [+0.0128,+0.0294] — entirely ABOVE the resolvable effect.**
**But length SATURATES at ~8,000 words** (worth +0.031 from 2,500->8,000, then a plateau). We are at 9,194 — past the
knee. **So length is a FLOOR (~5,000w), not a lever.**
**SURVIVING, WELL-POWERED NULL: sections +0.0020/SD, H3 +0.0018/SD. "Add 30+ subsections" is DEAD**, and the
H3 r=+0.519 correlation everyone read as a mandate is 100% SYSTEM IDENTITY.

**LENS 2 (the-0263) — REFUTED the synthesis's headline.** All five \`polaris_vm_*\` runs are ABORTS
(\`run_status.json\`: four_role_held / report_redaction_failed -> \`_ARTIFACT_KIND_DEGRADED\`, our own code calls it
"a run-level / infra failure"), generated **June 9 — five weeks stale** — and merely SCORED on July 11.
**The pipeline REFUSED to ship them.** And the overfit argument collapses on its own data: \`polaris_vm_t72\` IS a
task-72 run and scores 0.2530 — FOURTH OF FIVE, BELOW the mean of the four "unseen" tasks (0.2655). Task-72
advantage = **-0.0125, NEGATIVE.** 0.263 is a PIPELINE-VERSION number, not a GENERALITY number.
**WHAT SURVIVES: generality is UNMEASURED, not disproven — 37 scored runs since 07-12, ALL task 72, zero elsewhere.**

# WHAT THE JUDGE ITSELF SAYS (measured today — its OWN written critique, via scripts/judge_feedback.py)
POLARIS vs the reference, raw 0-10: INSIGHT 6.45 v 8.31 | COMPREH 7.22 v 8.08 | INSTR 6.11 v 7.40 | **READ 4.71 v 8.42**
bodhi = 0.5441. **cellcog = 0.5603 (MEASURED today, not estimated).** Both beat the reference on EVERY dimension.
**THE JUDGE'S STATED REASONS THEY WIN:**
- **+5.0 (bodhi) / +4.0 (cellcog): "explicitly states an evidence constraint to cite only journal articles"** —
  this is the SINGLE BIGGEST measured win on the board. **We score 1.5/10 on it. The reference scores 2.0.**
- +2.6/+3.1: "compares seminal theory, causal empirical studies, meta-analyses, field experiments, administrative
  data, and qualitative labor-process work" (evidence-TYPE diversity, not more papers)
- **+2.8: "its eight tagged syntheses ... show genuine synthesis beyond summary" — cellcog scored 9.8/10**
- +2.4/+2.7: "especially effective in reconciling conflicting evidence"
- +2.4: "its sectoral table is clear and useful"
Judge on OUR biggest single loss (-4.7): *"weak paragraph cohesion... extremely long paragraphs... a fragmented
narrative"*. And: *"some claims are difficult to attribute because no formal citations are provided."*
**THE REFERENCE'S SCORE MOVES**: the same reference scores insight 8.31 against US, 7.28 against cellcog.
`;

const V = {
  type: 'object',
  required: ['verdict', 'reasoning', 'what_survives'],
  properties: {
    verdict: { type: 'string', enum: ['CONFIRMED', 'PARTIALLY_REFUTED', 'REFUTED'] },
    reasoning: { type: 'string', description: 'Show your work. Run the numbers. Read the code. Quote the artifacts.' },
    what_survives: { type: 'string' },
    fix: { type: 'string' },
  },
}

phase('Attack')
const LENSES = [
  { k: 'kill-rule-math', q: `**THE KILL-RULE CLAIM — verify the arithmetic from the raw scores.**
The synthesis claims BOTH foundation plans have kill rules STATISTICALLY INCAPABLE of resolving a single lever:
"dS/dT = R/(T+R)^2 ~= 0.045 overall points per raw weighted point. A criterion of weight 0.0435 must move **+4.8
points on the 0-10 scale** to produce the +0.0094 both plans demand. **Both plans mandate one-lever-at-a-time AND a
kill rule that cannot see one lever. They would have killed every good lever they built.**"
And: "Sol's gate (0.5670) and Fable's (0.5672) require T/R = 1.31 — **higher than ANY system has EVER achieved on ANY
dimension of this task** (frontier 1.08-1.27; best single dimension = lunon's insight at 1.270)."
**DO THE MATHS YOURSELF** from \`${BOARD}/scores/*/raw_results.jsonl\` and \`${FW}/third_party/deep_research_bench/\`.
If true, it is the most important methodological finding in the project — it means we MUST measure at the CRITERION
level (which we can now do: the judge's written per-criterion scores are captured by scripts/judge_feedback.py).
If false, say so.` },
  { k: 'overfit-in-code', q: `**"THE OVERFIT IS CHECKED INTO THE SYSTEM."**
The synthesis claims domain-specific vocabulary is hardcoded in **10+ live source files**: \`decomposer.py\`,
\`claim_atom_extractor.py\`, \`scope_classifier_llm.py\`, \`template_classifier.py\`, \`evidence_value_extractor.py\`,
\`domain_signal.py\` ("a GLP-1-flavoured clinical term list").
**GO AND LOOK.** Is it true? How deep? A few term lists (a day's work) or a structural domain assumption (a rewrite)?
Quote file:line. **This determines whether "make it general" is a week or a quarter — the single most important
scoping question in the plan.**
NOTE: lens 2 REFUTED the "we shipped a lit review to a Parkinson's family" story — that came from an ABORTED June run.
So do NOT rest on it. Judge the CODE, not the dead artifact. Does the CURRENT composer hardcode an outline/genre?` },
  { k: 'fabrication', q: `**FABRICATION UNDER THE RELAXED CONTRACT.**
The synthesis relaxes faithfulness ("faithfulness is a property of NAMES, not SENTENCES; fabrication is always the
introduction of a PARTICULAR — a number, an entity, a study, a date, an attribution").
It also reports that \`validate()\` is imported at \`${FW}/scripts/cellcog_composer.py:49\` and **NEVER CALLED**, and
that the \`mechanisms\` field at \`:167\` is copied unchecked from LLM output. **VERIFY BOTH.**
Then: trace the CONCRETE path by which a false claim reaches the page under the new contract.
**Is "no new particular" a SUFFICIENT invariant?** Or can a fabrication be assembled entirely from EXISTING
particulars — e.g. binding a real number to the wrong study, or asserting a relation between two real findings that
neither supports? **That is the hole I most suspect. Find it or clear it.**
**And judge the OPPOSITE failure:** does the contract still BAN the legitimate scholarship the #1 system does
constantly (cellcog scored 9.8/10 for "eight tagged syntheses no single paper articulates")?` },
  { k: 'what-actually-wins', q: `**DOES THE PLAN AIM AT WHAT THE JUDGE ACTUALLY PAYS FOR? (I suspect it does not.)**
We now have the judge's OWN reasons — see context. It pays, in order:
**(1) declaring your evidence constraint (+5.0/+4.0 — the biggest measured win on the board; we score 1.5/10);**
(2) evidence-TYPE diversity (+2.6/+3.1); **(3) named, tagged original syntheses (+2.8, scored 9.8/10);**
(4) reconciling conflicting evidence (+2.4/+2.7); (5) a summary table (+2.4).
The synthesis's answer is "answer the actual question, with real evidence, and say something true" — and it books
document shape at ZERO.
**Has it over-rotated from "cosmetics matter" to "cosmetics are worthless" and thrown out the DECLARED-METHODOLOGY
lever — which costs ONE PARAGRAPH and is worth +5.0?** Go through the synthesis and check whether each of the five
judge-verified levers has a home in its plan. **Name what it misses. Be specific.**` },
]

const verdicts = (await parallel(LENSES.map(L => () =>
  agent(`${CTX}

# YOUR LENS
${L.q}

# RULES
- **VERIFY. Do not reason from the summary.** Open the files. Re-run the numbers. Read the code.
  Every document in this project has been wrong at least once — including the one you are attacking, the one that
  wrote it, and the two lenses summarised above.
- Default to REFUTED if you cannot confirm.
- A CONFIRMED claim is as valuable as a refuted one. Say plainly which it is.`,
    { schema: V, effort: 'max', label: `attack:${L.k}`, phase: 'Attack' })
    .then(v => v ? ({ lens: L.k, ...v }) : null)
))).filter(Boolean)
log(`verdicts: ${verdicts.map(v => `${v.lens}=${v.verdict}`).join(' | ')}`)

phase('Adjudicate')
const ADJ = {
  type: 'object',
  required: ['survives', 'dies', 'must_reverify', 'the_call', 'the_plan'],
  properties: {
    survives: { type: 'array', items: { type: 'string' } },
    dies: { type: 'array', items: { type: 'string' } },
    must_reverify: { type: 'array', items: { type: 'string' } },
    the_call: { type: 'string', description: 'What do we do FIRST? Be decisive.' },
    the_plan: { type: 'string', description: 'The final, consolidated, executable plan. Everything that survived, ordered.' },
  },
}
const adj = await agent(
  `Six adversarial lenses have now attacked the Opus synthesis. Adjudicate and write the FINAL PLAN.

${CTX}

# THE FOUR NEW VERDICTS
${JSON.stringify(verdicts, null, 1).slice(0, 100000)}

# ADJUDICATE
What SURVIVES. What DIES. What must be RE-VERIFIED.
Then write **THE FINAL PLAN** — everything that survived adversarial re-derivation, ordered, executable.

It must service the five things the judge SAYS it pays for (declared evidence constraint +5.0; evidence-type
diversity; named tagged syntheses; reconciling conflicts; a summary table) — those are MEASURED, not inferred.
It must respect the well-powered nulls (subsections are worthless; length is a floor not a lever).
It must resolve faithfulness: fabrication impossible, scholarly inference possible.
It must state what is UNMEASURED (generality: 37 runs, all task 72) and how we measure it CHEAPLY.
Be honest about whether it beats 0.5603 — and if not, say exactly what is missing.`,
  { schema: ADJ, effort: 'max', label: 'adjudicate:final', phase: 'Adjudicate' }
)
return { verdicts, adjudication: adj }
