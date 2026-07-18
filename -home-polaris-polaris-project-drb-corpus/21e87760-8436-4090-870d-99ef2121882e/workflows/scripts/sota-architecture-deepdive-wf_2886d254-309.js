export const meta = {
  name: 'sota-architecture-deepdive',
  description: 'Fetch the missing top-6 artifacts and reverse-engineer the architecture of every system above us on the GPT-5.5 board',
  phases: [
    { title: 'Acquire', detail: 'fetch the missing top-6 submission artifacts from HuggingFace/GitHub' },
    { title: 'Dissect', detail: 'one deep agent per system: architecture, design, published record' },
    { title: 'Verify', detail: 'adversarially check every architecture claim against a primary source' },
  ],
}

const CORPUS = '/home/polaris/polaris_project/drb_corpus'
const BOARD = `THE LEADERBOARD ON OUR EVALUATOR (GPT-5.5) — this is the ONLY board that matters to us:
  cellcog-max 55.78 | WhaleCloud-DocChain_0612 54.78 | bodhi 54.07 | lunon 53.51 | dalpha-deepresearch 53.10
  sourcery 51.17 | gemini-2.5-pro-deepresearch 49.98 (== the "reference", so parity = 0.50) | openai-deepresearch 47.84
  POLARIS (us) 43.82 | perplexity-Research 43.05 | grok-deeper-search 41.22
NOTE: the widely-cited "ADORE 52.65" is on NEITHER board — treat it as unverified. The legacy Gemini-2.5-Pro
board (qianfan 58.03, ZTE 57.27, ...) is a DIFFERENT evaluator and its numbers are NOT comparable to ours.
We already hold 100-task artifacts for: cellcog, tavily, onyx, deepinsight, baidu-qianfan (in ${CORPUS}).`

const ACQ = {
  type: 'object',
  required: ['fetched', 'notes'],
  properties: {
    fetched: { type: 'array', items: { type: 'object', properties: { system: { type: 'string' }, path: { type: 'string' }, tasks: { type: 'number' }, source_url: { type: 'string' } } } },
    notes: { type: 'string', description: 'What could NOT be fetched and why. Be explicit — a missing artifact is a finding.' },
  },
}

phase('Acquire')
const acquire = await agent(
  `Acquire the DeepResearch Bench submission ARTIFACTS (the generated reports, raw_data jsonl) for the systems we
are missing. We have cellcog, tavily, onyx, deepinsight, baidu-qianfan. We are MISSING the other top-6 on our board:
**WhaleCloud-DocChain_0612, bodhi, lunon_full100_FINAL.submission, dalpha-deepresearch, sourcery** — and also
**openai-deepresearch** and **gemini-2.5-pro-deepresearch** (the reference), which we want as calibration points.

${BOARD}

WHERE TO LOOK: the benchmark's HuggingFace org/dataset (muset-ai / DeepResearch-Bench, the leaderboard Space's
backing dataset repo — leaderboard Spaces usually store submissions in a dataset repo), the GitHub repo
github.com/Ayanami0730/deep_research_bench (data/test_data/raw_data/), and any HF dataset mirrors. Use huggingface_hub
/ curl / git clone as needed. Save each as ${CORPUS}/<system>.jsonl.

Verify each file: 100 lines, each with a 'prompt' and an 'article'/'content'. Report line counts.
If a submission is NOT publicly downloadable, say so plainly — do NOT fabricate a path. A confirmed absence is
a real finding (it means we can only reverse-engineer that system from its published score, not its text).`,
  { schema: ACQ, effort: 'high', label: 'acquire:top6-artifacts', phase: 'Acquire' }
)
log(`acquired ${acquire?.fetched?.length ?? 0} new artifact sets — ${acquire?.notes?.slice(0, 160)}`)

const ARCH = {
  type: 'object',
  required: ['system', 'has_paper', 'architecture', 'composition_method', 'evidence', 'what_we_can_steal'],
  properties: {
    system: { type: 'string' },
    has_paper: { type: 'boolean' },
    architecture: { type: 'string', description: 'End-to-end: planning, retrieval, memory, outline, composition, revision. Concrete.' },
    composition_method: { type: 'string', description: 'THE KEY QUESTION: how is the REPORT WRITTEN? one pass or many? section-scoped or global context? outline-first? revision loops? critic? How is synthesis produced?' },
    performance: { type: 'string', description: 'Its scores per dimension on OUR (GPT-5.5) board; how it differs from the pack.' },
    evidence: { type: 'string', description: 'URLs / file:line of artifacts measured. NO claim without a source.' },
    unknowns: { type: 'array', items: { type: 'string' }, description: 'What is genuinely NOT public. Say so rather than speculate.' },
    what_we_can_steal: { type: 'array', items: { type: 'string' } },
  },
}

phase('Dissect')
const SYSTEMS = [
  { k: 'cellcog', s: 'cellcog-max (55.78, RANK 1 on our judge)' },
  { k: 'whalecloud', s: 'WhaleCloud-DocChain_0612 (54.78, rank 2)' },
  { k: 'bodhi', s: 'bodhi (54.07, rank 3)' },
  { k: 'lunon', s: 'lunon (53.51, rank 4)' },
  { k: 'dalpha', s: 'dalpha-deepresearch (53.10, rank 5)' },
  { k: 'sourcery', s: 'sourcery (51.17, rank 6)' },
  { k: 'openai_gemini', s: 'openai-deepresearch (47.84) AND gemini-2.5-pro-deepresearch (49.98, the reference) — the two systems we can most directly calibrate against' },
]
const dissected = await parallel(SYSTEMS.map(x => () =>
  agent(`Reverse-engineer the ARCHITECTURE of: **${x.s}**

${BOARD}

DO BOTH of these:
1. THE PUBLISHED RECORD. Search hard: arXiv, GitHub, company blog, HF model/dataset card, tech report, WeChat/Zhihu
   posts (several of these are Chinese teams — search Chinese-language sources too: 深度研究, 智能体, 报告生成).
   Is there a paper? Code? A tech report? If there is genuinely NOTHING public, SAY SO — do not invent an architecture.
2. THE ARTIFACT. If we have its reports in ${CORPUS} (or the Acquire phase just fetched them), READ THEM and measure
   them across MANY tasks, not just task 72. Reverse-engineer the generation process from the text: section/subsection
   structure, paragraph length distribution, whether it uses bullets/tables (and whether that varies BY TASK GENRE),
   how it cites, whether it names studies in prose, how it handles conflicting evidence, whether it has a dedicated
   synthesis/tensions section, whether the writing looks single-pass or multi-step, whether there is evidence of a
   revision/critique pass.

THE QUESTION THAT MATTERS MOST: **how does it COMPOSE the report, and how does it produce SYNTHESIS?**
We are an extraction-grounded fact conveyor — we span-verify every sentence, which forbids cross-source inference.
We score insight 0.4238 (weight 0.32, our worst). Find out what these systems do INSTEAD.

Prefer primary sources. Mark anything unverified. We were burned tonight by a confidently-quoted stale number.`,
    { schema: ARCH, effort: 'high', label: `dissect:${x.k}`, phase: 'Dissect' })
))
const D = dissected.filter(Boolean)
log(`dissected ${D.length}/7 | with papers: ${D.filter(d => d.has_paper).length}`)

phase('Verify')
const V = {
  type: 'object', required: ['verdict', 'reasoning'],
  properties: {
    verdict: { type: 'string', enum: ['CONFIRMED', 'PARTIAL', 'UNSUPPORTED', 'FALSE'] },
    reasoning: { type: 'string' },
    corrected: { type: 'string' },
  },
}
const checked = await parallel(D.map(d => () =>
  agent(`Adversarially verify this reverse-engineered architecture claim. Default to UNSUPPORTED if you cannot
confirm it from a PRIMARY source (paper, repo, official doc) or from the artifact text itself.

SYSTEM: ${d.system}
HAS PAPER: ${d.has_paper}
ARCHITECTURE CLAIMED: ${d.architecture}
COMPOSITION METHOD CLAIMED: ${d.composition_method}
EVIDENCE CITED: ${d.evidence}

Check: does the cited source actually say this? Is it current (2026)? Is an "architecture" being inferred from
output text and then stated as fact? Inference from artifacts is LEGITIMATE but must be LABELLED as inference,
not presented as documented design. Flag any place that line is crossed.`,
    { schema: V, effort: 'high', label: `verify:${d.system?.slice(0, 20)}`, phase: 'Verify' })
    .then(v => ({ system: d.system, verdict: v.verdict, reasoning: v.reasoning, corrected: v.corrected, dissection: d }))
))
const C = checked.filter(Boolean)
log(`verified: ${C.filter(c => c.verdict === 'CONFIRMED').length} confirmed, ${C.filter(c => c.verdict === 'UNSUPPORTED' || c.verdict === 'FALSE').length} rejected`)

return { acquire, systems: C }
