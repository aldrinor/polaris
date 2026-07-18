export const meta = {
  name: 'judge-mechanics-and-techniques',
  description: 'Read the RACE judge code/prompts line by line, and find every published technique with real ablation numbers',
  phases: [
    { title: 'Judge', detail: 'reverse-engineer exactly how points are assigned' },
    { title: 'Literature', detail: 'published techniques with measured RACE gains' },
    { title: 'Synthesise', detail: 'what the judge pays for, and who has proven how to get it' },
  ],
}

const FW = '/home/polaris/wt/flywheel'
const DRB = `${FW}/third_party/deep_research_bench`

const M = {
  type: 'object',
  required: ['ok', 'findings', 'evidence'],
  properties: {
    ok: { type: 'boolean' },
    findings: { type: 'array', items: { type: 'string' } },
    evidence: { type: 'string' },
    exploitable: { type: 'array', items: { type: 'string' }, description: 'Mechanics that are exploitable WITHOUT cheating — i.e. legitimate writing choices the scoring rewards.' },
  },
}

phase('Judge')
const judge = await parallel([
  () => agent(`READ THE RACE JUDGE'S CODE AND PROMPTS, LINE BY LINE. Everything here is on disk — do not speculate.

  ${DRB}/deepresearch_bench_race.py     (the harness)
  ${DRB}/prompt/score_prompt_en.py      (the SCORING prompt — the actual rubric the judge follows)
  ${DRB}/prompt/criteria_prompt_en.py   (if present — how per-task criteria are generated)
  ${DRB}/utils/clean_article.py         (ArticleCleaner — strips citations/references BEFORE judging)
  ${DRB}/utils/score_calculator.py      (weighted aggregation)

Answer PRECISELY, quoting the prompt text:
1. What EXACTLY is the judge asked to do? Does it score target and reference in ONE call or two? Does it see them
   SIDE BY SIDE? Which is "article_1"? Is there a position/order effect we should know about?
2. What is the SCORING SCALE per criterion, and how do raw scores become the 0-1 overall? Confirm
   Overall = target/(target+reference). What score BAND does a criterion need to beat parity?
3. What does the rubric SAY it rewards on INSIGHT and on COMPREHENSIVENESS? Quote the criterion text verbatim.
4. Does the judge write a comparative ANALYSIS before scoring? If so, does a weakness in one dimension BLEED into
   the scoring of others (contrast effects)?
5. Does anything in the prompt reward or penalise: length, headings, tables, bullets, hedging, named sources in
   prose, an executive summary, explicit uncertainty?

This is the single most authoritative source available to us — it is the actual grader. Mine it exhaustively.`,
    { schema: M, effort: 'max', label: 'judge:read-the-rubric', phase: 'Judge' }),

  () => agent(`THE JUDGE'S BIASES AND THE SCORING MATH — what beats a 49.98 reference?

Files: ${DRB}/prompt/score_prompt_en.py, ${DRB}/utils/score_calculator.py, ${DRB}/deepresearch_bench_race.py.
Also read the DeepResearch Bench paper (arXiv 2506.11763) on RACE's design and validation.

Work out the ARITHMETIC of winning:
- The reference (gemini-2.5-pro-DR) scores 49.98 overall on this board — essentially parity with itself.
- SOTA (cellcog-max) = 55.78. On the dimensions: comprehensiveness 56.34, insight 57.08, IF 55.30, readability 51.94.
- POLARIS = 43.82 (comp 45.49, insight 42.38, IF 44.09, read 37.74) on task 72.
Given Overall = target/(target+reference): what RAW criterion scores must we hit to reach 50 / 52 / 55?
How much raw-score improvement does one point of overall cost? WHERE is the cheapest point on the board for us
(our readability is 37.74 vs SOTA's 51.94 — is readability the cheapest, given it is only 0.14 weight)?
Do the actual maths and show it.

Then search for published work on LLM-JUDGE BIASES relevant here: length bias, structure/formatting bias, position
bias, self-preference, verbosity bias, list bias. Which are DOCUMENTED with numbers, and which apply to a
reference-based pairwise judge like RACE? We need to know how much of the 12-point gap is presentation.`,
    { schema: M, effort: 'max', label: 'judge:scoring-math-and-bias', phase: 'Judge' }),
])
log(`judge phase: ${judge.filter(Boolean).filter(j => j.ok).length}/2 ok`)

phase('Literature')
const lit = await parallel([
  () => agent(`Find EVERY published deep-research / report-generation technique WITH MEASURED ABLATION NUMBERS on
DeepResearch Bench (RACE) or a directly comparable report-quality benchmark. 2025-2026, and search GitHub too.

Cover at minimum: WebWeaver, FS-Researcher (arXiv 2602.01566), TTD-DR (arXiv 2507.16075), STORM / Co-STORM,
OpenDeepResearch, ADORE, DeepResearcher, Test-Time Diffusion, plan-and-write, outline-then-expand, writer-critic
loops, self-refine/reflexion, multi-agent debate for reports, long-form RAG, hierarchical/agentic composition.

For each: WHAT IS THE MECHANISM, and WHAT DID IT MEASURE? I want ablation tables — "X without the outline-refinement
loop drops N points". Reject anything with no numbers. Say explicitly which evaluator (Gemini-2.5-Pro legacy vs
GPT-5.5) any RACE number was produced under — they are NOT comparable.

Our situation: we are at 43.82; insight (0.32 weight) is our worst dimension at 42.38; we span-verify every sentence
which forbids cross-source inference. Prioritise techniques that raise INSIGHT and that do NOT require abandoning
grounded generation.`,
    { schema: M, effort: 'high', label: 'lit:ablations-with-numbers', phase: 'Literature' }),

  () => agent(`THE SYNTHESIS PROBLEM specifically — how does the published literature produce faithful CROSS-SOURCE
INFERENCE in generated reports?

Our core constraint: POLARIS verifies every sentence against a source span (entailment judge; a sentence introducing
"a fact, entity, MECHANISM ... NOT present in the SPAN" is NEUTRAL => DELETED). That is exactly the sentence type
that earns insight. We are considering a two-tier contract: FACT (span-grounded) + INTERPRETATION (hedged, no new
numbers/entities, no citations, contradiction-screened).

Search the literature and GitHub for: attribution/grounding frameworks that admit INFERENCE (not just extraction);
"inference-level attribution", "reasoning attribution", claim-level vs inference-level provenance; RAG faithfulness
work that separates EXTRACTIVE from ABSTRACTIVE claims; multi-document summarisation with cross-document reasoning;
hallucination-safe synthesis; NLI-based verification of inferences from MULTIPLE premises (rather than one span);
"entailment from a set of premises" verification. Also: how do systematic-review/meta-analysis tools handle this?

WHAT WE NEED: prior art (or a proof that none exists) for admitting a cross-source inference sentence while
GUARANTEEING no fabrication. If our two-tier contract is a known pattern, find its name and its failure modes. If it
is genuinely novel, say so — that changes how carefully we must test it.`,
    { schema: M, effort: 'max', label: 'lit:faithful-inference', phase: 'Literature' }),
])
log(`literature: ${lit.filter(Boolean).filter(l => l.ok).length}/2 ok`)

phase('Synthesise')
const OUT = {
  type: 'object',
  required: ['what_the_judge_pays_for', 'cheapest_points', 'proven_techniques', 'unknowns'],
  properties: {
    what_the_judge_pays_for: { type: 'string', description: 'From the rubric text itself, not from vibes.' },
    cheapest_points: { type: 'string', description: 'The arithmetic: where do we buy overall points most cheaply, given the weights and our per-dimension deficits?' },
    proven_techniques: { type: 'array', items: { type: 'object', properties: { name: { type: 'string' }, mechanism: { type: 'string' }, measured_gain: { type: 'string' }, evaluator: { type: 'string' }, applicable_to_us: { type: 'string' } } } },
    unknowns: { type: 'array', items: { type: 'string' } },
  },
}
const out = await agent(
  `Synthesise: what does the RACE judge ACTUALLY pay for, and who has PROVEN how to get it?

JUDGE MECHANICS:
${JSON.stringify(judge.filter(Boolean), null, 1).slice(0, 30000)}

LITERATURE:
${JSON.stringify(lit.filter(Boolean), null, 1).slice(0, 30000)}

POLARIS: 43.82 overall (comp 45.49 | insight 42.38 | IF 44.09 | readability 37.74). Weights: insight .32,
comprehensiveness .29, IF .25, readability .14. Reference = 49.98 (parity). SOTA cellcog-max = 55.78.

Give me the rubric-grounded answer, the arithmetic of where points are cheapest, and only techniques with REAL
measured numbers (state the evaluator for each). Be explicit about what is NOT known — those are the places we
must run our own experiment rather than trust a paper.`,
  { schema: OUT, model: 'fable', effort: 'max', label: 'synth:judge-and-techniques', phase: 'Synthesise' }
)
return { judge: judge.filter(Boolean), literature: lit.filter(Boolean), synthesis: out }
