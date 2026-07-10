# DESIGN 2 — Holistic whole-report review (wire the reviewer into the REAL pipeline)

Author: FABLE 5 (architect). Date: 2026-07-10. Branch: `bot/I-deepfix-relaunch` (HEAD `0bde6438`).
Anchor audit: `.codex/I-arch-audit/fable_orchestration_audit.md` stage 8 + ranked gap #1.
Mandates honored: CLAUDE.md §-1.3 (weight-not-filter, consolidate-keep-all, basket faithfulness), faithfulness engine UNTOUCHED, §9.1.8 model/token lock, max parallelism, crash-resilient resume, requirement-aware not hardcoded.

---

## 1. What exists today (real code, verified)

### 1.1 The reviewer module EXISTS and is real

`src/polaris_graph/synthesis/cross_section_reflector.py` — "MoST Phase R: Cross-Section Self-Reflection". One LLM call per section critiques that section against its top-4 related sections (evidence-Jaccard + adjacency, `:181-246`), returns structured JSON (`contradictions / redundancies / cross_references / revision_needed`, `:100-110`), then a second LLM call revises the section (`_revise_with_reflection`, `:293-382`) under a word-count guard (revised must be 80%–130% of original, `:133-147`).

### 1.2 It is wired ONLY to the unused UI pipeline

The one production-code caller is pipeline B: `src/polaris_graph/agents/synthesizer.py:3054-3060` (`reflect_across_sections(...)` inside the LangGraph UI synthesizer). Zero references in `scripts/run_honest_sweep_r3.py` (verified by repo-wide grep — only tests, the pipeline-B synthesizer, and a legacy preflight script import it). The REAL pipeline is the standalone sweep CLI (`run_honest_sweep_r3.py`, driven by `scripts/dr_benchmark/run_gate_b.py`). This is the classic winner-built-but-not-wired pattern (memory 2026-06-28).

### 1.3 What the REAL pipeline has instead of holistic review

All partial, none holistic:
- `generator/fact_dedup.py` — cross-section NUMERIC redundancy: signature-groups sentences, one batched LLM rewrite of redundant instances into cross-references, rewrites RE-VERIFIED through `strict_verify` before acceptance (`multi_section_generator.py:10098-10165` — this re-verify pattern is the proven seam this design reuses).
- `generator/cross_section_repetition_guard.py` — EXACT-verbatim recycle consolidation, render-only, in-place substring swap, citation-preserving (called at `multi_section_generator.py:10633`).
- 4-role D8 whole-report adjudication + redaction (`roles/release_policy.py`, `roles/report_redactor.py`; seam at `run_honest_sweep_r3.py:18137+`) — FAITHFULNESS only; no tone, no ordering, no depth.
- Mechanical assembly (`synthesis/report_assembler.py:1-6` — "Pure code — no LLM calls").

Nothing reviews the WHOLE report for tone consistency, prose-level cross-section contradiction, paraphrase redundancy, ordering, or depth. Sections are composed in parallel and concatenated. Audit gap #1.

### 1.4 Why not lift the reflector as-is

Four hard mismatches, so we build a production-native module and REUSE the reflector's proven ideas (structured critique JSON, the 80–130% word guard, `_parse_reflection_json`):
1. **Data shape**: reflector works on pipeline-B `SectionDraft` with `[CITE:ev_xxx]` markers (`cross_section_reflector.py:60`). The sweep's unit is `SectionResult` (`multi_section_generator.py:1116-1204`) with `verified_text` (resolved `[N]` markers) + `kept_sentences_pre_resolve` (SentenceVerification objects still carrying `[#ev:id:start-end]` tokens).
2. **No strict_verify re-ground**: the reflector's revision prompt asks the LLM to behave (`:349-357`) but never re-verifies output. In the sweep, unverified rewrite text entering verified prose is forbidden (LAW II; the fact_dedup Codex iter-1 P1 that forced re-verify at `:10103-10113` is the precedent).
3. **Per-section view, not whole-report**: it reflects each section against top-4 neighbors, N calls. The requirement is ONE pass over the WHOLE report.
4. **Hardcoded tone**: "Maintain the same academic tone" (`:356`) — violates the requirement-aware mandate.

---

## 2. The design

### 2.1 New module: `src/polaris_graph/generator/holistic_review.py`

Three stages. Faithfulness-neutral by construction (§2.4).

**Stage H1 — ONE whole-report critique call (global view).**
Input: the research question, the optional deliverable spec (§2.5), and every rendered section (`title` + `verified_text` with section-local `[N]`, gap stubs and `dropped_due_to_failure` sections EXCLUDED — the same predicate the repetition guard uses, `multi_section_generator.py:10630-10632`). One LLM call returns one bound JSON edit plan:

```json
{
  "tone_findings":        [{"section": "...", "issue": "...", "revise": true}],
  "contradiction_pairs":  [{"section_a": "...", "quote_a": "...", "section_b": "...", "quote_b": "...", "action": "hedge_flag"}],
  "redundancy_clusters":  [{"primary_section": "...", "quote_primary": "...", "duplicates": [{"section": "...", "quote": "..."}]}],
  "depth_flags":          [{"section": "...", "issue": "thin|buried_lead", "lead_quote": "..."}],
  "section_order":        ["title_1", "title_2", ...],
  "no_edit_needed":       false
}
```
Quotes must be verbatim substrings of the supplied prose; a quote that does not match any section verbatim is DISCARDED (deterministic anchor check — the LLM can only point at real sentences, never invent targets).

**Stage H2 — deterministic structural edits (pure code, no LLM).**
- **Re-order**: `section_order` is applied as a permutation of `section_results` AND the outline plan list (the manifest reads `[p.title for p in multi.outline]`). Constraint solver: an existing fact_dedup cross-reference ("as noted under <title>" rewrites, `fact_dedup.py` step 4) creates a topological edge — the referenced section must stay BEFORE the referencing section; a permutation that violates any edge is repaired by stable-sorting within the constraint, and the repair is logged. Contract-template runs (clinical fixed 8-title outline, `multi_section_generator.py:784-793`) accept re-order only when the deliverable spec asks for it; default clinical order is a domain convention and stays.
- **Exact/near-duplicate consolidation**: clusters whose member sentences have IDENTICAL numeric-token signatures and citation sets route to the existing repetition-guard mechanics (richest instance + citation-preserving back-reference). Anything looser is NOT auto-collapsed (the guard's docstring bans paraphrase-collapse as a silent-drop risk); it goes to Stage H3 as a revise instruction instead.

**Stage H3 — concurrent per-section revise + MANDATORY re-verify.**
Only sections the plan flags get a revise call (tone, paraphrase redundancy, buried lead, hedge-flag). Calls run concurrently under `asyncio.gather` + semaphore (`PG_HOLISTIC_REVISE_CONCURRENCY`, default 32 — max-parallelism mandate; each call is independent, deterministic apply order by section index). Each revise call operates on the section's `kept_sentences_pre_resolve` SV sentence strings (which still carry `[#ev:]` tokens), NOT on resolved prose — exactly the fact_dedup lane. Acceptance per changed sentence:
1. Changed sentences re-run the UNCHANGED `strict_verify` (`generator/provenance_generator.py:3598`) against the section's `evidence_pool`, offloaded via `asyncio.to_thread` (the W03 offload pattern, `multi_section_generator.py:10136-10142`).
2. A rewrite that FAILS re-verify → the ORIGINAL sentence is kept (fallback-to-original, never drop — the original already passed; this differs from dedup, where the original was being consolidated away).
3. Surviving SV lists re-resolve via `resolve_provenance_to_citations_with_count` with the same basket-render kwargs (the SITE-2 pattern, `multi_section_generator.py:10186-10202`), refreshing `verified_text` + `biblio_slice`.

### 2.2 The edit contract — the ONLY four moves allowed

1. **Permute** whole sections (H2).
2. **Replace** an existing sentence with a rewrite that re-passes `strict_verify` (H3).
3. **Consolidate** exact-signature duplicates keeping every citation (H2, guard mechanics; §-1.3 principle 2).
4. **Attach** a short qualitative hedge/pointer clause to an EXISTING verified sentence (H3) — e.g. "…, though this estimate is contested (see the Safety section)". The host sentence keeps its `[#ev:]` tokens and re-passes strict_verify (decimals unchanged, content-word overlap intact). The clause itself must carry NO numerals and NO new claims.

**Forbidden**: new standalone sentences (a token-less sentence would be dropped by strict_verify anyway — we do not create work for the engine); deleting either side of a contradiction; moving a citation between sections; touching evidence rows, baskets, verified/dropped counts of unchanged sentences, or any faithfulness component.

### 2.3 Wiring point (exact)

Inside `generate_multi_section_report`, at `src/polaris_graph/generator/multi_section_generator.py` immediately BEFORE `_apply_cross_section_repetition_guard(section_results)` at `:10633`:

```
fact_dedup (+ re-verify)  ->  M-44/M-47 regen passes  ->  [HOLISTIC REVIEW HERE]
->  cross_section_repetition_guard (:10633)  ->  _merge_bibliographies + _remap_section_markers_to_global (:10641-10650)  ->  return MultiSectionResult
```

Why exactly here:
- **Whole report exists** (post-gather, post-dedup) and sentences still live at SV level with `[#ev:]` tokens → strict_verify re-runs directly; no `[N]`-to-span adapter needed.
- **Everything downstream inherits the reviewed prose automatically**: the repetition guard builds its back-references against the FINAL section order; the global citation remap runs after; in the sweep, Key Findings (`run_honest_sweep_r3.py:16516+`), the depth layer/depth synthesis (`:16541-16620`), Abstract/Conclusion (`:16737+`), `assemble_report_md` (`:16884`), and the 4-role D8 seam (`:18137+`) all read `multi` AFTER this pass — so D8 adjudicates the post-review sentences, and the extractive Abstract/Key-Findings quote reviewed prose. Zero changes needed in those consumers.
- The frozen faithfulness ordering is preserved: verify-before-compose per sentence already happened; this pass re-verifies its own edits; D8 verify-after-compose still runs on the final whole report.

Additive signature change: `generate_multi_section_report(..., deliverable_spec: dict | None = None)` — default `None` = byte-identical; the sweep threads it (§2.5).

### 2.4 Faithfulness-neutral hard rules (deterministic gates, not prompt hopes)

- **R1 re-verify**: every changed sentence re-passes the UNCHANGED `strict_verify`; fail → original kept. Engine untouched.
- **R2 zero citation loss**: before/after the whole pass, compute the global multiset of evidence_ids across all sections' SVs + back-references. Any evidence_id whose count would drop to ZERO report-wide blocks the specific edit that caused it (original kept). Consolidation keeps all citations (§-1.3 principle 2: repetition is corroboration).
- **R3 contradictions are never adjudicated**: the pass NEVER deletes or "resolves" a side — that is evidence adjudication and belongs to the faithfulness engine + the existing contradiction surfaces (`retrieval/semantic_conflict_detector.py`, `generator/contradiction_hedging.py`, contradictions.json). Allowed actions: hedge-clause attachment (§2.2 move 4) + a row in the existing contradictions disclosure. Both sides always ship.
- **R4 size guards**: per-section 80%–130% word guard (the reflector's CASE_2 guard, env `PG_HOLISTIC_SECTION_WORD_GUARD_LOW/HIGH`) + whole-report kept-sentence floor (`PG_HOLISTIC_REPORT_KEEP_FLOOR`, default 0.90) — a plan that would shrink the report below the floor is rejected wholesale, originals restored, degrade marker emitted. These are SAFETY bounds on an LLM editor's blast radius, not quality targets (§-1.3 day-waster ban does not apply: nothing here forces a number UP).
- **R5 fail-conservative**: entry snapshot (deep copy of `section_results` + outline order); ANY exception → restore snapshot, emit `[activation] holistic_review: unavailable_failopen (<err>)`, run continues (additive-pass convention, same as the repetition guard `:8813-8834`).
- **R6 kill-switch**: `PG_HOLISTIC_REVIEW` default OFF → the function is a no-op, byte-identical output (LAW VI + the default-OFF revert convention). The Gate-B slate pins it ON (`run_gate_b.py` env block) — flag-gated is NOT done until the slate pin lands (memory 2026-07-05).

### 2.5 Requirement-aware, not hardcoded

The critique + revise prompts take a `deliverable_spec` (tone, audience, structure/ordering preference, length posture) when one exists, and judge tone consistency AGAINST THE SPEC — never against a hardcoded "academic tone". Source of the spec, in order: (1) the Design-5 deliverable-spec extension of `retrieval/intake_constraint_extractor.py` once it lands (the audit's requirement-awareness deep-dive shows the intake pattern already works for scope; this pass is its first compose-side consumer); (2) until then, `None` → the prompt's default posture is "internally consistent with the report's own dominant register" — consistency is judged, never a fixed style. Scope constraints already parsed (`nodes/scope_gate.py:1010-1059`) ride along read-only so the reviewer never "fixes" a deliberate scope emphasis as a tone defect.

### 2.6 Models + tokens (§9.1.8 lock)

Critique and revise are GENERATOR-role calls (composition edits), resolved through the SAME central runtime-lock path fact_dedup and depth_synthesis use (`OpenRouterClient(model=gen_model)`, `multi_section_generator.py:10065`; depth_synthesis explicitly bans per-leg model knobs — same rule here). No `PG_HOLISTIC_MODEL` knob. Token caps generous (cap-not-target, usage-billed): `PG_HOLISTIC_CRITIQUE_MAX_TOKENS` (default 16384), `PG_HOLISTIC_REVISE_MAX_TOKENS` (default 8192), reasoning bounded via the same floor/bound pattern as fact_dedup (`:10079-10090`). Temperature 0.2 (dedup precedent) for determinism.

### 2.7 Parallelism + determinism + wall-clock

- H1 is ONE call (global view is irreducibly one look — but it is only one call).
- H3 revise calls: concurrent, semaphore 32 (env). Re-verify offloaded to threads.
- Deterministic across cores: plan JSON arrays sorted on parse; edits applied in section-index order; verbatim-quote anchoring is exact-match; temperature 0.2; the checkpoint replay (§3.3) is fully deterministic with zero LLM calls.
- Budget: 1 critique + K revise calls (K = flagged sections, typically 2–6). Target ≤ 3 minutes wall added to a full run; ≤ 30 s on the fast subset.

### 2.8 Telemetry + disclosure (fail loud, operator-readable)

- `multi.holistic_review_telemetry` dict → manifest: `{plan, edits_accepted, edits_rejected_reverify, edits_rejected_citation_loss, reorder_applied, contradiction_flags, depth_flags, wall_ms}`.
- Liveness marker on stdout each run: `[activation] holistic_review: accepted=<n> rejected=<m> reorder=<0|1> contradictions_flagged=<k>` (honest-liveness convention, `multi_section_generator.py:8806-8823`) — a silent no-op is detectable in the forensic monitor.
- Depth flags and contradiction flags also surface one line each in the existing Methods/Limitations disclosure lane — depth cannot be fabricated, so it is DISCLOSED (weight/disclose, never a forced number).

---

## 3. Self-contained section (the mandate: hamster loop + lock-down bar + checkpoint)

### 3.1 (a) Fast isolation hamster loop

Harness: `scripts/section_harness/holistic_review_harness.py`. It imports ONLY the module + fixtures — no sweep, no retrieval, no spend by default.

- **Input**: a sections snapshot — either a real run's `holistic_review_input.json` checkpoint (§3.3) or a banked fixture in `tests/fixtures/holistic_review/` (build one from the drb_72 report, whose composition-collapse redundancy is the known disease: Goldman 2.5% GDP in 4 sections, robot-count in 4 — the repetition-guard docstring documents it).
- **Modes**: `--fake-llm` (canned critique/revise JSON, zero spend, < 2 min) and `--live` (real generator-role calls on the snapshot, ≤ 10 min).
- **Output, every run**: the critique plan; per-edit ACCEPT/REJECT with reason (reverify_fail / citation_loss / word_guard / anchor_miss); a unified before/after diff per section; the R2 evidence-id preservation check result; the byte-identical-when-OFF check.
- **The loop**: quick test (harness) → read EVERY line of the diff + telemetry (forensic, §-1.1 — a wrong edit is a content defect, not a status) → Fable investigates root cause → Opus builds the patch → retest on the SAME snapshot. Concurrent with the other design sections' loops — the harness holds no shared state and the checkpoint file is its only interface.

### 3.2 (b) Lock-down acceptance bar

| # | Check | How proven |
|---|---|---|
| A1 | Flag OFF ⇒ byte-identical `MultiSectionResult` | hash test, offline |
| A2 | ZERO report-wide evidence-id loss, always | adversarial fake critique that tries to delete citations ⇒ edits rejected; deterministic R2 gate test |
| A3 | Every accepted rewrite re-passed the UNCHANGED strict_verify; a fake rewrite with a fabricated number is rejected and the original kept | offline red/green with fake LLM |
| A4 | Contradiction fixture (two sections, opposing verified claims) ⇒ both sides survive; tension hedged or disclosed; NEVER a side deleted | fixture test |
| A5 | Tone fixture + deliverable_spec ⇒ style converges to the SPEC (requirement-aware), numerals byte-preserved | fixture test with two specs producing two different accepted revisions |
| A6 | Re-order respects back-reference topology ("as noted under X" ⇒ X stays before the referencing section) | fixture test |
| A7 | ≤ 3 min wall added on the full drb_72 snapshot at concurrency 32 | live harness timing |
| A8 | Kill mid-pass ⇒ resume replays from checkpoint, zero repeated LLM spend | crash-resume test (§3.3) |
| A9 | D8 4-role inputs are built from the POST-review sentences | seam assertion in the sweep integration test |
| A10 | Word guards enforce 80–130% per section + report floor; violation ⇒ originals + degrade marker | fixture test |
| A11 | Behavioral fire in REAL output: on a small real run the liveness marker shows accepted ≥ 1 OR an honest `no_edit_needed` plan — never a silent inert flag | small real run before any paid full run (memory 2026-07-02) |

### 3.3 (c) Checkpoint at the input/output boundary

Boundary = the pass's entry/exit inside `generate_multi_section_report` (just before `:10633`).
- **Entry**: write `<PG_HOLISTIC_CHECKPOINT_DIR>/holistic_review_input.json` — question, deliverable_spec, per-section `{title, sv_sentences[], verified_text_sha256}`, plus a whole-input sha256. The sweep sets the dir env to the run's checkpoint folder (same incremental+resume family as the fetch `results.jsonl` + A15 resume machinery).
- **Exit**: write `holistic_review_output.json` — the critique plan, every edit with its ACCEPT/REJECT verdict + reason, the permutation, the final per-section sentence lists, telemetry.
- **Resume**: on re-entry, if the input hash matches an existing output file, REPLAY the recorded accepted edits deterministically (pure code, zero LLM calls) and continue. A crashed run resumes from this boundary instead of re-paying H1/H3 (resume-from-closest-checkpoint ground rule, memory 2026-07-01). The same two files ARE the harness fixtures — one artifact, three uses (resume, isolation loop, forensic audit trail).

---

## 4. Build plan for Opus (surgical, not rewrite)

| PR | Content | Est. LOC |
|---|---|---|
| 1 | `generator/holistic_review.py` (H1 parse+anchor check, H2 permutation+topology, H3 revise+re-verify, R1–R6 gates, checkpoint I/O) + unit tests with fake LLM (A1–A6, A10) | module ~550; tests ~400 |
| 2 | Wiring: `multi_section_generator.py` call before `:10633` + `deliverable_spec` kwarg + telemetry field on `MultiSectionResult` + sweep threading (env dir, manifest key) + integration test (A8, A9) | ~80 + tests |
| 3 | `scripts/section_harness/holistic_review_harness.py` + drb_72 fixture + Gate-B slate pin `PG_HOLISTIC_REVIEW=1` + A7/A11 live evidence | ~220 |

Each PR ≤ 200-LOC-of-src cap where feasible; PR 1's module exceeds it — declare the exemption in the brief up front. Standard dual gate (Codex + Fable) per issue. Do NOT touch: `strict_verify`, NLI, D8 roles, provenance, span-grounding, `cross_section_reflector.py` (stays as pipeline B's), the repetition guard, fact_dedup.

## 5. Explicit non-goals

- No paraphrase auto-collapse without the exact-signature gate (silent-drop risk the guard already litigated).
- No new standalone sentences, no LLM-authored transitions (assembly stays mechanical).
- No contradiction adjudication — flag/hedge only.
- No breadth/length/quality TARGET anywhere in the pass — the guards bound damage, they never chase a number.
