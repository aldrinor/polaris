HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

# Wave-2c WIRING brief — presentation_tables into the section render (I-deepfix-001 #1344)

## STATUS: BLOCKED — STOP-and-report per the task's explicit stop clause

The task instructed: *"If wiring risks inserting an unverified number or a non-changed
overwrite, STOP and report."* After a full trace of the render seam and the claim data
structures, **the safe wiring cannot be built as specified, because the input the module
requires — structured, VERBATIM-valued, `[N]`-carrying, strict_verify-passed numeric claims —
does not exist as a collection anywhere at the section render seam.** Building it is a NEW
faithfulness-sensitive numeric EXTRACTOR, not wiring. Details + a safe forward design below.

No source file was modified. No commit. No test was authored that pretends a safe source exists
(that would be LAW II fake-working / §9.4 placeholder).

---

## What the module needs (from `presentation_tables.py` + its Wave-2c brief)

`render_presentation_tables(*, claims, existing_report_md, ...)` coerces each claim via
`_coerce_claim`, which REQUIRES:
- `entity` (fallback `subject`) — non-empty
- `measure` (fallback `predicate`, `endpoint_phrase`) — non-empty
- `value` — non-empty, read via `_get(obj,"value")` → `_value_str` → **kept as a VERBATIM STRING;
  never parsed to float, never rounded, never reformatted** (module test #4: `"3,200.50"` must
  render exactly, and `"3,200.5"` / `"3,201"` must NOT appear).
- `unit`, `time_window`, `citation` — optional; `citation` (fallback `cite`, `marker`) is rendered
  verbatim in its own column, else `—`.

So the module needs **structured tuples carrying a VERBATIM value STRING and a real `[N]` citation**.

## The render seam (correctly identified — this part is not the blocker)

File: `src/polaris_graph/generator/multi_section_generator.py`, inside `_run_section` (the per-section
body producer). The section body is finalized here:

- `5688–5694` `verified_text, biblio_slice, resolved_emitted = resolve_provenance_to_citations_with_count(report.kept_sentences, evidence_pool, ...)` — strips `[#ev:...]` provenance tokens, emits `[N]`-cited prose, builds `biblio_slice`.
- `5699` `_normalize_citation_punctuation`, `5706` `_screen_uncited_numeric_sentences`, `5716` `_screen_render_chrome_prose`, `5741–5743` gap-stub, `5754–5757` `render_degraded_disclosures`, `5766–5777` B2 boundary line — all PRESENTATION-ONLY passes that run AFTER strict_verify.
- `5803` `return SectionResult(..., verified_text=verified_text, ...)`.

**The correct insert point** (were a safe source available) is immediately BEFORE the `return
SectionResult(...)` at ~5803, after all the presentation passes, guarded by
`presentation_tables_enabled()` and `not is_gap_stub`, calling `render_presentation_tables` ONCE for
the section and assigning `verified_text = result.text` **only when `result.changed` is True**
(OFF/no-comparable → `changed=False` → insert nothing → byte-identical). That call-site shape is
fine and faithfulness-safe. **The blocker is exclusively the `claims=` argument.**

## THE BLOCKER — no verbatim-valued, `[N]`-carrying structured numeric claim exists at the seam

Everything reachable at the seam falls into two buckets, and NEITHER supplies what the module needs:

**Bucket 1 — structured claim objects (`credibility_analysis.claims`): carry NO verbatim value.**
`credibility_analysis.claims` is a `list[AtomicClaim]` (`src/polaris_graph/synthesis/claim_graph.py:153`).
`AtomicClaim` fields are: `evidence_id, kind, subject, predicate, normalized_key, text, source_url,
source_tier, claim_cluster_id, domain, atom_uid`. There is **no `value` field and no `unit` field.**
- `getattr(atomic_claim, "value", "")` → `""` → `_coerce_claim` drops it. Feeding AtomicClaims → zero rows, no table.
- The number survives only inside `normalized_key` (a tuple; numeric value at index 3, unit at index 4 — this is exactly what Wave-2a's `numeric_comparator._VALUE_SLOT_INDEX=3` reads). But `normalized_key`'s value is a **rounded/normalized FLOAT** (`_normalized_key_numeric` rounds for merge stability), NOT the verbatim string. Feeding it would render a REFORMATTED/ROUNDED number → violates the module's verbatim invariant AND is the "insert an unverified number" the stop clause forbids (a rounded value is not the source's number).
- The upstream `ExtractedNumericClaim` (`src/polaris_graph/retrieval/contradiction_detector.py:733`) DOES have `subject/predicate/value/unit/endpoint_phrase` — but `value: float` is **also a float, not verbatim**, and this object is **flattened into `AtomicClaim` and discarded** before the generator; it is NOT retained at the multi_section seam.
- Additionally `credibility_analysis` is `None` on the flag-OFF / always-release-degrade path (`multi_section_generator.py:5148,5065` guards), so even the float is not always present.

**Bucket 2 — verified TEXT (`report.kept_sentences`, `biblio_slice.statement`, `verified_text`): verbatim numbers, but UNSTRUCTURED.**
- `report.kept_sentences` are `VerifiedSentence` objects (`clinical_generator/verified_report.py:75`): `sentence_text` (prose) + `provenance_tokens` (`[#ev:id:start-end]`). No entity/measure/value decomposition.
- `biblio_slice` is `list[{num, evidence_id, url, tier, statement}]` — gives a clean per-section `evidence_id → [N]` map and the cited span `statement`, but `statement` is free text.
- `verified_text` is `[N]`-cited prose. The verbatim numbers ARE here (post strict_verify), but only as free text.

To produce the module's required tuple `(entity, measure, VERBATIM-value, unit, [N])`, one must
**parse structured facets out of free text** (kept-sentence prose or the cited span) — i.e. run a
numeric+entity+measure EXTRACTOR. That is a new, faithfulness-sensitive step, with three concrete
lethal-direction risks (§-1.3, clinical-safety):
1. **Mis-attribution**: pairing a verbatim number with the wrong entity/measure label → a false
   like-with-like comparison in a table (the module groups by measure+unit and emits ≥2-row
   comparisons — a mis-labeled row manufactures a comparison the sources never made).
2. **Rounding**: any float-derived value breaks the verbatim invariant.
3. **Citation mis-pairing**: attaching an `[N]` that cites a different fact than the number.

None of these can be waved away by "the module copies verbatim" — the module faithfully copies
whatever tuple it is GIVEN; the faithfulness burden is entirely on the (missing) tuple builder.

## Why I did NOT ship a partial/stubbed wiring

- A call-site wired to a source that returns `[]` (pending the extractor) is a silent no-op stub → LAW II fake-working / §9.4 placeholder ban. Rejected.
- Feeding `normalized_key`'s rounded float → violates verbatim invariant + inserts an unverified number. Rejected.
- Feeding a fuzzy "value substring appears in `verified_text`" match → mis-attribution risk (a coincidental number under a wrong label). Rejected.
- Re-running a numeric extractor over spans/prose inside this "wiring" diff → NEW ~80–150 LOC faithfulness-sensitive module, exceeds the 200-LOC PR discipline and the "wiring, SURGICAL not rewrite" scope, and warrants its OWN brief + Codex+Fable diff gate, not improvisation here.

## Safe forward design (the real prerequisite — a separate Batch node)

Build `src/polaris_graph/generator/verified_numeric_claim_extractor.py` (own brief, own dual gate),
producing `VerifiedNumericClaim`s that are safe BY CONSTRUCTION, anchored to the verified render:
1. Input: `report.kept_sentences` (strict_verify-passed) + `evidence_pool` + `biblio_slice`.
2. For each KEPT verified sentence and each of its `[#ev:id:start-end]` provenance tokens, take the
   EXACT cited span text `evidence_pool[id][start:end]` (the same span strict_verify entailed).
3. Deterministically extract `(entity, measure, verbatim-value-STRING, unit)` **from that span**,
   keeping the value as the verbatim source substring (regex over the span, no float parse).
4. Citation `[N]` = `biblio_slice` num for that `evidence_id` (the resolver already mapped it).
5. Re-check each row: its verbatim value MUST be a decimal token present in the cited span (mirrors
   strict_verify check (c)); drop otherwise. Entity/measure content words must overlap the span
   (mirrors the ≥2-content-word overlap gate). This makes every emitted tuple co-present, verbatim,
   in ONE strict_verify-passed sentence's own cited span — faithfulness-neutral, no new engine.
6. Gate it, THEN the 2c-WIRING becomes the thin, safe call I described (insert-only-when-`changed`).

This keeps the ONLY hard gate the faithfulness engine, adds no cap/thinner/target (§-1.3), and never
lets a rounded or mis-attributed number reach the table.

## Files I have ALSO checked and they're clean

- `src/polaris_graph/generator/presentation_tables.py` — module contract confirmed: requires verbatim value STRING + `[N]`; float/rounded value would break test #4; missing value → row dropped.
- `src/polaris_graph/synthesis/claim_graph.py` (`AtomicClaim`, `_normalized_key_numeric`, `ClaimGraph`) — AtomicClaim has NO `value`/`unit` attr; value is a rounded float inside `normalized_key[3]`.
- `src/polaris_graph/retrieval/contradiction_detector.py` (`ExtractedNumericClaim`) — `value: float` (not verbatim) and not retained at the multi_section seam.
- `src/polaris_graph/generator/numeric_comparator.py` (Wave-2a sibling) — operates on `normalized_key` tuples to LICENSE a connective between INDEPENDENTLY-verified per-clause prose; it never emits a value, so its "already-verified float" is safe there but not reusable as a verbatim table value.
- `src/polaris_graph/generator/provenance_generator.py::resolve_provenance_to_citations_with_count` — returns `(verified_text, biblio_slice=[{num,evidence_id,url,tier,statement}], emitted_count)`; the clean `evidence_id→[N]`+span map for step 4 above.
- `src/polaris_graph/clinical_generator/verified_report.py` (`VerifiedSentence`) — `sentence_text` + `provenance_tokens` only; no structured numeric fields.
- `src/polaris_graph/clinical_generator/strict_verify.py` — the checks the re-check step 5 mirrors (decimal-in-span (c); content-word overlap (e)).
- Wave-2a (`~5166–5181,5243,5280`) and Wave-2d (`5300–5312`) insert points in `multi_section_generator.py` — confirmed the section-body composition + post-verify append pattern; the presentation-table call belongs after them, pre-`return SectionResult`.

## Recommendation

Escalate to the parent/Batch owner: the `2c-wiring` node has an unbuilt prerequisite
(`verified_numeric_claim_extractor`). Sequence it as its own dual-gated node, then this wiring is a
~15-line, provably-OFF-byte-identical, insert-only-when-`changed` call at ~line 5803. Do NOT ship a
rounded-float or fuzzy-substring source.
