HARD ITERATION CAP: 5 per document. This is iter 5 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Output schema (return EXACTLY this, machine-parsed for the final `verdict:` line):
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## ITER-5 CHANGELOG — addressing the iter-4 REQUEST_CHANGES (you returned 0 P0, 1 P1, accepted all P2)

**P1 — the 3 fixture files existed on disk but were UNTRACKED (`git ls-files` empty) — FIXED.** The gate-before-commit ordering was the trap: the workflow only `git add`-ed them at the commit step (after the gate), so you reviewed a tree where they were still untracked. Resolved by staging them into the git index NOW, before this gate:
- `git add tests/fixtures/drb90_redaction/{report.md,four_role_claim_audit.json,manifest.json}` — `git ls-files tests/fixtures/drb90_redaction/` now lists all three (and `--others` is empty). They are in the index and will be committed atomically with the code by the workflow's commit step.
- Also added `tests/fixtures/drb90_redaction/.gitattributes` pinning the three fixtures to `-text` (byte-exact LF, no autocrlf rewrite) so the redaction tests are deterministic on every platform/CI checkout — git had warned LF→CRLF conversion on these exact-content fixtures.
- `pytest tests/roles/test_report_redactor_iready017.py` → **16 passed** after `git add --renormalize`.

Run `git ls-files tests/fixtures/drb90_redaction/` to confirm: 4 tracked files (3 artifacts + .gitattributes). This is the cap iteration (5 of 5); the only remaining item across all 5 rounds was this fixture-tracking, now closed. Your iter-4 P2 follow-ups remain accepted (truncated fragment → generator-side; inert NLI → #1172; `abort_credibility_coverage_gap` v6-mirror → urgent follow-up).

---

## ITER-4 CHANGELOG — addressing the iter-3 REQUEST_CHANGES (you returned 0 P0, 1 P1, accepted all P2)

**P1 — real-artifact test fixtures were untracked (`outputs/*` gitignored) → CI would fail on a clean checkout — FIXED.** Exactly as you diagnosed. Committed the three genuine drb_90 artifacts (`report.md`, `four_role_claim_audit.json`, `manifest.json`) as a tracked fixture under `tests/fixtures/drb90_redaction/` (per CLAUDE.md §5 / LAW VI), and repointed the test's `_FORENSIC` from `outputs/vm_forensic/...` to `tests/fixtures/drb90_redaction`. These are the real shipped run (not synthetic — the leak is a render-mapping problem only the real artifacts exercise); `git check-ignore` confirms they are trackable. `pytest tests/roles/test_report_redactor_iready017.py` → **16 passed** reading from the committed fixture.

NOTE on the diff under review: the patch shows the CODE changes (the `_FORENSIC` repoint). The three fixture data files (~97 KB total, benign research outputs — no secrets/PII) are committed ALONGSIDE in the same commit (the workflow's git-add list includes them) but are not pasted into this review patch since they are data, not logic. `src/polaris_v6/schemas/run_status.py` (iter-3) is in the patch.

Your iter-3 P2s remain accepted follow-ups: truncated source fragment (generator-side), inert strict-verify NLI (#1172), `abort_credibility_coverage_gap` v6-mirror gap.

---

## ITER-3 CHANGELOG — addressing the iter-2 REQUEST_CHANGES (you returned 0 P0, 1 P1, accepted all P2)

**P1 — `abort_report_redaction_failed` missing from the v6 `PipelineStatus` Literal — FIXED.** Exactly as you diagnosed: the v6 actor stores `manifest.status` into `pipeline_status` for abort_* runs, and `RunStatusResponse` validates against the `PipelineStatus` Literal, so a redaction-failure run would 500 on GET/list. Registered `"abort_report_redaction_failed"` in `src/polaris_v6/schemas/run_status.py` (alongside `abort_four_role_release_held`), and added two mirror tests in the cluster suite, modeled on the existing `abort_discovery_degraded` guards:
- `test_abort_report_redaction_failed_in_v6_pipeline_status` — `"abort_report_redaction_failed" in get_args(PipelineStatus)`.
- `test_run_status_response_accepts_redaction_failed_without_validationerror` — your exact repro: `RunStatusResponse(..., pipeline_status="abort_report_redaction_failed")` constructs cleanly, no `ValidationError`.

Tests now: 29 in the redactor cluster + manifest-contract + fl05 v6-mirror suite → **43 passed**. (I noted `abort_credibility_coverage_gap` is ALSO absent from the same Literal — same class, pre-existing from I-cred-008b #1162; per your P2 ruling I left it out of this diff and will carry it as the urgent taxonomy-mirror follow-up, not a blocker here.)

Your iter-2 P2s are all accepted as you stated: the "UN Regulation No." truncated fragment → generator-side follow-up (no risky subset-matching added); the inert strict-verify NLI regression → filed as URGENT #1172; the `abort_credibility_coverage_gap` mirror gap → urgent follow-up.

---

## ITER-2 CHANGELOG — addressing the iter-1 REQUEST_CHANGES (you returned 0 P0, 1 P1, 3 P2)

**P1 — citation markers stripped from VERIFIED neighbors — FIXED.** Root cause confirmed: the old `re.split(r"(?<=[.!?])(?:\[\d+\])?\s+...")` made the boundary marker part of the discarded separator, so redacting one sentence dropped the `[8]`/`[4]` markers of its verified neighbors. Replaced the lossy split/rejoin with a byte-preserving span redactor:
- `_SENTENCE_BOUNDARY_RE = r"[.!?](?:\s*\[\d+\])*\s+(?=[A-Z\"'(#])"` — markers stay attached to the sentence they cite (left side); a decimal/`No. 157` is never a boundary (lookahead demands whitespace + sentence-start char, never a digit).
- `_sentence_spans()` returns (start,end) per rendered sentence INCLUDING its trailing markers; `_redact_line()` rebuilds from the ORIGINAL substrings, replacing ONLY the matching span and leaving every other sentence + all inter-sentence whitespace BYTE-IDENTICAL.
- Real-artifact proof (drb_90), marker delta after the fix: `[2] 2→1, [3] 5→4, [4] 21→17` — ONLY the 6 redacted claims' OWN markers drop. Verified neighbors keep theirs: `crashes.[8]`, `(OR 0.457)`, `(OR 0.171)`, `Level 5 (full automation)`, `basis.[4]` all survive. Under the bug you reproduced `[4]` dropped 21→**16**; the recovered 17th `[4]` is the verified 04-000 marker the fix no longer strips.
- New regressions: `test_redaction_preserves_neighbor_citation_markers` (synthetic), `test_real_drb90_verified_survivor_citations_preserved` (real artifact, asserts `crashes.[8]` + `basis.[4]` survive).

**P2-1 — audit-map-missing aborted even with empty/all-VERIFIED verdicts — FIXED.** `run_one_query` now computes `_nonverified_verdicts` from `final_verdicts` FIRST: none → skip (no-op, no abort); elif report.md absent → skip (nothing can leak); elif audit_map missing → fail-closed; else reconcile. Static/seam-timeout Gate-B runs no longer mislabel as `abort_report_redaction_failed`.

**P2-2 — over-redaction of a whole paragraph — FIXED** by the same span tokenizer (each unit is one sentence) PLUS a named `_MIN_REDACTION_COVERAGE = 0.6` floor so a short rejected claim whose words are a substring of a LONGER sentence does not redact that sentence. New regression `test_no_overredaction_of_verified_sentence_sharing_words`.

**P2-3 — leftover fragment "Instrument: UN Regulation No." — analysis + decision (please rule).** That fragment is PRE-EXISTING in the SOURCE report.md before any redaction (a truncated generator artifact at line 11; the full claim 01-000 sentence is at line 31, which the redactor DOES redact and record). Catching arbitrary truncated PREFIX fragments would require a `sentence ⊆ claim` match branch, which would FALSE-redact a legitimate shorter VERIFIED sentence that is a substring of a longer unsupported claim (e.g. verified "X causes Y" inside unsupported "X causes Y in adults at 14%") — dropping verified cited content, a worse faithfulness failure than leaving a pre-existing generator fragment. Proposal: file the truncated-fragment as a generator-side follow-up Issue; do NOT add risky fragment-matching to the redactor. Your call.

Also cleaned the cosmetic redundant `verdict != _VERDICT_VERIFIED` conjunct (your scrutiny point 4).

Tests now: `pytest tests/roles/test_report_redactor_iready017.py tests/polaris_graph/test_manifest_contract.py` → **27 passed** (was 24; +3 regressions).

---

# Diff review — I-beatboth-fix-000 (#1171) faithfulness cluster: close the drb_90 report.md leak

## What the diff is
The 3rd of 3 fix clusters in the 5-question beat-both forensic campaign. Branch `bot/I-ready-017-faithfulness`. The other two clusters (breadth `5c557548`, clinical-scope `fa72c398`) are already committed + Codex-APPROVED. This diff is the faithfulness leak-closure ONLY.

Patch under review: `.codex/I-ready-017/faithfulness_codex_diff.patch` (36.5 KB). Files:
- NEW `src/polaris_graph/roles/report_redactor.py` (234 lines) — pure-function post-gate reconciliation.
- NEW `tests/roles/test_report_redactor_iready017.py` — real-artifact tests (drb_90 forensic).
- `scripts/run_honest_sweep_r3.py` (+106) — caller wiring after the 4-role seam.
- `src/polaris_graph/audit_ir/regression_lab.py` (+4) — new terminal status in `_STATUS_TIERS`.
- `tests/polaris_graph/test_manifest_contract.py` (+2) — taxonomy mirror.

## The leak (root cause, confirmed against real artifacts)
`run_honest_sweep_r3.py` assembles `report.md` (L5780) from strict_verify-KEPT sentences BEFORE the authoritative 4-role D8 seam runs (L6407+). The seam re-judges every kept sentence with the stronger Mirror/Sentinel/Judge stack and can flip a kept sentence to material non-VERIFIED (UNSUPPORTED/FABRICATED/UNREACHABLE/PARTIAL at S0/S1/S2). Today the runner consumes that verdict ONLY as a manifest flag (`release_allowed=False` + `needs_rewrite`); it NEVER reconciles the assembled `report.md`. So a sentence the strongest verifier rejected still ships as asserted prose.

drb_90 proof (real forensic artifacts in `outputs/vm_forensic/drb_90_adas_liability/`): `needs_rewrite` carried 7 material UNSUPPORTED claim_ids; ≥5 of those sentences were physically present in shipped `report.md` — e.g. "$27,874 per violation" (06-002), "UN Regulation No. 157 - ALKS" (01-000), "should not be assumed statistically representative" (06-000).

## The fix (refuse-in-place, fail-closed)
`reconcile_report_against_verdicts(report_text, final_verdicts, audit_map)` — pure string function:
- For every claim whose 4-role `final_verdict` is material-non-VERIFIED (verdict in {UNSUPPORTED,FABRICATED,UNREACHABLE,PARTIAL} AND severity in S0/S1/S2), locate the verbatim sentence in rendered `report.md` and REPLACE it with the existing visible gap language. NO generative rewrite, NO new spend.
- VERIFIED claims NEVER redacted. S3 observe-only NEVER redacted (ships disclosure-only — the BUG-11 scope guard).
- Citation-insensitive matching (`[#ev:...]` provenance tokens render to `[N]` markers downstream; whitespace-normalized) at rendered-sentence granularity. Headings (`#`), bibliography rows (`[`), and blank lines are skipped.
- FAIL-CLOSED: if a material non-VERIFIED claim's normalized prose IS present in the report but cannot be pinned to a discrete rendered sentence (or has no audit row, or empty claim_text) → raises `ReportRedactionError`. The caller maps that to terminal `abort_report_redaction_failed` and does NOT ship. The unredacted report stays on disk for the curator.
- ALREADY-ABSENT is the SAFE state: a material non-VERIFIED claim whose prose was removed by downstream dedup/repair is recorded `already_absent`, not raised.

Caller wiring (`run_one_query`, after the 4-role seam): default-ON via `PG_REDACT_HELD_UNSUPPORTED=1` (kill-switch `=0` for offline-test isolation only). Runs on the HELD path too (the §-1.1 forensic audit reads `report.md`, not the manifest). Writes reconciled body BEFORE the V30 append. Emits one `redacted_unsupported` gap per removed claim into `gaps.json` (append; never overwrites curator gaps). Records `manifest.report_redaction`.

New terminal status `abort_report_redaction_failed` mirrored across the 3 enforced sites: `UNIFIED_STATUS_VALUES`, `_SUMMARY_TO_UNIFIED`, `regression_lab._STATUS_TIERS` (tier 2), `test_manifest_contract` (taxonomy + partial-mapping). This mirroring is test-enforced (`test_saturation_phase4` + `test_md9_regression_lab` + `test_manifest_contract`).

## Evidence (offline, real artifacts — §-1.1 anchored, NOT synthetic)
`tests/roles/test_report_redactor_iready017.py` runs against the REAL drb_90 forensic `report.md` + `four_role_claim_audit.json` + `manifest.json`:
- leak fragments PRESENT before redaction (proves the leak existed);
- 5 material-UNSUPPORTED fragments GONE after redaction, each recorded redacted;
- VERIFIED survivors KEPT ("OR 0.457", "0.171", "six levels … Level 0 … Level 5", '"reporting entities" defined to include only') — precision, not a blanket recall cut;
- gaps.json: exactly one `redacted_unsupported` per removal, no dup refs;
- 02-000 ("Tesla, Inc") downstream-removed → recorded `already_absent`, NOT raised (SAFE);
- S3 07-004 (UNSUPPORTED, S3) NOT redacted; its "95–98% algorithm efficiency" prose survives disclosure-only;
- present-but-unlocatable → raises; missing audit row for non-VERIFIED → raises (fail-closed);
- all-VERIFIED → byte-identical no-op;
- held-path (release_allowed=False) still redacts ≥5.
- Task-3 D8 guard: `test_d8_coverage_gate_is_fixed_denominator_fraction` pins the ruling that the D8 coverage HOLD is a legitimate fixed-denominator semantic-coverage fraction (`CoverageLedger.fraction()`), NOT a §-1.1-banned raw count — dropping a claim can only LOWER the fraction, never game it up. (No change to `release_policy.py`.)

Run result: `pytest tests/roles/test_report_redactor_iready017.py tests/polaris_graph/test_manifest_contract.py` → **24 passed**.

## Files I have ALSO checked and they're clean
- `release_policy.py` — `_MATERIAL_SEVERITIES=("S0","S1","S2")` matches `report_redactor.DEFAULT_MATERIAL_SEVERITIES` (lockstep noted in both files). `CoverageLedger` API (`required_element_ids`, `covered_element_ids`, `.fraction()`) exists and is used by the Task-3 guard. No change made here (D8 ruling = no-change-by-behavior).
- `four_role_result.final_verdicts` / `.held_reasons` — consumed read-only by the wiring; attributes confirmed present in the seam result object the block already logs.
- `gaps.json` append path — corrupt-sidecar guarded (`except` → `[]`), never drops the new redaction gaps; never overwrites curator gaps.
- The redactor runs only inside the `four_role_result`-in-scope block, so it cannot fire when the seam didn't run.

## ONE pre-existing finding I am surfacing (NOT in this diff — please rule block vs follow-up)
`pytest tests/polaris_graph/test_provenance_generator_entailment.py` → **4 failures**: `test_enforce_drops_contradicted_verdict`, `test_enforce_keeps_legit_paraphrase`, `test_warn_mode_runs_judge_but_does_not_drop`, `test_telemetry_judge_error_routes_to_judge_error_counter`. Symptom: the strict-verify entailment/NLI judge is invoked 0 times (fake judge `calls==0`) in enforce AND warn mode.
- This diff does NOT touch `provenance_generator.py`. The test file last changed at I-bug-098 (#349, which wired the gate); `provenance_generator.py` was later modified by I-cred-001 (#1149 disclosure schema), FX-02 (#1106), FIX-A3 (#1143). So this is a pre-existing regression of the strict-verify NLI layer, orthogonal to the drb_90 leak.
- Why it does NOT undercut THIS fix: the drb_90 leak root is the missing POST-GATE reconciliation against the 4-role SEAM (Mirror/Sentinel/Judge — a different, authoritative layer that DID flag the claims correctly). The redactor is the backstop that reconciles report.md against that seam regardless of the cheaper strict-verify NLI prefilter's state.
- My proposal: APPROVE this leak-closure; I file the strict-verify-NLI-inert regression as an URGENT separate follow-up Issue and fix it next (it is a real faithfulness hole, just not this cluster's scope, and bundling it would blow the 200-LOC cap + the no-while-were-at-it rule). Please rule: does it block this commit, or is follow-up correct?

## Scrutiny points (be adversarial)
1. Over-redaction risk: `_redact_line` uses `stem_norm in _normalize(piece)` (substring containment). Could an UNSUPPORTED claim's normalized prose be a substring of a DIFFERENT VERIFIED sentence and wrongly redact it? The real-artifact precision test guards the drb_90 set, but assess the general risk.
2. Under-redaction → is it always SAFE or fail-closed? (claim: yes — either `already_absent` if not a substring anywhere, or raise if substring-present-but-unpinnable.)
3. Default-ON (`PG_REDACT_HELD_UNSUPPORTED=1`) changes report.md behavior on EVERY full-pipeline run, not just the benchmark slate. Correct safety posture for a faithfulness gate, but does it break any existing full-pipeline test? (The kill-switch is documented test-isolation-only.)
4. `_is_material_non_verified` has a redundant `verdict != _VERDICT_VERIFIED` conjunct (VERIFIED isn't in the non-verified set). Cosmetic — confirm it's harmless.
5. Sentence splitter regex `_SENTENCE_SPLIT_RE` — does it ever split a decimal ("157.", "0.457") mid-number and cause a partial redaction? (claim: lookahead requires whitespace + uppercase/quote/bracket, so "0.457" is safe.)
