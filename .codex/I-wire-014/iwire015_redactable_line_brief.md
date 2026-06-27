HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- Same quality bar regardless of iteration count.
- Reserve P0/P1 for real execution risks; classify minor issues P2/P3.
- If iter 5 returns REQUEST_CHANGES, the doc is force-APPROVE'd on remaining-non-P0/P1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

REVIEW MODE: STATIC only. No pytest, no pipeline, no user input, no broad exploration. Read the diff + the one function. Emit the schema.

# I-wire-015 #1337 — the ACTUAL root cause of the whole-report collapse: `_is_redactable_body_line`

## This is RELEASE-SAFETY adjacent — review the invariant: a genuine bibliography reference must NOT become redactable, and an unsupported claim must STILL never ship.

## Context
The #1337 reconfirm3 final report collapsed to 363 words (`released_with_disclosed_gaps`) because the
post-gate redactor could not bound one un-VERIFIED claim (05-041) and fail-closed-aborted the WHOLE
report. The earlier TIER-4 section-withhold fix (already committed, 638d0131) did NOT help, because the
TRUE root cause is upstream of all tiers: `_is_redactable_body_line` treated ANY line starting with `[`
as a non-redactable bibliography row. But claim 05-041 was rendered on a BODY line that BEGINS with the
WRAPPED trailing citations of the prior sentence — `[71][5][7][6] Further research is needed...` — so
TIER-1 (per-line), TIER-2 (line/line-run), AND TIER-4 (section body-join, which also uses
`_is_redactable_body_line`) all SKIPPED that line -> present-but-unbounded -> whole-report abort.

## The fix (the ONLY change in this diff)
`_is_redactable_body_line`: a line starting with `[` is protected (bibliography) ONLY if it has a
SINGLE leading citation marker (a real reference row "[12] Autor, D. (2015). ..."). A line that begins
with 2+ CONSECUTIVE markers (`(?:\[\d+\]){2,}`) is a wrapped BODY line (content) and stays REDACTABLE.
```python
    if stripped.startswith("["):
        return bool(re.match(r"(?:\[\d+\]){2,}", stripped))   # 2+ leading markers => redactable body
    return True
```
Diff: `.codex/I-wire-014/iwire015_redactable_line_redaction.diff` (report_redactor.py only).

## Why this is faithfulness-safe
- A genuine bibliography reference NEVER starts with two consecutive citation markers, so this NEVER
  reclassifies a real reference as redactable (no over-redaction of references).
- It only makes wrapped-body lines redactable — which is REQUIRED so an unsupported claim on them is
  removed (the never-ship invariant), instead of collapsing the whole report.
- The fail-closed raise (and TIER-4 section withhold) remain for any claim still un-boundable.

## VALIDATION — offline repro on the EXACT reconfirm3 collapse data (real unredacted report + the run's
real four_role final_verdicts + audit_map):
- BEFORE this fix: raises on 05-041 -> whole-report abort (the 363-word collapse), with the flag ON or OFF.
- AFTER this fix: NON-EMPTY 25,071-word report; 43 non-VERIFIED claims -> 33 redacted at CLAIM scope
  (precise), 10 already-absent; NO fail-closed, NO section withhold needed; the report is full-length
  (not gutted). The unsupported claims (incl. 05-041) are removed.

## Things to verify (be adversarial)
1. Can this reclassify a REAL bibliography reference as redactable (and thus over-redact it)? A reference
   row starts with a single `[N]`; `(?:\[\d+\]){2,}` requires 2 consecutive markers. Any reference form
   that starts with two consecutive markers? (e.g. "[1][2] ..." — would that ever be a reference row?)
2. RESIDUAL (known, classify severity honestly): a BODY line that begins with a SINGLE marker
   ("[71] Further research...") is still protected (non-redactable). If an unsupported claim were on
   such a line it would still fail-closed (or TIER-4-withhold if bounded to a section body — but the
   line is excluded from the section join too, so it would raise). On the real reconfirm3 data this does
   NOT occur (0 such collapses; all 33 redacted at claim scope). Is the safe-degradation (raise / no
   ship of unsupported) acceptable as a residual, or do you require the section-aware fix now?
3. `re` is imported at module top (line 67). Confirm.

## Tests (local, 8/8 PASS — for awareness): wrapped-citation body line redactable (claim removed, scope
"claim", neighbour survives); single-marker biblio line protected; + the 6 TIER-4 tests.

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
