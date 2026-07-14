No code was changed. This is the build contract for Opus.

## Decision

Build a resolver-to-manifestation lane with four hard boundaries:

1. Repository adapters only discover `DocumentCandidate` records.
2. A generic acquisition executor fetches and hashes the bytes.
3. Reducers derive identity, completeness, version, and admissibility from those bytes.
4. Attribution permission is granted per verified span, never from an accepted-manuscript label.

Before adding volume, close the current P0:

- Remove `accepted_manuscript_of` from `SPAN_PRESERVING` in [provenance.py](/home/polaris/wt/flywheel/scripts/provenance.py:216).
- Stop mapping `acceptedVersion` to a span-preserving relationship in [version_align.py](/home/polaris/wt/flywheel/scripts/version_align.py:220).
- Stop declaring accepted manuscripts journal-admissible merely from repository metadata in [alignment_census.py](/home/polaris/wt/flywheel/scripts/alignment_census.py:140).

An accepted manuscript is admissible only when the contract permits accepted manuscripts, and attribution must name that manifestation. It is never the journal version merely because a repository says `acceptedVersion`.

Two verification corrections:

- `source_routes.yaml` is syntactically valid: 25 route IDs, no duplicate IDs. My interim duplicate-arXiv warning was caused by overlapping truncated output. The problem is missing executable adapter wiring, not malformed YAML.
- The named `outputs/acquisition_campaign/` contains discovery artifacts, not the 5,061-unit full-text dead-run ledger. I therefore accept the operator’s 2,490-candidate census as an input, but the yield figures below are forecasts, not measurements reconstructed from that directory.

## 1. The lane boundary

Introduce these persistent records:

```text
ResolveContext
  work_id
  contract_id
  identifiers[]        # DOI, PMCID, PMID, OAI ID, CELEX, ECLI, etc.
  title
  authors[]
  year
  required_artifact_kinds[]
  permitted_expression_kinds[]
  required_capabilities[]

DocumentCandidate
  candidate_id
  work_id
  discovered_by_route
  resolver_request_id
  identifier_used
  retrieval_url
  repository_record_url
  media_hint
  version_hint          # observation only
  license_observation   # observation only
  raw_metadata_blob_id
  raw_metadata_hash

Manifestation
  manifestation_id
  candidate_id
  retrieval_request_id
  raw_blob_id
  raw_hash
  extracted_text_blob_id
  extracted_text_hash
  extraction_version
```

The adapter must not write `FULLTEXT`, `THIS_WORK`, `VERSION_OF_RECORD`, `ADMISSIBLE`, or an expression edge. Those are reducer outputs derived from immutable metadata and document bytes.

`candidate_id` must follow the entire chain:

```text
resolver request → candidate → content request → redirects → manifestation
```

That fixes the current route-credit error: [source_router.py](/home/polaris/wt/flywheel/scripts/source_router.py) can presently credit an adapter with a full-text manifestation fetched through some other adapter because it reduces all work-level manifestations rather than the adapter’s own candidate lineage.

Also remove the flat-corpus write in [deep_fetch.py](/home/polaris/wt/flywheel/scripts/deep_fetch.py:185):

- It currently admits anything except `CITATION_ONLY`, including some unreadable/non-document results.
- It truncates extracted text to 120,000 characters.
- It discards the manifestation identity needed by the law.

Downstream synthesis should receive verified binding IDs, never detached text files.

## 2. Route specifications

All “yield” figures are gross forecasts among the approximately 2,490 no-known-OA candidates. They overlap and are not additive.

### PMC

- Query:
  1. Convert DOI/PMID to PMCID with the PMC ID Converter.
  2. `GetRecord` from PMC OAI using `oai:pubmedcentral.nih.gov:<numeric-pmcid>` and `metadataPrefix=pmc`.
  3. If needed, query the PMC OA service for PDF/tarball links.
- Resolves by: PMCID first; DOI or PMID through ID conversion.
- Returns: JATS full-text XML where rights permit; the OA service may return PDF/package links. A PMCID does not guarantee downloadable OA full text.
- Politeness: PMC OAI allows at most three requests per second, no concurrent requests, and recommends large harvesting off-peak. Batch up to 200 IDs through the ID converter. Register tool/email. [PMC ID Converter](https://pmc.ncbi.nlm.nih.gov/tools/id-converter-api/), [PMC OAI](https://pmc.ncbi.nlm.nih.gov/tools/oai/), [PMC OA service](https://pmc.ncbi.nlm.nih.gov/tools/oa-service/), [NCBI usage guidance](https://www.ncbi.nlm.nih.gov/books/NBK25497/)
- Clinical: primary full-text route; prefer JATS because identity, sections, contributors, DOI, and closure are structurally observable.
- Legal/comparative: invoked only when the contract requests scholarly literature carrying DOI/PMID identifiers, not for official legal texts.
- Thin evidence: a rights-blocked or missing OAI record is a route observation, not proof that no document exists.
- Data edit: PMC endpoints, identifier transforms, metadata prefixes, and rate budget. Code changes only for a new protocol/parser primitive.
- Silent failures: PMCID exists but full text is not in the OA subset; XML is front matter only; NIH manuscript is mistaken for publisher VoR; embargo/live status is ignored.
- Gross yield forecast: 20–60.

### Europe PMC

- Query: exact DOI search using `/rest/search?query=DOI:"..."&resultType=core&format=json`; inspect `pmcid`, `fullTextIdList`, `fullTextUrlList`, `hasPDF`, and OA fields. Fetch JATS with `/rest/{PMCID}/fullTextXML`.
- Resolves by: DOI, PMCID, PMID, or Europe PMC source/id.
- Returns: core metadata, full-text URLs, and OA JATS XML for eligible records. The currently configured `/{source}/{id}/fullTextXML` shape is wrong for PMCID retrieval.
- Politeness: official documentation does not publish a stable numeric public quota. Start at one request/second and one in flight, then obey `429`, `Retry-After`, and any returned limit headers. [Europe PMC REST](https://europepmc.org/RestfulWebService), [official API specification](https://www.ebi.ac.uk/europepmc/webservices/api/swagger.json)
- Clinical: complements PMC with European indexing and identifiers.
- Legal/comparative: only for relevant scholarly literature.
- Thin evidence: distinguishes “record found, no accessible full text” from “identifier not found.”
- Data edit: endpoint templates, response selectors, rate budget.
- Silent failures: abstract mistaken for full text; PMCID present but XML unavailable; source/id normalization error; duplicated PMC copy counted as incremental.
- Incremental gross yield forecast after PMC: 5–20.

### DOAJ

- Query: exact article search on DOI; read `bibjson.link[]` entries whose type is `fulltext`.
- Resolves by: DOI primarily; title plus author only as a candidate generator.
- Returns: metadata and publisher/repository full-text URLs, generally not document bytes.
- Politeness: average two requests/second; brief bursts may be queued. [DOAJ API](https://doaj.org/api/)
- Clinical: finds OA journals outside PMC coverage.
- Legal/comparative: finds OA legal and comparative scholarship, but never official legislation or judgments.
- Thin evidence: a DOAJ miss means “not indexed in DOAJ,” not “not open.”
- Data edit: query template and link selector.
- Silent failures: stale or landing-page URL; URL redirects to login; DOI metadata points to a supplement; directory membership is mistaken for byte-level version proof.
- Incremental gross yield forecast: 10–25.

### CORE

- Query: `/v3/search/works?q=doi:"..."`; prefer record `downloadUrl` or documented output download. Treat a returned `fullText` field as a derived text manifestation, not automatically as a complete PDF equivalent.
- Resolves by: DOI; CORE work/output ID; OAI ID; title plus author for unresolved candidates.
- Returns: metadata, extracted full text, source URLs, download URLs, and repository/OAI identifiers.
- Politeness: enforce the authenticated tier reported by CORE and its rate headers. Current documentation describes materially different daily and per-minute budgets by tier; full-text download is more expensive. The currently configured credential returns 401, so preflight must mark the route unavailable rather than conclude that content is absent. [CORE API](https://api.core.ac.uk/docs/v3)
- Clinical: useful for accepted manuscripts and institutional copies outside PMC.
- Legal/comparative: strong for repository scholarship and working papers, but repository copies are not official legal texts.
- Thin evidence: an exhausted authenticated exact-DOI query contributes to search coverage; an unauthenticated or 401 run contributes only `BACKEND_FAILED`.
- Data edit: credential profile, query template, output selectors, rate costs.
- Silent failures: OCR/truncated `fullText`; supplement returned as primary file; API tier omits full text; direct file link expires; repository metadata says accepted manuscript but bytes are another work.
- Gross yield forecast: 60–140.

### OpenAIRE Graph

- Query: current Graph API `/graph/v3/research-products?pid=<doi>`; inspect product instances, PIDs, access rights, licences, and URLs.
- Resolves by: DOI/PID or OpenAIRE research-product ID.
- Returns: graph metadata and candidate locations. URLs remain candidates; OpenAIRE metadata is not document proof.
- Politeness: current documented limits are up to 60 requests/hour unauthenticated and 7,200/hour authenticated. Use authentication and schedule against the lower of configured and observed limits. [OpenAIRE Graph API](https://graph.openaire.eu/docs/apis/graph-api/), [OpenAIRE API terms](https://graph.openaire.eu/docs/apis/terms)
- Clinical: finds institutional and national repository copies not exposed through PMC.
- Legal/comparative: finds cross-jurisdictional scholarship and repository deposits.
- Thin evidence: exact PID exhaustion can close this route; stale or inaccessible candidate URLs cannot.
- Data edit: replace the legacy endpoint in YAML with the Graph v3 operation and response selectors.
- Silent failures: access-right label is stale; URL is only a repository landing page; multiple instances represent the same file; graph metadata and fetched bytes disagree.
- Gross yield forecast: 45–110.

### Zenodo

- Query: `/api/records?q=doi:"..."`; also inspect `pids`, related identifiers, `conceptdoi`, version, resource type, and each file.
- Resolves by: record DOI, concept DOI, related DOI, Zenodo record ID; title plus creator only for candidate generation.
- Returns: record metadata and direct file links.
- Politeness: rate limits are endpoint/account dependent; use `X-RateLimit-Limit`, `Remaining`, and `Reset`, and defer on 429. [Zenodo API](https://developers.zenodo.org/)
- Clinical: can contain manuscripts, trial artifacts, protocols, data, and supplements. Artifact type must remain explicit.
- Legal/comparative: may contain scholarship or datasets, but not authoritative law merely because it has a DOI.
- Thin evidence: non-article files may themselves be the correct evidence artifact if the contract requested protocols or data; otherwise they do not fill the full-article role.
- Data edit: resource-type mappings, PID fields, file selectors, rate budget.
- Silent failures: dataset/supplement mistaken for article; concept DOI resolves to the wrong version; restricted record has metadata but no bytes; multiple files are concatenated into a fictitious document.
- Gross yield forecast: 5–20.

### Institutional OAI-PMH

- Query:
  - Do not attempt global per-work OAI harvesting.
  - Obtain the OAI identifier and repository base URL through CORE, OpenAIRE, repository metadata, or an incrementally maintained local index.
  - Use `GetRecord(identifier, metadataPrefix)`.
  - Rich formats such as JATS, METS, MODS, OAI-ORE, or repository-specific XML may expose document URLs. `oai_dc` commonly exposes metadata or a landing page only.
- Resolves by: OAI identifier. OAI-PMH has no universal exact-DOI lookup.
- Returns: metadata records; sometimes file URLs or embedded structured full text, depending on the repository and metadata format.
- Politeness: repository-specific. Default to one in flight and a two-second interval until the repository row states otherwise; obey `Retry-After`, robots rules, resumption tokens, and deletion records. [OAI-PMH specification](https://www.openarchives.org/OAI/openarchivesprotocol.html)
- Clinical: reaches university manuscripts and subject repositories beyond PMC.
- Legal/comparative: reaches institutional scholarship; official courts and legislatures should use dedicated official-source adapters.
- Thin evidence: only a clean `GetRecord`/indexed lookup closes that repository. A missing local DOI-to-OAI mapping does not.
- Data edit: each repository is a row containing base URL, supported metadata prefixes, identifier mappings, file XPath/selectors, and rate policy. A code edit is needed only for a genuinely new metadata dialect primitive.
- Silent failures: `oai_dc` landing page treated as PDF; deleted record treated as no-world evidence; DOI belongs to a cited reference; repository cover sheet hides a different article; resumption state is lost.
- Gross yield forecast: 35–90.

## 3. Priority and stopping policy

Given a DOI, resolve in waves:

1. Re-derive identity, completeness, and admissibility for already held bytes.
2. In parallel, perform cheap exact-ID resolution through PMC/Europe PMC where applicable, DOAJ, Unpaywall, OpenAlex, and Semantic Scholar.
3. Resolve through CORE, OpenAIRE, and Zenodo.
4. Use resulting OAI IDs/repository locations for targeted institutional OAI-PMH.
5. Use title-plus-author only after exact identifiers fail. It may generate candidates but cannot establish identity.

Candidate fetching is ordered separately:

1. Official or authoritative structured full text permitted by the contract: PMC JATS, official legal XML, registry JSON.
2. Publisher-hosted OA VoR.
3. Repository-hosted bytes whose own front matter proves they are the VoR.
4. Accepted manuscript.
5. Preprint or working paper.

A publisher URL gets one normal attempt. A 403 ends that URL attempt and advances to repositories; it does not trigger repeated publisher requests.

Stop rules:

- If a complete, identity-confirmed, policy-admissible manifestation is obtained, remaining lower-priority work is cancelled with a pointer to the reducer decision that satisfied the contract.
- If only an accepted manuscript is found under a journal-VoR-only contract, keep searching every applicable VoR route.
- If the contract permits accepted manuscripts, it can satisfy the role only as an accepted manuscript and must be attributed as such.

## 4. Version equivalence

`accepted_manuscript_of` remains a useful bibliographic edge, but it is not span-preserving.

Change the attribution API from manifestation-wide permission to binding-specific permission:

```text
resolve_attribution(binding_id, attribution_policy)
```

A `SpanCorrespondence` must contain:

```text
source_manifestation_id + raw/text hash + offsets + verbatim span
target_manifestation_id + raw/text hash + offsets + verbatim span
canonicalization algorithm and version
exact canonical-span hash
identity decisions for both manifestations
```

The verifier rechecks both hashes, both offsets, and exact canonical text equality.

Consequences:

- Repository metadata alone can never prove span equivalence.
- A matching span found independently in VoR bytes should normally be rebound directly to the VoR manifestation.
- A correspondence grants permission only for that span, not every assertion in the manuscript.
- A disagreement such as 0.37 versus 0.2 fails immediately.
- Expression-wide `exact_copy_of` is reserved for identity-confirmed manifestations whose entire canonical document text is equal.
- An accepted manuscript without VoR bytes remains accepted-manuscript-attributable only.

## 5. Wrong-work and completeness defence

Identity extraction must use the fetched content itself:

- JATS/XML: article DOI, title group, contributors, journal, publication dates.
- PDF: front-matter DOI, normalized title, byline, journal/version marks from the first pages. Repository cover sheets are segmented from article front matter.
- HTML: citation metadata plus visible article header. Metadata alone is insufficient if visible content conflicts.
- Legal text: package/CELEX/ECLI/docket/citation and revision/as-of markers.
- Registry: registry identifier and record version.

Decision rules:

- `CONFIRMED`: exact front-matter DOI, or high-specificity title plus compatible byline with no conflicting identifier.
- `DIFFERENT_WORK`: positive foreign DOI, or an incompatible foreign title plus disjoint byline.
- `UNRESOLVED`: generic title collision, weak title-only match, unreadable front matter, or contradictory metadata.

A generic title without an author must not produce `DIFFERENT_WORK`; the current event reducer is too aggressive here.

Completeness is artifact-specific and data-driven:

- JATS article: body-bearing structure and terminal sections/closure.
- PDF article: valid page structure, readable terminal pages, no truncation/download-error evidence.
- Legal judgment: short documents can be complete; use official structural closure rather than word thresholds.
- Registry: required record fields and version envelope, not prose length.

Every label is recomputed from raw content. HTTP 200, MIME type, API `fullText`, repository `acceptedVersion`, and filename are observations, never conclusions.

## 6. Generality contract

| Mechanism | Clinical | Legal/comparative | Thin evidence | Domain change |
|---|---|---|---|---|
| Capability routing | Selects trials, reviews, registries, guidelines, and biomedical full text | Selects official legislation/judgments plus doctrinal scholarship | Selects all routes capable of the required artifact, then reports clean exhaustion separately from failures | Add capability/artifact/source-policy rows |
| Identity | DOI/PMCID/NCT plus title/byline | CELEX/ECLI/package/docket/citation plus title/date | Leaves weak matches unresolved instead of forcing a corpus | Add identifier extractors/XPaths as data when supported |
| Version policy | Distinguishes registry, preprint, AM, and journal VoR | Distinguishes official revision, consolidated text, judgment, commentary | Allows “literature does not settle this” after admissible evidence is genuinely thin | Add permitted expression kinds to contract data |
| Completeness | JATS/article/registry profiles | Official XML/PDF and revision profiles | Short complete artifacts remain complete | Add artifact-profile rows |
| Search outcome | Separates no PMC full text from backend failure | Separates no official text from scholarship-only results | `SEARCHED_NONE`, `THIN`, and `SEARCH_FAILED` stay distinct | Add route coverage rows |

The router’s primary input must therefore be structured contract capabilities, not lexical topic matching. YAML token triggers can remain only as a low-confidence fallback. There must be no `if domain == clinical` or legal-topic regex.

Adding GovInfo, EUR-Lex, CourtListener, or another repository should normally mean adding rows for:

- protocol/adapter kind;
- supported artifact and jurisdiction capabilities;
- exact identifiers;
- endpoint templates;
- response/file selectors;
- version/revision fields;
- rate policy;
- authority class.

Code changes are warranted for a new wire protocol or a new reusable document/identity primitive—not for a new subject domain.

## 7. Politeness scheduler

Replace `_HOST_LAST` and the single `SPACING_S` in [acquisition.py](/home/polaris/wt/flywheel/scripts/acquisition.py) with a cross-process persistent scheduler:

- Per-host token bucket and concurrency limit.
- Resolver host and content host budgeted separately; redirects charge the destination host.
- Configured limits enforced from `source_routes.yaml`.
- Dynamic limits can only reduce the configured rate unless explicitly approved.
- Parse both numeric and HTTP-date `Retry-After`.
- Store `not_before`; do not sleep and retry three seconds later when the server requests hours.
- Cache exact-ID resolver responses; use ETag/Last-Modified where supported.
- Batch PMC identifiers.
- Circuit-break on repeated 401/403/429/5xx.
- Parallelize across independent hosts, not within a host beyond its policy.

Outcome semantics:

- 429 → `THROTTLED` and deferred.
- 401 → `AUTH_FAILED`.
- 403 → `ACCESS_DENIED` for that URL.
- Timeout/5xx → bounded retry then `BACKEND_FAILED`.
- None of these may reduce to “no OA copy exists.”

## 8. Yield forecast

For the approximately 2,490 candidates with no known OA URL:

- Complete, correct-work document manifestations: approximately 450–850, or 18–34%.
- Strict journal-VoR-attributable full texts: approximately 180–360, or 7–14%.
- Additional accepted-manuscript/preprint leads: approximately 200–400, not counted as strict journal full text.

The best working point estimate is roughly 260 additional strict journal-attributable full texts. It is not yet measured strongly enough to use as a commitment.

Calibrate with a frozen stratified canary of 200–300 DOI-bearing candidates, split across venue/year/field/access status. Report unique incremental yield after each route, not gross candidates.

## 9. Build and release order

1. Close the accepted-manuscript P0 and route-lineage bug.
2. Add candidate/provenance schema and persistent host scheduler.
3. Wire PMC, Europe PMC, and DOAJ.
4. Add CORE, OpenAIRE Graph v3, and Zenodo.
5. Add generic targeted OAI-PMH.
6. Add byte-derived identity, version, completeness, and per-span correspondence.
7. Run a cumulative ladder on one frozen corpus, one route addition at a time.
8. Only then freeze the enriched corpus and run synthesis comparisons.

Required tests:

- PMC VoR JATS becomes admissible.
- NIH/accepted manuscript remains non-VoR.
- The Parry/Yang-Hui He wrong-work case is quarantined.
- The Acemoglu 0.37/0.2 mismatch cannot align.
- An independently matching VoR span can be rebound.
- A short legal judgment is recognized as complete.
- A complete registry record does not need article-length prose.
- 429 never becomes `SEARCHED_NONE`.
- One route cannot inherit another route’s manifestation.
- Multiple worker processes remain inside the host budget.
- Truncated or HTML-error downloads cannot enter synthesis.

For every ladder step, report attempted, responded, candidate URLs, fetched manifestations, complete documents, identity-confirmed/unresolved/different-work, expression versions, strict journal-attributable count, unique incremental yield, overlap, 401/403/429, and unresolved route failures. Criterion-level evaluation must follow on a clinical, legal/comparative, and thin-evidence holdout before calling the lane general.