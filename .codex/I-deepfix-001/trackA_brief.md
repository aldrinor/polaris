HARD ITERATION CAP: 5 per document. This is iter 4 of 5.

## CHANGES SINCE ITER 3 (your three iter-3 findings ALL fixed — re-verify FIRST)
- **B16 epistemic P1a (methodological "assuming that…") FIXED** — `epistemic_overstatement_reason` is now VALUE-ANCHORED. New helper `_assumed_values_in_span` collects numbers ONLY from the assumption marker's OWN clause (up to the next `[,;:]` or a non-decimal `.`); the leg fires ONLY when (a) the span frames a specific VALUE as assumed AND (b) the claim ECHOES that same number AND (c) claim is empirical AND (d) claim carries no hedge. "Assuming that censoring was non-informative, … 12.3% reduction" → the in-clause after "Assuming that" has no number (12.3% is in the downstream result clause) → INERT. Added `test_leaf_epistemic_value_anchored`.
- **B18 table P1b (lost leading delimiter) FIXED** — `_repad_row(..., restore_leading=True)` restores ONE empty LEADING cell when a data row lost its leading pipe (`_LEADING_PIPE_PATTERN` no-match while the header has one), so values don't right-shift; remaining shortfall still right-pads. A row that kept its leading pipe is right-padded only. Added `test_lost_leading_delimiter_restores_leading_cell`; existing right-pad test unchanged.
- **D8 banner P2 (truthiness) FIXED** — `build_d8_unadjudicated_banner` now uses strict `release_disclosure.get("adjudicated") is not False` → emit ONLY on explicit `False`; None/0/""/missing → "". Added falsey-value asserts to `test_banner_silent_when_flag_missing_or_malformed`.

## CHANGES SINCE ITER 2 (fixed in iter 3, context only)
- **B16 epistemic over-drop P1 FIXED** in `overstatement_guard.py`: `_SPAN_ASSUMPTION_RE` is NARROWED to value-level assumption/projection framing only. Removed the bare noun `assumption(s)` and the bare verb `model(ed/ing)` (incl. "we modeled") that matched EMPIRICAL statistical-method prose. New triggers require explicit framing: `we assume(d)`, `if we assume`, `under the/an assumption`, `assuming a/an/the/that`, `we project(ed)`, `projected to`, `hypothes*`, `hypothetical`, `illustrative`, `for illustration`, `scenario analysis`, `simulat*`. Added `test_leaf_epistemic_no_false_drop_on_statistical_method_prose` asserting the four FP shapes you named ("proportional hazards assumption", "we modeled … via Cox regression", "outcomes were modeled using logistic regression", "the normality assumption held") return None while the value-level "we assumed 60%" true-positive still fires. Verify the narrowed trigger cannot drop empirical methods prose AND still catches a value rendered as a finding.

## CHANGES SINCE ITER 1 (both fixed in iter 2, re-confirmed by you — context only)
- **B16 P1 (temporal over-drop) FIXED** in `overstatement_guard.py`: `temporal_scope_reason` no longer does raw `(count, unit)` set-difference. It now converts every horizon to a MAGNITUDE IN DAYS (`_DAYS_PER_UNIT`: day/week/month=365/12/year/decade; year-range length×365) and fires ONLY on a genuine WIDENING — a claim horizon whose days exceed the span's LONGEST horizon by more than `_TEMPORAL_WIDEN_REL_TOLERANCE` (0.25). So "12 months" vs "one year", "52 weeks" vs "one year", "24 months" vs "two years", and any NARROWER claim horizon now PASS; only a claim asserting a longer horizon than the cited span drops. The `temporal_scope_mismatch:durations=…/ranges=…` reason format is unchanged. Verify: (a) equivalence + narrowing cannot drop; (b) real widening still drops; (c) still purely additive (only appends a reason).
- **B18 P2 (escaped pipe) FIXED** in `markdown_table_normalizer.py`: `_split_cells` now splits on `_UNESCAPED_PIPE_SPLIT = re.compile(r"(?<!\\)\|")` (a pipe not preceded by a backslash) instead of `body.split("|")`, and the trailing structural-pipe strip is escape-aware (`not body.endswith("\\|")`). An escaped `\|` now stays inside its cell. Verify no cell is dropped/reordered.

(The rest of this brief is unchanged from iter 1.)

- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

REVIEW MODE: STATIC ONLY. Do NOT run pytest / the pipeline / broad exploration. Read the combined diff at `.codex/I-deepfix-001/trackA_diff.patch` and the changed regions of the 6 source/script files it touches. Emit the verdict schema at the very end.

# I-deepfix-001 Track A (#1344) — 3 obvious-fix baskets, ONE combined diff gate

These are 3 independent, render/disclosure/verify-side fixes from the forensic campaign. All are env-gated default-ON with byte-identical OFF paths and fail-open. **The faithfulness engine (strict_verify numeric/span/content-overlap legs, NLI, 4-role D8, provenance) must NOT be relaxed.** Two of the three (B16) ADD strictness — review that boundary hardest.

## B8 — disclosure-to-render gap (files: scripts/run_honest_sweep_r3.py, src/polaris_graph/generator/provenance_generator.py, +test)
1. `build_d8_unadjudicated_banner(release_disclosure)` — prepends a top-of-report blockquote banner to report.md ONLY when `manifest['release_disclosure'].adjudicated == False` (the strongest verifier, four-role D8, did not bind this run). Returns "" when the flag is missing/malformed/truthy. Wired LAST in run_one_query (after all status reconciliation + chrome canary), idempotent (skips if marker present), gated `PG_REPORT_D8_BANNER` default-ON, fail-open.
2. `render_full_drop_disclosure_md(...)` — the "## Evidence-support disclosure" block now counts ALL drop categories (support-failed + un-provenanced + dedup-redundant + claim-frame/M-41c), not the support-failed subset only (prior block undercounted, e.g. "30 removed" when 49 were). Gated `PG_REPORT_FULL_DROP_DISCLOSURE` default-ON; legacy text preserved under the OFF branch.
3. Methods line now states the REAL generator vs evaluator training families via `family_from_model(...)` instead of the hardcoded "(different family)".

## B16 — numeric/temporal/epistemic overstatement guards (files: src/polaris_graph/generator/overstatement_guard.py [NEW], provenance_generator.py, live_deepseek_generator.py, +test) — FAITHFULNESS BOUNDARY
Adds TWO additive strict_verify-side legs invoked from `verify_sentence_provenance`, plus compose-prompt rule 11:
- Epistemic-marker preservation: DROPS a sentence that renders an assumption/modeled value as an empirical finding (span is explicitly an assumption AND the claim carries no hedge). Gated `PG_EPISTEMIC_MARKER_GUARD` default-ON.
- Temporal-scope match: DROPS a sentence that widens a year-range / horizon beyond the cited span ("over N years", "YYYY-YYYY"). Gated `PG_TEMPORAL_SCOPE_GUARD` default-ON.
The agent asserts: each leg ONLY appends a failure reason, NEVER clears one (so it can only make verify stricter, never looser); regex-lexical precision-over-recall (deliberately conservative to avoid false drops); flag-OFF reverts to PASS (additive proof).

## B18 — render/config defects (files: scripts/run_honest_sweep_r3.py, src/polaris_graph/generator/markdown_table_normalizer.py [NEW], src/polaris_graph/retrieval/contradiction_detector.py, +test)
1. `markdown_table_normalizer.py` — pure GFM table fixer: inserts the missing `| --- |` separator row and re-pads data rows to the header column count WITHOUT dropping the first cell or shifting columns. Wired at the render seam right after the existing render-seam sanitize.
2. `format_contradictions_for_user` — routes `possible_metric_mismatch`-marked records OUT of the headline contradiction count (kills junk like "437,481.7% rel_diff" as a quality signal) into a dedicated disclosure; every source still disclosed (§-1.3 keep-all). Default-ON, byte-identical OFF, fail-open.

## VERIFY HARDEST (be adversarial — these are the real risks)
1. **B16 over-drop (P0/P1 if real):** Can either new leg drop a LEGITIMATE empirical, correctly-scoped claim? Read `overstatement_guard.py` regexes + the `verify_sentence_provenance` call site. Is the empirical-vs-assumption discrimination sound, or will common clinical prose ("the trial demonstrated", "estimated", "projected over 5 years" matching its span) trip it? Over-dropping = breadth loss = real harm.
2. **B16 only-adds-never-clears:** Confirm neither leg can FLIP a fail→pass or suppress an existing failure reason. The legs must be strictly additive to the drop set.
3. **Faithfulness-neutral render (B8):** Confirm `render_full_drop_disclosure_md` and `build_d8_unadjudicated_banner` emit COUNTS / disclosure prose ONLY — never the raw dropped sentence text, never a citation token spliced into a finding, never resurrect a dropped claim as fact. (A support-failed sentence is generator-hallucinated; it must never ship as prose.)
4. **B8 banner honesty:** The banner fires on `adjudicated==False`. Confirm it reads the FINAL serialized flag (after A18/seam reconciliation) and cannot mislabel a genuinely-D8-judged run, nor suppress when D8 truly skipped.
5. **Default-ON OFF-path parity:** For every flag (PG_REPORT_D8_BANNER, PG_REPORT_FULL_DROP_DISCLOSURE, PG_EPISTEMIC_MARKER_GUARD, PG_TEMPORAL_SCOPE_GUARD), confirm OFF restores prior behavior.
6. **B18 table normalizer:** Confirm it never drops/reorders cells or fabricates data; only structural padding. And that contradiction re-routing still discloses every source (no silent drop).
7. **No faithfulness-engine edit:** Confirm strict_verify's existing numeric/span/overlap legs, NLI, span bounds, 4-role, provenance token parsing are UNCHANGED.

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
