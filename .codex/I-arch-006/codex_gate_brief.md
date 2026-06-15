HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If you detect "I'm holding back a P1 to surface next round" — DON'T. Surface it now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

ITER-1 RESULT: you returned REQUEST_CHANGES with 2 P1s; BOTH are now FIXED in this diff — (P1-1 BUG-19) bare 'not found' removed from error-page substring tokens so real negative findings ('Metastases were not found') are no longer dropped, only a literal whole-unit 404 stub is; (P1-2 BUG-7) a CRITICAL topic on a recognizer confident-negative now fail-closes+discloses when generic drug signal is present and discloses (never silent) otherwise. Verify these two fixes are correct + complete, and re-scan for any NOVEL P0/P1.

You are the CONSOLIDATED diff gate for I-arch-006 (#1262), a 19-fix "beat-both" hardening campaign on the POLARIS deep-research pipeline. STATIC REVIEW ONLY — do NOT run pytest or any command; read the files and reason line-by-line.

READ THESE FILES (under C:/POLARIS):
- `.codex/I-arch-006/full_campaign.diff`  — the 2710-line consolidated diff (20 files): the change under review.
- `outputs/audits/marlin_v2/MASTER_FIX_LIST.md`  — what each fix is supposed to do.
- `state/forensic_bug_list.md`  — the forensic evidence behind each bug.
Open the actual source files if you need surrounding context.

THE ONE BINDING QUESTION: did ANY change RELAX a faithfulness gate, or introduce a NEW silent-drop of a real claim/source? The hard gates (strict_verify / NLI / 4-role D8 / provenance / span-grounding) MUST keep byte-equivalent strictness. ALLOWED changes: input hygiene (strip BEFORE the gate), timing/concurrency, observability/disclosure, and selection in the §-1.3 weight-not-filter direction (keep unknown-relevance rows down-weighted, never hard-drop a real source).

CAREFULLY read these 6 faithfulness/clinical-touching changes:
1. fix#19 parallel verify (provenance_generator.py `strict_verify`): is per-claim verdict ORDER preserved (pool.map index-aligned with `_findings_to_verify`)? any race on kept/dropped or `_excluded_empty`? is each sentence still the IDENTICAL gate (verify_sentence_provenance + reanchor)? is default-OFF (PG_PARALLEL_VERIFY unset/1) byte-identical to the serial loop? is the contextvars copy correct (telemetry/role/provider pin not lost)?
2. BUG-19 (provenance_generator.py `_load_boilerplate_helpers` + the strip/drop, and src/tools/access_bypass.py helpers): is the boilerplate/non-assertional filter allowlist-only + WHOLE-UNIT anchored so it can never drop a REAL clinical sentence (any language)? does it only remove gate INPUT, never change a verdict/threshold? is the excluded unit removed from BOTH numerator and denominator consistently?
3. BUG-14 (evidence_selector.py `_fetch_degenerate` + floor exemption): does it ONLY keep unknown-relevance stub/failed-fetch rows (down-weighted to sort last), and still DROP genuinely off-topic REAL (non-empty) content? could it admit junk?
4. BUG-7 (completeness_checker.py + config/completeness_checklists/clinical.yaml): could a false-negative drug/intervention detector SILENTLY disable the `abort_critical_topic_uncovered` safety abort on a real drug question? does it fail-closed / disclose on ambiguity?
5. BUG-17 (contradiction_detector.py + domain_signal.py): could the subject-precision / clinical-routing change DROP a TRUE contradiction whose subject extraction failed (subject=unknown)? it must surface-as-disclosure, never blanket-skip a real conflict.
6. keystone deadline (openrouter_client.py / entailment_judge.py / semantic_conflict_detector.py / credibility_judge_caller.py): transport-only? verdict logic + the fail-CLOSED `judge_error:` sentinel + the model/two-family lock all UNCHANGED?

KNOWN GAP (do NOT fail the gate on it): BUG-15 (Zyte never firing on the paywalled-anchor path) is DEFERRED to a separate runtime-diagnosis fix. BUG-14 keeps+flags stub rows for re-fetch, but the Zyte re-fetch trigger itself is not wired in this batch. Note it under remaining_blockers if you wish, but it is intentionally out of scope here.

OUTPUT EXACTLY this schema (loose prose is rejected):
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]

APPROVE iff zero NOVEL P0 AND zero P1 that relaxes a faithfulness gate or adds a silent-drop. A pure observability/perf/style nit is P2/P3, not a blocker.
