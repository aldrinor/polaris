## Decision

Stop release. Preserve the acquired bytes, quarantine every unbound derived artifact, and rebuild the publishable cards from typed manifestations.

The enforcement point must be the final artifact writer—not another optional preflight. A report must be impossible to publish unless every attributed sentence resolves through:

`sentence → card → bound span → manifestation_id + content_hash → permitted expression → exact attribution`

I audited clean commit `4dccd15291d00dd2ff2273aa81347c943c91bb93`. I made no changes.

### Reality checks on the two modules

Their central ideas are right, but they are not wire-ready unchanged:

- [provenance.py](/home/polaris/wt/flywheel/scripts/provenance.py:482) correctly restricts attribution through asserted span-preserving edges, and [bind_span()](/home/polaris/wt/flywheel/scripts/provenance.py:517) returns the required manifestation/hash binding.
- But `bind_span()` does not validate bounds, returns attribution strings rather than target expression IDs, and [migrate()](/home/polaris/wt/flywheel/scripts/provenance.py:571) assumes every corpus row represents a journal expression. That is not valid for a judicial opinion or statute.
- [event_ledger.py](/home/polaris/wt/flywheel/scripts/event_ledger.py:166) has the right event/reducer separation.
- But [derive_content_profile()](/home/polaris/wt/flywheel/scripts/event_ledger.py:382) reinstates a universal `FULLTEXT_MIN = 2500` at line 372, contradicting both generality and `provenance.profile()`. Its `Ledger` also does not reload persisted JSONL, so each standalone script starts with an empty in-memory history.

Wire the primitives only after those adapter defects are corrected.

## (a) Exact critical-path wiring

### 1. Acquisition: all fetchers write observations and manifestations, never statuses

The run orchestrator creates one durable ledger before retrieval. These sites must emit into it:

- [journal_corpus_fetch.get_json()/get_text()](/home/polaris/wt/flywheel/scripts/journal_corpus_fetch.py:34)
- [deep_fetch.jget()/fetch_text()](/home/polaris/wt/flywheel/scripts/deep_fetch.py:34)
- [wp_fetch.polite_get()](/home/polaris/wt/flywheel/scripts/wp_fetch.py:69)
- [version_align.polite()/fetch_doc()](/home/polaris/wt/flywheel/scripts/version_align.py:75)

Exact event sequence per requested work:

1. `ROUTE_PLANNED` in each fetcher’s `main()` before its adapter loop.
2. `BACKEND_ATTEMPTED` immediately before each network request.
3. At the exception boundary, emit exactly one of:
   - `RESPONSE_RECEIVED`
   - `THROTTLED`
   - `BLOCKED`
4. `CANDIDATE_IDENTIFIED` when a URL/result is returned.
5. `MANIFESTATION_FETCHED` after bytes are obtained, including locator, immutable blob ID, byte hash, requested identity, and adapter observations.
6. `CONTENT_PROFILE_DERIVED` only from a shared artifact-profile reducer.

A 429 therefore persists as `THROTTLED → BACKEND_FAILED`; it cannot become `CITATION_ONLY`.

`content_status`, `fulltext_source`, and “still paywalled” must disappear from fetcher writes. [deep_fetch.py:127-137](/home/polaris/wt/flywheel/scripts/deep_fetch.py:127), [wp_fetch.py:211-224](/home/polaris/wt/flywheel/scripts/wp_fetch.py:211), and [journal_corpus_fetch.py:103-110](/home/polaris/wt/flywheel/scripts/journal_corpus_fetch.py:103) currently write those conclusions directly.

`merge_corpus.py` must merge event streams and immutable manifestations. It must stop choosing a winner by text length and claimed status at [lines 47-54](/home/polaris/wt/flywheel/scripts/merge_corpus.py:47).

### 2. Provenance construction: between acquisition and mining

After every acquisition batch, a single reducer builds or extends the typed graph:

- Work/evidence-unit
- Expression/version
- Manifestation/bytes
- Evidenced edges

Artifact type and completeness must come from one shared registry-driven reducer. Delete the second, conflicting 2,500-word implementation in `event_ledger.py`.

The graph must be persistently loadable. Add a strict `Graph.from_json()` and make loading validate:

- Hash equals manifestation text.
- Expression and work references exist.
- Edge endpoints and bases exist.
- Span-preserving asserted edges meet their authentication requirements.

The graph should expose:

```text
bind_span(manifestation_id, start, end)
resolve_attribution(manifestation_id, source_policy)
verify_span(binding)
```

`bind_span()` must reject negative, reversed, and out-of-range offsets. Its result must include `expression_id` and permitted target expression IDs, not merely human-readable `may_name` strings.

### 3. Mining: bind at card construction, not afterward

The critical call site is [evidence_miner.gate_card()](/home/polaris/wt/flywheel/scripts/evidence_miner.py:1060), immediately after `s_start/s_end` round-trip successfully.

Replace the copied row attribution at [lines 1195-1196](/home/polaris/wt/flywheel/scripts/evidence_miner.py:1195) with:

1. `binding = graph.bind_span(paper.manifestation_id, s_start, s_end)`
2. `target = graph.resolve_attribution(manifestation_id, contract.source_policy)`
3. Reject and count `source_policy_inadmissible` if no target exists.
4. Store:

```text
work_id / evidence_unit_id
expression_id
attribution_target_expression_id
manifestation_id
content_hash
span_start
span_end
span
attribution
```

Every `corroborating_sources` entry created in [consolidate()](/home/polaris/wt/flywheel/scripts/evidence_miner.py:1400) must carry the same complete binding.

[evidence_miner.mine()](/home/polaris/wt/flywheel/scripts/evidence_miner.py:1575) must select manifestations from the graph and reducers. It must not trust the flat `content_status != CITATION_ONLY` predicate at line 1580.

### 4. Coverage and study independence

[coverage_matrix()](/home/polaris/wt/flywheel/scripts/research_contract.py:751) must consume both the graph and ledger.

Replace `Cell.n_works = len(dois)` at [line 719](/home/polaris/wt/flywheel/scripts/research_contract.py:719) with distinct independent evidence-unit families:

- Scientific/clinical: distinct studies/trials, not reports or DOIs.
- Legal: distinct decisions; duplicate reporters of one decision count once, while appellate and lower-court opinions remain separate related authorities.
- Comparative/doctrinal: distinct authoritative instruments or decisions as specified by the contract.

For Acemoglu–Restrepo, the working paper and JPE article remain two expressions of one study. The journal article of record is the task-72 evidence; 0.37 versus 0.2 is a version change, not cross-study conflict or corroboration.

Only `derive_coverage_status()` may license an absence sentence:

- `SEARCHED_NONE`: scoped absence may be stated.
- `THIN` or `CONFLICTED`: “the literature does not settle this.”
- `UNROUTED`, `UNSEARCHED`, or `SEARCH_FAILED`: pipeline limitation, never literature absence.

### 5. Composition: one card lane and one publisher

There are currently two disconnected card lanes:

- The new miner writes `evidence_cards_v2.json` at [evidence_miner.py:80](/home/polaris/wt/flywheel/scripts/evidence_miner.py:80).
- The composer reads old `evidence_cards.json` at [cellcog_composer.py:53](/home/polaris/wt/flywheel/scripts/cellcog_composer.py:53).

That seam must be removed. The composer accepts one explicit card-bundle path plus its graph and ledger hashes.

Before any LLM call, `write_report()` must reverify every primary and corroborating binding. Then:

- `_fmt_cards()` refuses unbound cards.
- `_gate_attributed()` first calls `graph.verify_span(binding)` and verifies the chosen attribution target.
- `_evidence_table()` rechecks bindings too.
- Attribution is rendered programmatically from the selected expression; the model does not invent or copy it.
- Generated output is structured as `ATTRIBUTED(card_ids, body)` or `OWNED(premise_ids, body)`. Do not infer voice or source identity from surnames as `_cited_cards()` currently does.
- All abstract, methods, table, and conclusion sentences pass through the same typed report AST. The current hand-written abstract at [write_report()](/home/polaris/wt/flywheel/scripts/cellcog_composer.py:709) cannot bypass the law.
- [report.md write_text](/home/polaris/wt/flywheel/scripts/cellcog_composer.py:775) moves into a sole publisher. It writes atomically only after validating the entire report AST and generating a sentence-hash-to-binding sidecar.

## (b) A test that cannot certify the wrong lane

The test must attack the production release boundary, not import a gate or inspect an AST.

Create an end-to-end release test that launches the real production command in a sealed temporary run directory. Its fixture contains:

- Working-paper bytes under journal metadata.
- A landing page carrying genuine article phrases.
- A correct journal manifestation.
- A card with no `manifestation_id`.
- A card with the wrong hash.
- A card with a valid hash but impermissible journal attribution.
- An owned sentence carrying a new particular.
- A valid positive control.

Assertions:

1. Missing ID, wrong hash, invalid target, or contaminated manifestation causes nonzero exit and no released `report.md`.
2. The WP span cannot appear under the journal attribution.
3. The correct journal span does reach the released artifact.
4. Every attributed sentence in the released file has a sidecar binding that independently re-verifies against the immutable manifestation store.
5. Reopening the released file—not an intermediate variable—shows the attack text absent.
6. The report cannot be released without coverage derivations for every claimed gap.

To make this structurally unavoidable:

- Composers may write only drafts.
- Only the publisher process has filesystem permission to create files in the judged release directory.
- CI asserts that all benchmark and submission commands consume that directory.
- The attack runs the same submission command used for scoring.

The present canary at [test_gate_is_wired.py](/home/polaris/wt/flywheel/scripts/test_gate_is_wired.py:47) checks that `validate()` is called and tests selected composer phrasings. It is useful unit coverage, but it cannot prove release integrity.

Expected task-72 scalar delta: `0.000`. Mission-critical.

## (c) Replace “numbers first” with typed evidence acts

Do not delete the quantitative extractor. Make it one evidence-act schema alongside others:

- `quantitative_estimate`
- `qualitative_empirical_result`
- `doctrinal_holding_or_rule`
- `recommendation_or_guidance`
- `null_or_inconclusive_result`
- `methodological_limitation`
- `forecast_or_projection`

The names and required fields belong in a versioned data registry. The extraction code generically:

1. Examines every evidence-bearing block.
2. Proposes typed evidence acts.
3. Locates and stores the complete source slice.
4. Applies the schema’s required-field rules.
5. Records every rejection and every block yielding no act.

One correction to the adversary’s phrasing: `harvest()` is not literally the only path seen by the LLM; [mine_paper()](/home/polaris/wt/flywheel/scripts/evidence_miner.py:1472) sends every positive-weight chunk to the model. But the outcome is still fatal because [MINE_PROMPT](/home/polaris/wt/flywheel/scripts/evidence_miner.py:1254) requests quantitative tuples and `gate_card()` rejects qualitative material without an `outcome`. The no-digit harvester also makes its telemetry falsely report zero candidates.

D1 should not fall. The existing quantitative schema, full-document scan, numeric gates, and evidence table remain intact. Qualitative acts are additive and cannot displace quantitative acts through a fixed cap.

Because D1 has weight 0.014, even moving it from 5.90 to 10.00 can add only about `+0.0057` scalar. My expected task-72 effect from this extractor change alone is `0.000 to +0.006`; below the paired resolvability threshold. On a legal question, the effect is existential rather than scalar.

## (d) Quarantine, do not purge

Purging destroys the audit trail. Re-attributing everything is unsafe. Use selective deterministic rebinding:

1. Freeze and hash the present corpus, cards, report, graph, and logs as contaminated legacy artifacts.
2. Quarantine the current released report and all old `evidence_cards.json` cards. They lack sufficient binding information.
3. For each v2 card, attempt a unique rebind using:
   - DOI/work candidate
   - `source_version`
   - raw offsets
   - exact span
4. If exactly one manifestation matches, call `bind_span()`.
5. Apply the question’s source policy:
   - Journal manifestation: retain and reattribute from the graph.
   - Working paper/preprint: discovery lead; excluded from task 72.
   - Landing page, wrong work, extraction failure: quarantine.
   - Unresolved version: quarantine until identity is proven.
6. Rebind corroborating sources independently.
7. Collapse expressions into evidence-unit families before consolidation and coverage.
8. Re-mine only:
   - admissible manifestations without surviving cards;
   - newly recovered article-of-record manifestations;
   - quarantined high-priority works once correct bytes arrive.

Specific outcomes:

- Frey & Osborne’s ORA page is quarantined immediately. Its four cards do not survive.
- The six journal-labelled working-paper manifestations lose journal attribution.
- The Acemoglu–Restrepo 0.37 card is excluded from the journal-only answer. The JPE article must be mined for 0.2/0.42.
- Existing bytes are retained for discovery and audit.
- A 429 leaves the work in `SEARCH_FAILED`, eligible for retry; it does not become a permanent exclusion.

Immediate task-72 score effect is likely `-0.015 to -0.005`, because invalid but useful-looking evidence disappears. After article-of-record recovery and re-mining, corpus repair could recover `0.000 to +0.010`. These are separate ladder arms, not additive forecasts.

## Remaining new findings

### Duplicate study reports

Use graph-derived evidence-unit families in `consolidate()` and coverage. Same-study version changes are retained as version history but count as one independent study. Never interpret differing versions as literature disagreement.

Expected task-72 delta: `-0.003 to 0.000`; mission-critical correctness.

### Wage matcher

Do not add “wage” to a task-specific regex. Change `build_matchers()` generically:

- Shared stems produce an ambiguous candidate set; they are not discarded.
- Contract definitions and span context perform a semantic second-stage assignment.
- Unresolved assignments become `AMBIGUOUS/UNROUTED`, never `GAP`.
- Coverage cannot close or declare absence while relevant cards remain unrouted.

Aliases, concept definitions, and relations such as “earnings/remuneration/pay” are data edits in the generated contract, not code edits.

Expected task-72 delta: `0.000 to +0.004`.

### Judicial opinion

The opinion becomes a `doctrinal_holding_or_rule` card whose evidence is the holding’s verbatim span. Its completeness is assessed under the judicial-opinion artifact profile, with no word floor and no numeric requirement.

Expected task-72 delta: exactly `0.000`; mission-critical for the stated mission.

## Generality matrix

| Mechanism | Clinical behavior | Legal/comparative behavior | Thin-evidence behavior | Domain change is a data edit when… | Silent-failure mode and required response | Task-72 scalar |
|---|---|---|---|---|---|---:|
| Event-ledger acquisition | PubMed/registry 429 becomes `SEARCH_FAILED`, not “no trial” | Court/repository failure becomes retrieval failure, not doctrinal absence | Incomplete routes prohibit absence claims | Adding adapters, route plans, or artifact profiles | Missing terminal event leaves `UNSEARCHED`; publishable gaps are blocked | `0.000` frozen corpus |
| Manifestation-bound provenance | Trial report, protocol, preprint and article remain separate expressions | A short opinion is complete; duplicate reporter copies can share one decision expression | Unresolved version is disclosed and excluded, not silently promoted | Adding source types, expression kinds, permitted relations | Any absent/mismatched ID/hash aborts release | `-0.015 to 0.000` initially |
| Release-boundary attack | Protocol result cannot be credited to the results article | Landing page cannot be credited to the court or journal | No proof means no artifact | Adding fixtures for new artifact classes | Alternate writer is prevented by release-directory permissions | `0.000` |
| Typed evidence acts | Preserves effects, CIs, harms, null results and qualitative safety findings | Extracts holdings, rules, reasoning and comparisons without digits | Null, conflicting and inconclusive findings become evidence acts | Adding/changing schemas and required fields | Every block and rejection is counted; unexplained zero-yield blocks fail audit | `0.000 to +0.006` |
| Evidence-unit families | Registry, preprint and publication count as one trial unless distinct analyses are proven | Duplicate reporters count once; appellate decisions remain distinct related authorities | One family stays `THIN`, however many expressions it has | Adding asserted relation rows | Unresolved possible duplication is disclosed and conservatively not counted as independence | `-0.003 to 0.000` |
| Semantic routing with tri-state outcomes | “overall survival” can route despite vocabulary variation | “duty,” “burden,” and “standard” route from contract definitions | Unrouted evidence blocks absence language | Editing term definitions, aliases and ontology relations | `UNROUTED/AMBIGUOUS` is visible in artifact and blocks false gaps | `0.000 to +0.004` |
| Quarantine and selective rebind | Preserves raw trial records while discarding invalid cards | Preserves opinions and landing pages as distinct artifacts | Corpus shrinkage is disclosed, not rendered as literature silence | Adding corrected manifestations or asserted relations | Rebind failures produce a quarantine manifest; no implicit deletion | `-0.015 to -0.005` before recovery |

## (e) Landing estimate

Yes, the estimate changes.

Under the law, the currently contaminated artifact scores `0.00` regardless of its judge scalar. For the next defensible artifact:

- Immediate rebuild from currently admissible bytes, before article-of-record recovery: `0.45–0.49`.
- After recovering and re-mining the missing journal manifestations: `0.48–0.52`.
- The prior `0.49–0.53` is now a recovery-conditional upside range, not the base landing range.
- `0.5603` remains unsupported.

No scalar improvement should be forecast from wiring or the canary. Their value is that the next measured score describes a real artifact.