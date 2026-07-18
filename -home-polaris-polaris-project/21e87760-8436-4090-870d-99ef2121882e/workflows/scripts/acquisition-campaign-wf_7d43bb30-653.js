export const meta = {
  name: 'acquisition-campaign',
  description: "Max-effort source acquisition for task 72 — every route, date-lane, citation-graph and gap query — admit only genuinely on-topic, journal-attributable bytes. Get from 10 works toward SOTA richness, honestly.",
  phases: [
    { title: 'Expand', detail: '4 scouts, each a different discovery modality — citation-graph, OA routes, 2023-25 frontier, empty-cell industry search' },
    { title: 'Fetch', detail: 'pull every candidate through acquisition.Acquirer — all OA locations, polite, honest outcome codes' },
    { title: 'Admit', detail: 'bind via provenance, gate on-topic + journal-attributable, honest census of what we actually gained' },
  ],
}

const ROOT = '/home/polaris/wt/flywheel'

const LAW = `
=== THE LAW (violating it burns the artifact regardless of score) ===
A source may enter the corpus ONLY bound to real bytes through provenance.py: manifestation_id +
content_hash, and for task 72's JOURNAL-ONLY policy it must be journal-attributable (a working paper is a
DISCOVERY LEAD, not journal evidence — peer review changes numbers; Acemoglu's robot effect was 0.37pp in
the NBER WP and 0.2pp in the JPE). Every fetch goes through acquisition.Acquirer, which emits observations,
never statuses. A 429 is THROTTLED -> BACKEND_FAILED, NEVER "no evidence exists".

=== THE TWO GUARDRAILS — WE HAVE HURT OURSELVES ON BOTH BEFORE ===
1. MAX THE SEARCH, NOT THE COUNT. Sol: the objective is NOT "100 papers" or "202 numbers" — it is ENOUGH
   INDEPENDENT, INTERPRETABLE EVIDENCE to close the question's cells and create high-value CONTRASTS.
   bodhi scores 0.5441 with ONE venue mention. So: cast the widest possible net, but ADMIT ONLY genuinely
   on-topic journal articles. A keyword net once dragged in ResNet, SMOTE, skin-cancer classification and
   the European Heart Journal ('work' is a substring of 'network'). Semantic on-topic gate, WORD BOUNDARIES.
2. GENERALITY. Run the CONTRACT-DRIVEN pipeline (research_contract -> source_router), NOT a hardcoded
   task-72 regex. We are running it ON task 72; we are not baking task 72 into the code.

=== DO NOT COLLIDE ===
Two other wheels are live (composer wiring, generality). Write ONLY to outputs/acquisition_campaign/.
Do NOT touch cellcog_composer.py, outputs/journal_corpus_content.json, or outputs/evidence_cards_bound.json.
acquisition.py's ledger is append-only union — safe to share.
`

const SEED = `
=== WHERE WE ARE ===
10 admissible journal works (the honest post-quarantine corpus). cellcog #1 has ~98 sources; bodhi #2 ~33.
This is a FLOOR, not SOTA. The seed works, with DOIs to expand from:
  Acemoglu 2019 JEP | Goos 2014 AER | Damioli 2021 Eurasian Bus Rev | Schwabe 2020 PLOS ONE |
  Tolan 2021 J.AI Research | Cao 2021 Technovation | Braganza 2021 J.Bus.Research | Raj 2019 J.Org.Design |
  Ayling 2022 AI&Ethics | Chalmers 2021 Entrep.Theory&Practice

EMPTY COVERAGE CELLS (the outline promises sections we cannot support): healthcare, manufacturing, retail,
finance, education, agriculture, transport. And our corpus ENDS IN 2023 — the entire generative-AI turn
(2023-2025) is missing, and the judge rewards current evidence.

TOOLS ON DISK (read them, use them, do not rebuild): source_router.py (+ config/source_routes.yaml),
recency.py, gap_search.py, insight_value.py, weighting.py, journal_corpus_build.py (has citation-graph
expansion that once took us 22->70 papers), deep_fetch.py, wp_fetch.py, acquisition.py, provenance.py,
research_contract.py.
`

phase('Expand')

// 4 discovery modalities, each BLIND to the others — the multi-modal sweep. Discover candidates only; do
// not fetch yet. Each returns {doi, title, venue, year, why_relevant, cell_served}.
const scouts = await parallel([
  () => agent(`${LAW}\n${SEED}

MODALITY 1 — CITATION-GRAPH EXPANSION. The most important paper in this field (Autor-Levy-Murnane, 4,743
cites) has neither "AI" nor "labor market" in its title — keyword search misses it, the citation graph
finds it. Use OpenAlex referenced_works + cited_by (via acquisition.Acquirer / the pattern in
journal_corpus_build.py) to expand OUTWARD from the 10 seed DOIs: their references AND the papers that cite
them. TWO HOPS where budget allows. Keep only JOURNAL ARTICLES that are genuinely about AI/automation/
technology AND work/employment/wages/skills/tasks/productivity/industry-restructuring (semantic judgement,
word boundaries — NOT 'work' in 'network'). For each candidate return doi/title/venue/year/why_relevant/
which coverage cell it serves. Aim WIDE — hundreds of candidates is fine, admission happens later. Do NOT
fetch full text yet. Return the candidate list (deduped by DOI) + counts by cell.`,
    { label: 'scout: citation-graph', phase: 'Expand' }),

  () => agent(`${LAW}\n${SEED}

MODALITY 2 — OA-ROUTE DISCOVERY FOR THE EMPTY CELLS. Use source_router.py + config/source_routes.yaml to
route AI-and-work queries for EACH empty industry cell (healthcare, manufacturing, retail, finance,
education, agriculture, transport) to the right OA sources (DOAJ, OpenAlex, CORE, Europe PMC, Crossref).
This is where we are thinnest and where two criteria regressed (Industry Scope, Various Industries). Query
each cell specifically — "AI automation employment healthcare", "industrial robots manufacturing jobs",
"algorithmic management retail warehouse workers", "AI finance banking employment", etc. Keep only journal
articles genuinely on-topic (semantic gate, word boundaries). Return doi/title/venue/year/why_relevant/
cell_served, deduped, counts by cell. Do NOT fetch full text yet. If a cell genuinely has little journal
literature, SAY SO — an honest thin cell is a real finding.`,
    { label: 'scout: OA industry cells', phase: 'Expand' }),

  () => agent(`${LAW}\n${SEED}

MODALITY 3 — THE 2023-2025 FRONTIER. Our corpus ends in 2023; the generative-AI turn is missing and the
judge rewards current evidence. Use recency.py's frontier lane: search publication/online dates in
overlapping bands (since 2023, last 24 months, last 12 months, online-ahead-of-print) via Crossref's DATE
filters + OpenAlex, SORTED BY DATE not citations (recent papers have no citations yet — that is the whole
point). Target: generative AI / LLMs / ChatGPT and work, employment, wages, tasks, productivity, occupations,
skill demand. Keep only journal articles (or clearly-labelled journal versions), genuinely on-topic. Return
doi/title/venue/year/why_relevant/cell_served, deduped, counts by year. Do NOT fetch full text yet. Report
how much 2023-2025 journal literature is actually reachable.`,
    { label: 'scout: 2023-25 frontier', phase: 'Expand' }),

  () => agent(`${LAW}\n${SEED}

MODALITY 4 — THE CANON + THE CONTRASTS. A SOTA review needs the field's landmark journal papers AND
deliberate CONTRASTS (papers that DISAGREE, different methods, null results) — that is what critical
synthesis is built from. Find, by title/author, the canonical AI-and-labor JOURNAL articles a top review
would cite: Acemoglu & Restrepo "Robots and Jobs" (JOURNAL version, JEP/AER — NOT the NBER WP), Autor's
published work, Frey & Osborne's PUBLISHED journal article (Technological Forecasting & Social Change — the
JOURNAL, not the ORA landing page), Brynjolfsson, Bresnahan (QJE published), Webb, Felten, plus recent
null/counter findings on AI employment effects. Also actively seek papers that CONTRADICT the seed set
(different unit of analysis, opposite direction). Return doi/title/venue/year/why_relevant/what_it_contrasts_
with, deduped. Do NOT fetch. Flag any that exist only as working papers (discovery leads, not task-72
admissible).`,
    { label: 'scout: canon + contrasts', phase: 'Expand' }),
])

const candidates = scouts.filter(Boolean)
log(`Discovery complete: ${candidates.length}/4 modalities returned candidates`)

phase('Fetch')

// Fetch is one agent (shared network budget, must be polite — we got 429'd all night). It de-dupes the
// union of all 4 scout lists and pulls full text through acquisition.Acquirer.
const fetched = await agent(`${LAW}\n${SEED}

Four discovery scouts just returned candidate journal articles (deduped union below). FETCH THEM.
${candidates.map((r, i) => `--- modality ${i + 1} ---\n${String(r).slice(0, 1100)}`).join('\n\n')}

YOUR TASK:
 1. Build the DEDUPED UNION of all candidate DOIs across the four scouts (by DOI, and by title where DOI
    is missing). Report the union size.
 2. For each candidate, fetch full text through acquisition.Acquirer + deep_fetch.fetch_text — try EVERY
    OA location (OpenAlex locations, Unpaywall, publisher OA, PMC/Europe PMC, DOAJ). BE POLITE: >=1.1s
    spacing, exponential backoff on 429 (we hammered these APIs all night and got IP-throttled — do NOT
    repeat that). Record every attempt on the ledger with its honest outcome: FETCHED | NOT_FOUND |
    ACCESS_DENIED | THROTTLED | LANDING_PAGE | ABSTRACT_ONLY | WRONG_WORK.
 3. Write recovered manifestations to outputs/acquisition_campaign/ — NOT the main corpus. Content-address
    the bytes (provenance.record_manifestation). Do NOT clobber anything.
 4. This may be large. If the union is huge, prioritise by weighting.py (field-normalized quality) and the
    empty cells first, and LOG what you deprioritised — no silent truncation.

Report: union size, FETCHED count, and the honest outcome histogram (how many paywalled vs throttled vs
landing-page). A THROTTLED is retriable, NOT an absence — keep those distinct.`,
  { label: 'fetch all candidates', phase: 'Fetch' })

phase('Admit')

const census = await agent(`${LAW}\n${SEED}

The fetch phase reported:
${String(fetched).slice(0, 2000)}

YOUR TASK — THE HONEST ADMISSION CENSUS. For everything fetched into outputs/acquisition_campaign/:
 1. Build/extend the provenance graph over the new manifestations. Derive each one's artifact_kind and
    completeness FROM THE BYTES (a judicial opinion is complete at 105 words; a cookie banner is not a
    paper at 100,000). A landing page is NOT a journal article — Frey & Osborne's ORA page fooled us once.
 2. For each, decide admissibility under the JOURNAL-ONLY policy: is it a bound, complete, journal-
    attributable manifestation, genuinely on-topic? Working papers/preprints -> DISCOVERY LEAD (not
    task-72 admissible). Landing pages / wrong-work / abstract-only -> QUARANTINE.
 3. Produce the census:
      - NEW admissible journal works added (the number that matters) — 10 -> ?
      - which empty coverage cells now have >=2 independent works (healthcare, manufacturing, retail,
        finance, education, agriculture, transport)
      - how many 2023-2025 frontier works admitted
      - genuine CONTRASTS gained (papers that disagree with the seed set)
      - honestly unreachable: paywalled-no-OA count, and throttled-retriable count (NOT the same thing)
 4. Do NOT merge into the shipping corpus yet — that is a scored decision for the A6 arm. Just report what
    a merge WOULD add, with every source's binding.

Be brutal and honest. If max-effort search still only yields, say, 25 admissible works, SAY SO — that tells
us the ceiling is access, not effort, and that is a real finding. If it yields 60+, say that too. Return the
full census.`,
  { label: 'admission census', phase: 'Admit' })

return { scouts: candidates.length, fetched: String(fetched).slice(0, 800), census }
