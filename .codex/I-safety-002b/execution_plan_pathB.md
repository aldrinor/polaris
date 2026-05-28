# I-safety-002b — Path B execution plan (v5): POLARIS vs ChatGPT/Gemini/Perplexity DR, 5 clinical Qs, full-power + per-run §-1.1 line-by-line

**Status**: v5 (addresses Codex iter-1 5P1/7P2, iter-2 4P1/3P2, iter-3 2P1/3P2, iter-4 3P1/1P2). On Codex APPROVE → open GitHub issue → execute as military order.
**Parent**: `proper_dr_headtohead_design.md`. **Constraint**: §-1.1 line-by-line, human-free judges, top-tier only, API-fee budget.

## §0. Operator directive (binding)
Path B. Each question run FULL/MAX POWER (full model, full structure, no shortcuts). After EACH run, BOTH Codex AND Claude immediately read+reason EVERY line — data flow / reasoning flow / output content / citation — §-1.1, NOT metadata. Plan → Codex APPROVE → GitHub issue → execute as military order.

## §1. Scope (pre-registered, frozen)
5 in-scope clinical Qs from `config/benchmark/clinical_n10.json` (no refusal bait): **Q02** metformin safety / **Q03** statins→CV mortality / **Q06** FOLFIRINOX prognosis / **Q07** warfarin INR / **Q08** PD-1 NSCLC. 4 systems: POLARIS + ChatGPT DR + Gemini DR + Perplexity DR. **PILOT (n=5), NOT a superiority claim.**

## §2. POLARIS full-power run (REAL control surface — Codex P1-1)
**Runner**: `scripts/run_honest_sweep_r3.py` (the full-scale pipeline-A runner), with the 5 Qs added as full-power clinical sweep vectors (slug + question + clinical template). NOT `live_run_smoke.py` (that's a conformance smoke, needs `--template`, not full-scale).
**Full-power env manifest (override the low defaults; pinned per run)**:
```
PG_SWEEP_MAX_SERPER=50        # (default 8)
PG_SWEEP_MAX_S2=50            # (default 8)
PG_SWEEP_FETCH_CAP=500        # (default 20)
PG_LIVE_MAX_EV_TO_GEN=300     # (default 20)
PG_V30_ENABLED=1
PG_V30_PHASE2_ENABLED=1
PG_MAX_COST_PER_RUN=40.00              # not budget-throttled below full depth
OPENROUTER_ALLOW_FALLBACKS=false       # (default is TRUE) — close the V4-Pro-fallback ambiguity (Codex P1)
# generator DeepSeek V4 Pro; evaluator Gemma 4 31B (two-family); all retrieval tiers + fetch/access flags on
```
Each run writes its `run_dir` (manifest.json, model_pin.json, live_corpus_dump.json, protocol.json, report.md, bibliography.json, evaluator_rule_checks.json, qwen_judge_output.json, …) + the signed bundle.

### §2.1 Pin ENFORCEMENT — whole-surface `effective_config.json`, per-role, fatal (Codex iter-3 P1)
A handpicked env list is insufficient — the runner/client have MANY output-affecting controls (`OPENROUTER_PROVIDER_ORDER`, `OPENROUTER_REQUIRE_PARAMETERS`, `PG_GENERATOR_MODEL`, `PG_EVALUATOR_MODEL`, `PG_REASONING_FIRST_MIN_MAX_TOKENS`, `PG_R6_ENABLE_EXPANSION`, `PG_R6_EXPAND_QUERY_CAP`, `PG_SECTION_MAX_TOKENS`, `PG_MIN_KEPT_FRACTION`, `PG_DISABLE_ACCESS_BYPASS`, `PG_SWEEP_MAX_PRIMARY_TRIAL_ANCHORS`, `PG_SWEEP_MAX_REGULATORY_ANCHORS`, + the §2 knobs). A hidden override could change behavior while a handpicked gate passes. Existing `model_pin.json` is non-gating, generator-only, empty prompt hashes (`run_honest_sweep_r3.py:1077-1099`); `OPENROUTER_ALLOW_FALLBACKS` defaults TRUE (`openrouter_client.py:1365`).

**Build deliverable: `scripts/dr_benchmark/pathB_run_gate.py`** (thin wrapper; built+tested in §7 step 1):
- **Preflight — config snapshot, SECRET-REDACTED (fatal; Codex iter-4 P1)**: enumerate EVERY `PG_*` / `OPENROUTER_*` / retrieval env var the runner+client read (grep the codebase to build the complete control set, not a handpicked list) → `effective_config.json`. For **secret-named** vars (API keys, e.g. `OPENROUTER_API_KEY`) store ONLY `{present: bool, length, salted_hmac}` (artifact-local salted/HMAC digest, not a bare sha256, since bundles may be shared externally — Codex iter-5 P2) — NEVER the value (no credential leak into artifacts). Non-secret vars: `name → value → default → source file:line`. Assert `OPENROUTER_ALLOW_FALLBACKS=false` + a **singleton** `OPENROUTER_PROVIDER_ORDER`. Hash-pin `effective_config.json` + prompt/template hashes BEFORE the run.
- **Full-power RETRIEVAL preflight + post-run attempt assertion (fatal; Codex iter-4 P1 + iter-5 P2)**: "full power" silently degrades if a retrieval key is absent (`SERPER_API_KEY` missing → `live_retriever` SKIPS Serper rather than failing — `live_retriever.py:86`). Preflight FATAL-asserts required retrieval capability: `SERPER_API_KEY` + `SEMANTIC_SCHOLAR_API_KEY` present + reachable (+ fetch/cache identity knobs captured, redacted). **Post-run FATAL assertion**: each required backend (Serper, S2) was actually ATTEMPTED + logged this run — so a transient backend failure cannot masquerade as a valid low-yield retrieval. Missing/never-attempted required backend = abort, never a degraded "full power."
- **Per-role pins (fatal) — SERVED-IDENTITY SURROGATE, not a non-existent `model_version` (Codex iter-4 P1)**: OpenRouter does NOT expose a stable `model_version` (chat returns `model` + optional `system_fingerprint`; generation metadata returns `model` + `provider_name`; router metadata is experimental). So pin per role `{role → model_slug, provider_name, served_identity}` where `served_identity` = the pre-registered surrogate `sha256(provider_name + model + system_fingerprint-if-present + generation-metadata)`, **explicitly EXCLUDING volatile fields** (request id, timestamps, token counts, latency, cost) so the surrogate is stable across calls (Codex iter-5 P2). Preflight PROVES which of these fields each pinned provider actually returns and pins exactly those. Two-family segregation stays.
- **Post-run (fatal)**: for each LLM call, recompute the `served_identity` surrogate from response metadata; if it differs from the per-role pin, OR a pre-registered surrogate FIELD is absent (missing the agreed surrogate ≠ tolerated), OR the post-run `effective_config.json` re-snapshot drifts → run is **INVALID, discarded + re-run**, never scored.
- The gate (not prose) makes the run full-power (incl. retrieval) + correctly-modeled + drift-free + secret-safe.

## §3. Competitor capture + citation manifest (Codex P1-3, P2)
Per Q × tool, Deep Research mode, same window, "You decide" on clarification, final report + citations. Pre-register competitor product settings: account tier, DR mode/depth/model toggle, browser/export method, start/end timestamps, clarification text, retry/failed-run policy. Export:
```
external_outputs/<tool>/Q##/report.html        # citation anchors preserved
external_outputs/<tool>/Q##/report.txt
external_outputs/<tool>/Q##/sources/<citation_id>.html   # run-time snapshot of EVERY cited page
external_outputs/<tool>/Q##/citation_manifest.json
```
**`citation_manifest.json` schema (binding)**: per citation `{citation_id, anchor_text, target_url, snapshot_path, sha256, fetch_status, fetched_utc, extracted_text}`. Every in-report citation anchor/footnote/hover resolves to exactly one row. **Auditors score ONLY against the frozen snapshot's extracted_text — live refetch is a diagnostic fallback that may NOT change a verdict (Codex P2).**

## §4. Per-run IMMEDIATE §-1.1 dual line-by-line (Claude AND Codex, independent) + full data-flow artifacts (Codex P1-5)
After EACH run, both auditors read+reason EVERY line over a **canonical normalized report text with stable line + claim IDs** (one per system, so both ledgers reconcile against the same IDs — P2).
Required POLARIS data-flow artifacts (NOT just verified_report.json + evidence_pool.json):
- retrieved/selected evidence rows (`live_corpus_dump.json`), per-section evidence assignments, raw pre-verify drafts, **dropped-sentence ledger**, strict_verify/entailment settings, final emitted report, `model_pin.json` + `pathB_run_pin.json`.
- **Exact-prompt capture + fatal completeness check, ALL LLM paths (Codex P1/P2; iter-4 P2)**: the Path-B gate wraps the LLM call boundary to log per call `{call_id, role, prompt_messages(system+user), request_hash, response_model, response_provider, served_identity}` → `prompt_capture.jsonl`. **This MUST cover every LLM path** — not only `OpenRouterClient`, but also raw/non-OpenRouterClient HTTP calls (esp. the entailment/NLI judge and any direct provider calls): they are forced through the same wrapper or independently logged to the same schema. **Fatal completeness check**: every LLM call has a matching `call_id` with prompt capture + request hash + served model/provider/served_identity; any call missing any field ⇒ run INVALID. Built in §7 step 1.
- **POLARIS citation-manifest equivalent (Codex P2 — §3's `citation_manifest.json` is competitor-only)**: parallel `polaris_citation_manifest.json` mapping each claim's provenance token → `evidence_pool` source row → fetched source snapshot + sha256 + the cited char-span text. So POLARIS claims are audited against the same `citation_id → snapshot span` structure as competitors, judged from scratch (NOT `verifier_pass`).
Audit per claim: **data flow** (what entered generation) → **reasoning flow** (does each step follow from cited evidence) → **output content** (every atomic claim, NO sampling) → **citation** (claim → citation_manifest row → frozen snapshot span) → verdict **VERIFIED / PARTIAL / UNSUPPORTED / FABRICATED / UNREACHABLE** + exact span quote.
Claude ledger + Codex ledger produced **independently** (normalized/blinded **where possible** — POLARIS bundles reveal identity, so record where identity was visible — P2), then **reconciled** claim-by-claim. Artifact: `outputs/dr_benchmark/pathB/<Q>/<system>/{claude_ledger.json, codex_ledger.json, reconciled_ledger.json}`.

## §5. Pre-registered scoring rules (Codex P1-4 — close the degrees-of-freedom leak; frozen BEFORE any output viewed)
- **Severity taxonomy** (per claim): S0 critical / S1 high / S2 medium / S3 low — operationalized per 0a.-1.B's decision tree (the locked clinical rubric).
- **Materiality rule**: a claim is "material" iff it is a decision-relevant clinical assertion (S2 or worse); S3 stylistic/non-decision claims are observed, not scored.
- **Lane-1 faithfulness verdicts**: VERIFIED (span supports) / PARTIAL (partial support) / UNSUPPORTED (no support) / FABRICATED (span refutes) / UNREACHABLE (cannot verify). **UNREACHABLE subtypes** (paywall / robots / fetch-failure / source-missing), kept DISTINCT from FABRICATED, counted only under the materiality rule.
- **Headline**: **S0-S2 material** unsupported-or-worse rate = (PARTIAL+UNSUPPORTED+FABRICATED+material-UNREACHABLE)/all material atoms. (S3 is observed-only, NOT scored — Codex P2.)
- **Partial-credit rule**: PARTIAL = 0.5 weight in the rate (pre-registered), reported separately too.
- **Conflict rule (weak cited source vs higher-tier gold)**: faithfulness (Lane 1) scores ONLY whether the cited source supports the claim. If a claim is faithfully cited to a weak/outdated source that conflicts with higher-tier gold evidence, it is VERIFIED for faithfulness BUT flagged in **Lane 2** as an evidence-hierarchy/quality failure. The two lanes are reported separately; neither is collapsed.
- **Lane-2 coverage threshold**: a system "passes" a Q iff zero S0-S2 FABRICATED/UNSUPPORTED material claims AND **≥ 0.70** of gold-rubric required elements covered (each itself citation-supported). Threshold = literal **0.70**, frozen pre-run (Codex P2 — no "e.g.").

## §6. Gold rubrics (5, pre-registered, hash-pinned BEFORE any output viewed — Codex P2)
Per Q: required answer elements from INDEPENDENT primary/regulatory sources (Cochrane / FDA label / specialty guideline / landmark RCT) + clinical evidence hierarchy. Hash-pin the rubric text **AND** source URLs + source snapshots + extracted gold spans, before any system output is viewed. Authored by Claude+Codex from sources (human-free), Codex-reviewed.

## §7. Execution order (military — gates BEFORE any output viewed; Codex P2)
1. Build (before any run): (a) `src/polaris_graph/benchmark/claim_audit_scorer.py` (audit ledger; replaces beat_both_scorer) + scorer fixtures → green (no model); (b) **`scripts/dr_benchmark/pathB_run_gate.py`** (§2.1 fatal preflight+post-run pin gate + `OPENROUTER_ALLOW_FALLBACKS=false` enforcement + `pathB_run_pin.json`) + its fixtures; (c) **the prompt-capture wrapper** (§4 `prompt_capture.jsonl`) + **`polaris_citation_manifest.json`** builder.
2. Pre-register + hash-pin: §5 scoring rules (literal thresholds), §6 gold rubrics (text+sources+snapshots+spans), §2 `effective_config.json` + per-role model pins, §3 competitor settings, AND **the scorer/auditor (judge) model versions + judge prompts + judge decoding settings + scorer commit/hash** (Codex P2 — the JUDGE must be pinned before any output is viewed, same as the systems under test). **Quarantine any pre-existing exports until after hash-pin.**
3. **Codex reviews scorer + gate + rubrics + pins (gate, §-1.1).** No POLARIS or competitor output is VIEWED before steps 1-3 complete.
4. Run POLARIS Q02 full-power (§2) + pin-enforce (§2.1) → Claude + Codex independent line-by-line ledgers (§4) → reconcile.
5. Repeat Q03, Q06, Q07, Q08.
6. As operator supplies competitor exports (§3) → same dual line-by-line per (Q × tool).
7. Aggregate → honest pilot report: per-system Lane-1 + Lane-2, every claim traceable to its frozen span. No "wins" headline.

## §8. Honest framing (anti-bullshit)
n=5 = pilot. No metadata, no counts, no auto-wins, no sampling. Frozen snapshots are primary truth. POLARIS judged from scratch (never its own verifier_pass). Every reported number links to claim/span evidence.

## §9. Cost/resource (§8.4)
POLARIS full runs = V4 Pro + retrieval API (PG_MAX_COST_PER_RUN raised for full depth); dual line-by-line judging = cross-family LLM API. One heavy process at a time; kill orphans between steps; operator-instructed → authorized, released after.

## §10. Definition of done
5 Qs × 4 systems run full-power (pin-enforced) + dual §-1.1 line-by-line audited + reconciled ledgers + two-lane scored against pre-registered rules + honest pilot report. Codex APPROVE on plan → GitHub issue → execute.
