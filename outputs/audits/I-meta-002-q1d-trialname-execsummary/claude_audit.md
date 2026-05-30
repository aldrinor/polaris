# Claude architect audit — PR12: trial-name verifier body→cited-span fallback + verified exec-summary (#949)

**Issue:** #949 (q1c-8, concern #5 follow-up). **Branch:** `bot/I-meta-002-q1d-trialname-execsummary`.
**Both Codex gates APPROVE** — brief iter-1 ("title-authority rule is the key safety condition") + diff
iter-2 (zero P0/P1/P2; the safety-core confirmed clean both rounds, the one P2 polish fixed). **NO SPEND** —
offline, the only network-touching paths (LLM) are not added.

## Part (a) — the safety-core change (TOP scrutiny)

Codex-verified gap (#941): the provenance verifier dropped well-framed CORRECT prose on `trial_name_mismatch`
when the evidence row's TITLE/statement lacked the literal trial token (a fully-framed SURPASS-2 sentence was
dropped). The issue asked to "match against evidence body" — but the code comment (DR pass 7) documents that
scanning `direct_quote` is exactly what CAUSED FABRICATED #20: a SURMOUNT-3 paper's body cites SURMOUNT-1 as
a prior reference, which let a fabricated "In SURMOUNT-1, ..." sentence pass when bound to that SURMOUNT-3 row.

**The tension is real; naive loosening is clinical-safety-LETHAL.** Resolution (Codex-confirmed): a
title-authority-preserving, CITED-SPAN (not whole-body) fallback —
- `_trial_names_for_cited_row(ev, cited_spans)`: returns `title_trials` (statement|title) if NON-EMPTY — the
  span is NOT consulted, so a row whose title declares trial T can never match a different-trial sentence,
  regardless of body content. **This preserves the FABRICATED #20 locked-FAIL via TITLE AUTHORITY** (even
  when the citation span is the whole body, as the pass-7 fixture is).
- ELSE (title names no trial — the SURPASS-2-omitted case), the union of trial names in the CITED SPANS only
  (`direct_quote[start:end]` for that row's tokens — the exact slice the numeric/content checks use), NOT the
  whole body. The cited *results* span names the trial whose result it states.
- Gate rewired to group tokens by `evidence_id` → resolve per-row with that row's own cited spans (row-local,
  span-local; never whole `direct_quote`, never cross-row).

**Why cited-span and not a body-trial-count heuristic** (the design I started with, then rejected): a count
heuristic both (a) launders a one-trial prior-reference body and (b) still drops the REAL SURPASS-2 paper
(which contextualises against SURPASS-1/-3, so its body names ≥2 trials). Cited-span solves both: the
reference outside the cited span never matches, and the cited results span names the actual trial.

Default-ON kill-switch `PG_VERIFY_TRIAL_NAME_SPAN_FALLBACK`; OFF → exact pass-7 title/statement-only behavior.

### Mandatory locked-FAIL regressions (both GREEN)
1. `test_pass7_regression_direct_quote_mention_insufficient` — ev_015 title=SURMOUNT-3, cited span = whole
   body containing SURMOUNT-1 → SURMOUNT-1 sentence REJECTED (title authority).
2. NEW `test_locked_fail_one_reference_outside_cited_span_rejected` — title names no trial; SURMOUNT-1
   referenced in the INTRO outside the cited results span → fabricated SURMOUNT-1 sentence REJECTED (span
   scope, not body scope — closes the one-reference hole).
Plus the SURPASS-2 RESCUE (title lacks token, body has SURPASS-1/-3, cited results span names SURPASS-2 →
PASSES, proving it's span-based not count-based) and kill-switch-OFF → title-only.

## Part (b) — verified-only extractive exec-summary

`key_findings.build_key_findings(sections)`: lifts the first verified sentence (verbatim, citation intact)
from each non-dropped section with `verified_text`, into a "## Key Findings" block at the top of report.md.
PURELY EXTRACTIVE — no LLM, no spend, zero synthesized claims (asserted by
`test_extractive_property_every_bullet_sentence_in_some_section`). Bullet cap; empty → "" (no heading);
default-ON `PG_SWEEP_KEY_FINDINGS`; fail-open wiring. The sentence matcher keeps trailing-citation forms
(`claim. [1]` and `claim [1].`) attached and never splits inside a decimal ("2.1").

## Tests (24 + 67 no-regression, NO SPEND)

17 trial-name (2 locked-FAILs + rescue + kill-switch + all prior M-25 cases) + 7 key-findings (extractive
property, dropped/empty excluded, cap, kill-switch, trailing-citation, decimal-preservation). 67 PASS
no-regression across the provenance verifier + M-18/M-41 trial suites. `py_compile` OK.

## Verdict

Loosens trial-name matching ONLY via title-authority + cited-span-local fallback (re-opens no fabrication
path; both locked-FAILs green; Codex confirmed FABRICATED #20 shape preserved across both diff rounds), adds
a verified-only extractive exec-summary, both kill-switchable, the rest of strict_verify untouched, NO SPEND.
Both gates APPROVE. Ready to queue for operator merge.
