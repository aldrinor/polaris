# DESIGN 6 — Section-modular checkpoint / resume / traceability architecture

Author: Fable 5 (architect). Date: 2026-07-10. Branch: `bot/I-deepfix-relaunch` (HEAD 0bde6438).
Grounding: real code cited per file:line + `.codex/I-arch-audit/fable_orchestration_audit.md`.
Standing mandates honored: §-1.3 weight-not-filter + basket faithfulness; the faithfulness engine
(strict_verify / NLI / 4-role D8 / span-grounding) is UNTOUCHED; max parallelism; requirement-aware
not hardcoded; fast subset + full run; crash-resilient incremental + resume.

---

## 1. What already exists (the seam this design generalizes — all real, all on the branch)

The sweep (`scripts/run_honest_sweep_r3.py`, driven by `scripts/dr_benchmark/run_gate_b.py`) already
has a working two-and-a-half-checkpoint resume spine:

| Existing artifact | Stage it captures | Written at | Loaded at |
|---|---|---|---|
| `fetch_snapshot.json` (#1259) | POST-FETCH: raw fetched+merged corpus, before rerank/selection | `run_honest_sweep_r3.py:11664` (fresh runs only, `:11647`) | `:9151-9153` |
| `corpus_snapshot.json` (F04 #539/#629) | POST-SELECTION: the billed `evidence_for_gen` + retrieval counts | `:15058` (the single pre-generation seam, `:15046-5055`) | `:9147-9150` |
| `postgen_checkpoint.json` (A12) | POST-GENERATION: raw section drafts + identity hashes | `:15367` (helper `:6858`) | loader exists `:6950` — **not yet a skip re-entry** |
| `generation_snapshot` (ITEM 5/5a) | outline (`SectionPlan` asdict) + raw drafts + atom catalog + flag slate | module `src/polaris_graph/generator/generation_snapshot.py` | sweep-side loader `:8740-8790`; generator-side re-entry hook **deferred** (slate deliberately not force-ON, `run_gate_b.py:1410-1420`) |
| `postverify_checkpoint.json` (A12) | POST-VERIFICATION: per-sentence verification accounting | `:17523` (helper `:6896`) | loader exists `:6950` — **not yet a skip re-entry** |
| `storm_outline.json` | structure-only outline scaffold across resume | `:6989-7002` (allow-list projection `:7005`) | on `--resume` |

Resume driver: `run_gate_b.py --resume` (`:6392-6394`) → `run_one_query(resume=...)`
(`:5593`, `:5955`, `:6623`). Resume-from-nearest picks the LATER of corpus/fetch snapshot
(`run_honest_sweep_r3.py:9147-9153`). GATE0 identity: a snapshot built for a DIFFERENT question
fail-loud aborts (`:9123-9147`). A15 degraded-row re-fetch on resume: `retrieval/resume_refetch.py`
+ `PG_RESUME_REFETCH_DEGRADED=1` (`run_gate_b.py:1357-1365`). Corrupt/version-mismatched snapshots
fail LOUD (`corpus_snapshot.py:137-180`); atomic write via temp + `os.replace`
(`corpus_snapshot.py:127-133`).

**The two binding invariants already enforced — this design keeps both ABSOLUTE:**
1. **DATA-ONLY checkpoints (§-1.3).** A checkpoint stores DATA, never a verdict. Forbidden verdict
   keys are rejected recursively at load (`run_honest_sweep_r3.py:6936-6947`, `:6950-6974`;
   `generation_snapshot.py` recursive guard). A resume re-runs EVERY faithfulness gate from the
   reloaded data. Nothing in this design changes that; it extends the same envelope to new stages.
2. **Fail-loud identity.** schema_version pin + question SHA + generation flag slate
   (`generation_snapshot.assert_generation_flags_match`) — a stale or mismatched checkpoint refuses
   to load; it never silently degrades.

**Gaps this design closes:** (a) only 2 of the checkpoints are actual re-ENTRY points; postgen /
postverify are written but never skipped-into (ITEM 5a deferral); (b) no checkpoints at the
consolidation, outline, or adjudication boundaries; (c) no way to resume WITH a user adjustment —
today `--resume` is byte-identical replay only; (d) no machine-readable per-run checkpoint index
(traceability ledger); (e) fetch worker count and the paid-tail retry are not yet the operator-LOCKED
values (audit gap #4).

---

## 2. Section boundaries — the pipeline as 8 locked sections, 8 checkpoints

Each SECTION is a module with a frozen input contract (the upstream checkpoint) and a frozen output
contract (its own checkpoint). A section owns everything between its two checkpoints and NOTHING
else. Every boundary below is an EXISTING seam in `run_one_query` — no pipeline re-write, this is
the SURGICAL re-wire mandate (§-1.3): formalize the seams that are already there.

| # | Section | Contents (real code) | Output checkpoint | Status |
|---|---|---|---|---|
| S0 | INTAKE | question + scope-constraint extraction (`retrieval/intake_constraint_extractor.py`, `nodes/scope_gate.py:1010-1059`) + the Design-5 deliverable-spec parse (tone/structure/references — the audit's requirement-BLIND gap) | `cp0_intake_spec.json` — question, question_sha, scope constraints, deliverable spec, active flag slate | NEW (small) |
| S1 | RETRIEVE | FS-Researcher query-gen (`retrieval/fs_researcher_query_gen.py`, dispatch `run_honest_sweep_r3.py:10289-10307`) + search fusion + fetch cascade (`src/tools/access_bypass.py:4553-5062`) + merge lanes + **the LOCKED fetch settings (§5)** + fetch-yield gate (`live_retriever.py:1974-2089`, evaluated post-tail-retry) | `cp1_fetch_snapshot.json` = existing `fetch_snapshot.json` | EXISTS |
| S2 | SELECT+WEIGH | embedding rerank, scope-weight demote map (`retrieval/constraint_enforcement.py`, wired `:14011-14063`), topic gate (`topic_relevance_gate.py`, called `:13329-13331`), junk-deletion gate + disclosure (`junk_deletion_gate.py`, wired `:13254-13350`), selection + V30/upload prepends | `cp2_corpus_snapshot.json` = existing `corpus_snapshot.json` (`:15058`) | EXISTS |
| S3 | CONSOLIDATE | finding/claim baskets (`synthesis/finding_dedup.py:933-1064`, `credibility_pass.py:51-77`), contradiction detectors (`retrieval/semantic_conflict_detector.py`, `contradiction_detector.py`, `qualitative_conflict_detector.py`) | `cp3_basket_snapshot.json` — baskets (members, corroboration_count, weights), contradiction pairs. DATA only: a basket is consolidated evidence, NOT a verdict | NEW |
| S4 | OUTLINE | outline planner `_call_outline` (`generator/multi_section_generator.py:2547`, prompts `:1380/:1419/:1454`) — upgraded per Design 3 to consume S3 basket digests | `cp4_outline_snapshot.json` — `SectionPlan` list (asdict round-trip, pattern already in `generation_snapshot.py`) + planner inputs digest | NEW (persistence pattern exists) |
| S5 | COMPOSE | multi-section generation + depth synthesis (`generator/depth_synthesis.py`, wired `:16550-16561`) + analyst synthesis | `cp5_generation_snapshot.json` = existing `generation_snapshot` + `postgen_checkpoint.json` (`:15367`) — **finish the ITEM 5a generator re-entry hook so this becomes a real skip point** | EXISTS, re-entry deferred |
| S6 | VERIFY | strict_verify + NLI sentence-repair (the frozen faithfulness engine — untouched) | `cp6_postverify_checkpoint.json` = existing (`:17523`) — wire its loader as a re-entry | EXISTS, re-entry not wired |
| S7 | ADJUDICATE+RENDER | 4-role D8 (`roles/release_policy.py`), redaction (`roles/report_redactor.py`), holistic review pass (Design 4), assembly (`synthesis/report_assembler.py` — pure code, no LLM) + manifest | terminal artifacts: `report.md`, `manifest.json`, `evidence_pool.json` (`:17546`), `four_role_settled_verdicts.jsonl` sidecar (`:6608`) | EXISTS |

**S7 is deliberately NOT a resumable-past point.** The D8 verdict may never be checkpoint-replayed
(§-1.3 ABSOLUTE, `_A12_FORBIDDEN_VERDICT_KEYS`). Any resume that lands at or after cp6 re-runs the
full S7 as one unit — that is exactly what `postverify_checkpoint` was built for: "re-enter right
before the judge seam and re-run only the cents-cost judge" (`run_honest_sweep_r3.py:17517-17520`).
The one narrow exception: a RENDER-ONLY re-run (formatting/citation-style change with byte-identical
prose) may re-execute `report_assembler` alone, because it is pure code with no LLM and no gate
(`synthesis/report_assembler.py:1-6`); if one verified sentence changes, S7 re-runs whole.

---

## 3. Checkpoint artifact format — one envelope for all 8

Every `cpN_*.json` uses the SAME envelope (superset of what `corpus_snapshot.py` /
`generation_snapshot.py` already write, so cp1/cp2/cp5/cp6 migrate by adding fields, not rewriting):

```json
{
  "schema_version": 1,                      // per-file pin; mismatch = fail-loud refuse (corpus_snapshot.py:168-174)
  "stage": "s3_consolidate",                // one of the 8 section ids
  "run_id": "...", "slug": "...", "domain": "...",
  "question": "...", "question_sha": "...", // GATE0 identity (run_honest_sweep_r3.py:9123-9147)
  "created_utc": "...",
  "upstream": {"name": "cp2_corpus_snapshot.json", "sha256": "..."},   // hash-chain: each checkpoint pins its input
  "flag_slate": {"...": "..."},             // the generation/selection-affecting env flags active when written
                                            // (assert_generation_flags_match pattern; resume refuses on drift)
  "adjustments_applied": [],                // list of adjustment-spec sha256s folded in upstream (empty on a fresh run)
  "payload": { ... },                       // the stage DATA (rows / baskets / plans / drafts / accounting)
  "faithfulness_invariant": "DATA ONLY; no verdict stored; a resume re-runs every gate."
}
```

Rules (all inherited from the existing modules, now uniform):
- **DATA only**, forbidden-verdict-key guard runs RECURSIVELY on load for every checkpoint
  (extend `load_a12_checkpoint`, `run_honest_sweep_r3.py:6950-6974`, into a shared
  `src/polaris_graph/generator/checkpoint_envelope.py`).
- **Atomic write** (temp + `os.replace`), sorted-keys JSON, no pickle — deterministic bytes so the
  same stage on any of the 128 cores produces the same sha256 (cross-core determinism check).
- **Best-effort write, fail-loud read**: a checkpoint write failure never aborts a paid run
  (`:15069-15070`); a corrupt/mismatched checkpoint never silently loads (`corpus_snapshot.py:137-180`).
- **`checkpoint_index.json`** (NEW, one per run_dir): append-ordered list of
  `{stage, file, sha256, created_utc, upstream_sha}` — the TRACEABILITY LEDGER. The forensic
  monitor and the resume resolver both read only this file to know where a run died and what is
  trustworthy. Hash-chain validation = walk the list, verify each `upstream_sha` matches the prior
  entry's `sha256`.

---

## 4. The resume contract — load N, adjust DOWNSTREAM only, re-run N+1..7

### 4.1 CLI + prompt surface

Extend the existing `run_gate_b.py --resume` (`:6392`), keeping it as the zero-argument
"nearest checkpoint, no adjustment" fast path:

```
python scripts/dr_benchmark/run_gate_b.py --only workforce/drb_72_ai_labor \
    --resume --resume-from cp4_outline --adjust adjustments.yaml
```

- `--resume-from <cpN>`: explicit entry stage. Default (absent) = nearest, the existing
  later-checkpoint-wins rule (`run_honest_sweep_r3.py:9147-9153`) generalized over the 8-chain via
  `checkpoint_index.json`.
- `--adjust <file>`: a user adjustment spec applied to DOWNSTREAM stages only.

**Requirement-aware prompt deployment (the operator's ask):** the user can hand the orchestrator a
plain-language instruction — "resume the drb_72 run from the outline step, but make the tone
executive-brief and cap it at 3000 words" — and the S0 intake extractor (same
`intake_constraint_extractor.py` fill-not-override pattern the audit verified for scope, extended
per Design 5 to the deliverable axis) parses it into `{run_dir, resume_from, adjustments}`. NOTHING
about the resume path is hardcoded to a template: the adjustment spec is the same requirement-spec
schema S0 produces on a fresh run, so fresh-run requirements and resume-time adjustments are ONE
vocabulary.

### 4.2 Adjustment spec (DOWNSTREAM-only by construction)

```yaml
resume_from: cp4_outline            # entry checkpoint
adjustments:
  deliverable:                      # tone / structure / audience / citation_style / length
    tone: executive_brief
    max_words: 3000
  scope:                            # date window / source-type weights / geo — S2 knobs
    date_window: {to: "2026-06"}
  env_overrides:                    # LAW VI: named flags only, validated against an allow-list;
    PG_FACET_OUTLINE: "1"           # flags that would change UPSTREAM stages are REJECTED for this entry point
```

**Validity matrix (enforced, fail-loud):** each adjustment class declares its EARLIEST valid entry
checkpoint. Deliverable adjustments → valid from cp3 or later (they touch outline/compose/render
only). Scope adjustments → valid from cp1 (they change S2 selection weights); requesting them at
cp4 is a hard error telling the user the correct earlier checkpoint. Question text change → NO
resume, GATE0 blocks it (`:9123-9147`) — that is a new run. This is what "adjustments applied to the
DOWNSTREAM only" means mechanically: an adjustment can never mutate a loaded checkpoint's payload
(frozen upstream truth); it only reconfigures the stages that will re-run.

### 4.3 Resume algorithm (the orchestrator loop)

1. Read `checkpoint_index.json`; validate the hash-chain up to the requested `cpN`; fail loud on a
   broken chain (a §-1.1 auditor gets the exact stage where trust ends).
2. Load `cpN` through the shared envelope loader: schema pin + question SHA + flag-slate match +
   recursive forbidden-verdict-key guard. Any mismatch = refuse, name the mismatch.
3. Validate the adjustment spec against the validity matrix for `cpN`.
4. **Supersede, never delete:** move every existing checkpoint LATER than `cpN` plus the old
   terminal artifacts into `run_dir/superseded/<utc>/` and record the supersession (with the
   adjustment-spec sha256) in `checkpoint_index.json`. Full lineage stays on disk — traceability.
5. Apply adjustments to the DOWNSTREAM config only (deliverable spec object + validated env slate).
6. Re-run sections `S(N+1)..S7` exactly as a fresh run runs them — every faithfulness gate
   re-executes (strict_verify, NLI, 4-role D8, span-grounding). Each completed section writes its
   fresh checkpoint, whose envelope records `adjustments_applied`.
7. Stamp the resume event into `manifest.json` + the report Methods disclosure: entry checkpoint,
   adjustment-spec digest, superseded-lineage pointer. Disclosed, never silent (§-1.3.1 discipline).

Crash DURING a resume is just another crash: the freshly written checkpoints make the next
`--resume` land at the new nearest point. Incremental + idempotent.

### 4.4 What resuming at each checkpoint buys (cost honesty)

cp1: skips search+fetch (the wall-clock/network bulk — `corpus_snapshot.py:3-8`); re-runs
selection→D8. cp2: also skips rerank+selection; the classic replay seam (GAP1, `run_gate_b.py:6382-6394`).
cp3: also skips basket consolidation (NLI cross-encoder time). cp4: also skips outline; re-composes.
cp5: skips the ~30-40 min generation, re-enters at verify (`generation_snapshot.py` WHY block) —
requires landing ITEM 5a. cp6: re-runs only the cents-cost D8 judge + render (`:17517-17520`).

---

## 5. LOCKED fetch settings folded into S1 (operator lock, this design's binding input)

- **14 workers, not 48.** `PG_BYPASS_MAX_INFLIGHT=14` becomes the slate value in
  `run_gate_b.py:1492-1495` (currently `"20"`; history: 48 blew the container PID cap → 16 in commit
  `abb39195` → 20). 14 is the operator-locked ceiling for the AccessBypass concurrent-fetch pool
  (`access_bypass.py:319`, read at call time). Rationale from the audit: concurrency-overload
  timeouts at 48 were ENVIRONMENT-induced and, under the per-URL cap-2 negative cache
  (`live_retriever.py:372-425`, `PG_REFETCH_PER_URL_CAP`), became PERMANENT losses for the run.
- **Paid-tail retry on the last ~8%.** After the main S1 fetch pass completes, the residual
  failed/timeout/shell URLs (empirically ~8% of the corpus at parallel-14; parallel-8 recovered
  ~52% of the parallel-48 failures per the audit) get ONE structured second pass INSIDE S1, before
  `cp1_fetch_snapshot.json` is written and before the fetch-yield gate evaluates:
  - concurrency `PG_FETCH_TAIL_CONCURRENCY=8` (the empirically-validated recovery parallelism —
    the `run_fetch_921.sh:15-24` back-off pattern, now wired into the pipeline instead of living
    only as a VM diagnostic);
  - routed PAID-lane-first: Zyte first for the tail (`PG_ZYTE_PAYWALL_FIRST` leg,
    `access_bypass.py:4796-4814`, scoped to the tail set), falling through the normal cascade —
    reusing the `resume_refetch.py` repopulate-the-`direct_quote` machinery so a recovered row is
    re-grounded and de-flagged, and a still-dead row stays disclosed-degraded, never fabricated;
  - overload-timeouts counted SEPARATELY from real failures so the tail pass does not burn the
    cap-2 per-URL budget (the audit's fix #4);
  - flags (LAW VI, all env-config): `PG_FETCH_TAIL_RETRY=1`, `PG_FETCH_TAIL_CONCURRENCY=8`,
    `PG_FETCH_TAIL_PAID_FIRST=1`.
  Because the tail retry runs BEFORE cp1 is written, every downstream section and every resume sees
  only the post-recovery corpus; `fetch_snapshot.json` needs no schema change. The fetch-yield HARD
  gate (`PG_MIN_FETCH_YIELD`, `live_retriever.py:1974-2089`) then scores the honest post-tail yield.

---

## 6. Composition from locked sections (how Designs 1-5 plug in)

Each sister design's fixed component IS a section under this architecture, locked behind its two
checkpoints: the fetch harness + tail retry → S1 (cp0→cp1); off-topic judge dual-anchor fix → S2
(cp1→cp2); dedup/basket loop (`.codex/I-dedup-loop-001/fable_dedup_basket_loop_design.md`) → S3
(cp2→cp3); outline-from-baskets + refine → S4 (cp3→cp4); holistic review + deliverable-aware compose
→ S5/S7; requirement intake → S0. A section can be swapped, re-baked, or bake-off'd in ISOLATION by
feeding it a banked upstream checkpoint and diffing its output checkpoint — no full-pipeline run
needed. The pipeline composes as `S0 ∘ S1 ∘ ... ∘ S7` where every `∘` is a validated checkpoint file
on disk. MAX PARALLELISM is per-section and unchanged by this design: queries parallelize as
independent run_dirs/processes with independent chains (per-query crash isolation already exists —
crash sidecar `run_gate_b.py:6580-6595`; the sequential loop at `:6587` lifts to N processes on the
128-core box); intra-section LLM stages keep their 32-64-concurrent slate knobs
(`PG_PARALLEL_VERIFY`, `PG_CREDIBILITY_PASS_MAX_INFLIGHT=20`, `run_gate_b.py:1180`); fetch is
LOCKED at 14 (§5); D8 4-role runs its roles concurrently as today.

---

## 7. SELF-CONTAINED SECTION spec for THIS component (the checkpoint/resume layer itself)

**(a) Fast isolation hamster loop** — `scripts/checkpoint_resume_harness.py` (offline, minutes):
- Input: a BANKED real run_dir (the drb_72 artifacts already on disk hold real
  fetch/corpus/postgen/postverify snapshots — no new spend).
- Matrix, run CONCURRENTLY (ThreadPool, one case per entry checkpoint × adjustment class):
  for each cpN — (1) simulate a kill by copying the run_dir truncated after cpN; (2) run the resume
  resolver; (3) assert it selects cpN, validates the hash-chain, refuses tampered/verdict-smuggled
  payloads (mutate a copy to prove fail-loud), rejects invalid adjustment/entry pairs; (4) for
  cheap stages (S2 selection, S3 consolidation offline parts, render) actually re-run and diff the
  regenerated checkpoint against the banked one (byte-determinism proof). LLM-stage re-entries
  smoke via `--smoke-scale` (`run_gate_b.py:4239-4365`, `_SMOKE_SCALE_OVERRIDES:4168`) on ONE query.
- Loop: quick test → read EVERY line of the resume log (forensic, §-1.4) → Fable investigates the
  divergence → Opus builds the fix → concurrent retest. Cycle time: seconds offline, ~minutes for a
  smoke re-entry.

**(b) Lock-down acceptance bar** — ALL must hold before the section is LOCKED:
1. Kill/resume matrix GREEN: for every cpN, a resumed run completes and `checkpoint_index.json`
   hash-chain validates end-to-end.
2. Upstream-skip proof: resumed run's cost ledger (`logs/pg_cost_ledger.jsonl`) shows ZERO
   search/fetch/generator billing for stages ≤ N (per entry point's skip table §4.4).
3. Gate re-run proof: resumed run_log contains the strict_verify / NLI / fetch-yield /
   `[activation]` D8 markers for every stage > N — verdicts recomputed, never replayed.
4. Verdict-smuggling RED test: a checkpoint with any `_A12_FORBIDDEN_VERDICT_KEYS` member at any
   depth is REFUSED (existing guard `:6936-6974` extended to all 8 files).
5. Adjustment-scoping proof: a cp4 tone adjustment changes prose downstream while cp1-cp3 sha256s
   are UNCHANGED; a cp4 scope-adjustment attempt is REJECTED with the correct earlier entry named.
6. Determinism proof: the same section re-run twice on the banked upstream produces byte-identical
   checkpoints for the deterministic stages (S2 selection given fixed embeddings, render).
7. §-1.1 line-by-line audit of one full resumed report vs cited spans — claim-by-claim, no
   metadata shortcut.
8. Full-run parity: one fresh full run and one cp2-resumed run on the same question produce reports
   whose verified-claim sets are equivalent under the frozen faithfulness engine.

**(c) Checkpoint at the component's own boundary:** this component IS the boundary layer; its own
input contract is the run_dir + `checkpoint_index.json`, its output contract is the resumed run's
fresh checkpoints + the supersession record. It is trivially resumable from itself: a crash mid-
resume leaves the index consistent (writes are atomic and append-ordered), and the next resume
lands on the new nearest checkpoint.

---

## 8. Build order for Opus (surgical, each PR ≤200 LOC, §-1.2 issue-first)

1. `checkpoint_envelope.py` (shared envelope: save/load, hash-chain, recursive verdict guard,
   flag-slate assert) + migrate cp1/cp2 writers to emit envelope fields additively (schema_version
   bump; old snapshots still load via legacy branch, fail-loud on ambiguity). + `checkpoint_index.json`.
2. S1 LOCKED fetch: slate `PG_BYPASS_MAX_INFLIGHT` 20→14 + the paid-tail retry pass (reuse
   `resume_refetch` cascade; new flags §5) + separate overload-timeout accounting.
3. cp3 basket + cp4 outline checkpoints (writers at the S3/S4 seams; loaders in the resume ladder).
4. Land ITEM 5a: the generator-side cached-draft re-entry hook (`run_honest_sweep_r3.py:8740-8790`
   already validates + reconstructs; the missing piece is the multi_section_generator entry that
   consumes `reused_outline` + raw drafts) → makes cp5 a real skip point; then wire cp6 re-entry.
5. `--resume-from` + `--adjust` + validity matrix + supersession + manifest disclosure in
   `run_gate_b.py` / `run_one_query`.
6. `scripts/checkpoint_resume_harness.py` + offline oracle tests (`tests/harness/`, no production
   predicate imports — I-wire-013 independence lesson).
7. S0 intake-spec checkpoint (lands with Design 5's deliverable-spec extractor; cp0 is just the
   envelope around its output).

Dual gate per PR: real Codex CLI + real Fable 5, both APPROVE (standing rule 2026-07-04).
