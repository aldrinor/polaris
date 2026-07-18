export const meta = {
  name: 'consolidate-the-one-plan',
  description: 'Merge all six adversarial verdicts, the judge oracle, and every correction into ONE executable plan — then hand it to the wheel',
  phases: [
    { title: 'Consolidate', detail: 'three independent consolidators, different priorities' },
    { title: 'Attack', detail: 'attack the consolidation itself' },
    { title: 'Final', detail: 'the one plan' },
  ],
}

const PP = '/home/polaris/polaris_project'
const FW = '/home/polaris/wt/flywheel'
const F = `${PP}/sota_review/foundation`

const GROUND = `
# READ THESE FIRST, IN FULL
- ${F}/ALL_VERDICTS.md   — all SIX adversarial verdicts + the adjudication. Everything here has been ATTACKED.
- ${F}/FINAL_PLAN.md     — the adjudicator's plan.
- ${F}/SOL_PLAN_V4.md, ${F}/FABLE_PLAN_V4.md, ${F}/OPERATOR_FIXES.md, ${F}/OPUS_SYNTHESIS_V1.md — the inputs.

# THE MEASURED TRUTH (all from the judge's OWN written output — scripts/judge_feedback.py)
| system | insight | compreh | instr | read | OVERALL |
|---|---|---|---|---|---|
| cellcog (#1) | 9.53 | 9.48 | 9.24 | 9.11 | **0.5603** (MEASURED today, not estimated) |
| bodhi | 8.84 | 9.02 | 8.99 | 8.60 | 0.5441 |
| **POLARIS** | 6.45 | 7.22 | 6.11 | **4.71** | **0.4382** |
Weights: INSIGHT .32 | COMPREH .29 | INSTR .25 | READ .14.

**R IS NOT A CONSTANT — PROVEN.** The SAME reference article scores 8.033 against us, 7.545 against bodhi,
7.363 against cellcog. The judge marks the reference DOWN as the target improves. Proof without statistics: if R
were fixed at 8.033, cellcog's 0.5603 would require T = 10.24/10. Impossible. cellcog scored it. Therefore R fell.
=> **Every improvement pays TWICE. Our weak report is currently INFLATING our opponent's score.**

**THE HONEST BAR: our weighted mean across all 25 criteria must go 6.35 -> 9.63/10 — ABOVE cellcog's 9.38.**
That needs ~13 stacked levers. cellcog is not winning on a trick; it is an outstanding report.

# WHAT THE JUDGE SAYS IT PAYS FOR (its own words, measured — not inferred)
- **"explicitly states an evidence constraint to cite only journal articles"** — bodhi +5.0 raw, cellcog +4.0 raw.
  **We score 1.5/10; the REFERENCE scores 2.0.** Highest headroom on the board. **BUT NOTE THE UNITS ERROR THAT WAS
  IN OUR OWN BRIEF: +5.0 is RAW CRITERION POINTS. In SCORE units it is +0.0093 — at the resolvable threshold, not
  a headline lever.** Price everything in SCORE units.
- "compares seminal theory, causal studies, meta-analyses, field experiments, administrative data, qualitative work"
  (evidence-TYPE diversity, not more papers) — +2.6/+3.1 raw
- **"its eight tagged syntheses ... genuine synthesis beyond summary" — cellcog scored 9.8/10**
- "especially effective in reconciling conflicting evidence" — +2.4/+2.7 raw
- On US: *"weak paragraph cohesion... extremely long paragraphs... a fragmented narrative"* (-4.7, our biggest loss)
  and *"some claims are difficult to attribute because no formal citations are provided"*

# WHAT SURVIVED ADVERSARIAL ATTACK
- **THE CHANNEL DEFECT.** RACE's cleaner deletes our 345 [n] markers and our reference list before the judge reads a
  word — leaving 3 journal names and 11 CONSULTANCY names visible. **We are graded on a corpus we did not submit.**
  Our 1.5/10 on the journal criterion is a CHANNEL defect, not a corpus defect.
- **READABILITY IS NOT WORTHLESS.** The 7 readability criteria taken to cellcog's level = **+0.0270 with the R-drag —
  2.9x the resolvable effect.** (The "document shape is worth zero" claim was a UNITS ERROR: the beta was per SD of a
  RESIDUALIZED regressor. Correctly scaled, log(words) = +0.0211/SD, t=5.0.)
- **BUT: sections/H3 ARE a well-powered null** (+0.0020/SD). "Add 30+ subsections" is DEAD. The H3 r=+0.519 that
  everyone read as a mandate is 100% SYSTEM IDENTITY. **And length SATURATES at ~8,000 words — it is a FLOOR
  (~5,000w), not a lever. We are at 9,194, past the knee.**
- **THE OVERFIT IS IN THE OUTLINE, NOT THE TERM LISTS.** \`multi_section_generator.py:785 _ALLOWED_SECTIONS\` hardcodes
  a DRUG-TRIAL genre (Efficacy/Safety/Regulatory/Dose Response). **AND THE FIX IS ALREADY BUILT AND UNWIRED:**
  \`config/domain_packs/{clinical,economics,general,policy,science,technology}.yaml\` each own a \`sections:\` list.
- **GENERALITY IS UNMEASURED, NOT DISPROVEN.** The "0.263" was five ABORTED runs, five weeks stale. But: **38 scored
  runs since 07-12, ALL task 72, zero on anything else.** We do not know what we score on an unseen question.
- **FABRICATION AND INSIGHT OCCUPY THE SAME CELL.** Both are non-entailed relations over true particulars. The
  contract's premise-independent rules reject **97% of cellcog's 9.8/10 prose.** Entailment CANNOT separate them.
- **★ THE INVARIANT (the resolution): EVERY SENTENCE IS EITHER ATTRIBUTED OR OWNED.**
  ATTRIBUTED = names a source; **must be ENTAILED by that source's own verbatim span**; carries the numbers.
  OWNED = the reviewer's voice; **may not name a source**; no new particulars; contradiction-screened;
  **EXPLICITLY PERMITTED TO BE NON-ENTAILED — because that is what insight IS.**
  **FABRICATION = an ATTRIBUTED sentence its source does not entail. INSIGHT = an OWNED sentence its premises do not
  entail. SAME LOGICAL SHAPE — distinguished by WHOSE VOICE, not by entailment.**

# ALREADY BUILT AND WORKING (do not re-plan these; USE them)
- \`scripts/judge_feedback.py\` — THE ORACLE. Captures the judge's per-criterion scores AND written analysis, for
  both articles. The harness discards it. **This is how we stopped guessing.**
- \`scripts/criterion_ab.py\` — criterion-level A/B. **20 of 25 criteria cannot clear a scalar kill rule even at 10/10;
  a lever must be judged on THE CRITERION IT TARGETS.**
- \`scripts/test_gate_is_wired.py\` — CI canary that FAILS if the faithfulness gate is bypassed. **All 4 checks pass.**
- \`scripts/cellcog_composer.py\` — gate now ON THE CRITICAL PATH; mechanism launder CLOSED (34 fabrications purged);
  FABRICATED_BINDING caught by name.
- Baseline pinned: rank10 = 0.4382 (k=5, judge SD 0.0074).
`;

const PLAN = {
  type: 'object',
  required: ['thesis', 'the_wheel', 'turns', 'integrity', 'generality', 'expected', 'kill_rules'],
  properties: {
    thesis: { type: 'string', description: 'Three sentences. What actually gets us from 0.4382 to >0.5603.' },
    the_wheel: { type: 'string', description: 'The loop: fix -> compose -> score (CRITERION level) -> read the judge -> fix. Concretely, with the scripts we already have.' },
    turns: {
      type: 'array',
      description: 'The ORDERED turns. Each is ONE executable unit of work with a measurable target.',
      items: {
        type: 'object',
        required: ['n', 'name', 'change', 'targets_criteria', 'expected_score_units', 'cheap_test', 'kill'],
        properties: {
          n: { type: 'number' },
          name: { type: 'string' },
          change: { type: 'string', description: 'Concrete. file:line. What code changes.' },
          targets_criteria: { type: 'array', items: { type: 'string' }, description: 'The EXACT rubric criteria this moves — we measure the lever on THESE, not on the scalar.' },
          expected_score_units: { type: 'string', description: 'In SCORE units (not raw criterion points). Price honestly.' },
          cheap_test: { type: 'string', description: 'Proves the mechanism FIRED before any judge call.' },
          kill: { type: 'string', description: 'What result kills this turn.' },
        },
      },
    },
    integrity: { type: 'string', description: 'The faithfulness contract, rewritten around VOICE (ATTRIBUTED vs OWNED). What ships, what is deleted, what the CI canary asserts.' },
    generality: { type: 'string', description: 'How we wire the domain packs and MEASURE generality (38 runs, all task 72 — we do not know). The cheapest test.' },
    expected: { type: 'string', description: 'Honest. Does the stack of turns beat 0.5603? If not, say how short and what is missing.' },
    kill_rules: { type: 'string', description: 'Pre-registered. What stops us. No re-narration.' },
  },
}

phase('Consolidate')
const ANGLES = [
  { k: 'score-first', q: 'Consolidate with ONE priority: the fastest path to a MEASURED score above 0.5603 on task 72. Order the turns by score-units-per-hour. Be ruthless about what is worth doing.' },
  { k: 'system-first', q: 'Consolidate with ONE priority: a GENERAL system. 38 scored runs, all task 72 — generality is UNMEASURED. Wire the domain packs. Make the answer-shape derived. A system that answers one question is a demo. But do NOT let this become an excuse to defer the score — sequence both.' },
  { k: 'integrity-first', q: 'Consolidate with ONE priority: the faithfulness architecture, rebuilt around the ATTRIBUTED/OWNED invariant. The old contract rejects 97% of the prose that scores 9.8/10. Design the contract that admits cellcog-class synthesis and still makes fabrication impossible — then fit the score plan around it.' },
]
const cons = await parallel(ANGLES.map(a => () =>
  agent(`${GROUND}

# YOUR ANGLE
${a.q}

# RULES
- **Everything here has already been ATTACKED.** Build on what SURVIVED; do not resurrect what DIED.
- **Price every lever in SCORE UNITS, not raw criterion points.** That units error was in our own brief and it
  inflated the headline lever 5x.
- **Every lever must name the CRITERIA it targets** — we now measure levers at the criterion level.
- Be honest about the bar: **6.35 -> 9.63/10 weighted, above cellcog's 9.38.** ~13 stacked levers.
- No proxies. Verify anything load-bearing.`,
    { schema: PLAN, effort: 'max', label: `consolidate:${a.k}`, phase: 'Consolidate' })
))
const C = cons.filter(Boolean)
log(`consolidators: ${C.length}/3`)

phase('Attack')
const V = { type: 'object', required: ['refuted', 'reasoning'], properties: { refuted: { type: 'boolean' }, reasoning: { type: 'string' }, fix: { type: 'string' } } }
const attacked = await parallel(C.map((c, i) => () =>
  agent(`Attack this consolidated plan. Default refuted=true if uncertain.

THESIS: ${c.thesis}
WHEEL: ${String(c.the_wheel).slice(0, 2500)}
TURNS: ${JSON.stringify(c.turns).slice(0, 6000)}
INTEGRITY: ${String(c.integrity).slice(0, 2000)}
EXPECTED: ${c.expected}

ATTACK ON ALL OF:
1. **ARITHMETIC**: do the turns, priced in SCORE units, actually sum to >0.5603? Remember R DROPS as we improve
   (proven), so every lever is worth ~20% more than an R-fixed model says. Check the sum honestly.
2. **DEAD LEVERS**: does it resurrect anything that DIED? (30+ subsections = well-powered null. Length beyond 8k =
   saturated. "Document shape is worthless" = a units error, but so was "+5.0 is the biggest lever".)
3. **FABRICATION**: under the ATTRIBUTED/OWNED contract, trace a concrete path by which a false claim ships.
4. **THE UNMEASURED**: does it actually MEASURE generality, or just assert it? 38 runs, all task 72.
5. **WASTE**: is any turn unmeasurable at the criterion level? A lever we cannot resolve is a lever we cannot keep.`,
    { schema: V, effort: 'high', label: `attack:${ANGLES[i].k}`, phase: 'Attack' })
    .then(v => ({ angle: ANGLES[i].k, plan: c, verdict: v }))
))
const A = attacked.filter(Boolean)
log(`attacks: ${A.filter(a => a.verdict?.refuted).length}/${A.length} refuted`)

phase('Final')
const final = await agent(
  `Three consolidators produced plans (score-first, system-first, integrity-first). Each was attacked.

${GROUND}

# THE THREE PLANS AND THEIR ATTACKS
${JSON.stringify(A.map(a => ({
    angle: a.angle, thesis: a.plan.thesis,
    turns: a.plan.turns, integrity: String(a.plan.integrity).slice(0, 2500),
    generality: String(a.plan.generality).slice(0, 1500),
    expected: a.plan.expected, kill: a.plan.kill_rules,
    attack: { refuted: a.verdict?.refuted, why: String(a.verdict?.reasoning).slice(0, 2500), fix: a.verdict?.fix },
  })), null, 1).slice(0, 110000)}

# WRITE THE ONE PLAN
Merge them. Where they conflict, DECIDE and justify. Where an attack landed, FIX or DROP.

It must be **THE WHEEL**: an ordered list of TURNS, each one executable, each naming the CRITERIA it targets, each
with a CHEAP TEST that proves the mechanism fired before a judge call, and each with a KILL condition.

Non-negotiable:
- **Turn 1 is already DONE**: the faithfulness gate is wired, the mechanism launder is closed, the canary is green.
- Price in SCORE units. Account for the R-drag (every lever is worth ~20% more than an R-fixed model says).
- Measure levers at the CRITERION level (scripts/criterion_ab.py). 20 of 25 criteria cannot clear a scalar rule.
- Rebuild the contract around **ATTRIBUTED vs OWNED**. The old one rejects 97% of 9.8/10 prose.
- **MEASURE generality** — do not assert it. 38 runs, all task 72.
- Be honest: does the stack beat 0.5603? **If not, say exactly how short and what is missing.** Do not re-target.`,
  { schema: PLAN, effort: 'max', label: 'the-one-plan', phase: 'Final' }
)
return { consolidations: C.map(c => c.thesis), attacks: A.map(a => ({ angle: a.angle, refuted: a.verdict?.refuted })), plan: final }
