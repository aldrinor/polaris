# I-deepfix-001 (#1344) Wave-3 brief — ACTIVATE the core path + ARCHIVE (surgical, proven-dead only)

Branch `bot/I-wire-001-integration`. This is the END-STATE wave after Waves 1+2 (10 units committed+dual-gated). Two read-only scouts mapped the exact activation surface and the archive import-closure; this brief is authored against their maps. **You (Codex / Fable) are reviewing the PLAN.** After you APPROVE the plan, each build sub-unit's DIFF is separately dual-gated.

---

## GOVERNING FACT (drives the whole sequencing — verify it)
The new-core capability flags are **default-OFF and NOT in the gate-B slate today**: `PG_SYNTH_PRIMARY` (verified_compose.py:1328 default ""), `PG_CROSS_SOURCE_BODY` (cross_source_synthesis.py:508 default "0"), `PG_TWO_SIDED_DEBATE` (multi_section_generator.py:4883 default "0"), `PG_MIN_CITE_SET` (citation_set_minimizer.py:79 default "0"), plus `PG_FINDING_DEDUP_NLI`, `PG_PROVENANCE_REANCHOR`, `PG_NUMERIC_COMPARATOR`. grep of `scripts/dr_benchmark/run_gate_b.py` returns ZERO hits for these (only `.codex/` artifacts reference them).

**Consequence:** the OLD composition path and the OLD cross-source tail are STILL the live production default. Archiving them NOW = deleting live code. Per the operator's 2026-07-05 lock (WIRE+ACTIVATE **then** ARCHIVE): activate the new core → validate a real run → THEN re-run import-closure and archive what is proven dead. So Wave-3 archive is deliberately SPLIT: a tiny proven-dead set now (3b), the big candidates DEFERRED to post-validation.

---

## PART 3a — ACTIVATE the core path (the substantive work)

### The activation mechanism (from the activate-surface scout, verify)
The sanctioned paid launcher is `scripts/dr_benchmark/run_gate_b.py`. It arms flags via a coordinated QUAD applied by `apply_full_capability_benchmark_slate()` (:3004-3068; FORCE_ON/FORCE_EXACT → hard `os.environ[name]=value`, else `setdefault`). `_PAID_PATH_WINNER_FLAGS` (run_honest_sweep_r3.py:20092) fires ONLY on the direct `main_async` launch, NOT on gate-B — so we wire the SLATE, not that tuple.

The QUAD constructs, each added flag must be COHERENT across all four (+ the purity allowlist):
1. `_FULL_CAPABILITY_BENCHMARK_SLATE` (dict name→"1", :529-1612) — the master slate.
2. `_BENCHMARK_FORCE_ON_FLAGS` (frozenset) — operator `.env=0` cannot win (winner-slate semantics).
3. `_BENCHMARK_PREFLIGHT_REQUIRED_FLAGS` (fail-CLOSED before spend if not truthy).
4. `_BENCHMARK_FORCE_EXACT_FLAGS` (string/numeric pins) — N/A for these boolean flags.
5. `_WINNER_FLAG_ALLOWLIST` (SLATE-PURITY) — every slated winner must be listed or purity fails.

### The 12 core flags — activation plan
Already FORCE-ON (leave as-is, confirm still coherent): **PG_EXPERT_FACET_PLANNER**, **PG_SPAN_RESOLVER**.
Promote setdefault → FORCE-ON (operator-proof, winner semantics): **PG_BASKET_CONSUME_FINDING_DEDUP** (slate-dict 1317 → add to FORCE_ON + REQUIRED + allowlist), **PG_SUBENTITY_QUERY_EXPANSION** (hardcoded setdefault 3092 → move into slate-dict + FORCE_ON + REQUIRED + allowlist; remove the ad-hoc setdefault).
Add (NOT-WIRED → slate-dict + FORCE_ON + REQUIRED + allowlist), 8:
- **PG_SYNTH_PRIMARY** — compose-then-verify group writer as PRIMARY body.
- **PG_FINDING_DEDUP_NLI** — directional bidirectional-entailment qualitative same-claim grouping.
- **PG_PROVENANCE_REANCHOR** — re-anchor wrongly-cited claim to best ENTAILING span (faithfulness-positive).
- **PG_CROSS_SOURCE_BODY** — plan-driven cross-source pairing into the body.
- **PG_TWO_SIDED_DEBATE** — composer debate-disclosure + con-side retrieval guarantee.
- **PG_MIN_CITE_SET** — minimal independently-entailing inline cite set vs weight-channel demotion (render lever, faithfulness-neutral, keep-all).
- **PG_NUMERIC_COMPARATOR** — upgrade fully-comparable neutral cross-source pair to `comparison` connective (render lever, faithfulness-neutral).
- **PG_SHALLOW_REPORT_CANARY** — Wave-1d fail-loud detector (see nuance below).

**Per-flag nuances (call out any you disagree with):**
- `PG_SHALLOW_REPORT_CANARY` is a pure DETECTOR (report bytes unchanged when it does not fire). Adding it to the slate + REQUIRED means a paid run refuses to start unless the fail-loud guard is armed, and a genuinely-shallow released run exits rc=1. That is the intended activation of the guard. It goes in slate + FORCE_ON + REQUIRED + allowlist like the rest.
- `PG_MIN_CITE_SET`, `PG_NUMERIC_COMPARATOR` change rendered report bytes but are faithfulness-neutral (min-cite keeps ALL sources, just inline-vs-weight-channel placement; numeric only upgrades a connective on a fully-comparable pair). Their OFF path is byte-identical (already dual-gated in Waves 2b/2a). Activating them is a rendered-output change we WANT (that is the point of activation) and will be caught by validation.
- The other 9 change core pipeline behavior by design (retrieval breadth / consolidation grouping / synthesis / provenance anchoring / debate). Each retains its default-OFF kill switch, so non-slate contexts (unit tests) stay byte-identical.

### 3a build sub-units (each a separate dual-gated diff)
- **3a-slate** (`run_gate_b.py` only): wire the 10 flags (8 add + 2 promote) coherently across the QUAD + allowlist; remove the now-redundant PG_SUBENTITY_QUERY_EXPANSION ad-hoc setdefault (3092). NO logic change outside the slate constructs. Byte-identical when the slate is not applied (unit tests / non-benchmark).
- **3a-canary** (`run_gate_b.py` only): a fail-loud **activation canary** in the post-run canary block (~5288-5347, beside breadth/M6/shallow). On a RELEASED non-smoke paid run it asserts each newly-activated CORE module actually FIRED, via the stable-literal-marker → post-run-parse convention (reuse the `_CrossSourceMarkerCaptureHandler` pattern :2516). Markers for verified_compose (synth-primary), finding_dedup (NLI regroup), provenance_generator (re-anchor), cross_source_synthesis (body), expert_facet_planner (debate/facet). STRUCTURAL "activated-yet-did-not-fire" contradiction only — NEVER a count/quantity threshold (§-1.3). Default-OFF opt-in kill switch `PG_ACTIVATION_CANARY`; byte-identical OFF (mirror the Wave-1d shallow-canary OFF-purity contract EXACTLY — no null record key when OFF; missing/unreadable log → skip:no-run-log, not ok).
- **3a-harden** (module files — fold the Waves-2 residual hardening now that the modules go live):
  - 2a: legacy arm-default `'treatment'` → `'unknown'` (clinical-safety; blank/unknown arm must not license a comparison). Locate the exact `'treatment'` default in the numeric/cross-source legacy key.
  - 2d P3s: the two-sided-debate P3 items from the 2d gate.
  - 2b-wiring P2s: the citation-minimizer CWF-seam P2 items from the 2b-wiring gate.
  - Each is faithfulness-neutral or faithfulness-positive; each behind its existing flag; each OFF byte-identical.

---

## PART 3b — ARCHIVE (surgical; only proven-dead NOW; big candidates DEFERRED)

### 3b-now (safe today — import-closure proven zero live callers)
- **`is_self_contained_furniture_line`** (`src/polaris_graph/generator/chrome_furniture_screen.py:144`) — ZERO callers anywhere in src/scripts/tests. Dead. Archive (delete the function; confirm no import breaks).
- **`is_boilerplate_quality`** (`src/polaris_graph/generator/span_resolver.py:273`) — test-only, and not even a text-chrome detector (checks a provenance-quality label). Archive (delete + drop its test-only reference).
- **Dormant banned scope hard-DROP branch** (`topic_relevance_gate.py` `topic_gate_hard_drop_enabled` / `PG_SCOPE_TOPIC_GATE_HARD_DROP`, :72-84; and `evidence_selector.py` `_apply_scope_denylist` #1244 gate :2263-2269): §-1.3 bans number-forcing hard-DROP filters. These are default-OFF today (byte-identical dormant). The default topic gate (`PG_SCOPE_TOPIC_GATE` default-ON) is DEMOTE-not-DROP = a §-1.3-compatible WEIGHT and STAYS. **Proposal: delete the banned hard-DROP branch per §-1.3** (keep the DEMOTE weight path). This is the one operator-judgment item — it is currently a deliberate disclosed audit-reversal hatch. Recommend deletion per the §-1.3 lock; flag for operator visibility in the commit. If Codex/Fable judge it should stay as a disclosed reversal switch, hold it.
- **Candidate-4 bolt-ons**: already DELETED (`PG_SPAN_PER_SOURCE_CITE_CAP`, `PG_LEGACY_SECTION_BREADTH_TARGET`, `PG_SECTION_SOURCE_BREADTH_TARGET`, `PG_BREADTH_CANARY_MIN`) — preflight `operational_readiness_preflight.py:807-812` asserts absence. NOTHING to archive; just confirm they stay gone (no action).

### 3b-DEFERRED (NOT-SAFE today — after activation + a validating real run)
- **Candidate 1** old atom-glue compositor (`verified_compose.py` legacy `_compose_one_basket` body + K-span producers): the OLD path is the LIVE default until PG_SYNTH_PRIMARY is activated; the K-span producers are the faithfulness-FLOOR fallback the group writer degrades to — likely NEVER archivable. Re-run import-closure AFTER activation to see if any truly-dead sub-part emerges; otherwise leave (it is the safety net, not dead code).
- **Candidate 3** `synthesize_cross_source_findings` depth tail: slate-pinned LIVE (`PG_SWEEP_DEPTH_LAYER` force-on), strict_verify-gated + D8-threaded, just modified this campaign, NOT superseded by PG_CROSS_SOURCE_BODY. Do NOT archive.
- **Candidate 2** chrome-denylist collapse-to-ONE: every wrapper has live callers with seam-specific concerns; collapsing is a behavior-changing RE-WIRE, out of scope for an archive wave. Defer as a separate design task if desired.

### MUST-NOT-TOUCH (faithfulness engine — confirmed zero overlap)
strict_verify / verify_sentence_provenance (provenance_generator.py), consolidation_nli.py, four-role D8 (native_gate_b_inputs.py / sweep_integration.py), provenance tokens/span bounds, span grounding (verified_compose.py:2677 + span_resolver.py), NLI judges (entailment_judge.py / semantic_conflict_detector.py). NEVER archived.

---

## VALIDATION (after 3a + 3b-now commit)
1. Isolated replay on banked corpora (V1/V2/V3) to confirm the activated core FIRES and the activation canary passes; OFF-context unit suites still green.
2. ONE fresh front-half paid VM run (heavy → VM, never local).
3. Acceptance ladder: `deeptrace_self_score.py` (triage) → `rendered_report_acceptance_harness.py` (clean-room) → paid DeepTRACE + DRB-II → §-1.1 line-by-line.
4. Re-run the archive import-closure post-validation to prove candidate-1/3 old-path importers went to zero before any deferred archive.
5. Present the operator the built + activated + archived(-safe) + validation-ready state, honestly stating what was deferred and why.

---

## Follow-up GitHub issues (separate, do NOT fold into Wave 3)
- pre-existing `test_bibliography_basket_iarch002` 3 failures (broken at HEAD by doi/pmid projection).
- `verified_numeric_claim_extractor` node → then 2c-wiring (PG_PRESENTATION_TABLES stays deferred, NOT activated in 3a).
- M6 marker drift (`_CROSS_SOURCE_SILENT_NOOP_MARKER` absent from cross_source_synthesis.py).

---

## GUARDRAILS (binding on every 3a/3b diff)
Faithfulness engine byte-untouched. OFF/non-slate = byte-identical per unit (git diff -w must equal git diff; rstrip-align cleaner if the editor churns whitespace). WEIGHT-not-FILTER + CONSOLIDATE-keep-all. Word/citation/source COUNT thresholds BANNED (canaries STRUCTURAL only). Commit EXACT files only, never `-A`. Surgical, no reformat drift.

## Output schema (return exactly)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
sequencing_correct: true|false   # activate-then-archive; big candidates deferred correctly?
activation_surface_correct: true|false   # QUAD wiring is the right seam, coherent across all 4 + allowlist?
archive_safe_only: true|false    # only proven-dead archived now; faithfulness engine untouched?
faithfulness_untouched: true|false
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
notes: <short>
```
APPROVE iff zero novel P0 AND zero continuing P0 AND zero P1.
