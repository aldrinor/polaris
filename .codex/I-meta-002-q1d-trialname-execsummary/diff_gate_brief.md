HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL findings. Reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## iter-1 was APPROVE (safety-core confirmed). The single P2 is now FIXED — re-gate the regenerated patch:
- iter-1 P2 (Key Findings citation-retention format-sensitive: `claim. [1]` could detach): the sentence
  extractor now MATCHES (not splits) with `_SENTENCE_RE = .+?[.!?](?:\s*\[\d+\])*(?=\s+[A-Z(\[\d]|\s*$)` — it
  keeps trailing `[N]` citations attached (`claim. [1]` AND `claim [1].`) AND the boundary lookahead prevents
  stopping inside a decimal ("2.1" — period followed by a digit, no whitespace, is not a boundary). New test
  `test_trailing_citation_form_stays_attached`; the decimal-preservation cases stay green. 24 tests PASS.
- The safety-core trial-name change is UNCHANGED since iter-1 APPROVE (title authority + cited-span fallback,
  both locked-FAILs green). Only the extractive exec-summary helper's sentence regex changed.

RULE NOW — emit the YAML verdict block FIRST. Read ONLY the patch at
`.codex/I-meta-002-q1d-trialname-execsummary/codex_diff.patch` (5 files, +298/-4). **TOP SCRUTINY — this
MODIFIES strict_verify's trial-name gate (clinical-safety chokepoint).** Verify the loosening cannot re-open
FABRICATED #20. NO SPEND.

## Output schema (emit FIRST)
```yaml
verdict: APPROVE | REQUEST_CHANGES
p0: [...]
p1: [...]
p2: [...]
required_changes: [...]
convergence_call: accept_remaining
```

# Codex diff-gate (iter 1) — PR12: trial-name verifier body→cited-span fallback + verified exec-summary (#949)

Verify the diff implements the brief-gate-APPROVE'd design (brief APPROVE iter 1).

## What to verify (a) — the safety-core change
1. New `_trial_names_for_cited_row(ev, cited_spans)`: returns `title_trials` (statement|title) if NON-EMPTY
   — span NOT consulted (TITLE AUTHORITY); ELSE (and only if `_trial_name_span_fallback_enabled()`) the union
   of `extract_trial_names(direct_quote[start:end])` over THIS row's cited spans ONLY (never whole body,
   never cross-row). Empty title + flag-off → `title_trials` ({}).
2. Gate rewired (provenance_generator ~:1117) to group `tokens` by `evidence_id` into `spans_by_ev`, then
   `evidence_trials = ∪ _trial_names_for_cited_row(ev, spans_for_that_ev)`. Per-row, cited-span-local.
3. **CONFIRM the pass-7 locked-FAIL is preserved by TITLE AUTHORITY:** ev_015 statement names SURMOUNT-3
   (non-empty title_trials) → span ignored even though the cited span is the whole body containing
   SURMOUNT-1 → SURMOUNT-1 sentence still `trial_name_mismatch`. This is the binding invariant.
4. Default-ON kill-switch `PG_VERIFY_TRIAL_NAME_SPAN_FALLBACK`; OFF → byte-identical pass-7 behavior.

## What to verify (b) — the exec-summary (lower risk)
5. `key_findings.build_key_findings(sections)` is PURELY EXTRACTIVE: lifts the first verified sentence
   (verbatim, citation intact) from each non-dropped section with verified_text; bullet cap; empty → "" (no
   heading); default-ON `PG_SWEEP_KEY_FINDINGS`. No LLM, no new claims. Wired into report.md AFTER the title,
   BEFORE sections (fail-open).

## Evidence (verified by Claude main-thread, NO SPEND)
- 17 trial-name tests PASS incl. TWO locked-FAILs: pass-7 (title authority, whole-body citation) + NEW
  one-reference-outside-cited-span (title silent, SURMOUNT-1 ref in intro outside the cited results span →
  SURMOUNT-1 sentence REJECTED); the SURPASS-2 RESCUE (title lacks token, body has SURPASS-1/-3, cited
  results span names SURPASS-2 → PASSES — proves cited-span, not a count heuristic); kill-switch-OFF →
  title-only. 6 key-findings tests (extractive property, dropped/empty excluded, cap, kill-switch). 67 PASS
  no-regression across the provenance verifier + M-18/M-41 trial suites. `py_compile` OK.

## The real risks to rule on
1. Can the cited-span fallback re-open FABRICATED #20 in ANY path? (Claim: no — title naming a trial ALWAYS
   gates and is never overridden; span fallback fires only when title is silent, and then only the CITED
   span (not whole body) is scanned, so a reference outside the cited span never matches. The two locked-FAIL
   tests pin both: title-present whole-body-citation + title-silent reference-outside-span.)
2. Is the grouping row-local + span-exact (not whole direct_quote, not cross-row union)? (Codex P2.)
3. Is the exec-summary genuinely extractive (no synthesized claim)? (Claim: yes — verbatim first sentence,
   asserted by test_extractive_property_every_bullet_sentence_in_some_section.)
4. Default-ON for both flags — acceptable? (Codex brief ruled default-ON for the verifier fallback.)

APPROVE iff the trial-name loosening is title-authority + cited-span-local ONLY (re-opens no fabrication
path; pass-7 + one-reference locked-FAILs GREEN), the exec-summary is verified-only/extractive, both are
kill-switchable, the rest of strict_verify is untouched, and it is NO-SPEND offline.
