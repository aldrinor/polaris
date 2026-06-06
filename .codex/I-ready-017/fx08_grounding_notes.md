# FX-08 (#1112) grounding notes — Mirror pass-2 tolerant parse + determinism + dedup

INDEP lane. Base = current HEAD bot/I-ready-017-faithfulness (FX-07 leg1 verified, 50f0d5d4).

## ✅ LOAD-BEARING SAFETY INVARIANT — VERIFIED against real code (mirror_adapter.py)
The plan's claim holds: pass-1 `<co>` grounding gate fires BEFORE pass-2.
- `mirror_adapter.py:337` `grounded_spans = _extract_citations(pass1_response, valid_doc_ids)`
- `:338-344` `if not grounded_spans: raise MirrorCitationError(...)` — the ONLY grounding gate, fires here.
- `:363-368` pass-2 (`build_mirror_pass2_request` → `transport.complete` → `_parse_pass2`) runs AFTER.
- `:378` `if not verify_pass2_binding(pass1, pass2):` fail-closed — pass-2 must classify the SAME
  (answer+citations) artifact via expected_content_hash.
**Conclusion:** broadening pass-2 parsing (PART A) CANNOT create a false-accept — an ungrounded
claim already raised MirrorCitationError before pass-2 runs, and content_hash binding ties pass-2 to
the grounded pass-1. FX-08 PART A is faithfulness-safe. (NEGATIVE-PROOF test still required: a
genuinely-ungrounded pass-1 STILL fails closed.)

## PART A — tolerant pass-2 recovery (mirror_adapter.py)
- `_coerce_classification_value` (~:210-228): coerce int/float/bool → str(value) (json_repair
  philosophy); keep dict sorted-key serialization; return None ONLY for empty-string/empty-collection.
- `_parse_pass2` (~:231-250 / :289-294): when body is a non-empty JSON object with no
  `classification`/alternate key (e.g. `{domain:..,field:..}`), serialize the WHOLE object as the
  non-gating verdict string instead of raising MirrorParseError; raise ONLY for non-JSON body and
  truly-empty `{}` (`{}` → observable raise OR sentinel 'unclassified' — Codex picks).
- Rewrite test_mirror_adapter.py:171,424 (justified contract change, NOT assertion-relaxation).
- NEED: read _coerce_classification_value + _parse_pass2 (mirror_adapter.py:200-300).

## PART B — determinism + dedup
- `openrouter_role_transport.py:485-528`: add temperature=0 + seed=PG_VERIFIER_SEED (env, LAW VI).
- claim-level dedup keyed by (normalized_sentence + sorted evidence_ids + sorted spans); run pipeline
  ONCE per distinct key, fan verdict out. **Dedup hook PINNED to sweep_integration.py** (the 4-role
  batch ENTRY), NOT role_pipeline.py (avoids FX-11/BUG-10b same-file collision). If Codex prefers
  role_pipeline.py, serialize FX-08 behind FX-11.
- NEED: read openrouter_role_transport.py:485-528 + sweep_integration.py batch entry.
- LOC budget ~60-110; if dedup threatens 200-LOC cap, ship tolerant-parse + temp/seed first, dedup follow-up.

## Smoke + §-1.1 (per plan)
- Unit: the EXACT pass-2 bodies (`{"classification":0}` 00-028, `{}` 05-004, `{"domain":..}` 00-078);
  non-empty → recovered string for grounded pass-1; non-JSON raises; determinism (byte-identical
  claims → identical verdict); dedup (identical claims → pipeline once).
- §-1.1 on re-run: byte-identical (sentence+ids+spans) share ONE verdict; 17 mirror-failed-closed no
  longer UNSUPPORTED-on-shape; NEGATIVE PROOF — ungrounded pass-1 still fails closed.

## Resume: author PART A (mirror_adapter) first + tests + NEGATIVE-PROOF test, then PART B (temp/seed + dedup). ONE gate when done.
