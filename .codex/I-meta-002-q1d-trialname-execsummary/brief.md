HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings. Reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

RULE NOW — emit the YAML verdict block FIRST. APPROVE this CONCRETE plan or REQUEST_CHANGES with specifics.
**TOP SCRUTINY — this MODIFIES strict_verify's trial-name gate (the clinical-safety chokepoint).** The issue
asks to LOOSEN it; the code comment documents that the loosening it literally requests (scan direct_quote)
is what CAUSED the FABRICATED-#20 hole. This brief proposes a NARROW loosening that rescues the false-drop
WITHOUT re-opening that hole, and a MANDATORY locked-FAIL regression. NO SPEND offline.

## Output schema (emit FIRST)
```yaml
verdict: APPROVE | REQUEST_CHANGES
p0: [...]
p1: [...]
p2: [...]
required_changes: [...]
convergence_call: accept_remaining
```

# Codex brief-gate (iter 1) — PR12: trial-name verifier body-fallback, locked-FAIL preserved (#949 part a)

## THE TENSION (front-loaded — rule on this directly)
Issue #949(a): the verifier drops well-framed CORRECT prose on `trial_name_mismatch` when the evidence row's
TITLE/statement lacks the literal trial token (a fully-framed SURPASS-2 sentence was dropped because the row's
title field didn't contain "SURPASS-2"). It asks to "match against evidence body, not just title."
BUT `provenance_generator._trial_names_in_evidence` (line 872) DELIBERATELY excludes `direct_quote` — DR pass
7 found that scanning the body is TOO PERMISSIVE: a SURMOUNT-3 paper's `direct_quote` cites SURMOUNT-1 as a
prior reference, which let a FABRICATED "In SURMOUNT-1, ..." sentence pass when bound to ev_015 (the SURMOUNT-3
paper). Naively "scan the body" re-opens FABRICATED #20 (clinical-safety LETHAL).

## GROUNDED FACTS (verified; do not re-explore)
- `provenance_generator.py:872 _trial_names_in_evidence(ev)` scans `statement`+`title` ONLY (AUTHORITATIVE
  identity), NOT `direct_quote`. Gate at :1117-1130: `sentence_trials = extract_trial_names(sentence)`;
  `evidence_trials = ∪ _trial_names_in_evidence(cited rows)`; if `sentence_trials` non-empty and
  `sentence_trials ∩ evidence_trials == ∅` → `trial_name_mismatch` failure (sentence dropped).
- `extract_trial_names` extracts SURPASS-N / SURMOUNT-N / STEP-N / SURMOUNT-CN (numbered, case-insensitive)
  + ALLCAPS acronyms (SELECT/LEADER/SUSTAIN/PIONEER/REWIND/AWARD/GRADE).
- Locked regression EXISTS: `tests/polaris_graph/test_m25_trial_name_match.py::
  test_pass7_regression_direct_quote_mention_insufficient` — ev_015 title/statement=SURMOUNT-3, direct_quote
  mentions BOTH SURMOUNT-1 + SURMOUNT-3; a SURMOUNT-1 sentence bound to it MUST be rejected. THIS TEST MUST
  STAY GREEN (the binding clinical-safety invariant).

## CONCRETE PROPOSAL — title-authority + CITED-SPAN fallback (NOT whole body, NOT a count heuristic)
The naive "scan direct_quote" re-opens FABRICATED #20. A single-trial body-count heuristic ALSO fails two
ways (a one-trial prior-reference body launders; the real SURPASS-2 paper contextualizes vs SURPASS-1/-3 so
its body has ≥2 trials and the count heuristic still drops the correct sentence). And pure span-scoping ALONE
breaks the lock (the pass-7 fixture cites the WHOLE direct_quote `0-len`, so span==body==contains SURMOUNT-1).
The robust rule COMBINES title authority (preserves the lock) with a CITED-SPAN (not whole-body) fallback:

Per cited row, the row's authoritative trial set for a sentence's tokens =
- `title_trials = extract_trial_names(statement) | extract_trial_names(title)` IF NON-EMPTY — the title/
  statement DECLARES the row's identity; the span is NOT consulted, so a SURMOUNT-3 paper can never match a
  SURMOUNT-1 sentence regardless of what its body/span contains; ELSE (title names no trial at all)
- `∪ extract_trial_names(direct_quote[tok.start:tok.end])` over THIS row's cited tokens — the trial named in
  the CITED SPAN only (the exact span already sliced for the numeric check at provenance_generator.py:1051),
  NOT the whole body. The results span being cited names the trial whose result it states.
- Gate otherwise unchanged: `evidence_trials = ∪` over rows; `sentence_trials ∩ evidence_trials == ∅` →
  `trial_name_mismatch`.

**Why this is safe (rule on each):**
1. Locked-FAIL preserved by TITLE AUTHORITY (not span): pass-7 ev_015 title=SURMOUNT-3 → `title_trials`
   non-empty → span IGNORED → {SURMOUNT-3} → SURMOUNT-1 sentence FAILS even though the cited span (whole
   body) contains SURMOUNT-1. THIS is why title-authority must gate the span, not the other way around.
2. One-reference laundering closed: a review row whose title names no trial AND whose body mentions
   SURMOUNT-1 once as a prior reference OUTSIDE the cited results span → the cited span does not contain
   SURMOUNT-1 → not matched → a fabricated SURMOUNT-1 sentence FAILS. (Span scope, not body scope, is what
   closes the advisor-flagged one-reference hole.)
3. SURPASS-2 false-drop rescued — including the real paper: a SURPASS-2 paper whose title lacks the token,
   whose intro references SURPASS-1/-3 (so whole-body has 3 trials), but whose CITED RESULTS span names
   SURPASS-2 → span fallback gives {SURPASS-2} → matches. The count heuristic FAILED this; cited-span SOLVES it.
- Residual (rule on it): title-silent + the cited span genuinely contains a trial name AND that trial's
  number AND ≥2 shared content words (the numeric + overlap checks already gate the same span). At that point
  the span is genuinely stating that trial's result, so the citation is grounded in what the source says —
  acceptable, and strictly safer than the status quo which drops the legit SURPASS-2 entirely.
- Default-ON kill-switch `PG_VERIFY_TRIAL_NAME_SPAN_FALLBACK` (default "1"): off → exact current title-only
  behavior (byte-identical). RULE: default-ON (rescue recall) or default-OFF (conservative until live smoke)?

## SCOPE — verifier ONLY this PR (exec-summary is a separate sibling)
#949(b) (add a verified-only executive-summary block to report.md) is LOWER-risk and COSMETIC; mixing it
into a strict_verify-core diff makes review harder. I will ship it as a SEPARATE follow-up PR (digest of
already-verified body sentences, verbatim, zero new claims). This PR is the verifier change ONLY.

## Tests (offline, NO SPEND — clinical-safety MANDATORY)
- **MANDATORY locked-FAIL #1 (binding, title authority):** `test_pass7_regression_direct_quote_mention_
  insufficient` STAYS GREEN — ev_015 title=SURMOUNT-3, cited span = whole body containing SURMOUNT-1 →
  SURMOUNT-1 sentence REJECTED (title authority beats span).
- **MANDATORY locked-FAIL #2 (NEW, advisor-flagged one-reference hole):** title names NO trial; body mentions
  SURMOUNT-1 ONCE as a prior reference OUTSIDE the cited results span; the cited span (the SURMOUNT-3 result)
  does NOT contain SURMOUNT-1 → a fabricated SURMOUNT-1 sentence REJECTED (span scope, not body scope).
- **Rescue (NEW):** SURPASS-2 paper, title lacks the token, body intro references SURPASS-1/-3 (≥2 trials in
  body), but the CITED RESULTS span names SURPASS-2 → a SURPASS-2 sentence PASSES (was dropped; the count
  heuristic would still drop it — proves cited-span is required).
- Kill-switch OFF → exact title-only behavior (the rescue case fails again; byte-identical to today).
- All existing `test_m25_trial_name_match.py` cases stay green.

## Constraints / frozen
snake_case; explicit imports; no except:pass; fail-closed. Untouched: the rest of strict_verify (decimal/
content-overlap/evidence-id/span checks), provenance core, the gate's structure. ≤80 LOC. NO SPEND.

## The real risks to rule on
1. Does title-authority + cited-SPAN fallback re-open FABRICATED #20 in ANY case? (Claim: no — title naming
   a trial ALWAYS gates and is never overridden by span; the lock is preserved by title authority, proven by
   pass-7 staying green with a whole-body citation.)
2. Is cited-SPAN (vs whole-body, vs single-trial-count) the right fallback scope? (Claim: yes — it closes the
   one-reference laundering hole (ref outside the cited span) AND rescues the real multi-trial-body SURPASS-2
   paper (cited results span names the actual trial), which the count heuristic could not.)
3. Is the title-silent residual (cited span genuinely names trial + its number + ≥2 overlap) acceptable, or
   does it need an additional guard?
4. Default-ON vs OFF for a strict_verify loosening — your call.
5. Are the TWO locked-FAIL regressions (title-authority + one-reference span) sufficient adversarial coverage?

APPROVE iff this loosens trial-name matching ONLY via title-authority + cited-SPAN fallback (title-names-a-
trial → span ignored; title-silent → trial must appear in the CITED span, not the whole body), keeps the
pass-7 locked-FAIL regression GREEN, adds the one-reference-span adversarial locked-FAIL + the real-paper
rescue test, is kill-switchable, leaves the rest of strict_verify untouched, and is NO-SPEND offline.
