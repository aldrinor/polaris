HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

REVIEW MODE: STATIC review only. Do NOT run pytest, do NOT run the pipeline, do NOT request user input, do NOT explore broadly. Read the diff + the one function it changes. Emit the verdict schema at the end.

# I-wire-015 #1337 R5 — post-gate redaction: SECTION-level fallback instead of whole-report abort

## This is a RELEASE-SAFETY change — review for the one invariant: an UNSUPPORTED claim must NEVER ship as fact.

## What this fixes
GH #1337. The post-gate redactor `reconcile_report_against_verdicts` (report_redactor.py) removes every
non-VERIFIED claim's prose from report.md. When TIER-1 (precise span) AND TIER-2 (minimal containing
unit / contiguous body-line run) BOTH fail to bound an un-VERIFIED claim, it RAISED `ReportRedactionError`
-> the caller aborts the ENTIRE release (`released_with_disclosed_gaps`, ~empty report). In the #1337
reconfirm3, ONE un-boundable chrome fragment ("The document presents firm-level evidence from Germany
with JEL classification...") collapsed an otherwise-good 25K-word report to 363 words.

## The fix (TIER-4: section-level bounded withhold)
Insert a TIER-4 step between TIER-2 and the raise. When TIER-1+TIER-2 cannot bound a PRESENT un-VERIFIED
claim, withhold ONLY the markdown SECTION (the run of lines from one `#`-heading to the next) whose
redactable BODY lines' join contains the stem: blank that section's body (first redactable line -> the
gap sentence, rest -> "") keeping the heading. The unsupported claim is FULLY removed; only that one
section's coverage is lost (disclosed in gaps.json as redaction_scope="section"); every OTHER section
survives. If NO section body contains the stem (it lives only in a heading/bib line, or straddles a
section boundary), TIER-4 returns False and the ORIGINAL whole-report raise fires (true last resort).
Default-ON via `PG_REDACT_SECTION_LEVEL_FALLBACK`; OFF reverts to the legacy whole-report abort.

## The diff (the ONLY code change)
READ `.codex/I-wire-014/iwire015_r5_redaction.diff` (146 lines, report_redactor.py only). Summary:
- new `_section_level_fallback_enabled()` (env gate, default ON).
- new `_redact_containing_section(report_text, stem_norm)` -> (bool, text): finds the section whose
  redactable body-join contains the stem, blanks that body, returns (True, new); else (False, unchanged).
  Reuses `_is_redactable_body_line` (skips headings `#` / bib `[` / blanks) and `_GAP_REPLACEMENT`.
- loop insertion: after TIER-2 fails, if the gate is ON, call TIER-4; on success continue, else raise.
- `RedactedClaim.redaction_scope: str = "claim"` (new default field, backward-compatible); set to
  "section" when TIER-4 fired; surfaced in `gaps_json()` note.

## Things to verify (be adversarial — this is release safety)
1. FAITHFULNESS INVARIANT: after TIER-4, is the unsupported claim's prose GUARANTEED gone? TIER-4 blanks
   EVERY redactable body line of the matched section (first -> gap, rest -> ""). Confirm a claim split
   across non-contiguous body lines within the section is fully removed (the loop re-checks
   `_prose_present` and only records after it returns absent). Any path where the claim could survive?
2. NEVER-SHIP on the un-boundable case: if TIER-4 returns False (no single section body bounds the stem,
   e.g. it straddles a heading), the code MUST still raise (whole-report fail-closed). Confirm the raise
   is reached and the loop cannot spin (no-progress + still-present == raise, same as before).
3. TERMINATION: each TIER-4 success blanks a section whose body no longer matches the stem; the outer
   `while _prose_present` loop consumes occurrences monotonically. Confirm no infinite loop (TIER-4
   returning True must make progress; TIER-4 returning False must raise, not loop).
4. NO REGRESSION to the normal path: a claim bounded by TIER-1/TIER-2 is unchanged (redaction_scope
   stays "claim"); the section fallback only runs when BOTH fail.
5. OVER-REDACTION is acceptable here (faithfulness-safe): blanking a whole section drops VERIFIED
   neighbours in it too — a disclosed COVERAGE loss, never a faithfulness violation (no unsupported
   claim ships). Confirm this is the only downside and it is disclosed (gaps.json scope="section").
6. The default-ON flag + backward-compatible dataclass field: any consumer of RedactedClaim that would
   break on the new field? (It has a default.)

## Validation (local pytest, 6/6 PASS — for your awareness, do not re-run)
section-withhold-not-whole-report (scope=section, other section survives, claim gone); flag-off reverts
to raise; normal bounded claim unaffected (scope=claim, neighbour+[1] survive); multi-occurrence two
sections both withheld + terminates; section-straddle still raises (last resort, no spin); VERIFIED
never redacted.

## Output schema (REQUIRED, last lines)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
