# Verdict

A SOTA-class corpus makes `0.5603` reachable, but the corpus alone will not get there. The correct diagnosis is:

- The current corpus is materially weaker than its labels say: 70 works, 24 nominal full texts, but only 16 complete evidence-bearing manifestations and only 10 currently journal-attributable.
- Source policy must remain question-derived. Cellcog’s lenient 8.0 is evidence about the judge, not permission to violate “only journal articles.”
- Working papers should be admitted when the question permits them, cited explicitly as working papers. They remain discovery-only for task 72.
- The winning acquisition objective is not “100 papers” or “202 numbers.” It is enough independent, interpretable evidence to close the question’s important cells and create high-value contrasts.
- A realistic forecast is `+0.035–0.065` from the corpus program with the present writer, and another `+0.025–0.055` from architecture that actually turns those sources into report-level argument. Those effects overlap. `0.5603` lies inside the combined plausible range, but remains unmeasured.

The strongest evidence that corpus is not sufficient is bodhi: `0.5441` with one venue mention and 4,361 words. Cellcog proves what a deep corpus plus strong document architecture can do; bodhi proves citation count is not the mechanism.

## What the code actually does today

The acquisition path is a task-72 program:

- [journal_corpus_build.py](/home/polaris/wt/flywheel/scripts/journal_corpus_build.py:44) contains twelve hand-selected AI/labor anchors and two topic regexes.
- Its selection test searches title plus venue, not source content, and raw Crossref citation count becomes ranking and output order.
- [deep_fetch.py](/home/polaris/wt/flywheel/scripts/deep_fetch.py:62) searches OA locations by DOI but originally accepted 500 words as full text and collapses HTTP failures into missing results.
- [wp_fetch.py](/home/polaris/wt/flywheel/scripts/wp_fetch.py:51) improves the length test and correctly adds title-based version discovery, but stamps every successful result `working_paper` without retaining the URL or deriving what the bytes actually are.
- [research_contract.py](/home/polaris/wt/flywheel/scripts/research_contract.py:136) is a good start on question-derived policy and coverage, but it is downstream of acquisition. Its coverage closure still uses global constants and lexical routing.
- [journal_corpus_content.json](/home/polaris/wt/flywheel/outputs/journal_corpus_content.json) ends in 2023.
- The newer [provenance.py](/home/polaris/wt/flywheel/scripts/provenance.py:143) correctly distinguishes works, expressions, manifestations, and spans. Applied read-only to the corpus, it finds:

| Content-derived state | Count |
|---|---:|
| Complete evidence-bearing manifestations | 16 |
| Journal-attributable manifestations | 10 |
| Complete working-paper manifestations | 6 |
| Unknown-version manifestations | 50 |
| Wrong-work bodies | 1 |
| Corrupt extraction | 1 |

Therefore the next legal release may initially score lower: the release boundary will remove evidence previously counted as usable. That loss is mandatory under the Law.

# The acquisition pipeline

```text
Question
  ↓
Question-derived research contract and source policy
  ↓
Evidence-requirement graph
  cells × evidence roles × dates × contrasts
  ↓
Query portfolio
  broad | cell-specific | recent | null/contrary | method | citation graph | exact-version
  ↓
Capability-based source router
  ↓
Parallel search and complete attempt ledger
  ↓
All-location fetch
  ↓
Content-derived identity, completeness, and manifestation typing
  ↓
Span-bound evidence cards with interpretable result tuples
  ↓
Study/work/expression/manifestation deduplication
  ↓
Claim baskets and contradiction graph
  ↓
Coverage/gap remeasurement
  ↺ recursive search until evidence closure or honest saturation
  ↓
Report-specific weighted evidence view
```

The permanent objects should be:

1. `CandidateRecord`: what search found, which query found it, and which cells it might serve.
2. `Work`: study, case, statute, trial, or other research object.
3. `Expression`: journal version, accepted manuscript, working paper, preprint, official text, registry record.
4. `Manifestation`: exact fetched bytes, URL, hash, fetch outcome, and content-derived profile.
5. `EvidenceCard`: verbatim span plus population/design/outcome/scope/time/uncertainty.
6. `Basket`: independent cards addressing the same typed proposition.
7. `GapRecord`: what remains missing and whether it is a discovery, access, extraction, contradiction, or real-evidence gap.

“Select” means scheduling high-marginal-value candidates for fetching and composition. It does not mean deleting credible on-topic sources. Hard deletion remains limited to chrome/non-sources and semantically confirmed off-topic material.

# 1. Source policy

## Decision

Admissibility is a function of the question and the expression actually held:

```text
admissible = policy(question) × expression_kind × evidence_role × completeness
```

Use three lanes:

- `REPORT_EVIDENCE`: may be cited in the answer.
- `DISCOVERY_ONLY`: may generate queries, references, author searches, and version searches, but may not enter report prose.
- `QUARANTINE`: wrong work, landing page, corrupt extraction, unresolved version, or incomplete artifact.

For an unrestricted research question, a working paper may enter `REPORT_EVIDENCE`, explicitly as “NBER Working Paper …” or “working paper,” at its appropriate weight. It can support findings printed in its own verbatim spans.

For task 72, the explicit “only … journal articles” clause controls:

| Expression held | Task-72 body |
|---|---|
| Journal version | Yes |
| Publisher OA copy of journal version | Yes |
| Accepted manuscript | Only if an asserted span-preserving relationship permits the exact span to name the journal expression |
| Working paper | No; discovery-only |
| Preprint | No; discovery-only |
| Book or magazine essay | No |
| Official report | No |

Cellcog’s use of Webb, Schwab’s book, and *Foreign Affairs* is honest attribution but imperfect instruction following. It is not fabrication, yet it remains a policy violation. We should not copy that violation merely because the judge was lenient.

In a non-exclusive report, lower-status expressions belong where their role fits:

- Working papers/preprints: “emerging or not-yet-peer-reviewed evidence.”
- Books: theory, history, or doctrine.
- Essays and policy reports: framing or institutional context.
- They must never be printed under the journal manifestation’s name.

## Does this recover Autor, Acemoglu, and Goos tonight?

Partly, but not by blanket re-admission:

- Autor–Levy–Murnane 2003: its 14,926-word body is currently an unresolved expression, so it is admissible under neither journal-only nor any-identified-version policy until its identity/version is established.
- Acemoglu–Restrepo, “Robots and Jobs”: the held 19,205-word body identifies itself as an NBER working paper. It becomes admissible immediately under an any-version policy, cited as the NBER working paper. It remains excluded from task 72.
- Acemoglu–Restrepo 2019 JEP: the held body is already recognized as a journal version.
- Goos–Manning–Salomons 2014: the held body is already journal-attributable.
- Goos and Manning 2007 is not in this 70-work corpus and still requires discovery and acquisition.

So the source-policy change recovers real evidence for questions that permit working papers. It does not honestly restore all of it to task 72.

Clinical behavior: journal versions, systematic reviews and completed trials dominate; registries and regulatory texts are authoritative for their own claims; preprints are clearly separated and cannot ground clinical recommendations.

Legal behavior: official statute, regulation, treaty, and judicial-opinion expressions dominate. Books and journal commentary are secondary doctrine. “Journal-only” is applied only if the question actually asks for it.

Thin-evidence behavior: working papers do not get promoted merely to avoid saying “unsettled.” The correct answer remains thin.

Data edit: add expression-kind/evidence-role rows to a source-policy table. A new domain must not require a new `if domain == ...` branch.

Silent failure: a fetcher’s `working_paper`, `FULLTEXT`, or `peer_reviewed` label is trusted. Prevention: derive the release label again from bytes and graph edges.

Expected delta: immediate strict enforcement before replenishment: `-0.005 to -0.020`. After replenishment: `+0.002 to +0.008`. The source-quality criterion can contribute at most about `+0.010` from its present 7.32 even if raised to 10.

# 2. Reaching approximately 100 deep sources

The strategy must change from “choose canonical paywalled works, then chase copies” to “OA-first discovery plus version pursuit.”

## Actual routes

| Route | Role |
|---|---|
| Publisher-native OA, DOAJ, SciELO | Highest-yield journal-version lane. DOAJ currently exposes over 13 million article records and open metadata. [DOAJ](https://doaj.org/) |
| PMC and Europe PMC | Journal versions and author manuscripts in clinical/life-science domains; Europe PMC offers OA full-text XML. [Europe PMC API](https://europepmc.org/RestfulWebService) |
| PubMed/PMC linking | Domain search, MeSH expansion, publication types, and PMID–PMCID–DOI linking. [NCBI APIs](https://www.ncbi.nlm.nih.gov/home/develop/api/) |
| OpenAlex and Unpaywall | Enumerate known publisher and repository locations; never treat their version label as final truth. OpenAlex exposes location version, PDF, OA, accepted and published fields. [OpenAlex work API](https://developers.openalex.org/api-reference/works/get-a-single-work) |
| CORE | Search institutional and subject repositories, including full text and version/duplicate discovery. [CORE API](https://core.ac.uk/services/api) |
| OpenAIRE | European research-product and repository metadata, access rights, instances and identifiers. [OpenAIRE Graph API](https://api.openaire.eu/graph/swagger-ui/index.html) |
| OpenDOAR plus repository OAI-PMH | Discover and query institutional repositories directly. [OpenDOAR](https://opendoar.ac.uk/) |
| Zenodo/HAL/institutional archives | Accepted manuscripts, reports, preprints and publisher PDFs—each retyped from its bytes. [Zenodo API](https://developers.zenodo.org/) |
| NBER/IZA/RePEc/SSRN/arXiv/medRxiv | Separate-work and preprint discovery. Admissible only when the question’s policy permits that expression. |
| Crossref | Identity, dates, relations, references, retractions and exact-title discovery—not a full-text service. [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/) |
| Official legal systems | GovInfo/courts, EUR-Lex/Cellar, national legislation portals and official gazettes. [GovInfo developer hub](https://www.govinfo.gov/developers), [EUR-Lex services](https://eur-lex.europa.eu/content/help/data-reuse/webservice.html?locale=en) |

For PMC, bulk acquisition must use the permitted OAI-PMH, FTP, or cloud services rather than scraping the public site. [PMC access rules](https://pmc.ncbi.nlm.nih.gov/about/copyright/)

Every discovered location is attempted, with these outcomes kept distinct:

```text
FETCHED
NOT_FOUND
ACCESS_DENIED
THROTTLED
TRANSIENT_ERROR
LANDING_PAGE
ABSTRACT_ONLY
WRONG_WORK
CORRUPT_EXTRACTION
```

Only `NOT_FOUND` across exhausted applicable routes supports “we did not locate an accessible copy.” A 429 never does.

## Realistic yield

For task 72:

- One night cannot credibly promise 100 complete journal-attributable manifestations.
- OA-first discovery should do materially better than the observed 19% success from chasing a paywalled bibliography, but management and information-systems publishing remains the hard tail.
- My engineering forecast is 40–70 complete, journal-attributable manifestations after a serious acquisition pass.
- Approximately 70–100 complete, honestly named manifestations is plausible if working papers and accepted manuscripts are permitted.
- Reaching 100 journal-only works may require several hundred candidate works, a subscription/resolver lane, or a longer repository campaign.

The count remains a capacity target, not a stopping rule. A clinical question may yield hundreds through PMC; a narrow legal comparison may need only a few controlling authorities; a thin field may correctly stop at six.

Clinical behavior: use PubMed, Europe PMC/PMC, trial registries and regulatory records. NIH’s current policy makes accepted manuscripts for covered papers publicly available without embargo from the official publication date, improving this lane. [NIH Public Access policy](https://www.grants.nih.gov/policy-and-compliance/policy-topics/public-access)

Legal behavior: official texts are often directly accessible; the scarcity problem is usually identifying controlling and comparable authority, not PDF access.

Thin-evidence behavior: the system retains a small honest corpus. It never manufactures breadth through weaker adjacent material.

Data edit: a source-route registry row defines API, query syntax, supported expression kinds, date fields, authentication, rate limits and jurisdictions.

Silent failure: abstract/landing page stamped full text; wrong work matched by title; repository label treated as version; missing URL prevents provenance; throttling treated as absence.

Expected delta: `+0.010 to +0.025`, principally through depth/representativeness, evidence clarity and grounded mechanism coverage.

# 3. Recency

“Just search by date” is correct because backward citation expansion systematically misses recent work: recent papers have not accumulated references or citations.

Use two independent lanes:

1. Foundation lane: seminal theories, landmark methods and long-run evidence. No recency penalty simply for being old.
2. Frontier lane: explicit publication-date windows searched directly and sorted by publication/online date, not citation count.

For task 72, the frontier lane begins at the generative-AI event boundary and searches overlapping bands such as:

- since 2023;
- last 24 months;
- last 12 months;
- accepted/online-ahead-of-print;
- newly indexed since the previous run.

The exact windows belong in a recency profile, not code. Queries must use each database’s correct fields: publication date, accepted date, posted date, registration date and last-updated date are not interchangeable. Crossref exposes separate publication, online, accepted and posted date filters. [Crossref date filters](https://www.crossref.org/documentation/retrieve-metadata/rest-api/rest-api-filters/)

Recency is claim-specific:

- A current adoption-rate claim needs recent evidence.
- A foundational theory does not.
- A current statute needs effective/amendment status.
- A clinical conclusion needs the latest completed trials, corrections and retractions.
- A thin frontier may have only preprints, which must remain labeled as such.

Cochrane’s guidance treats current searching as a separate obligation: relevant sources should be rerun close to publication, with ongoing and awaiting-classification studies tracked rather than silently omitted. [Cochrane searching guidance](https://training.cochrane.org/handbook/current/chapter-04)

Clinical behavior: search publication dates, trial completion/results-posting dates, registry updates, corrections and retractions.

Legal behavior: prioritize current effective text and subsequent treatment, not merely the newest commentary.

Thin-evidence behavior: a recent search returning no eligible evidence strengthens a corpus-scoped “no recent eligible evidence located” statement, not “the field proves no effect.”

Data edit: recency profile rows specify relevant date semantics, surveillance cadence and frontier windows for evidence ecosystems.

Silent failure: sorting by index date; future-dated records; recent studies penalized for low citations; recent-only search deletes foundational work; stale search cache appears current.

Expected delta: `+0.006 to +0.015`. The current corpus’s 2023 ceiling makes task 72 unusually likely to sit near the top of this range.

# 4. Gap-driven recursive search

A coverage cell must be an evidence requirement, not a topic keyword. Each cell carries:

```text
subject/population
outcome or doctrinal issue
evidence role
minimum interpretable tuple
time requirement
source-policy requirement
current supporting works
contradictions
gap type
```

After each acquisition/extraction round, gaps are classified:

- `DISCOVERY_GAP`: no candidate work found.
- `ACCESS_GAP`: candidates exist but no admissible complete manifestation is held.
- `EXTRACTION_GAP`: text exists but no direct result span was extracted.
- `DIVERSITY_GAP`: evidence comes from one study, design or context.
- `RECENCY_GAP`: no current evidence for a time-sensitive claim.
- `CONTRADICTION_GAP`: findings conflict and moderators are missing.
- `EVIDENCE_GAP`: independent search routes are saturated without eligible evidence.

Each gap generates a different query family. Retail employment, for example, would trigger outcome-specific, method-specific, current, cited/citing and null-result searches—not another copy of the broad AI/labor query.

A cell closes on evidence only when it has enough independent result-bearing evidence to support the requested comparison. It closes as thin when:

- multiple applicable databases and query families were attempted;
- citation chasing and exact-version pursuit were exhausted;
- recent queries were run;
- duplicate studies were collapsed;
- recent attempts produced no new eligible evidence;
- failures were not throttling or access errors.

This is operational saturation, not a claim of exhaustive literature recall.

Clinical behavior: cells are population × intervention × comparator × outcome × time, with trial design and risk of bias carried explicitly.

Legal behavior: cells are jurisdiction × issue × authority level × relevant period; “two sources” never substitutes for one controlling authority.

Thin-evidence behavior: thin closure is a successful terminal state and produces appropriately scoped uncertainty.

Data edit: coverage profiles specify evidence tuple, authority rules, design-diversity requirements and saturation parameters.

Silent failure: bad aliases create a false gap; ten manifestations of one study close a cell; access failure becomes evidence absence; repeated near-identical queries masquerade as independent search.

Expected delta: `+0.014 to +0.025`. Raising the two measured industry criteria merely from 5.76/5.82 to about 7.5 is worth roughly `+0.019` by their weights, before any synthesis benefit.

# 5. Insight rather than count

The acquisition objective is marginal insight readiness:

```text
Value of candidate =
  new required-cell coverage
+ complete interpretable result tuple
+ independent corroboration
+ method/population/context contrast
+ null or counterevidence
+ current-frontier contribution
+ ability to explain an existing contradiction
- same-study/version redundancy
```

This is a vector retained through composition, not one opaque scalar. Source authority, methodological quality, relevance, independence, recency and contrast value stay separate.

An “insight-ready basket” contains:

- exact verbatim spans;
- comparable outcome and unit;
- population, setting, time and design;
- independent works rather than versions of one work;
- agreement or contradiction;
- the moderator that may explain the difference.

That is what permits high-value owned synthesis. For example:

- Attributed premises: each paper’s reported result, tied to its span.
- Owned inference: “The divergence is more consistent with institutional setting than with technology class.”
- The owned sentence names no source and introduces no new figure or source-specific particular.

The system should actively search for null findings, counterexamples and different methods. A fifth positive estimate in the same context usually adds less insight than the first credible null, a different population, or a design that resolves a disagreement.

Clinical behavior: prioritize effect size plus comparator, population, follow-up, uncertainty and bias—not isolated percentages.

Legal behavior: insight comes from comparing rules, holdings, exceptions, authority levels and institutional consequences; numbers may be irrelevant.

Thin-evidence behavior: a well-supported explanation of why evidence cannot settle the issue is an insight outcome.

Data edit: domain profiles supply evidence-tuple fields, quality/risk-of-bias dimensions, authority hierarchy and useful contrast types.

Silent failure: the model-written claim determines routing; versions of one study count as corroboration; source count becomes quality; positive findings crowd out nulls; an owned synthesis sentence accidentally names a source.

Expected delta: `+0.008 to +0.020` from better acquisition and allocation under the present writer; `+0.015 to +0.035` when the report-level synthesis architecture actually consumes the baskets.

# 6. Does this make 0.5603 reachable?

Yes—but only as a joint corpus-and-architecture result.

The measurable headroom shows the division:

| Criterion | Current | Leader | Maximum weighted gap represented |
|---|---:|---:|---:|
| Critical cross-industry synthesis | 6.36 | 9.60 | `+0.0259` |
| Industry-specific analysis | 5.76 | 9.30 | `+0.0257` |
| Novel themes/linkages | 7.20 | 9.80 | `+0.0166` |
| Analytical mechanisms | 7.96 | 9.70 | `+0.0139` |
| Depth/representativeness | 7.16 | 9.50 | `+0.0102` |
| Source exclusivity | 7.32 | 8.00 | `+0.0025` |

The corpus directly attacks industry coverage, representativeness, current evidence, empirical texture and the availability of contrasts. It does not by itself create:

- report-level argument;
- cross-source explanatory synthesis;
- section transitions;
- hierarchy and pacing;
- disciplined owned insight;
- fluent document control.

My non-additive forecast is:

| Release state | Expected movement from the `0.4603` performance coordinate |
|---|---:|
| Strict manifestation enforcement before replenishment | `-0.005 to -0.020` |
| SOTA-class acquisition corpus with current writer | `+0.035 to +0.065` |
| Architecture able to exploit insight-ready baskets | additional `+0.025 to +0.055` |
| Combined plausible band | approximately `0.520–0.580` |

This changes my earlier architecture-only answer: architecture alone cannot reach the leader from this corpus. A SOTA-class corpus makes the target reachable, but does not make it expected.

Clinical behavior: success requires current trials, systematic reviews, registries and claim-level bias/certainty—not merely more papers.

Legal behavior: success may use a small corpus of controlling primary texts plus strong comparative doctrine. A 100-source target would actively damage it.

Thin-evidence behavior: the winning corpus may be deliberately small, because the correct report is an uncertainty result.

Data edit: a new domain adds routes, authority/quality profiles, vocabularies, evidence tuples and evaluation questions. The orchestration code remains unchanged.

Silent failure: a task-72 win is reported as generalization; corpus and writer changes are stacked; judge-relative movement is mistaken for absolute improvement; the legal release baseline is compared with a previously fabricated artifact.

Expected delta: corpus-only `+0.035–0.065`; full system `+0.060–0.105`, with overlap and large uncertainty.

## Release order

The cumulative ladder should be:

1. Frozen current corpus + strict manifestation boundary.
2. Same writer + repaired publisher/OA locations.
3. Add OA-native discovery routes.
4. Add date-lane searches.
5. Add gap recursion.
6. Add marginal-insight scheduling and basket consolidation.
7. Only then enable report-level synthesis over the frozen enriched corpus.
8. Run the same ladder on unseen clinical, legal/comparative and deliberately thin-evidence questions.

A claimed “general system” requires those cross-domain results. Until then, the honest conclusion is narrower: this is the acquisition design most likely to remove the task-72 source ceiling without baking task 72 into the code.