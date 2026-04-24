V30 Phase-2 M-66 fix plan v2 review — xhigh reasoning (pass-2).

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your pass-1 review at
`outputs/codex_findings/v30_m66_plan_review/findings.md`
returned CONDITIONAL-blockers (2 + 3 + 1). Claude landed Medium #4
immediately (M-56 constructor shape + 3 new regression tests,
39/39 green, commit 8d57ab1) and rewrote the plan at
`outputs/audits/v30_phase2/fix_plan_run3_v2.md` addressing all
other revisions.

## Pass-1 issues + how v2 claims to have fixed them

### Blocker 1 — M-66a over-positioned as root-cause

**v2 claim**: M-66a split into:
- `M-66a-T`: telemetry only (per-slot `contract_slot_drop_log`
  exposing {raw_sentences, kept_sentences, dropped_count,
  drop_reasons}); lands this cycle
- `M-66a-R`: verifier relaxation; DEFERRED to M-67, data-driven
  decision only if M-66b-T + M-66a-T telemetry still shows
  legitimate extracted fields dropped

**Verify**: Does this sequencing actually guarantee source
content is fixed FIRST before any verifier change? Or is there a
scenario where M-66a-T could still silently mask a verifier bug?

### Blocker 2 — Acceptance criteria false-pass

**v2 claim**: Criteria tightened:
- "7 rendered pass subsections when CVOT remains paywalled
  (SURPASS-1/2/3/4/5/6 + SURMOUNT-2 — this is 7, not 8)"
- CVOT no longer in the hard gate (deferred to M-61)
- "4 of 6 regulatory slots with status=pass in
  frame_coverage_report" — mandatory set is FDA Mounjaro + FDA
  Zepbound + EMA Mounjaro EPAR + NICE TA924; NICE TA1026 + HC
  monograph may defer
- Trial Summary: "≥6 rows with non-empty Comparator + Endpoint +
  Result fields (not placeholder '—' or 'at week 18' style junk)"
- Trial Timeline: "≥6 entries with non-null Year field"
- Completeness assertion: "Report must NOT claim 'Completeness
  checklist: 7/7 topics covered' while any regulatory slot is
  fail_min_fields"

**Verify**: Do these still permit any false-pass I was worried
about? Specifically:
- The "real content" filter for Trial Summary — what test
  catches "insulin glargine in adults with type" fragment? Does
  the plan say HOW to test this or only WHAT?
- The 4-of-6 regulatory gate — is allowing 2 to fail_min_fields
  (NICE TA1026 + HC) actually OK for ship, or should I push
  back to 6-of-6 (forcing M-61 completion)?
- BEAT-BOTH ≥5/7 with zero LB — but the honest projection
  accepts 1 LB (narrative depth). That's 6/7 ≥BEAT_ONE, not
  5/7 BB. Does the plan confuse these?

### Medium 1 — M-66b scope split

**v2 claim**: M-66b split into:
- `M-66b-R`: regulatory url_pattern fetch (FDA/EMA/NICE/HC),
  separate test `TestOrchestratorRegulatoryUrlFetch`
- `M-66b-T`: OA PDF full-text fetch (Unpaywall oa_pdf_url),
  separate test `TestOrchestratorOaFullTextFetch`
- Each leg has its own acceptance criterion so the bundle can't
  hide which leg moved which dimension

**Verify**: Is the split clean, or are there shared code paths
(`_fetch_url_pattern` helper) that effectively re-bundle them?

### Medium 2 — Structure + narrative depth over-projection

**v2 claim**: Honest projection table revised to:
- Structure: BO (was BB) with explicit table/timeline fix
- Narrative depth: LB (was BO) acknowledged as synthesis
  deficit not source-volume deficit
- Optimistic scenario preserved separately, not pre-booked

**Verify**: Is the honest projection actually honest, or still
over-projecting somewhere?

### Medium 3 — stale RetrievalAttempt constructor

**Already LANDED** in commit 8d57ab1. Plan v2 §Medium #4 records
this. Verify the fix (frame_fetcher.py:807-821) + the 3 tests
(test_doi_mismatch_rejects_pubmed_abstract,
test_doi_match_accepts_pubmed_abstract,
test_pubmed_without_doi_element_still_works).

### Nit — M-66c independence

**v2 claim**: M-66c lands first (15 min, yaml-only, Thomas clamp
field realignment).

**Verify**: Is this order actually cheaper? Or is there a
dependency (e.g., Thomas clamp fields depend on M-66b-T oa
full-text) that makes C-first pointless?

## Your specific pass-2 questions

1. Do the split acceptance criteria (7 efficacy pass excluding
   CVOT, 4 of 6 regulatory, ≥6 table rows with real content,
   completeness assertion) actually prevent the false-pass
   conditions I flagged in pass-1?

2. Is the "honest projection: 2 BB + 4 BO + 1 LB" claim achievable?
   Or should one of the "BO" cells probabilistically still fail?

3. The narrative-depth LB acknowledged — is the ship decision
   rule clear: "BEAT-BOTH ≥5/7 with zero LB" (strict) vs
   "BEAT-BOTH ≥5/7 net ≥BEAT_ONE: 7" (lenient). Plan v2 uses
   the latter. OK with that?

4. Medium #3 fix: are the 3 new tests sufficient coverage for the
   branch, or should I ask for a 4th test (e.g., CrossRef has
   an abstract AND PubMed has a mismatching DOI — the guard
   should still fire because it prevents wrong metadata leakage
   into title/authors)?

5. Any NEW blocker that emerged from the plan v2 that wasn't in
   pass-1?

## Output

Write to
`outputs/codex_findings/v30_m66_plan_review/pass2_findings.md`.

```markdown
# V30 M-66 fix plan v2 review (pass 2)

**Verdict**: APPROVED | CONDITIONAL-no-blockers | CONDITIONAL-blockers | REJECT

## Pass-1 issue resolution status

1. Blocker 1 (M-66a over-positioning): RESOLVED | PARTIAL | NOT_RESOLVED — <why>
2. Blocker 2 (acceptance false-pass): ...
3. Medium 1 (M-66b split): ...
4. Medium 2 (projection honesty): ...
5. Medium 3 (RetrievalAttempt fix already landed): ...
6. Nit (M-66c order): ...

## Answers

1. Split criteria false-pass prevention: ...
2. Projection achievability: ...
3. Ship decision rule clarity: ...
4. Medium #3 test coverage: ...
5. New blockers: ...

## Findings (if any new)

## Next

On APPROVED / CONDITIONAL-no-blockers: Claude implements.
Otherwise: plan v3.
```

Keep under 180 lines. Full xhigh budget.
