# PREFLIGHT SPEC — v2 CORRECTIONS (Codex completeness gate iter-1)

Amends `PREFLIGHT_SPEC.md`. Where this file and the base spec disagree, THIS file wins. Codex iter-1 verdict on the base spec: **REQUEST_CHANGES** — `covers_all_6_residuals_behaviorally: false`, `covers_all_winners_firing: false`, `faithfulness_bar_airtight: false`, 4 novel P0. All findings incorporated below. The base spec + this layer will be RE-GATED (iter-2) until APPROVE before any paid run.

## A. SSOT resolution (model / family / lock) — was a real conflict
- **Generator = GLM-5.2**, **D8 terminal judge = moonshotai/kimi-k2.6** (distinct family), mirror = GLM-5.2, sentinel = minimax. This is the **beat-both benchmark override** of `config/architecture/polaris_runtime_lock.yaml` (which still pins deepseek-v4-pro generator + qwen judge, the sovereign config). The override is DELIBERATE (all-GLM campaign, sovereignty dropped, $300 banked) and MUST be NAMED in the run manifest, not silent. Preflight 0.2/0.3 assert the RESOLVED benchmark models AND that the run manifest DISCLOSES the lock-override. **Operator to confirm the override or update the lock.**
- **`PG_PERMIT_GENERATOR_EVALUATOR_SAME_FAMILY=1`** governs ONLY the disclosed all-GLM SIDE surface (GLM generator vs GLM external-evaluator/side-checkers). `assert_four_role_families_distinct()` must still (a) PASS with the gen/mirror z-ai collision as the ONE allowed same-family pair, AND (b) FAIL-CLOSED if the D8 JUDGE ever collapses to the generator family. Preflight 0.4 asserts BOTH legs.
- **`<base>` for the frozen-engine diff = `73f3bb13`** (the pre-Wave-B gated HEAD). WS-1 already edited `judge_adapter.py` (verdict-cache reset) + `openrouter_role_transport.py` (kimi default) in Wave A — those are BEFORE this base and were themselves Codex-gated, so the frozen-engine name-only check over the 11 engine files is EMPTY vs `73f3bb13` and remains the airtight gate. Preflight 0.1 pins base = 73f3bb13.

## B. The 4 novel P0 — fixed
- **P0-1 (vacuous query):** Stage B MUST render the **exact drb_72 AI-labor query** (the case that produced D1-D6), NOT a generic clinical query — else the residual checks pass vacuously. The preflight ABORTS unless the render's inputs contain the Eloundou-class figure, the journal-only AI-labor source class, a DOI-only entity, and >=1 contradiction record (the defect preconditions must be PRESENT to be tested).
- **P0-2 (GO skips Phase 4):** GO requires ALL of Phase 4.1-4.6 to EXECUTE and pass, not just 4.1. WS-14 scorers (DeepTRACE re-impl estimate + DRB-II `run_evaluation.py`) are REQUIRED post-render, not optional.
- **P0-3 (release_allowed):** 4.6 requires `manifest.four_role_evaluation ... release_allowed == True`. A disclosed-gap / `release_allowed=false` is **NO-GO**, never accepted as success.
- **P0-4 (degraded tiering):** 1.5 requires `retrieval_wall_hit == false` AND `tiering_mode != rules_floor_degraded` (the LLM tiering genuinely ran; a rules-floor fallback is a FAIL).

## C. Per-element additions (P1) — each now a fail-loud check
- **D6 weight-basis:** assert the report/manifest disclose a SINGLE `weight_basis` (the post-P3 authority-adjusted credibility_weight) as the source of truth, and `tiering_mode != rules_floor_degraded`, so the same URL never shows two different "credibility weight" numbers via a degraded-tiering path. (WS-9b proved the two labels read the SAME field; this guards the degraded path that could still diverge them.)
- **D2 citation-chrome root cause:** a >0 corroboration count must be backed by NON-chrome claim spans — assert each counted verified origin is a real content span (passes the chrome screen), not citation boilerplate / member-length artifact.
- **WS-2 / M6 output-fired:** require RENDERED, D8-VERIFIED cross-source sentences carrying >=2 DISTINCT evidence tokens + cited multi-source baskets in report.md — not just the telemetry counter.
- **WS-3 no_provenance_token (de-tautologize):** assert a specific fixtured no-token sentence that IS basket-supported was REPAIRED + rendered + strict_verify-VERIFIED; and a genuinely unsupported one was LOUDLY withheld (dropped). Remove the ">0 OR 0" tautology.
- **WS-1 judge stability firing-check:** in the render, assert 0 `JudgeEnumError` / `RoleTransportError`, enum `response_format` enforced, retry-before-degrade exercised on any transient blank/429 (never a conviction), span-identity verdict idempotency (no byte-twin split).
- **WS-12 quantified no-op:** assert the quantified-analysis path did NOT silently no-op (`spec_validation_rejected` / `quantified_silent_no_op` absent); a quantified section either renders verified quantified prose or LOUDLY discloses why not.
- **D4 specific breaching classes:** explicitly assert the audit's classes do NOT headline — 1986 pre-AI robotics (J. Operations Mgmt), T4 Frontiers forecast, OECD/IZA working-paper/non-journal — while each STAYS in the basket at low weight (demote-not-drop, §-1.3).
- **D5 non-vacuous:** the Stage B render must contain a DOI-only VERIFIED entity AND a basket-member-credit case; grep the coverage output proving no body-VERIFIED entity is listed as a gap.

## D. Threshold / wording fixes
- **DeepTRACE = ESTIMATE** (no public scorer/leaderboard): label it "estimated via our re-implemented scorer, judge substitution + calibration-vs-published-GPT-5-DR disclosed." Not a proven #1.
- **DRB-II:** `TotalScore >= 66` with InfoRecall / Analysis / Presentation SUB-targets separated (not a single blob).
- **Token-budget check** inspects OBSERVED request bodies per role/provider (real max_tokens sent), not only `GET /models`.
- Replace vague "well above 12" / "most claims": breadth = the SURFACED keep-all count (NO forced target — §-1.3); corroboration reported as a distribution (median independent origins per claim), not a hard floor.
- **§-1.1 audit** aborts on fabrication AND over-claim / unsupported-PARTIAL, not fabrication only.

## E. HONEST SCOPE of THIS run (no over-claim)
This run validates **Wave A+B+C**: the 6 residuals fixed + the WEIGHT-and-CONSOLIDATE winners firing + strong span-grounded faithfulness. Expected: **very strong / likely #1-competitive on DeepTRACE faithfulness**, **contention band (~low-60s) on DeepResearch-Bench-II coverage**. A **clear #1 on coverage requires WS-15 (TTD-DR draft→gap→revise)**; the **DeepTRACE top slot / Source-Necessity + debate** require **WS-10 / WS-11** — none built yet (Wave D/E). The preflight GATES the residuals + winners + faithfulness for THIS run; it does NOT assert a clear #1-on-both until Wave D/E ship.

## F. Executable driver
New `scripts/dr_benchmark/beatboth_preflight.py` (distinct from the existing offline `scripts/deepfix_preflight.py` canary): Stage A (static + pytest) local; Stage B (the drb_72 render) SSH-driven on the VM; pull artifacts; Phases 1-4 assertions + §-1.1 audit + WS-14 scorers; emit `{go: bool, failed_checks: [...]}`. GO launches the paid run; NO-GO lists every failed element.
