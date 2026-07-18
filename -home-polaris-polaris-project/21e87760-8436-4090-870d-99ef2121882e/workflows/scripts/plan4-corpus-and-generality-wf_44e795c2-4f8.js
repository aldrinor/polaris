export const meta = {
  name: 'plan4-corpus-and-generality',
  description: "Sol plan 4 corpus acquisition (OA routes, date-lane, gap recursion, weighting) + the first-ever generality gate harness — collision-safe with the running integrity adversary",
  phases: [
    { title: 'Acquisition', detail: 'OA-native discovery + date-lane + gap recursion + multidimensional weighting (all NEW files)' },
    { title: 'Generality', detail: 'the harness that runs the pipeline on clinical / legal / thin-evidence questions' },
  ],
}

const ROOT = '/home/polaris/wt/flywheel'

const LAW = `
=== THE LAW (violating it burns the artifact regardless of score) ===
Every sentence is ATTRIBUTED (names a source -> MUST be entailed by THAT source's VERBATIM SPAN) or
OWNED (reviewer's voice -> names no source, carries no new particular, MAY be non-entailed). THE VERBATIM
SPAN IS THE ONLY EVIDENCE; the model-written \`claim\` is a display cache and nothing is validated against it.

=== STANDING ORDERS ===
GENERALITY IS NOT OPTIONAL. Every mechanism must state its behaviour on a CLINICAL question, a LEGAL
question, and a THIN-EVIDENCE question (where "the literature does not settle this" is the CORRECT answer
and saying so is a PASS). A domain change must be a DATA edit (a new registry row), never a CODE edit.
THE TELL WE KEEP FAILING: a hand-written regex, a hardcoded topic gate, a domain insight baked into code.

=== WHAT ALREADY EXISTS — BUILD ON IT, DO NOT DUPLICATE IT ===
The integrity layer is BUILT AND WIRED (another workflow just finished it):
  acquisition.py   -- THE ONE DOOR TO THE NETWORK. It emits observations, never statuses. A 429 lands as
                      THROTTLED; the reducer derives BACKEND_FAILED; nothing can turn it into "no evidence".
                      USE Acquirer.get_json / record_manifestation. Do NOT open your own urllib path.
  provenance.py    -- Work / Expression / Manifestation / typed edges. bind_span, resolve_attribution,
                      verify_span. Spans bind to manifestation_id + content_hash, never to a DOI.
  event_ledger.py  -- pure reducers over an append-only ledger. Content completeness is per-artifact-kind
                      (a judicial opinion is complete at 105 words; a journal article is not).
  research_contract.py -- compiles a question -> contract -> coverage matrix -> outline -> facets.
                      coverage cell status: UNSEARCHED|SEARCH_FAILED|UNROUTED|SEARCHED_NONE|THIN|SUPPORTED|
                      CONFLICTED. Only SEARCHED_NONE after route completion licenses an absence statement.
  evidence_miner.py -- typed evidence acts (config/evidence_acts.json); binds at card construction.
Read these first. Everything you build plugs into them.
`

const PLAN4 = `
=== SOL PLAN 4 — THE WINNING CORPUS. THIS IS THE DESIGN. EXECUTE IT, DO NOT REDESIGN IT. ===

The corpus is TEN journal-attributable works (we claimed 32). cellcog has ~98 sources. But bodhi scores
0.5441 with ONE venue mention -- so the objective is NOT "100 papers" or "202 numbers". It is ENOUGH
INDEPENDENT, INTERPRETABLE EVIDENCE to close the question's important cells and create high-value contrasts.

Sol's forecast: SOTA-class corpus = +0.035 to +0.065; combined with synthesis architecture, 0.520-0.580.
cellcog's 0.5603 is inside that band.
`

phase('Acquisition')

const acq = await parallel([
  () => agent(`${LAW}\n${PLAN4}

YOUR TASK — Sol plan 4 item 2: OA-NATIVE DISCOVERY ROUTES + THE CAPABILITY-BASED SOURCE ROUTER.
Build ${ROOT}/scripts/source_router.py.

The strategy must change from "choose canonical paywalled works, then chase copies" (which gave a 19%
hit rate) to "OA-FIRST DISCOVERY plus version pursuit." Build a DECLARATIVE, DATA-DRIVEN router:

  config/source_routes.yaml (or .json) -- ONE ROW PER ROUTE, keyed by EVIDENCE CAPABILITY not domain:
     adapter_id | evidence_roles | document_types | jurisdiction_coverage | query_dialects |
     identifier_types | version_resolvers | rate_policy | coverage_note

  Representative rows (Sol named these): DOAJ (13M+ article records), PMC + Europe PMC (OA full-text XML),
  OpenAlex + Unpaywall (enumerate locations -- never treat their version label as final), CORE
  (institutional repositories), OpenAIRE, Zenodo/HAL, Crossref (identity/dates/relations, NOT full text),
  NBER/IZA/RePEc/SSRN/arXiv/medRxiv (separate-work + preprint discovery, admissible only when policy
  permits that expression), official legal systems (GovInfo, EUR-Lex, CourtListener).

  The router performs SET COVER over the plan's required evidence roles and invokes every matching route
  family. IT DOES NOT ask an LLM to remember that economists use NBER or clinicians use PubMed -- the
  routing is DERIVED from the contract's evidence roles against the route table.

  ALL discovery goes through acquisition.Acquirer -- so every attempt is on the ledger, and these outcomes
  stay DISTINCT: FETCHED | NOT_FOUND | ACCESS_DENIED | THROTTLED | TRANSIENT_ERROR | LANDING_PAGE |
  ABSTRACT_ONLY | WRONG_WORK | CORRUPT_EXTRACTION. Only NOT_FOUND across exhausted applicable routes
  supports "we did not locate an accessible copy." A 429 NEVER does.

Clinical: routes to PubMed/PMC/Europe PMC/ClinicalTrials.gov. Legal: GovInfo/EUR-Lex/CourtListener/SSRN,
NOT NBER. Adding a domain that existing adapters serve is ONLY NEW ROWS.

Include a __main__ that, for task 72 and for a CLINICAL question and a LEGAL question, PRINTS which routes
fire. If the clinical question routes to NBER, IT IS BROKEN and you must say so. Do NOT do a full live
crawl (slow, and rate-limits); prove the ROUTING is correct with a dry run + a handful of live probes.

Return: what you built, the route table, and the three routing dry-runs.`,
    { label: 'source_router.py', phase: 'Acquisition' }),

  () => agent(`${LAW}\n${PLAN4}

YOUR TASK — Sol plan 4 item 3: RECENCY (the operator's own insight -- "just search by date").
Build ${ROOT}/scripts/recency.py.

Sol: "'Just search by date' is correct because BACKWARD CITATION EXPANSION SYSTEMATICALLY MISSES RECENT
WORK: recent papers have not accumulated references or citations." OUR CORPUS ENDS IN 2023. The
generative-AI turn is 2023-2025 and we have NOTHING there.

Two independent lanes:
  1. FOUNDATION lane: seminal theories, landmark methods, long-run evidence. NO recency penalty for age.
  2. FRONTIER lane: explicit publication-date windows, searched directly and SORTED BY PUBLICATION/ONLINE
     DATE, never by citation count.

For task 72 the frontier lane begins at the generative-AI boundary and searches overlapping bands:
since 2023 | last 24 months | last 12 months | accepted/online-ahead-of-print | newly-indexed-since-last-run.
THE EXACT WINDOWS LIVE IN A RECENCY PROFILE, NOT CODE. Queries must use each database's CORRECT date field
-- publication vs online vs accepted vs posted vs registration vs last-updated are NOT interchangeable
(Crossref exposes them separately).

RECENCY IS CLAIM-SPECIFIC: a current adoption-rate claim needs recent evidence; a foundational theory does
not; a current statute needs effective/amendment status; a clinical conclusion needs the latest completed
trials + corrections + retractions.

Clinical: publication + trial-completion + registry-update + correction/retraction dates. Legal: current
EFFECTIVE text and subsequent treatment, not merely newest commentary. Thin-evidence: a recent search
returning nothing strengthens "no recent eligible evidence located", NOT "the field proves no effect".

Use acquisition.Acquirer for any probe. Include a __main__ that builds the frontier query bands for task 72
and for a clinical question, and PRINTS them. Return what you built + the bands.`,
    { label: 'recency.py', phase: 'Acquisition' }),

  () => agent(`${LAW}\n${PLAN4}

YOUR TASK — Sol plan 4 items 4 & 5: GAP-DRIVEN RECURSIVE SEARCH + MARGINAL-INSIGHT SCHEDULING.
Build ${ROOT}/scripts/gap_search.py and ${ROOT}/scripts/insight_value.py.

--- GAP RECURSION (item 4) ---
A coverage cell is an EVIDENCE REQUIREMENT, not a topic keyword. After each acquisition/extraction round,
classify each gap and generate a DIFFERENT query family for each:
   DISCOVERY_GAP (no candidate found) | ACCESS_GAP (candidate exists, no admissible complete manifestation)
   | EXTRACTION_GAP (text exists, no result span extracted) | DIVERSITY_GAP (evidence from one study/design/
   context) | RECENCY_GAP (no current evidence for a time-sensitive claim) | CONTRADICTION_GAP (findings
   conflict, moderators missing) | EVIDENCE_GAP (routes saturated, no eligible evidence).
Retail employment triggers OUTCOME-specific + METHOD-specific + CURRENT + cited/citing + null-result
searches -- NOT another copy of the broad query. A cell closes on evidence only with enough independent
result-bearing evidence for the requested comparison; it closes as THIN only after multiple databases +
query families + citation chasing + version pursuit + recent queries were attempted and duplicates
collapsed. THIS IS OPERATIONAL SATURATION, not a claim of exhaustive recall. A BUDGET STOP IS NOT A GAP.

--- MARGINAL INSIGHT (item 5) ---
The acquisition objective is MARGINAL INSIGHT READINESS, a VECTOR retained through composition:
   value(candidate) = new required-cell coverage + complete interpretable result tuple + independent
   corroboration + method/population/context contrast + null-or-counterevidence + current-frontier
   contribution + explains-an-existing-contradiction - same-study/version redundancy
"A FIFTH POSITIVE ESTIMATE IN THE SAME CONTEXT usually adds less insight than THE FIRST CREDIBLE NULL, a
different population, or a design that resolves a disagreement." Actively search for nulls, counterexamples,
different methods. Do NOT collapse quality into a scalar -- authority, method quality, relevance,
independence, recency, contrast value stay SEPARATE dimensions.

Clinical: cells = population x intervention x comparator x outcome x time, risk-of-bias carried explicitly.
Legal: cells = jurisdiction x issue x authority-level x period; "two sources" never substitutes for one
controlling authority. Thin-evidence: THIN closure is a SUCCESSFUL terminal state.

Use research_contract's coverage matrix + provenance's evidence-unit families. __main__: run over the
current bound cards (outputs/evidence_cards_bound.json), print each cell's gap type and the query family it
would generate, and the marginal-value ranking. Return what you built + the gap census on our real corpus.`,
    { label: 'gap_search + insight_value', phase: 'Acquisition' }),

  () => agent(`${LAW}\n${PLAN4}

YOUR TASK — Sol plan 4 item 6 (from plan 2): MULTIDIMENSIONAL WEIGHTING. Build ${ROOT}/scripts/weighting.py.

NEVER collapse quality into raw citations. Our own code comment confesses it: "Crossref sorted by
citations returns ResNet and SMOTE -- famous, not relevant." 4,743 citations makes Autor the most
important paper in labour economics; the same count in ML is unremarkable.

Carry a VECTOR, each dimension separate and each with PROVENANCE:
   explicit_eligibility | topical_relevance | evidentiary_directness | methodological_quality |
   source_authority | field_year_type_normalized_influence | independence | recency_fit |
   content_completeness | marginal_coverage_contribution

ONLY explicit source constraints, faithfulness, chrome, and confirmed off-topic status are HARD GATES.
Everything else is a WEIGHT. For scholarly influence use OpenAlex citation_normalized_percentile / FWCI
when available (OpenAlex field-normalizes by subfield); MISSING VALUES ARE 'UNKNOWN', NEVER ZERO.
Field-normalized + AGE-ADJUSTED: a 2003 paper with 4,743 cites and a 2023 paper with 50 may BOTH be
top-decile in their cohort. Do not let influence outrank methodological quality or directness.

'high_quality' is FORBIDDEN as a bare label. It must render as its components -- directness=high,
method_quality=low, influence_percentile=0.92 -- each with provenance.

Clinical: risk-of-bias, design, directness, endpoint relevance dominate; a highly-cited biased
observational paper stays biased; a recent trial is not penalized for lacking citations. Legal:
bindingness, court hierarchy, jurisdictional fit, current validity dominate; raw citations are optional
context, not authority.

Use acquisition.Acquirer for OpenAlex probes. __main__: rank our current corpus by OLD (raw citations)
beside NEW (the vector), print both side by side. If the new ranking barely differs, SAY SO and say why.
Return what you built + the old-vs-new table.`,
    { label: 'weighting.py', phase: 'Acquisition' }),
])

log(`Acquisition modules: ${acq.filter(Boolean).length}/4 built`)

phase('Generality')

const gen = await agent(`${LAW}

YOU ARE BUILDING THE FIRST GENERALITY GATE THIS SYSTEM HAS EVER HAD. All 38 scored runs are task 72.
"General system" is, until you measure it, AN UNSUPPORTED CLAIM -- exactly the kind of unverified label
that has cost us all night. Sol put this gate BEFORE task-72 scoring for that reason.

Build ${ROOT}/scripts/generality_gate.py. It runs the ACTUAL pipeline (contract -> routing -> coverage ->
extraction dry-run, NOT a full paid compose) on these questions and reports what happens:
  1. task 72   -- AI and the labour market                                  [control]
  2. clinical  -- "What does the evidence say about SGLT2 inhibitors in heart failure with preserved
                   ejection fraction?"
  3. legal     -- "How do common-law and civil-law jurisdictions differ in enforcing non-compete clauses?"
  4. thin      -- "Long-term health effects of microplastic inhalation in occupational settings"
                   [deliberately thin -- "the literature does not settle this" is a PASS, not a failure]

For EACH, measure and PRINT (Sol's metrics): does compile_contract produce a sane contract or emit
AI/labour concepts? Does the router send it to the RIGHT sources (clinical->PubMed, legal->SSRN/GovInfo,
NOT NBER)? false-gap rate; relevant-primary-work recall; route-attempt honesty (is a 429 a SEARCH_FAILED
or an "absence"?); and whether the thin-evidence conclusion is CORRECT.

Then answer plainly: IS THIS A GENERAL RESEARCH SYSTEM, OR STILL A TASK-72 MACHINE? Name the file:line
where it breaks. Be brutal -- we would rather know it is overfit than believe it is general. The seed is
STILL a hardcoded task-72 regex in journal_corpus_build.py; if that (or anything like it) forces every
question toward AI/labour, REPORT IT as the overfit point.

Report ONLY what you actually ran. Quote real output. Return the four per-question reports + the verdict.`,
  { label: 'generality gate', phase: 'Generality' })

return { acquisition: acq.filter(Boolean).length, generality: gen }
