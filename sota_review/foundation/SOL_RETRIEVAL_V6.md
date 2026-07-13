## Verdict

Keep the provisional program’s three ideas, but change their implementation:

- Keep declarative routing, but extend the existing `EvidenceNeed` adapter registry. Do not build a second domain router.
- Keep field-normalized influence, but make it one dimension of an evidence vector—not the definition of quality.
- Keep coverage-driven selection, but make it coverage-driven search and allocation. It must never become a quota-based filter.

Do not wire the composer yet. There is a new integrity blocker.

### New P0 finding: working-paper text is being attributed to journal articles

[`wp_fetch.py`](/home/polaris/wt/flywheel/scripts/wp_fetch.py:211) inserts working-paper text into the corpus row for a journal DOI. [`evidence_miner.py`](/home/polaris/wt/flywheel/scripts/evidence_miner.py:1445) then hashes that text but retains the journal’s attribution metadata. It does not verify that the mined span appears in the published journal version.

That creates this path:

```text
NBER/SSRN working-paper span
    → stored under journal DOI row
    → writer names the journal article
    → gate checks the working-paper span
```

Under the Law, that is not admissible. A predecessor working paper and later journal article may be closely related, but they are different sources until version equivalence is proven. The recovered text is presently a discovery lead, not automatically journal-attributable evidence.

The completed fetch also reintroduced a false label: the current JSON calls the 544-word Autor (2015) copy `FULLTEXT`, because the fetch process had loaded the old threshold before the fix landed. The post-fetch artifact now says 27 full texts, but three are under 2,500 words—Frey, Tallon, and Autor—so the content-derived count is 24.

## Target architecture

```text
question
  → one canonical, provenance-bearing research plan
  → coverage atoms × required evidence roles
  → capability-registry route derivation
  → reproducible multi-family searches
  → typed work/version/content graph
  → semantic span-to-coverage binding
  → multidimensional evidence weights
  → adaptive gap-directed retrieval
  → claim baskets + global argument allocation
  → composer
```

### 1. One canonical research plan

**(a) Mechanism.** Merge `research_contract.Contract` with the existing live `ResearchFrame`; do not retain two independent LLM planners. One call emits entities, relations, comparators, outcomes, jurisdictions, source constraints, coverage axes, evidence roles, contrasts, and extraction facets. Every field carries provenance:

```text
question_span       hard constraint, because the question actually says it
planner_hypothesis  may guide retrieval, but may not exclude evidence
registry_derivation pure downstream derivation
```

All routing, outline, and coverage derivations after that call are pure functions. LLM-derived aliases may expand recall but cannot be hard gates.

**(b) Clinical.** The same frame projects into population/intervention/comparator/outcome/design atoms. The clinical projection comes from data-defined schemas, not a `clinical` branch in core code.

**(c) Legal/comparative.** It projects into jurisdiction, legal issue, authority type, effective date, procedural posture, and comparison atoms. No effect-size or number requirement is introduced.

**(d) Thin evidence.** An inferred facet remains a search hypothesis. Failure to find it becomes `SEARCHED_NONE` or `THIN`, not a fabricated filled cell.

**(e) Data edits.** New domain terminology, controlled vocabularies, evidence-role mappings, and quality-rubric schemas are new registry rows. Core compiler code changes only when the universal schema itself changes.

**(f) Silent failure.** The dangerous output is `contract_complete` when a required clause was omitted or an invented restriction was accepted. Every hard constraint therefore needs its own question span; plan completeness is computed from question-clause accounting, not asserted by the model.

**(g) Task-72 delta.** **0.000 to +0.002.** Mostly generality and wiring; the prior forecast already assumed a functioning contract.

---

### 2. Evidence-role capability registry

**(a) Mechanism.** Extend the existing `SourceAdapterRegistry`, keyed by evidence capability rather than domain. Each data row declares:

```yaml
adapter_id:
evidence_roles:
document_types:
jurisdiction_coverage:
query_dialects:
controlled_vocabulary:
identifier_types:
version_resolvers:
content_profiles:
rate_policy:
authority_features:
```

The router performs set cover over the plan’s required evidence roles and invokes every matching route family. It does not ask the LLM to remember that economists use NBER or clinicians use PubMed.

Representative rows would include PubMed/PMC, ClinicalTrials.gov, Europe PMC, medRxiv, official legislation/court repositories, CourtListener, SSRN, NBER, RePEc, OpenAlex, Semantic Scholar, and generic web discovery. PubMed exposes stable programmatic search and retrieval through E-utilities; ClinicalTrials.gov provides a versioned v2 API. [NCBI E-utilities](https://www.ncbi.nlm.nih.gov/books/NBK25499/), [ClinicalTrials.gov API](https://clinicaltrials.gov/data-about-studies/learn-about-api).

**(b) Clinical.** A trial-effect question requests scholarly studies, systematic reviews, trial registrations, and possibly regulatory records. PubMed/PMC, ClinicalTrials.gov, Europe PMC, and permitted preprint routes fire because their rows advertise those roles. medRxiv stays in the discovery ledger but is ineligible for a peer-reviewed-only answer.

**(c) Legal/comparative.** Binding-authority roles route to jurisdiction-specific official legislation and opinions; secondary scholarship routes to journal indexes and SSRN. Court hierarchy and precedential status remain metadata, not lexical guesses. CourtListener, for example, exposes court, status, citation, opinion type, and related-opinion fields. [CourtListener search fields](https://www.courtlistener.com/help/search-operators/).

**(d) Thin evidence.** Every required role is attempted. Empty returns do not cause fallback to unrelated sources merely to fill a cell.

**(e) Data edits.** Adding a domain that existing adapters can serve is only new rows. Adding a genuinely new API protocol requires one adapter plugin, after which its applicability remains data-driven.

**(f) Silent failure.** `route_complete` must never mean “an adapter was mapped.” It means every planned adapter has an attempt record. HTTP 429/503 is `BACKEND_FAILED`, not “no evidence exists.”

**(g) Task-72 delta.** **+0.002 to +0.006**, mainly through alternate manifestations and relevant scholarly routes. This overlaps heavily with the earlier corpus-expansion forecast.

---

### 3. Coverage-directed, reproducible query families

**(a) Mechanism.** Each coverage atom generates several query families:

1. Direct database search from question terms.
2. Controlled-vocabulary expansion supplied by the adapter row.
3. Backward and forward citation expansion from semantically admitted seeds.
4. Exact title/author searches for alternate versions.
5. Identifier-link expansion across DOI, repository, registry, and publication records.
6. Contradiction, null-result, and alternative-comparator searches.

Every query records its originating atom, renderer, exact text, timestamp, result count, and backend status. Search continues against unresolved atoms until:

- the atom has sufficient independent, directly relevant evidence;
- all applicable route families completed and yielded none;
- marginal new eligible-work yield saturates;
- or a budget/backend boundary is reached and disclosed.

A budget stop is not an evidence gap.

**(b) Clinical.** Use broad, sensitive free-text plus subject-heading searches; do not require an outcome term in every search. Cochrane recommends high-sensitivity searching, multiple databases, free text plus controlled vocabulary, citation searching, and treating studies—not reports—as the unit of interest. [Cochrane Handbook, Chapter 4](https://www.cochrane.org/authors/handbooks-and-manuals/handbook/current/chapter-04).

**(c) Legal/comparative.** Queries use jurisdiction, court, precedential status, citations, statute identifiers, effective dates, and related/citing opinions. Qualitative doctrinal propositions are first-class retrieval targets.

**(d) Thin evidence.** The search stays anchored to the exact combination in the question. It may seek proximate evidence, but proximate evidence is labeled as such and cannot close the direct-evidence atom.

**(e) Data edits.** New controlled vocabularies, query renderers, field names, and citation-expansion capabilities are registry data.

**(f) Silent failure.** Likely shapes are `saturated` after one search engine, `no evidence` after throttling, or query expansion drifting away from the original relationship. Saturation therefore requires route-family completion plus stable work-level marginal yield, and every query must retain its originating atom.

**(g) Task-72 delta.** **+0.004 to +0.009**, principally Depth/Representativeness, Industry Scope, Various Industries, and Balance.

---

### 4. Typed work, version, study, and content identity

**(a) Mechanism.** Replace the single DOI-keyed row with a typed graph:

```text
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
```

Every span binds to its exact `manifestation_id` and content hash. Attribution may name only that manifestation, unless a stronger edge proves that the cited source contains the same span.

For task 72:

- An NBER working paper may lead to the journal article.
- It may be mined for discovery.
- It may not be rendered as a QJE/JEP/AER finding unless the relevant text is verified in the journal version or an authenticated accepted manuscript of that version.
- If only the working paper is available, citing it violates the journal-only instruction, so it stays outside the answer body.

Content status is also typed. Derive `artifact_kind`, sections present, body/chrome ratio, result-bearing sections, extractability, and fetch outcome from the bytes. A universal word threshold cannot define “full text”: a short judicial opinion, statute section, trial-registry record, and journal article have different completeness profiles.

**(b) Clinical.** NCT registry records, protocols, conference abstracts, publications, follow-up papers, and meta-analyses remain distinct. `reports_same_trial` consolidates the study without pretending all reports say the same thing.

**(c) Legal/comparative.** Slip opinions, reporter copies, concurrences, dissents, later procedural history, and amended statutes receive typed identities. A short official opinion is not mislabeled an abstract.

**(d) Thin evidence.** A preprint or registry entry can show that research exists while correctly recording that peer-reviewed results are unavailable.

**(e) Data edits.** Identifier equivalence rules, artifact profiles, authoritative-host rows, and permitted edge types are data. New parsers are code only when a novel file/protocol requires them.

**(f) Silent failure.** The lethal labels are `same_work`, `FULLTEXT`, `journal_evidence`, and `no_free_copy`. Each must expose its derivation. A title similarity match can propose `predecessor_of`; it cannot assert `exact_copy_of`.

**(g) Task-72 delta.** Once version alignment is proven, **+0.001 to +0.004**. Before that, the visible judge scalar could fall because inadmissible working-paper findings disappear. Under the Law that is not a valid regression—the alternative artifact is burned.

---

### 5. Semantic relevance and span-to-coverage binding

**(a) Mechanism.** Replace both `TOPIC_*` and lexical coverage matching with a two-stage semantic process over source-authored content:

1. High-recall BM25/dense retrieval against the question and individual coverage atom.
2. Cross-encoder or constrained LLM verdict: `MATCH`, `NO_MATCH`, or `UNCERTAIN`, with the source span that caused the verdict.

Routing sees title, abstract, and verbatim body span—never the model-written `claim`. A finding may bind to multiple cells, with one primary cell and explicit secondary edges. `UNCERTAIN` remains visible and cannot create either a closed cell or an evidence gap.

Whole-source deletion remains limited to chrome or independently confirmed off-topic material, fail-open on disagreement.

**(b) Clinical.** Findings bind by actual population, intervention, comparator, outcome, design, and endpoint. Null findings and adverse effects are not demoted merely because they oppose the expected direction.

**(c) Legal/comparative.** Holdings, rules, exceptions, authority status, and jurisdiction bind semantically. No numeric-result heuristic fires.

**(d) Thin evidence.** Unrouted or uncertain material is reported as `UNROUTED`/`UNCERTAIN`, not “the literature does not cover this.”

**(e) Data edits.** Coverage-atom descriptions, controlled terms, and adjudication fixtures are data. No domain/topic regex belongs in code.

**(f) Silent failure.** The likely false label is `GAP` when aliases failed to match real evidence—the present `research_contract.py` risk. Every gap must distinguish `SEARCHED_NONE`, `SEARCH_FAILED`, `UNROUTED`, and `THIN`.

**(g) Task-72 delta.** **+0.003 to +0.008**, affecting focus, industry placement, breadth, P1, and critical synthesis.

---

### 6. Multidimensional weighting

**(a) Mechanism.** Never collapse quality into raw citations. Carry this vector:

```text
explicit eligibility
topical relevance
evidentiary directness
methodological quality
source/issuer authority
field-year-type-normalized influence
independence
recency fit
content completeness
marginal coverage contribution
```

Only explicit source constraints, faithfulness, chrome, and confirmed off-topic status are hard gates. Everything else is a weight.

For scholarly influence, use OpenAlex’s `citation_normalized_percentile` or FWCI when available; missing values are `UNKNOWN`, not zero. OpenAlex explicitly field-normalizes by work-level subfield and exposes both FWCI and normalized percentile. [OpenAlex FWCI documentation](https://help.openalex.org/hc/en-us/articles/24735753007895-Field-Weighted-Citation-Impact-FWCI), [Works API](https://developers.openalex.org/api-reference/works).

Do not let influence outrank methodological quality or directness. A famous review cannot displace a direct high-quality study merely because it is famous.

**(b) Clinical.** Risk of bias, design, population/directness, endpoint relevance, and reporting status dominate. A highly cited biased observational paper remains biased; a recent trial is not penalized for lacking citations.

**(c) Legal/comparative.** Bindingness, court hierarchy, jurisdictional fit, current validity, and official text dominate. SSRN scholarship is secondary even if influential. Raw citation count is optional context, not legal authority.

**(d) Thin evidence.** Low-quality or indirect evidence remains visible but yields low certainty. Weighting must never transform weak evidence into “settled.”

**(e) Data edits.** Method-quality rubrics, authority hierarchies, document-type priors, and field-specific feature mappings are versioned rows. The generic vector and comparator remain code.

**(f) Silent failure.** `high_quality` is forbidden as a bare label. It must render as components such as `directness=high`, `method_quality=low`, `influence_percentile=0.92`, with provenance for each.

**(g) Task-72 delta.** **0.000 to +0.003.** Raw citations happen to elevate useful task-72 economics papers, so normalization is mainly mission-critical generality rather than a large task-72 lever.

---

### 7. Coverage allocation, baskets, and thin-evidence stopping

**(a) Mechanism.** Delete the composer’s [`_select()`](/home/polaris/wt/flywheel/scripts/cellcog_composer.py:401) path and do not retain its lexical equivalent in the new planners.

The allocator operates as follows:

1. Bind every admitted finding to coverage atoms semantically.
2. Consolidate equivalent propositions into baskets while retaining every source and every verbatim span.
3. Keep contradictions in separate linked baskets.
4. Assign every basket one primary narrative location.
5. Permit reuse only for a new analytical role—comparison, method boundary, contradiction, implication—not another full narration.
6. Search unresolved cells before outlining them as evidence sections.
7. If context is constrained, map-reduce baskets while retaining all member sources in the composition ledger; do not select a top-\(k\) subset and discard the rest.

Cell status becomes:

```text
UNSEARCHED
SEARCH_FAILED
UNROUTED
SEARCHED_NONE
THIN
SUPPORTED
CONFLICTED
```

Only `SEARCHED_NONE` after adequate route completion supports a scoped absence statement. `CONFLICTED` and `THIN` directly support “the literature does not settle this.”

**(b) Clinical.** Trial reports consolidate at the study level while effect estimates remain endpoint-specific. Meta-analyses, RCTs, harms, and contradictory findings remain distinguishable.

**(c) Legal/comparative.** Allocation operates across issue × jurisdiction × authority. One controlling judgment may legitimately dominate a legal proposition; there is no universal “two sources per cell” rule.

**(d) Thin evidence.** The correct result is an explicit unresolved section supported by the search ledger and the weak/conflicting evidence actually found.

**(e) Data edits.** Closure policies by evidence role and artifact genre are data. The current fixed `MIN_WORKS_PER_CELL=2` cannot be universal.

**(f) Silent failure.** The dangerous outputs are `SUPPORTED` from duplicate reports of one study, `GAP` from failed retrieval, and “consensus” from a basket that silently swallowed contradiction. Independence and contradiction state must be derived before closure.

**(g) Task-72 delta.** **+0.003 to +0.008**, primarily through less repetition, better industry placement, Critical Synthesis, Balance, and P1.

---

### 8. Event-derived labels and adversarial observability

**(a) Mechanism.** Every status is a pure reducer over an append-only event ledger:

```text
route planned
backend attempted
response received / throttled / blocked
candidate identified
manifestation fetched
content profile derived
semantic binding decided
eligibility decided
weight components derived
coverage status derived
```

No component may write `complete`, `fulltext`, `no evidence`, `same work`, or `high quality` directly.

**(b) Clinical.** The ledger exposes searched databases, exact queries, trial/publication linkage, and incomplete outcome reporting.

**(c) Legal/comparative.** It exposes jurisdiction coverage, official-versus-secondary authority, precedential status, and version/effective-date handling.

**(d) Thin evidence.** It distinguishes a substantive negative result from backend failure, inaccessible material, budget exhaustion, and genuinely sparse literature.

**(e) Data edits.** New domain canaries and expected label derivations are fixtures/data. Core reducer logic remains unchanged.

**(f) Silent failure.** Canary attacks must include: 429 rendered as “no copy,” abstract rendered as full text, predecessor rendered as journal version, duplicate reports counted as independent studies, lexical miss rendered as a gap, and a legal source rejected for lacking numbers.

**(g) Task-72 delta.** **0.000.** Mission-critical and validity-critical.

## What to keep and what to replace

- Keep the pure-function idea and useful schema in [`research_contract.py`](/home/polaris/wt/flywheel/scripts/research_contract.py:439), but make it an adapter over the one canonical plan. Its lexical matcher may generate candidates; it may not close cells.
- Retire [`journal_corpus_build.py`](/home/polaris/wt/flywheel/scripts/journal_corpus_build.py:66) from the live path. Keep it only as a task-72 replay fixture.
- Keep `wp_fetch.py`’s retry and fetch mechanics, but source ordering must come from manifestation-resolver rows. It must never overwrite bibliographic identity.
- Reuse the existing EvidenceNeed registry, WRRF, semantic relevance judge, and authority infrastructure.
- Replace the global fixed citation anchors in `scholarly_weights.yaml` with OpenAlex’s field/year/type normalization when available.
- Replace `_select()` and every downstream lexical clone with the semantic binder and global basket allocator.

The component deltas above are deliberately non-additive. Their combined retrieval/selection contribution on task 72 is approximately **+0.010 to +0.018**, but most of that is the implementation of the earlier **+0.010 to +0.015 coverage-expansion lever**, not a new gain to stack on top of it.

## Measurement

Use two separate ladders:

1. Freeze a candidate universe and compare only semantic binding, weighting, baskets, and allocation. This isolates selection changes.
2. Freeze code and run fresh retrieval on a multi-domain set: clinical, legal/comparative, thin-evidence, and unrelated holdouts. This measures routing and recall.

For task 72, retain the cumulative A0→A3 ladder over one frozen evidence snapshot. Decide by criterion movement and complete regression enumeration, not scalar alone. For the generality suite, measure false-gap rate, relevant-primary-work recall, version-binding accuracy, route-attempt honesty, contradiction retention, and whether the thin-evidence conclusion is correct.

## Revised landing estimate

Generalizing retrieval does not itself justify raising the task-72 estimate. It is the correct implementation of a lever already in the forecast.

More importantly, I cannot presently credit the recovered working-paper bodies as journal evidence. They are stored under journal attribution without span-level version alignment. Therefore, as the artifact stands, the weaker corpus wins.

My conditional forecast is:

- **Current unaligned corpus:** **0.49–0.52** valid landing.
- **After journal/accepted-manuscript alignment proves the recovered spans:** restore **0.50–0.53**, with **~0.54** still an upside case.
- **0.5603 remains unsupported.**

If alignment succeeds, the canonical papers win narrowly over the corpus-count loss because they improve Depth/Representativeness, D1, mechanisms, and comparative synthesis. They still do not by themselves solve industry breadth, 4IR integration, or the research agenda. The likely center moves upward only a few thousandths—below the stated resolvable effect—so I would not advertise a forecast increase until the criterion ledger measures it.