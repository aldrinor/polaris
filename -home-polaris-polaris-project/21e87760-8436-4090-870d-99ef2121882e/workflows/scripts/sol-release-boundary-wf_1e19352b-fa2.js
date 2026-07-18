export const meta = {
  name: 'sol-release-boundary',
  description: "Execute Sol's plan 3: fix the P0 module defects, wire acquisition/mining/composition, build the release-boundary publisher (filesystem permission, not a test), typed evidence acts, quarantine+rebind",
  phases: [
    { title: 'Repair', detail: 'fix the adapter defects Sol found IN the P0 modules themselves' },
    { title: 'Wire', detail: 'acquisition emits events not statuses; cards bind at construction; one card lane' },
    { title: 'Publisher', detail: 'the release boundary — composers write drafts, only the publisher writes the judged file' },
    { title: 'Attack', detail: 'the release-boundary attack: run the real submission command against a poisoned fixture' },
  ],
}

const ROOT = '/home/polaris/wt/flywheel'

const LAW = `
=== THE LAW (violating it burns the artifact regardless of score) ===
Every sentence is ATTRIBUTED (names a source -> MUST be entailed by THAT source's VERBATIM SPAN) or
OWNED (reviewer's voice -> names no source, carries no new particular, MAY be non-entailed).
THE VERBATIM SPAN IS THE ONLY EVIDENCE. The model-written \`claim\` is a display cache; nothing is ever
validated against it.

SOL: "Under the law, the currently contaminated artifact scores 0.00 regardless of its judge scalar."
Our 0.4603 IS NOT A REAL NUMBER. The artifact that earned it cites working papers as journals and a WEB
PAGE as a peer-reviewed article.

=== WHAT WE HAVE LEARNED, AT COST, TONIGHT ===
* 6 of 6 adversary attacks SUCCEED while test_gate_is_wired.py is 16/16 GREEN and NOTHING was weakened.
  "The checks certify a lane the fabrication no longer uses."
* 6,463 lines of correct, self-tested modules are DEAD CODE. The composer imports NOT ONE of them.
  provenance.py passes its own 18/18 self-test while the P0 it was built to stop is LIVE ON DISK.
* We reproduced the exact bug the canary exists to catch (validate() imported, never called) INSIDE THE
  FIX FOR IT.
* THE BUILDER CANNOT BE THE VERIFIER. Every module tonight self-tested green and was inert.
* PEER REVIEW CHANGES NUMBERS, PROVEN: Acemoglu-Restrepo robots-and-jobs is 0.37pp in NBER WP 23285 and
  0.2pp in the published JPE. Our card #1 held 0.37 attributed to the JPE. THE SPAN IS VERBATIM AND THE
  GATE PASSED IT -- the document named is simply not the document the span came from.
`

const PLAN = `
=== SOL'S PLAN 3. THIS IS THE DESIGN. EXECUTE IT. DO NOT REDESIGN IT. ===

DECISION: Stop release. Preserve the acquired bytes, QUARANTINE every unbound derived artifact, and
rebuild the publishable cards from typed manifestations.

THE ENFORCEMENT POINT IS THE FINAL ARTIFACT WRITER -- NOT ANOTHER OPTIONAL PREFLIGHT.
A report must be IMPOSSIBLE TO PUBLISH unless every attributed sentence resolves through:

    sentence -> card -> bound span -> manifestation_id + content_hash -> permitted expression -> attribution
`

phase('Repair')

const repair = await agent(`${LAW}\n${PLAN}

YOUR TASK — Sol's "Reality checks". The two P0 modules are NOT WIRE-READY. Fix exactly these defects,
in ${ROOT}/scripts/provenance.py and ${ROOT}/scripts/event_ledger.py. Do not redesign them; their central
ideas are right.

provenance.py:
  1. bind_span() DOES NOT VALIDATE BOUNDS. It must REJECT negative, reversed, and out-of-range offsets.
  2. bind_span() returns human-readable attribution STRINGS. It must return \`expression_id\` and the
     PERMITTED TARGET EXPRESSION IDs — not \`may_name\` prose.
  3. migrate() ASSUMES EVERY CORPUS ROW IS A JOURNAL EXPRESSION. "That is not valid for a judicial
     opinion or statute." Expression kind must be derived, not assumed.
  4. Add a strict \`Graph.from_json()\`. Loading MUST validate: hash equals manifestation text; expression
     and work references exist; edge endpoints and bases exist; span-preserving ASSERTED edges meet their
     authentication requirements.
  5. Expose exactly: bind_span(manifestation_id, start, end) / resolve_attribution(manifestation_id,
     source_policy) / verify_span(binding)

event_ledger.py:
  6. derive_content_profile() REINSTATES A UNIVERSAL \`FULLTEXT_MIN = 2500\` at line ~372. DELETE IT.
     ** This is Opus's own bug reappearing INSIDE the fix for it. ** It contradicts generality AND
     provenance.profile(). Artifact type and completeness come from ONE shared registry-driven reducer.
     A judicial opinion, statute section and trial-registry record are COMPLETE AT ANY LENGTH.
  7. Ledger DOES NOT RELOAD PERSISTED JSONL, so every standalone script starts with an empty in-memory
     history. Make it durable and loadable.

Run \`python scripts/test_gate_is_wired.py\` — must stay 16/16. NEVER weaken a check to make it pass.
Report exactly what you changed and what you verified by RUNNING it.`,
  { label: 'repair the P0 modules', phase: 'Repair' })

phase('Wire')

const wire = await parallel([
  () => agent(`${LAW}\n${PLAN}

The P0 modules were just repaired: ${String(repair).slice(0, 900)}

YOUR TASK — SOL'S (a)(1) and (a)(2): ACQUISITION EMITS OBSERVATIONS AND MANIFESTATIONS, NEVER STATUSES.
These are Sol's exact call sites. Wire them.

  scripts/journal_corpus_fetch.py  get_json() / get_text()
  scripts/deep_fetch.py            jget() / fetch_text()
  scripts/wp_fetch.py              polite_get()
  scripts/version_align.py         polite() / fetch_doc()

The run orchestrator creates ONE DURABLE LEDGER before retrieval. Exact event sequence per requested work:
  1. ROUTE_PLANNED           in each fetcher's main(), before its adapter loop
  2. BACKEND_ATTEMPTED       immediately before each network request
  3. at the exception boundary, EXACTLY ONE of: RESPONSE_RECEIVED | THROTTLED | BLOCKED
  4. CANDIDATE_IDENTIFIED    when a URL/result is returned
  5. MANIFESTATION_FETCHED   after bytes are obtained — locator, immutable blob id, byte hash,
                             requested identity, adapter observations
  6. CONTENT_PROFILE_DERIVED only from the shared artifact-profile reducer

** A 429 THEREFORE PERSISTS AS THROTTLED -> BACKEND_FAILED. IT CANNOT BECOME CITATION_ONLY. **
(Tonight a forced 429 on Autor/Levy/Murnane — whose free copy provably exists — wrote CITATION_ONLY,
which is the MINER'S EXCLUSION LABEL. A transient throttle PERMANENTLY DELETED a paper from the evidence
base. A fact about our request rate, written to disk as a fact about the world.)

DELETE these conclusions from fetcher writes — \`content_status\`, \`fulltext_source\`, "still paywalled":
    deep_fetch.py:127-137 | wp_fetch.py:211-224 | journal_corpus_fetch.py:103-110
They currently write those conclusions DIRECTLY. A component may not conclude; it may only observe.

merge_corpus.py must MERGE EVENT STREAMS AND IMMUTABLE MANIFESTATIONS. It must STOP choosing a winner by
text length and claimed status (lines 47-54).

Then build the PROVENANCE CONSTRUCTION reducer (Sol's a.2): after every acquisition batch, ONE reducer
builds/extends the typed graph — Work / Expression / Manifestation / evidenced edges.

Canary must stay 16/16. Report what you wired, with the call sites, and what you ran to verify it.`,
    { label: 'wire acquisition', phase: 'Wire' }),

  () => agent(`${LAW}\n${PLAN}

The P0 modules were just repaired: ${String(repair).slice(0, 900)}

YOUR TASK — SOL'S (a)(3), (a)(4) and (c): BIND AT CARD CONSTRUCTION, AND TYPED EVIDENCE ACTS.

--- (a)(3) MINING: bind at card construction, not afterward ---
The critical call site is \`evidence_miner.gate_card()\` (~line 1060), IMMEDIATELY AFTER s_start/s_end
round-trip successfully.

REPLACE the copied row attribution at evidence_miner.py:1195-1196 with:
    1. binding = graph.bind_span(paper.manifestation_id, s_start, s_end)
    2. target  = graph.resolve_attribution(manifestation_id, contract.source_policy)
    3. REJECT and COUNT \`source_policy_inadmissible\` if no target exists
    4. STORE: work_id/evidence_unit_id, expression_id, attribution_target_expression_id,
              manifestation_id, content_hash, span_start, span_end, span, attribution

Every \`corroborating_sources\` entry in consolidate() (~1400) MUST carry the same complete binding.
evidence_miner.mine() (~1575) MUST select manifestations FROM THE GRAPH. It must NOT trust the flat
\`content_status != CITATION_ONLY\` predicate at line 1580.

--- (c) TYPED EVIDENCE ACTS — replace "numbers first" ---
Opus pushed quantitative-first extraction to chase D1. Sol: "D1 has weight 0.014. Even moving it from
5.90 to 10.00 can add only about +0.0057 scalar." To chase a criterion that cannot move the score, the
extractor now silently discards EVERY SOURCE WITHOUT A DIGIT — judicial opinions, doctrinal holdings, all
qualitative evidence. A judicial opinion produced ZERO cards AND THE DISCARD WAS NOT EVEN COUNTED.

DO NOT DELETE the quantitative extractor. Make it ONE evidence-act schema among several:
    quantitative_estimate | qualitative_empirical_result | doctrinal_holding_or_rule |
    recommendation_or_guidance | null_or_inconclusive_result | methodological_limitation |
    forecast_or_projection
Names and required fields live in a VERSIONED DATA REGISTRY (a data edit, never a code edit).
Extraction generically: examine every evidence-bearing block -> propose typed acts -> locate and store
the COMPLETE SOURCE SLICE -> apply the schema's required-field rules -> RECORD EVERY REJECTION AND EVERY
BLOCK YIELDING NO ACT.

Sol's correction to the adversary: harvest() is not the only path the LLM sees — mine_paper() (~1472)
sends every positive-weight chunk. But the outcome is still fatal because MINE_PROMPT (~1254) REQUESTS
QUANTITATIVE TUPLES and gate_card() REJECTS qualitative material lacking an \`outcome\`. The no-digit
harvester also makes telemetry FALSELY REPORT ZERO CANDIDATES. Fix all three.
D1 MUST NOT FALL: the quantitative schema, full-document scan, numeric gates and evidence table all
remain intact. Qualitative acts are ADDITIVE and cannot displace quantitative acts through a fixed cap.

--- (a)(4) COVERAGE: evidence-unit families, not DOIs ---
research_contract.coverage_matrix() (~751) must consume BOTH the graph and the ledger.
REPLACE \`Cell.n_works = len(dois)\` (line ~719) with DISTINCT INDEPENDENT EVIDENCE-UNIT FAMILIES:
    scientific/clinical -> distinct STUDIES/TRIALS, not reports or DOIs
    legal               -> distinct DECISIONS; duplicate reporters of one decision count ONCE, while
                           appellate and lower-court opinions remain SEPARATE related authorities
For Acemoglu-Restrepo: the working paper and the JPE article are TWO EXPRESSIONS OF ONE STUDY. The
journal article of record is the task-72 evidence. ** 0.37 versus 0.2 IS A VERSION CHANGE, NOT
CROSS-STUDY CONFLICT OR CORROBORATION. ** Never interpret differing versions as literature disagreement.

Only derive_coverage_status() may license an absence sentence:
    SEARCHED_NONE -> a scoped absence MAY be stated
    THIN / CONFLICTED -> "the literature does not settle this"
    UNROUTED / UNSEARCHED / SEARCH_FAILED -> A PIPELINE LIMITATION. NEVER LITERATURE ABSENCE.

--- the wage matcher (generically, NOT a task-72 regex) ---
build_matchers() DROPS a stem shared by >=2 term families, so the dimension 'Wages' cannot match the word
'wage'. Sol: do NOT add 'wage' to a regex. Shared stems produce an AMBIGUOUS CANDIDATE SET; they are not
discarded. Contract definitions + span context perform a SEMANTIC second-stage assignment. Unresolved ->
AMBIGUOUS/UNROUTED, NEVER GAP. Coverage cannot close or declare absence while relevant cards remain
unrouted.

Canary 16/16. Report what you changed, with line numbers, and what you RAN to verify.`,
    { label: 'wire mining + evidence acts', phase: 'Wire' }),
])

phase('Publisher')

const pub = await agent(`${LAW}\n${PLAN}

Wired so far:
${wire.filter(Boolean).map((r, i) => `--- ${i + 1} ---\n${String(r).slice(0, 1000)}`).join('\n\n')}

YOUR TASK — SOL'S (a)(5) and (d): THE RELEASE BOUNDARY. This is the heart of his plan.

--- (a)(5) ONE CARD LANE AND ONE PUBLISHER ---
There are TWO DISCONNECTED CARD LANES today:
    the new miner writes  evidence_cards_v2.json   (evidence_miner.py:80)
    the composer reads    evidence_cards.json      (cellcog_composer.py:53)
REMOVE THAT SEAM. The composer accepts ONE explicit card-bundle path plus its graph and ledger hashes.

BEFORE ANY LLM CALL, write_report() must REVERIFY every primary and corroborating binding. Then:
  * _fmt_cards() REFUSES unbound cards
  * _gate_attributed() FIRST calls graph.verify_span(binding) and verifies the chosen attribution target
  * _evidence_table() rechecks bindings too
  * ATTRIBUTION IS RENDERED PROGRAMMATICALLY from the selected expression. THE MODEL DOES NOT INVENT OR
    COPY IT.
  * generated output is structured as ATTRIBUTED(card_ids, body) or OWNED(premise_ids, body).
    ** DO NOT INFER VOICE OR SOURCE IDENTITY FROM SURNAMES, as _cited_cards() currently does. **
  * ALL abstract, methods, table and conclusion sentences pass through the SAME typed report AST. The
    hand-written abstract at write_report() (~709) CANNOT BYPASS THE LAW.

--- THE PUBLISHER (this is the answer to "what test cannot be routed around") ---
Sol: "COMPOSERS MAY WRITE ONLY DRAFTS. ONLY THE PUBLISHER PROCESS HAS FILESYSTEM PERMISSION TO CREATE
FILES IN THE JUDGED RELEASE DIRECTORY."

  * cellcog_composer.py's \`report.md\` write_text (~775) MOVES INTO A SOLE PUBLISHER.
  * The publisher writes ATOMICALLY, and ONLY AFTER validating the ENTIRE report AST.
  * It emits a SENTENCE-HASH-TO-BINDING SIDECAR alongside the released file.
  * A report is IMPOSSIBLE TO PUBLISH unless every attributed sentence resolves through:
        sentence -> card -> bound span -> manifestation_id + content_hash -> permitted expression -> attribution
  * Enforce the boundary with actual FILESYSTEM PERMISSIONS on the release directory — not a convention,
    not a check a future agent can forget. A test can be bypassed. A PROCESS THAT LACKS WRITE PERMISSION
    CANNOT.

--- (d) QUARANTINE, DO NOT PURGE ---
"Purging destroys the audit trail. Re-attributing everything is unsafe."
  1. FREEZE AND HASH the present corpus, cards, report, graph and logs as CONTAMINATED LEGACY artifacts.
  2. QUARANTINE the current released report and ALL old evidence_cards.json cards — they lack sufficient
     binding information.
  3. For each v2 card attempt a UNIQUE REBIND using DOI/work candidate, source_version, raw offsets,
     exact span. If EXACTLY ONE manifestation matches, call bind_span().
  4. Apply the question's SOURCE POLICY:
        journal manifestation      -> retain, reattribute FROM THE GRAPH
        working paper / preprint   -> DISCOVERY LEAD; EXCLUDED from task 72
        landing page / wrong work  -> QUARANTINE
        unresolved version         -> QUARANTINE until identity is proven
  5. Rebind corroborating sources INDEPENDENTLY.
  6. Collapse expressions into EVIDENCE-UNIT FAMILIES before consolidation and coverage.

SPECIFIC OUTCOMES SOL REQUIRES — verify each actually happens:
  * Frey & Osborne's ORA LANDING PAGE is quarantined. ITS FOUR CARDS DO NOT SURVIVE.
  * The six journal-labelled working-paper manifestations LOSE journal attribution.
  * The Acemoglu-Restrepo 0.37 card is EXCLUDED from the journal-only answer.
  * Existing bytes are RETAINED for discovery and audit — nothing is deleted.
  * A 429 leaves the work SEARCH_FAILED and ELIGIBLE FOR RETRY, never a permanent exclusion.

Canary 16/16. Report the quarantine manifest honestly — I expect the corpus to SHRINK. Say by how much.`,
  { label: 'the publisher + quarantine', phase: 'Publisher' })

phase('Attack')

const attack = await agent(`${LAW}

The release boundary and quarantine were just built:
${String(pub).slice(0, 2200)}

YOU ARE THE ADVERSARY. Build and run SOL'S RELEASE-BOUNDARY ATTACK — his (b). This is the only test he
believes cannot certify the wrong lane, and it is the one thing standing between us and shipping a
fabrication.

"The test must attack THE PRODUCTION RELEASE BOUNDARY, not import a gate or inspect an AST."

Create an end-to-end release test that LAUNCHES THE REAL PRODUCTION COMMAND in a sealed temporary run
directory. THE ATTACK MUST RUN THE SAME SUBMISSION COMMAND USED FOR SCORING — not a helper, not an
import, not a reimplementation.

THE POISONED FIXTURE must contain:
  * working-paper bytes under journal metadata          (the P0)
  * a landing page carrying genuine article phrases     (Frey & Osborne is REAL — its bytes are the
                                                         Oxford ORA web page, and 4 cards cited it as a
                                                         journal article)
  * a correct journal manifestation                     (the positive control)
  * a card with NO manifestation_id
  * a card with the WRONG hash
  * a card with a valid hash but IMPERMISSIBLE journal attribution
  * an OWNED sentence carrying a new particular
  * a valid positive control

ASSERTIONS (all must hold):
  1. Missing ID, wrong hash, invalid target, or contaminated manifestation causes NONZERO EXIT and
     ** NO RELEASED report.md **
  2. The working-paper span CANNOT appear under the journal attribution.
  3. The correct journal span DOES reach the released artifact.
  4. EVERY attributed sentence in the RELEASED FILE has a sidecar binding that INDEPENDENTLY RE-VERIFIES
     against the immutable manifestation store.
  5. REOPENING THE RELEASED FILE — not an intermediate variable — shows the attack text ABSENT.
     (Tonight the composer's stats were computed on a CORRECTED string while the DISK KEPT THE BROKEN
      ONE. Never trust an in-memory value again.)
  6. The report CANNOT be released without coverage derivations for every claimed gap.

Then verify the STRUCTURAL boundary itself:
  * Can a composer process write to the judged release directory? IT MUST NOT BE ABLE TO.
  * Is the permission real, or merely a convention a future agent can ignore? PROVE IT by trying.

Finally run \`python scripts/test_gate_is_wired.py\` (must be 16/16) and re-run the SIX ORIGINAL ATTACKS
(429->no-copy, abstract->fulltext, predecessor->journal, duplicate->independent, lexical-miss->gap,
legal-source-rejected). ALL SIX SUCCEEDED LAST TIME while the canary was green.

Report ONLY what you actually executed. Quote real output. If an attack SUCCEEDS, say exactly how, with
the failing input. A finding that we are still broken is worth more than a clean report — we have shipped
a green canary over live fabrication FOUR TIMES tonight.`,
  { label: 'release-boundary attack', phase: 'Attack' })

return { repair: String(repair).slice(0, 500), wired: wire.filter(Boolean).length, publisher: String(pub).slice(0, 700), attack }
