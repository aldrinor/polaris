# Codex iter 1 — atom_refusal_validator.py diff review

## §8.3.1 cap directive (verbatim)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Context

You APPROVE_DESIGN'd refusal/gap rendering (`codex_refusal_design_verdict.txt`):
- Approach C hybrid (prompt + post-hoc)
- STRICT layer: missing/invalid atom_id → REPLACE sentence with refusal
- SOFT layer: value mismatch → logged_only
- Sentence-level granularity
- III_both: inline refusal markers + gaps.json sidecar
- Quantitative-claim detector: Trigger A (number + endpoint) + Trigger B (number alone, excluding admin) + qualitative comparative
- Narrative allowed: mechanism, trial design, eligibility, hedges
- Multi-atom: ALL_REQUIRED
- new_module: src/polaris_graph/generator/atom_refusal_validator.py
- consumer: src/polaris_graph/generator/multi_section_generator.py (Step 3 — not in this PR)

I implemented per your spec. Commit `2eaef4e9` on PR #905.

## What I shipped

`src/polaris_graph/generator/atom_refusal_validator.py` (~430 lines):

### Public surface
- `RefusalAction` enum: REFUSED / ALLOWED / LOGGED_ONLY
- `RefusalReason` enum: 6 reasons matching your schema
- `GapRecord` dataclass: per-sentence record matching your gaps.json claim schema
- `SectionValidationResult` dataclass: per-section result with rendered_text + gap_records + counts
- `requires_atom_citation(sentence) -> (bool, trigger_reason)` — claim detector
- `extract_atom_citations(sentence) -> list[str]` — atom_NNN extraction
- `extract_ev_citations(sentence) -> list[str]` — [ev_XXX] extraction
- `has_ev_citation_for_factual_claim(sentence) -> bool` — ev-for-claim detector
- `split_sentences(text) -> list[str]` — decimal-aware split
- `validate_sentence(sent, idx, sec_id, sec_title, catalog) -> GapRecord`
- `validate_section(text, sec_id, sec_title, catalog) -> SectionValidationResult`
- `build_gaps_document(doc_id, sections) -> dict` — gaps.json schema
- `write_gaps_sidecar(out_dir, doc_id, sections) -> Path` — writes gaps.json

### Trigger detector

Priority order:
1. Narrative category match → False (unless qual-comparative or outcome-number combo overrides)
2. Trigger A: number + endpoint vocab term → True
3. Qualitative: comparative phrase + endpoint → True (no number needed)
4. Trigger B: numbers present, less than fully-admin-explained → True
5. Otherwise → False

Number regex uses non-letter context (same as atom_extractor) to avoid
matching "1" inside "HbA1c".

Admin exclusion: `phase \d+`, `\d+ weeks`, `\d+ mg`, `n=\d+`, etc.

Qualitative regex captures "greater <noun> than", "superior to",
"reduced/increased/decreased/elevated", "compared to/with", "versus/vs".

Narrative categories: mechanism, trial design, eligibility, hedges,
limitations, cross-trial synthesis.

### Validation flow

```python
def validate_sentence(sentence, ...):
    cited_atoms = extract_atom_citations(sentence)
    requires_atom, claim_trigger = requires_atom_citation(sentence)

    # Non-claim narrative with no atoms → ALLOWED
    if not requires_atom and not cited_atoms:
        return ALLOWED

    # Requires atom but no atom cited
    if requires_atom and not cited_atoms:
        if has_ev_citation_for_factual_claim(sentence):
            return REFUSED(EV_CITATION_FOR_CLAIM)
        return REFUSED(MISSING_ATOM_CITATION)

    # Validate ALL cited atoms exist (ALL_REQUIRED)
    missing = [a for a in cited_atoms if a not in catalog]
    if missing:
        return REFUSED(INVALID_ATOM_ID, missing_atoms=missing)

    # SOFT mismatch check: cited atom value not present in sentence text
    soft_notes = []
    for aid in cited_atoms:
        atom = catalog[aid]
        atom_val_stripped = atom.value.lstrip("-−")
        if atom_val_stripped and atom_val_stripped not in sentence:
            soft_notes.append(f"atom={aid} value={atom.value!r} not in sentence")
    if soft_notes:
        return LOGGED_ONLY(SOFT_MISMATCH, kept_text=sentence)

    return ALLOWED
```

### Refusal rendering

When refused, the sentence is REPLACED with the refusal template from
atom_extractor.format_refusal_for_missing_atom (your APPROVE_DESIGN
wording). The template substitutes detected endpoint, entity, timepoint
from sentence text (via _detect_*_in_sentence helpers).

### gaps.json schema (matches your APPROVE_DESIGN)

```json
{
  "document_id": "...",
  "generated_at": "ISO-8601",
  "sections": [
    {
      "section_id": "...",
      "section_title": "...",
      "claims": [
        {
          "claim_id": "sec.s000",
          "sentence_index": 0,
          "original_sentence": "...",
          "rendered_text": "...",
          "action": "refused|allowed|logged_only",
          "reason": "missing_atom_citation|invalid_atom_id|...",
          "cited_atoms": [...],
          "missing_atoms": [...],
          "detected_endpoint": "...|null",
          "detected_entity": "...|null",
          "detected_timepoint": "...|null",
          "detected_values": [...],
          "notes": "...|null"
        }
      ],
      "summary": {
        "total_sentences": N,
        "refused": N,
        "soft_mismatch": N,
        "allowed": N
      }
    }
  ],
  "totals": { same shape as summary }
}
```

## Tests (30/30 PASS)

`tests/polaris_graph/test_atom_refusal_validator.py` (~480 lines):

- **Claim detector** (8 tests): triggers A/B/qualitative, narrative passes, admin exclusions (phase, week, dose)
- **Citation parsing** (5 tests): single + multiple atom_NNN, ev_XXX, has_ev_citation_for_factual_claim
- **STRICT layer** (5 tests): missing citation, invalid atom_id, ev for claim, multi-atom ALL_REQUIRED, all-valid allowed
- **SOFT layer** (1 test): value mismatch logged_only
- **Narrative** (2 tests): mechanism + trial design allowed
- **Section end-to-end** (3 tests): mixed sentences, counts, rendered_text replacement
- **gaps.json** (3 tests): build_gaps_document schema, claim record schema, write_gaps_sidecar
- **Sentence splitter** (1 test): decimal-aware

Combined with atom_extractor: 82/82 tests pass.

## Design questions for your review

### Q1: Is the trigger order correct?

Currently:
1. Narrative override check (allows narrative if no outcome-number/qual)
2. Trigger A
3. Qualitative
4. Trigger B

You may want Qualitative BEFORE Trigger A so "reduced HbA1c by 2.30" reports as "trigger_A" (number+endpoint) rather than "trigger_qualitative". Currently the more-specific A wins which seems right.

### Q2: Edge case — eligibility ranges with numbers

"Eligible patients had inclusion criteria of HbA1c between 7.0 and 10.0."

- has_outcome_number = True (numbers 7.0, 10.0 + endpoint HbA1c)
- Narrative override BLOCKED by has_outcome_number
- Returns True (Trigger A)

This is over-strict — eligibility-range numbers aren't outcome claims. Is the trade-off acceptable, or should I add an "inclusion criteria" detector that overrides Trigger A?

### Q3: SOFT mismatch — value detection

Current check: `atom.value.lstrip("-−") in sentence`. So atom value "-2.30" matches sentence "2.30" but also matches "12.30", "32.30", etc. Should I tighten to word-boundary check? E.g. `re.search(rf"\b{re.escape(atom_val)}\b", sentence)`.

### Q4: Detected endpoint/entity/timepoint for refusal template

In `_build_refusal_record`, I extract these from sentence text using the same vocab regexes. If detection fails, refusal template uses "this outcome" / "" / "" defaults. Is that the right fallback, or should refusal be more specific (e.g., refuse with literal sentence snippet)?

### Q5: SOFT layer scope — is current scope enough?

Currently SOFT only checks value-not-in-sentence. Your design verdict listed additional soft checks:
- "Log endpoint/entity/timepoint/comparator mismatch when detectable"
- "Log suspected partial coverage in multi-number sentences"

I deferred those to keep this iter focused on the STRICT contract. Want me to add them in iter-2, or are they P2 follow-ups?

### Q6: Multi-atom + multiple numbers

A sentence with N atoms cited and M numbers — currently I don't pair them. Should I detect "atom_001 has value X but no X in sentence; atom_002 has value Y and Y is in sentence; therefore atom_001 is suspect"? That's the "partial coverage" check.

### Q7: Empty catalog edge case

If V4 Pro receives empty atom catalog (no atoms extracted for section), EVERY claim sentence will be REFUSED. That's correct per design — but the report becomes pure refusal blocks. Is that the right behavior, or should we add a section-level "refused entirely" header?

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES

trigger_detector_correctness: YES | NO | PARTIAL
  if_not_yes: |
    (specific case + repro)

strict_layer_complete: YES | NO
  missing_check: |
    (which reason)

soft_layer_scope_for_iter1: APPROPRIATE | TOO_NARROW | TOO_BROAD
  if_too_narrow: |
    (which additional checks to add now vs P2 follow-up)

refusal_template_substitution_correct: YES | NO
  fallback_strategy_correct: YES | NO

gaps_json_schema_matches_design: YES | NO
  if_no: |
    (drift)

sentence_split_decimal_aware: YES | NO

edge_cases_remaining:
  - id: ...
    severity: P0 | P1 | P2
    repro: |
      ...
    expected: |
      ...

novel_p0: [...]
novel_p1: [...]
p2: [...]
p3: [...]

approval_to_proceed_to_step_3: YES | NO
  if_no: |
    (specific blocker before V4 Pro `_call_section` integration)

convergence_call: continue | accept_remaining
```

EMIT YAML ONLY. Diff is at `.codex/I-gen-005-refusal/codex_diff_iter1.patch` (1055 lines).
