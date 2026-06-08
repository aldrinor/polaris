## ITER-4 RESOLUTIONS (final narrow edge cases — alias resolve path + plan-sufficiency re-cert)

Codex iter-4 narrowed to 2 precise edge cases + 2 P2 carriers. All resolved:

**P1-1 — fact-dedup ALIAS resolve path (FIXED):** fact-dedup creates FRESH post-dedup `SentenceVerification`s at `multi_section_generator.py:4910` and re-resolves through a LOCAL ALIAS `_resolve(final_svs, evidence_pool)` at `:4950` (a literal `resolve_provenance_to_citations(` grep misses the alias). The central P8 populate+render set therefore explicitly covers the fact-dedup alias too. **Full covered-emitter set (sweep-runner activation scope):**
- `multi_section_generator.py:2264` (legacy per-section)
- `multi_section_generator.py:4910`/`:4950` (fact-dedup fresh SVs + `_resolve` alias)
- `contract_section_runner.py:845` + its MANUAL regroup
- `quantified_analysis.py:380`
008b test: render a fact-dedup-REWRITTEN sentence through the `_resolve` alias and assert the disclosure fields are populated (not only the literal-grep sites).

**P1-2 — P10 dissent preserves plan-sufficiency certification (FIXED):** the saturation path re-gates adequacy after `evidence_for_gen = _billed` at `scripts/run_honest_sweep_r3.py:4332-4333`. A dissent round after `proceed` must NOT mutate the final generator-visible set without the same certification. Resolution: the P10 dissent round is **APPEND-ONLY / NO-EVICTION** (it only ADDS evidence; it never evicts a plan-sufficiency-certified row), AND `plan_sufficiency` is RE-RUN on the post-dissent final `evidence_for_gen` before generation (re-certify adequacy on the enlarged set). The fail-closed preflight asserts the post-dissent re-certification executed.

**P2 carriers:**
- **honest_pipeline.py:286 scope:** the master credibility activation is SCOPED to the sweep runner (`run_honest_sweep_r3` / `run_gate_b`) where the analysis context (credibility/origin maps) exists. `honest_pipeline.py:286` is a separate non-Gate-B entry OUTSIDE activation scope — a global resolver hook there would have no maps, so it is explicitly NOT activated (master off on that path). Documented; the coverage assertion's universe is the sweep-runner resolve sites only.
- **P3 certainty carrier:** P3's `certainty_downgrade` / `soft_warning` are carried EXPLICITLY into P8's `certainty_label` disclosure field (and surfaced in render) — not only folded into the post-P3 `credibility_weight`. So a superseded/retracted source's certainty downgrade is visible in the per-claim disclosure, not silently absorbed into a number.

**Net (locked, sweep-runner scope):** retrieve+mutate → hoist M-52 effective pool (later M-52 no-op) → credibility_pass over EFFECTIVE pool [P4 copied-annotated (fail-loud) → P2 (fail-loud judge_error) → P3 → credibility=P2×P3, certainty carried → P5 → P6] → if edges: P10 APPEND-ONLY dissent round (shared budget) → re-run plan_sufficiency on enlarged evidence_for_gen → generate → strict_verify (BINDING) → P8 POPULATE on every section's SV → SHARED disclosure render at ALL sweep-runner resolve emitters {2264, 4910/4950 alias, 845+regroup, 380} → assert every cited token covered (else abort_credibility_coverage_gap) → 4-role D8 over kept_sentences_pre_resolve (BINDING, both-sides appendix excluded) → assemble [P8 fields + P7 appendix].
