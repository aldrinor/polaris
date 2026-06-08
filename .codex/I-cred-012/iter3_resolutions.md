## ITER-3 RESOLUTIONS (final two resolve-path edge cases; iter-2 design CONFIRMED by Codex)

Codex iter-3 confirmed the iter-2 design (effective-pool, post-P3 credibility, P4 copied-annotation, fail-loud, D8-exclusion, P10 shape all accepted). Two precise resolve-path edge cases remain — both resolved by treating P8 as POPULATE (on the SentenceVerifications) + a SHARED RENDER applied at EVERY site that emits cited prose, verified by a grep-confirmed enumeration of the FOUR live resolve call sites:

- `multi_section_generator.py:2264` (legacy per-section)
- `contract_section_runner.py:845` (V30 contract — see P1-1)
- `quantified_analysis.py:380` (quantified analysis — see P1-2)
- `honest_pipeline.py:286` (pipeline assembly)

**P1-1 — contract-section MANUAL regroup (FIXED):** `contract_section_runner.py` calls `resolve_provenance_to_citations` at :845 but then REBUILDS the final contract prose MANUALLY from `sv.sentence` + `[N]` markers (`resolved_body` is discarded). So a disclosure renderer living only in the resolver would NOT reach contract prose. Resolution: P8 POPULATE runs on the contract section's `SentenceVerification[]` BEFORE the manual regroup, and the SHARED disclosure renderer (the same helper the resolver uses) is applied in the contract regroup path so contract-section sentences carry the disclosure fields. 008b test: render a contract-section sentence through the manual regroup and assert the disclosure fields are present.

**P1-2 — quantified_analysis separate resolve path (FIXED — covered, NOT force-disabled):** the live Gate-B slate force-enables `PG_ENABLE_QUANTIFIED_ANALYSIS=1`; `generator/quantified_analysis.py:380` has its OWN `strict_verify → resolve_provenance_to_citations` path appending verified cited prose to `report.md` outside `SectionResult.kept_sentences_pre_resolve`. Resolution: the central P8 populate+render + the cited-token coverage assertion EXTEND to the quantified_analysis resolve site (380) — quantified analysis stays ON (no capability downgrade per the operator's no-silent-downgrade rule); its cited tokens are included in the `abort_credibility_coverage_gap` assertion universe. The coverage invariant "every cited kept token across ALL resolve sites has origin+credibility coverage" is enforced over all four sites including quantified_analysis.

**P2 confirmations (accepted as written):**
- M-52 effective-pool hoist: ensure the later generator M-52 path becomes a NO-OP (or reuses the same effective pool) so the analysis pass and the generator cannot diverge.
- P8 render in `provenance_generator`: additive disclosure ONLY (render already-populated inert fields, flag-gated); never touches verification decisions.
- P10 external bounded dissent round: run pass on effective pool → build dissent queries from P5/P6 contested set → spend through shared `preflight_round_budget` → re-run pass on enlarged effective pool before generation.

**Net (locked, all four resolve sites):** retrieve+mutate → hoist M-52 effective pool (later M-52 = no-op) → credibility_pass over EFFECTIVE pool [P4 copied-annotated rows (fail-loud missing eid/canonical) → P2 (fail-loud judge_error) → P3 → credibility=P2×P3 → P5 → P6] → if edges: P10 external bounded dissent round (shared budget) → re-run pass → generate → strict_verify (BINDING) → P8 POPULATE on each section's SV → SHARED disclosure render at all 4 resolve sites (2264 / 845+manual-regroup / 380 quantified / 286) → assert every cited token covered (else abort_credibility_coverage_gap) → 4-role D8 over kept_sentences_pre_resolve (BINDING, both-sides appendix excluded) → assemble [P8 fields + P7 appendix].
