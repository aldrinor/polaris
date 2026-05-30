RULE NOW — emit the YAML verdict block FIRST. Read the patch at `.codex/I-meta-002-q1d-analyst-synthesis-safety/codex_diff.patch` (2 files, +227/-3). Do NOT explore beyond it. NO SPEND.

HARD ITERATION CAP: 5. Iter 1 of 5. Front-load all findings; reserve P0/P1 for real execution risks.

## Output schema (emit FIRST)
```yaml
verdict: APPROVE | REQUEST_CHANGES
p0: [...]
p1: [...]
p2: [...]
required_changes: [...]
convergence_call: accept_remaining
```

# Codex diff-gate (iter 1) — PR3 analyst-synthesis safety hardening (#953 q1d-c, CLINICAL-SAFETY). Verify the diff implements the APPROVE'd brief. NO SPEND / NO NETWORK / NO LLM in the new screens.

## What the diff implements (verify)
1. **Evidence sanitization (closes §9.1.7 bypass).** `_format_evidence_pool_for_prompt` now routes BOTH
   the quote AND the evidence_id through `sanitize_evidence_text(...)[0]` (P2 #1) before building the
   block; accumulates redactions into `synthesis_evidence_redaction_count`. The closing delimiter changed
   from bare `<<<end>>>` to `<<<end_evidence>>>` — the SAME delimiter the verified `wrap_evidence_for_prompt`
   uses and that `sanitize_evidence_text` redacts (a forged bare `<<<end>>>` was NOT in the redaction set;
   a forged `<<<end_evidence>>>` now IS).
2. **Qualitative-negation SAFETY screen (fail-closed DROP).** New pure `_screen_qualitative_negations`:
   operates PER LINE (preserving `###` headings + blank lines); within a prose line, `_split_sentences`
   (abbreviation-masked, decimal-safe) splits sentences; a sentence matching BOTH `_NEGATION_CUE_RE` AND
   `_SAFETY_TERM_RE` is DROPPED; survivors rejoined. Counts → `synthesis_negation_dropped_count` + WARNING
   log. Runs AFTER the `[#ev]`/`[N]` scrubs, BEFORE return — the verified core above is untouched.
3. **Operator kill-switch.** `generate_analyst_synthesis` checks `PG_SWEEP_ANALYST_SYNTHESIS` (default "1")
   FIRST — before the openrouter import / prompt build / model call (P2 #2 — disabling avoids spend) —
   returning `("", 0, 0)` (caller omits the section).

## Evidence (verified by Claude main-thread)
- 9 new tests PASS (`test_analyst_synthesis_safety.py`): "did not lead to discontinuation" DROPPED; benign
  + positive ("discontinuation occurred in 0.3%") KEPT; negation-without-safety KEPT; markdown structure
  preserved; decimal/`e.g.` not shredded; determinism; forged `<<<end_evidence>>>`+`<<<evidence:>>>`
  redacted (exactly 1 real opening+closing); legit content preserved; kill-switch returns "" with no model
  call. Plus 48 existing analyst tests (test_analyst_synthesis / telemetry / alert) PASS.
- `verify_lock --consistency` OK. Diff +227/-3 net 224 (module ~95 executable, rest comments+tests).
- Frozen/untouched: strict_verify / provenance_generator's VERIFY path / D8 / runtime lock / the 5 PR-10
  contracts / the verified multi_section core. This only HARDENS the unverified layer.

## Rule on
1. Can a forged real delimiter (`<<<evidence:...>>>` / `<<<end_evidence>>>`) in evidence still break out of
   its DATA block? (Must be NO — sanitize_evidence_text redacts both; the closing now matches.)
2. Does the negation screen preserve markdown structure (headings, blank lines, paragraph breaks)?
3. Could the kill-switch path still incur a model call / spend when off? (Must be NO — checked first.)
4. Over-/under-drop: is DROP correctly scoped to negation+safety co-occurrence (not gutting all prose)?
   For the UNVERIFIED layer, over-drop is the SAFE direction — confirm it does not touch the verified core.
5. Determinism; no sentinel-mask leak; sanitize is content-preserving for legitimate evidence.

APPROVE iff the §9.1.7 sanitization is closed (id + quote + matching delimiter), the negation class is
dropped fail-closed with structure preserved, the kill-switch avoids spend, the verified core + D8 are
untouched, and it's test-proven.
