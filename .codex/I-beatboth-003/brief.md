# Codex brief review — I-beatboth-003 (#1280): SURE-RAG per-citation relevance gate — INCREMENT 1 (F3-0 harness + F3-2 three-way judge + F3-3 label semantics + minimum-retention)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## FRONTIER-TECH MANDATE
Review ONLY against 2025-2026 frontier practice; no grandfather downgrade. The three papers below are dated + linked; reject any sourcing pre-2024 or any "the old POLARIS way is fine" reasoning. Verify each design claim against the cited primary source, not memory.

---

## GOAL (the WHY — helps both boards)
`strict_verify` is **relevance-BLIND**: invariant #3's `>=2-content-word` overlap (`PG_PROVENANCE_MIN_CONTENT_OVERLAP`) PASSES a source that shares two incidental words without establishing the required RELATION — the "off-topic-but-topical" case (right entity named, wrong relation). These off-topic citations spike **DeepTRACE** citation-imprecision AND dilute **DRB-II** relevance. This issue adds a **SURE-RAG-style three-way per-citation judgment ALONGSIDE strict_verify** — it LABELS each citation, it never holds/abstains/drops.

This brief reviews the **plan/acceptance correctness** for **INCREMENT 1 only** = **F3-0 + F3-2 + F3-3 + minimum-retention**. (Diff review is a separate gate.)

## ACCEPTANCE for this increment (each gated by a §-1.4 fail-loud replay-harness)

- **F3-0 (harness FIRST — mock judge = deterministic, NO spend):** given a FAKE judge labeling a citation `Insufficient` → it is DEMOTED from support to **listed-not-load-bearing** (NOT a support cite); `Refuted` → routed to a **contradiction flag**; the report **STILL ships** (always-release). Harness FAILS LOUD (non-zero exit) if (i) any `Insufficient`/`Refuted` source remains a support citation OR (ii) any statement goes cited→uncited (the over-drop tripwire).
- **F3-2:** add the three-way per-citation relevance judge in `provenance_generator.py` **ALONGSIDE** strict_verify, run by the campaign judge model (**GLM-5.2 via OpenRouter**; model + threshold env-configurable, LAW VI, conservative default), **fail-loud (not advisory)**, emitting a per-citation **LABEL** (Supported / Insufficient / Refuted). **Default-OFF, byte-identical when off.**
- **F3-3:** wire label semantics — `Supported` keeps the support citation; `Insufficient` demotes to listed-not-load-bearing; `Refuted` → contradiction edge. **MINIMUM-RETENTION GUARD:** demote an off-topic citation ONLY if `>=1` supporting citation remains, else re-anchor or mark the statement weak — **NEVER strand it uncited.**

## OUT OF SCOPE for this increment (do NOT flag their absence as a gap)
- **F3-1** two-layer render (inline load-bearing subset + appendix keyed by `corroboration_id`; reframe — never delete — "Corroborated Weighted Findings").
- **F3-4** threshold calibration on a banked set (calibrated-not-binary, per The Distracting Effect).
- **F3-5** the campaign-level §-1.4 acceptance gate (fail-loud replay on a real `corpus_snapshot.json`). NOTE: F3-0 here is the increment-1 harness (mock judge); F3-5 is the later campaign acceptance gate (real run) — keep them DISTINCT.

---

## 2026 grounding (verify against the primary sources)
- **SURE-RAG** (arXiv 2605.03534, 2026-05-05): three-way per-evidence **Supported / Insufficient / Refuted**; "Insufficient" = passage mentions the right entity WITHOUT establishing the required relation. **NATIVE SURE-RAG ABSTAINS below threshold — POLARIS must NOT import the abstain.** Convert to a per-citation LABEL: Supported=cite-as-support / Insufficient=listed-not-load-bearing / Refuted=contradiction-flag. The report still ships.
- **InfoGain-RAG** (arXiv 2509.12765, 2025-09-12): the **minimum-retention** guard (retain >=N documents / never strand a statement uncited).
- **The Distracting Effect** (arXiv 2505.06914, 2025-05): calibrated threshold, NOT a hard binary drop. (Calibration itself is F3-4 = out of scope; the conservative default + env-knob design is in scope.)

---

## BINDING faithfulness invariants (verify each is satisfied by the plan)
1. **ALWAYS-RELEASE.** The relevance judgment is a per-citation **LABEL**, NEVER a hold/abstain. The report ALWAYS ships. (`feedback_always_release_verifier_labels_never_holds`.)
2. **NEVER strand a statement uncited (minimum-retention).** Demote an off-topic citation ONLY if `>=1` genuinely-supporting citation remains; else re-anchor to a supporting span or mark the statement weak. Stranding a statement's LAST citation is FORBIDDEN — it would WORSEN DeepTRACE Unsupported.
3. **strict_verify / NLI / 4-role D8 / provenance / span-grounding = the ONLY hard gate, NEVER relaxed.** The relevance check is a **NEW ADDED dimension**, never a replacement, never a retrieval/consolidation DROP, never a cap/floor/thinner (§-1.3 WEIGHT-AND-CONSOLIDATE).
4. **Default-OFF + byte-identical when off.** New behavior fires only under the new env flag. OFF-byte-identity is defined over **behavioral/output fields + rendered artifacts**, NOT raw `dataclasses.asdict` (the established Codex iter-3 P2 scoping for the additive `judge_error` field — the new label field follows the SAME precedent).
5. **Judge model + threshold env-configurable (LAW VI).** Default **GLM-5.2 via OpenRouter**; no hardcoded model/threshold.
6. **F3-0 harness MOCKS the judge** (deterministic, NO LLM spend in the harness).

---

## CODE MAP (adjacent-file scan — so you VERIFY, not discover)

### 1. `src/polaris_graph/generator/provenance_generator.py` — the per-citation gate + label attachment point
- **Per-token loop** (`verify_sentence_provenance`): **lines 1846–1882**. Iterates `for tok in tokens:`, validates each token INDEPENDENTLY (`evidence_not_in_pool` / `span_out_of_bounds` / `span_invalid` / `fetch_shell_cited_span` [the I-beatboth-001 #1276 sibling gate]), appends to `failures`, and sets `valid_token_found`. The relevance judge attaches HERE (alongside, after the existing span checks).
- **`SentenceVerification` dataclass:** **lines 622–658**. Already carries additive side-output fields that are NEVER inputs to `is_verified`: `soft_warnings: list[str]`, `judge_error: bool`, `span_verdict: str` (e.g. "SUPPORTS"), `credibility_weight`, `independent_origin_count`, `reanchor_original_slot_id`. **The new per-citation LABEL must follow this EXACT additive pattern** (new field or `soft_warnings` carrier — see THE CRUX below).
- **Return point:** **line ~2341** (`return SentenceVerification(...)`), after `is_verified` is determined.
- **Reanchor machinery (REUSE for minimum-retention, do NOT reinvent):** `_provenance_reanchor_enabled()` (line 1158); reanchor telemetry dict + `get_reanchor_telemetry`/`reset_reanchor_telemetry` (lines ~1191–1204, counters `reanchor_attempts` / `reanchor_recovered` / `reanchor_uncited_bound`). This is the over-drop-recovery infra the minimum-retention guard should hang off.

### 2. `src/polaris_graph/llm/entailment_judge.py` — judge client + model selection
- **`class _EntailmentJudge`** line 400; **`judge(self, sentence, span) -> tuple[str, str]`** line 509 (returns the **NLI** taxonomy ENTAILED/…, NOT Supported/Insufficient/Refuted); **`_get_judge()`** singleton accessor line 885.
- **Model select:** `self._model = os.environ.get("PG_ENTAILMENT_MODEL", _DEFAULT_ENTAILMENT_MODEL)` (~line 431).
- **Default model:** `_DEFAULT_ENTAILMENT_MODEL = "z-ai/glm-5.1"` (line 82) — campaign overrides to **GLM-5.2** via env.
- **`check_family_segregation(evaluator_model=self._model)` is called in `__init__` (~line 440)** and `raise`s `RuntimeError` if evaluator and generator share a family. **See P0-class risk #2 below.**
- The relevance judge MUST have its **OWN prompt + OWN model env + OWN taxonomy** (Supported/Insufficient/Refuted) — NOT a silent relabel of the existing NLI `judge(sentence, span)` ENTAILED call.

---

## DISCRIMINATING QUESTIONS — the brief is APPROVE only if the plan answers all of these correctly

**P0-class risk #1 — per-CITATION vs per-SENTENCE topology (THE design crux).** The per-token loop (1846–1882) validates tokens independently but returns ONE `SentenceVerification` per sentence. I-beatboth-001 used "option (a)" — a bad token fails the WHOLE sentence (drop). **F3-3 demotion CANNOT use option (a):** dropping the sentence on an `Insufficient` citation would STRAND the statement, violating minimum-retention (invariant #2) and always-release (#1). So "demote a CITATION (not the sentence)" requires EITHER per-token labels (e.g. a per-token role map carried on the SV) OR a precisely-specified sentence-level rule that demotes the offending citation while KEEPING the sentence + its remaining support citations. **Verify the plan resolves this coherently and consistently with always-release + minimum-retention — it must NOT inherit option (a).**

**P0-class risk #2 — two-family segregation crash under all-GLM-5.2.** `_EntailmentJudge.__init__` calls `check_family_segregation(evaluator_model=self._model)` which `raise`s when evaluator==generator family. The campaign is **all-GLM-5.2 single family** (generator==judge==GLM, §9.1.1 deliberately OVERRIDDEN per MASTER_PLAN, model lock re-rolled). **If the new relevance judge builds on the entailment-judge infra, it INHERITS this check and the run crashes at judge construction.** Verify the plan: does instantiating the relevance judge re-trip `check_family_segregation` under all-GLM, and if so does it ride the SAME documented override (not a new silent bypass)?

**P1 — minimum-retention must be fail-LOUD, reuse existing infra.** The over-drop tripwire (statement cited→uncited) must FAIL LOUD (non-zero exit in the harness), not advisory. The retention/re-anchor path should REUSE `_provenance_reanchor_enabled` + reanchor telemetry, not reinvent. Verify.

**P1 — model is GLM-5.2, NOT GLM-5.1.** The design basis (`PHASE4_DESIGN_BASIS_2026.md` lines 112/125) says "locked GLM-5.1 mirror judge" — that text is **STALE** (pre-dates the all-GLM-5.2 pivot in MASTER_PLAN). The issue #1280 + MASTER_PLAN + binding invariants all say **GLM-5.2 via OpenRouter, env-configurable**. Verify the plan specifies GLM-5.2 and does NOT let the stale GLM-5.1 phrasing leak into the default.

**P1 — default-OFF byte-identity.** With the new flag OFF, the new judge must NOT instantiate, NOT call the LLM, and the rendered artifacts + behavioral/output fields must be byte-identical to HEAD. Verify the OFF path is a true no-op (the additive label field inert exactly like `judge_error`).

**P2 — relevance LABEL is a side-output, never an input to `is_verified` or the six strict_verify checks.** Like `span_verdict`/`soft_warnings`. Verify the plan does not feed the label back into the hard gate (that would relax/replace it — invariant #3).

**P2 — F3-0 harness asserts the EFFECT in the real path, not a config flag.** The mock-judge harness must drive the actual `verify_sentence_provenance` → render path and assert the demotion/contradiction-flag/always-ship effects + both tripwires, per §-1.4 (behavioral, fail-loud). Verify the acceptance is behavioral, not "flag is set / tests green."

---

## Files I have ALSO checked and they're clean (adjacent-file scan)
- **`provenance_generator.py`** — `SentenceVerification` (622–658) already hosts 6 additive side-output fields never read by `is_verified`; the additive-field + soft-warning pattern is proven and the right home for the LABEL. Per-token loop (1846–1882) is the single per-citation chokepoint; the I-beatboth-001 `fetch_shell_cited_span` gate sits in the same loop as a working precedent.
- **`entailment_judge.py`** — `judge()` returns the NLI taxonomy (ENTAILED/…), DISTINCT from Supported/Insufficient/Refuted; `check_family_segregation` in `__init__` is the segregation chokepoint; `PG_ENTAILMENT_MODEL` is the env precedent for a new `PG_*_RELEVANCE_MODEL` knob.
- **`openrouter_client.py`** — model routing / `check_family_segregation` source; the relevance judge routes through the same OpenRouter base-url (`OPENROUTER_BASE_URL` override honored).
- **Render/consumer paths** that read `span_verdict=="SUPPORTS"` / `verified_support_origin_count` (`weighted_enrichment.select_unbound_supports_by_weight`, `multi_section_generator` corroboration header, `disclosure_population`, `both_sides`) — the contradiction-edge routing (`Refuted`) targets the SAME both-sides/contradiction machinery I-beatboth design Fix 1 wires; this increment only sets the LABEL, it does not build F3-1 render.
- **Reanchor infra** (`_provenance_reanchor_enabled`, reanchor telemetry ~1191–1204) — the minimum-retention recovery hook; not reinvented.
- **Sibling brief** `.codex/I-beatboth-001/brief.md` — the cited-span shell gate in the SAME loop; confirms the additive-fail-closed pattern (but that gate DROPS; THIS gate must DEMOTE-not-drop — the crux).
- **`state/beatboth_campaign/PHASE4_DESIGN_BASIS_2026.md`** Fix 3b (lines 100/112/118–128) — the design source; its GLM-5.1 model phrasing is stale (superseded by all-GLM-5.2 MASTER_PLAN).
- **`state/beatboth_campaign/MASTER_PLAN.md`** — all-GLM-5.2 single-family lock + two-family override rationale.

---

## Output schema (§8.3.9 — emit EXACTLY this, no loose prose)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
