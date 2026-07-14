The binding gate belongs in `Graph.resolve_attribution()`. Migration must preserve and re-derive identity correctly, but it must not be the safety boundary. `SourcePolicy` remains expression policy only; `_mining_units()` may optimize spend using the resolver’s structured decision but must not implement a second identity rule.

I reproduced the probe: under `JOURNAL_ONLY`, 12 `DIFFERENT_WORK` manifestations currently name the claimed DOI, as do 39 `UNRESOLVED_BINDING` manifestations.

## 1. Correct seam

### Authoritative enforcement point

Insert the identity check in [`Graph.resolve_attribution()`](/home/polaris/wt/flywheel/scripts/provenance.py:1264), after a supplied span binding has been verified but before attribution targets or expression kinds can admit anything.

The resolver’s conjunction becomes:

```text
ADMIT =
    valid bound span
    AND complete, readable manifestation
    AND positively proven manifestation-to-work identity
    AND binding/expression-kind consistency
    AND at least one verified target expression permitted by SourcePolicy
```

The identity allowlist is:

```python
IDENTITY_PROVEN = {
    SAME_WORK,
    VERSION_OF_PUBLISHED,
    VERSION_OF_ACCEPTED,
    VERSION_OF_PREPRINT,
}
```

This must be an allowlist. Missing, malformed, stale, or newly introduced verdicts reject by default.

On identity failure, return:

```text
admitted = False
names_expression_id = None
text = None
permitted_expression_ids = ()
```

Add structured results to `Attribution`, rather than forcing callers to parse refusal prose:

```text
identity_verdict
disposition       # ADMIT | LEAD_ONLY | QUARANTINE
reason_code       # IDENTITY_DIFFERENT_WORK, IDENTITY_UNRESOLVED, ...
```

Identity precedes the current completeness check at [`provenance.py:1318`](/home/polaris/wt/flywheel/scripts/provenance.py:1318) and the expression-policy check at [`provenance.py:1323`](/home/polaris/wt/flywheel/scripts/provenance.py:1323). Record all component outcomes for audit even when one earlier component already determines rejection.

Why this seam:

- Census reaches it through [`journal_attributable()`](/home/polaris/wt/flywheel/scripts/provenance.py:1376).
- Quarantine calls it at [`quarantine.py:150`](/home/polaris/wt/flywheel/scripts/quarantine.py:150).
- Miner preflight calls it at [`evidence_miner.py:2168`](/home/polaris/wt/flywheel/scripts/evidence_miner.py:2168).
- Card construction calls it at [`evidence_miner.py:1401`](/home/polaris/wt/flywheel/scripts/evidence_miner.py:1401).
- Publisher and report-AST callers also converge there.

No caller can acquire attribution merely by bypassing miner selection.

### Supporting construction invariants

These are necessary inputs to the gate, not alternative gates:

1. Keep [`derive_semantic_binding()`](/home/polaris/wt/flywheel/scripts/event_ledger.py:1122) as the single semantic rule. Factor its per-manifestation core so graph construction can run the same reducer from requested identity plus the manifestation’s bytes. Do not create a provenance-specific approximation.

2. Store a structured per-manifestation binding verdict and basis in `Manifestation.profile`. Do not copy the row-level verdict to every manifestation: the corpus row verdict describes the selected best holding, not necessarily its abstract or other retained manifestations.

3. At [`ingest_bytes()`](/home/polaris/wt/flywheel/scripts/provenance.py:1639), a live `DIFFERENT_WORK` verdict must take the existing quarantine-expression path at [`provenance.py:1653`](/home/polaris/wt/flywheel/scripts/provenance.py:1653). It creates no edge to the claimed expression.

4. [`migrate()`](/home/polaris/wt/flywheel/scripts/provenance.py:1715) must re-derive the verdict from bytes and requested Work metadata. `row["semantic_binding"]` is an audit cache: compare and report disagreement, but never use it to promote.

5. [`Graph.from_json()`](/home/polaris/wt/flywheel/scripts/provenance.py:1391) must re-derive semantic binding and refuse a stored graph whose verdict disagrees. This parallels its current re-derivation of hashes, extractability, and completeness at [`provenance.py:1479`](/home/polaris/wt/flywheel/scripts/provenance.py:1479).

6. Replace the weaker whole-body `identity.verdict == CONFIRMED` authority in correspondence checks at [`provenance.py:1127`](/home/polaris/wt/flywheel/scripts/provenance.py:1127) with the semantic-binding allowlist. Whole-body author occurrence is unsafe because references “confirm” unrelated papers.

7. Fix [`evidence_miner.py:1401`](/home/polaris/wt/flywheel/scripts/evidence_miner.py:1401) to call:

```python
graph.resolve_attribution(binding, policy)
```

not `resolve_attribution(mid, policy)`. The current call discards the binding it just created, skips `verify_span()`, and prevents legitimate span-specific correspondence from being considered.

### Rejected alternatives

- `_mining_units()` alone is not a safety seam; cards, census, quarantine, publisher, or future callers could bypass it.
- `SourcePolicy` must not carry an optional identity requirement. Identity is required for every attributed sentence, while policy governs which positively identified expressions the task permits.
- Migration alone is insufficient because serialized graphs and other constructors exist.
- Foreign bytes should not automatically be attributed to their observed foreign DOI. A foreign DOI proves “not the requested Work”; it does not necessarily supply the complete, independently verified bibliographic record required to cite the stranger. Retain the bytes and retrieval relationship in quarantine. They may later be re-ingested under the foreign Work after positive resolution.

## 2. Decision table

Assume first that the span verifies and the manifestation is complete/readable. Those requirements remain independently mandatory.

| Semantic binding | Identity result | Own expression required | `JOURNAL_ONLY` | `ANY_VERSION` |
|---|---|---|---|---|
| `SAME_WORK` | Pass | Whatever expression the bytes independently establish | Admit only if a verified target is `journal_version`; otherwise lead-only | Admit the manifestation’s own identified, permitted expression; unknown expression remains lead-only |
| `VERSION_OF_PUBLISHED` | Pass | `journal_version` or other independently derived published expression | Admit its own `journal_version`; never merely the metadata-claimed node | Admit its own published expression |
| `VERSION_OF_ACCEPTED` | Pass | `accepted_manuscript` | Lead-only unless this exact bound span has a verified correspondence into a journal manifestation, in which case name that journal expression for this span only | Admit naming `accepted_manuscript`, never the claimed journal version |
| `VERSION_OF_PREPRINT` | Pass | `working_paper` or `preprint` | Lead-only under the same exact-span correspondence exception | Admit naming the actual working-paper/preprint expression |
| `DIFFERENT_WORK` | Fail positively | None relative to the requested Work | Quarantine; name nothing | Quarantine; name nothing |
| `UNRESOLVED_BINDING` | Not proven | None | Lead-only; name nothing | Lead-only; name nothing |
| Missing or unknown verdict | Fail closed | None | Quarantine/integrity failure | Quarantine/integrity failure |

A mismatch such as `VERSION_OF_PREPRINT` attached to `journal_version` is `DERIVATION_CONFLICT`, not an opportunity to choose the more permissive label. Quarantine it.

The resolver must prefer the manifestation’s own expression. It may name another expression only through an asserted whole-document byte-equivalence edge or a verified correspondence for this exact bound span. Metadata saying that a journal article exists is not such an edge.

`LEAD_ONLY` is not a form of attribution: `admitted=False`, with no source name.

## 3. `UNRESOLVED` disposition and salvage

Choose positive re-resolution plus lead-only retention:

- Initial and residual `UNRESOLVED_BINDING` manifestations are never attributable.
- They remain visible as leads for retrieval, OCR, coverage accounting, and later resolution.
- They should not enter the expensive attributed-evidence LLM lane until promoted. `_mining_units()` may pre-skip them using the resolver’s `reason_code`, count them as `identity_unresolved_lead`, and retain their IDs and reasons.
- Their absence from evidence cards says only “the pipeline could not prove attribution,” never “the literature contains no evidence.”

### Positive re-resolution rule

Run re-resolution only over `UNRESOLVED_BINDING`. It may conclude:

- an identity-proven binding;
- `DIFFERENT_WORK` from newly recovered positive foreign evidence; or
- remain unresolved.

Promotion is allowed only by one of these positive receipts:

1. **Exact self-identifier**

   The exact normalized requested DOI or other typed persistent identifier appears in a document-self-identifying location:

   - machine-readable article metadata contained in the retrieved artifact;
   - article front matter after repository-cover segmentation;
   - or repeated page header/footer furniture on at least two pages before the references.

   A bare DOI occurrence anywhere in narrative text or references is only a candidate signal. Papers cite other papers; it cannot promote identity by itself.

2. **OCR recovery of front matter**

   OCR the article’s title/byline page, excluding a segmented repository cover. Promote when OCR recovers either:

   - the exact requested persistent identifier; or
   - the requested title plus at least one requested author in a positively detected byline.

   Title matching may tolerate OCR normalization only when accompanied by the byline match. An author name elsewhere in the body is not a byline.

3. **Typed official identity**

   For non-article sources, an exact source-native identifier in self-identifying metadata is equivalent: trial registration number, ECLI/docket identifier, statute identifier, report accession, and so forth.

Every receipt must retain:

```text
manifestation content hash
extractor/OCR algorithm and version
raw matched text
offsets or page coordinates
identifier/title/byline normalization result
cover/front-matter segmentation result
```

The loader and resolver must revalidate the receipt. OCR failure, no match, or an inaccessible raw page changes nothing and never promotes.

If positive target and foreign self-identifiers conflict, the result is unresolved-with-conflict, not `SAME_WORK`. If OCR reveals a foreign DOI or a genuinely disjoint foreign byline with no target tie, it may positively resolve to `DIFFERENT_WORK`.

For Autor–Levy–Murnane, body references to those authors are insufficient. It promotes only if OCR of its damaged title page recovers the target DOI or the target title plus byline. Otherwise it remains lead-only.

## 4. Generality and metamorphic properties

The gate consumes a structural verdict derived from typed identity observations. It contains no task-72 DOI, title, author, journal, or subject vocabulary.

Primary metamorphic test:

> Start with an admitted manifestation whose article front matter prints DOI `d1` and whose Work is `d1`. Change only the requested/claimed Work DOI to `d2`, where `d2 != d1`, leaving all bytes unchanged. Live derivation must become `DIFFERENT_WORK`, and both policies must return `admitted=False`, `names_expression_id=None`.

Also require:

- Adding expression kinds to a `SourcePolicy` can never overcome `DIFFERENT_WORK` or `UNRESOLVED_BINDING`.
- Removing the last positive identity receipt from an admitted manifestation changes it to unresolved and rejects; it never remains admitted.
- Adding an unrelated DOI in the references does not change identity.
- A new, unregistered binding enum rejects by default.
- Graph JSON tampering from `DIFFERENT_WORK` to `SAME_WORK` fails strict load or is re-derived back to `DIFFERENT_WORK`.

Domain behavior:

- Clinical: article DOI or trial identifier proves identity; accepted manuscripts/preprints still obey the selected expression policy.
- Legal/comparative: ECLI, docket, reporter, or statute identity can prove `SAME_WORK`; lack of an author byline is irrelevant and cannot convict.
- Thin evidence: unresolved leads reduce attributable coverage and are reported as unresolved. They never license an absence claim.
- New identifier schemes, document metadata extractors, or source-expression mappings should be registry/data additions. Domain/topic strings do not enter the gate.

## 5. Acceptance battery

Each vector must use the real chain:

```text
derive/re-derive binding
→ ingest/migrate
→ bind_span
→ resolve_attribution(binding, policy)
→ graph JSON round-trip
```

No mocked `Attribution` objects.

1. **Foreign front-matter DOI**

   Requested DOI `10.x/a`; readable article front matter prints only `10.x/b`.

   Expected: `DIFFERENT_WORK`; quarantine expression; both policies reject; claimed DOI never named.

2. **Disjoint byline**

   Requested Work has authors A/B. Readable article front matter contains a positively detected byline C/D; no target DOI, specific-title match, or other target tie.

   Expected: `DIFFERENT_WORK`; both policies reject. Removing the byline cue must weaken this to `UNRESOLVED_BINDING`, not leave it different.

3. **Glyph-header right paper, no receipt**

   Header is `(cid:NN)` garbage; body is readable and contains requested author names only in citations/references.

   Expected: `UNRESOLVED_BINDING`; `LEAD_ONLY`; both policies reject; no expensive evidence mining.

4. **Glyph-header with successful OCR**

   Same bytes/raw PDF, but a versioned OCR receipt recovers the requested full title and requested authors in the title-page byline, or the exact target DOI.

   Expected: promote to the appropriate identity-proven binding. Admission still depends independently on the derived expression kind and policy.

5. **Generic-title collision without byline**

   Generic requested title overlaps the fetched document; no positively observed byline or self-identifier.

   Expected: `UNRESOLVED_BINDING`, never `DIFFERENT_WORK`; lead-only and unattributable.

6. **Clean same-work journal**

   Exact target DOI in article front matter, clean journal-version furniture, complete body.

   Expected: identity `SAME_WORK` or `VERSION_OF_PUBLISHED` according to the shared reducer; both policies admit and name the graph’s actual `journal_version`.

7. **Working-paper manifestation**

   Target title/byline positively matches; header says working paper/preprint.

   Expected: `VERSION_OF_PREPRINT`; `ANY_VERSION` admits the actual `working_paper`/`preprint`; `JOURNAL_ONLY` returns lead-only and never names the claimed journal.

8. **Accepted manuscript**

   Target identity matches; accepted-manuscript stamp has precedence over a cover-sheet citation to the published article.

   Expected: `VERSION_OF_ACCEPTED`; `ANY_VERSION` names `accepted_manuscript`; `JOURNAL_ONLY` is lead-only.

9. **Exact-span journal correspondence**

   Use vector 7 or 8 plus held journal bytes and a verified exact correspondence for one bound span.

   Expected: whole-document `JOURNAL_ONLY` remains inadmissible, but that exact binding may name the journal expression. An adjacent or containing span must not inherit permission.

10. **Conflicting recovered identifiers**

    OCR/self-metadata contains both target and foreign identifiers without a defensible voice/cover segmentation.

    Expected: unresolved-with-conflict; no policy admits.

11. **Unknown enum**

    Store `semantic_binding="SAMEISH_WORK"`.

    Expected: strict graph load failure or resolver quarantine; never default admission.

12. **Corpus cohort regression**

    Against the current 501 rows:

    - all 15 `DIFFERENT_WORK` rows must be rejected under both policies for identity, including the two also incomplete;
    - zero may name the claimed DOI;
    - every residual `UNRESOLVED_BINDING` row must have `admitted=False`;
    - counts must separately report different-work quarantine, unresolved leads, completeness failures, and expression-policy leads.

That closes the P0 at the universal naming boundary while retaining unresolved documents honestly for recovery.