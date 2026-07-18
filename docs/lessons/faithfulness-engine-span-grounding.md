# Lessons: Faithfulness engine & span grounding (runtime)

Canonical home: CLAUDE.md §9.1 invariants 2–4 + §-1.3 principle 3; memory `feedback_faithfulness_is_context_level_not_lexical_overlap_2026_07_10.md`, `project_4_role_architecture_locked_2026_05_28.md`, `feedback_faithfulness_engine_unlocked_serves_visible_quality_2026_07_10.md`.

This hub covers the runtime engine that is the ONLY hard gate for claims: strict_verify, NLI entailment, provenance tokens, the 4-role D8 judge, and basket faithfulness.

## The generator's span-selection must use the verifier's exact criteria

When a generator emits provenance spans that a separate verifier later checks, both must use identical span-selection logic and share the same helper functions (`_content_words`, `_decimals_in`). If the writer picks spans by one rule and strict_verify checks by another, correct claims get dropped for a purely mechanical mismatch at the boundary.

Why: Two components enforcing the same invariant with different code will disagree at the seam and silently discard good work. Retrieve-then-Generate also beats Generate-then-Ground for faithfulness.

Evidence: M-2 content-starvation (2026-04-18): the rewriter defaulted no-decimal sentences to span (0,200) (often the title) and gave decimal sentences ±30-char windows, both orthogonal to the content-word-overlap check strict_verify added later, causing an 80% drop. A content-aware sliding-window finder reusing strict_verify's exact helpers cut drops 80%→15% and 32%→3.7%.

Recurrence: One deep instance; a general principle for any produce-then-verify seam.

## Decide coverage against the whole basket with pooled, polarity-aware entailment — never a single-source string match

A required element or category is SATISFIED iff SOME verified claim ANYWHERE in the pool ENTAILS its requirement hypothesis (pooled, polarity-aware NLI, max-over-evidence), residual-only for spend. Do not compute coverage as an exact-string token match against ONE claim's cited tokens.

Why: Claim verification is multi-document by definition (SciFact, FActScore, MiniCheck); single-source verification is a blind spot. Tunnel-vision single-source coverage blocks a fully-grounded report over a literal string gap.

Evidence: `permanent_fix_migration_blueprint.md` I-perm-002 (`native_gate_b_inputs.py:312-352`, #1196): a must-cover gate fired "missing: contraindications" while the fact shipped VERIFIED on the page, because the shipped claim had "immunocompromised" but not the literal "contraindicated".

Recurrence: One-off root cause with a durable rule; matches §-1.3 basket faithfulness.

## Verify meaning at the atom level — force-route negation, numeric, entity, and qualitative atoms to entailment

Decompose each claim into atoms that cover EVERY assertion (including a contraindication clause), run entailment at the claim level, and require topical relevance BEFORE span-fidelity. Force-route any atom with a number, unit, named-entity, or qualitative negation to the strict entailment path regardless of the classifier's opinion; add an explicit specific→general directional clause to the entailment prompt. A judge that returns ENTAILED/VERIFIED must still be rebutted per-atom, not trusted.

Why: "did not reduce" and "reduced" share every content word, so a ≥2-content-word overlap check passes the exact opposite of the claim. Lexical, regex, and numeric checks are blind to polarity and to scope-widening ("all" vs "some"); a missed refutation is the lethal error. This is the code-level face of "faithfulness is context-level, not lexical."

Evidence: `polaris_fundamental_rearchitecture_plan.md` §3 Gap 16 / Regime C; `permanent_fix_migration_blueprint.md` I-perm-004 (#1180 widening); I-arch-004 F05/D2 (judge VERIFIED an "implemented" vs "study" misattribution, rubber-stamped 69/69), F06 (un-atomized contraindication clause); I-arch-006 BUG-19 (regex would drop a real "Metastases were absent"); beatboth CX-04/CX-09; memory `feedback_qualitative_negation_escapes_regex_2026_05_26`.

Recurrence: Recurring across the faithfulness-engine campaigns (I-arch-004, I-arch-006, beatboth, B_gen).

## Any intermediate check stricter than the binding gate is pure recall loss — make it non-blocking telemetry

If an earlier check is stricter than the final gate, it can only subtract recall with zero faithfulness benefit, because the final gate is the sole authority. Compute such a check for telemetry and never return None or hard-reject on it.

Why: The final strict_verify re-fits a prose-matched span over the whole direct_quote and re-checks numbers against THAT, so an earlier narrow-quote number check is redundant and only leaks recall — its own docstring called it "a cheap local pre-filter before entailment," but entailment was already non-blocking.

Evidence: `keystone_collapse_forensic_consolidated.md` PART 2 (`evidence_distiller.py:584`, #1217): step-4 `_all_numbers_in_span` hard-rejected any claim whose number was outside the model's narrow support_quote, leaving only the lone non-numeric claim.

Recurrence: Concrete recurring anti-pattern — mirror the already-non-blocking entailment.

## Spend the repair budget on evidence sufficiency, not on prose rewriting — delete phantom rewrite gates

Intrinsic LLM self-correction without external feedback does not improve faithfulness and often degrades it; a tighter-retry regen just re-prompts the SAME evidence and cannot add faithful content it did not have. The valuable repair is on EVIDENCE SUFFICIENCY (iterate retrieval until sufficient, then generate once). Delete a gate that blocks release for a rewrite the architecture never runs.

Why: Gains from intrinsic self-correction plateau after 1–2 rounds; a gate blocking on a phantom attempt is pure lost yield. The strongest permanent fix here was mostly deletion.

Evidence: `permanent_fix_migration_blueprint.md` I-perm-006 (`release_policy.py:296-297`, #1200): `d8_pending_rewrite` blocked release for a rewrite that structurally never ran (`rewrite_already_attempted` hardcoded False, no outer loop); ICLR 2024 arXiv:2310.01798 / 2306.09896.

Recurrence: One-off phantom with a durable self-correction lesson.

## On the safety path, fail CLOSED — withhold the body; a disclosed-gap note does not license shipping a clinical report

When a safety-floor or required-coverage check fails, withhold or downgrade the user-facing body to a clear non-answer and make the run's exit code non-zero for any non-success status. Emitting a normal-looking body plus a disclosed-gap note is a fail-open and is not acceptable on the clinical path.

Why: This is about what the READER receives. A report that looks complete but is missing diathermy or MRI contraindications will be trusted and acted on. The default on the clinical path is closed.

Evidence: `beatboth_p1_codex_verdict.txt` CX-02 (release_allowed=False, coverage=0.000, yet body_withheld=False so a normal body shipped); I-arch-004 F03 (partial status returns rc=0 GREEN, gap-stubbed clinical report ships), F26 (atom-refusal strict-mode fail-open).

Recurrence: Recurring in the clinical/beatboth verdicts; the class the §-1.1 "it is literal" standard exists to stop.
