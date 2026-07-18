export const meta = {
  name: 'refetch-campaign',
  description: "Re-run the acquisition fetch that died at 0.3% — extend the preprint-stamp list first, fetch DETACHED (survives agent boundaries) prioritising the 2,571 offline-OA-URL candidates, then the honest census",
  phases: [
    { title: 'Harden', detail: 'extend _PREPRINT_STAMP so a working-paper header cannot pass as journal full text; canary green' },
    { title: 'Fetch', detail: 'detached resumable fetch, offline-OA-first, real budget, streaming ledger' },
    { title: 'Census', detail: 'honest admission census over everything actually fetched' },
  ],
}

const ROOT = '/home/polaris/wt/flywheel'
const CAMP = `${ROOT}/outputs/acquisition_campaign`

const LAW = `
=== THE LAW ===
A source enters the corpus ONLY bound to real bytes via provenance.py (manifestation_id + content_hash),
and for task 72's JOURNAL-ONLY policy it must be journal-attributable. A WORKING PAPER / PREPRINT is a
DISCOVERY LEAD, never journal evidence -- peer review changes numbers (Acemoglu's robot effect: 0.37pp in
the NBER WP, 0.2pp in the JPE). Every fetch goes through acquisition.Acquirer; a 429 is THROTTLED ->
BACKEND_FAILED, NEVER "no evidence". \`${ROOT}/scripts/test_gate_is_wired.py\` must stay GREEN.

WRITE ONLY under ${CAMP}/ and the shared ledger. Do NOT touch cellcog_composer.py, the main corpus, or
outputs/evidence_cards_bound.json. Another concern: do not clobber outputs/release/.
`

const CONTEXT = `
=== WHAT HAPPENED ===
The acquisition fetch worker was KILLED ~63s into a 55-min budget -- 16 units attempted of a 5,061-unit
union (0.3%). 2,571 candidates carry an OFFLINE OA URL (already discovered, zero network to resolve) and
were NEVER SPENT. So we have a census of a barely-started run, not the access ceiling. Discovery is DONE
and proved the literature is NOT thin.

Census findings you must honour:
 * CEILING IS ACCESS-CONTROL, NOT THROTTLING: zero 429s; 24x 403 (Wiley/Elsevier-JS/MDPI/OUP). So
   PRIORITISE routes that actually return OA full text: PMC / Europe PMC / DOAJ / publisher-OA-PDF /
   OpenAlex best_oa_location pdf_url. DE-PRIORITISE Wiley/Elsevier-direct/MDPI-direct (they 403).
 * THE P0 TRIED TO CRAWL BACK: the reducer scored a GLO Discussion Paper and an arXiv preprint AS
   JOURNAL FULL TEXT. _PREPRINT_STAMP (event_ledger.py:381) knows nber|iza|arxiv|"this version:" but NOT
   "GLO Discussion Paper", "Discussion Paper No.", "Working Paper", "SSRN", "RePEc", "MPRA", "Munich
   Personal RePEc", "Documento de Trabajo", "Cahier de recherche", etc. FIX THIS FIRST.

Candidate lists on disk (${CAMP}/): frontier_2023_2025_FINAL.json, oa_cell_discovery.json,
canon_and_contrasts_leads.json, citation-graph output, _known_dois.json, campaign_ledger.jsonl,
census_probe.py. Tools: acquisition.py, deep_fetch.py, provenance.py, event_ledger.py, weighting.py.
`

phase('Harden')

const harden = await agent(`${LAW}\n${CONTEXT}

YOUR TASK: extend the preprint/working-paper header detector so a working paper CANNOT pass as journal
full text. The census caught the reducer scoring a GLO Discussion Paper and an arXiv preprint as journal
FULLTEXT -- the exact P0 failure, crawling back through a gap in the stamp list.

 1. In event_ledger.py (~:381, \`_PREPRINT_STAMP\`), extend the pattern to recognise, case-insensitively,
    at least: "GLO Discussion Paper", "Discussion Paper No", "Working Paper", "SSRN", "RePEc", "MPRA",
    "Munich Personal RePEc", "IZA DP", "NBER Working Paper", "CEPR Discussion Paper", "Documento de
    Trabajo", "Cahier de recherche", "econstor", "preprint", "This version:", "arXiv:". Header/first-page
    scan. If a stamp is present -> the manifestation is a PREPRINT/WORKING-PAPER expression, NOT
    journal_version, so it is a DISCOVERY LEAD under journal-only policy.
 2. This must be DATA-DRIVEN where possible (a list/registry), not a wall of hardcoded ifs -- adding a new
    repository stamp should be a data edit.
 3. Add/extend a canary or self-test proving: a GLO Discussion Paper header and an arXiv-stamped header are
    classified preprint (NOT journal full text), and a genuine journal header still passes. Then run
    \`python scripts/test_gate_is_wired.py\` (must stay green).

Report exactly what you changed (file:line), the stamps you added, and the test output. Do NOT commit.`,
  { label: 'harden preprint stamp', phase: 'Harden' })

phase('Fetch')

const fetch = await agent(`${LAW}\n${CONTEXT}

The preprint stamp was just hardened: ${String(harden).slice(0, 700)}

YOUR TASK: RE-RUN THE FETCH THAT DIED -- and make it SURVIVE this time.

WHY IT DIED: the previous fetch ran inside an agent turn and was killed silently at 63s with no traceback,
no budget_stopped. So DO NOT run the fetch synchronously inside your own tool call. Instead:

 1. Build (or reuse) a RESUMABLE batch fetcher script under ${CAMP}/ that:
    - loads the deduped candidate union from the scout JSONs (frontier_FINAL, oa_cell_discovery,
      canon_and_contrasts, citation-graph)
    - PRIORITISES the 2,571 candidates that ALREADY carry an offline OA URL (best_oa_location.pdf_url /
      an OA pdf field) -- these cost near-zero to resolve and are the highest yield
    - within those, orders by weighting.py quality and by EMPTY CELL (manufacturing/retail/finance/
      education/agriculture/transport are where we are thin) and by 2023-2025 recency
    - fetches through acquisition.Acquirer + deep_fetch.fetch_text, POLITELY (>=1.1s spacing, backoff)
    - PREFERS OA routes that return full text (PMC/EuropePMC/DOAJ/OA-pdf); skips or deprioritises the
      403-walls (Wiley/Elsevier-direct/MDPI-direct) after one failure -- do not waste the budget on walls
    - CHECKPOINTS each outcome to the ledger immediately (resumable: on restart, skip units already in the
      ledger by DOI+route)
    - records honest outcomes: FETCHED | NOT_FOUND | ACCESS_DENIED(403) | THROTTLED(429) | LANDING_PAGE |
      ABSTRACT_ONLY | WRONG_WORK | PREPRINT_STAMPED
 2. LAUNCH IT DETACHED so it outlives your turn:
      setsid nohup python ${CAMP}/refetch.py > ${CAMP}/refetch.log 2>&1 &
    Give it a real budget (aim for the full offline-OA set, target ~60+ min of runtime; it checkpoints so
    it is safe to run long).
 3. Confirm it is alive and WRITING to the ledger (tail the log, show the ledger growing past the old 16),
    then RETURN -- do not block your turn waiting for it to finish. The main session will monitor the
    ledger and run the census when it plateaus.

Report: the priority list size, the offline-OA subset size, the launch command, proof it is running and
the ledger is growing, and the streaming outcome histogram so far. Do NOT commit.`,
  { label: 'launch detached fetch', phase: 'Fetch' })

return { harden: String(harden).slice(0, 600), fetch }
