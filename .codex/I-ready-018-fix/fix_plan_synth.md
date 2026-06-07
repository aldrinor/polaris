This settles the A3 direction **decisively**, and it is the more dangerous interpretation:

- The **cited span [7500-8300]** ends in: *"AI users' sales grow faster. The growth rates amount to about **5.4% versus 3.7%**"* — i.e., the span is about **sales growth rates**.
- The **claim** is *"continuous R&D (**50% versus 19%**)"* — and `50% versus 19%` lives at index **8421**, in a sentence about *"the share of firms engaging in R&D on a permanent basis (the mean of RDCON is 50% versus 19%)"*.

So the printed token points at a span about **sales growth**, while the claim's number is about **R&D participation share** — a different metric, ~121 chars downstream. The NLI judge's exact words ("the span supports the sales growth figures but does not contain the specific percentages") match. The local-window fallback matched on generic content words (firms/AI/R&D) and passed it. This is a **genuine misattribution**, not benign span imprecision. Therefore fix direction **(B) — fail/flag the claim when the number is absent from the cited span** is the correct lead recommendation, with (A) as the inferior alternative that would paper over a real misattribution. I'll present both to Codex with this evidence, recommending B, and flag the I-gen-005 false-drop regression risk explicitly.

I now have complete, primary-source grounding for all five fixes. Writing the final plan.

# drb_72 (0.286) Release-Held — Consolidated Codex-Gateable Fix Plan

**Run:** `SWEEP_workforce_drb_72_ai_labor_1780848496` · status `abort_four_role_release_held` · `coverage_fraction=0.286` (< 0.700).
**Umbrella:** #1100. All targets below verified against working-tree HEAD on `bot/I-ready-consolidated`.

**Plan-level invariant (governs EVERY fix):** the acceptance criterion is **"drb_72 STILL HOLDS (`release_allowed=False`)"** — NOT "coverage improves." A variant that moves toward release IS the failure mode; the HOLD was correct per the §-1.1 re-audit. All offline smokes freeze the existing run artifacts (`manifest.json`, `report.md`, `four_role_claim_audit.json`, `evidence_pool.json`, `four_role_role_calls.jsonl`) into `tests/fixtures/drb72/` and assert per-fix deltas — **no pipeline re-run, no paid spend** until the final operator-gated canary.

---

## 1. Ordered list of fixes (each: target, change, offline smoke)

### FIX-A3 — span-provenance misattribution (P0, faithfulness, §-1.1 lethal-class — LEAD, and most dangerous to change)

**Target:** `src/polaris_graph/generator/provenance_generator.py:1316-1358` — the `_find_local_support_window` fallback inside `verify_sentence_provenance`.

**Evidence (primary-source, this run):** claim `03-004` "...continuous R&D (50% versus 19%)" prints token `[#ev:ev_037:7500-8300]`. In `ev_037.direct_quote`, `50% versus 19%` is at **index 8421** — outside the span. Bare `50` and `19` appear **nowhere** in `[7500-8300]` (so it is not a coincidental-substring false-match). The cited span ends at *"sales grow faster. The growth rates amount to about 5.4% versus 3.7%"* (**sales-growth metric**); the claim's number is from *"the mean of RDCON is 50% versus 19%"* (**R&D-participation metric**), 121 chars downstream. The local-window fallback (lines 1318-1351) scanned the whole `direct_quote` in a 400-byte window, matched on generic content words (firms/AI/R&D), logged "span_imprecise but locally grounded; passing," and passed it VERIFIED. The 4-role D8 also marked it VERIFIED; only the advisory NLI path (gemma) caught it NEUTRAL. **This is a genuine cross-metric misattribution, not benign imprecision.**

**This change reverts a Codex-approved tradeoff — route the direction to Codex.** Lines 1318-1323 state the local-window fallback is *intentional* (I-gen-005 Step 1, Codex P1 #1) and was built to prevent a different failure ("cancer-50% in an unrelated paragraph" false-drop). So a naive tightening reintroduces the false-drop regression I-gen-005 was avoiding — the same M-68 trap FIX-SLOT avoids. **Present two options to Codex with the 8421 evidence attached; recommend (B):**

- **(B) RECOMMENDED — fail/flag when the number is absent from the cited span.** When `missing_in_span` is non-empty AND the local window's matched offset lies outside the printed token's `[start,end]`, append `number_not_in_cited_span` and DROP the claim (do not pass on the local window). The §-1.1 violation is "the printed citation token does not contain the number" — only (B) closes it. False-drop risk is bounded: re-pointing exists as the fallback if Codex rejects (B).
- **(A) inferior — honest-token re-pointing.** When the local window fires, re-emit the printed token to the window where the number was actually found. Preserves I-gen-005 intent but, given this is a *cross-metric* misattribution (sales-growth span vs R&D claim), (A) would paper over a real misattribution by silently moving the token to a span the generator never claimed — rejected as the lead.

**Offline smoke (no spend):** `tests/polaris_graph/test_a3_span_provenance.py` — construct `ev_037` from the frozen fixture, call `verify_sentence_provenance` on the exact `03-004` sentence + token `[7500-8300]`. Assert under (B) the result is a DROP/FAIL with reason `number_not_in_cited_span` (not VERIFIED with an excluded-number token). Add a **false-drop guard** case: a claim whose number genuinely IS inside its cited span still passes (proves we did not over-tighten). Add the I-gen-005 regression case ("cancer-50% in an unrelated paragraph" → still correctly fails). Assert frozen `manifest.json` re-scored under the new gate keeps `release_allowed=False`.

---

### FIX-SLOT — template-slot "not extractable" placeholder leakage (P1, coverage-killer, the best-analyzed fix)

**Target:** `src/polaris_graph/generator/slot_fill.py:674-732` — `render_slot_prose()`, specifically the `not_extractable` branch (724-727) and the mixed `gap_unrecoverable` branch (728-731).

**Change:** in the per-field loop, SKIP fields with `status != "extracted"` — do not append a sentence for `not_extractable` or mixed `gap_unrecoverable` fields. Render only `extracted` fields. The existing `all_gap` short-circuit (699-706) is untouched. **Verified fall-through:** if every field is non-extracted, `sentences` is empty → `render_slot_prose` returns `""` → `slot_det_prose.append("")` (contract_section_runner.py:650) yields an empty deterministic stream → strict_verify keeps 0 → the slot falls to the EXISTING zero-kept gap path (`contract_section_runner.py:945-1011`), which emits ONE honest *"Contract-bound content for {entity} did not survive strict verification ... curator-actionable gap [N]"* sentence (the same shape Frey-Osborne already gets at report.md:30, disposition `rendered_as_gap_disclosure`). The honest disclosure is NOT lost — it persists in `manifest.frame_coverage_report` (status `curator_gap_no_substantive_content`) and `human_gap_tasks.json`. This is one cut upstream of strict_verify, the rescue exemption (contract_section_runner.py:124-125), and Gate-B claim extraction, so placeholders never enter ANY of those paths.

**Offline smoke (no spend):** `tests/polaris_graph/test_m58_slot_fill.py` (UPDATE — remove the now-dead `not_extractable`-render assertion; do NOT loosen any faithfulness assertion). Add: (1) a payload with all-`not_extractable` fields → `render_slot_prose` returns `""`; (2) a partial payload (some extracted, some not) → output contains ONLY the extracted-field sentences, zero `_NOT_EXTRACTABLE_PHRASE`; (3) **fall-through end-to-end**: feed an empty `slot_det_prose` through the contract_section_runner slot loop and assert the slot still emits the gap heading + the one gap-disclosure sentence (proves no silent slot omission — the run-7 structural-LB regression M-68 Fix #1 guards). Assert the frozen drb_72 manifest, with placeholders removed, keeps `coverage_fraction < 0.70` and `release_allowed=False` (denominator is the fixed required-entity set at `native_gate_b_inputs.py:448`, unchanged; dropping a placeholder-only entity's claim can only LOWER the numerator → stronger hold).

---

### FIX-BP — hardcoded clinical/diabetes boilerplate in contradiction disclosure (P1, domain leak)

**Target:** `scripts/run_honest_sweep_r3.py:5202-5205` — the hardcoded `"(e.g. HbA1c % vs body-weight %), different doses, different populations (T2D vs obesity-without-diabetes)"` inside the unguarded `if contradictions:` block.

**Change:** replace the clinical parenthetical with domain-agnostic category words, e.g. *"different measured endpoints, units, sub-populations, time windows, or comparators."* The concrete subject/predicate pairs already render below via the per-flag enumeration loop (5211-5247), so the abstract example sentence can drop the parenthetical clinical instances entirely. **PT08 safety:** the evaluator's PT08 disclosure check requires each contradiction's subject+predicate to appear verbatim in report text — that is satisfied by the enumeration loop (5211-5247), NOT by the example sentence, so removing the clinical parenthetical does not break PT08. (Secondary, lower-severity, OPTIONAL same-PR or follow-up: de-clinicalize the generator few-shot examples at `multi_section_generator.py:1085-1115/1148/1151-1153`, or gate the trial-summary-table prompt to clinical domains only — this is byte-affecting for ALL domains, so it needs a generator regression smoke before shipping; recommend splitting to its own item to keep this PR text-only and low-risk.)

**Offline smoke (no spend):** `tests/polaris_graph/test_contradiction_disclosure_domain_neutral.py` — render the disclosure block with a non-clinical `contradictions` list; assert output contains NO `HbA1c`/`T2D`/`obesity`/`body-weight` and DOES contain each contradiction's subject+predicate verbatim (PT08 invariant holds). Snapshot the rendered block to lock byte-shape.

---

### FIX-JO — journal_only filter never activated for the drb_72 run (P1, corpus-quality wiring)

**Target:** `scripts/dr_benchmark/run_gate_b.py` — the full-capability slate (≈418-903). The slate force-sets `PG_SWEEP_*`, NLI, STORM, safety-refusal, table-cell-verify, etc. but contains **no** `PG_SOURCE_RESTRICTION_JOURNAL_ONLY` entry. Activation requires `PG_SOURCE_RESTRICTION_JOURNAL_ONLY=1` (`journal_only_filter.py:45,62-83`) AND protocol `source_restriction: journal_only` (`workforce.yaml:93`); the loader correctly preserves `source_restriction` (`scope_gate.py:220`), so the ONLY missing condition was the flag.

**Change — PER-QUESTION, not a blanket global (this is the load-bearing constraint):** `workforce.yaml:77-87` is explicit that the generic T3 statistical-agency contract is correct for general workforce questions and journal_only is intended only for literature-review questions like drb_72; a global flag-on would force journal_only onto every workforce query and kill the intended T3 path. In order of preference: **(1)** set `PG_SOURCE_RESTRICTION_JOURNAL_ONLY=1` only in the per-question Gate-B invocation keyed by slug (the slate already keys per-slug required_entities at run_gate_b.py:22), OR **(2)** move `source_restriction` out of the always-on template into a per-question contract so activation is question-driven.

**Honesty caveat that MUST be in the brief (do not let Codex or operator infer "set the flag → run passes"):** activating journal_only does NOT make drb_72 shippable. The primary failure (`coverage_fraction 0.286`) is FIX-SLOT slot degeneracy + unfetchable full text (Frey-Osborne/Eloundou contributed ~nothing), independent of tier mix. journal_only cleans the corpus contract; it does not raise coverage. It may instead trip `abort_corpus_inadequate` / `abort_journal_only_contract_conflict` (the `is_citeable_journal` OpenAlex peer-review sidecar is absent from this run's artifacts, so the ≥12-distinct-journals + 4-anchor-DOI floor cannot be confirmed offline). That is confirmable only on an ON-path rerun (operator budget-gated).

**Offline smoke (no spend):** `tests/dr_benchmark/test_gate_b_journal_only_per_slug.py` — assert that for slug `drb_72_ai_labor` the slate sets `PG_SOURCE_RESTRICTION_JOURNAL_ONLY=1` and `journal_only_active(load_scope_template('workforce'))` returns True; assert that for a non-journal workforce slug the flag is NOT set and `journal_only_active(...)` is False (proves no blanket activation, T3 path preserved). No corpus re-run.

---

### FIX-GLM — Mirror provider routing hardening (P2, config-only, see Decision §2)

**Target:** `config/settings/openrouter_provider_routing.yaml:13-14` (Mirror chain). **Confirmed NOT in `docs/canonical_pin.txt`** → no §3.1 halt; LAW VI config-only, no lock edit, no model swap.

**Change:** remove `parasail` from the Mirror `order` (line 13, currently `[friendli, parasail, io-net, fireworks, baidu, siliconflow]`) and add `parasail` to the Mirror `ignore` list (line 14). Io Net (0/39 blank) + the remaining providers cover the role. Optional small code hardening (separate follow-up): persist the per-claim blanked-provider exclusion across claims (transport-instance-scoped ignore set) so a provider that blanks early is not re-tried at order-position 2 every claim.

**Offline smoke (no spend):** `tests/polaris_graph/test_mirror_routing_excludes_parasail.py` — load the YAML, assert `parasail not in mirror.order` and `parasail in mirror.ignore`; assert the other three role chains are byte-unchanged; assert `allow_fallbacks:false` and `require_parameters:true` for Mirror are preserved. No network.

---

## 2. DECISION on GLM — KEEP + config-only failover (NO swap)

**Decision: keep `z-ai/glm-5.1` as Mirror; do NOT swap.** Hardening is config-only (FIX-GLM above).

**Rationale, grounded in this run's primary evidence:**
- Per-provider blank rates: **Io Net 0/39 (0%)**, Friendli 1/17 (5.9%), Parasail 23/126 (18.3%). GLM is blank-free on the cleanest provider → the model is not the cause.
- Blank anatomy: 23 of 24 blanks are **Parasail clean-200 empties** (`finish_reason=stop`, ~8-11 tokens, `content=None`) — the textbook intermittent-provider empty-200, exactly the PR #1052 lesson ("Mirror blank = INTERMITTENT PROVIDER FAILURE, not the model"). The single budget-exhaustion blank is Friendli (`finish_reason=length`, 23,325 reasoning tokens despite the 4000 cap).
- **Zero functional impact:** `four_role_role_calls.jsonl` shows 158 successful Mirror verdicts, all 158 claims covered, 100% of the 24 blanks recovered by retries. The run's HOLD was the unrelated `coverage_fraction=0.286` quality gate; there is no `judge_error_rate>=0.10` / `abort_verifier_degraded` threshold in current code.
- **Open-weight lock + two-family:** a swap would break the certified 4-distinct-family slate (Mirror=glm / Sentinel=minimax / Judge=qwen / Generator=deepseek) and the runtime lock — for a problem that is provider-side and already auto-recovered. The named bake-off candidate is therefore NOT triggered. (Only IF a future bake-off shows GLM itself is unstable across ALL healthy providers would the contingency open: strongest open-weight, non-GPT/Claude/Gemini, family-distinct-from-minimax/qwen/deepseek candidates = `moonshotai/kimi-k2` (Modified-MIT) or `mistralai` Large — both open-weight per the lock. Not now.)

The fix is to **stop routing the binding Mirror through Parasail**, not to replace the certified model.

---

## 3. NEW issues from the re-audit, prioritized

**P0**
- **A3 span misattribution** — covered as FIX-A3 above (the headline correction: the HOLD was coverage-driven and the 4-role gate MISSED this real provenance defect). File under #1100, but treat as its own URGENT GitHub issue given it touches the core faithfulness gate.
- **A9 silent capability degradation (quantified analysis):** `quantified_analysis enabled=True` but `execution_success=False, fired=False, spec_produced=False, outputs=0` despite 111 sourced numbers extracted — undisclosed in the report. Operator-furious-class silent downgrade (LAW II, `feedback_no_downgrade_without_operator_approval`). Needs root-cause issue: why it silently no-op'd, plus a fail-loud + report-disclosure surface.
- **A10 silent retrieval degradation:** 62% of fetch attempts failed (`fetch_failed=163`, `manifest.retrieval.failed=129`, `parallel_fetch_timeout_count=129`), undisclosed. Primary upstream driver of the low-coverage output. Fail-loud + disclose-in-report issue. (Both A9 and A10 are P0/P1 — the operator no-downgrade directive makes "silent + undisclosed" the high-harm property, independent of severity of the underlying capability.)

**P1**
- **A1 degenerate contradiction cluster (≠ FIX-BP):** the contradiction **detector** groups 5 unrelated numbers (poverty % vs story-enjoyment % vs graph-vertex-share %) under `subject='unknown'/predicate='ttr'` and ships a bogus 53.3% "high-severity" disagreement to report Limitations. Different root cause and different file than the boilerplate string — this is the detector/grouping logic, not the disclosure renderer. Own issue.
- **A2 three inconsistent tier distributions:** manifest (T1 19.8/T4 41.9/T7 17.7) vs report Methods (T1 17/T4 50/T7 9) vs report Limitations (20% T1/42% T4, T7 omitted) — the report disagrees with itself. Tier-disclosure consistency issue: single source of truth for the rendered numbers.
- **A4 selected-evidence far worse than disclosed:** generation input was T1=2 / T4=8 / UNKNOWN=2 (67% T4); the corpus-level "20% T1" disclosure masks an 8/12-low-tier generator input. Directly breaches the "only high-quality journal articles" ask. Partly addressed by FIX-JO ON-path, but the *disclosure* gap (selected vs corpus tier mix) is its own surface.
- **A6 non-journal source in T1 bucket:** bibliography [3] `fourth_industrial_revolution_framing` is tier-tagged T1 but `journal=''`, `year=None`, content is a WEForum nav dump — inflates the disclosed T1 fraction. T1-bucket gating issue (require journal+year for T1).

**P2**
- **A5 four-role verdict miscalibration:** 03-002 (span-supported 15%) marked UNSUPPORTED on a benign connective phrase while 03-004 (the real defect) marked VERIFIED — gate over-penalizes framing prose, under-penalizes span-binding. Track; FIX-A3 addresses the under-penalty leg.
- **A7 missing bibliography URLs** for [4]/[6]/[7] (2 of 4 flagship numeric papers) — reader cannot reach the sources.
- **A8 secondary "cited in the literature" attribution** under [8] (Behrens & Trunschke +8.3% presented as a Czarnitzki finding) — citation-appropriateness, correctly span-bound, not fabrication.
- **Bare "." empty sentences** in `nli_verification.disputed` — a SEPARATE splitter degeneracy (empty-string sentences surviving the splitter); explicitly out of scope for FIX-SLOT, own item.

---

## 4. Faithfulness-safety argument per fix (must not weaken strict_verify / 4-role D8 / provenance / two-family)

- **FIX-A3 (option B):** STRENGTHENS the provenance gate — it makes the printed citation token a *necessary* container of the claimed number, closing the §-1.1 "number not in cited span" hole. It does not relax any existing check (numeric-match, content-overlap, span-bounds all still run). The only risk is over-tightening (false-drop), which is why the I-gen-005 regression case + the false-drop guard case are mandatory smokes, and why the direction is routed to Codex.
- **FIX-SLOT:** touches NO faithfulness gate. It operates UPSTREAM of strict_verify, the rescue exemption, NLI, the 4-role D8, and `verify_sentence_provenance` — those all keep operating on real extracted prose only. Gate-neutrality is provable: coverage denominator is the fixed required-entity set (unchanged); placeholder claims never advanced the substantive numerator; dropping a placeholder-only entity's claim can only LOWER coverage (stronger hold), never relax it. The honest gap disclosure is preserved via the existing zero-kept gap path. Two-family untouched.
- **FIX-BP:** text-only edit to a disclosure string; no gate, no model, no provenance path touched. PT08 invariant preserved by the enumeration loop. Two-family untouched.
- **FIX-JO:** STRENGTHENS the corpus contract (restricts citeable set to T1/T2 + adds the ≥12-journals/4-DOI floor) when active; default-OFF byte-identical, so it cannot weaken any non-journal run. No per-sentence faithfulness gate touched. Two-family untouched.
- **FIX-GLM:** config-only routing change; does not touch any gate, the runtime lock, or the 4-distinct-family slate. Mirror stays glm (two-family preserved). `allow_fallbacks:false` + `require_parameters:true` preserved. STRENGTHENS reliability of the verifier path by removing a flaky provider.

---

## 5. Sequence: per-fix Codex diff-gate (5-iter cap) + offline micro-smoke, then operator-gated canary re-run

Recommended order (independent fixes, each its own branch + brief + diff + Codex diff-gate per §3.0; 5-iter cap per §8.3.1; smoke offline before brief per §-1.2):

1. **FIX-A3** (P0, lead). Brief Codex with the 8421 evidence + both options (A)/(B), recommend (B), flag the I-gen-005 false-drop regression risk explicitly. Codex diff-gate. Offline micro-smoke `test_a3_span_provenance.py` (incl. false-drop guard + I-gen-005 regression case). Most-dangerous-to-change → highest Codex scrutiny.
2. **FIX-SLOT** (P1). Codex diff-gate. Offline smoke incl. the fall-through end-to-end case + drb_72-still-HOLDS assertion.
3. **FIX-BP** (P1, text-only, fast). Codex diff-gate. Offline PT08-preserving snapshot smoke.
4. **FIX-JO** (P1). Codex diff-gate — brief MUST carry the "flag does not make drb_72 shippable" honesty caveat + the per-question (not global) constraint. Offline per-slug activation smoke.
5. **FIX-GLM** (P2, config-only). Codex diff-gate. Offline routing-YAML smoke.

Per-step micro-smoke is offline and free. After all five land (Codex-APPROVE + CI-green), and only then:

**Final re-run — operator budget-gated, behind the canary.** A single drb_72 ON-path re-run (journal_only active, all fixes in) confirms end-to-end. **NO-SPEND `--list` first**; operator sets `PG_AUTHORIZED_SWEEP_APPROVAL` (Claude never self-sets that or the budget); built-in canary armed; monitor via `tail run_status.json` + `retrieval_trace.jsonl`. **Real acceptance = a fresh §-1.1 line-by-line audit of the new report (claim-by-claim vs cited span)**, NOT "coverage went up" — and the expected, correct outcome remains `release_allowed=False` unless genuine substantive coverage clears 0.70 on real extracted prose. Per the runbook in `state/q1_run_prep_one_go_ahead.md`.

---

**Verified file:line targets (all primary-source-confirmed this session):**
- `src/polaris_graph/generator/provenance_generator.py:1316-1358` (FIX-A3)
- `src/polaris_graph/generator/slot_fill.py:674-732` (FIX-SLOT); fall-through sink `src/polaris_graph/generator/contract_section_runner.py:945-1011`; rescue exemption `:124-125`; append site `:650`
- `scripts/run_honest_sweep_r3.py:5202-5205` (FIX-BP); secondary `src/polaris_graph/generator/multi_section_generator.py:1085-1115/1148/1151-1153`
- `scripts/dr_benchmark/run_gate_b.py:~418-903` slate (FIX-JO); flag def `src/polaris_graph/nodes/journal_only_filter.py:45,62-83`; protocol `config/scope_templates/workforce.yaml:93`; loader `src/polaris_graph/nodes/scope_gate.py:220`
- `config/settings/openrouter_provider_routing.yaml:13-14` (FIX-GLM; confirmed NOT canonical-pinned)