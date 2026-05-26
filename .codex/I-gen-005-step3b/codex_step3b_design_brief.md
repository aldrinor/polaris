# Codex — Step 3b DESIGN brief (full post-hoc atom validator pipeline wiring)

## §8.3.1 cap directive (verbatim)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings. No drip-feeding.
- "Don't pick bone from egg" — reserve P0/P1 for execution risks.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE per §8.3.1.
- Verdict APPROVE iff zero NOVEL P0/P1.
```

## Where we are

PR #905 MERGED 2026-05-26 — landed prompt-side atom catalog injection (Step 3a) + atom_refusal_validator + claim_atom_extractor on polaris.

You explicitly recommended Step 3b as SEPARATE_PR with these P2s:
1. preserve exact `_call_section` atom catalog/atom_NNN numbering
2. strip `atom_NNN` before strict_verify numeric matching
3. start logging-only behind a flag

This brief asks design questions before implementation.

## Existing pipeline (post-_call_section)

`_call_section` returns `(raw, in_tok, out_tok)` then:
- `_rewrite_draft_with_spans(raw, evidence_pool)` produces `rewritten`
- `strict_verify(rewritten, evidence_pool)` produces `report` with kept/dropped SVs
- `repair_dropped_section_sentences(...)` re-verifies repaired sentences
- M-41c policy filter drops under-framed trial-name claims
- `resolve_provenance_to_citations(kept_sentences, evidence_pool)` produces `verified_text`
- SectionResult returned at line 1517

## Step 3b proposed architecture

### Hook point

Run `validate_section(verified_text, section_id, section_title, catalog)` right after `verified_text = _normalize_citation_punctuation(verified_text)` at line 1509. The catalog must be threaded through from `_call_section`.

### Catalog threading

Change `_call_section` signature to also return the catalog:
```
async def _call_section(...) -> tuple[str, int, int, dict[str, ClaimAtom]]
```

If atom extraction errored (fail-soft fallback fires), return `{}`.

### atom_NNN strip before strict_verify

Before passing `rewritten` to `strict_verify`, strip `atom_\d+` tokens so the verifier does not parse "003" inside "atom_003" as a number that must appear in cited spans. The rewritten draft KEPT on SectionResult preserves atom_NNN so the validator can read them later.

### PG_ATOM_REFUSAL_MODE env flag

Three values:
- `off` (default — pre-Step-3b behavior, no validator)
- `log_only` (run validator, write gaps.json, do not replace prose)
- `strict` (replace refused sentences inline + write gaps.json)

### SectionResult new fields

```
atom_validation_result: SectionValidationResult | None = None
refusal_count: int = 0
soft_mismatch_count: int = 0
atom_validation_mode: str = "off"
```

### gaps.json sidecar

Pipeline-level write at end of generation. Path: `outputs/<sweep_id>/<vector_id>/gaps.json` next to `report.md`.

### Refusal sentence formatting

Replace 1-for-1; refusal sentence does not carry `[ev_XXX]` (it is a disclosure, not an evidence-cited claim).

## Open design questions

### Q1: Catalog rebuild vs threading

I propose changing `_call_section` return signature. Alternative: rebuild at validation site from same `evidence_subset` (deterministic since `build_atom_catalog` uses a global counter in order). Which approach?

### Q2: Strip atom_NNN scope

Apply only to the initial `strict_verify(rewritten)` call, or also to repair re-verification? Repair generates new sentences from raw evidence so they should not have atom_NNN.

### Q3: Validator hook BEFORE or AFTER M-41c filter?

I prefer AFTER M-41c (cleaner separation: M-41c is policy on cited claims; validator enforces atom contract). Disagree?

### Q4: Empty-catalog behavior

If `evidence_subset` produces zero atoms, catalog is `{}`. In `strict` mode every claim-detect sentence refuses. In `log_only` section reads as-is but gaps.json shows all flagged. Add a "no_catalog_section_skip" flag, or keep honest-mostly-refusal?

### Q5: Sweep script integration

`run_honest_sweep_r3.py` is the active sweep entry. Modify it directly to call `write_gaps_sidecar`, or add an intermediate generator-level helper?

### Q6: Cost concern

Catalog is already built inside `_call_section` (Step 3a). Step 3b adds no NEW extraction call — only consumes existing catalog via signature change. Validator adds regex sweep per sentence. Confirm no incremental cost concern?

## Output schema

```
verdict: APPROVE_DESIGN | REQUEST_CHANGES

catalog_threading_approach: SIGNATURE_CHANGE | REBUILD_AT_VALIDATOR | TELEMETRY_SINK
  reasoning: ...

atom_strip_scope: INITIAL_VERIFY_ONLY | INITIAL_AND_REPAIR | OTHER

validator_hook_position: BEFORE_M41C | AFTER_M41C | BOTH
  reasoning: ...

empty_catalog_behavior: ALWAYS_RUN | SKIP_SECTION_WHEN_EMPTY | FLAG_DEPENDENT
  reasoning: ...

sweep_integration: DIRECT_IN_SWEEP | GENERATOR_HELPER | OTHER

flag_default: off | log_only | strict
  reasoning: ...

section_result_fields_correct: YES | NO

gaps_json_location: SECTION_NEXT_TO_REPORT | SWEEP_LEVEL | BOTH

refusal_sentence_no_ev_citation_correct: YES | NO

paragraph_integrity_strategy: ONE_FOR_ONE_REPLACE | REFLOW | DROP_PARA_IF_MOSTLY_REFUSED

novel_p0: []
novel_p1: []
p2: []

ready_to_implement: YES | NO
```

EMIT YAML ONLY.
