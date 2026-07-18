# Build plan: evidence-card corpus audit

The audit will be a fail-closed, resumable offline workflow. Every serialized card receives deterministic verification and an independent Opus semantic audit. Every ATTRIBUTED card—currently all `evidence_cards_v2` records—receives two independent Opus passes. High-risk cases and disagreements receive a third adjudication. Nothing enters the composer unless every applicable dimension passes after any repair.

One critical repo finding must be handled first: the current miner can consolidate unrelated qualitative cards as “corroboration,” omit binding fields from those nested records, and create duplicate card IDs. The audit cannot recover claims already erased by lossy consolidation. Phase 0 therefore includes an auditability gate and a mandatory replay branch if the final artifact exhibits that loss.

## 1. Non-negotiable architecture

Use these existing enforcement points:

- Faithfulness: [`report_ast.entailed_by_span()`](/home/polaris/wt/flywheel/scripts/report_ast.py:1106).
- Card-to-binding adapter: [`report_ast._binding_from_card()`](/home/polaris/wt/flywheel/scripts/report_ast.py:199).
- Binding verification: [`Graph.verify_span()`](/home/polaris/wt/flywheel/scripts/provenance.py:1454).
- Binding-specific source-policy resolution: [`Graph.resolve_attribution(binding, policy)`](/home/polaris/wt/flywheel/scripts/provenance.py:1311).
- Whole critical path: [`CardBundle.resolve()`](/home/polaris/wt/flywheel/scripts/report_ast.py:356).
- Typed OWNED validation: [`report_ast.validate_node()`](/home/polaris/wt/flywheel/scripts/report_ast.py:1493).
- Card claim reconstruction: [`evidence_miner.derive_claim()`](/home/polaris/wt/flywheel/scripts/evidence_miner.py:1254).
- Act rules: [`config/evidence_acts.json`](/home/polaris/wt/flywheel/config/evidence_acts.json).
- Atomic artifact pattern: [`publisher._atomic_write()`](/home/polaris/wt/flywheel/scripts/publisher.py:108).

Do not use legacy [`scripts/quarantine.py`](/home/polaris/wt/flywheel/scripts/quarantine.py). It hardcodes journal-only policy and resolves manifestation-wide rather than binding-specific.

The workflow follows an audit-then-adjudicate pattern: a failure or disagreement must carry exact evidence and can be revised only through an explicit adjudication/repair record. This is consistent with the 2026 DeepFact “Audit-then-Score” finding that difficult factuality labels become more reliable through evidence-backed challenge and adjudication rather than one-shot judgment. [DeepFact, ACL 2026](https://aclanthology.org/2026.acl-long.1586/)

## 2. Exact per-card pass/fail contract

Use four verdict values internally:

- `PASS`
- `FAIL`
- `UNCERTAIN`
- `NOT_APPLICABLE`

No `UNCERTAIN` may appear in the composer-facing set.

### Faithfulness

For each top-level card and each claimed corroborating support edge:

1. Resolve the exact raw binding.
2. Obtain `resolved_span = manifestation.text[span_start:span_end]`.
3. Normalize the claim exactly as the composer does: HTML-unescape, collapse whitespace, strip only a final period.
4. Call:

```python
report_ast.entailed_by_span(
    normalized_claim,
    resolved_span,
    graph.works[manifestation.work_id],
)
```

Pass only if the result is `(True, "")` or equivalent successful return.

Precise rules:

- `ATTRIBUTED`: every factual atom must be entailed by its own bound span.
- `OWNED`: not tested for source entailment, but must pass the report-AST OWNED gate and carry no new particular.
- A corroborating span must independently entail the primary claim. It never inherits the primary card’s pass.
- `NOT_ENTAILED`, `UNCERTAIN`, transport failure, malformed judge output, or missing span means `FAIL`.
- A report-AST failure cannot be overridden by an Opus opinion. The card must be repaired and rerun.
- Never test against `card["span"]`, concatenated metadata, wider context, another source, or a corroboration basket. Use only verified `span_raw` bytes.
- Never concatenate `span + claim`; that recreates evidence laundering.

### CoT contamination

This is a positive structural test, not a blacklist of phrases.

Every non-empty string field must be classified into exactly one allowed provenance class:

- `SOURCE_BYTES`: exact verified source substring, such as `span_raw`.
- `CANONICAL_SOURCE_VIEW`: deterministic normalization of verified source bytes, such as `span`.
- `DERIVED_CACHE`: byte-for-byte recomputable from audited fields, such as `claim`.
- `GRAPH_METADATA`: exactly matches live Work/Expression/Manifestation metadata.
- `REGISTRY_VALUE`: member of an allowed closed vocabulary.
- `ATOMIC_EVIDENCE_VALUE`: concise extracted value semantically supported by its declared source window.
- `EMPTY`.

Fail if any string is:

- process narration;
- model self-talk;
- instructions to itself or another model;
- analysis of how to answer;
- candidate enumeration or abandoned alternatives;
- confidence commentary;
- JSON/prompt scaffolding;
- an unclassified free-text field;
- a derived cache that does not exactly recompute.

Opus must return a content class for every non-empty auditable field. Absence of suspicious phrases is never sufficient.

A source span that itself says “we reason…” remains `SOURCE_BYTES`; that is author prose, not leaked miner CoT. If apparent CoT text cannot be proven to be source bytes, it fails.

### Numeric fidelity

Run both report-AST mechanical checks and an Opus atom-level comparison.

All subdimensions must pass:

- `number`: same canonical number, including sign and decimal precision.
- `direction`: rose/fell, positive/negative, increase/decrease unchanged.
- `magnitude`: no doubled/halved/substantial/majority or similar inflation.
- `unit`: percent and percentage points remain distinct; currency, rate, time, and denominator preserved.
- `comparator`: baseline, control group, “per,” “relative to,” and reference category preserved.
- `population`: no widening from subgroup to all people/firms/studies.
- `geography`: no local-to-global widening.
- `period`: dates, follow-up interval, forecast horizon, and temporal qualifiers preserved.
- `scope`: technology, industry, unit of analysis, outcome, and conditions preserved.
- `uncertainty`: confidence interval, p-value, approximation, “at least,” “up to,” null result, mixed result, and exceptions preserved.
- `modality`: association is not upgraded to causation; forecast is not rendered as observation.
- `precision`: claim may not add digits, remove uncertainty, or invent exactness.

Any failed atom means the dimension fails. A mechanical pass is never an admission; semantic judgment remains required.

### Relevance and facet correctness

The audit must use the exact pinned research question and frozen compiled contract.

Pass relevance only when Opus classifies the card as:

- `DIRECT_ANSWER_EVIDENCE`, or
- `NECESSARY_CONTEXT` with a specific connection to the research question.

Fail:

- merely adjacent subject matter;
- generic filler;
- evidence useful to a different question;
- source metadata or methods with no role in answering the question;
- a span whose only relevant content exists outside its binding.

Facet rules:

- Every existing `facet_tags_span` value must be supported by the span.
- Context-derived tags must be supported by the declared context window.
- Every tag must exist in the pinned contract taxonomy.
- A relevant card with incorrect tags is repairable by retagging.
- A semantically off-topic card is quarantined; its source remains in the corpus.
- If the question or exact contract cannot be pinned, the audit stops. It must not invent a fallback topic.

### Structure and binding

Pass only if all are true:

- JSON type and closed schema are valid.
- Required fields exist and have valid types.
- `id` is non-empty and globally unique in the clean set.
- `manifestation_id`, hash, offsets, and `span_raw` pass `Graph.verify_span`.
- Stored `permitted_expression_ids` exactly equal the live per-span set.
- Binding-specific `resolve_attribution(binding, derived_policy)` admits.
- Stored `attribution_target_expression_id` equals the live target.
- `expression_id == manifestation.expression_id`.
- `work_id == evidence_unit_id == manifestation.work_id`.
- Stored source policy equals the policy re-derived from the original question.
- The manifestation’s `semantic_binding` is in `IDENTITY_PROVEN`.
- The `(semantic_binding, expression_kind)` pair is in `COMPATIBLE_VERSION_PAIRS`.
- Work DOI/authors/year/venue caches agree with live graph metadata.
- `source_version`, `text_field`, aliases, and normalized span agree with live values.
- `act` exists in the pinned act registry and required/allowed fields comply.
- `claim == derive_claim(card, act)` after canonical normalization.
- `has_number`, `span_numbers`, `complete_tuple`, aliases, and source counts recompute exactly.
- Every nested corroborator has a complete independent binding.
- `n_sources` and `n_evidence_units` equal verified independent evidence units, not stored counts.

Unknown fields fail schema validation until explicitly added to the schema.

### Voice

The current v2 schema has no voice field. Therefore:

- Every incoming v2 evidence card is normalized as `ATTRIBUTED`.
- A failing card must never be silently reinterpreted as `OWNED`.
- `card_kind` is not voice.
- Only an explicit repair disposition can create an OWNED suggestion, and it is not citeable evidence.

## 3. Tiering and Opus coverage

### Tier 0: deterministic screen on everything

Run on:

- every top-level record;
- every primary binding;
- every `corroborating_sources` entry;
- every `same_unit_other_expressions` entry for structure, though these do not support the claim;
- every non-empty card field.

This handles byte hashes, offsets, schema, caches, numeric token checks, duplicate IDs, source-policy resolution, and registry consistency.

### Tier 1: first Opus pass on every card

Every top-level card receives a complete Opus judgment covering:

- faithfulness;
- CoT content classes for every field;
- numeric atoms;
- relevance;
- facet correctness;
- proposed disposition.

Every primary and corroborating claim/span pair is examined. Structurally unreachable cards still receive the remaining semantic judgments; their faithfulness verdict is `UNREACHABLE`.

There is no sample-only lane.

### Tier 2: second independent Opus pass

Run in a fresh context with no access to the first verdict for:

- every ATTRIBUTED card;
- every numeric card;
- every low-corroboration card;
- every card with a non-span field used in its claim;
- forecasts, recommendations, null results, limitations, mixed findings, and third-party attribution cues;
- every report-AST failure or uncertainty;
- every card flagged for CoT, relevance, facet, or numeric risk.

Since the current v2 corpus is entirely ATTRIBUTED, all current cards receive two independent Opus passes.

### Tier 3: adjudication

A third Opus agent receives the card, exact source bytes, deterministic receipt, report-AST result, and both independent Opus verdicts when:

- the Opus passes disagree;
- either Opus pass fails;
- report-AST passes but Opus alleges an unsupported atom;
- a repair is proposed;
- a support edge is proposed for removal;
- a card is proposed for OWNED demotion.

The adjudicator must identify the deciding source substring and atom. It may resolve an Opus false positive, but it cannot override a failed byte binding or failed `entailed_by_span`. Those require a new repaired card and a complete rerun.

### Efficient execution

Configure, do not hardcode:

- first-pass packets: token-bounded to approximately 12,000 input tokens and at most 16 cards;
- second-pass packets: at most 8 cards;
- adjudication and repair: one card per packet;
- default concurrency: 24 Opus worker processes;
- maximum retries: 3, same model only;
- no fallback to Sonnet, Haiku, GLM, or a deterministic “pass.”

The orchestrator bin-packs by actual serialized length so long spans or large corroboration sets receive smaller batches.

Use fresh `claude -p` sessions with:

```text
--model opus
--effort max
--permission-mode dontAsk
--output-format json
--json-schema <audit schema>
```

Workers get read-only, self-contained packets and no Agent, Bash, Edit, Write, web, or task-spawning tools. Require response metadata to prove the requested model was used.

Opus output must be short structured receipts, not its reasoning trace.

## 4. Disposition rules

Never delete silently. Every input row and support edge gets exactly one final disposition.

### `KEEP_UNCHANGED`

All applicable dimensions pass.

### `REPAIR_TIGHTEN`

Allowed when the span supports a narrower claim.

Examples:

- delete an unsupported magnitude adjective;
- narrow population or geography;
- restore uncertainty;
- correct an optional tuple field;
- remove a contaminated optional field;
- correct facet tags.

Rules:

1. Repair agent proposes typed field changes, not arbitrary replacement prose.
2. Source bytes, hash, manifestation, and offsets remain immutable.
3. Recompute the claim using `derive_claim`; do not accept model-written claim prose.
4. Rerun every deterministic dimension.
5. Rerun report-AST entailment.
6. Require two fresh Opus passes.
7. Record before/after hashes and exact changed fields.
8. Original remains in the lineage ledger as `SUPERSEDED`.

### `REBASE_TO_VALID_SUPPORT`

If the primary span fails but a corroborating source independently supports the claim:

- rebuild a complete binding from that source’s graph bytes;
- make it the primary;
- issue a collision-safe card ID;
- recompute attribution and counts;
- rerun all dimensions.

Never merely swap the attribution string.

### `REMOVE_BAD_SUPPORT_EDGE`

If the primary card passes but one corroborator does not:

- retain the primary card;
- move the bad edge into quarantine with its reason;
- recompute `n_sources` and `n_evidence_units`;
- rerun low-corroboration/risk classification.

The disappearance must be counted as a repair, never hidden.

### `DEMOTE_TO_OWNED_SUGGESTION`

Sound only when the replacement:

- contains no number, named source, unsupported entity, magnitude, particular population, or source-specific finding;
- is a genuine frame, transition, or proof-carrying synthesis;
- for synthesis, names at least two passing premise IDs;
- passes `report_ast.validate_node(Owned(...), bundle)`.

An overclaimed numerical magnitude cannot be demoted while retaining the number. It must be tightened or quarantined.

Because evidence cards are citeable ATTRIBUTED objects, demoted material moves to `owned_suggestions.json`; it does not remain in `audited_cards.json`. This preserves it without laundering it through the evidence lane.

### `QUARANTINE_CARD`

Required for:

- invalid or unverifiable binding;
- unresolved or wrong identity;
- inadmissible expression under the derived source policy;
- no entailed repair;
- unremovable CoT contamination in a required field;
- numeric contradiction;
- off-topic card;
- irreparable schema ambiguity;
- duplicate-ID collision that cannot be safely re-ID’d;
- consolidation information loss.

### `QUARANTINE_SUPPORT_EDGE`

Used for false corroboration or incomplete nested bindings when the primary remains valid.

There is no `DELETE` disposition.

## 5. Agent-executable phased implementation

## Phase 0 — Freeze the completed mine and prove auditability

Files:

- New: `scripts/evidence_card_audit.py`
- New: `src/schemas/evidence_card_audit.py`
- Modify when necessary: [`scripts/evidence_miner.py`](/home/polaris/wt/flywheel/scripts/evidence_miner.py:3151)
- Inputs:
  - `outputs/evidence_cards_v2.json`
  - `outputs/evidence_cards_v2.meta.json`
  - `outputs/evidence_cards_v2.quarantine.json`
  - `outputs/journal_corpus_content.json`
  - `outputs/provenance_graph.json`
  - exact contract under `outputs/contracts/`
  - `outputs/event_ledger.jsonl`
  - `config/evidence_acts.json`

Exact steps:

1. Wait for the miner process to exit successfully. Do not infer completion from file existence; the current on-disk 521-card file is stale until `mine()` returns.
2. Read each input twice and require identical SHA-256 values.
3. Copy inputs into:

```text
outputs/audits/evidence_cards/<cards_sha>/inputs/
```

4. Write `input_manifest.json` containing:
   - absolute original paths;
   - size and SHA-256;
   - card count;
   - git commit;
   - question;
   - exact source policy;
   - exact contract path/hash;
   - graph hash;
   - corpus hash;
   - act-registry hash/version.
5. Strict-load the graph with `Graph.from_json`.
6. Re-derive policy from `meta.question`; compare with metadata and every card.
7. Pin the exact cached research contract. Do not recompile it.
8. Reconstruct the graph from the pinned corpus if the miner did not persist its exact graph. Require every card binding to verify against the chosen graph.
9. Enumerate top-level rows by `audit_row_id = sha256(input_sha + JSON pointer + canonical row JSON)` so duplicate card IDs cannot hide records.
10. Enumerate every nested support edge separately.
11. Test for:
    - duplicate card IDs;
    - unrelated qualitative records merged as corroboration;
    - nested corroborators missing `span_raw` or permitted IDs;
    - raw-card information loss;
    - mismatch between `cards_pre_consolidation` and serialized accounting.

Acceptance:

- `input_manifest.json` is complete and immutable.
- All top-level rows and nested edges have stable audit IDs.
- Graph and contract are uniquely pinned.
- No input changes after snapshot.
- Auditability status is `PASS`.

### Mandatory Phase 0R branch — repair lossy miner serialization

Enter this branch if unrelated qualitative consolidation or unrecoverable nested cards are found.

Modify [`scripts/evidence_miner.py`](/home/polaris/wt/flywheel/scripts/evidence_miner.py):

1. Write `evidence_cards_v2.raw.jsonl` atomically before consolidation.
2. Make qualitative `finding_key()` include:
   - act;
   - canonical primary content field (`finding`, `holding`, `recommendation`, or `limitation`);
   - outcome/scope where applicable.
3. Make IDs include a stable act/claim hash in addition to binding coordinates.
4. Extend `_binding_of()` to preserve complete binding fields plus the nested card’s own claim and typed fields.
5. Persist exact graph, contract, corpus, prompt/model/version, and hashes in miner metadata.
6. Write cards/meta/quarantine through atomic replacement.
7. Replay the mine from a saved raw checkpoint. If none exists, rerun the mine and disclose the extra run.

Acceptance:

- Raw-card accounting is exact.
- No duplicate clean IDs.
- No unrelated qualitative card is labeled corroboration.
- Every nested binding independently resolves.
- The completed replay becomes the new pinned Phase 0 input.
- The original completed mine remains archived, not overwritten.

If Phase 0R is required and not completed, the workflow must not claim that every mined card was audited.

## Phase 1 — Deterministic inventory and screen

Files:

- `scripts/evidence_card_audit.py`
- `src/schemas/evidence_card_audit.py`
- New: `config/settings/evidence_card_audit.yaml`
- Tests: `tests/test_evidence_card_audit.py`

Exact steps:

1. Define closed schemas for:
   - input card;
   - support edge;
   - deterministic receipt;
   - Opus verdict;
   - adjudication;
   - repair;
   - disposition;
   - audit manifest.
2. Normalize all v2 rows as `voice=ATTRIBUTED`.
3. Run structure/binding rules against every row/edge.
4. Recompute all derived caches and counts.
5. Run report-AST mechanical and semantic entailment on every ATTRIBUTED claim/support pair.
6. Store append-only receipts in:
   - `inventory.jsonl`
   - `deterministic_receipts.jsonl`
   - `entailment_receipts.jsonl`
7. Continue evaluating other dimensions after a hard failure so the adversary battery can show every planted fault was detected.

Acceptance:

- Inventory count equals the full serialized census.
- Every audit ID has one deterministic receipt.
- Every ATTRIBUTED support edge has one report-AST receipt.
- Missing/uncertain judge results are failures.
- Reopening receipts and rerunning produces identical decisions.

## Phase 2 — Opus prompt and structured verdict contract

Files:

- New: `config/prompts/evidence_card_audit_opus.md`
- New: `config/prompts/evidence_card_adjudicator_opus.md`
- New: `config/prompts/evidence_card_repair_opus.md`
- `src/schemas/evidence_card_audit.py`
- Tests: `tests/test_evidence_card_audit_generality.py`

Exact steps:

1. Prompts accept only injected values:
   - research question;
   - frozen contract facets;
   - card fields;
   - exact verified span;
   - support role;
   - deterministic receipt.
2. Require per-dimension JSON objects with:
   - verdict;
   - machine reason code;
   - unsupported atom;
   - deciding source substring;
   - affected field;
   - proposed disposition.
3. Require a CoT content class for every non-empty field.
4. For numeric claims, require all numeric subdimension verdicts.
5. Do not include task-72 subjects, benchmark examples, AI/labor-market vocabulary, DOI literals, venue literals, or a fixed journal-only policy.
6. Validate every agent response against JSON schema before accepting it.

Acceptance:

- The prompts work unchanged on clinical, legal, economics, and computer-science fixtures.
- Unknown/missing fields fail schema validation.
- No free-form agent reasoning is persisted.
- Opus cannot mark a structurally unreachable span faithful.

## Phase 3 — Durable, parallel Opus orchestrator

Files:

- New: `scripts/evidence_card_audit_orchestrator.py`
- `config/settings/evidence_card_audit.yaml`
- Reference pattern: [`scripts/autoloop/orchestrator.py`](/home/polaris/wt/flywheel/scripts/autoloop/orchestrator.py)
- Reference watchdog: [`scripts/iarch007_box_watchdog.sh`](/home/polaris/wt/flywheel/scripts/iarch007_box_watchdog.sh)

Exact steps:

1. Build token-bounded batches from inventory.
2. Persist each request before invocation:

```text
batches/<pass>/<batch_id>.request.json
```

3. Launch bounded parallel `claude -p --model opus --effort max` workers.
4. Write responses via temp file, fsync, and `os.replace`.
5. Validate:
   - response schema;
   - every requested audit ID appears exactly once;
   - no foreign ID appears;
   - model metadata proves Opus;
   - response is complete.
6. Append accepted verdicts to `opus_pass_a.jsonl` or `opus_pass_b.jsonl`.
7. Maintain `progress.json` with:
   - total/completed/failed/pending batches;
   - last heartbeat;
   - current worker PIDs;
   - retry count;
   - token/cost telemetry.
8. `--resume` reconstructs state exclusively from durable files.
9. Watchdog relaunches a dead orchestrator at most three times with `--resume`.
10. Retry provider failures with the same model. Never degrade.

Acceptance:

- Killing the orchestrator midway and restarting produces no duplicate or missing verdicts.
- Batch order and worker completion order do not affect canonical output.
- Every top-level card has pass A.
- Every ATTRIBUTED card has pass B.
- No batch is considered complete from an unvalidated response.

## Phase 4 — Adjudication and repair

Files:

- `scripts/evidence_card_audit.py`
- `scripts/evidence_card_audit_orchestrator.py`
- Opus adjudicator/repair prompts
- Tests: `tests/test_evidence_card_audit.py`

Exact steps:

1. Join deterministic, report-AST, Opus A, and Opus B receipts by audit ID.
2. Generate one-card adjudication packets for disagreements or failures.
3. Apply fail-closed combination rules.
4. Generate typed repair proposals only for repairable cases.
5. Apply repairs in a new object; never mutate the frozen input.
6. Recompute claim through `derive_claim`.
7. Rerun the entire audit stack on repaired cards.
8. Record:
   - original hash;
   - repaired hash;
   - changed fields;
   - repair agent;
   - adjudicator;
   - old/new verdict vectors.
9. Emit final disposition for every row and support edge.

Acceptance:

```text
input_top_level
  = kept_unchanged
  + repaired_and_superseded
  + quarantined
  + demoted_to_owned_suggestion
```

And separately:

```text
input_support_edges
  = kept_support_edges
  + repaired_support_edges
  + quarantined_support_edges
```

No unaccounted row or edge is allowed.

## Phase 5 — Publish clean set and quarantine ledger

Files:

- `scripts/evidence_card_audit.py`
- Reuse `publisher._atomic_write()`
- Outputs under the SHA-addressed audit directory

Exact steps:

1. Build `audited_cards.json` from `KEEP_UNCHANGED`, validated repairs, and valid rebases only.
2. Build:
   - `quarantine.json`
   - `repairs.json`
   - `owned_suggestions.json`
   - `decisions.jsonl`
3. Sort outputs canonically.
4. Reopen the clean set and construct `CardBundle`.
5. Run `cellcog_composer.reverify(bundle)`.
6. Require zero duplicate IDs and zero failed primary/corroborating resolutions.
7. Rerun `entailed_by_span` over every shipped claim/support edge.
8. Atomically publish:
   - `outputs/evidence_cards_audited.json`
   - `outputs/evidence_cards_audited.manifest.json`
9. Recompute hashes from disk after publication.

Acceptance:

- Every shipped card passes all applicable dimensions.
- Every shipped support edge passes independently.
- No `UNCERTAIN`, `FAIL`, or missing receipt exists in the clean set.
- Clean file SHA matches both manifests.
- Raw v2 is unchanged.
- Quarantine and repair ledgers preserve every excluded/superseded object.

## Phase 6 — Composer interlock

Files:

- Modify [`scripts/cellcog_composer.py`](/home/polaris/wt/flywheel/scripts/cellcog_composer.py:144)
- Tests:
  - `tests/test_evidence_card_audit.py`
  - existing release/binding tests

Exact steps:

1. Remove the production default to `evidence_cards_bound.json`.
2. Require:
   - `--cards outputs/evidence_cards_audited.json`
   - `--audit-manifest <path>`
   - exact graph path;
   - exact ledger path;
   - expected cards/graph hashes.
3. In `load_bundle`, verify:
   - audit manifest status is `COMPLETE`;
   - planted adversary status is `PASS`;
   - zero unresolved decisions;
   - clean-set SHA;
   - graph/corpus/contract hashes;
   - derived source policy.
4. Derive policy from the manifest/question; do not default production to journal-only.
5. Preserve `CardBundle.resolve()` and `reverify()` before any composer LLM call.
6. Stop overwriting a supplied contract with `AP.default_contract()`.
7. Build jobs and planner facets from the pinned actual contract.
8. Ensure publisher provenance records the audit-manifest hash.

Acceptance:

- Raw `evidence_cards_v2.json` is rejected as a production composer input.
- Missing/incomplete/tampered audit manifest is rejected before any LLM call.
- A one-byte clean-set edit is rejected.
- A source-policy mismatch is rejected.
- Composer `--dry` succeeds on the exact audited bundle with zero binding failures.

## Phase 7 — Audit report

Files:

- New outputs:
  - `audit_report.json`
  - `audit_report.md`
  - `worst_offenders.json`

Required metrics:

- Input census:
  - top-level cards;
  - primary bindings;
  - corroborating edges;
  - same-unit expression records.
- Per-dimension raw pass/fail/uncertain/N-A counts and rates.
- Post-repair pass rates.
- Report-AST vs Opus A/B agreement matrix.
- Opus A/B agreement rate.
- Adjudication count and outcomes.
- Quarantine counts by stable reason code.
- Repairs by type.
- Demotions by type.
- False corroboration removed.
- Duplicate-ID collisions.
- Consolidation information loss.
- Pass/quarantine by:
  - Work and manifestation;
  - act;
  - section;
  - facet;
  - source policy;
  - expression kind;
  - numeric/non-numeric;
  - corroboration level.
- Worst offenders:
  - highest failure count;
  - highest failure rate with denominator;
  - severe fabrication examples;
  - CoT-contaminated fields;
  - numeric/sign errors;
  - off-topic clusters.
- Coverage impact:
  - cards and independent evidence units retained per facet;
  - lost facets;
  - low-corroboration areas.
- Model, prompt, code, input, and output hashes.
- Tokens, cost, wall time, retries, and provider failures.

Report both raw and post-repair rates. Never make a repaired corpus appear as if the raw mine had passed.

Acceptance:

- JSON and Markdown totals reconcile exactly with decisions.
- Every reported offender links to audit IDs and exact receipts.
- No sample-based claim is presented as corpus-wide.
- `composer_ready=true` only when the clean-set and adversary gates pass.

## Phase 8 — Generality, metamorphic, and adversarial acceptance

Files:

- New: `tests/test_evidence_card_audit_adversary.py`
- New: `tests/test_evidence_card_audit_generality.py`
- New fixtures under:
  - `tests/fixtures/evidence_card_audit/`
- Existing regression suites remain mandatory.

### Metamorphic test

Create structurally identical fixtures in:

- clinical medicine;
- case law;
- economics;
- computer science.

Change only:

- question subject;
- Work identifiers;
- authors and venues;
- facet vocabulary.

Assert the verdict vector and disposition are unchanged.

Additional metamorphic assertions:

- renaming IDs changes no verdict;
- input-order permutation changes no verdict or final canonical SHA;
- changing batch boundaries changes no verdict;
- journal-only versus any-version wording changes only source-policy admissibility;
- adding one unsupported magnitude changes only the appropriate faithfulness/numeric result.

### Planted adversary

After snapshotting, create a test-only copy and seed one compound known-bad card with:

- a fabricated or tampered binding;
- CoT text in the claim/field;
- a flipped direction;
- off-topic content.

Run every dimension even after the first failure and require:

- structure catches the fabricated binding;
- CoT catches the contaminated field;
- numeric fidelity catches the sign flip;
- relevance catches off-topic content;
- final disposition is quarantine;
- it never appears in `audited_cards.json`.

Also add four single-fault cards so one failure cannot mask another.

Additional attacks:

- valid hash but reversed/empty offsets;
- wrong permitted expression set;
- source-policy laundering;
- unknown semantic-binding verdict;
- impossible semantic-binding/expression-kind pair;
- duplicate card ID;
- false corroborating span;
- invented precision;
- percent/percentage-point swap;
- association-to-causation upgrade;
- subgroup-to-global scope widening;
- judge exception, timeout, garbage, or uncertainty;
- a side-judge `("ENTAILED", "judge_error: ...")` sentinel, which must map to uncertainty rather than admission;
- contaminated optional field repair;
- attempted ATTRIBUTED-to-OWNED laundering.

Acceptance:

- The compound canary is caught in all four requested dimensions.
- Every single-fault canary is caught by its intended dimension.
- No planted fabrication survives.
- Removing or disabling any critical check makes at least one adversary test fail.
- No task-specific literal appears in production audit prompts or rules.

## 6. Regression commands

Run focused tests first:

```bash
cd /home/polaris/wt/flywheel
PYTHONPATH=scripts:src pytest -q \
  tests/test_evidence_card_audit.py \
  tests/test_evidence_card_audit_adversary.py \
  tests/test_evidence_card_audit_generality.py
```

Then the existing binding and policy battery:

```bash
PYTHONPATH=scripts:src pytest -q \
  tests/test_binding_gate_foundation.py \
  tests/test_binding_gate_acceptance.py \
  tests/test_binding_gate_adversary.py \
  tests/test_correspondence_semantic_identity.py \
  tests/test_mining_identity_preskip.py \
  tests/test_source_policy_derivation.py \
  tests/test_version_derivation_unification.py
```

Then production-path attacks:

```bash
PYTHONPATH=scripts:src python scripts/evidence_miner.py --self-test
PYTHONPATH=scripts:src python scripts/test_gate_is_wired.py
PYTHONPATH=scripts:src python scripts/test_fabrication_paths.py
PYTHONPATH=scripts:src python scripts/test_release_e2e_attack.py
```

Final dry composer invocation:

```bash
python -u scripts/cellcog_composer.py \
  --dry \
  --cards outputs/evidence_cards_audited.json \
  --audit-manifest outputs/evidence_cards_audited.manifest.json \
  --graph <pinned-graph-path> \
  --ledger <pinned-ledger-path> \
  --policy <manifest-derived-policy> \
  --expect-cards-sha <audited-cards-sha> \
  --expect-graph-sha <graph-sha>
```

## 7. Production run sequence

1. Wait for mine exit.
2. Snapshot and hash inputs.
3. Run Phase 0 auditability gate.
4. If necessary, execute Phase 0R and replay the mine.
5. Run deterministic inventory.
6. Run report-AST entailment receipts.
7. Launch Opus A across every card.
8. Launch Opus B across every ATTRIBUTED/high-risk card.
9. Launch adjudication and repair jobs.
10. Rerun all repaired cards from zero.
11. Run the planted adversary against a test copy.
12. Build clean/quarantine/repair/owned artifacts.
13. Reopen and independently reverify the clean set.
14. Publish audited cards and manifest atomically.
15. Run composer dry interlock.
16. Mark manifest `COMPLETE` and `composer_ready=true`.

The main session only monitors `progress.json`, worker health, and the five-minute forensic log. It does not make card-level judgments or manually advance batches.

## Definition of done

The audit is complete only when:

- 100% of serialized cards and support edges are accounted for;
- any lossy miner serialization has been repaired and replayed;
- every current v2 card has two independent Opus verdicts;
- every shipped ATTRIBUTED claim passes `report_ast.entailed_by_span`;
- every shipped binding resolves under the pinned derived policy;
- every shipped numeric atom matches its source;
- every shipped field has positive clean-content provenance;
- every shipped card is relevant and correctly facet-tagged;
- no unresolved or ambiguous decision remains;
- quarantine is complete and counted;
- the known-bad card is caught and absent from the clean output;
- `CardBundle` and composer dry-run accept the exact audited artifact;
- the composer cannot consume raw or unaudited cards.