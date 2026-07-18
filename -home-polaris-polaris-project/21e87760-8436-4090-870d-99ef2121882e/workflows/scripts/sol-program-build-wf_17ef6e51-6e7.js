export const meta = {
  name: 'sol-program-build',
  description: "Build Sol's integrated program: query compiler, full-document evidence miner, argument planner, fact-use ledger, then wire + verify",
  phases: [
    { title: 'Foundations', detail: 'research contract compiler + full-document evidence miner + argument planner + fact-use ledger (new files, no conflicts)' },
    { title: 'Wire', detail: 'integrate into the composer, add implications generator + restricted cohesion pass (serialized — one writer)' },
    { title: 'Verify', detail: 'adversarial faithfulness attacks + canary must stay green' },
  ],
}

const ROOT = '/home/polaris/wt/flywheel'

const LAW = `
=== THE LAW. VIOLATING IT BURNS THE ARTIFACT REGARDLESS OF SCORE. ===

Every sentence is either ATTRIBUTED or OWNED.
  ATTRIBUTED names a source -> MUST be ENTAILED by THAT source's VERBATIM SPAN.
  OWNED is the reviewer's voice -> names NO source, carries NO new particular (no number, no new
  entity), and is EXPLICITLY ALLOWED to be non-entailed, because that is what INSIGHT IS.
Fabrication = an ATTRIBUTED sentence its source does not entail.
Insight     = an OWNED sentence its premises do not entail.
Same logical shape. Distinguished by WHOSE VOICE, not by entailment.

WE JUST CLOSED AN EVIDENCE-LAUNDERING PATH. Read it and never re-open it:
  The gate validated sentences against \`span + claim\`. But \`claim\` is WRITTEN BY THE MODEL (the
  extract prompt says "state the finding IN YOUR WORDS"), and the writer was handed ONLY the claim,
  never the span. So: model writes claim -> writer writes from claim -> gate checks writing against
  claim. THE GATE VALIDATED THE MODEL AGAINST ITSELF. A hallucinated figure was found IN THE
  HALLUCINATION and shipped under a real citation.

  RULE: THE VERBATIM SPAN IS THE ONLY EVIDENCE. \`claim\` is a display cache, derived AFTER
  verification, and NOTHING is ever validated against it. Ever.

HARD CONSTRAINTS:
  * ${ROOT}/scripts/test_gate_is_wired.py MUST pass 16/16 when you are done. Run it. If you break it,
    fix it. Do NOT weaken a check to make it pass -- that is the exact failure that let fabrication ship.
  * Never widen a gate to admit prose. If good prose is being deleted, the fix is to make the CARDS
    carry the evidence, not to lower the bar.
  * Attributed clauses, once admitted, are IMMUTABLE byte-for-byte. No later pass may rewrite them.
  * GENERAL, NOT TASK-72. No hardcoded "AI and the labor market". Everything derives from a research
    contract compiled from the question. The mission is a system that beats SOTA on ANY question.
`

const CONTEXT = `
=== WHERE WE ARE (all measured, k=5 paired; judge noise SD=0.0074) ===
us 0.4603 | bodhi(#2) 0.5441 | cellcog(#1) 0.5603.  Our weighted criterion mean 6.857/10 vs cellcog ~9.4.
We just won +0.0310 BY FIXING BUGS, not by ideas.

THE DIAGNOSIS (Codex 5.6 "Sol", max reasoning, read the code line by line):
  * The composer generates 28 subsections INDEPENDENTLY in 6 threads with NO SHARED ARGUMENT STATE.
    A later cohesion pass CANNOT manufacture comparisons the planner never selected. This is the
    single highest-value defect (+0.010 to +0.016 expected).
  * The extractor sees only the first 28,000 chars = 31.9% of the full text -- mostly INTRODUCTIONS,
    exactly where generic claims live and findings do not.
  * We print 2 quantitative findings in 8,012 words. cellcog prints 202. But "reach 202" is the WRONG
    objective (count-chasing yields contextless figures). The target is INTERPRETABLE EVIDENCE TUPLES:
    effect + unit + population + design + scope + uncertainty.
  * Our corpus is thin on industries (healthcare 2, manufacturing 2, retail 0, finance 2, education 1)
    while the outline promises a 4-subsection industry section. THE OUTLINE WRITES CHEQUES THE CORPUS
    CANNOT CASH. Two criteria regressed for this (w=.0725 and w=.0375).
  * 222 card slots are drawn from only 82 cards. One finding is used 8 times; 41 exact repetitions.

PROVEN DEAD LEVERS -- DO NOT BUILD THESE:
  * document structure (677w->106w paragraphs and 0->21 H3 moved readability -0.08)
  * more length (saturates ~8,000 words; it is a FLOOR, not a lever). We are at 8,012.
  * a formal reference list (an LLM "ArticleCleaner" DELETES all reference lists and [n] markers before
    the judge reads anything -- but TABLES SURVIVE, and the judge praises cellcog's).
`

phase('Foundations')

const foundations = await parallel([
  () => agent(`${LAW}\n${CONTEXT}

YOUR TASK: build ${ROOT}/scripts/research_contract.py — THE QUERY COMPILER. This is the generality fix.

The composer is literally a task-72 machine: the extraction question, outline, title, abstract, sectors
and rubric reading are all hardcoded (cellcog_composer.py:103, :255). Every one of our 38 scored runs is
task 72. We do not know what this pipeline scores on an unseen question. The mission is a GENERAL system.

Compile ANY question into a RESEARCH CONTRACT:
    requested source constraints   (e.g. "only high-quality English-language journal articles")
    core concepts
    outcome dimensions
    industries / subpopulations
    geographies
    time horizons
    method/design diversity
    required contrasts
    output genre                   (literature review? policy brief? comparative analysis?)
    extraction facets              (derived from the question -- e.g. for task 72 one facet is the 4IR,
                                    but NOTHING about 4IR may be hardcoded)

From the contract, derive:
  - a COVERAGE MATRIX: cells = (industry/subpopulation x outcome dimension). A cell CLOSES when it has
    >=2 groundable relevant journal works, >=1 quantitative or direct qualitative result, methodological
    contrast where material -- OR an explicit, corpus-scoped EVIDENCE GAP (an honest "the literature does
    not cover this" is a legitimate close, and is worth more than filler).
  - the OUTLINE (sections/subsections), generated from the contract, not hardcoded.
  - the extraction FACETS the miner will harvest.

Use the LLM helper in cellcog_composer.py (\`llm()\`) for compilation; keep it deterministic where you can.
Read cellcog_composer.py first to match its conventions. Include a __main__ that compiles task 72's
question and PRINTS the contract + coverage matrix, so we can eyeball it. Task 72's question is in
${ROOT}/third_party/deep_research_bench/data/ (find it — do not invent it).

Return: what you built, the compiled task-72 contract, and any assumption you had to make.`,
    { label: 'research_contract.py', phase: 'Foundations' }),

  () => agent(`${LAW}\n${CONTEXT}

YOUR TASK: build ${ROOT}/scripts/evidence_miner.py — FULL-DOCUMENT EVIDENCE MINING.

Today's extractor (cellcog_composer.py:160, \`extract_cards\`) takes text[:28000] — 31.9% of the corpus,
overwhelmingly INTRODUCTIONS. That is why 1,825 quantitative findings sit in fulltext we already hold and
only 2 reached the page: WE NEVER LOOKED AT THE RESULTS SECTIONS.

Build:
 1. SECTION-AWARE CHUNKING of the full text (abstract / methods / RESULTS / tables / discussion /
    conclusion / appendix), with overlap. Results and tables are where findings live — weight them.
 2. DETERMINISTIC CANDIDATE HARVEST FIRST (no LLM): regex-find sentences carrying effect sizes,
    percentages, coefficients, elasticities, confidence intervals, sample sizes, study periods,
    comparative quantities. This is cheap, exhaustive, and cannot hallucinate.
 3. SEMANTIC EXTRACTION over those candidates + every chunk, producing a card with a COMPLETE ESTIMATE
    TUPLE — reject orphan numbers:
        span (VERBATIM, whole, with byte offsets into the source), effect, unit, denominator/comparator,
        population/sample, geography, period, technology, industry, outcome, unit_of_analysis,
        method/design, uncertainty/significance, facet_tags[], source_version
 4. HARD GATE: the span must appear VERBATIM AND WHOLE in the source (not a 60-char prefix — that was a
    real bug: a span could open with 60 real chars and continue into invention). Store the offsets.
    Every figure in the tuple MUST appear in the span, as its OWN number (a substring test leaks:
    "0.2" in "10.25" is True in Python).
 5. \`claim\` is a DISPLAY CACHE derived AFTER verification. Nothing is ever validated against it.
 6. CONSOLIDATE duplicate cards BY FINDING, not by paper — and KEEP all corroborating sources (a finding
    replicated in 3 papers is stronger, not redundant).
 7. Accept the FACETS from research_contract.py (another agent is building it — import defensively /
    accept a facets list argument; do not block on it).

Do NOT chase a count. cellcog's "202 numbers" includes years and sample sizes. The objective is
interpretable evidence: effect + unit + population + design + scope.

Include a __main__ that mines ${ROOT}/outputs/journal_corpus_content.json and reports: cards produced,
% carrying a complete tuple, % of source text actually examined (must be ~100%, not 31.9%), and the
number of verifiable quantitative findings. Do not overwrite outputs/evidence_cards.json — write
outputs/evidence_cards_v2.json.

Return: what you built and the mining stats.`,
    { label: 'evidence_miner.py', phase: 'Foundations' }),

  () => agent(`${LAW}\n${CONTEXT}

YOUR TASK: build ${ROOT}/scripts/argument_planner.py — THE HIGHEST-VALUE FIX ON THE BOARD (+0.010-0.016).

THE DEFECT: all 28 subsections are generated INDEPENDENTLY, in 6 threads, with NO SHARED ARGUMENT STATE
(cellcog_composer.py, \`write_report\`). Nobody ever decides WHAT IS BEING COMPARED WITH WHAT. So the
report lists findings instead of adjudicating them, our Critical Synthesis section came out at 210 words
of 8,012 (2.6% of the report for 8% of the score), and it scores 6.36 on the JOINT-HEAVIEST criterion
(w=0.0800). A later cohesion pass CANNOT fix this: it cannot manufacture a comparison the planner never
selected.

Build a DOCUMENT-LEVEL planner that runs BEFORE any prose is written:

 1. COMPARISON BUNDLES. Key cards by:
        technology x outcome x industry x unit_of_analysis x method x horizon x geography x direction
    Find the bundles that MATTER: same outcome + different unit (the classic "they only look
    contradictory" case); same unit + opposite direction (genuine conflict); same finding + different
    method (robustness); a finding with NO counterpart (a boundary).
 2. Assign each subsection a PLAN:
        - a claim-first thesis
        - >=2 ATTRIBUTED evidence clauses (each bound to a card_id — NOT to a surname; binding by
          surname is ambiguous when one author has several papers)
        - THE EXACT COMPARISON being made
        - whether the estimates are methodologically COMPARABLE, and if not, why
        - an OWNED verdict (the reviewer's voice; may be non-entailed; carries NO new particular)
        - a boundary / what the evidence does NOT settle
        - a bridge to the next subsection (analytical movement: level, method, horizon, sector —
          never "Turning now to...")
 3. Emit a structured SENTENCE IR the writer must fill, so voice is carried STRUCTURALLY rather than
    guessed from prose later:
        { voice: "attributed"|"owned", text, source_clauses:[{card_id, clause_text}], premise_card_ids:[] }
 4. THE TRAP TO AVOID: a wrong method/horizon tag manufactures a FALSE RECONCILIATION ("these agree
    because they measure different units" — when they don't). Those fields must come from the card's
    verified metadata, never inferred. If the tags are missing, the bundle is NOT a comparison; say so.
 5. An OWNED verdict may NEVER silently inherit a source attribution.

Include a __main__ that plans over ${ROOT}/outputs/evidence_cards.json (or evidence_cards_v2.json if it
exists) and PRINTS the comparison bundles it found, so we can see whether they are real. Read
cellcog_composer.py first (esp. _select, _clean, _gate_attributed, _gate_multi) to match conventions.

Return: what you built, and the actual comparison bundles it discovered from our real cards.`,
    { label: 'argument_planner.py', phase: 'Foundations' }),

  () => agent(`${LAW}\n${CONTEXT}

YOUR TASK: build ${ROOT}/scripts/fact_use_ledger.py — RHETORICAL reuse accounting.

MEASURED: 28 subsection jobs draw 222 card slots from only 82 cards. One finding is selected EIGHT
times. Several canonical claims recur four times verbatim. The report contains at least 41 exact
normalized repetitions — roughly 1,500-2,000 words of restatement that buy nothing.

BUT: a hard "one card, one section" rule is WRONG and Sol explicitly rejected it — it would STARVE the
theory and synthesis sections, which legitimately need to re-use canonical findings, and it contradicts
the consolidate-don't-drop architecture. The ledger governs RHETORICAL REUSE, not evidence retention.

Build:
 - stable finding_id and work_id
 - a ledger recording, per finding: primary section, analytical role, attributed uses, owned syntheses
   using it, and whether a later use ADDS a new comparison / boundary / method / implication
 - RULES: a finding is NARRATED IN FULL ONCE. A later section may use it ONLY in a NEW analytical role.
   Otherwise the writer must make an OWNED BACKWARD REFERENCE without restating the fact.
 - corroborating sources stay in the basket; consolidation never deletes evidence
 - each section gets a deliberately DIFFERENT evidence bundle

Include a __main__ that runs over our real cards + the current report
(${ROOT}/outputs/cellcog_arm/report.md) and PRINTS: which findings are over-narrated, the exact repeated
sentences, and the estimated wasted words. Show the truth even if it is unflattering.

Return: what you built and the measured restatement waste.`,
    { label: 'fact_use_ledger.py', phase: 'Foundations' }),
])

log(`Foundations complete: ${foundations.filter(Boolean).length}/4 modules built`)

phase('Wire')

// SERIALIZED: one agent owns cellcog_composer.py. Parallel edits to one file are how we lose a turn.
const wired = await agent(`${LAW}\n${CONTEXT}

Four new modules were just built (read them first — they are the foundation of this task):
  ${ROOT}/scripts/research_contract.py   — the query compiler (contract -> coverage matrix -> outline -> facets)
  ${ROOT}/scripts/evidence_miner.py      — full-document, section-aware, complete-tuple evidence mining
  ${ROOT}/scripts/argument_planner.py    — comparison bundles + the sentence IR (THE highest-value fix)
  ${ROOT}/scripts/fact_use_ledger.py     — rhetorical reuse accounting

Here is what they reported:
${foundations.filter(Boolean).map((r, i) => `--- module ${i + 1} ---\n${String(r).slice(0, 1400)}`).join('\n\n')}

YOUR TASK: wire them into ${ROOT}/scripts/cellcog_composer.py, and add the two remaining passes.
YOU ARE THE ONLY AGENT TOUCHING THIS FILE. Work carefully and sequentially. Run the canary after EVERY
change: \`python scripts/test_gate_is_wired.py\` must stay 16/16.

 1. WIRE THE PLANNER. The writer must no longer freelance 28 independent subsections. It receives a PLAN
    (thesis, attributed clauses bound BY card_id, the comparison, the owned verdict, the boundary, the
    bridge) and fills the sentence IR. Voice is carried STRUCTURALLY from generation — never re-guessed
    from prose by matching surnames (that is ambiguous when one author has several papers).

 2. THE WRITER SEES THE VERBATIM SPAN (already fixed in _fmt_cards — keep it that way). Every figure it
    prints must appear in the span it can actually see.

 3. ADD A DEDICATED IMPLICATIONS / RESEARCH-AGENDA GENERATOR (runs AFTER the factual + synthesis ledger
    is complete; criterion "Value and Foresight" REGRESSED to 5.42, w=.0480, and we have no such pass).
    Three classes:
      - implications directly ATTRIBUTED to policy/organisational evidence cards
      - OWNED implications derived from established boundary conditions
      - research gaps derived from EMPTY or CONFLICTING coverage-matrix cells
    Each implication names: premises, affected actor, level, time horizon, boundary condition, evidence
    status. NO PREDICTIONS. "More longitudinal evidence is needed to distinguish temporary adoption
    effects from durable employment change" is VALID when the ledger shows only short horizons. A new
    policy prescription (UBI, robot tax, retraining) REQUIRES ITS OWN EVIDENCE CARDS — implications are
    the easiest place in the whole report to smuggle in new actors and forecasts.

 4. ADD A RESTRICTED SEQUENTIAL COHESION PASS (S2 Paragraph Cohesion = 4.90, our LOWEST criterion; the
    judge: "fragmented narrative... without adequate transitions").
    ** DO NOT let a model rewrite the report. ** ATTRIBUTED CLAUSES ARE FROZEN BYTE-FOR-BYTE.
    The pass may ONLY: add/revise OWNED topic sentences; add OWNED transitions; reorder already-admitted
    paragraph objects WITHIN their section; delete redundant OWNED sentences; repair grammar WITHOUT
    touching a factual clause.
    Give it the previous paragraph's summary, the current paragraph's role, and the next paragraph's
    role. Transitions must express ANALYTICAL MOVEMENT (level, method, horizon, sector) — never generic
    connectives. A free-form rewrite pass can silently alter numbers and swap source bindings: the
    immutability of attributed objects IS the safety boundary.

 5. The abstract and conclusion are currently HARDCODED AFTER ALL GATES (cellcog_composer.py ~:705) and
    make substantive claims that pass through NEITHER lane. Generate them LAST, from ADMITTED sentence
    objects, and run them through the same contract as everything else.

 6. Keep it GENERAL. Nothing task-72-specific in code. Drive it from the research contract.

Do NOT run a full compose (it is slow and costs money) — but DO run any cheap dry-run/unit path you can
to prove the wiring works, and DO run the canary. Report exactly what you changed, what you verified,
and anything you could not finish.`,
  { label: 'wire the composer', phase: 'Wire' })

phase('Verify')

const verdict = await agent(`${LAW}

An agent just rewired ${ROOT}/scripts/cellcog_composer.py to use a document-level argument planner, a
full-document evidence miner, a fact-use ledger, an implications generator and a restricted cohesion
pass. It reported:

${String(wired).slice(0, 3000)}

YOU ARE THE ADVERSARY. Your job is to BREAK IT, not to bless it. Assume it is broken and find out how.
We have shipped a green canary over live fabrication FOUR TIMES tonight, every time because the test
checked a case the author thought of, in the author's own phrasing.

 1. Run \`python scripts/test_gate_is_wired.py\`. It must be 16/16. If any check was WEAKENED or DELETED
    to make it pass, that is the worst possible outcome — say so loudly.

 2. Run these attacks against the ACTUAL wired pipeline, in the EXACT phrasing the writer prompt emits
    (not your own phrasing — that is the mistake that let fabrication ship four times):
      a. EVIDENCE LAUNDERING — a figure hallucinated into the model-authored \`claim\`, absent from the span
      b. SPAN-PREFIX SPOOFING — 60 real characters followed by an invented tail carrying the figure
      c. CLAIM SELF-VALIDATION — anything validated against \`claim\` instead of \`span\`
      d. SAME SURNAME, DIFFERENT PAPERS — Autor 2003 vs Autor 2019; is the binding still by surname?
      e. WRONG-PAPER MECHANISM BINDING — a real mechanism credited to a paper that never states it
      f. DECIMAL SUBSTRING LEAK — a fabricated "0.2" where the source says "10.25"
      g. MIXED-SOURCE CLAUSES — a comparative sentence whose second clause fabricates
      h. UNGATED ABSTRACT/CONCLUSION — do they still make substantive claims without passing a lane?
      i. COHESION PASS MUTATION — can it alter a number, or move a clause to a different source?

 3. Confirm the OWNED lane still permits non-entailed insight (if the fix strangled insight to achieve
    safety, that is ALSO a failure — it is what cost us 163 sentences in turn 1).

 4. Confirm nothing is task-72-hardcoded in the new modules.

Report ONLY what you actually executed and observed. Quote real output. If it is broken, say exactly how,
with the failing input. If you cannot verify something, say "I could not verify X" — do not assume.`,
  { label: 'adversary', phase: 'Verify' })

return { foundations: foundations.filter(Boolean).length, wired: String(wired).slice(0, 900), verdict }
