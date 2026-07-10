# MASTER EXECUTION PLAN — architecture fix campaign (Fable 5 synthesis of Designs 1-6)

Author: FABLE 5 (architect brain). Date: 2026-07-10. Branch: `bot/I-deepfix-relaunch` (HEAD `0bde6438`).
Synthesizes: `01_offtopic_subquery.md`, `02_holistic_review.md`, `03_deliverable_awareness.md`,
`04_baskets_per_section.md`, `05_orchestrator_revise.md`, `06_checkpoint_resume_arch.md`, anchored on
`.codex/I-arch-audit/fable_orchestration_audit.md`. Design 7 (`07_querygen_breadth_scope.md`) and
`00_frontier_reference_2602_01566.md` are reference docs, not build items in this plan.

**How Opus uses this document.** This plan is the ORDER OF BATTLE: it fixes the section boundaries,
the build sequence, the cross-design conflict rulings, and the locked config. Each numbered design
doc remains the BINDING detail spec for its component (file:line seams, dataclasses, flags, prompts).
Where this plan and a design doc disagree, THIS PLAN WINS (the rulings in §2 exist precisely to
resolve those disagreements). Opus follows this plan verbatim: work packages in §5 order, each under
§-1.2 issue-first workflow, each dual-gated (real Codex CLI + real Fable 5, both APPROVE), 200-LOC
PR cap with declared exemptions.

**Standing mandates (unchanged, binding on every work package):**
- §-1.3 weight-and-consolidate; the faithfulness engine (strict_verify / NLI / 4-role D8 /
  provenance / span-grounding) is UNTOUCHED by every package — zero diffs under those paths, checked
  at every gate.
- §-1.1 line-by-line forensic audits; no metadata/pattern/sample shortcuts.
- LAW VI: every knob is env/config; defaults are byte-identical-OFF; the Gate-B slate pins the ON
  state (flag-gated is NOT done until the slate pin lands).
- §9.1.8 model/token lock: generator `deepseek/deepseek-v4-pro`, mirror `z-ai/glm-5.1`, sentinel
  `minimax/minimax-m2`, judge `qwen/qwen3.6-35b-a3b`; side judges map to the mirror; max_tokens
  generous (cap-not-target); no per-leg model knobs.
- Fable investigates root cause, Opus builds, Codex+Fable gate. Offline tests are not a preflight:
  each section proves itself on banked replay, then ONE small real run, before any paid full run.

---

## 1. SECTION DECOMPOSITION — the pipeline as 8 locked, checkpointed sections

This is Design 6 §2 adopted verbatim as the master skeleton. Every section is a module with a frozen
input contract (the upstream checkpoint) and a frozen output contract (its own checkpoint). All
boundaries are EXISTING seams in `run_one_query` — surgical re-wire, no pipeline rewrite.

| # | Section | Owns | Output checkpoint | Fix applied (design) |
|---|---|---|---|---|
| S0 | INTAKE | question + scope-constraint extraction + NEW deliverable-spec extraction | `cp0_intake_spec.json` | Design 3 (deliverable spec) |
| S1 | RETRIEVE | FS-Researcher query-gen, search fusion, fetch cascade, merge, fetch-yield gate | `cp1_fetch_snapshot.json` (exists) | Design 6 §5 (LOCKED fetch 14 + paid-tail retry) |
| S2 | SELECT+WEIGH | rerank, scope-weight demote, topic gate, junk-deletion gate, selection | `cp2_corpus_snapshot.json` (exists) | Design 1 (sub-query-aware off-topic judge) |
| S3 | CONSOLIDATE | finding/claim baskets, contradiction detectors | `cp3_basket_snapshot.json` (NEW) | Design 6 (checkpoint only; dedup loop already landed) |
| S4 | OUTLINE | outline planner + NEW basket-digest menu + requirement block + revise loop | `cp4_outline_snapshot.json` (NEW) | Design 5 (ORCH-1/2/3) + Design 4 D3 (merged, ruling R2) |
| S5 | COMPOSE | multi-section generation, section-basket map, depth/analyst synthesis, fact_dedup, holistic review (tail), repetition guard | `cp5_generation_snapshot.json` (exists; land ITEM 5a re-entry) | Design 4 (baskets-per-section) + Design 2 (holistic review) + Design 3 consumer 2 (style block) |
| S6 | VERIFY | strict_verify + NLI sentence repair — the frozen engine | `cp6_postverify_checkpoint.json` (exists; wire re-entry) | none (untouched); wiring only |
| S7 | ADJUDICATE+RENDER | 4-role D8, redaction, reference-style/shape render, assembly, manifest | terminal artifacts (`report.md`, `manifest.json`, sidecars) | Design 3 consumer 3/4 (reference style, shape, adherence disclosure) |

S7 is never resumable-past: D8 verdicts are never checkpoint-replayed (§-1.3 ABSOLUTE). The one
narrow exception is a render-only re-run (pure-code `report_assembler`) when prose is byte-identical.

---

## 2. CROSS-DESIGN CONFLICT RULINGS (binding — these amend the design docs)

**R1 — ONE DeliverableSpec.** Designs 3 and 5 each specify an extractor. RULING: build Design 3's
module `src/polaris_graph/retrieval/deliverable_spec_extractor.py` (the richer dataclass with
`structure_slots`, `reference_style`, `length_*`, `raw_directives`, O2 slot wiring). Design 5 ORCH-2
does NOT build its own dataclass; it CONSUMES Design 3's spec (Design 5's `required_sections` :=
Design 3's `structure_slots` titles; `length_target` := Design 3's length fields). One flag:
`PG_DELIVERABLE_SPEC` (Design 3's name). Design 5's `PG_EXTRACT_DELIVERABLE_SPEC` is dropped.

**R2 — ONE outline basket-digest menu.** Design 4 D3 and Design 5 ORCH-1 build the same thing.
RULING: build Design 5's `src/polaris_graph/generator/outline_digest.py` (it is the fuller spec:
basket lines + singleton lines + graceful terse + headroom guard + 100%-of-pool honesty assert).
Flag: `PG_OUTLINE_BASKET_DIGEST` (Design 5's name). Design 4's `PG_OUTLINE_BASKET_DIGESTS` flag and
its D3 subsection are superseded; Design 4 keeps everything else (map, roles, refine-NLI, absorb).

**R3 — Holistic review wiring point is Design 2's seam, inside S5.** Design 6's table places the
holistic pass in S7; Design 2 cites the exact code seam: inside `generate_multi_section_report`,
immediately BEFORE `_apply_cross_section_repetition_guard` at `multi_section_generator.py:10633`.
RULING: Design 2's seam is authoritative — the pass runs at the S5 TAIL, where sentences still live
at SV level with `[#ev:]` tokens (strict_verify re-runs directly). D8 stays in S7 and adjudicates the
POST-review prose. Design 6's S7 row is amended accordingly.

**R4 — ORCH-3 revise and the section-basket map compose cleanly.** Order inside S4→S5: wave-1
outline → build `SectionBasketMap` → compose wave-1 → ORCH-3 revise ops → REBUILD the map for the
new plan set (pure code, <5 s — never patch it incrementally) → recompose only changed sections
(each recomposed section gets its baskets through the rebuilt map) → holistic review → repetition
guard. Per-section composed checkpoints (`section_<idx>_composed.json`, Design 4 §7c) key on the
PLAN HASH so a revised section invalidates only itself.

**R5 — ORCH-4 gap re-retrieval ships OFF** (`PG_OUTLINE_GAP_QUERIES=0`), exactly per Design 5. It is
a follow-on activation after the full pipeline holds its bar; it is NOT in this campaign's critical
path.

**R6 — checkpoint names.** Design 1's `topic_gate_verdicts.jsonl` (intra-S2 incremental), Design 2's
`holistic_review_input/output.json` (intra-S5), Design 4's `baskets_global/outline_plans/
section_basket_map.json` (intra-S4/S5), and Design 5's `outline_input/plan/final.json` (S4) are all
INTRA-section checkpoints. They live inside the run_dir, are listed in `checkpoint_index.json` with
`stage` sub-ids, and use the shared envelope where JSON-shaped (JSONL streams record their file
sha256 in the index at section close). The 8 `cpN` files are the SECTION boundaries; intra-section
files make crashes cheap within a section. Design 5's `outline_final.json` IS `cp4` (one file, both
names retired in favor of `cp4_outline_snapshot.json`).

**R7 — Design 2's deliverable-spec dependency is soft.** Holistic review takes `deliverable_spec`
when present; `None` → "internally consistent with the report's own dominant register" (Design 2
§2.5). So the holistic module builds WITHOUT waiting for Design 3 to land; the spec threads in when
S0 merges.

---

## 3. PER-SECTION: fix + hamster loop + lock-down acceptance bar

Each subsection names the fix, the fast concurrent loop (test → read-every-line → Fable-investigate
→ Opus-build → retest), and the bar. The named design doc's full acceptance list is BINDING; the bar
here is the summary contract Opus must not ship under.

### S0 — INTAKE (Design 3)
- **Fix:** `deliverable_spec_extractor.py` — regex primary for mechanical fields (citation style,
  lengths, shape words, tables), ONE mirror-model (GLM-5.1) call for semantic fields (tone, audience,
  reading level), O2 `extract_instruction_slots` finally wired into `structure_slots`. Anti-invention:
  every field carries a verbatim trigger span or is rejected. Threaded: scope_gate seam (after
  `scope_gate.py:1059`) → `protocol["deliverable_spec"]` → `run_dir/deliverable_spec.json` → four
  consumers (outline, compose style block, render, Methods adherence disclosure).
- **Hamster loop:** Level 0 offline battery (~40 real DRB-II prompt phrasings, seconds); Level 1
  `scripts/deliverable_spec_harness.py` live extraction at 32-concurrent (~1 min/iter), Fable reads
  every JSON line field-by-field vs the prompt's actual words; Level 2 banked-corpus compose replay
  (outline + one section + references, minutes). Exit: two consecutive iterations, zero IGNORED, zero
  FAITHFULNESS-VIOLATION.
- **Bar (Design 3 §6.b, all six):** OFF byte-identical (prompt-string SHA equals HEAD); 100% mechanical
  extraction with spans, zero invented fields; behavioral honoring on 3 corpora × 3 specs
  (dual-gate directive-by-directive); faithfulness-neutral (±2% verified-sentence noise, zero diff
  under untouchable paths); fail-open proof; Methods adherence disclosure present.

### S1 — RETRIEVE (Design 6 §5 — the LOCKED fetch config)
- **Fix:** `PG_BYPASS_MAX_INFLIGHT` 20→14 in the Gate-B slate (operator-locked ceiling). NEW paid-tail
  retry INSIDE S1: after the main fetch pass, the residual failed/timeout/shell URLs (~8%) get ONE
  structured second pass at `PG_FETCH_TAIL_CONCURRENCY=8`, routed PAID-lane-first (Zyte first for the
  tail, then the normal cascade), reusing `resume_refetch.py` re-grounding; overload-timeouts counted
  SEPARATELY from real failures so they never burn the per-URL cap-2 budget. Tail runs BEFORE
  `cp1_fetch_snapshot.json` is written and before the fetch-yield gate scores the honest post-tail
  yield. Flags: `PG_FETCH_TAIL_RETRY=1`, `PG_FETCH_TAIL_CONCURRENCY=8`, `PG_FETCH_TAIL_PAID_FIRST=1`.
- **Hamster loop:** replay the banked failed-URL set from the drb_72 fetch artifacts through the tail
  pass alone (the `run_fetch_921.sh` pattern, now in-pipeline); read every recovered/still-dead row
  line; Fable names the leak, Opus patches, rerun. Real proof: one small real run; the fetch-yield
  number (N of M) is the FIRST forensic number every monitoring tick.
- **Bar:** tail pass recovers a material fraction of the banked failure set (line-by-line verified,
  no fabricated rows — a still-dead row stays disclosed-degraded); overload-timeout accounting visible
  in telemetry; `fetch_snapshot.json` schema unchanged; fetch-yield gate evaluates post-tail; flags
  OFF byte-identical.

### S2 — SELECT+WEIGH (Design 1)
- **Fix:** sub-query-aware topic judge. Stamp `retrieval_subquery` on every FS row (3 sites in
  `fs_researcher_query_gen.py`); gate derives anchors (`retrieval_subquery` > `query_origin` > none;
  label/junk anchors degrade to main-only); group rows by anchor; dual-anchor prompt per group; verdict
  set `ON_MAIN / ON_SUBQUERY / OFF_ASPECT / OFF_SUBJECT`; ON if on-topic to EITHER anchor; delete stays
  reserved for OFF_SUBJECT-against-BOTH (junk gate needs ZERO changes — the deletable class narrows
  mechanically). `ON_SUBQUERY` stamps a telemetry sidecar. Parallel batch dispatch
  `PG_SCOPE_TOPIC_PARALLEL` (slate 32). Incremental JSONL checkpoint `topic_gate_verdicts.jsonl` with
  header-pinned identity; resume replays judged rows without LLM calls. Flag
  `PG_TOPIC_GATE_SUBQUERY_AWARE` default ON.
- **Hamster loop:** `scripts/dr_benchmark/topic_gate_subquery_harness.py` on the banked drb_72
  `corpus_snapshot` (`--only 50` in <60 s; full 900 rows in single-digit minutes at parallel 32).
  One printed line per row (`evidence_id | verdict | anchor_kind | subquery | title`); Fable reads
  the verdict lines against actual titles; `--refresh-group` re-judges only the group under
  investigation.
- **Bar (Design 1 §4d, all seven):** OFF byte-identical, existing suite green untouched; unit battery
  (label-anchor rejection, precedence, legacy tokens, fail-open, deterministic grouping); drb_72
  behavioral replay — zero sub-query-relevant deletions AND the confirmed true junk still deletes with
  disclosure, read line-by-line; determinism at parallel 32; crash-resume identity; zero faithfulness
  diffs; dual gate.

### S3 — CONSOLIDATE (Design 6 checkpoint only)
- **Fix:** none to the consolidation logic itself (finding_dedup/credibility_pass/detectors stand as
  deployed). NEW `cp3_basket_snapshot.json` writer at the post-consolidation seam: baskets (members,
  corroboration_count, weights), contradiction pairs — DATA only (a basket is consolidated evidence,
  not a verdict).
- **Hamster loop:** shared with the checkpoint layer (§4): write → kill → resume-at-cp3 → assert
  basket identity vs the banked run.
- **Bar:** cp3 round-trips byte-identically on the drb_72 bank; verdict-smuggling RED test refuses a
  poisoned cp3; resume at cp3 skips the NLI cross-encoder time and re-runs S4-S7 gates fresh.

### S4 — OUTLINE (Design 5, digest per ruling R2, spec per ruling R1)
- **Fix:** three components. ORCH-1 `outline_digest.py`: basket lines (claim text + corroboration +
  tier mix + member ev_ids) + singleton lines, 100% pool coverage, graceful terse, flag
  `PG_OUTLINE_BASKET_DIGEST`. ORCH-2 requirement-aware outline: REQUIREMENTS block (from the S0 spec)
  in the user prompt — required sections REQUIRED-IF-GROUNDED (undersupplied → disclosed-gap section,
  never silent drop, never fabrication), audience/tone as planning context, scope constraints stated;
  clinical 8-title path byte-identical unless the user explicitly supplies structure. ORCH-3 revise:
  wave barrier after compose → deterministic per-section `SectionOutcome` digests (pure code) → ONE
  reviser call → ops `keep/merge/split/retitle/reassign/add` under deterministic apply rules (`keep`
  = byte-identical reuse; recompose runs the FULL section pipeline; invalid ops rejected with reason
  codes; wholesale-invalid → keep wave-1). Bounds: `PG_OUTLINE_REVISE_ROUNDS=1` (hard max 2),
  `PG_OUTLINE_REVISE_MAX_RECOMPOSE=8`. ORCH-4 ships OFF (ruling R5).
- **Hamster loop:** `scripts/orchestrator_lab/outline_lab.py` on banked run dirs, three modes —
  `plan` (1 LLM call, <1 min), `revise` (1 call, no recompose cost), `apply-dry` (recorded output,
  zero LLM, milliseconds — where apply bugs are hunted). Multiple banked domains run concurrently.
- **Bar (Design 5 §9, all nine):** structural validity on 3 corpora × 3 runs; menu honesty (100% of
  rows accounted); coverage (every corroboration≥3 cluster assigned or disclosed-orphaned); requirement
  firing IN THE RENDERED report (headings match user structure, order included); revision firing on a
  banked thin-section run with byte-identical `keep` hashes; zero faithfulness diffs; apply-dry
  determinism; §-1.1 line-by-line audit of one full revised report; clinical byte-identity flags-OFF.

### S5 — COMPOSE (Design 4 + Design 2 + Design 3 consumer 2)
- **Fix A (Design 4 — baskets-per-section):** `synthesis/section_basket_map.py` — deterministic
  basket→section map: candidates from three signals (provenance floor = today's intersection rule,
  sub-query lineage, topical overlap), ONE primary home per basket (weighted argmax, keep-first ties),
  corroborating memberships carry only the section-matched facet ev_ids, no-candidate baskets go to
  ONE residual section — `stranded_count == 0` structurally (vs ~600/657 stranded today). Compose:
  primary view → full per-basket treatment exactly once run-wide; corroborating view → facet-scoped
  multicited sentence, never the full narrative re-emitted. Verify pools stay FULL basket-scoped in
  both roles (no sentence newly passes or fails). D4 per-section merge-refinement NLI (pairs ≤~1800,
  under the 20000 global cap that skips on big corpora — the drb_72 under-merge recall returns);
  merges relabel GLOBALLY. F1 orphan-router and the recomputed intersection become flag-OFF legacy.
  Flag `PG_SECTION_BASKET_MAP` (+ role policy, refine-NLI, weight knobs).
- **Fix B (Design 2 — holistic review, at ruling-R3's seam):** `generator/holistic_review.py` —
  H1 ONE whole-report critique call → bound JSON edit plan with verbatim-quote anchoring (unmatched
  quotes discarded); H2 deterministic structural edits (section permutation under back-reference
  topology; exact-signature consolidation via repetition-guard mechanics); H3 concurrent per-section
  revise (semaphore 32) on SV sentences with MANDATORY strict_verify re-run per changed sentence —
  fail → original kept. Edit contract: permute / re-verified replace / exact-signature consolidate /
  hedge-clause attach — nothing else. Hard gates R1-R6: re-verify, zero report-wide evidence-id loss,
  contradictions never adjudicated (hedge + disclose, both sides ship), 80-130% word guard + 0.90
  report keep-floor, fail-conservative snapshot restore, kill-switch `PG_HOLISTIC_REVIEW` (slate ON).
  Consumes the S0 deliverable spec when present (ruling R7).
- **Fix C (Design 3 consumer 2):** `render_section_style_block(spec, n_sections)` appended by the
  section-prompt selector — audience/tone wording + derived sentence budget when a length ask exists
  (`hard` strictness routes to the existing CONCISE variant); CRITICAL RULES always win; brevity
  compresses sentences, never drops sources (multi-citation consolidation keeps every basket source).
- **Hamster loops (three, concurrent — no shared state):** `scripts/replay_section_basket_map.py`
  (banked drb_72 baskets+plans, pure code, SECONDS per iteration, full assignment table read
  line-by-line; 30-basket fixture for branch coverage); `scripts/section_harness/
  holistic_review_harness.py` (`--fake-llm` <2 min zero spend / `--live` ≤10 min on the drb_72
  snapshot; per-edit ACCEPT/REJECT with reason + before/after diff read line-by-line); the Design 3
  Level-2 compose replay for the style block.
- **Bar:** Design 4 §7b all eight (stranded==0; one primary home per basket; full treatment exactly
  once + repetition-guard fires ~0; byte-identical map across 3 builds/any worker count/any input
  permutation; faithfulness frozen incl. §-1.1 before/after audit; OFF byte-identity; ≥1 refine merge
  where the global pass skipped; map <5 s, refine <60 s/section) AND Design 2 §3.2 all eleven (A1
  OFF-hash through A11 behavioral fire in real output) AND the style block's faithfulness-neutral
  proof (Design 3 bar #4).

### S6 — VERIFY (wiring only)
- **Fix:** none to the engine. Land ITEM 5a (generator-side cached-draft re-entry consuming
  `reused_outline` + raw drafts — validation/reconstruction already exists at
  `run_honest_sweep_r3.py:8740-8790`) so cp5 becomes a real skip point; wire the existing
  `postverify_checkpoint` loader as the cp6 re-entry ("re-enter right before the judge seam,
  re-run only the cents-cost judge").
- **Hamster loop / bar:** covered by the checkpoint-layer matrix (§4): resume-at-cp5 skips the
  ~30-40-min generation with zero generator billing for stages ≤5 AND the run_log shows every
  verify/D8 `[activation]` marker recomputed downstream; resume-at-cp6 re-runs only D8+render.

### S7 — ADJUDICATE+RENDER (Design 3 consumers 3+4)
- **Fix:** `_render_bibliography_lines` gains `reference_style` (numeric default byte-identical;
  author-year/APA/Harvard/Vancouver render from REAL captured metadata only — no-author rows fall back
  to title-year WITH a Methods disclosure; never fabricate an author or year; in-text `[N]` stays in
  v1). `assemble_report_md` gains ordering (summary-first / memo shapes / recommendations-last) —
  re-ordering and re-labeling of verbatim-extractive blocks only, zero new claim text. Methods gains
  the "Deliverable requirements" adherence block: every parsed directive verbatim + HONORED /
  PARTIAL(reason) / NOT-GROUNDED status. D8 + redaction untouched.
- **Hamster loop:** Design 3 Level-2 harness renders references+shape from banked corpora per spec
  fixture; every reference line read against real captured metadata.
- **Bar:** Design 3 bars #1, #3, #6 as they apply to render; zero fabricated metadata (spot-read
  line-by-line); render-only re-run path proven (byte-identical prose in → only assembly re-executes).

---

## 4. CHECKPOINT / RESUME / TRACEABILITY ARCHITECTURE (Design 6, the connective tissue)

**Envelope.** One shared `src/polaris_graph/generator/checkpoint_envelope.py` for all 8 `cpN` files:
`schema_version` pin, `stage`, question SHA (GATE0 identity), `upstream {name, sha256}` hash-chain,
`flag_slate` (resume refuses on drift), `adjustments_applied`, DATA-only payload with the RECURSIVE
forbidden-verdict-key guard extended to every checkpoint. Atomic writes (temp + `os.replace`),
sorted-keys deterministic bytes. Best-effort write (never abort a paid run), fail-loud read (corrupt/
mismatched never silently loads). cp1/cp2/cp5/cp6 migrate ADDITIVELY (old snapshots still load via a
legacy branch).

**Traceability ledger.** `checkpoint_index.json` per run_dir: append-ordered
`{stage, file, sha256, created_utc, upstream_sha}` covering section checkpoints AND intra-section
files (ruling R6). Hash-chain validation = walk the list; the forensic monitor and the resume
resolver read ONLY this file to know where a run died and what is trustworthy.

**Resume contract — load N, adjust DOWNSTREAM only, re-run N+1..7.**
`run_gate_b.py --resume [--resume-from cpN] [--adjust adjustments.yaml]`. Default = nearest checkpoint
(the existing later-wins rule generalized over the 8-chain). The adjustment spec uses the SAME
requirement vocabulary S0 produces on a fresh run — fresh-run requirements and resume-time adjustments
are ONE schema, so the operator can say "resume drb_72 from the outline step, tone executive-brief,
cap 3000 words" and the S0 extractor parses it. Validity matrix enforced fail-loud: deliverable
adjustments valid from cp3+; scope adjustments from cp1 (asking at cp4 errors and names the correct
earlier entry); question change = new run (GATE0 blocks). An adjustment can NEVER mutate a loaded
checkpoint's payload — it only reconfigures the stages that re-run. Supersede-never-delete: later
checkpoints + old terminals move to `run_dir/superseded/<utc>/`, recorded in the index. Resume event
stamped into manifest + Methods (entry checkpoint, adjustment digest, lineage pointer) — disclosed,
never silent. Every resumed stage re-runs EVERY faithfulness gate from data; a crash mid-resume is
just another crash (next `--resume` lands on the new nearest point).

**Isolation dividend.** Each section can be swapped, re-baked, or bake-off'd alone by feeding it a
banked upstream checkpoint and diffing its output checkpoint — this is what makes every hamster loop
in §3 cheap, and it is why the envelope builds FIRST (§5 wave 0).

**Layer's own loop + bar (Design 6 §7):** `scripts/checkpoint_resume_harness.py` — concurrent
kill/resume matrix over every cpN × adjustment class on the banked drb_72 run_dir (truncate-copy,
resolve, assert selection + chain validation + tamper refusal + validity rejection; cheap stages
actually re-run and byte-diff). Bar: all eight of Design 6 §7b — matrix green; upstream-skip proven in
the cost ledger; gate re-run markers present; verdict-smuggling RED; adjustment-scoping proof (cp4
tone change leaves cp1-cp3 sha256s untouched); determinism; §-1.1 audit of one resumed report;
fresh-vs-cp2-resumed parity of verified-claim sets.

---

## 5. SEQUENCING — waves, dependencies, concurrency

Dependency spine: envelope → everything; S0 spec → S4 ORCH-2 / S5 style block / S7 render / --adjust
vocabulary (soft for Design 2 per ruling R7); S4 digest → S4 revise; map rebuild rule R4 ties S4↔S5.
Everything else is independent. Each work package = its own GitHub Issue (§-1.2: issue FIRST, grep
adjacent files, offline smoke, then Codex brief), its own PR(s), dual-gated.

**WAVE 0 — foundation (build first, both packages concurrent).**
- WP-0a: `checkpoint_envelope.py` + `checkpoint_index.json` + additive cp1/cp2 migration (Design 6
  build item 1).
- WP-0b: LOCKED fetch — slate 20→14 + paid-tail retry + separate overload accounting (S1; Design 6
  build item 2). ← cheap fix #1 (audit gap #4, small).

**WAVE 1 — independent section fixes (all four concurrent; no shared files).**
- WP-1a: S2 sub-query-aware topic judge, PR-1 core + PR-2 parallel/checkpoint/harness (Design 1).
  ← cheap fix #2 (audit gap #2, small).
- WP-1b: S0 deliverable-spec extractor + scope-gate seam + protocol/checkpoint threading (Design 3
  PRs 1-2). ← cheap fix #3 (the extractor is small; it unblocks three downstream consumers).
- WP-1c: S5 `holistic_review.py` module + fake-LLM unit battery + harness (Design 2 PRs 1+3 module
  part; wiring deferred to wave 3). Uses ruling R7 — no wait on WP-1b.
- WP-1d: S5 `section_basket_map.py` module + fixture + replay harness (Design 4 WP1).

**WAVE 2 — outline + compose consumption (starts as its wave-1 inputs land).**
- WP-2a: S4 `outline_digest.py` + `finding_clusters` threading (Design 5 build 1; ruling R2).
- WP-2b: S4 ORCH-2 requirement block (needs WP-1b) + cp3/cp4 checkpoints (Design 6 build 3,
  Design 5 build 3).
- WP-2c: S5 compose wiring of the basket map — fast path, role policy, F1 absorb, per-section
  composed checkpoints (Design 4 WP2+WP5).
- WP-2d: S5 style block + section-prompt selector threading (Design 3 PR-3; needs WP-1b).
- WP-2e: S5 D4 per-section merge refinement (Design 4 WP4).

**WAVE 3 — the loops that span sections (sequential-ish; each depends on wave 2).**
- WP-3a: S4 ORCH-3 revise (outcome digests, reviser call, deterministic apply, recompose wave, map
  rebuild per ruling R4) + `outline_lab.py` (Design 5 builds 4-5).
- WP-3b: S5 holistic-review wiring at the `:10633` seam + sweep threading + slate pin + A7/A11 live
  evidence (Design 2 PRs 2-3 remainder).
- WP-3c: S6/S5 re-entry — ITEM 5a generator hook + cp6 loader wiring (Design 6 build 4).
- WP-3d: S7 render — reference style + assembler ordering + Methods adherence block + Level-1/2
  harness (Design 3 PR-4).

**WAVE 4 — the connective layer + full assembly (after waves 0-3 lock).**
- WP-4a: `--resume-from` + `--adjust` + validity matrix + supersession + manifest disclosure
  (Design 6 build 5) + `checkpoint_resume_harness.py` (build 6) + cp0 (build 7).
- WP-4b: FULL-PIPELINE ASSEMBLY — all slate pins ON together; the kill/resume matrix across the
  8-chain; then ONE small real run read forensically line-by-line (fetch yield first number every
  tick); then the paid full run; then the §-1.1 before/after report audit vs the pre-campaign
  baseline.

Rules of engagement: a wave-1 package never blocks on another wave-1 package; within a package, its
own hamster loop runs to its bar BEFORE the dual gate; NO package merges without its design doc's
full acceptance list green; force-APPROVE only per §8.3.1 at iter-5 with residuals filed as Issues.

---

## 6. LOCKED CONFIG (operator-locked; the Gate-B slate is the single source of truth)

| Setting | Value | Where |
|---|---|---|
| Fetch workers | `PG_BYPASS_MAX_INFLIGHT=14` (operator-locked ceiling; history 48→16→20→14) | slate `run_gate_b.py:1492-1495` |
| Paid-tail retry | `PG_FETCH_TAIL_RETRY=1`, `PG_FETCH_TAIL_CONCURRENCY=8`, `PG_FETCH_TAIL_PAID_FIRST=1` (Zyte-first tail, before cp1 + yield gate) | S1, new |
| Topic gate | `PG_TOPIC_GATE_SUBQUERY_AWARE=1` (default ON), `PG_SCOPE_TOPIC_PARALLEL=32`, `PG_TOPIC_SUBQ_MIN_TOKENS=3` | S2 |
| Deliverable spec | `PG_DELIVERABLE_SPEC=1` (slate; default OFF), `PG_DELIVERABLE_SPEC_LLM=1`, `PG_DELIVERABLE_RENDER=1` | S0/S7 |
| Outline | `PG_OUTLINE_BASKET_DIGEST=1`, `PG_OUTLINE_DIGEST_MAX_CHARS=60000`, `PG_OUTLINE_REVISE=1`, `PG_OUTLINE_REVISE_ROUNDS=1` (hard max 2), `PG_OUTLINE_REVISE_MAX_RECOMPOSE=8`, `PG_OUTLINE_GAP_QUERIES=0` (ships OFF) | S4 |
| Section-basket map | `PG_SECTION_BASKET_MAP=1`, `PG_SECTION_BASKET_MAP_REFINE_NLI=1`, `PG_SECTION_BASKET_ROLE_POLICY=facet`, weights w_p=3/w_q=2/w_t=1 | S5 |
| Holistic review | `PG_HOLISTIC_REVIEW=1` (slate; default OFF), `PG_HOLISTIC_REVISE_CONCURRENCY=32`, word guard 80-130%, `PG_HOLISTIC_REPORT_KEEP_FLOOR=0.90`, critique/revise max_tokens 16384/8192 | S5 |
| Section compose concurrency | `PG_MAX_PARALLEL_SECTIONS` / `PG_PARALLEL_SECTIONS` raised 6→32 (env only; provider-rate permitting) | S5 |
| Verify / credibility concurrency | `PG_PARALLEL_VERIFY` as-is; `PG_CREDIBILITY_PASS_MAX_INFLIGHT=20` as-is | S6/S3 |
| Models | §9.1.8 lock verbatim: generator deepseek-v4-pro; mirror glm-5.1 (spec extractor semantic pass + side judges); judge qwen3.6-35b-a3b; NO per-leg model knobs; max_tokens = real provider caps | all |
| Slate discipline | force-exact frozenset pattern (`run_gate_b.py:1509-1527`) so a stray env cannot silently downgrade a paid run | all |

Max-parallelism posture: queries parallelize as independent run_dirs/processes with independent
checkpoint chains on the 128-core box; intra-section LLM stages run at their 32-band knobs; fetch is
the ONE deliberately low number (14) because overload-timeouts poison the per-URL cap — the paid tail
at 8 is the recovery lane, not a throttle.

---

## 7. DEFINITION OF DONE (the campaign, not a package)

1. Every §3 section bar green, every package dual-gate APPROVED, all slate pins landed.
2. The wave-4 kill/resume matrix green across all 8 checkpoints including one adjusted resume
   (cp4 + tone adjustment) with upstream sha256s untouched.
3. One small real run, then one paid full run, forensically monitored (fetch yield N-of-M first,
   every line read), with: zero sub-query-relevant deletions; stranded baskets 0; repetition-guard
   fires ~0; holistic review liveness marker honest; requested-structure headings honored in
   `report.md`; Methods carries adherence + deletion + resume disclosures.
4. §-1.1 line-by-line before/after audit of the full report vs the pre-campaign baseline: zero new
   UNSUPPORTED/FABRICATED, faithfulness engine byte-untouched (`git diff` proof on the frozen paths).
5. Residual risks stay OPEN as Issues (corroborating-role under-render A/B; author-metadata capture
   for full in-text author-year v2; ORCH-4 activation) — filed, not silently absorbed.
