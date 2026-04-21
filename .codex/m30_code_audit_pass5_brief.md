You are re-auditing M-30 after Claude addressed your pass-4
NOT_READY finding. This is pass 5.

## Pass-4 verdict

`outputs/codex_findings/m30_code_audit_pass4/findings.md` — NOT_READY:

- BLOCKER: ALL-CAPS after a context-dependent abbreviation was
  unconditionally non-boundary, masking the false-pass class where
  the ALL-CAPS word is actually the subject of a new sentence.
  Demonstrated probes:
    - `"... 4.2%, ..., 9.7% in the U.S. FDA approved the endpoint summary.[1]"`
    - `"... 4.2%, ..., 9.7% in the U.S. CDC reported a separate finding.[1]"`
  Both passed PT11; `[1]` cites the "FDA approved..." / "CDC reported..."
  sentence, not the prior one with the decimals.

## Pass-5 changes (commit `82b2625`)

Added verb-indicator disambiguation for ALL-CAPS next-word case:

1. `_PT11_VERB_INDICATORS` (frozen set of common modals/auxiliaries +
   common present-tense reporting verbs: is, was, has, can, will,
   reports, issues, approves, concludes, ...).
2. `_looks_like_verb_form(word_lowercase)` helper returns True for:
   - modal/auxiliary (in verb-indicator set)
   - past-tense `-ed` suffix (≥4 chars: "approved", "reported", ...)
   - gerund/participle `-ing` suffix (≥5 chars: "reporting", ...)
3. In `_is_abbreviation_period` ALL-CAPS branch: inspect next-next
   word. If `_looks_like_verb_form` → return False (boundary, ACRONYM
   is subject of new sentence). Otherwise → True (non-boundary).

4. Tests (+4):
   - `test_pt11_boundary_on_acronym_plus_verb_fda_approved` (your
     exact pass-4 probe).
   - `test_pt11_boundary_on_acronym_plus_verb_cdc_reported` (your
     second pass-4 probe).
   - `test_pt11_boundary_on_acronym_plus_modal_fda_is` (modal case).
   - `test_pt11_preserves_acronym_chain_fda_database` (pass-3
     counter-test still passes).

## Verifications

- `python -m pytest tests/polaris_graph/test_m30_pt11_abbreviation_boundary.py`
  → 40 passed.
- `python -m pytest tests/polaris_graph/` → 747 passed.
- PT11 on V19 real report still `passed=True`.

## Your task

1. Verify both pass-4 probes now FAIL PT11:
   - `"... in the U.S. FDA approved the endpoint summary.[1]"`
   - `"... in the U.S. CDC reported a separate finding.[1]"`
2. Verify the pass-3 positive case still PASSES:
   - `"... in the U.S. FDA database across cohorts.[1]"`
3. Verify all pass-1 and pass-2 blockers still FAIL:
   - Jan. A, U.S. A, et al. A, etc. A
4. Additional probes (your choice):
   - `"... in the U.K. NHS is responsible for health.[1]"` → should
     FAIL (NHS + modal "is").
   - `"... in the E.U. ECB announced rate cuts.[1]"` → should FAIL
     (ECB + -ed "announced").
   - `"... U.K. Biobank data ...[1]"` → should PASS.
   - Any acronym + present-tense verb case you want to test (e.g.
     "FDA issues", "CDC reports").
5. Any NEW blocker class introduced by pass-5?
6. Hard-coding check: `_PT11_VERB_INDICATORS` is generalizable English
   vocabulary (modals + common reporting verbs), no domain-specific
   terms.

## Expected READY criteria

- All prior blockers closed.
- Pass-3 counter-test (FDA database) still passes.
- New verb-detection correctly splits new-sentence-subject cases.
- Hard-coding remains generalizable.
- Acceptable trade-off: rare false-FAIL from noun-parsed-as-verb
  (e.g. "offering") documented in commit message; false-PASS is the
  dangerous class and is closed.

## Verdict format

Write `outputs/codex_findings/m30_code_audit_pass5/findings.md`:

```
# M-30 code audit — pass 5

VERDICT: READY | NOT_READY

## Blockers
- <list or none>

## Mediums
- <list or none>

## Lows / nits
- <list or none>

## Notes
<any other observations>
```

If READY, V20 sweep launches next. If NOT_READY, Claude considers
whether the remaining case is meaningful enough to warrant pass 6 or
whether the trade-off is acceptable.

## Scope

Audit ONLY the pass-4 → pass-5 diff (commit `82b2625`). Do NOT audit
M-28, M-29, other PT rules, or V19 outline-decode failure (task #8).
