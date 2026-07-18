export const meta = {
  name: 'wheel-turn-3',
  description: 'HAMSTER WHEEL turn 3 — Fable does deep thinking (parallel to Sol); Opus investigates, builds, tests, scores',
  phases: [
    { title: 'Think', detail: 'Fable diagnoses the failed arm (Sol runs in parallel, detached)' },
    { title: 'Investigate', detail: 'Opus reads the actual prose line by line — where is it truncated, repetitive, thin?' },
    { title: 'Build', detail: 'Opus implements the fixes' },
    { title: 'Test', detail: 'Opus proves each mechanism fired BEFORE any judge call' },
  ],
}

const PP = '/home/polaris/polaris_project'
const FW = '/home/polaris/wt/flywheel'
const BRIEF = `${PP}/wheel/turn3_brief.md`
const ARM = `${FW}/outputs/cellcog_arm/report.md`
const BASE = `${FW}/outputs/rank10_sections_compose/report.md`

const THINK = {
  type: 'object',
  required: ['diagnosis', 'turn3_changes', 'corpus_decision', 'prose_defect_root_cause', 'cheap_tests'],
  properties: {
    diagnosis: { type: 'string', description: 'Why did turn 2 lose? Be specific and brutal.' },
    turn3_changes: { type: 'array', items: { type: 'object', properties: { change: { type: 'string' }, targets_criterion: { type: 'string' }, expected: { type: 'string' }, where: { type: 'string' } } } },
    corpus_decision: { type: 'string', description: 'Compose from the 32-paper journal corpus, or TRANSFORM the 97-source rank10 report? Argue it with the measured comprehensiveness collapse (-1.14).' },
    prose_defect_root_cause: { type: 'string', description: 'The prose is repetitive/truncated/incomplete. PROMPT, TOKEN BUDGET, or ARCHITECTURE? Read the code and the actual output.' },
    cheap_tests: { type: 'array', items: { type: 'string' } },
  },
}

phase('Think')
const fable = await agent(
  `Read ${BRIEF} IN FULL — it contains the judge's OWN written critique of a real failed arm.

Then READ THE ACTUAL PROSE:
  - ${ARM}   (turn 2, scored 0.4224 — the arm that LOST)
  - ${BASE}  (rank10, scored 0.4382 — the baseline it lost to)
and the composer that produced it: ${FW}/scripts/cellcog_composer.py

THE ONE CONFIRMED WIN: visible journal attribution took the "Exclusive Citation of High-Quality Journal Articles"
criterion from **1.5/10 to 7.5/10** (+6.0). The judge says so in writing. That mechanism is REAL.

EVERYTHING ELSE LOST. The judge's reasons, verbatim:
- readability: *"repeated phrases such as 'Writing in,' duplicated clauses, incomplete sentences, awkward
  constructions, missing words"* — **we used ONE attribution template 135 times.**
- structure: *"repetition, incomplete sections, abrupt endings, and sections that do not fulfill their headings"*
- comprehensiveness: 4IR is *"thin, fragmented"*; disruption scale is *"extremely brief"*
- insight: implications are *"truncated, repetitive"*
- **and: "the article lacks a formal reference list, making verification difficult"** — I deleted the bibliography
  because RACE's cleaner strips it. The judge noticed its ABSENCE and marked us down.

AND THE HARD MEASURED FACT: paragraphs 677w -> 106w and H3 0 -> 21 moved readability by **-0.08**.
**STRUCTURE ALONE IS WORTH NOTHING.** The 898-article panel said so (a well-powered null) and turn 2 confirmed it.
The judge's actual complaint is COHESION — *"fragmented narrative ... without adequate transitions"*.

Diagnose it properly and design turn 3. Do not hand me a proxy.`,
  { schema: THINK, model: 'fable', effort: 'max', label: 'fable:diagnose-turn3', phase: 'Think' }
)
log(`fable: ${fable?.turn3_changes?.length ?? 0} changes proposed | corpus: ${String(fable?.corpus_decision).slice(0, 90)}`)

const INV = {
  type: 'object',
  required: ['findings', 'truncation_evidence', 'repetition_evidence'],
  properties: {
    findings: { type: 'array', items: { type: 'string' } },
    truncation_evidence: { type: 'string', description: 'Actual truncated/incomplete sentences from the arm, quoted.' },
    repetition_evidence: { type: 'string', description: 'Count the attribution templates. Quote the repetition.' },
    root_cause: { type: 'string' },
  },
}

phase('Investigate')
const inv = await agent(
  `Read ${ARM} (turn 2, scored 0.4224) LINE BY LINE, END TO END. The judge says it is *"repetitive, truncated,
incomplete, with abrupt endings and sections that do not fulfill their headings."* **FIND THE ACTUAL DEFECTS.**

Then read ${FW}/scripts/cellcog_composer.py — the WRITE_PROMPT, the max_tokens, the _clean() gate, the section loop.

ANSWER, WITH EVIDENCE FROM THE TEXT:
1. **HOW MANY attribution templates are used?** Count "Writing in the" and every variant. The judge calls it out
   explicitly as a clarity defect.
2. **WHERE is it truncated?** Quote the abrupt endings and incomplete sentences. Is it the max_tokens (3000)?
   Is it the gate dropping a sentence mid-paragraph and leaving a dangling clause?
3. **WHICH sections "do not fulfill their headings"?** Which are thin or empty?
4. **Is the 4IR section actually thin?** The judge says *"thin, fragmented"* — quote it.
5. Does the report have a REFERENCE LIST? (The judge says it does not, and penalised us.)
Be concrete. Quote. Count.`,
  { schema: INV, effort: 'max', label: 'opus:investigate-the-prose', phase: 'Investigate' }
)
log(`investigation: ${inv?.findings?.length ?? 0} defects found`)

const BUILT = {
  type: 'object',
  required: ['ok', 'changes_made', 'evidence'],
  properties: {
    ok: { type: 'boolean' },
    changes_made: { type: 'array', items: { type: 'string' } },
    evidence: { type: 'string', description: 'Paste the actual test output proving each fix works.' },
  },
}

phase('Build')
const build = await agent(
  `Implement the turn-3 fixes in ${FW}/scripts/cellcog_composer.py. **You are Opus; you build and you test.**

FABLE'S DIAGNOSIS:
${JSON.stringify(fable, null, 1).slice(0, 12000)}

THE LINE-BY-LINE INVESTIGATION OF THE ACTUAL PROSE:
${JSON.stringify(inv, null, 1).slice(0, 10000)}

THE CONFIRMED WIN TO PRESERVE: visible journal attribution (1.5 -> 7.5 on the journal-citation criterion).
**DO NOT BREAK IT.** But the judge says one template used 135 times *"severely reduces clarity"*.

MANDATORY FIXES (from the judge's own critique):
1. **ROTATE THE ATTRIBUTION FORMS.** At least 5 natural variants, e.g.:
   - "Writing in the <JOURNAL> in <YEAR>, <AUTHORS> show that ..."
   - "<AUTHORS>, in the <JOURNAL>, find that ..."
   - "In their <YEAR> <JOURNAL> article, <AUTHORS> report ..."
   - "<AUTHORS> (<JOURNAL>) demonstrate that ..."
   - "Evidence from <AUTHORS> in the <JOURNAL> indicates ..."
   Enforce it: no single template may exceed ~30% of attributions.
2. **RESTORE A REFERENCE LIST.** The judge explicitly penalised its absence. Emit a proper bibliography.
3. **FIX TRUNCATION.** Sections end abruptly. Raise max_tokens; and when the gate drops a sentence, do not leave a
   dangling clause — drop the whole clause cleanly.
4. **DEEPEN THE RUBRIC-NAMED THIN SECTIONS**: 4IR grounding (judge: "thin, fragmented"), disruption scale/speed
   ("extremely brief"), and implications/research agenda ("truncated, repetitive"). These are NAMED CRITERIA.
5. **ADD TRANSITIONS.** The judge's real readability complaint is COHESION, not paragraph size — proven: 677w->106w
   moved readability -0.08. Each paragraph must connect to the previous one.

Then TEST: run the composer, and PROVE each fix fired (count the templates; confirm the reference list exists;
confirm no truncated sentences; confirm the thin sections grew). Paste the real output.
Run \`python scripts/test_gate_is_wired.py\` — it MUST stay green. **Faithfulness is not negotiable.**`,
  { schema: BUILT, effort: 'max', label: 'opus:build-turn3', phase: 'Build' }
)
log(`build: ok=${build?.ok} — ${(build?.changes_made ?? []).length} changes`)
return { fable, investigation: inv, build }
