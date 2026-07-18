export const meta = {
  name: 'how-sota-is-achieved',
  description: 'Deep multi-modal research into how ADORE (0.5265), Tavily (0.5244) and every >0.50 system beat the human reference on DeepResearch Bench RACE — and what is transferable to POLARIS',
  phases: [
    { title: 'Sweep', detail: 'parallel multi-angle search: leaderboard, papers, code, judge-mechanics' },
    { title: 'Deep read', detail: 'fetch and read the primary sources properly' },
    { title: 'Verify', detail: 'adversarially check every extracted technique claim' },
    { title: 'Transfer', detail: 'map verified techniques onto POLARIS gaps; what we can steal, what we cannot' },
  ],
}

const FIND = {
  type: 'object',
  required: ['findings'],
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        required: ['claim', 'source_url', 'confidence', 'detail'],
        properties: {
          claim: { type: 'string', description: 'A specific, checkable claim about HOW a system scores what it scores.' },
          detail: { type: 'string', description: 'The mechanism, in enough detail to implement or refute.' },
          source_url: { type: 'string' },
          system: { type: 'string', description: 'ADORE / Tavily / other / RACE-judge-itself' },
          confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
        },
      },
    },
  },
}

// OUR MEASURED POSITION — every agent gets this so nothing is generic.
const US = `POLARIS's MEASURED position on DeepResearch Bench task 72 (RACE, gpt-5.5 evaluator, k=5 pinned):
  overall 0.4382 | comprehensiveness 0.4549 | insight 0.4238 | instruction-following 0.4409 | readability 0.3774
  baseline was 0.4062. Human reference = 0.5000 by construction. SOTA (ADORE) = 0.5265. Our gap = 0.088.
  RACE formula: Overall = target/(target+reference), an LLM judge scores BOTH against per-task weighted criteria.
  Task-72 dimension weights: insight 0.32, comprehensiveness 0.29, instruction-following 0.25, readability 0.14.
  KEY MECHANIC WE VERIFIED: RACE runs an LLM "ArticleCleaner" that STRIPS ALL CITATION MARKERS, REFERENCE LISTS
  AND FOOTNOTES before the judge reads anything (our 9,300 words -> 7,692; 345 [n] markers -> 0; bibliography deleted).
  So citation/bibliography quality is INVISIBLE to RACE. Only the running prose scores.
  OUR KNOWN WEAKNESS: the judge reads 12 paragraphs averaging 633 words, 0 subsections, 0 tables, 0 bullets.
  The human reference: 59 paragraphs averaging 142 words, 24 H3, 10 tables, 91 bullets. We LIST findings; the
  reference EXPLAINS them. Our pipeline span-grounds every sentence, which structurally forbids cross-source
  inference — the sentence type that earns INSIGHT (0.32, heaviest weight, our worst dimension).`

phase('Sweep')
const ANGLES = [
  { k: 'adore', q: `ADORE — the #1 system on DeepResearch Bench RACE (~52.65). Find the paper, arXiv entry, blog post, and any code. What is the ACTUAL METHOD? Search: "ADORE deep research agent", "ADORE DeepResearch Bench", "ADORE RACE 52.65", "ADORE report generation agent". Extract the architecture: how does it plan, retrieve, and above all COMPOSE the report? What does it do that a naive retrieve-then-write pipeline does not?` },
  { k: 'tavily', q: `Tavily Research (~52.44 on DeepResearch Bench RACE) — how does it generate its reports? Search Tavily's blog, docs, engineering posts, any paper. What is its report-composition architecture (outline? sections? synthesis passes? self-critique? multi-agent?). What does it claim beats other deep-research agents?` },
  { k: 'leaderboard', q: `The CURRENT DeepResearch Bench RACE leaderboard (HuggingFace space muset-ai/DeepResearch-Bench-Leaderboard, and the GitHub Ayanami0730/deep_research_bench README). Get the ACTUAL ranked table: every system above 0.50, its overall score AND its four dimension scores if published. Note WHICH evaluator (legacy Gemini-2.5-Pro vs new GPT-5.5) each leaderboard uses. We need to know if 52.65 is on the same evaluator we score with (GPT-5.5).` },
  { k: 'judge', q: `How the RACE judge actually assigns points — read the scoring prompt in github.com/Ayanami0730/deep_research_bench (prompt/score_prompt_en.py, deepresearch_bench_race.py) and the DeepResearch Bench paper (arXiv 2506.11763). What EXACTLY does the judge reward on INSIGHT and COMPREHENSIVENESS? Is the score reference-RELATIVE (target/(target+reference))? What makes a report beat a human reference — i.e. what did >0.50 systems do that the human did not?` },
  { k: 'techniques', q: `Published TECHNIQUES that raise deep-research report quality on DeepResearch Bench / RACE specifically: test-time scaling, FS-Researcher (file-system agents, arXiv 2602.01566), STORM, plan-and-write, outline-then-expand, self-critique/reflection loops, multi-agent writer-critic, report-length control, structured formatting (tables/sections), citation-free synthesis. Which are EMPIRICALLY shown to raise RACE, with numbers? Which raise INSIGHT specifically? Cite the ablations.` },
  { k: 'formatting', q: `Evidence on whether DOCUMENT FORMATTING affects LLM-judge report scores: tables, headings/subsections, bullet lists, paragraph length, topic sentences, executive summaries. Is there measured evidence (ablation, paper, blog with numbers) that structure alone raises an LLM judge's rating of a report? Also: LLM-judge biases — length bias, structure bias, list bias, position bias. We need to know how much of the last 0.088 is presentation vs substance.` },
]
const swept = await parallel(ANGLES.map(a => () =>
  agent(`You are researching how the BEST deep-research agents beat the human reference on DeepResearch Bench (RACE).

${US}

YOUR ANGLE: ${a.q}

Use WebSearch and WebFetch aggressively — multiple queries, follow the links, READ the primary sources (papers, repos, docs), do not stop at a search snippet. Prefer papers/code/official docs over blog summaries. If you cannot verify something, mark it confidence=low and say so rather than guessing. We have already been burned tonight by a plausible-but-stale number (we planned against 48.88, which turned out to be a year out of date).`,
    { schema: FIND, effort: 'high', label: `sweep:${a.k}`, phase: 'Sweep' })
))
const all = swept.filter(Boolean).flatMap(s => s.findings ?? [])
log(`sweep: ${all.length} raw findings from ${swept.filter(Boolean).length}/6 angles`)

phase('Verify')
const VER = {
  type: 'object',
  required: ['verdict', 'reasoning'],
  properties: {
    verdict: { type: 'string', enum: ['CONFIRMED', 'UNSUPPORTED', 'FALSE', 'STALE'] },
    reasoning: { type: 'string' },
    corrected: { type: 'string', description: 'If STALE/FALSE, the correct fact, with a source.' },
  },
}
// dedup by claim text before paying for verification
const seen = new Set()
const uniq = all.filter(f => {
  const k = (f.claim || '').slice(0, 80).toLowerCase()
  if (seen.has(k)) return false
  seen.add(k)
  return true
})
log(`verifying ${uniq.length} unique claims (deduped from ${all.length})`)

const verified = await parallel(uniq.slice(0, 40).map(f => () =>
  agent(`Adversarially VERIFY this research claim about how a top deep-research system scores on DeepResearch Bench.

CLAIM: ${f.claim}
DETAIL: ${f.detail}
SYSTEM: ${f.system}
SOURCE GIVEN: ${f.source_url}
STATED CONFIDENCE: ${f.confidence}

Go to the source. Check it actually says this. Check it is CURRENT (the benchmark's leaderboard and evaluator both
changed in 2026 — the original paper's numbers are stale; Gemini-2.5-Pro was replaced by GPT-5.5 as the RACE judge).
Default to UNSUPPORTED if you cannot confirm it from a primary source. We would rather have five verified facts
than thirty plausible ones.`,
    { schema: VER, effort: 'high', label: `verify:${(f.claim || '').slice(0, 30)}`, phase: 'Verify' })
    .then(v => ({ ...f, verification: v }))
))
const good = verified.filter(Boolean).filter(f => f.verification?.verdict === 'CONFIRMED')
log(`verified: ${good.length} CONFIRMED of ${verified.filter(Boolean).length} checked`)

phase('Transfer')
const PLAN = {
  type: 'object',
  required: ['how_sota_wins', 'transferable', 'not_transferable', 'verdict_on_our_gap'],
  properties: {
    how_sota_wins: { type: 'string', description: 'The actual mechanism(s) by which the >0.50 systems beat the human reference. Be concrete.' },
    transferable: {
      type: 'array',
      items: {
        type: 'object',
        required: ['technique', 'evidence', 'maps_to_our_gap', 'expected_points', 'effort', 'risk'],
        properties: {
          technique: { type: 'string' },
          evidence: { type: 'string', description: 'the CONFIRMED source' },
          maps_to_our_gap: { type: 'string', description: 'which of our dimension deficits it attacks' },
          expected_points: { type: 'string' },
          effort: { type: 'string', enum: ['small', 'medium', 'large'] },
          risk: { type: 'string', description: 'incl. whether it would break our faithfulness moat' },
        },
      },
    },
    not_transferable: { type: 'array', items: { type: 'string' }, description: 'What they do that we CANNOT or SHOULD NOT copy, and why.' },
    verdict_on_our_gap: { type: 'string', description: 'Honest: does the confirmed evidence close our 0.088 gap? If not, how much of it, and what remains unexplained?' },
  },
}
const transfer = await agent(
  `Synthesise how the SOTA deep-research systems actually beat the human reference on DeepResearch Bench, and what POLARIS can steal.

${US}

CONFIRMED FINDINGS (these survived adversarial verification against primary sources):
${JSON.stringify(good.map(f => ({ system: f.system, claim: f.claim, detail: f.detail, url: f.source_url })), null, 1).slice(0, 40000)}

REJECTED / STALE (do NOT build on these):
${JSON.stringify(verified.filter(Boolean).filter(f => f.verification?.verdict !== 'CONFIRMED').map(f => ({ claim: f.claim, verdict: f.verification?.verdict, corrected: f.verification?.corrected })), null, 1).slice(0, 8000)}

OUR CURRENT PLAN (for comparison — say if the evidence says we are wrong):
  Wave1 structure (subsections, 150-word topic-sentence paragraphs, bullets) + interpretive weave
  (cross-source hedged inference sentences, deterministically barred from carrying numbers/entities/citations);
  Wave2 comparison matrix + a sectoral/industry section + naming journals in running prose.
  Projected: Wave1 -> 0.46-0.48, Wave2 -> 0.47-0.50. Neither reaches 0.5265.

Answer the question the operator actually asked: **HOW do people achieve 0.5265?**
- Name the concrete mechanism, not a vibe.
- Say which of our four dimensions each technique moves, and roughly by how much.
- Say plainly what we CANNOT copy (e.g. anything requiring us to abandon span-grounded faithfulness — that is our moat and is NOT for sale).
- Be brutally honest in verdict_on_our_gap: if the confirmed evidence does NOT explain how anyone gets from 0.44 to 0.53, SAY SO. An honest "the published record does not explain the last N points" is a far more useful answer than an invented one.`,
  { schema: PLAN, model: 'fable', effort: 'max', label: 'synthesise:how-sota-wins', phase: 'Transfer' }
)

return { confirmed_count: good.length, checked: verified.filter(Boolean).length, transfer }
