# DESIGN 1 — Off-topic judge becomes SUB-QUERY-AWARE

Author: FABLE 5 (architect brain). Date: 2026-07-10. Branch: `bot/I-deepfix-relaunch` (HEAD 0bde6438).
Grounding: audit `.codex/I-arch-audit/fable_orchestration_audit.md` stage 4 + ranked gap #2. All file:line cites below are from the real tree on this branch.

---

## 1. The problem, in one paragraph

The topic judge compares every source against ONLY the main research question. The prompt embeds one anchor: `RESEARCH QUESTION` (`src/polaris_graph/retrieval/topic_relevance_gate.py:335`), and the orchestrator calls it with the main `q["question"]` (`scripts/run_honest_sweep_r3.py:13329-13335`). But production retrieval is per-SUB-query: FS-Researcher issues each sub-query as its own retrieval (`src/polaris_graph/retrieval/fs_researcher_query_gen.py:110,165,969`), and every candidate is stamped with the search query that surfaced it (`query_origin`, `src/polaris_graph/retrieval/live_retriever.py:5800,5827,5869,5917`; carried onto the evidence row at `:7588,7872`). The judge never sees that sub-query — it is read ONLY for anchor exemption (`topic_relevance_gate.py:253-257`). So a source that legitimately serves a sub-query, but whose subject entity differs from the main question's, reads OFF_SUBJECT → it is weight-sunk AND hard-deleted by the junk-deletion gate (`src/polaris_graph/generator/junk_deletion_gate.py:139-203,247-256`; seam `run_honest_sweep_r3.py:14988-14994`). The fetch-side embedding filter already anchors on the per-retrieval question — which in the FS lane IS the sub-query (`src/polaris_graph/retrieval/prefetch_offtopic_filter.py:19-24`) — so today fetch-side and selection-side use INCONSISTENT anchors. This design makes them consistent.

**The rule this design implements (operator directive):** a source is ON if it is on-topic to EITHER its own sub-query OR the main question. It is OFF only when it is off BOTH. Delete stays reserved for OFF_SUBJECT-against-BOTH.

---

## 2. Provenance map — where the sub-query is born and where it dies today

| Step | Where | What exists |
|---|---|---|
| Sub-query created | `fs_researcher_query_gen.py` todo-queue; each todo → one query | The sub-query string `q` |
| Retrieval per sub-query | `per_query_retrieve(research_question=q, ...)` (`fs_researcher_query_gen.py:110,165,969`) | The retriever's WHOLE call is anchored on the sub-query |
| Candidate stamped | `SearchCandidate.query_origin = q` (`live_retriever.py:5800,5827,5868-5869,5916-5917`) | The retriever-level search query (derived from — often equal to — the sub-query) |
| Non-query labels | `query_origin = "need_type_backend"` (`:5986-5995`), `"domain_backend"` (`:6037-6048`), `seed_query_origin="primary_trial_doi_seed"` (`:5413,5754`), required-entity origins (`required_entity_retrieval.py:556,967`) | **CAUTION:** `query_origin` is sometimes a provenance LABEL, not a natural-language query |
| Evidence row | `"query_origin": getattr(cand, "query_origin", "")` (`live_retriever.py:7588,7872`) | The field survives onto the row dict, into selection, into `evidence_for_gen`, into `corpus_snapshot` |
| Selection reads it | `_row_query_origin` (`evidence_selector.py:1273-1275`) for the per-sub-query reserve | Precedent accessor to mirror |
| Topic judge | `classify_topic_relevance(evidence_for_gen, q["question"], ...)` (`run_honest_sweep_r3.py:13329-13335`) | **The provenance dies here.** Judge sees title+snippet+MAIN question only (`topic_relevance_gate.py:382-391`) |

Two gaps: (a) the judge never reads the field; (b) the field is the retriever's search query, not always the FS sub-query itself, and is sometimes a label.

---

## 3. The design

### D1 — Stamp the true sub-query on every row (`retrieval_subquery`)

At the three places FS-Researcher receives a per-sub-query result, stamp the sub-query verbatim on each returned evidence row:

- serial loop: after `result = per_query_retrieve(research_question=q, ...)` (`fs_researcher_query_gen.py:110-112`) → `row["retrieval_subquery"] = q` for every row in `result.evidence_rows`;
- parallel fan-out: same stamp where each result folds in (`:176-180` and the pool-merge below it);
- expansion loop: same at `:969`.

Pure data plumbing. `merge_retrieval_results` (`:1003`) already carries rows through untouched, so the field survives the merge, selection, and the `corpus_snapshot` write (`run_honest_sweep_r3.py:15046`), which gives the resume path the anchor for free.

Why a NEW field instead of reusing `query_origin`: `query_origin` is the retriever-level search query (a derivative), is sometimes a label, and is load-bearing for the per-sub-query reserve (`evidence_selector.py:1273`) and marquee detection (`topic_relevance_gate.py:253-257`). Never overload a load-bearing field. `retrieval_subquery` is the clean, judge-facing anchor; `query_origin` becomes its fallback.

### D2 — Anchor derivation inside the gate

Add two pure helpers to `topic_relevance_gate.py` (mirroring the `_row_title_text` accessor pattern at `:215-225`):

- `_row_subquery_anchor(row) -> str` — precedence `retrieval_subquery` > `query_origin` > `""`. (`seed_query_origin` is deliberately EXCLUDED: seed rows are anchors and already gate-exempt at `:238-258`.)
- `_usable_subquery_anchor(text) -> bool` — True only for a real natural-language query. Rejects: empty; the known provenance labels (`need_type_backend`, `domain_backend`, `primary_trial_doi_seed`, anything containing `required_entity` or `anchor` — module constant tuple, LAW VI); and any string with fewer than `PG_TOPIC_SUBQ_MIN_TOKENS` (default 3) whitespace tokens. A label or junk anchor must degrade to today's main-question-only judging, never poison the prompt.

Rows whose anchor is unusable are judged exactly as today (main-question-only group). Zero caller signature change: the gate derives everything from the rows it already receives.

### D3 — Group by sub-query; one dual-anchor prompt per group

Inside `classify_topic_relevance` (`:481`), after the existing exempt/chrome partition (`:539-564`), partition `judged_rows` by their usable anchor (first-appearance order — deterministic). Each group is batched exactly as today (`topic_batch_size`, `:180-191`; loop `:606`). `_build_batch_prompt` (`:261`) gains an optional `subquery: str | None = None` parameter:

- `subquery=None` → byte-identical current prompt (the main-only group and the flag-OFF path both use this).
- `subquery` set → the prompt carries TWO anchor blocks — `MAIN RESEARCH QUESTION:` and `SUB-QUERY (this batch of sources was retrieved specifically to answer this):` — and STEP 1/STEP 2 change to: name the subject entity + aspect of BOTH anchors silently; a source is **ON if it plausibly bears on EITHER anchor** (its sub-query's subject+aspect OR the main question's); `OFF_ASPECT` = same subject entity as either anchor but the wrong aspect for BOTH; `OFF_SUBJECT` = a clearly different subject entity from BOTH anchors. The DATE-BLIND rule (`:369-373`), the fail-open instruction (`:375-376`), and the strict verdict-only output contract (`:300-305`) are kept verbatim — they are hard-won forensic fixes.

Grouping is the right unit (rather than a per-source-line sub-query note) because: the LLM gets ONE stable pair of anchors per call instead of N different rubrics interleaved with titles; parse stays the trivial `<index>: VERDICT` contract; and groups are the natural parallel dispatch unit (D7).

### D4 — Verdict set + parser extension (fail-open preserved)

Extend the split-mode verdict set to four tokens: `ON_MAIN`, `ON_SUBQUERY`, `OFF_ASPECT`, `OFF_SUBJECT`. `_parse_batch_verdicts_split` (`:433-478`) learns the two new tokens with the same normalization (`on_main`/`onmain`, `on_subquery`/`onsubquery`/`on_sub_query`); a plain `ON` still parses (maps to `ON_MAIN` — legacy-compat, same conservatism as plain `OFF` → `OFF_ASPECT` at `:471-474`). Everything else is unchanged: exactly one recognized verdict per requested index or the WHOLE batch fails open (`:476-477`); any LLM exception keeps the batch (`:620-625`). The fail-open contract in the module docstring (`:28-35`) is untouched.

### D5 — Keep semantics: ON via either anchor, disclosed

In the verdict loop (`:636-664`):

- `ON_MAIN` → exactly today's confident-ON path (rescue False-stamp, `:656-664`).
- `ON_SUBQUERY` → SAME keep path, PLUS a telemetry-only sidecar `row["topic_on_via_subquery"] = True` and a counter `n_on_via_subquery` on `TopicGateResult` (`:194-212`). This is the forensic number the acceptance bar keys on: how many sources the sub-query anchor rescued. It changes NO downstream behavior — `weighted_enrichment._is_confirmed_offtopic` and the junk gate never read it.
- `OFF_ASPECT` / `OFF_SUBJECT` → unchanged demote/sidecar paths (`:673-708`), including the stale-sidecar pop (`:704-708`).

### D6 — Delete semantics: untouched code, stricter meaning

`junk_deletion_gate.py` needs ZERO changes. `is_row_deletable_offtopic` (`:156-202`) already keys on the `topic_off_subject` stamp + fresh-verdict-only ids (`run_honest_sweep_r3.py:13345-13350,14993`). Because D3 redefines what earns `OFF_SUBJECT` — off-subject against BOTH anchors — the deletable class mechanically narrows to exactly the operator's rule. §-1.3.1 carve-out semantics hold: delete is still judge-verdict-only, fail-open, disclosed (`run_honest_sweep_r3.py:15025-15044`). The faithfulness engine (strict_verify / NLI / 4-role / provenance) is not touched anywhere in this design.

### D7 — MAX PARALLELISM: concurrent batch dispatch

Today the batch loop is SERIAL (`:606-664`) — on a 900-row corpus at batch 25 that is ~36 sequential LLM round-trips. Add `PG_SCOPE_TOPIC_PARALLEL` (default 1 = serial, byte-identical): when >1, dispatch all (group × batch) prompts through a bounded `ThreadPoolExecutor` (production slate: 32). This is safe because the production `_topic_llm` closure is already self-contained per call — it builds its own client, own event loop, own thread, and does context-safe cost write-back (`run_honest_sweep_r3.py:13262-13321`). Determinism: verdicts key to rows positionally inside each pre-built batch; kept order is computed once from the original `sources` order (`:677`); temperature is 0.0 (`:13297`). Same verdict map at parallel 1 and parallel 32; only wall-clock changes (minutes, not tens of minutes).

### D8 — Flags (kill-switch discipline)

- `PG_TOPIC_GATE_SUBQUERY_AWARE` — default **ON** (this is the fix; matches the convention of Fix 3/Fix 4 defaults at `:113-141`). OFF ⇒ no grouping, no new prompt text, no new verdict tokens, no sidecar — byte-identical to today's split-mode gate.
- `PG_TOPIC_SUBQ_MIN_TOKENS` — anchor-shape floor, default 3.
- `PG_SCOPE_TOPIC_PARALLEL` — default 1 (serial).
- All existing flags (`PG_SCOPE_TOPIC_GATE`, `_HARD_DROP`, `_SUBJECT_ASPECT_SPLIT`, `PG_RESUME_RUN_TOPIC_JUDGE`, `PG_JUNK_CHROME_BEFORE_OFFTOPIC`, `PG_SCOPE_TOPIC_MAX_TOKENS`) keep their exact meaning. Sub-query awareness composes with the split; with split OFF the dual-anchor rubric still applies to the two-verdict prompt (ON if either anchor; OFF only if both).

### D9 — Resume + legacy snapshots

Old `corpus_snapshot` rows have no `retrieval_subquery`; most carry `query_origin` (persisted since `live_retriever.py:7588`). Fallback order in D2 handles both: new runs use the verbatim sub-query; resumed old corpora use `query_origin` when it is a usable query; label-or-missing rows degrade to main-only. `PG_RESUME_RUN_TOPIC_JUDGE` re-judges (`run_honest_sweep_r3.py:13247-13253`) therefore get the dual anchor on resume too — this matters because the resume re-judge + rescue stamp (`topic_relevance_gate.py:656-664,680-685`) is exactly the mechanism that un-buries sources a previous main-only judge wrongly demoted.

---

## 4. SELF-CONTAINED SECTION — isolation loop, acceptance bar, checkpoint

### (a) Component boundary

- **INPUT:** `evidence_for_gen` rows (title/snippet + `retrieval_subquery`/`query_origin` provenance) + the main question + the LLM callable.
- **OUTPUT:** the same rows stamped (`topic_offtopic_demoted` / `topic_off_subject` / `topic_on_via_subquery`) + `TopicGateResult` telemetry + `_fresh_off_subject_ids` for the junk gate.

### (b) CHECKPOINT at the boundary (crash-resilient, incremental, resumable)

New optional kwarg `checkpoint_path: Path | None` on `classify_topic_relevance`, passed from the orchestrator as `run_dir / "topic_gate_verdicts.jsonl"` (same durable-seam pattern as `junk_deletion_disclosure.json`, `run_honest_sweep_r3.py:15032-15044`).

- **Incremental write:** as EACH batch's verdicts parse, append one JSONL record: `{evidence_id, verdict, anchor_kind: main|subquery, subquery, batch_idx}`. A crash mid-gate loses at most one in-flight batch.
- **Resume replay:** on entry, load the file; any row whose `evidence_id` already has a verdict is stamped from the record WITHOUT an LLM call; only unjudged rows go to the model. Guard: a header record pins `{main_question_sha, n_in, flag_state}` — mismatch ⇒ ignore the file and re-judge fresh (never replay verdicts from a different question or flag config).
- **Pipeline resume:** because verdict stamps also persist inside `corpus_snapshot`, the pipeline can resume AFTER the gate without re-running it (existing behavior), or resume AT the gate mid-way via the JSONL. Fail-open: any checkpoint read/write error ⇒ log + proceed as if no checkpoint (a checkpoint bug must never drop or invent a verdict).

### (c) Fast isolation hamster loop (quick test → read every line → Fable investigates → Opus builds → retest)

New harness `scripts/dr_benchmark/topic_gate_subquery_harness.py` (standalone CLI, LAW VII):

1. **Load** a real corpus: `--snapshot <corpus_snapshot.json>` from any past run (drb_72 first — it holds the known false OFF_SUBJECT deletions AND the known true junk), or `--fixture` for the offline stub-LLM tests.
2. **Run** `classify_topic_relevance` in isolation with the REAL production model + `PG_SCOPE_TOPIC_PARALLEL=32`. Fast subset: `--only N` rows or `--group "<subquery>"` for one group; full corpus is the same command without the flag. Target: full 900-row corpus in single-digit minutes; a `--only 50` iteration in <60 seconds.
3. **Read every line:** the harness prints one line per row — `evidence_id | verdict | anchor_kind | subquery[:60] | title[:80]` — plus the group table (per-sub-query ON/OFF_ASPECT/OFF_SUBJECT counts, n_on_via_subquery, fail-open batch count). §-1.1: the operator/Fable reads the verdict lines against the actual titles, claim-by-claim, not the counts.
4. **Fable investigates** every misverdict (wrong anchor picked, prompt confusion, parse fail-open) → names the exact defect → **Opus builds** the patch (prompt wording, label list, parser token) → **retest** the same snapshot. Iterations are cheap because the checkpoint replay skips already-correct groups (`--refresh-group` re-judges only the group under investigation).

### (d) Lock-down acceptance bar (all must pass before the section is closed)

1. **Byte-identical OFF:** full existing suite (`tests/polaris_graph/test_topic_gate_aspect_ff4.py`, `test_topic_gate_subject_aspect_split_od.py`, `test_od_seam_complete.py`) green with `PG_TOPIC_GATE_SUBQUERY_AWARE=0`, no test edits.
2. **Unit (stub LLM, no key):** label-valued `query_origin` never becomes an anchor; `retrieval_subquery` > `query_origin` precedence; `ON_SUBQUERY` stamps the sidecar and keeps; plain `ON`/`OFF` legacy tokens still parse; count-mismatch still fails open per batch; grouping order deterministic.
3. **Behavioral replay on drb_72 (the §-1.1 bar):** (i) every previously-deleted source that is on-topic to its sub-query now verdicts ON (`topic_on_via_subquery` where main-question-off) — zero sub-query-relevant deletions; (ii) the confirmed true junk (scholar-mill / unrelated-domain rows named in the I-deepfix-003 forensics) still verdicts OFF_SUBJECT against BOTH anchors and still deletes with disclosure; (iii) verdict lines read line-by-line, not counted.
4. **Determinism:** two harness runs at parallel 32 produce identical verdict JSONLs (modulo timestamps).
5. **Crash-resume:** kill the harness mid-run; rerun; verdict map identical to an uninterrupted run; LLM calls made only for the unjudged remainder.
6. **Faithfulness untouched:** `git diff` shows zero edits under `generator/provenance*`, `strict_verify`, NLI, 4-role, `junk_deletion_gate.py`.
7. **Dual gate:** real Codex CLI + real Fable 5 both APPROVE the diff (standing mandate).

---

## 5. Files touched + PR split (200-LOC cap per PR)

| PR | Files | ~LOC | Content |
|---|---|---|---|
| PR-1 (core) | `retrieval/fs_researcher_query_gen.py` (stamp, ~12); `retrieval/topic_relevance_gate.py` (anchors, grouping, prompt, parser, sidecar, ~140) | ~150 + tests | D1-D6, D8, D9 |
| PR-2 (throughput + boundary) | `topic_relevance_gate.py` (parallel dispatch + checkpoint, ~90); `run_honest_sweep_r3.py` (pass checkpoint_path, ~6); `scripts/dr_benchmark/topic_gate_subquery_harness.py` (~120, harness scripts exempt from prod-LOC scrutiny but reviewed) | ~220 total, harness-heavy | D7 + section 4 |

Requirement-aware, not hardcoded: both anchors are runtime data (the user's question and the run's own sub-queries); nothing domain-specific enters the prompt; every knob is an env flag (LAW VI). §-1.3 posture unchanged: this design makes the judge MORE conservative about OFF (either-anchor keep), narrows the only deletable class, and adds zero new drop paths.
