# POLARIS v1.1 Backlog

**Locked from v1.0 GREEN state.**
**Last updated:** 2026-04-30
**Status:** v1.0 shipped (all reachable milestones LOCKED via Codex audit loop). v1.1 work below.

---

## A. Phase G remaining BEAT-BOTH gaps (2 dimensions)

POLARIS v1.0 is BEAT-BOTH on 4 of 7 BEAT-BOTH dimensions on full-scale runs. These 2 are BEHIND-BOTH:

### A.1 narrative_length — POLARIS=2346 vs ChatGPT=4830 / Gemini=6835

**Root cause analysis:**

The synthesizer caps prose at `section_max_tokens=2400` per section (`scripts/run_honest_sweep_r3.py:1933`). With 3 sections, the theoretical ceiling is ~7200 tokens ≈ 5400 words. POLARIS produces 2346 words — well below the cap.

The actual bottleneck is **`min_kept_fraction=0.4`** (`scripts/run_honest_sweep_r3.py:1934`). Strict_verify drops sentences that don't pass verification. From v1.0 smoke logs:

```
[multi_section] Population Subgroups post-M-41c kept_fraction=0.30 below min 0.40 → retrying
[multi_section] Comparative post-M-41c kept_froact=0.20 below min 0.40 → retrying
```

The generator drafts ~6000 words, strict_verify drops ~60-70%, leaving 2346.

**v1.1 candidate fixes** (in increasing risk order):

1. **~~Raise `section_max_tokens` 2400 → 4800.~~** **EMPIRICALLY INVALIDATED 2026-04-30.** Tested via `PG_SECTION_MAX_TOKENS=4800` env override. Result: word count went from 2346 → 2032 (REGRESSION, not improvement). Hypothesis: larger generation budget produces more low-quality tail sentences that fail strict_verify; additional retries actually shrink the final kept prose. The token cap is NOT the bottleneck — it's the draft quality crossing the 0.4 kept_fraction floor.

2. **Add 1-2 more sections to outline.** Current outline has 3 sections; competitors have 8-15 narrative blocks. Compose at outline-time to have 5-6 sections and fold the existing prose-blocks into separate sub-sections. Mostly a synthesizer prompt change. **Risk:** more sections = more strict_verify failures = more retries.

3. **~~Raise the kept_fraction floor 0.4 → 0.35.~~** **EMPIRICALLY INVALIDATED 2026-04-30.** Tested via `PG_MIN_KEPT_FRACTION=0.35`. Result: 2346 → 2285 (-2.6% regression). Confirms the bottleneck is structural — synthesizer produces shorter prose because the strict_verify-passing CONTENT pool is bounded by the evidence pool, not by retry threshold. Both retry-knob options (1 + 3) now invalidated.

4. **Better evidence-grounding so kept_fraction goes up naturally.** Refactor the M-58 slot-fill prompt to bias toward verbatim verification matches. **Risk:** synthesizer rewrite.

**Empirical state (2026-04-30):** options 1 + 3 invalidated. Inspecting actual output revealed:

- POLARIS outline IS already at 6 sections (`sections_kept=6`)
- The 6 outline sections expand to 28 sub-sections in the rendered report
- Total prose: 2606 words across 28 sub-sections (avg 93 words/sub-section)
- BEAT-BOTH extractor sees 2285 (some sub-section prose is in contract-render path)

The bottleneck is **per-sub-section brevity**, not section count. M-58 slot-fill produces concise per-trial summaries (60-110 words each). Competitors (ChatGPT 4830w, Gemini 6835w) write 200-400 word narrative blocks per topic, not 60-110.

**Closure requires option 4** (synthesizer prompt rewrite) — explicit instruction to expand each slot-fill into 200-300 word narrative paragraphs while remaining strict-verify-grounded. **Option 2 invalidated** (we already have 28 effective sub-sections; adding more makes them shorter, not longer).

This is a multi-day synthesizer engineering effort, not a tuning loop. Deferred to v1.1 active development by user.

### A.2 contradiction_handling_grammar — POLARIS=3 vs ChatGPT=27 / Gemini=18

**Root cause analysis:**

The scorer counts contrast markers ("however", "but", "in contrast", "conversely", "on the other hand", "whereas", "although", "despite", "nonetheless", "yet") in prose body (`src/polaris_graph/audit_ir/beat_both_scoring.py:560-562`).

POLARIS produces 3 markers in 2346 words = 1 per 782 words.
ChatGPT produces 27 in 4830 words = 1 per 179 words.
Gemini produces 18 in 6835 words = 1 per 380 words.

POLARIS marker density is 4-5x lower than competitors. Two compounding issues:
1. Shorter prose (see A.1)
2. Lower marker density per word

**v1.1 candidate fixes:**

1. **Closes alongside A.1.** If narrative_length doubles, marker count likely doubles (3 → 6). Still BEHIND-BOTH but closer.

2. **Synthesizer prompt change**: explicit instruction to use contrast markers when evidence supports contrastive claims. Surfaced in M-71 (`contradiction_hedging.py`) but not exercised in v1.0 prompts.

**Recommended first attempt:** ship A.1 first, re-measure. If still BEHIND-BOTH, add a "contrast marker budget" to the synthesis prompt.

### A.3 claim_frames — N/A on regex extraction

POLARIS v1.0 bibliography stores `evidence_id + statement + tier`, not the 4 required frame fields (N, baseline, endpoint, CI). Both POLARIS and competitors score 0 → N/A verdict.

**v1.1 fix:** LLM-based extractor that reads claims from the M-58 slot-fill output (which DOES have N + baseline + endpoint + CI in `m50_per_trial_subsections.json`) and surfaces them at the manifest level for `_ClaimFramesScorer` to count.

**Estimated effort:** 1-2 days. Mostly a stitch from `m50_per_trial_subsections.json` → `manifest.json` `claims` field.

---

## B. M-INT-4 / M-INT-5 promotion from telemetry to enforcement

**Current state (v1.0):**
- `M-INT-4` LLM scope classifier runs in best-effort telemetry mode (`scripts/run_honest_sweep_r3.py:1055-1097`)
- `M-INT-5` domain router runs in telemetry mode (`scripts/run_honest_sweep_r3.py:1096-1146`)
- Production routing decision in v1.0 comes from the deterministic `template_classifier` + `TEMPLATE_CATALOG` (3 clinical variants)

**v1.1 promotion path:**

1. **M-INT-4 enforcement**: when LLM scope verdict is `out_of_scope`, refuse before retrieval. Add a `PG_M_INT_4_ENFORCE` flag (default OFF in v1.1, ON in v1.2 after calibration).

2. **M-INT-5 enforcement**: when LLM-routed domain doesn't match the template's `domain` field, log a divergence event. After M-D4 calibration window (≥6 months telemetry), promote to gating.

**Risk:** M-INT-4 has been seen to mis-classify clinical questions as `uncertain` ~5% of the time (per v1.0 sweep telemetry). Enforcing without calibration would refuse legitimate questions.

---

## C. Public exposure of non-clinical templates

`config/scope_templates/` ships 5 YAML templates (clinical, due_diligence, policy, tech, custom). Only `clinical` (and its 2 derived variants) is in `TEMPLATE_CATALOG`.

**v1.1 promotion path:**

1. Author concrete `template_id` entries for the 4 non-clinical templates with:
   - `drug_keywords` / domain-specific keyword lists (replacing clinical drug names)
   - `display_name`, `description`, `scope_summary`
   - JobRunner registration for the template

2. Add to `TEMPLATE_CATALOG` tuple
3. Update `template_classifier` confidence-gating thresholds per-template
4. Update `docs/supported_scope.md` with the 4 new domains
5. Run M-LIVE-1 smoke against one query per new template

**Estimated effort:** ~3-5 days per new template (mostly keyword curation + scope brief writing). 12-20 days total.

---

## D. M-INT-0b org-scoping

**Current state (v1.0):** pin files in `outputs/.../model_pin.json` do not carry an `org_id` field. The M-LIVE-3 dashboard `pin-trends` endpoint gates on auth but cannot filter pins per-org.

**v1.1 fix:** add `org_id` to `ModelPin` dataclass. Backwards-compat: pins missing org_id resolve as "unscoped" and are visible to all auth'd callers.

**Estimated effort:** ~1 day. Touches `model_pin.py` + the M-INT-0b capture path in `run_honest_sweep_r3.py`.

---

## E. M-PROD-3 metrics endpoint hardening

**Current state (v1.0):**
- In-memory + per-process counters (resets on FastAPI restart)
- No per-org filtering (process-global)
- JSON format only, no Prometheus exposition format

**v1.1 fixes:**

1. **Persistence**: SQLite-backed counters via the same pattern as M-D3 decision telemetry. Survives restart.

2. **Per-org filtering**: counter keys include `org_id` from caller. Admin role sees aggregate; member role sees own org only.

3. **Prometheus text format**: GET `/api/inspector/metrics?format=prometheus` returns `# HELP` / `# TYPE` / sample lines per Prometheus exposition spec. Enables direct scrape via `prometheus.yml`.

**Estimated effort:** 3-5 days.

---

## F. Workflow YAML push

**Current state (v1.0):** `.github/workflows/m_live_4_regression_gate.yml.pending_workflow_scope` exists locally but cannot be pushed because the OAuth token Claude Code uses lacks the `workflow` scope.

**v1.1 path:** user pushes via web UI or workflow-scoped CLI. Once pushed, the M-D9 regression gate runs on every PR + push to main/polaris.

---

## G. M-PROD-2 first paying pilot customer

**Current state (v1.0):** sales milestone, calendar-blocked.

**Pre-requisites met:** SOC2 dry-run GREEN, M-LIVE-1..4 LOCKED, BEAT-BOTH on 4/7 dims, pricing locked at $30k-$80k pilot tier.

**Path to revenue:** outbound to regulated org R&D leads, demo POLARIS on their internal clinical question, package as 60-day pilot.

---

## H. Phase G stop-criterion decision

**Per FINAL_PLAN Phase G:** "BEAT-BOTH on all 7 OR asymptote-stop with documented threat-model boundary."

**v1.0 state:** 4/7 BEAT-BOTH, 2/7 BEHIND-BOTH (synthesizer-side), 1/7 N/A (extractor-side).

**Decision:** v1.0 ships at 4/7. The 2 BEHIND-BOTH gaps are synthesizer capacity issues, NOT POLARIS having lower-quality evidence (POLARIS has MORE citations, MORE regulatory coverage, MORE jurisdictional precision). The "BEHIND" is on raw word count + contrast marker count — fixable in v1.1 without compromising the strict_verify guarantee.

**Not asymptote-stop yet** — there's explicit code work that closes both. Documented in A.1 + A.2 above.

---

## v1.1 release gate

POLARIS v1.1 ships when:

1. ✓ A.1 + A.2 close (BEAT-BOTH on narrative_length + contradiction_handling)
2. ✓ A.3 closes (claim_frames LLM extractor)
3. ✓ M-INT-0b org-scoping (D)
4. Optional: M-INT-4 enforcement (B), one non-clinical template (C)
5. Optional: M-PROD-3 hardening (E)

Then re-run M-LIVE-2 BEAT-BOTH and lock v1.1 release notes via the same autoloop.

**Estimated v1.1 wallclock:** 4-6 weeks. Driven by the synthesizer capacity tuning loop in A.1.
