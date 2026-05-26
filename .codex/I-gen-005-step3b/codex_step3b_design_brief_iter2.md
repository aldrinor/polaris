# Codex Step 3b DESIGN iter 2 — address 4 novel P1s

## §8.3.1 cap (verbatim)

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL findings. No drip-feeding.
- "Don't pick bone from egg" — reserve P0/P1 for execution risks.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE per §8.3.1.
- Verdict APPROVE iff zero NOVEL P0/P1.
```

## Iter 1 verdict → iter 2 responses

Codex iter-1: REQUEST_CHANGES, 4 novel P1s + 3 P2s. Excellent catches.

### P1.1: `[N]` bibliography markers parsed as numbers by validator

After `resolve_provenance_to_citations` runs, the text has `[1]`, `[2]` etc. citation markers. `_NUMBER_RE` in atom_refusal_validator matches `1`, `2` as numbers — narrative sentences with `[1]` citation get flagged as Trigger B (number alone) → required atom citation falsely.

**Iter-2 fix**: pre-strip `[N]` markers AND `[ev_XXX]` AND `atom_NNN` from the sentence COPY used by claim detection BEFORE running `requires_atom_citation`. The original sentence stays intact for record-keeping. New helper in atom_refusal_validator:

```python
_BIBLIO_MARKER_RE = re.compile(r"\[\d+\]")
_EV_TOKEN_FOR_STRIP_RE = re.compile(r"\[?ev_\d+(?::\d+-\d+)?\]?")
_ATOM_TOKEN_FOR_STRIP_RE = re.compile(r"\(?atom_\d{3,}(?:,\s*atom_\d{3,})*\)?")

def _strip_citation_tokens_for_detection(sentence: str) -> str:
    s = _BIBLIO_MARKER_RE.sub(" ", sentence)
    s = _EV_TOKEN_FOR_STRIP_RE.sub(" ", s)
    s = _ATOM_TOKEN_FOR_STRIP_RE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()
```

Used in `requires_atom_citation` AND in `_NUMBER_RE.findall` for value extraction. NOT used for citation parsing (`extract_atom_citations` still sees originals).

### P1.2: Destructive atom_NNN strip before strict_verify breaks validator

If I strip atom_NNN from the rewritten text and pass that to strict_verify, the kept_sentences will be the stripped versions — verified_text becomes atom-free — validator sees no atom citations on every sentence → all factual claims refused (false positive).

**Iter-2 fix**: do NOT destructively strip. Instead, pre-process inside strict_verify's numeric-matching pass (or upstream) to skip atom_NNN tokens. Concretely: pass a SEPARATE clean copy to strict_verify ONLY for the numeric-check portion, while strict_verify continues to operate on the original sentence for the kept/dropped decision.

Cleaner approach: extend strict_verify itself to recognize and ignore atom_NNN tokens during numeric extraction. Touches strict_verify code (small addition). Alternative: pre-process rewritten BEFORE strict_verify and ALSO transform the strict_verify output to restore atom_NNN tokens.

Recommended: small change to `strict_verify`'s number-extraction step that excludes atom_NNN and ev_XXX tokens. Single-line addition. Want me to propose the exact diff in iter-3?

### P1.3: Line 1509 hook too early — later mutations rewrite verified_text

You correctly noted that fact_dedup (cross-section pass), M44/M47 regens, and final citation remapping can rewrite `sr.verified_text` AFTER line 1509. Validator results would be stale.

**Iter-2 fix**: identify the LAST mutation site. Need to grep multi_section_generator for sites that mutate `sr.verified_text` post-SectionResult-construction.

My read: fact_dedup runs in the orchestrator AFTER `_generate_single_section` returns SectionResult. The dedup pass may rewrite `verified_text`. So the validator must hook AFTER fact_dedup + AFTER the final citation remap.

Proposed hook: in the orchestrator's main loop, after `_generate_single_section` returns AND after the global cross-section fact_dedup + final remap have completed. Concretely: at the point where MultiSectionResult is assembled and `report.md` is about to be written.

The validator runs on `sr.verified_text` for each section AT THAT POINT. SectionResult is updated with atom_validation_result. Then `report.md` is written.

This is a bigger refactor than line 1509 but architecturally correct.

### P1.4: atom_NNN strip must apply to ALL strict_verify call sites

Repair retry, M-41c re-verify, possibly others. Any strict_verify call receiving atom_NNN-bearing prose needs the same numeric-ignore.

**Iter-2 fix**: if strict_verify is updated to ignore atom_NNN/ev_XXX in numeric extraction (per P1.2), ALL call sites get the fix for free. That's the cleanest path. If we go the pre-process-input-only route, every call site needs the pre-process.

Recommended: update strict_verify itself. Single change, all call sites benefit.

## Updated P2s addressed

- Add `atom_catalog: dict[str, ClaimAtom]` + `catalog_status: str` ("ok" / "extractor_error" / "empty") as transient fields on SectionResult.
- gaps.json totals include `atom_validation_mode` per section + per-document totals + catalog_status per section.
- `validate_section` preserves paragraph boundaries: split on `\n\n+`, validate per paragraph, join with `\n\n`.

## Open questions for iter-2

### Q1: Validator hook precise placement

After mapping the orchestrator's post-_generate_single_section flow (fact_dedup, M44/M47, final citation remap), what's the safest hook point?

Candidates:
- Inside `_generate_single_section` at the very end (catches per-section, but misses cross-section fact_dedup mutations)
- In the orchestrator after fact_dedup BUT before final citation remap
- In the orchestrator AFTER final citation remap (truly final state)

Recommendation: AFTER final citation remap. The validator sees the EXACT text that ships to report.md.

### Q2: strict_verify modification scope

Update `strict_verify` to skip atom_NNN/ev_XXX/[N] markers in numeric extraction. This is a touch to existing production code. Is this acceptable as part of Step 3b PR, or should it be a separate prerequisite PR?

### Q3: atom_NNN preservation through fact_dedup

fact_dedup may rewrite sentences (consolidate). Does dedup preserve atom_NNN tokens in the rewritten consolidated sentences, or strip them? If strips, the validator at the post-dedup hook sees no atoms.

I'll need to grep fact_dedup to confirm. Likely it preserves tokens (it operates on string-equal grouping, not LLM rewrite). But worth verifying.

## Updated output schema

```
verdict: APPROVE_DESIGN | REQUEST_CHANGES

p1_1_biblio_markers_strip_correct: YES | NO

p1_2_non_destructive_strict_verify_approach: STRICT_VERIFY_MODIFICATION | PRE_PROCESS_ONLY | OTHER
  if_strict_verify_modification:
    acceptable_in_same_pr: YES | NO

p1_3_hook_at_final_remap: YES | NO
  if_no: |
    (alternative hook point)

p1_4_apply_via_strict_verify_modification: YES | NO

section_result_fields_with_catalog_and_status: YES | NO

paragraph_preservation_correct: YES | NO

gaps_json_totals_include_status: YES | NO

novel_p0: [...]
novel_p1: [...]
continuing_p0: [...]
continuing_p1: [...]
p2: [...]

ready_to_implement: YES | NO
```

EMIT YAML ONLY.
