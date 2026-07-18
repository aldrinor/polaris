export const meta = {
  name: 'fulltext-lane',
  description: "Build Sol's full-text acquisition lane: close the accepted-manuscript P0, add per-span attribution, wire PMC/EuropePMC/DOAJ/CORE/OpenAIRE/Zenodo/OAI-PMH, persistent host scheduler — then adversary, then the big fetch",
  phases: [
    { title: 'P0', detail: 'accepted_manuscript_of is NOT span-preserving; per-span attribution; route-lineage fix' },
    { title: 'Routes', detail: 'wire the 7 full-text routes + persistent cross-process host scheduler' },
    { title: 'Attack', detail: "Sol's 11 required tests, run by an adversary who did not build it" },
    { title: 'Fetch', detail: 'detached, resumable, cumulative — the real corpus' },
  ],
}

const ROOT = '/home/polaris/wt/flywheel'
const DESIGN = `${ROOT}/sota_review/foundation/SOL_FULLTEXT_LANE_V9.md`

const LAW = `
=== THE LAW ===
A source enters the corpus ONLY bound to real bytes via provenance.py (manifestation_id + content_hash).
Under a JOURNAL-ONLY contract it must be journal-attributable. A working paper / preprint / ACCEPTED
MANUSCRIPT is NOT the journal version -- peer review changes numbers (Acemoglu's robot effect: 0.37pp in
the NBER WP, 0.2pp in the published JPE). \`${ROOT}/scripts/test_gate_is_wired.py\` must stay GREEN;
NEVER weaken a check to make it pass. WE DO NOT USE SCI-HUB/LIBGEN -- only legitimate green-OA.

=== TONIGHT'S LESSON, EARNED FOUR TIMES ===
THE BUILDER CANNOT VERIFY ITSELF. Modules self-tested green while fabrication shipped; provenance.py
passed 18/18 while the P0 ran live on disk; the canary went 16/16 while 6 attacks succeeded. So: the
agent that builds does NOT verify. A separate adversary attacks.
`

const CTX = `
=== SOL'S DESIGN IS AT ${DESIGN} — READ IT FIRST. IT IS THE BUILD CONTRACT. DO NOT REDESIGN IT. ===

Why this lane: our corpus is TEN journal-attributable works. cellcog (#1) has ~98 sources. The argument
planner (the biggest score lever) found ZERO genuine cross-source conflicts in 10 papers -- it is STARVED.
Sol's yield forecast for the ~2,490 no-known-OA candidates: 450-850 complete documents, 180-360 STRICT
journal-VoR-attributable, best estimate ~260 additional strict journal full texts. The three biggest lanes
(CORE 60-140, OpenAIRE 45-110, OAI-PMH 35-90) ARE ALL UNBUILT.

Discovery is DONE: ~5,061 candidates in ${ROOT}/outputs/acquisition_campaign/ (frontier_2023_2025_FINAL,
oa_cell_discovery, canon_and_contrasts_leads, citation-graph). ~2,571 already carry an offline OA URL.
Existing tools: acquisition.py (the ONE network door), provenance.py, event_ledger.py, source_router.py +
config/source_routes.yaml, deep_fetch.py, weighting.py.
`

phase('P0')

const p0 = await agent(`${LAW}\n${CTX}

YOUR TASK — SOL'S SECTION "Decision" + §4 + the route-lineage bug. THIS IS A LIVE FABRICATION PATH. Close
it BEFORE any volume is added.

 1. \`accepted_manuscript_of\` is currently in SPAN_PRESERVING (provenance.py:216). REMOVE IT.
    version_align.py:220 maps 'acceptedVersion' to a span-preserving relationship — STOP THAT.
    alignment_census.py:140 declares accepted manuscripts journal-admissible from repository METADATA —
    STOP THAT. "An accepted manuscript is NEVER the journal version merely because a repository says
    acceptedVersion."

 2. PER-SPAN ATTRIBUTION (Sol §4). Change the API from manifestation-wide permission to binding-specific:
        resolve_attribution(binding_id, attribution_policy)
    A SpanCorrespondence must carry: source manifestation_id + raw/text hash + offsets + verbatim span;
    target manifestation_id + raw/text hash + offsets + verbatim span; canonicalization algorithm AND
    version; exact canonical-span hash; identity decisions for both manifestations.
    The verifier RECHECKS both hashes, both offsets, and exact canonical text equality.
    Consequences Sol requires: repository metadata alone can NEVER prove span equivalence; a span found
    independently in VoR bytes should be REBOUND directly to the VoR manifestation; a correspondence
    grants permission for THAT SPAN ONLY; "a disagreement such as 0.37 versus 0.2 fails immediately";
    expression-wide exact_copy_of is reserved for identity-confirmed manifestations whose ENTIRE canonical
    text is equal; an accepted manuscript with no VoR bytes stays accepted-manuscript-attributable only.

 3. ROUTE-LINEAGE BUG: source_router.py can credit an adapter with a manifestation fetched through a
    DIFFERENT adapter, because it reduces all work-level manifestations instead of its own candidate
    lineage. candidate_id must follow the whole chain: resolver request -> candidate -> content request ->
    redirects -> manifestation. Add the ResolveContext / DocumentCandidate / Manifestation records from
    Sol §1. "The adapter must not write FULLTEXT, THIS_WORK, VERSION_OF_RECORD, ADMISSIBLE, or an
    expression edge" — those are REDUCER outputs.

 4. Remove the flat-corpus write in deep_fetch.py:185 (it admits anything except CITATION_ONLY, truncates
    text at 120k chars, and discards the manifestation identity the law needs).

 5. WRONG-WORK + COMPLETENESS (Sol §5): identity from the FETCHED CONTENT (JATS article-DOI/title/
    contributors; PDF front-matter DOI/title/byline with repository COVER SHEETS SEGMENTED from article
    front matter; HTML citation meta + visible header). CONFIRMED / DIFFERENT_WORK / UNRESOLVED per his
    decision rules — and note his correction: "a generic title without an author must NOT produce
    DIFFERENT_WORK; the current event reducer is too aggressive." Completeness is artifact-specific: a
    short legal judgment is COMPLETE; a registry record needs no prose.

Run \`python scripts/test_gate_is_wired.py\` after every change (must stay green). Report file:line for
every change and what you RAN to verify. Do NOT commit.`,
  { label: 'close the P0 + per-span attribution', phase: 'P0' })

phase('Routes')

const routes = await parallel([
  () => agent(`${LAW}\n${CTX}

The P0 was just closed (per-span attribution now exists): ${String(p0).slice(0, 900)}

YOUR TASK — SOL §2, the BIOMEDICAL + OA-INDEX routes. Build ${ROOT}/scripts/routes_bio.py (or extend the
adapter registry) wiring PMC, Europe PMC, and DOAJ as FULL-TEXT routes (today they are queried for
discovery only, never for the document).

PMC: DOI/PMID -> PMCID via the PMC ID Converter (batch up to 200 ids); GetRecord from PMC OAI using
  oai:pubmedcentral.nih.gov:<numeric-pmcid> with metadataPrefix=pmc; then the PMC OA service for PDF/
  tarball links. Returns JATS full-text XML where rights permit. POLITENESS: <=3 req/s, NO concurrent
  requests, register tool+email. A PMCID does NOT guarantee downloadable OA full text.
EUROPE PMC: exact DOI search /rest/search?query=DOI:"..."&resultType=core&format=json; inspect pmcid,
  fullTextIdList, fullTextUrlList, hasPDF, OA fields; fetch JATS via /rest/{PMCID}/fullTextXML.
  ** Sol: "the currently configured /{source}/{id}/fullTextXML shape is WRONG for PMCID retrieval." **
  Start at 1 req/s, 1 in flight; obey 429/Retry-After.
DOAJ: exact article search on DOI; read bibjson.link[] entries whose type is 'fulltext'. ~2 req/s.
  A DOAJ miss means "not indexed in DOAJ", NOT "not open".

Everything goes through acquisition.Acquirer. Adapters ONLY produce DocumentCandidate records — they may
NOT write FULLTEXT/ADMISSIBLE/VERSION_OF_RECORD. Endpoints, identifier transforms, metadata prefixes and
rate budgets are DATA (config/source_routes.yaml rows), not code.
Silent failures to defend against (Sol): PMCID exists but full text is not in the OA subset; XML is front
matter only; an NIH accepted manuscript mistaken for the publisher VoR; abstract mistaken for full text.

Prove it with a handful of LIVE probes on real DOIs from our candidate lists. Canary green. Do NOT commit.`,
    { label: 'routes: PMC + EuropePMC + DOAJ', phase: 'Routes' }),

  () => agent(`${LAW}\n${CTX}

The P0 was just closed (per-span attribution now exists): ${String(p0).slice(0, 900)}

YOUR TASK — SOL §2, THE THREE BIGGEST LANES, ALL CURRENTLY UNBUILT (CORE 60-140, OpenAIRE 45-110,
Zenodo 5-20). This is where the ~260 papers come from. Build ${ROOT}/scripts/routes_repo.py.

CORE: /v3/search/works?q=doi:"..."; prefer record downloadUrl or documented output download. Treat a
  returned \`fullText\` field as a DERIVED TEXT manifestation, NOT automatically a complete PDF equivalent.
  ** The currently configured credential returns 401 — so PREFLIGHT MUST MARK THE ROUTE UNAVAILABLE
  rather than conclude content is absent. ** (401 -> AUTH_FAILED, never "no OA copy exists.") Enforce the
  authenticated tier + rate headers.
OPENAIRE GRAPH: current Graph API /graph/v3/research-products?pid=<doi>; inspect product instances, PIDs,
  access rights, licences, URLs. ** Sol: replace the LEGACY endpoint in the YAML with Graph v3. ** URLs
  remain CANDIDATES; OpenAIRE metadata is NOT document proof. Limits: 60 req/hr unauthenticated,
  7,200/hr authenticated — authenticate if possible.
ZENODO: /api/records?q=doi:"..."; also inspect pids, related identifiers, conceptdoi, version, resource
  type, and each file. Obey X-RateLimit-* headers. Artifact type must stay EXPLICIT — a dataset or
  supplement is NOT an article.

Silent failures Sol names: OCR/truncated fullText; a supplement returned as the primary file; the API tier
omits full text; repository metadata says accepted manuscript but the BYTES ARE ANOTHER WORK; a concept
DOI resolving to the wrong version; multiple files concatenated into a FICTITIOUS DOCUMENT.

Adapters produce DocumentCandidate records only. Endpoints/selectors/rate budgets are DATA rows.
Prove it with LIVE probes on real DOIs from our candidate lists. Canary green. Do NOT commit.`,
    { label: 'routes: CORE + OpenAIRE + Zenodo', phase: 'Routes' }),

  () => agent(`${LAW}\n${CTX}

The P0 was just closed: ${String(p0).slice(0, 700)}

YOUR TASK — SOL §7 (the persistent host scheduler) + §2 (targeted OAI-PMH, 35-90 yield).

A. PERSISTENT CROSS-PROCESS SCHEDULER. Replace _HOST_LAST and the single SPACING_S in acquisition.py:
   per-host TOKEN BUCKET + concurrency limit; resolver host and content host budgeted SEPARATELY (a
   redirect charges the DESTINATION host); limits enforced from source_routes.yaml; DYNAMIC LIMITS MAY
   ONLY REDUCE the configured rate; parse BOTH numeric and HTTP-date Retry-After; store \`not_before\` —
   "do not sleep and retry three seconds later when the server requests hours"; cache exact-ID resolver
   responses (ETag/Last-Modified); batch PMC identifiers; CIRCUIT-BREAK on repeated 401/403/429/5xx;
   parallelise ACROSS independent hosts, never within a host beyond its policy. Must be safe across
   MULTIPLE WORKER PROCESSES (we will run this detached and resumable).
   OUTCOME SEMANTICS, exactly: 429 -> THROTTLED (deferred) | 401 -> AUTH_FAILED | 403 -> ACCESS_DENIED
   (that URL) | timeout/5xx -> bounded retry then BACKEND_FAILED.
   ** NONE of these may EVER reduce to "no OA copy exists." ** (We got IP-throttled all night; and a 403
   is publisher access-control, not absence.)

B. TARGETED OAI-PMH. Do NOT attempt global per-work OAI harvesting. Obtain the OAI identifier + repository
   base URL through CORE / OpenAIRE / repository metadata / a local index, then GetRecord(identifier,
   metadataPrefix). Rich formats (JATS/METS/MODS/OAI-ORE) may expose document URLs; oai_dc commonly
   exposes only metadata or a LANDING PAGE. Default 1 in flight, 2s interval until the repository row says
   otherwise; obey Retry-After, robots, resumption tokens, deletion records. EACH REPOSITORY IS A DATA ROW
   (base URL, metadata prefixes, identifier mappings, file selectors, rate policy).
   Silent failures: oai_dc landing page treated as a PDF; a deleted record treated as "no evidence in the
   world"; the DOI belonging to a CITED REFERENCE; a repository COVER SHEET hiding a different article.

Canary green. Prove the scheduler holds under 2+ concurrent worker processes. Do NOT commit.`,
    { label: 'scheduler + OAI-PMH', phase: 'Routes' }),
])

phase('Attack')

const attack = await agent(`${LAW}

The full-text lane was just built. P0: ${String(p0).slice(0, 800)}
Routes: ${routes.filter(Boolean).map((r, i) => `\n--- ${i + 1} ---\n${String(r).slice(0, 700)}`).join('')}

YOU ARE THE ADVERSARY. You did not build this. Sol named ELEVEN REQUIRED TESTS — run every one against
the ACTUAL code and report real output. Assume it is broken until you cannot make it fail.

  1.  A PMC VoR JATS becomes ADMISSIBLE.
  2.  An NIH / accepted manuscript REMAINS NON-VoR (this is the P0 — it must NOT be citable as the journal).
  3.  The Parry / Yang-Hui He WRONG-WORK case is QUARANTINED (a theorem-proving arXiv paper was once filed
      under an HR journal article by title match).
  4.  The Acemoglu 0.37 / 0.2 mismatch CANNOT ALIGN (the working paper says 0.37pp, the JPE says 0.2pp —
      a SpanCorrespondence between them must FAIL).
  5.  An independently matching VoR span CAN be rebound to the VoR manifestation.
  6.  A SHORT LEGAL JUDGMENT is recognised as COMPLETE (no word floor).
  7.  A complete REGISTRY RECORD does not need article-length prose.
  8.  A 429 NEVER becomes SEARCHED_NONE.
  9.  ONE ROUTE CANNOT INHERIT ANOTHER ROUTE'S MANIFESTATION (the route-lineage bug).
  10. MULTIPLE WORKER PROCESSES stay inside the host budget.
  11. TRUNCATED or HTML-ERROR downloads CANNOT ENTER SYNTHESIS.

Then: \`python scripts/test_gate_is_wired.py\` must be GREEN, and check \`git diff\` on the verifier files —
if any check was DELETED or LOOSENED to pass, that is the WORST outcome and you must say so loudly.

Report ONLY what you executed; quote real output. If a test fails, name file:line and the failing input.
A finding that we are still broken is worth more than a clean report.`,
  { label: 'adversary: 11 required tests', phase: 'Attack' })

phase('Fetch')

const fetch = await agent(`${LAW}\n${CTX}

The lane is built and the adversary reported:
${String(attack).slice(0, 2000)}

YOUR TASK: RUN THE REAL FETCH. This is the corpus that decides whether we hit SOTA.

A previous fetch died silently at 63 SECONDS (killed inside an agent turn, 16 of 5,061 units). DO NOT
run it synchronously inside your tool call. Build a RESUMABLE batch runner and LAUNCH IT DETACHED:
    setsid nohup python <runner> > outputs/acquisition_campaign/fulltext_run.log 2>&1 &

The runner must:
 * load the ~5,061 deduped candidates from outputs/acquisition_campaign/
 * WAVE ORDER (Sol §3): (1) re-derive identity/completeness for bytes we ALREADY hold; (2) cheap exact-ID
   resolution — PMC/EuropePMC/DOAJ/Unpaywall/OpenAlex/S2 in parallel; (3) CORE, OpenAIRE, Zenodo;
   (4) targeted OAI-PMH from the OAI ids those return; (5) title+author ONLY after exact identifiers fail
   (it generates candidates, it CANNOT establish identity).
 * FETCH ORDER per candidate: official/structured full text (PMC JATS) > publisher OA VoR > repository
   bytes whose OWN FRONT MATTER proves they are the VoR > accepted manuscript > preprint.
 * A PUBLISHER URL GETS ONE ATTEMPT. A 403 ends that URL and ADVANCES TO REPOSITORIES — it must not
   trigger repeated publisher requests (we burned the last run on 403 walls).
 * STOP RULE: once a complete, identity-confirmed, policy-admissible manifestation is obtained, cancel the
   remaining lower-priority work for that candidate.
 * CHECKPOINT every outcome to the ledger immediately (resumable: on restart, skip units already done).
 * prioritise the EMPTY CELLS (manufacturing/retail/finance/education/agriculture/transport) and the
   2023-2025 frontier, then by weighting.py quality.
 * REPORT per Sol: attempted, responded, candidate URLs, fetched manifestations, complete documents,
   identity CONFIRMED/UNRESOLVED/DIFFERENT_WORK, expression versions, STRICT JOURNAL-ATTRIBUTABLE COUNT,
   unique incremental yield per route, overlap, 401/403/429, unresolved route failures.

Confirm it is ALIVE and the ledger is GROWING (tail the log, show blobs appearing), then RETURN — do not
block your turn. The main session monitors and runs the census when it plateaus.

Report: the launch command, proof it is running, the streaming outcome histogram so far, and the current
strict-journal-attributable count. Do NOT commit.`,
  { label: 'launch the real fetch', phase: 'Fetch' })

return { p0: String(p0).slice(0, 600), routes: routes.filter(Boolean).length, attack, fetch: String(fetch).slice(0, 1200) }
