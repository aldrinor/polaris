export const meta = {
  name: 'artifact-forensics',
  description: 'Forensic measurement of every competitor artifact across MANY tasks — find what actually correlates with score, not what we assume',
  phases: [
    { title: 'Instrument', detail: 'build a measurement harness over the cleaned artifacts' },
    { title: 'Measure', detail: 'multi-task, multi-system structural + rhetorical profiling' },
    { title: 'Correlate', detail: 'which measured features actually track the score — and which do not' },
  ],
}

const CORPUS = '/home/polaris/polaris_project/drb_corpus'
const FW = '/home/polaris/wt/flywheel'

const BOARD = `GPT-5.5 board (our evaluator): cellcog-max 55.78 | WhaleCloud 54.78 | bodhi 54.07 | lunon 53.51 |
dalpha 53.10 | sourcery 51.17 | gemini-2.5-pro-DR 49.98 (== the reference, parity=0.50) | openai-DR 47.84 |
POLARIS 43.82 | perplexity 43.05 | grok 41.22.
Artifacts on disk (100 tasks each): cellcog, tavily, onyx, deepinsight, baidu-qianfan.
CRITICAL: RACE runs an LLM ArticleCleaner that STRIPS all citation markers, reference lists and footnotes BEFORE
judging (${FW}/third_party/deep_research_bench/utils/clean_article.py). ALL measurement must be on the CLEANED text,
or on features the cleaner preserves. Headings, paragraphs, bullets and tables SURVIVE; citations do NOT.`

const M = {
  type: 'object',
  required: ['ok', 'findings', 'evidence'],
  properties: {
    ok: { type: 'boolean' },
    findings: { type: 'array', items: { type: 'string' } },
    evidence: { type: 'string', description: 'Actual numbers/tables. No claim without output.' },
    surprises: { type: 'array', items: { type: 'string' }, description: 'Anything that CONTRADICTS our current thesis. These are the most valuable findings.' },
  },
}

phase('Measure')
const probes = await parallel([
  () => agent(`STRUCTURAL PROFILE across MANY TASKS (not just 72 — we must not overfit to one task).

${BOARD}

For EVERY system artifact in ${CORPUS} and for a stratified sample of >= 25 tasks each, measure on the CLEANED text:
words, H1/H2/H3 counts, paragraph count, paragraph-length distribution (median + IQR), bullets, tables, sentences
per paragraph, and whether structure VARIES BY TASK GENRE (a literature review vs a market analysis vs a how-to).

THE KEY QUESTION: cellcog (rank 1) used 0 bullets and 0 tables on task 72 while tavily (near the bottom) used 141
bullets. Is that a GENRE adaptation (cellcog uses bullets/tables on OTHER task types) or a global house style?
Get the per-task numbers. This decides whether our rebuild should ban bullets outright or ban them only for
literature reviews.

Also profile POLARIS's own rank10 report (${FW}/outputs/rank10_sections_compose/report.md, body only — split at
'## References') as the comparison point. Paste the real table.`,
    { schema: M, effort: 'high', label: 'probe:structure-by-genre', phase: 'Measure' }),

  () => agent(`RHETORICAL / SYNTHESIS PROFILE — how do winners actually WRITE the argument?

${BOARD}

Read ACTUAL PROSE (not just counts) from cellcog (55.78), onyx, tavily, qianfan and the reference (49.98), across
>= 8 varied tasks. Characterise, with VERBATIM QUOTES:
  - How do they present CONFLICTING evidence? Do they reconcile it, and with what sentence pattern?
  - Do they name studies/authors/venues IN THE RUNNING PROSE (which survives the cleaner) vs relying on [n] markers
    (which are DELETED)? Count named-study attributions per 1000 words.
  - Do they have a dedicated synthesis / tensions / limitations / future-research section? What is in it?
  - Do they make claims that are NOT traceable to a source — i.e. genuine cross-source inference? Quote examples.
    QUANTIFY: roughly what fraction of sentences are ungrounded interpretation vs grounded fact?
  - Do they hedge? What is the hedging vocabulary?
  - Executive summary / TL;DR at the top? Numbered sections?

WHY THIS MATTERS: POLARIS span-verifies EVERY sentence, which structurally forbids cross-source inference, and we
score worst on insight (0.4238, weight 0.32). If the winners ship substantial ungrounded interpretation, that is
the mechanism — and we must decide, explicitly, how much of it we are willing to ship under a hedged, uncited,
number-free contract. Quantify what they actually do.`,
    { schema: M, effort: 'high', label: 'probe:rhetoric-synthesis', phase: 'Measure' }),

  () => agent(`FEATURE-vs-SCORE CORRELATION — which measurable features actually track the score?

${BOARD}

Using per-system artifacts in ${CORPUS} plus the published per-dimension scores in
${CORPUS}/leaderboard_gpt55_judge.csv (and leaderboard_gemini25pro_judge.csv for the legacy board), test which
document features correlate with OVERALL and with each DIMENSION:
  words | H3 count | median paragraph length | bullets | tables | named-study attributions per 1k words |
  hedging density | dedicated-synthesis-section present | sections count | sentences per paragraph

We only have ~5 systems with artifacts, so this is descriptive, NOT inferential — DO NOT over-claim significance
with n=5. Report the direction and the counter-examples. Specifically test these claims of ours:
  (a) "short paragraphs + many H3 => higher readability AND higher insight" — is it true across systems?
  (b) "length drives comprehensiveness" — but onyx scores well on only 4,554 words. Where does that leave it?
  (c) "bullets hurt" — tavily is bullet-heavy and low. Is that causal or coincidental (tavily may just be weaker)?
  (d) deepinsight ships ONE 24,333-word paragraph with zero headings. What does it score, and what does that do to
      the "structure matters" thesis? THIS IS THE STRONGEST AVAILABLE TEST OF OUR CENTRAL HYPOTHESIS — chase it.

Be brutally honest. If the structure thesis does not survive contact with the data, SAY SO — we are about to build
a whole wave on it.`,
    { schema: M, effort: 'max', label: 'probe:what-actually-correlates', phase: 'Measure' }),
])
const P = probes.filter(Boolean)
log(`forensics: ${P.filter(p => p.ok).length}/3 probes ok | surprises: ${P.flatMap(p => p.surprises ?? []).length}`)

phase('Correlate')
const SYN = {
  type: 'object',
  required: ['what_the_data_says', 'thesis_survives', 'corrections_to_our_plan', 'open_questions'],
  properties: {
    what_the_data_says: { type: 'string' },
    thesis_survives: { type: 'boolean', description: 'Does "document mode / structure + synthesis" survive the artifact data?' },
    corrections_to_our_plan: { type: 'array', items: { type: 'string' } },
    open_questions: { type: 'array', items: { type: 'string' } },
  },
}
const syn = await agent(
  `Synthesise the forensic evidence into a verdict on OUR central thesis.

OUR THESIS (about to be built): POLARIS scores 43.82 because its report is 12 paragraphs of 677 words with zero
subsections and lists facts rather than explaining them. Fix = subsections + ~80-word single-idea paragraphs +
cross-source reconciliation sentences (hedged, no new numbers/entities) + a dedicated Critical Synthesis section
+ more coverage (7.7k -> ~11-12k words).

THE PROBES:
${JSON.stringify(P, null, 1).slice(0, 45000)}

Answer honestly:
- Does the artifact data SUPPORT the structure thesis, or is structure merely CORRELATED with systems that are
  better in other ways? (deepinsight's single 24k-word paragraph is the sharpest test — what does it score?)
- What in our plan is now WRONG or unsupported?
- What did we MISS entirely?
- What can the artifacts NOT tell us (i.e. where must we run our own experiment)?

An honest "the data cannot distinguish these hypotheses" is more useful than a confident story.`,
  { schema: SYN, model: 'fable', effort: 'max', label: 'forensics:verdict', phase: 'Correlate' }
)
return { probes: P, verdict: syn }
