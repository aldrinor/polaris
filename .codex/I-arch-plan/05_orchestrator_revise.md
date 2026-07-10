# DESIGN 5 — Stronger orchestrator: basket-digest outline + requirement-aware planning + outline revision

Author: Fable 5 (architect). Date: 2026-07-10. Branch: `bot/I-deepfix-relaunch` (HEAD 0bde6438).
Audit anchor: `.codex/I-arch-audit/fable_orchestration_audit.md` stage 5 ("PARTIAL — content-aware but one-shot and title-starved"), ranked gap #3, gap #5 (deliverable-blind), gap #6 (baskets never meet sections).
Every claim below cites real code on this branch.

---

## 1. What is broken today (grounded)

The outline planner is real and content-aware, but it is starved, blind to requirements, and fires once.

1. **Title-starved menu.** `_call_outline` (`src/polaris_graph/generator/multi_section_generator.py:2547`) serializes the evidence menu two ways. Small pool: ev_id + tier + 120-char title + 160-char statement (`:2613-2628`). Large pool (the production case — hundreds of rows): the digest is TERSED to ev_id + tier + title only; the statement is dropped (`:2649-2659`, rationale at `:756-760`). Under the redesign flag the terse menu covers the full pool with no row cap (`:2607`, `:2648`), but it is still titles. The planner assigns `ev_ids` to sections while never seeing what the rows actually SAY.
2. **One shot, no revision.** One LLM call + one validation retry (`retry_on_invalid` capped at 1, `:2553-2559`) + deterministic fallback (`_build_archetype_fallback_outline`, `:2507-2544`). After sections come back — some thin, some dropped by the `min_kept_fraction=0.5` gate (`:8867`), some baskets never cited — nothing revisits the plan. Sections are composed concurrently under a semaphore (`max_parallel_sections`, `:8868`; `_section_concurrency`, `:9769-9777`; slate sets 6 via `PG_MAX_PARALLEL_SECTIONS`/`PG_PARALLEL_SECTIONS`, `scripts/dr_benchmark/run_gate_b.py:1490-1491`) and concatenated.
3. **Requirement-blind.** The prompt's SCOPE constraints are parsed and flowed (`intake_constraint_extractor.py:1-24`; ON via `run_gate_b.py:619` + `:5831`), but tone / structure / audience / reference-style / length asks are parsed NOWHERE (audit §RA(b)). The outline runs a fixed template: clinical 8-title allow-list (`multi_section_generator.py:784-793`), generic 6-title (`:800-807`), or the emergent facet prompt (`OUTLINE_SYSTEM_PROMPT_FACET`, `:1454-1478`; production non-clinical, `PG_FACET_OUTLINE=1`, `run_gate_b.py:1288`). A user who asks "give me exactly these five sections, written for a hospital formulary committee" is ignored.
4. **Baskets never reach the planner.** `dedup_by_finding` runs BEFORE the generator call (`scripts/run_honest_sweep_r3.py:14650-14697` vs the `generate_multi_section_report` call at `:15169`) and produces clusters with `finding_key`, `corroboration_count`, `member_hosts` (`:14689-14696`). Claim baskets exist in `synthesis/credibility_pass.py` (HOP-A consume-finding-dedup, `:51-77`). Both are thrown away for planning: the outline sees raw-row titles, not consolidated claims.
5. **A revision-loop precedent already exists in pipeline B.** `graph_v3.py` routes outline → gap_check → gap_search (bounded `PG_V3_MAX_GAP_SEARCHES=2`, `graph_v3.py:34-57`). The concept is proven in-tree; it was never ported to the production sweep.

## 2. Design goals and binding constraints

- **§-1.3 weight-and-consolidate.** The richer menu compresses by CONSOLIDATION (baskets), never by dropping rows. Revision regroups sections; it never deletes evidence. No caps, no targets, no thinners.
- **Faithfulness engine untouched.** The orchestrator changes PLANS only. Every recomposed section runs the full existing per-sentence pipeline (strict_verify → NLI → 4-role D8). Kept sections keep their already-verified text byte-identical.
- **MAX PARALLELISM, deterministic.** Sections compose concurrently in waves (32-64 in-flight is an env raise of the existing semaphore, `run_gate_b.py:1490-1491`); the reviser is ONE call at a deterministic wave barrier; the recompose wave is concurrent again. Merge order stays the original `plans` order (the existing merge contract, `run_gate_b.py:1478-1480` comment).
- **Crash-resilient.** DATA-ONLY checkpoints at the orchestrator's input and output boundaries, following the A12 pattern (`run_honest_sweep_r3.py:6858-6974`) and the storm-outline checkpoint precedent (`:6989-7103`, wired `:9165`, `:10118`).
- **REQUIREMENT-AWARE, not hardcoded.** The user's deliverable asks (structure/tone/audience/reference style/length) are parsed once at intake and THREADED into the planner and the reviser. A user-specified structure WINS over facet emergence; evidence decides only what each requested section can honestly contain.

## 3. Architecture — four components

```
                    ┌────────────────────────────────────────────────┐
                    │  CHECKPOINT: outline_input.json (input boundary)│
                    └────────────────────────────────────────────────┘
 evidence_for_gen ──► ORCH-1 basket-digest menu ─┐
 finding_dedup clusters ─────────────────────────┤
 scope constraints (existing) ───────────────────┼──► ORCH-2 outline call (requirement-aware)
 deliverable spec (NEW parse) ───────────────────┘         │  checkpoint: outline_plan.json
                                                           ▼
                                   WAVE-1: compose ALL sections concurrently (existing path)
                                                           │  per-section outcome digest (pure code)
                                                           ▼
                                   ORCH-3 reviser (1 LLM call, bounded rounds)
                                     keep / merge / split / retitle / reassign / add
                                     optional ORCH-4 gap queries (bounded, default 0)
                                                           │
                                   WAVE-2: recompose ONLY changed sections concurrently
                                     (full strict_verify + all gates re-run on changed text)
                                                           ▼
                    ┌────────────────────────────────────────────────┐
                    │ CHECKPOINT: outline_final.json (output boundary)│
                    └────────────────────────────────────────────────┘
```

### ORCH-1 — Basket-digest evidence menu (fixes title starvation)

New pure module `src/polaris_graph/generator/outline_digest.py` (one responsibility, no LLM, no network):

```python
@dataclass
class OutlineDigestMenu:
    basket_lines: list[str]      # one line per finding_dedup cluster
    singleton_lines: list[str]   # one line per row in no multi-member cluster
    ev_id_to_basket: dict[str, str]
    total_chars: int

def build_outline_digest(
    evidence: list[dict], clusters: list[FindingCluster],
) -> OutlineDigestMenu: ...
```

- **Basket line** (the new content layer): `B07 [x4 sources: T1,T1,T2,T6] claim: "tirzepatide 15mg reduced HbA1c -2.1% vs placebo at 40w" members: ev_012,ev_044,ev_101,ev_180`. The claim text is the cluster representative's statement (the row `finding_dedup` keeps, `synthesis/finding_dedup.py:1-16`), ~200 chars. Corroboration and tier mix come free from the cluster (`corroboration_count`, `member_hosts` — `run_honest_sweep_r3.py:14689-14696`).
- **Singleton line**: `ev_203 [T4] | title: <120c> | <120c statement>` — the small-pool format (`multi_section_generator.py:2613-2628`) applied to singletons only.
- **Consolidation IS the compression.** A 787-row pool collapses to ~99 clusters (`synthesis/credibility_pass.py:56-58` measured) + singletons. The planner now reads CLAIM CONTENT for every consolidated finding at FEWER tokens than 150 bare titles, and the menu covers the FULL pool (every row is either in a basket line's members or a singleton line — zero rows dropped, §-1.3-clean).
- **Headroom guard stays.** The existing reasoning-first budget protections are reused unchanged (`PG_OUTLINE_MIN_MAX_TOKENS=16384` content + `PG_OUTLINE_REASONING_MAX_TOKENS=6144`, `multi_section_generator.py:2691-2696`). If the digest exceeds a char budget (`PG_OUTLINE_DIGEST_MAX_CHARS`, default 60000), singleton lines terse to title-only FIRST (statement dropped, row kept), then basket member lists elide to counts — content degrades gracefully; no row ever leaves the menu.
- **Wiring.** The sweep already holds `_dedup.clusters` before the generator call (`run_honest_sweep_r3.py:14662`); thread it as a new kwarg `finding_clusters` on `generate_multi_section_report` (precedent: the `credibility_pass_judge` kwarg, `multi_section_generator.py:8855`). Inside `_call_outline`, flag `PG_OUTLINE_BASKET_DIGEST=1` selects the digest menu; OFF is byte-identical to today's small/large-pool split.
- **Bonus: closes audit gap #6 at the plan level.** Because the planner assigns BASKETS (whose members are known), each section plan now carries `basket_ids` alongside `ev_ids` — the section composer can be handed its section-scoped baskets in a later design without re-deriving membership.

### ORCH-2 — Requirement-aware outline call (fixes deliverable blindness at the planning seam)

1. **Parse a DeliverableSpec at intake.** Extend `src/polaris_graph/retrieval/intake_constraint_extractor.py` (the proven extraction pattern, `:1-24`) with a second dataclass:

```python
@dataclass
class DeliverableSpec:
    required_sections: list[str]   # explicit user-ordered headings, [] = none
    audience: str                  # "" = unspecified
    tone: str                      # "" = unspecified
    reference_style: str           # "" = unspecified (renderer consumes later; carried now)
    length_target: str             # verbatim user phrase, "" = none; NEVER a truncation gate
    raw_spans: list[str]           # the exact prompt spans each field came from (audit trail)
```

    Deterministic regex primary + the same injected-LLM fallback the scope extractor uses. Flag `PG_EXTRACT_DELIVERABLE_SPEC` (default OFF; slate ON). Extracted in `nodes/scope_gate.py` next to the existing constraint extraction (`scope_gate.py:1010-1059` per audit §RA(a)) and threaded through the protocol like `user_constraints`.
2. **REQUIREMENTS block in the outline prompt.** `_call_outline` appends a block to the user prompt (never the system prompt, so injection-stripped question handling is unchanged):
   - If `required_sections` is non-empty: "The user REQUIRES this section structure, in this order: [...]. Map the evidence facets INTO these sections. Do not invent sections outside this list. If a required section has no supporting evidence, still emit it with `ev_ids: []` and set `"undersupplied": true` — the pipeline will disclose the gap, never fake content." Requirement wins over facet emergence; evidence honesty is preserved because an undersupplied section renders as a disclosed gap, and strict_verify makes fabrication impossible downstream.
   - Audience/tone are passed to the planner as CONTEXT for focus-sentence wording and section granularity (an executive summary audience gets fewer, broader sections; a formulary committee gets finer clinical splits). The per-sentence compose prompt is out of scope here (that is the compose-side design's seam); the spec object is carried on `MultiSectionResult` so the compose/render designs can consume it without a second parse.
3. **Scope constraints join the same block.** The already-parsed date window / geography / source-type constraints (audit §RA(a)) are stated to the planner ("evidence outside 2020-2024 is weight-demoted; prefer in-window baskets when choosing section anchors") — one line each, read from the protocol fields that already exist.
4. **Clinical safety unchanged.** `domain in ("", "clinical")` keeps the proven fixed 8-title path byte-identical (`_allowed_sections_for_domain`, `:810-817`) unless the user EXPLICITLY supplies `required_sections` — an explicit user structure is a Session-Instruction-level requirement (APD precedence) and applies to clinical too, with the undersupplied-disclosure rule guarding safety.

### ORCH-3 — Outline revision after sections return (fixes one-shot)

**Wave barrier, not streaming.** All planned sections compose concurrently exactly as today (semaphore path `:9769-9777`). When the wave completes, the orchestrator builds a deterministic per-section OUTCOME DIGEST from telemetry that already exists — pure code, no LLM:

```python
@dataclass
class SectionOutcome:
    title: str
    verified_sentence_count: int      # from per-section verify results
    kept_fraction: float              # the min_kept_fraction input (:8867)
    dropped: bool                     # section failed regen and was dropped
    unused_ev_ids: list[str]          # assigned but never cited in verified prose
    uncovered_baskets: list[str]      # corroboration>=2 baskets assigned here, zero verified sentences
    undersupplied: bool               # ORCH-2 flag carried through
```

Plus a report-level list: `orphan_baskets` — multi-source baskets (corroboration_count >= 2) assigned to NO section anywhere.

**One reviser LLM call** (`_call_outline_revise`, same model/temperature/token discipline as `_call_outline`, tagged `call_type="outline_revise"` via `set_reasoning_call_context`, precedent `:2698-2701`). Input: the accepted outline, the outcome digests, the SAME basket-digest menu, the REQUIREMENTS block. Output schema (parsed with the `_parse_outline`-style structured validator, `OutlineParseResult` precedent `:1363-1372`):

```json
{"ops": [
  {"op": "keep",    "title": "..."},
  {"op": "merge",   "titles": ["A","B"], "new_title": "...", "reason": "..."},
  {"op": "split",   "title": "...", "into": [{"title":"...","ev_ids":[...]},{...}], "reason": "..."},
  {"op": "retitle", "title": "...", "new_title": "...", "reason": "..."},
  {"op": "reassign","title": "...", "add_ev_ids": [...], "drop_ev_ids": [...], "reason": "..."},
  {"op": "add",     "title": "...", "focus": "...", "ev_ids": [...], "reason": "..."}
 ],
 "gap_queries": ["..."],
 "revision_needed": true}
```

**Apply rules (the hard part, deterministic pure code):**
- `keep` → the section's VERIFIED text is reused byte-identical. No re-verify, no cost, no drift.
- `merge` → recompose ONE new section from the UNION of the two ev_id sets. Never text-glue: gluing verified prose would create transition sentences with no provenance token. Recompose runs the full existing section pipeline.
- `split` / `retitle` / `reassign` / `add` → recompose the affected sections only. `reassign.drop_ev_ids` removes rows from a SECTION's assignment only — the rows stay in the pool, other sections, and the bibliography (§-1.3: reassignment, never deletion).
- Every ev_id validated against the full pool (`allowed_ev_ids` discipline, `:2668-2673`); an op referencing an unknown id is rejected with a reason code; a wholly-invalid response falls back to the wave-1 outline (fail-open to the existing good result — the reviser can only improve or no-op, never lose a report).
- Recomposition wave: all changed sections concurrent under the same semaphore. Final assembly in plan order.
- **Bounds:** `PG_OUTLINE_REVISE_ROUNDS` default 1, hard max 2. A round whose ops are all `keep` (or that fails parse) ends the loop. Guard: total recomposed sections per round <= `PG_OUTLINE_REVISE_MAX_RECOMPOSE` (default 8) — a compute-safety ceiling in the spirit of `_FACET_OUTLINE_MAX_SECTIONS_DEFAULT=40` (`:839`), not a quality target; overflow keeps the highest-impact ops (dropped/undersupplied sections first) and logs the rest as disclosed no-ops.
- **Boundary with the holistic prose reviewer (audit gap #1 / `synthesis/cross_section_reflector.py:23-50`):** ORCH-3 is STRUCTURAL — it merges/splits/reassigns sections and never edits sentence text. The prose-level whole-report review (tone smoothing, cross-section contradiction hedging in composed prose) is a separate design at the post-assembly seam. The two do not collide: ORCH-3 finishes before assembly; the reflector-style pass runs after.

### ORCH-4 — Bounded gap re-retrieval (optional, ships OFF)

When a REQUIRED (user-specified) section is undersupplied, or an outcome digest shows a facet with zero usable evidence, the reviser may emit `gap_queries`. These route through the EXISTING per-query retrieval lane — the same `per_query_retrieve` the FS-Researcher sub-queries use (`src/polaris_graph/retrieval/fs_researcher_query_gen.py:110`) — so new rows get the full tier-classify / topic-judge / junk-gate / dedup treatment automatically. Bounds: `PG_OUTLINE_GAP_QUERIES` (default 0 = OFF; slate may set 4), ONE round only, and gap retrieval happens between wave-1 and the recompose wave. Precedent: pipeline B's outline gap loop (`graph_v3.py:34-57`, capped 2). Ships OFF so the first production activation isolates ORCH-1/2/3 behavior; ORCH-4 is a follow-on activation once the loop is proven.

## 4. Checkpoints — the self-contained-section boundary

All checkpoints follow the A12 DATA-ONLY contract: no verdict keys, fail-loud loader (`load_a12_checkpoint` forbidden-key check, `run_honest_sweep_r3.py:6936-6974`), schema-versioned allow-list projection (storm-outline precedent `:6989-7002`).

| Checkpoint | Boundary | Contents | Resume semantics |
|---|---|---|---|
| `outline_input.json` | INPUT — everything the orchestrator consumes | digest menu (basket + singleton lines), DeliverableSpec, scope-constraint block, `evidence_id_hash` (`_a12_hash` pattern `:6879`) | evidence hash matches → skip digest rebuild; mismatch → rebuild (fail loud on silent corpus drift) |
| `outline_plan.json` | after wave-1 outline accepted | plans (title/focus/ev_ids/basket_ids/archetype), reason codes, raw LLM output | resume re-enters at section compose with the accepted plan; raw output kept for deterministic replay of the APPLY step |
| `outline_final.json` | OUTPUT — the orchestrator's product | final plans + full revision audit trail (every op, reason, round; rejected ops with reason codes) | resume re-enters at assembly; kept sections reload raw drafts from the EXISTING A12 postgen checkpoint (`write_postgen_checkpoint` `:6858`) and RE-RUN every faithfulness gate (never replay a verdict) |

The pipeline can therefore resume from: before planning, after planning, or after revision — the orchestrator is a resumable segment with hard, hash-guarded input/output edges. Checkpoint writes are best-effort (never abort a paid run, `:6871`, `:6892`); loads are fail-loud.

## 5. Parallelism and determinism

- Digest build: pure CPU over in-memory rows — negligible.
- Outline: 1 call. Reviser: 1 call per round (max 2). Serial cost added to the run ≈ 2-3 planner-class calls.
- Section waves: existing semaphore; the slate raises `PG_MAX_PARALLEL_SECTIONS` / `PG_PARALLEL_SECTIONS` (`run_gate_b.py:1490-1491`) from 6 toward 32 as provider rate limits allow — an env change, no code. Recompose wave reuses it.
- Determinism contract: everything AROUND the LLM calls is deterministic — digest line order (sorted by basket id then ev_id), outcome digests (pure function of section results), op application (stable order: merges, splits, retitles, reassigns, adds; ties broken by plan index), final merge in plan order. Raw LLM outputs are persisted in the checkpoints so any run is replayable byte-for-byte through the apply step. LLM sampling itself is the only nondeterministic element, exactly as for today's single outline call.

## 6. Flags (LAW VI — all env, all read at call time, all default-safe)

| Flag | Default | Slate | Meaning |
|---|---|---|---|
| `PG_OUTLINE_BASKET_DIGEST` | 0 | 1 | ORCH-1 menu (OFF = today's menu byte-identical) |
| `PG_OUTLINE_DIGEST_MAX_CHARS` | 60000 | — | graceful-terse threshold, never a row drop |
| `PG_EXTRACT_DELIVERABLE_SPEC` | 0 | 1 | ORCH-2 intake parse |
| `PG_OUTLINE_REVISE` | 0 | 1 | ORCH-3 loop |
| `PG_OUTLINE_REVISE_ROUNDS` | 1 | 1 | hard max 2 |
| `PG_OUTLINE_REVISE_MAX_RECOMPOSE` | 8 | — | compute-safety ceiling, not a target |
| `PG_OUTLINE_GAP_QUERIES` | 0 | 0 (first ship) | ORCH-4 bounded re-retrieval |

Slate activation uses the run_gate_b force-exact frozenset pattern (`run_gate_b.py:1509-1527`) so a stray operator env cannot silently downgrade a paid run.

## 7. What is NOT touched

- `strict_verify`, provenance tokens, NLI entailment, 4-role D8, `report_redactor` — zero diff (acceptance bar checks the git paths).
- Clinical fixed-title path with flags OFF: byte-identical (`:784-793`, `:810-817`).
- `_build_archetype_fallback_outline` and the M-31 lenient parse chain: unchanged; the reviser's failure mode is "keep wave-1 outline", wave-1's failure mode is the existing fallback chain.
- `finding_dedup` / `credibility_pass` computation: consumed, not modified.

## 8. Fast isolation hamster loop (requirement a)

Lab harness: `scripts/orchestrator_lab/outline_lab.py` — runs the orchestrator segment ALONE on a banked REAL run directory (LAW II: real fetched rows only; no mocks outside tests/fixtures/).

- **Inputs:** a finished run dir (e.g. the drb_72 outputs) supplies `corpus_snapshot` evidence rows, `manifest['finding_dedup']` clusters (`run_honest_sweep_r3.py:14675-14697`), and A12 postgen raw drafts (`post_generation` checkpoint `:6858-6893`) for the revise mode.
- **Mode `plan`:** build digest → real outline call → print the outline + a coverage table (every basket → assigned section or ORPHAN). One LLM call; runs in under a minute.
- **Mode `revise`:** compute outcome digests from the banked drafts + verification details (postverify checkpoint `:6896`) → real reviser call → print the op list + the would-be recompose set. One LLM call; no section recomposition cost in the lab.
- **Mode `apply-dry`:** deterministic apply step on a RECORDED reviser output (from the checkpoint) — zero LLM, pure code, milliseconds; this is where apply-logic bugs are hunted.
- **The loop:** run a mode → READ EVERY LINE of the produced outline/ops (forensic content read, not a status check — memory 2026-07-01) → Fable investigates any defect → Opus patches → rerun. Multiple banked run dirs (one per domain: clinical, workforce, policy) run CONCURRENTLY since the lab is per-directory isolated. Offline unit tests for parser + apply live in `tests/polaris_graph/` with fixtures under `tests/fixtures/` (the one allowed mock location).

## 9. Lock-down acceptance bar (requirement b)

The section is DONE when all of these hold, none waived:

1. **Structural:** on 3 banked corpora (clinical + 2 non-clinical) × 3 runs each: outline JSON valid, every ev_id in pool, every basket_id resolvable, zero parse fallbacks.
2. **Menu honesty:** the serialized menu accounts for 100% of pool rows (basket member or singleton line) — asserted by the lab, every run.
3. **Coverage:** every cluster with `corroboration_count >= 3` is assigned to ≥1 section OR listed in the plan artifact's disclosed `orphan_baskets` with a reason. Silent orphaning = FAIL.
4. **Requirement firing (behavioral, in rendered output):** a prompt carrying an explicit user structure produces `report.md` headings that match that structure, order included; an undersupplied required section renders as a disclosed gap. Acceptance = fires in the RENDERED report, not "flag set" (wiring standard, memory 2026-06-24).
5. **Revision firing:** on a banked run with a known dropped/thin section, the reviser emits ≥1 non-keep op; the recomposed report passes every existing gate; every `keep` section's text is byte-identical (hash compare).
6. **Faithfulness untouched:** `git diff` contains zero changes under the faithfulness-engine paths (strict_verify / entailment / roles/); every recomposed sentence carries valid provenance tokens (existing verify telemetry asserts this for free).
7. **Determinism of code path:** replaying recorded LLM outputs through `apply-dry` twice yields identical final plans, and checkpoint hashes match.
8. **§-1.1 line-by-line audit** of ONE full revised report (claim-by-claim vs cited spans) with zero FABRICATED and zero regression vs the same corpus un-revised.
9. **Clinical byte-identity:** flags OFF → clinical benchmark output unchanged (existing test-suite + one banked-corpus replay).

## 10. Build order for Opus (each its own PR, smallest first)

1. `outline_digest.py` + `finding_clusters` kwarg threading + unit tests (ORCH-1; smallest, immediately testable in the lab `plan` mode).
2. `DeliverableSpec` extraction + REQUIREMENTS block in `_call_outline` (ORCH-2).
3. Checkpoints `outline_input/plan/final` + resume wiring (the segment boundary; follows the storm-outline checkpoint recipe end-to-end).
4. Outcome digests + `_call_outline_revise` + parse + deterministic apply + recompose wave (ORCH-3; the largest — split parse/apply and wave-wiring into two PRs if the 200-LOC discipline demands).
5. Lab harness `outline_lab.py` + acceptance run against banked corpora.
6. (Follow-on activation) ORCH-4 gap queries, only after 1-5 hold the acceptance bar in a real run.

Every PR flows the standing dual gate (Codex CLI + Fable 5 both APPROVE) per the Claude Codex Workflow.
