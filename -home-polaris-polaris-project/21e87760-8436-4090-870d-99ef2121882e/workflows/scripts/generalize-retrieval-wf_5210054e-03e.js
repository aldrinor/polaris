export const meta = {
  name: 'generalize-retrieval',
  description: 'Make fetch/select/weight general: contract-driven retrieval plan, declarative source router, coverage-driven selection, field-normalized weighting, and a generality gate on unrelated questions',
  phases: [
    { title: 'Generalize', detail: 'retrieval planner + source router + coverage-driven selection + field-normalized weighting' },
    { title: 'Prove', detail: 'run the whole pipeline on unrelated questions — the generality gate' },
  ],
}

const ROOT = '/home/polaris/wt/flywheel'

const LAW = `
=== THE LAW (violating it burns the artifact regardless of score) ===
Every sentence is ATTRIBUTED (names a source -> MUST be entailed by THAT source's VERBATIM SPAN) or
OWNED (reviewer's voice -> names no source, carries no new particular, MAY be non-entailed — that is
what insight IS). The VERBATIM SPAN is the only evidence. The model-written \`claim\` is a display
cache and NOTHING is ever validated against it. \`${ROOT}/scripts/test_gate_is_wired.py\` must stay
16/16 — never weaken a check to make it pass.
`

const GAP = `
=== THE GAP THE OPERATOR FOUND ===
The mission is "a research system that beats SOTA on ANY question, not a machine that answers task 72."
We have been building the machine. The retrieval layer is NOT general, and here is the proof from our
own code:

1. THE SEED IS A HARDCODED TASK-72 REGEX (scripts/journal_corpus_build.py):
       TOPIC_WORK = re.compile(r'(labor|labour|employment|job|occupation|wage|skill|task|...)')
   Ask this system about drug trials or contract law and IT RETRIEVES NOTHING. That regex IS the task.

2. SELECTION IS LEXICAL WORD-OVERLAP (cellcog_composer.py _select):
       want = {w for w in re.findall(r'[a-z]{4,}', sub.lower())}; score = len(want & have)
   Same family as the bug that let ResNet and skin-cancer classification into an AI-and-labour corpus
   ('work' is a substring of 'network'). It has no idea what is MISSING from the corpus.

3. WEIGHTING IS RAW CITATION COUNT, and the file's own comment confesses the flaw:
       "Crossref sorted by citations: returns ResNet and SMOTE — famous, not relevant."
   Raw citations are NOT comparable across fields. 4,743 citations makes Autor the most important paper
   in labour economics; the same number in machine learning is unremarkable. Field-blind weighting picks
   the wrong papers the moment the question changes.

4. wp_fetch.py's CODE is general (search S2/OpenAlex/arXiv by DOI and title), but THE STRATEGY WAS
   HAND-REASONED BY A HUMAN: "in economics the working paper is the paper — look at NBER." That insight
   recovered Autor/Levy/Murnane (21,029 words, 1,085 quantitative claims) after we had called it
   "still paywalled" all night. It is ALSO exactly the kind of hand-tuning that does not transfer: for
   medicine the answer is PubMed Central/medRxiv, for law SSRN, for physics arXiv.

5. research_contract.py compiles a question into a contract + coverage matrix + outline, and mentions
   retrieval 26 times — but NOTHING WIRES IT TO THE FETCHERS. The plan stops at the outline.

ALL 38 of our scored runs are task 72. We do not know what this pipeline scores on an unseen question.
`

phase('Generalize')

const built = await parallel([
  () => agent(`${LAW}\n${GAP}

YOUR TASK: build ${ROOT}/scripts/retrieval_plan.py — CONTRACT-DRIVEN RETRIEVAL + A DECLARATIVE SOURCE ROUTER.

Read ${ROOT}/scripts/research_contract.py FIRST (it compiles question -> contract -> coverage matrix ->
outline -> facets; it is 1,500 lines and already has retrieval-adjacent fields). Read scripts/wp_fetch.py,
scripts/deep_fetch.py and scripts/journal_corpus_build.py to see what retrieval we actually have.

Build:

 1. RETRIEVAL PLAN, derived from the contract (NOT hand-written):
      - concepts and their synonyms/expansions (generated, not a regex you author)
      - source constraints THE QUESTION ACTUALLY STATED (journal-only? preprints admissible? news?
        patents? primary sources?) — these come from the contract, which span-gates them against the
        question's own words
      - disciplines / fields implicated
      - recency window, geography, method requirements
      - the coverage cells that must be filled (from the coverage matrix)

 2. A DECLARATIVE SOURCE ROUTER — a data table, not code branches:
        discipline -> [repositories, in priority order]
        economics/finance   -> NBER, IZA, RePEc/EconPapers, SSRN, OpenAlex
        CS / ML / AI        -> arXiv, OpenAlex, S2
        biomedicine/clinical-> PubMed Central, medRxiv, Europe PMC
        law / policy        -> SSRN, government/IGO repositories
        physics / maths     -> arXiv
        social science      -> SSRN, OSF, OpenAlex
        DEFAULT             -> OpenAlex + Unpaywall + Crossref + S2
    Each entry declares HOW to query it and how to get full text. Adding a field must be a DATA edit,
    never a code edit. Include an honest \`coverage_note\` per repository (e.g. "no working-paper
    culture in management journals — expect paywalls", which is what we actually measured tonight:
    the hit rate fell from 50% among NBER economists to ~19% in management/IS journals).

 3. QUERY GENERATION from the contract's concepts + coverage cells — NOT a hardcoded topic regex.
    Generate queries that target the EMPTY CELLS specifically (that is what a gap-driven searcher does).

 4. AN ON-TOPIC GATE THAT IS DERIVED, NOT AUTHORED. The current one is
    \`TOPIC_WORK = re.compile(r'(labor|labour|employment|...)')\` — a hand-written task-72 regex whose
    trailing word-boundary bug once made "automat" fail to match "automation", so it REJECTED Frey &
    Osborne and Acemoglu-Restrepo as off-topic. Derive relevance from the contract's concepts, and use
    WORD BOUNDARIES correctly — 'work' must not match 'network' (that exact bug put ResNet in our corpus).

 5. RECURSIVE/GAP-DRIVEN RETRIEVAL: keep searching until coverage cells close OR are declared honest,
    corpus-scoped EVIDENCE GAPS. An honest "the literature does not cover this" is a legitimate close
    and is worth more than filler — the judge marked us DOWN 0.84 for a sectoral section written from
    2 healthcare papers.

Include a __main__ that plans retrieval for THREE questions and PRINTS the plans side by side:
   (a) task 72 (AI and the labor market)
   (b) "What does the evidence say about SGLT2 inhibitors in heart failure with preserved ejection
       fraction?"   [clinical — must route to PubMed/Europe PMC, not NBER]
   (c) "How do common-law and civil-law jurisdictions differ in enforcing non-compete clauses?"
       [legal — must route to SSRN, not arXiv]
If the router sends the clinical question to NBER, IT IS BROKEN and you must say so.

Return: what you built, and the three retrieval plans it produced.`,
    { label: 'retrieval_plan.py', phase: 'Generalize' }),

  () => agent(`${LAW}\n${GAP}

YOUR TASK: build ${ROOT}/scripts/select_and_weight.py — COVERAGE-DRIVEN SELECTION and FIELD-NORMALIZED WEIGHTING.
These are two of the three things the operator identified as overfit. Replace them properly.

--- A. SELECTION (today: lexical word-overlap in cellcog_composer.py \`_select\`) ---
Today's selector scores a card by counting words shared with the subsection title. It is blind to
MEANING and blind to what is MISSING. Measured consequences: 222 card slots drawn from 82 cards, one
finding selected EIGHT times, 41 exact repetitions — while whole coverage cells stayed empty.

Build selection that:
  - CLOSES COVERAGE CELLS. The coverage matrix (research_contract.py) already knows which cells are
    empty. Selection should maximise cell closure, not word overlap. A card that fills an empty cell is
    worth more than a fifth card in a full one.
  - scores SEMANTIC relevance to the contract's concepts (embeddings or an LLM relevance call — but
    keep a deterministic fallback; do not make the pipeline unrunnable if the model is unavailable)
  - prefers cards carrying a COMPLETE ESTIMATE TUPLE (effect + unit + population + design + scope) over
    a bare assertion — the judge scores us 5.90 vs cellcog's 9.20 on "clarity of data/evidence" and
    wrote: "citations are named but findings are missing"
  - enforces the contract's SOURCE CONSTRAINTS before composition (e.g. journal-only)
  - respects the fact-use ledger (scripts/fact_use_ledger.py) so a finding is narrated once and re-used
    only in a NEW analytical role
  - honours WORD BOUNDARIES. 'work' must never match 'network'. That exact bug put ResNet and
    skin-cancer classification into an AI-and-labour corpus.

--- B. WEIGHTING (today: raw citation count) ---
Raw citations are not comparable across fields, and our own code comments admit it: "Crossref sorted by
citations returns ResNet and SMOTE — famous, not relevant." 4,743 citations makes Autor/Levy/Murnane the
most important paper in labour economics; the same count in machine learning is unremarkable.

Build weighting that is:
  - FIELD-NORMALIZED: citation percentile WITHIN the paper's own field and publication-year cohort, not
    a raw count. (OpenAlex exposes concepts/fields and per-field counts; derive the percentile. If the
    data is unavailable, say so and degrade honestly rather than silently falling back to raw counts.)
  - AGE-ADJUSTED: a 2003 paper with 4,743 citations and a 2023 paper with 50 may BOTH be top-decile in
    their cohort. Citations accrue over time; not adjusting for that systematically buries recent work —
    and the operator's own instruction was that recency matters.
  - EVIDENCE-QUALITY-AWARE: does the paper actually carry effect sizes, or only prose?
  - VENUE-QUALITY relative to the FIELD (a top law review is not a top medical journal, and neither is
    comparable to NeurIPS).
  - and it must EXPLAIN ITSELF: emit, per paper, WHY it ranked where it did. A weight nobody can audit
    is a weight nobody should trust.

Include a __main__ that runs over ${ROOT}/outputs/journal_corpus_content.json and PRINTS the top 15 papers
by the OLD weighting (raw citations) beside the NEW weighting (field-normalized), so the difference is
visible. Show the truth even if the new ranking is unflattering or barely differs — if it barely differs,
SAY SO, and say why.

Return: what you built, and the old-vs-new ranking table.`,
    { label: 'select_and_weight.py', phase: 'Generalize' }),
])

log(`Generalization modules: ${built.filter(Boolean).length}/2 built`)

phase('Prove')

const gate = await agent(`${LAW}

Two modules were just built to generalize retrieval, selection and weighting:
  ${ROOT}/scripts/retrieval_plan.py     — contract -> retrieval plan -> declarative source router
  ${ROOT}/scripts/select_and_weight.py  — coverage-driven selection + field-normalized weighting

They reported:
${built.filter(Boolean).map((r, i) => `--- module ${i + 1} ---\n${String(r).slice(0, 1500)}`).join('\n\n')}

YOU ARE THE GENERALITY GATE. Sol called this mission-critical and it has never been run: ALL 38 of our
scored runs are task 72. "General system" is currently an UNSUPPORTED CLAIM and your job is to test it,
not to defend it.

RUN THE ACTUAL PIPELINE (not a description of it) on these questions and REPORT WHAT HAPPENS:
  1. task 72 — "the restructuring impact of AI on the labor market"     [our home turf; the control]
  2. clinical  — "What does the evidence say about SGLT2 inhibitors in heart failure with preserved
                  ejection fraction?"
  3. legal     — "How do common-law and civil-law jurisdictions differ in enforcing non-compete clauses?"
  4. thin      — "What is known about the long-term health effects of microplastic inhalation in
                  occupational settings?"   [deliberately thin evidence — the honest answer may be
                  'the literature does not settle this', and SAYING SO is a PASS, not a failure]

For EACH, report concretely:
  - does compile_contract() produce a sane contract, or does it emit AI/labour-market concepts?
  - does the source router send it to the RIGHT repositories? (clinical -> PubMed/Europe PMC;
    legal -> SSRN; NOT NBER. If a clinical question routes to NBER, THE ROUTER IS BROKEN — say so.)
  - does the on-topic gate accept relevant papers and reject irrelevant ones, or is it still the
    hardcoded AI/labour regex?
  - does selection/weighting behave sanely, or does it surface famous-but-irrelevant papers (the
    ResNet/SMOTE failure)?
  - WHERE DOES IT BREAK? Name the file and line.

Then answer, plainly: IS THIS A GENERAL RESEARCH SYSTEM, OR STILL A TASK-72 MACHINE?

Be brutal. We would rather know it is overfit than believe it is general. Report ONLY what you actually
ran and observed — quote real output. If you could not run something, say "I could not run X" rather than
assuming. Do NOT do a full expensive compose; contract + retrieval plan + selection dry-runs are enough
to answer the question.`,
  { label: 'generality gate', phase: 'Prove' })

return { built: built.filter(Boolean).length, verdict: gate }
