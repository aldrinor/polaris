# Binding-gate build plan

I reviewed the authoritative design note and the live tree. The six hand edits are directionally correct, but they are not yet sufficient to ship. The remaining critical issues are:

- Two independent version derivations still disagree.
- Generic call paths still default to `JOURNAL_ONLY`.
- Prompt-derived source policy can be lost in fallback contract paths.
- Correspondence still trusts the old whole-body `identity.verdict`.
- Unresolved/different works still reach the expensive mining lane.
- Machine-readable self-metadata is not yet used for positive salvage.
- The composer and argument planner still contain live task-specific defaults.

The workflow should execute the eight gated phases below in order: P1, P1S, P2–P7. P1S is the explicit source-policy phase required by the operator; numbering P2–P7 remains aligned with the requested phase names.

## Global rules for every phase

Every phase must preserve these invariants:

1. No DOI, title, author, venue, journal, topic, benchmark ID, or subject string may participate in a production decision.
2. Decisions may depend only on typed work metadata, artifact structure, self-identifying metadata, byte-derived observations, verified span relationships, and the original prompt.
3. The identity gate is always active and is independent of source policy.
4. Missing, malformed, stale, or unknown values fail closed.
5. `JOURNAL_ONLY` is selected only from a positive constraint in the original prompt. Otherwise use `ANY_VERSION`.
6. Each phase must add at least one metamorphic test where identifiers and subject vocabulary are replaced while structure is held constant.
7. Do not tune production rules to make the 501-row cohort count come out correctly. Cohort counts are regression observations, not rule inputs.
8. Do not advance to the next phase until the phase command exits zero.

---

## P1 — Finish and harden the six foundation edits

### Files

- [scripts/event_ledger.py](/home/polaris/wt/flywheel/scripts/event_ledger.py)
- [scripts/provenance.py](/home/polaris/wt/flywheel/scripts/provenance.py)
- [scripts/evidence_miner.py](/home/polaris/wt/flywheel/scripts/evidence_miner.py)
- [scripts/cellcog_composer.py](/home/polaris/wt/flywheel/scripts/cellcog_composer.py)
- [scripts/argument_planner.py](/home/polaris/wt/flywheel/scripts/argument_planner.py)
- [scripts/synthesis_contract.py](/home/polaris/wt/flywheel/scripts/synthesis_contract.py)
- New: `tests/test_binding_gate_foundation.py`
- New: `tests/test_runtime_contract_generality.py`

### Exact edits

#### 1. `derive_binding_core` and `IDENTITY_PROVEN`

Keep both additions in `event_ledger.py`.

Correct the string comparison:

```python
if binding is SAME_WORK:
```

must become:

```python
if binding == SAME_WORK:
```

Keep `derive_semantic_binding(events)` as a thin wrapper. No other identity reducer may be introduced.

All verdict consumers must import or call the same `IDENTITY_PROVEN`; do not reproduce its members in another tuple.

#### 2. Identity derivation in `ingest_bytes()`

Keep the live `observe_text(text) → derive_binding_core(...)` path and the stored:

```python
profile["semantic_binding"]
profile["semantic_binding_basis"]
profile["semantic_binding_derived_by"]
```

Keep `DIFFERENT_WORK` on the quarantine-expression path. It must:

- create no claimed-expression edge;
- use `kind="unknown"`;
- use an expression ID structurally derived from work ID and disposition;
- retain the manifestation bytes.

Do not copy `row["semantic_binding"]` into each manifestation.

In `migrate()`, compare a row-level cached verdict only to the row’s selected `fulltext_manifestation`, when that relationship is explicitly present. Store the comparison as audit-only data:

```python
profile["row_binding_cache"] = {
    "stored": ...,
    "live": ...,
    "agrees": bool,
}
```

No resolver or constructor may read this field to grant permission.

#### 3. `Attribution` fields

Keep:

```python
identity_verdict
disposition
reason_code
```

Define stable constants for dispositions and reason codes in `provenance.py`; do not scatter string literals through callers.

Stamp every resolver return, including invalid bindings:

- invalid span: `QUARANTINE / SPAN_BINDING_INVALID`;
- different work: `QUARANTINE / IDENTITY_DIFFERENT_WORK`;
- unresolved: `LEAD_ONLY / IDENTITY_UNRESOLVED`;
- missing/unknown verdict: `QUARANTINE / IDENTITY_UNKNOWN_VERDICT`;
- incomplete: `QUARANTINE / INCOMPLETE_BYTES`;
- policy mismatch: `LEAD_ONLY / VERSION_NOT_PERMITTED`;
- successful resolution: `ADMIT / ADMITTED`.

Every refusal must have:

```python
admitted is False
names_expression_id is None
text is None
permitted_expression_ids == ()
```

for identity/integrity failures.

#### 4. Resolver identity gate

Keep its location after span verification and before completeness and expression policy.

Remove the unused local imports of each version constant. Import only the canonical allowlist and the two explicit negative verdicts.

Do not compute a permissive fallback from the legacy `profile["identity"]["verdict"]`.

#### 5. Strict JSON load

Keep live re-derivation and refusal on disagreement, but tighten it:

- Missing stored `semantic_binding` is an integrity error, not an old-file compatibility path.
- Unknown stored verdict is an integrity error.
- Re-derive both verdict and basis.
- Use the live verdict and live basis after validation.
- A stored row-cache verdict is never used.
- Update `_take()` to recognize dataclass defaults mechanically with `dataclasses.MISSING`; do not maintain a special handwritten list such as `{"profile", "kind"}`.

Migration is the compatibility path for legacy corpus rows. Strict graph load must not silently migrate an old graph.

#### 6. Miner binding call

Keep the corrected call:

```python
graph.resolve_attribution(binding, policy)
```

Add a regression proving that exact-span correspondence is visible only when the binding, rather than the bare manifestation ID, is passed.

#### Remove live task-specific runtime defaults

The current downstream runtime still contains task-specific production values.

In `cellcog_composer.py`:

- Delete the fixed AI/labor `WRITE_PROMPT` subject.
- Delete the fixed `OUTLINE`.
- Delete the fixed report title.
- Change writer input to accept the compiled `research_contract.Contract`, its question/title, and `research_contract.derive_outline(...)`.
- Render source-method prose from `Contract.source_policy.compliance_prose()`.
- Card instructions must say “permitted source” or the derived policy description, not always “peer-reviewed journal article.”
- `abstract_nodes()` and `methods_nodes()` must receive the contract and derive their wording from it.

In `argument_planner.py`:

- Remove the production `default_contract()` containing AI/labor facets.
- Replace it with `contract_from_research_contract(contract, outline)`.
- A no-contract call produces an empty, facet-agnostic contract, not an AI contract.
- Any AI fixture belongs under tests or an explicitly named demo helper used only by `__main__`.

In `synthesis_contract.py`:

- The historical task-specific members have already been removed from `SAFE_CAPS`; preserve that.
- Delete the `SAFE_CAPS` authority entirely from production validation.
- Capitalized names are permitted only when present in a premise, in the original question/compiled contract, sentence-initial by orthography, or emitted from a typed renderer enum.
- Replace fixed `LEVEL_CUES` as an authority with per-contract facet matchers or span receipts. Fixed social-science vocabulary must not decide clinical, legal, or CS evidence.
- `argument_planner.owned_is_safe()` must use the same structural predicate, not import a second allowlist.

Historical examples may remain in comments and tests, but no runtime default may contain or select the task subject.

### Acceptance test

Create foundation tests covering:

- live foreign DOI derives `DIFFERENT_WORK`;
- changing only requested DOI makes the same bytes reject under both policies;
- changing row cache from `DIFFERENT_WORK` to `SAME_WORK` does not change live resolution;
- missing and unknown verdicts fail closed;
- invalid binding is structurally stamped;
- JSON verdict tampering is refused;
- the corrected `gate_card()` passes its binding.

Generality test:

- compile and render one clinical, one legal, and one CS prompt;
- none may inherit AI, labor-market, journal-only, or 4IR wording;
- a capitalized entity absent from premises/contract is rejected;
- replacing it with a completely different entity produces the same structural result;
- putting that entity into a premise makes it admissible without adding it to an allowlist.

Gate:

```bash
cd /home/polaris/wt/flywheel
PYTHONPATH=scripts python -m pytest -q \
  tests/test_binding_gate_foundation.py \
  tests/test_runtime_contract_generality.py
PYTHONPATH=scripts python scripts/provenance.py
```

### Depends on

None.

---

## P1S — Infer the adjustable source policy from the original prompt

### Files

- [scripts/research_contract.py](/home/polaris/wt/flywheel/scripts/research_contract.py)
- [scripts/evidence_miner.py](/home/polaris/wt/flywheel/scripts/evidence_miner.py)
- [scripts/provenance.py](/home/polaris/wt/flywheel/scripts/provenance.py)
- [scripts/event_ledger.py](/home/polaris/wt/flywheel/scripts/event_ledger.py)
- New: `tests/test_source_policy_derivation.py`

### Exact prompt-derivation rule

Add a deterministic, clause-scoped function in `research_contract.py`:

```python
derive_version_scope(question: str) -> tuple[str, list[str]]
```

It returns `("JOURNAL_ONLY", evidence_clauses)` only when a clause positively directs the system to use published, peer-reviewed, or journal sources.

A positive directive requires both:

1. A source-class phrase:

```text
journal article/source/publication/literature
peer-reviewed article/source/publication/literature
published article/study/source/paper
```

2. A directive or exclusivity relation in the same clause:

```text
use, cite, include, draw on, rely on, restrict to, limit to,
must be, should be, ensure sources are, only, exclusively, solely
```

Negation or widening in the same clause defeats `JOURNAL_ONLY`, including:

```text
not limited to journals
do not restrict to journals
include preprints/working papers/accepted manuscripts
journal articles and preprints
```

Mere discussion of journals, publication, peer review, or comparisons between source types does not set the gate.

No source-class demand means `ANY_VERSION`.

The function must return the exact verbatim clause(s) that justified the restriction. The LLM contract compiler may not invent, remove, or broaden this value.

### Wiring

In `research_contract.SourcePolicy`, add:

```python
version_scope: str = "ANY_VERSION"
version_scope_evidence: list[str] = field(default_factory=list)
```

`_floor_source_policy(question)` sets these exclusively through `derive_version_scope(question)`.

In `evidence_miner.load_contract()`:

- Every return path—explicit facets, compiled contract, cache, question-term fallback, and no-question fallback—must pass through one finalizer.
- The finalizer derives provenance policy from the original `question`, not from the most recently cached contract.
- `JOURNAL_ONLY` maps to `provenance.JOURNAL_ONLY`.
- `ANY_VERSION` maps to `provenance.ANY_VERSION`.
- Remove the current inference from `peer_reviewed_only + excluded_types`.
- Remove the `PEER_REVIEWED` intermediate behavior from this two-state version policy.

Correct generic defaults:

```python
Graph.resolve_attribution(..., source_policy=ANY_VERSION)
gate_card(...): ... or P.ANY_VERSION
MiningContract.source_policy: ANY_VERSION
```

Keep `journal_attributable()` explicit about passing `JOURNAL_ONLY`.

In `mine()`:

- The contract-derived policy is authoritative when `question` is nonempty.
- An explicit `source_policy` that disagrees with a nonempty prompt-derived policy raises `ValueError`.
- Explicit policy remains allowed for low-level tests with `question == ""`.

In `event_ledger.py`:

- Replace `journal_articles_only: bool = True` in `derive_eligibility()` and `record_eligibility()`.
- Accept an explicit `SourcePolicy`, defaulting to `ANY_VERSION`.
- Version eligibility must consult the policy’s permitted expression kinds.
- A preprint is not unconditionally a discovery lead under `ANY_VERSION`.
- Remove task-number language from function semantics.

### Acceptance test

The same valid, complete preprint fixture must produce:

| Prompt | Policy | Result |
|---|---|---|
| “Summarize the evidence about X.” | `ANY_VERSION` | `ADMIT`, names preprint |
| “Use journal articles and preprints about X.” | `ANY_VERSION` | `ADMIT`, names preprint |
| “Explain differences between journals and preprint servers.” | `ANY_VERSION` | `ADMIT`, names preprint |
| “Use only peer-reviewed sources about X.” | `JOURNAL_ONLY` | `LEAD_ONLY` |
| “Cite published journal articles about X.” | `JOURNAL_ONLY` | `LEAD_ONLY` |
| “Do not limit this to journal articles; include working papers.” | `ANY_VERSION` | `ADMIT` |

For `JOURNAL_ONLY`, assert:

```python
admitted is False
disposition == "LEAD_ONLY"
reason_code == "VERSION_NOT_PERMITTED"
names_expression_id is None
```

Metamorphic test: replace X with unrelated clinical, legal, economics, and CS subjects; policy must not change.

Gate:

```bash
cd /home/polaris/wt/flywheel
PYTHONPATH=scripts python -m pytest -q tests/test_source_policy_derivation.py
```

### Depends on

P1.

---

## P2 — Unify version derivation and quarantine impossible pairs

### Design decision

Use one version reducer. Do not retain two competing derivations and choose between them later.

`version_evidence()` becomes the single reducer that returns both:

```python
VersionDecision(
    semantic_binding,
    expression_kind,
    evidence_key,
    basis,
)
```

`ingest_bytes()` must assign its expression kind from this result. `derive_binding_core()` must use the same result when identity is proven.

The resolver still validates the resulting pair, but that is an invariant check against tampering or in-memory corruption—not a second version derivation.

### Files

- [scripts/event_ledger.py](/home/polaris/wt/flywheel/scripts/event_ledger.py)
- [scripts/provenance.py](/home/polaris/wt/flywheel/scripts/provenance.py)
- New: `tests/test_version_derivation_unification.py`

### Exact edits

In `event_ledger.py`:

- Replace `VERSION_EVIDENCE` triples with typed ordered rules that specify both semantic binding and expression kind.
- Split working-paper and preprint observations structurally.
- Preserve precedence:

```text
accepted manuscript
working paper
preprint
published/proceedings version
no version evidence
```

- Cover-sheet and article-front voices remain separately recorded.
- Accepted/preprint/working evidence vetoes published evidence.
- Repository names may be registry data, but no DOI, title, author, journal, or subject may appear in the reducer.
- For non-scholarly typed works, derive `official_text` or `registry_record` from `Work.kind`, not scholarly furniture.

In `provenance.py`:

- `profile()` may retain artifact diagnostics, but it must not independently decide the expression kind.
- Make `derive_expression_kind()` a compatibility wrapper over the shared observations and `version_evidence()`, or remove it after all callers migrate.
- In `ingest_bytes()`, obtain `VersionDecision` once and use its `expression_kind` and basis.
- Store the decision’s evidence key in the profile.
- In `Graph.from_json()`, re-run the same reducer and refuse disagreement with:
  - stored expression kind;
  - the manifestation’s expression node kind;
  - stored semantic version when identity is proven.
- In `resolve_attribution()`, after identity and before completeness, validate the pair against one declarative compatibility table.
- Any incompatible pair returns:

```python
admitted=False
disposition="QUARANTINE"
reason_code="DERIVATION_CONFLICT"
names_expression_id=None
text=None
permitted_expression_ids=()
```

### Exact pair decision table

Assume valid span, identity-proven bytes, and completeness. Correspondence exceptions apply only to the exact bound span.

| Semantic binding | Own expression kind | Pair status | `JOURNAL_ONLY` | `ANY_VERSION` |
|---|---|---|---|---|
| `VERSION_OF_PUBLISHED` | `journal_version` | consistent | ADMIT journal | ADMIT journal |
| `VERSION_OF_PUBLISHED` | `proceedings_version` | consistent | LEAD_ONLY | ADMIT proceedings |
| `VERSION_OF_ACCEPTED` | `accepted_manuscript` | consistent | LEAD_ONLY; exact verified journal correspondence may admit that span | ADMIT accepted manuscript |
| `VERSION_OF_PREPRINT` | `working_paper` | consistent | LEAD_ONLY; exact verified journal correspondence may admit that span | ADMIT working paper |
| `VERSION_OF_PREPRINT` | `preprint` | consistent | LEAD_ONLY; exact verified journal correspondence may admit that span | ADMIT preprint |
| `SAME_WORK` | `official_text` for typed case/statute | consistent | LEAD_ONLY | ADMIT official text |
| `SAME_WORK` | `registry_record` for typed trial/registry work | consistent | LEAD_ONLY | ADMIT registry record |
| `SAME_WORK` | `unknown` | unresolved version, not conflict | LEAD_ONLY | LEAD_ONLY |
| Any proven semantic version | Any other own expression kind | conflict | QUARANTINE | QUARANTINE |

In particular:

```text
VERSION_OF_PREPRINT + journal_version = DERIVATION_CONFLICT
VERSION_OF_ACCEPTED + journal_version = DERIVATION_CONFLICT
VERSION_OF_PUBLISHED + working_paper/preprint/accepted_manuscript = DERIVATION_CONFLICT
```

There is no rank scheme and no “choose the safer-looking label.”

### Metamorphic acceptance vector

Create one accepted fixture, then mutate only structural version furniture:

1. Published furniture → `VERSION_OF_PUBLISHED / journal_version`.
2. Add accepted-manuscript stamp → both outputs change to accepted.
3. Replace accepted stamp with working-paper stamp → both outputs change to preprint/working.
4. Relabel the graph expression node to `journal_version` without changing bytes → loader refuses and resolver returns `DERIVATION_CONFLICT`.
5. Repeat with unrelated clinical, legal, and CS titles/authors; results remain identical.

The real seven known conflicts must become zero admissible conflicts without listing their identifiers.

Gate:

```bash
cd /home/polaris/wt/flywheel
PYTHONPATH=scripts python -m pytest -q tests/test_version_derivation_unification.py
```

### Depends on

P1 and P1S.

---

## P3 — Make correspondence use semantic identity

### Files

- [scripts/provenance.py](/home/polaris/wt/flywheel/scripts/provenance.py)
- New: `tests/test_correspondence_semantic_identity.py`

### Exact edits

Delete:

```python
CORRESPONDENCE_IDENTITY_OK = ("CONFIRMED",)
```

Update all three correspondence/whole-copy seams:

1. `make_correspondence()`
2. `Graph.exact_copy_failure()`
3. `Graph.verify_correspondence()`

Use:

```python
m.profile["semantic_binding"] in IDENTITY_PROVEN
```

`SpanCorrespondence.source_identity` and `target_identity` must store semantic-binding verdicts, not legacy whole-body `identity.verdict`.

At verification:

- recompute live semantic binding from each manifestation’s bytes and Work;
- reject stale stored correspondence identity;
- reject `DIFFERENT_WORK`, `UNRESOLVED_BINDING`, missing, and unknown values;
- then perform hashes, offsets, canonical equality, and basis checks.

Update comments and error messages so they no longer claim that `CONFIRMED` is authoritative.

The legacy `profile["identity"]` may remain diagnostic but may not authorize exact copies or span correspondence.

### Acceptance test

Construct two manifestations whose bodies mention requested authors only in references and whose legacy whole-body identity says `CONFIRMED`, while semantic identity is unresolved. Exact-copy edge and correspondence construction must both fail.

Add valid semantic identities without changing the equal span: correspondence succeeds.

Metamorphic test: replace the scholarly Works with two typed legal or registry Works and repeat. Authorization must depend on semantic allowlisting and exact bytes, not bylines or field.

Gate:

```bash
cd /home/polaris/wt/flywheel
PYTHONPATH=scripts python -m pytest -q tests/test_correspondence_semantic_identity.py
```

### Depends on

P2.

---

## P4 — Pre-skip identity failures before LLM mining

### Files

- [scripts/evidence_miner.py](/home/polaris/wt/flywheel/scripts/evidence_miner.py)
- New: `tests/test_mining_identity_preskip.py`

### Exact edits

At the beginning of each manifestation iteration in `_mining_units()`:

```python
att = graph.resolve_attribution(mid, policy)
```

Inspect only structured `reason_code`.

Pre-skip:

```text
IDENTITY_UNRESOLVED       -> identity_unresolved_lead
IDENTITY_DIFFERENT_WORK   -> different_work_quarantine
IDENTITY_UNKNOWN_VERDICT  -> identity_integrity_quarantine
DERIVATION_CONFLICT       -> derivation_conflict_quarantine
```

Each detail entry must retain:

```python
manifestation_id
work_id
content_hash
identity_verdict
disposition
reason_code
why
```

After those checks, retain the existing completeness selection.

Do not pre-skip `VERSION_NOT_PERMITTED` solely from the whole-manifestation answer: a verified exact-span correspondence may permit a particular span even when the whole manifestation cannot name the journal.

This phase is only a spend optimization. Card construction must continue to call the universal resolver.

Expose the four skip counts separately in `stats["not_minable"]` and `not_minable_detail`.

### Acceptance test

Construct:

- a complete unresolved manifestation;
- a complete different-work manifestation;
- a complete preprint under `JOURNAL_ONLY`;
- a complete valid journal manifestation.

Assert:

- unresolved and different work are absent from mining units and counted in separate buckets;
- the preprint remains available for possible span-specific correspondence;
- the journal remains available;
- monkeypatched LLM/miner functions are never called for the first two.

Metamorphic test: change all titles, DOIs, authors, and subjects while preserving verdict structure; unit selection and counters must be unchanged.

Gate:

```bash
cd /home/polaris/wt/flywheel
PYTHONPATH=scripts python -m pytest -q tests/test_mining_identity_preskip.py
```

### Depends on

P3.

---

## P5 — Positive machine-metadata salvage for unresolved manifestations

### Files

- New: `scripts/identity_receipts.py`
- [scripts/event_ledger.py](/home/polaris/wt/flywheel/scripts/event_ledger.py)
- [scripts/provenance.py](/home/polaris/wt/flywheel/scripts/provenance.py)
- [scripts/provenance_construct.py](/home/polaris/wt/flywheel/scripts/provenance_construct.py)
- New: `tests/test_identity_metadata_salvage.py`
- New: `tests/fixtures/identity_metadata/`
- New: `docs/identity_metadata_salvage.md`

### Exact data model

Add an explicit `IdentityReceipt` dataclass containing at least:

```python
receipt_id
manifestation_id
manifestation_content_hash
artifact_blob_id
artifact_sha256
media_type
extractor_name
extractor_version
receipt_kind              # SELF_IDENTIFIER | SELF_TITLE_BYLINE
metadata_container        # pdf_info | pdf_xmp | html_head | jats_front
metadata_field
raw_match
start_offset
end_offset
normalized_value
requested_normalized_value
supporting_matches
```

For field-based PDF metadata, offsets are offsets inside the named metadata field. For XMP/HTML/JATS, offsets are byte or decoded-character offsets in the raw artifact. The location type must make the coordinate space explicit.

Extend `Manifestation` with optional raw-artifact lineage:

```python
raw_blob_id
raw_content_hash
content_type
identity_receipts
```

`provenance_construct.construct()` passes raw `blob_id`, `byte_sha256`, and content type from ledger manifestations.

`migrate()` matches the selected `fulltext_manifestation` or exact `text_sha256` against `row["manifestations"]` and passes its raw blob reference. It must not copy a receipt or verdict from the row.

### Exact extraction rule

Run `reresolve_unresolved_metadata(graph, blob_store)` only after baseline manifestations exist, and only over live `UNRESOLVED_BINDING`.

Admissible self-fields are:

#### PDF, through PyMuPDF/fitz

- DOI: PDF Info or XMP self-metadata fields.
- Title: PDF Info/XMP title.
- Authors: PDF Info/XMP author/creator.

Do not inspect rendered body or reference text.

#### HTML

Inside `<head>` only:

- identifier: `citation_doi`, `DC.identifier`;
- title: `citation_title`, `DC.title`;
- author: repeated `citation_author`, `DC.creator`.

#### JATS

Inside `<front><article-meta>` only:

- identifier: `<article-id pub-id-type="doi">`;
- title: `<article-title>`;
- authors: `<contrib contrib-type="author">`, using structured name fields.

Never search `<body>` or `<back>`.

### Positive promotion rule

Normalize DOI by parsing DOI URI/prefix forms, case-folding, percent-decoding, and stripping terminal citation punctuation.

Normalize title with Unicode NFKC, entity decoding, case-folding, punctuation-to-space, and whitespace collapse. Title match is exact after normalization—no fuzzy threshold.

Normalize authors structurally:

- compare requested family name to a structured surname field; or
- compare an exact normalized full-name sequence;
- a single requested surname must equal a metadata surname token, not be a substring.

Promote only when one of these holds:

1. Exact requested DOI in a permitted self-identifier field.
2. Exact normalized requested title and at least one requested author in permitted self-identity fields.

Conflict rule:

- if self-identifier fields contain both target and foreign DOI values, remain unresolved with `IDENTITY_METADATA_CONFLICT`;
- title/author evidence cannot override a conflicting self-identifier;
- absence of metadata changes nothing.

A verified receipt becomes an observation consumed by `derive_binding_core()`. The reducer then re-derives `SAME_WORK` or the appropriate version verdict. Do not directly assign a promoted verdict in the salvage loop.

### Loader revalidation

`Graph.from_json(..., blob_store=...)` must:

1. load raw bytes by immutable blob ID;
2. verify raw hash;
3. rerun the named metadata extractor/version;
4. re-find the exact raw match at the recorded location;
5. re-normalize the value;
6. re-evaluate it against the Work;
7. compare the canonical live receipt to the stored receipt;
8. re-run `derive_binding_core()` using verified receipts;
9. refuse the graph on any mismatch or unavailable receipt artifact.

A graph with receipts cannot load without access to the referenced blob store.

### OCR status

Do not implement OCR.

Document in `docs/identity_metadata_salvage.md`:

```text
IMAGE_OCR_IDENTITY_RECEIPT: BLOCKED
reason: no installed/revalidatable OCR backend; tesseract unavailable and no sudo
effect: residual glyph-header manifestations remain LEAD_ONLY
```

An `OCR`-typed receipt supplied through JSON must be refused as an unsupported receipt type.

Expected cohort measurement is approximately:

```text
initial unresolved: 155
machine-metadata promotions: ~67
residual unresolved leads: ~88
OCR promotions: 0
```

These are audit counts, not thresholds in production logic.

### Acceptance test

Fixtures must include:

- PDF Info exact DOI;
- PDF XMP title plus author;
- HTML `citation_doi`;
- HTML `DC.title + DC.creator`;
- JATS article DOI;
- JATS title plus contributor;
- target DOI appearing only in references;
- target author appearing only in body;
- generic title without author;
- target and foreign self-DOIs;
- tampered raw artifact;
- tampered receipt offsets;
- unsupported OCR receipt.

Assert only the first six promote.

Metamorphic test: generate the same containers with unrelated identifiers and titles across medicine, law, economics, and CS. Changing only the requested identifier changes target receipt into nonmatching/conflicting evidence without changing extraction behavior.

Cohort gate:

- baseline 155 unresolved when run against the recorded corpus hash;
- approximately 60–75 machine-metadata promotions;
- all promotions carry revalidatable receipts;
- residual count equals initial minus promotions;
- zero residual unresolved manifestations are admitted;
- zero OCR promotions.

Gate:

```bash
cd /home/polaris/wt/flywheel
PYTHONPATH=scripts python -m pytest -q tests/test_identity_metadata_salvage.py
PYTHONPATH=scripts python scripts/provenance_construct.py --rebuild
```

### Depends on

P4.

---

## P6 — Real-chain 12-vector acceptance battery and cohort regression

### Files

- New: `tests/test_binding_gate_acceptance.py`
- New: `tests/fixtures/binding_gate/`
- Update embedded self-tests in:
  - [scripts/provenance.py](/home/polaris/wt/flywheel/scripts/provenance.py)
  - [scripts/evidence_miner.py](/home/polaris/wt/flywheel/scripts/evidence_miner.py)

### Test-chain requirement

Every synthetic vector must run through:

```text
observe/derive
→ ingest_bytes
→ optional metadata re-resolution
→ bind_span
→ resolve_attribution(binding, policy)
→ Graph.to_json
→ Graph.from_json
→ bind/resolve again
```

No mocked `Attribution` and no direct assignment of a successful verdict.

### The 12 vectors

1. **Foreign front-matter DOI**

   Requested `d1`; article self-front matter contains only `d2`.

   Expected: `DIFFERENT_WORK`, quarantine expression, both policies reject, no expression for `d1` named before or after JSON round-trip.

2. **Disjoint byline**

   Requested authors A/B; readable foreign title and positive byline C/D; no requested DOI/title tie.

   Expected: `DIFFERENT_WORK`, both reject. Remove only the byline cue: result weakens to `UNRESOLVED_BINDING`.

3. **Glyph header, no receipt**

   Header contains `(cid:NN)` garbage; readable body mentions requested authors or DOI only in citations/references.

   Expected: `UNRESOLVED_BINDING`, `LEAD_ONLY`, both reject, P4 pre-skips it.

4. **Glyph header salvage and OCR block**

   Same glyph artifact with valid machine self-metadata containing target DOI or title+author.

   Expected: receipt revalidates, identity promotes, admission then follows version/policy.

   Companion assertion: an OCR-typed receipt is refused and the no-metadata artifact stays unresolved. This is the deliberate no-OCR adaptation of the prior OCR-success vector.

5. **Generic-title collision**

   Generic requested title overlaps artifact title; no matching self-ID or author.

   Expected: unresolved, never different-work, no attribution.

6. **Clean same-work journal**

   Exact target identity plus structural journal-version furniture and complete body.

   Expected: unified reducer gives `VERSION_OF_PUBLISHED / journal_version`; both policies admit the actual journal expression.

7. **Working-paper manifestation**

   Target identity matches; structural working-paper furniture.

   Expected: `VERSION_OF_PREPRINT / working_paper`; `ANY_VERSION` admits its own expression; `JOURNAL_ONLY` is lead-only and never names the journal.

8. **Accepted manuscript**

   Target identity matches; accepted-manuscript stamp plus citation to published version.

   Expected: `VERSION_OF_ACCEPTED / accepted_manuscript`; `ANY_VERSION` admits manuscript; `JOURNAL_ONLY` lead-only.

9. **Exact-span journal correspondence**

   Start with vector 7 or 8 and separately held identity-proven journal bytes. Add verified exact correspondence for one span.

   Expected:
   - bare manifestation under `JOURNAL_ONLY`: not admitted;
   - exact bound span: admitted and names journal;
   - adjacent, containing, or overlapping-but-not-identical span: not widened.

10. **Conflicting recovered identifiers**

    Self-metadata contains both target and foreign DOI values without a structural separation.

    Expected: unresolved with metadata conflict; both policies reject; round-trip preserves refusal.

11. **Unknown enum and impossible pair**

    Test both:
    - stored `semantic_binding="SAMEISH_WORK"`;
    - `VERSION_OF_PREPRINT` manifestation relabeled to `journal_version`.

    Expected: strict load failure. An equivalent in-memory corruption returns quarantine, respectively `IDENTITY_UNKNOWN_VERDICT` or `DERIVATION_CONFLICT`.

12. **501-row cohort regression**

    Migrate/rebuild the actual corpus and assert under both policies:

    - every `DIFFERENT_WORK` manifestation rejects for identity;
    - zero different-work manifestations name the claimed DOI/expression;
    - every residual unresolved manifestation has `admitted=False`;
    - zero derivation conflicts are admitted;
    - all accepted/working/preprint policy outcomes follow the pair table;
    - counts separately report:
      - different-work quarantine;
      - unresolved leads;
      - derivation conflicts;
      - incomplete bytes;
      - version-policy leads;
      - metadata promotions.

### Cross-vector generality assertion

Parameterize vectors 1–11 over at least four unrelated Work identities:

- clinical study;
- legal document;
- economics paper;
- CS preprint.

The expected result must be determined by typed structure. No production code or fixture helper may branch on those domain labels.

### Acceptance test

```bash
cd /home/polaris/wt/flywheel
PYTHONPATH=scripts python -m pytest -q tests/test_binding_gate_acceptance.py
PYTHONPATH=scripts python scripts/provenance.py
PYTHONPATH=scripts python scripts/evidence_miner.py
```

The embedded miner self-test must not invoke OpenRouter.

### Depends on

P1–P5.

---

## P7 — Independent adversary pass

### Files

- New: `tests/test_binding_gate_adversary.py`
- New audit output: `outputs/audits/binding-gate-adversary/report.md`
- Production files only if the adversary finds a genuine structural bypass.

### Agent instructions

Assign an Opus agent that did not implement P1–P6.

The agent must treat graph JSON, corpus rows, metadata receipts, bindings, expression nodes, and cached contracts as attacker-controlled inputs. It may mutate test fixtures and in-memory graphs but must not alter the production corpus.

For any successful bypass:

1. Save the minimized failing artifact as a regression fixture.
2. Explain which positive invariant was missing.
3. Fix the invariant structurally.
4. Add a metamorphic variant with unrelated identifiers/subject.
5. Re-run P1–P7 gates.

The agent must attempt at least these attacks:

1. **Foreign-DOI relabel**

   Keep bytes self-identifying as `d1`; relabel requested Work, row DOI, claimed expression, and attribution as `d2`.

   Required result: both policies name nothing.

2. **Glyph-header laundering**

   Put target DOI/title/authors only in body citations or references; leave self-header unreadable.

   Required result: unresolved lead; forged metadata/OCR receipt rejected.

3. **Generic-title collision**

   Reuse a short generic title across unrelated Works, with absent or disjoint byline variants.

   Required result: absent byline → unresolved; positive disjoint byline → different work; neither admitted.

4. **JSON tampering**

   Modify independently:
   - semantic verdict;
   - expression kind;
   - content hash;
   - Work ID;
   - receipt raw match/offset;
   - correspondence identity;
   - permitted expression IDs;
   - cached contract source policy.

   Required result: strict load failure or resolver quarantine; no repair that increases permission.

5. **Unknown enum**

   Inject unknown semantic binding, expression kind, disposition, receipt type, and policy kind.

   Required result: fail closed; no default admission.

6. **Policy laundering**

   Compile a journal-only prompt, then pass/corrupt `ANY_VERSION`; compile an unconstrained prompt, then verify no path silently substitutes `JOURNAL_ONLY`.

7. **Structural fuzzing**

   Run at least 100 seeded mutations per attack family, varying all DOI/title/author/field strings independently.

### Acceptance test

The audit report must record:

- seed;
- attack count;
- minimized failures, if any;
- exact regression test added;
- final admitted-fabrication count.

Required terminal result:

```text
admitted fabricated attributions: 0
unknown-enum admissions: 0
tampered graphs loaded: 0
policy-laundering successes: 0
```

Gate:

```bash
cd /home/polaris/wt/flywheel
PYTHONPATH=scripts python -m pytest -q tests/test_binding_gate_adversary.py
PYTHONPATH=scripts python -m pytest -q \
  tests/test_binding_gate_foundation.py \
  tests/test_runtime_contract_generality.py \
  tests/test_source_policy_derivation.py \
  tests/test_version_derivation_unification.py \
  tests/test_correspondence_semantic_identity.py \
  tests/test_mining_identity_preskip.py \
  tests/test_identity_metadata_salvage.py \
  tests/test_binding_gate_acceptance.py \
  tests/test_binding_gate_adversary.py
```

### Depends on

P6.

---

## Final workflow release gate

After P7, the monitoring session should require one clean sequential run:

```bash
cd /home/polaris/wt/flywheel
PYTHONPATH=scripts python -m pytest -q \
  tests/test_binding_gate_foundation.py \
  tests/test_runtime_contract_generality.py \
  tests/test_source_policy_derivation.py \
  tests/test_version_derivation_unification.py \
  tests/test_correspondence_semantic_identity.py \
  tests/test_mining_identity_preskip.py \
  tests/test_identity_metadata_salvage.py \
  tests/test_binding_gate_acceptance.py \
  tests/test_binding_gate_adversary.py
PYTHONPATH=scripts python scripts/provenance.py
PYTHONPATH=scripts python scripts/provenance_construct.py --rebuild
```

Release only if:

- all tests exit zero;
- no `DIFFERENT_WORK`, residual `UNRESOLVED_BINDING`, unknown verdict, or derivation conflict is admitted;
- the unconstrained-prompt preprint is admitted as its actual preprint under `ANY_VERSION`;
- the journal-constrained version of the same prompt makes that preprint `LEAD_ONLY`;
- approximately 67 unresolved manifestations have machine-metadata receipts and approximately 88 remain leads;
- no OCR promotion is claimed;
- the composer’s title, outline, methods prose, and source wording are derived from the current contract rather than task-specific runtime constants.