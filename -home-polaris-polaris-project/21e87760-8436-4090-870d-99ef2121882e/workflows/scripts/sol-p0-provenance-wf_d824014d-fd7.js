export const meta = {
  name: 'sol-p0-provenance',
  description: "Execute Sol's P0: typed manifestation graph so no span can be attributed to a source that does not contain it; content-derived artifact profiles; event-derived labels; adversarial canaries",
  phases: [
    { title: 'P0 Provenance', detail: 'typed work/version/manifestation graph + content-derived artifact profile + event-derived labels' },
    { title: 'Align', detail: 'attempt journal/accepted-manuscript version alignment for the recovered working papers' },
    { title: 'Attack', detail: "Sol's six canary attacks — every one must be rejected" },
  ],
}

const ROOT = '/home/polaris/wt/flywheel'

const LAW = `
=== THE LAW (violating it burns the artifact regardless of score) ===
Every sentence is ATTRIBUTED (names a source -> MUST be entailed by THAT source's VERBATIM SPAN) or
OWNED (reviewer's voice -> names no source, carries no new particular, MAY be non-entailed — that is
what insight IS). THE VERBATIM SPAN IS THE ONLY EVIDENCE. The model-written \`claim\` is a display
cache and NOTHING is ever validated against it.

A 0.60 obtained by fabricating is a 0.00. The artifact is burned regardless of score.

\`${ROOT}/scripts/test_gate_is_wired.py\` must stay 16/16. NEVER weaken a check to make it pass — that
is the exact failure that let fabrication ship four times tonight.

=== THE FAILURE SHAPE WE KEEP REPEATING ===
EVERY defect found tonight had ONE shape: A LABEL THAT ASSERTED MORE THAN ITS CONTENT SUPPORTED, WITH
NOTHING CHECKING. Not one announced itself; every one read as a fact about the world.
    "gate: WIRED"         -> it checked the wrong lane; fabrication shipped
    "span-verified"       -> verified by its FIRST 60 CHARACTERS
    "fabrication-proof"   -> the table printed model-written prose
    "still paywalled"     -> we asked by DOI; the free copy is a SEPARATE WORK
    "FULLTEXT"            -> 535 words. An abstract.
    "no free copy exists" -> we were HTTP 429. A fact about our REQUEST RATE, disguised as a fact about
                             the world.
THEREFORE: re-derive every label FROM ITS CONTENT. Never trust a claim a component makes about itself.
`

const P0 = `
=== SOL'S P0 (Codex 5.6, max reasoning). THIS IS THE DESIGN. EXECUTE IT. DO NOT REDESIGN IT. ===

WORKING-PAPER TEXT IS BEING ATTRIBUTED TO JOURNAL ARTICLES.

  scripts/wp_fetch.py     writes the NBER/SSRN working paper's text INTO THE CORPUS ROW FOR A JOURNAL DOI
  scripts/evidence_miner.py  hashes that text but RETAINS THE JOURNAL'S ATTRIBUTION METADATA

  path:  NBER working-paper span
           -> stored under journal DOI row
           -> writer names THE JOURNAL ARTICLE
           -> gate checks it against THE WORKING-PAPER SPAN

Sol: "A predecessor working paper and later journal article may be closely related, but they are
DIFFERENT SOURCES until version equivalence is proven. The recovered text is presently A DISCOVERY LEAD,
not automatically journal-attributable evidence."

Peer review CHANGES NUMBERS. And task 72 demands JOURNAL ARTICLES ONLY — so citing the working paper
BREAKS THE INSTRUCTION, and citing the journal with the working paper's text IS FABRICATION.
There is no version in which the 1,691 recovered numbers ship as they stand.

Sol on the cost, and we accept it:
  "The visible judge scalar could FALL because inadmissible working-paper findings disappear. Under the
   Law that is not a valid regression — the alternative artifact is burned."
  "As the artifact stands, THE WEAKER CORPUS WINS."

ALSO: a false label was reintroduced. Autor (2015), 544 words, is STILL labelled FULLTEXT — the running
wp_fetch process had loaded the OLD MIN_WORDS threshold at import before the fix landed. The corpus
claims 27 fulltext; the content-derived count is 24 (Frey, Tallon and Autor 2015 are all under 2,500w).
`

phase('P0 Provenance')

const p0 = await parallel([
  () => agent(`${LAW}\n${P0}

YOUR TASK — SOL'S ITEM 4, VERBATIM. Build ${ROOT}/scripts/provenance.py: a TYPED WORK / VERSION /
MANIFESTATION GRAPH. This is Sol's design; implement it, do not redesign it.

Replace the single DOI-keyed corpus row with a typed graph:

    Research object / case / trial
      ├─ report or expression
      │    ├─ journal version
      │    ├─ accepted manuscript
      │    ├─ working paper or preprint
      │    └─ repository manifestation
      └─ typed edges:
           exact_copy_of
           accepted_manuscript_of
           predecessor_of
           reports_same_study
           supersedes
           cites

THE CORE RULE (Sol, verbatim):
  "Every span binds to its exact manifestation_id and content hash. ATTRIBUTION MAY NAME ONLY THAT
   MANIFESTATION, unless a stronger edge proves that the cited source contains the same span."

  "An NBER working paper MAY lead to the journal article. It MAY be mined for discovery. It MAY NOT be
   rendered as a QJE/JEP/AER finding unless the relevant text is VERIFIED IN THE JOURNAL VERSION or an
   authenticated accepted manuscript of that version. If only the working paper is available, citing it
   VIOLATES THE JOURNAL-ONLY INSTRUCTION, so it stays OUTSIDE THE ANSWER BODY."

  "A title similarity match can PROPOSE predecessor_of; it CANNOT ASSERT exact_copy_of."

ALSO — CONTENT-DERIVED ARTIFACT PROFILES (Sol, item 4): "A universal word threshold cannot define
'full text': a short judicial opinion, statute section, trial-registry record, and journal article have
different completeness profiles." So MY MIN_WORDS=2500 IS ITSELF WRONG and must go. Derive from the bytes:
    artifact_kind, sections present, body/chrome ratio, result-bearing sections present,
    extractability, fetch outcome
A short official judicial opinion must NOT be mislabelled an abstract.

Migrate outputs/journal_corpus_content.json onto the graph WITHOUT DELETING ANY TEXT. The working-paper
bodies are retained as manifestations of type working_paper, correctly labelled, and marked
NOT-JOURNAL-ATTRIBUTABLE until an alignment edge proves otherwise.

Include a __main__ that prints, honestly: manifestations by type, how many spans are currently
journal-attributable, how many are working-paper-only (and therefore INELIGIBLE for a journal-only
answer), and the content-derived artifact profile of every recovered paper. Expect the honest count to
be WORSE than the corpus currently claims. Report it anyway.

Return: what you built and the honest provenance census.`,
    { label: 'provenance graph', phase: 'P0 Provenance' }),

  () => agent(`${LAW}\n${P0}

YOUR TASK — SOL'S ITEM 8, VERBATIM: EVENT-DERIVED LABELS. Build ${ROOT}/scripts/event_ledger.py.
This is Sol's design; implement it, do not redesign it.

Sol: "Every status is a PURE REDUCER over an append-only event ledger:
        route planned / backend attempted / response received / throttled / blocked /
        candidate identified / manifestation fetched / content profile derived /
        semantic binding decided / eligibility decided / weight components derived /
        coverage status derived
      NO COMPONENT MAY WRITE \`complete\`, \`fulltext\`, \`no evidence\`, \`same work\`, or
      \`high quality\` DIRECTLY."

This is the structural cure for the ONE failure shape that has cost us every turn tonight. A component
that can assert its own success will eventually assert it falsely, and nothing will catch it. So a
component may only EMIT EVENTS; the label is DERIVED from the events by a reducer nobody can bypass.

The distinctions that MUST be preserved and never collapsed (Sol):
    HTTP 429/503                     -> BACKEND_FAILED,  ** NOT "no evidence exists" **
                                        (we hammered S2/OpenAlex, got 429, and the code read it as
                                         "no free copy of this paper exists" — a fact about our own
                                         request rate, disguised as a fact about the world)
    route_complete                   -> means EVERY PLANNED ADAPTER HAS AN ATTEMPT RECORD.
                                        It must NEVER mean "an adapter was mapped."
    a budget stop                    -> IS NOT AN EVIDENCE GAP
    coverage cell status             -> UNSEARCHED | SEARCH_FAILED | UNROUTED | SEARCHED_NONE | THIN |
                                        SUPPORTED | CONFLICTED
                                        Only SEARCHED_NONE after adequate route completion supports a
                                        scoped absence statement. CONFLICTED and THIN directly support
                                        "the literature does not settle this" — which is a CORRECT
                                        answer, not a failure.
    "high_quality"                   -> FORBIDDEN as a bare label. It must render as its components:
                                        directness=high, method_quality=low, influence_percentile=0.92,
                                        each with provenance.

Include a __main__ that replays our REAL history through the ledger and shows what the labels SHOULD
have been: the 429s (which we recorded as "no free copy exists"), the 535-word abstract (recorded as
FULLTEXT), the working-paper span (recorded as journal evidence). Show that the reducer produces the
TRUE label where the old code produced a false one.

Return: what you built, and the replay showing each false label the reducer would have caught.`,
    { label: 'event ledger', phase: 'P0 Provenance' }),
])

log(`P0 modules: ${p0.filter(Boolean).length}/2`)

phase('Align')

const align = await agent(`${LAW}\n${P0}

The provenance graph and event ledger were just built:
${p0.filter(Boolean).map((r, i) => `--- ${i + 1} ---\n${String(r).slice(0, 1200)}`).join('\n\n')}

YOUR TASK: attempt VERSION ALIGNMENT for the recovered working papers — Sol's condition for admitting
any of that text as journal evidence.

We recovered 6 working-paper full texts (1,691 quantitative claims), including Autor/Levy/Murnane 2003
(21,029 words, 1,085 numbers — NBER WP 8337, whose published version is in the Quarterly Journal of
Economics). RIGHT NOW NONE OF IT IS ADMISSIBLE, because a span from the working paper cannot be
attributed to the journal article.

For each recovered working paper, try to establish a SPAN-LEVEL alignment edge:
  1. Is an OPEN-ACCESS JOURNAL VERSION or an AUTHENTICATED ACCEPTED MANUSCRIPT reachable? (Unpaywall,
     PMC, publisher OA, institutional repository with a version statement.) Use scripts/wp_fetch.py's
     polite_get — 1.1s spacing + exponential backoff. WE ARE THE ONES WHO GOT OURSELVES THROTTLED
     TONIGHT; do not do it again, and if you are throttled, record BACKEND_FAILED, never "no copy".
  2. If a journal version IS reachable: verify each mined span appears VERBATIM in it. Spans that verify
     become journal-attributable (edge: exact_copy_of / accepted_manuscript_of). Spans that DO NOT verify
     STAY INADMISSIBLE — peer review changes numbers, and that is exactly the risk.
  3. If NO journal version is reachable: the working paper remains a DISCOVERY LEAD ONLY. Mark it
     working-paper-only, INELIGIBLE for a journal-only answer, and SAY SO. Do not soften it.

A title match may PROPOSE predecessor_of. It may NEVER assert exact_copy_of. Only verbatim span
verification in the journal version does that.

Report honestly and concretely: for each of the 6 papers — journal version reachable? how many spans
verified? how many remain inadmissible? I expect most to remain inadmissible. THAT IS THE CORRECT
ANSWER AND YOU MUST REPORT IT AS SUCH. Do not manufacture an alignment to save the corpus.

Return: the alignment census, paper by paper.`,
  { label: 'version alignment', phase: 'Align' })

phase('Attack')

const attack = await agent(`${LAW}

Built this round: ${ROOT}/scripts/provenance.py (typed manifestation graph), ${ROOT}/scripts/event_ledger.py
(event-derived labels). Version alignment reported:
${String(align).slice(0, 2000)}

YOU ARE THE ADVERSARY. Sol named the six attacks that MUST be rejected. Run each against the ACTUAL code
and report what happens. Assume it is broken and find out how — a green canary has covered live
fabrication FOUR TIMES tonight, every time because the test checked a case the author thought of, in the
author's own phrasing.

  1. 429 RENDERED AS "NO COPY"          — force a throttle/backend failure. Does anything conclude
                                          "no free copy exists"? It must say BACKEND_FAILED.
  2. ABSTRACT RENDERED AS FULL TEXT     — feed a 535-word abstract. Does anything call it FULLTEXT?
                                          (It did tonight. Twice. And Frey & Osborne — a 548-word
                                          abstract stamped FULLTEXT — is the paper our synthesis
                                          section leaned on.)
  3. PREDECESSOR RENDERED AS JOURNAL VERSION — take an NBER working-paper span and try to get it
                                          attributed to the QJE article. THIS IS THE P0. It must be
                                          REFUSED unless a verbatim span alignment proves it.
  4. DUPLICATE REPORTS COUNTED AS INDEPENDENT STUDIES — two reports of ONE study must not close a
                                          coverage cell as if they were two independent findings.
  5. LEXICAL MISS RENDERED AS A GAP     — a relevant paper the alias list misses must NOT produce
                                          "the literature does not cover this". It must be UNROUTED or
                                          SEARCH_FAILED, which are different things.
  6. A LEGAL SOURCE REJECTED FOR LACKING NUMBERS — a doctrinal holding carries no effect size. Nothing
                                          may demand a number for it to count as evidence. (Our current
                                          extractor PRIORITISES quantitative findings — does that
                                          silently discard a legal or qualitative source?)

Then run \`python scripts/test_gate_is_wired.py\` — it must be 16/16. If any check was WEAKENED or
DELETED to make it pass, that is the WORST possible outcome and you must say so loudly.

Report ONLY what you actually executed and observed. Quote real output. If an attack SUCCEEDS, say
exactly how, with the failing input. If you could not test something, say "I could not verify X" — never
assume. A finding that we are still broken is worth more to us than a clean report.`,
  { label: 'adversary: 6 attacks', phase: 'Attack' })

return { p0: p0.filter(Boolean).length, align: String(align).slice(0, 800), attack }
