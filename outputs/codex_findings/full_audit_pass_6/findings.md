---
verdict: CONDITIONAL
pass: 6
commit: 3921bc0
m6_sound: false
m3_sound: true
m4_sound: true
m2_deferral_reasonable: true
new_blockers: 0
new_mediums: 1
rationale: |
  The M-3 advisory gate wiring is sound, and I found no downstream consumer that parses manifest.evaluator_gate.reasons in a way that would be confused by the new advisory_ prefix. M-2 deferral remains reasonable before the sweep: the content-aware span finder attacks the measured root cause, and per-template overlap changes would trade away semantic grounding without new sweep evidence. M-6 creates one new advisory-signal evasion: a research_question containing the single-word PT13 superlative vocabulary suppresses those exact terms throughout prose, so PT13 can silently pass adversarial generator claims. M-4's runbook framing is directionally right, but material_deviation is not actually auto-approved; it ships only when the note check passes, and that check is minimal rather than deeply semantic.
---

## 1. M-6 PT13 title + question-inherited exemption

The title-line strip only removes line 0 if that exact first line is an H1 (`lines_pt13[0].lstrip().startswith("# ")`). That is acceptable for the current report shape, which is assembled as `# Research report: ...` at byte 0, but it is not a general Markdown H1 detector. If a report starts with a blank line, YAML/frontmatter, or a code fence before the H1, the title is not stripped. That is mostly harmless for current generated artifacts, but it is a brittle assumption.

The multi-word case is correctly left unexempted. `question_superlatives` is built from a regex containing only single-word alternatives (`best`, `superior`, `unmatched`, etc.), while `_detect_unhedged_superlative()` can return multi-word phrases such as `better than`, `most effective`, and `more effective than`. The exemption compares the full matched phrase to the single-word set, so `best practices` only contributes `best`; it does not exempt `best practices`, `better than`, or other multi-word comparative claims.

There is a real evasion risk. I confirmed with a direct evaluator call that this research question:

`best leading superior top unparalleled unmatched unprecedented largest highest greatest`

causes a report containing unhedged prose such as `This method is unparalleled. It is unmatched. It is the greatest. It is superior.` to pass PT13 with empty details. The suppression is exact-word and bounded to the listed vocabulary, and PT13 is advisory, so this is not a release-integrity blocker. It is still a new silent-loss-of-signal mode introduced by M-6 because the PT13 advisory can disappear entirely instead of surfacing in `manifest.evaluator_gate.reasons`.

Recommended targeted fix before sweep: keep title stripping, but narrow the prose exemption. Options include applying question-inherited exemption only to the H1/title sentence, capping it to a small number of inherited words, or requiring the prose sentence to be a close lexical echo of the research question rather than exempting the word globally.

## 2. M-3 PT13 advisory surfacing

`ADVISORY_RULES` is symmetric with the existing gate maps: rule ID to stable reason code. The implementation appends `advisory_pt13_unhedged_superlatives` to `reasons`, does not append PT13 to `rule_blockers`, and does not set `abort_on_rule`. As a result, a PT13-only failure leaves `gate_class=pass` and `release_allowed=True`, while other abort/partial causes still dominate. That matches the intended advisory semantics.

I searched source, tests, and docs for downstream `evaluator_gate`/`reasons` consumers. The only code consumer is `graph_v4.py`, which passes the manifest field through; tests assert field presence or exact expected reason strings. I did not find a reader that parses reason prefixes as an exhaustive enum or treats unknown prefixes as blocking. The `advisory_` prefix is therefore unlikely to confuse downstream code.

Focused tests passed:

`python -m pytest tests/polaris_graph/test_external_evaluator.py::test_pt13_exempts_title_and_question_inherited_superlatives tests/polaris_graph/test_external_evaluator.py::test_pt13_still_flags_real_generator_superlatives tests/polaris_graph/test_m205_evaluator_gate.py::test_m3_pt13_failure_surfaces_in_reasons_without_gating tests/polaris_graph/test_m205_evaluator_gate.py::test_m3_pt13_passing_does_not_emit_advisory_reason -q`

Result: 4 passed, with only the existing `.pytest_cache` WinError 5 warning.

## 3. M-4 runbook material_deviation section

The framing is mostly accurate: a released manifest with `corpus.material_deviation=true` should be read as pipeline reliability evidence, not as a clean content-quality benchmark. The manifest and `corpus_approval.json` expose the skew, and downstream evaluator/adequacy/completeness still run.

The wording at `docs/runbook.md` line 212 is loose. `corpus_approval_gate` does not auto-approve material deviations: `compute_tier_distribution()` sets `auto_approve_allowed=False` when a material deviation exists, and the sweep runner calls `check_auto_approve_allowed()` before proceeding. If approval is denied, `scripts/run_honest_sweep_r3.py` emits `abort_corpus_approval_denied` before synthesis. So the factual rule is: material_deviation runs ship only if the operator/sweep note passes the note check, plus downstream gates pass.

One caveat: the code's "substantive" check is shallow. It requires at least 30 stripped characters and rejects only exact trivial phrases such as `ok`, `approved`, and `looks fine`. The live M-6 artifact passed with `R-3 sweep. Domain=tech. Auto-approve on sweep.`, which satisfies length/non-exact-trivial checks but is not a domain-specific explanation. This does not break the M-4 runbook framing, but the runbook should not imply a deeper semantic review than the code performs.

The listed re-run levers are real: `PG_LIVE_MAX_SERPER_PER_Q` controls Serper results per query in the sweep runner/live retriever path, domain backends exist and are wired for tech/policy/due-diligence augmentation, and narrowing the question affects scope validation, search queries, and off-topic filtering.

## 4. M-2 docs-only deferral

The deferral is reasonable pre-sweep. The content-aware span finder now selects a default 500-character window that maximizes content-word overlap while preserving the decimal hard requirement, which directly targets the measured drop causes from pass 4/5. Tests cover no-decimal content-rich windows, multi-decimal windows, tail windows, and the `PG_PROVENANCE_SPAN_WINDOW` override.

I do not recommend implementing per-template `PG_PROVENANCE_MIN_CONTENT_OVERLAP` before the sweep. The current default of 2 is the semantic grounding floor, and lowering it per template risks reintroducing one-anchor false verification. The documented option remains appropriate if the 8-query sweep shows a specific short-sentence/domain regression.

## 5. Suite state

Full suite command:

`python -m pytest tests/polaris_graph/ -q`

Result in this Codex shell: 428 collected, 403 passed, 2 failed, 23 errored, 3 warnings. The failures/errors reproduce the previously noted Windows temp/cache permission issue: `PermissionError: [WinError 5] Access is denied` under `C:\Users\msn\AppData\Local\Temp\pytest-of-msn`, plus `.pytest_cache` write warnings. The M-3/M-6 focused tests passed separately.

## 6. Final verdict

CONDITIONAL.

No new blocker was found. One new medium should be fixed before the 8-query sweep: constrain M-6's question-inherited PT13 exemption so an adversarial or overloaded `research_question` cannot globally suppress all single-word superlative advisories in generated prose.
