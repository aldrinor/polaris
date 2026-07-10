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

---

## 6. SELECT+WEIGH v2 — three-way line-level drop (operator sharpening, 2026-07-10)

Author: FABLE 5. Operator directive 2026-07-10. Grounding branch: `bot/I-deepfix-relaunch` (all file:line cites verified against the real tree). This section EXTENDS §1-5 (Design 1 stands unchanged); it adds a LINE-level select/drop reader on top of the sub-query-aware whole-source judge.

### 6.1 The operator's policy, and how it reconciles with §-1.3 (LOCKED DNA)

The sharpened policy does not violate WEIGHT-not-FILTER — it names WHICH axis is weight and WHICH is drop:

- **CREDIBILITY → WEIGHT, never drop.** A credible, on-topic, in-scope source is NEVER dropped; low tier = low weight, surfaced to the user. This is §-1.3 principle 1 verbatim. The weighting machinery is already real and stays UNTOUCHED: the tier-derived `authority_score` join + the raise-only institutional floor (`src/polaris_graph/synthesis/credibility_pass.py:266-324`), the T1-T7 tier classifier, the selection sort weights.
- **EXACTLY THREE DROP TRIGGERS:**
  1. **OFF_TOPIC** — off BOTH its own sub-query AND the main question (§3 D3's dual-anchor rule; delete stays reserved for OFF_SUBJECT-against-BOTH, §3 D6).
  2. **OUT_OF_USER_SCOPE** — outside the user's EXPLICIT scope in RunConfig (date window / recency / source type / peer-reviewed-only / geography / language / author). This is the USER's own hard filter — their right to exclude — not a pipeline quality knob, so the §-1.3 day-waster ban is not implicated: nothing here targets a breadth or quality number. If the user said "since 2023", a 2019 line is theirs to exclude → DROP.
  3. **JUNK** — chrome/nav/cookie/boilerplate. Already authorized whole-source by §-1.3.1(a); v2 extends it to welded chrome LINES inside otherwise-real pages.
- **LINE-LEVEL GRANULARITY (the new requirement):** the section reads EVERY line of each kept source and decides per line KEEP vs DROP-reason ∈ {off_topic, out_of_scope, junk}. A source that is 80% relevant keeps its 80%; only a source that is 100% off/out/junk drops whole. This generalizes the §-1.3.1 rule "off-topic SPAN inside an ON-TOPIC source → drop the span, keep the source" from the compose-side cited-span screen to the S2 grounding corpus.
- **FAIL-OPEN on every doubt (line kept), every drop DISCLOSED (line counts + reasons + quoted lines), marquee/contract sources protected from whole-drop.** The faithfulness engine (strict_verify / NLI / 4-role D8 / provenance / span-grounding) is untouched: the screen runs at S2 BEFORE generation, so it only SHRINKS the groundable text — a claim citing a dropped line fails strict_verify; nothing can pass that would not have passed before.

### 6.2 What already exists (reuse, do NOT reimplement)

| Capability | Where it lives today | Gap vs the policy |
|---|---|---|
| Whole-source topic judge (dual-anchor per §3) | `src/polaris_graph/retrieval/topic_relevance_gate.py:261-391` prompt, `:481` entry; judges TITLE+SNIPPET only (`:382-391`) | Never reads body lines |
| Whole-source junk delete | chrome stamp via `src/tools/access_bypass.py::detect_content_integrity_junk` at the seam (`scripts/run_honest_sweep_r3.py:14881-14960`); partition + marquee exemption + positive-relevance veto + disclosure (`src/polaris_graph/generator/junk_deletion_gate.py:205-263,156-202,299-322`) | Whole pages only; welded chrome LINES inside real pages leak through (I-fetchclean-001 residuals) |
| Span-level off-topic drop | compose-side WITHHOLD `weighted_enrichment.py:775-851` (`_span_is_confidently_offtopic`, fail-open ladder), `_withhold_offtopic_spans` `:880`, call sites `:5203,5338` | Lexical-overlap heuristic; runs at compose on CITED spans only, not on the S2 corpus; no scope/junk reasons |
| User scope extraction | `intake_constraint_extractor.py:136-157` `UserConstraints`: month-precision date window, language, `journal_only` (extracted, dormant), `timeline_strictness` weight/hard + verbatim `timeline_trigger_span` | Extracted but enforced only as WEIGHT (default) |
| Scope enforcement plan | `constraint_enforcement.py:55-70` `ScopeEnforcementPlan` (url_to_scope_weight / grounding_excluded_ids / scope_excluded_records), flag `PG_SCOPE_CONSTRAINT_ENFORCE` default OFF (`:47-50`); facets via `scope_facet_classifier.py` (ontology `config/scope_ontology/source_types.yaml`, reuses `is_peer_reviewed_journal_article`) | Weight/mask, not drop; source-level only |
| Date out-of-window predicate | `evidence_selector.py:918-1027` — `_row_out_of_window_ym` month precision, fail-open on undated (`:999-1005`), tail partition | Weight demote, not drop; source-level only |
| Chrome line vocabulary | `shell_detector.py:158-183` SHELL_COOCCURRENCE cookie/CMP/bot-wall classes; `:144-152` documents why whole-body lexical deletion is UNSAFE | Whole-body classifier; at LINE granularity co-occurrence-in-one-line is safe |
| Widest-body probe | `run_honest_sweep_r3.py:14925-14932` — max over `fetched_body/full_text/content/extracted_text/raw_content/raw_text/page_text/direct_quote/statement/...` | Reused verbatim as the line-read surface |

### 6.3 Design deltas (V1-V8, additive on D1-D9)

**V1 — Read surface.** New leaf module `src/polaris_graph/retrieval/line_screen.py` (LAW V, LAW VII: pure, LLM injected). For each source that SURVIVES the whole-source gates, take the widest body via the exact §6.2 probe list and split into line units (non-empty physical lines; a line under `PG_LINE_SCREEN_MIN_LINE_CHARS` merges into its neighbor so verdicts are judgeable units). Screening what the row actually carries is screening exactly what composition can cite — the grounding surface, not a phantom full text.

**V2 — Per-line three-way judge (semantic, dual-anchor + scope block).** One prompt per source (chunked at `PG_LINE_SCREEN_MAX_LINES_PER_CALL`, default 120, order-stable reassembly), reusing D3's scaffold: MAIN RESEARCH QUESTION + the row's SUB-QUERY anchor (D2 accessors reused) + — ONLY when RunConfig carries an explicit scope — a verbatim `USER SCOPE (explicit, from the user's own prompt):` block. Numbered lines; strict output contract `<line_idx>: KEEP|OFF_TOPIC|OUT_OF_SCOPE|JUNK` (same verdict-only discipline as `topic_relevance_gate.py:300-305`); count-mismatch ⇒ the WHOLE call fails open (all its lines KEEP), mirroring `:476-477`. Rubric nuances: (a) OFF_TOPIC = the line bears on NEITHER anchor (dual-anchor, same as D3); (b) the DATE-BLIND rule (`:369-373`) applies to OFF_TOPIC but NOT to OUT_OF_SCOPE — dates are precisely what an explicit date window judges; (c) OUT_OF_SCOPE may only be answered when the scope block is present; with no explicit scope the token is not offered and cannot fire; (d) JUNK = navigation/cookie/subscribe/related-articles chrome, with the `shell_detector.py:158-183` vocabulary supplied as HINT examples. Deterministic pre-pass: a line matching a SHELL_COOCCURRENCE class entirely WITHIN the one line is stamped junk without an LLM (at line granularity the `:144-152` false-positive objection dissolves — a real sentence discussing cookie policy does not carry CTA co-occurrence in one line); everything else is judge-decided.

**V3 — The out-of-scope predicate is RunConfig, never hardcoded.** Source-level: deterministic metadata vs the explicit scope — publication date via the `_row_out_of_window_ym` semantics (fail-open on undated, `evidence_selector.py:999-1005`), source-type/peer-reviewed/geography via `scope_facet_classifier` facets, language, author. Line-level: the V2 judge (a 2019-cohort line inside a 2024 in-window source is the judge's call). ACTIVATION RULE (anti-invention): the drop leg arms ONLY when the extracted constraint carries a verbatim trigger span (`UserConstraints.raw_directives` / `timeline_trigger_span`, `intake_constraint_extractor.py:154-156`) or an explicit control-panel override in RunConfig.scope (master plan §1.3 precedence). No explicit scope ⇒ ZERO out_of_scope drops anywhere; the existing weight demotes stay as-is. This PROMOTES explicit user scope from weight to drop (supersedes the weight-only default for the explicit case, including `journal_only`'s dormancy — the old veto barred PIPELINE-initiated journal filtering; a user's explicit "peer-reviewed only" is their hard filter and is now honored as a drop). Undated / unresolvable-facet rows and lines: KEEP (fail-open) + today's weight demote — we never drop what we cannot prove out of scope.

**V4 — Effect of a drop.** Kept lines are rejoined into the row's grounding body (`direct_quote` and the screened widest-body field are rewritten kept-lines-only); the original body remains untouched in `fetch_snapshot.json` (#1259) for audit. Each row gains a `line_screen` sidecar `{n_lines, n_dropped, reasons: {off_topic, out_of_scope, junk}}`; every dropped line is recorded VERBATIM with its reason in `line_screen_disclosure.json` (same disclosure discipline as `junk_deletion_gate.disclosure_records`, `:299-322`) and the Methods section states the counts (§-1.3.1 fail-loud, never silent).

**V5 — Whole-drop stays two-key.** A source whole-drops only via the EXISTING channels: chrome content-integrity (§6.2), judge OFF_SUBJECT-against-BOTH (D6), or NEW deterministic explicit-scope metadata violation (V3, disclosed through the same partition seam). If the line screen drops 100% of a source's lines but the whole-source verdict does NOT concur on the same reason class, that is a judge disagreement ⇒ fail-open: the source keeps ALL its lines (unscreened) and the disagreement is disclosed for audit. The marquee/contract exemption (`junk_deletion_gate.py:239-241`) and the positive-relevance veto (`:185-187`) hold for every whole-drop; marquee sources still get LINE screening (a cookie line in a marquee source is still junk) but can never be whole-dropped. This is guarantee (b) of the lock bar made structural: a credible on-topic in-scope source is NEVER whole-dropped.

**V6 — MAX PARALLELISM.** Per-source line-screen calls dispatch through the same bounded-executor pattern as D7 (`PG_LINE_SCREEN_PARALLEL`, default 1 = serial byte-identical; production slate 32), safe for the same reason: the production `_topic_llm`-style closure is self-contained per call with context-safe cost write-back (`run_honest_sweep_r3.py:13262-13321`). ~900 sources × 1-3 chunk calls at 32-wide = minutes, not hours. Verdicts key positionally per chunk; temperature 0.0; identical output at parallel 1 and 32.

**V7 — Crash resilience.** Incremental `line_screen_verdicts.jsonl` (same pattern as §4b): one record per screened source `{evidence_id, body_sha, n_lines, dropped: [{line_idx, reason, quote}]}`; header pins `{main_question_sha, scope_sha, flag_state}` — mismatch ⇒ ignore and re-screen. A crash loses at most the in-flight chunk; resume replays screened rows without LLM calls. The screened corpus lands in `cp2_corpus_snapshot` (the S2 checkpoint, unchanged name/seam `run_honest_sweep_r3.py:15058`), so pipeline resume after S2 needs no re-screen. Any checkpoint read/write error ⇒ proceed as if absent (a checkpoint bug must never drop or invent a verdict).

**V8 — Flags (LAW VI; all registry rows per master plan §1.2).** `PG_LINE_SCREEN` (kill-switch; OFF = byte-identical, no line is ever touched), `PG_LINE_SCREEN_PARALLEL` (default 1, slate 32), `PG_LINE_SCREEN_MAX_LINES_PER_CALL` (default 120), `PG_LINE_SCREEN_MIN_LINE_CHARS`, `PG_LINE_SCREEN_SCOPE` (out_of_scope leg; auto-inert without an explicit RunConfig scope). No scope value, no threshold, no domain term is hardcoded — the scope predicate is entirely the user's RunConfig.

### 6.4 Hamster loop + lock bar (v2 addendum; checkpoint = cp2_corpus_snapshot)

**Harness:** `scripts/dr_benchmark/line_screen_harness.py` (standalone CLI, same pattern as §4c): `--snapshot` a banked real corpus (drb_72 first — it holds known welded-chrome leaks, known off-topic rows, and rich mixed sources), `--only N` / `--source <evidence_id>` fast subsets, `--scope '<json>'` to inject an explicit RunConfig scope. Prints EVERY dropped line VERBATIM with its reason plus a per-source table (kept/dropped per reason, whole-drop events with which key concurred). Fable reads the dropped lines and a sample-free sweep of kept lines against the §-1.1 standard — claim-by-claim forensic read, never counts. Iterate: quick run → read every line → Fable names the defect → Opus patches → retest same snapshot (checkpoint replay makes re-runs cheap).

**Lock bar (all must pass, on the REAL corpus, before S2 v2 closes):**
- (a) Off-topic / out-of-scope / junk LINES are dropped with the exact line QUOTED in `line_screen_disclosure.json` and the harness output — verified against the known drb_72 welded-chrome and off-topic-line forensics.
- (b) A credible on-topic in-scope source is NEVER whole-dropped: the drb_72 replay shows the previously-mass-deleted credible institutions (St. Louis Fed, OECD, ILO, the 23 T1 journal rows named in the I-deepfix-003 forensics) all survive with their relevant lines intact; the V5 two-key rule and marquee exemption assert-tested.
- (c) A rich MIXED source keeps its relevant lines and drops only the bad ones: named mixed sources from the bank show partial keeps (~80% kept where ~80% is relevant), never all-or-nothing.
- (d) The user-scope filter drops out-of-scope and KEEPS in-scope: a "since 2023" RunConfig drops pre-2023 lines/sources (quoted, disclosed) and keeps in-window ones; the SAME corpus with an empty scope produces ZERO out_of_scope drops (activation-rule proof); undated rows are kept both ways (fail-open proof).
- (e) Fail-open on uncertainty: injected malformed verdict ⇒ chunk's lines all KEEP; LLM exception ⇒ source kept unscreened + disclosed; kill mid-run ⇒ resume produces the identical verdict map with LLM calls only for the unscreened remainder.
- Plus the standing items: `PG_LINE_SCREEN=0` byte-identical with the full suite green; determinism at parallel 32; `git diff` clean of `generator/provenance*` / strict_verify / NLI / 4-role; dual gate (real Codex CLI + real Fable 5 APPROVE).

### 6.5 PR split addendum

| PR | Files | ~LOC | Content |
|---|---|---|---|
| PR-3 (line screen core) | `retrieval/line_screen.py` (new leaf, ~170); `run_honest_sweep_r3.py` seam after the junk-gate partition (~20) | ~190 + tests | V1-V5, V8 |
| PR-4 (scope leg + throughput + harness) | `line_screen.py` scope predicate wiring to `UserConstraints`/facets (~60); parallel + JSONL checkpoint (~70); `scripts/dr_benchmark/line_screen_harness.py` (~130, harness-exempt) | ~130 prod | V3, V6, V7 + §6.4 |

### 6.6 Master-plan amendment (S2 row) — recorded here, mirrored in MASTER_EXECUTION_PLAN.md

S2 SELECT+WEIGH gains the line-level select/drop reader: scope column becomes "rerank, scope-weight demote, topic gate (sub-query-aware), junk-deletion gate, **line-level three-way select/drop reader (off_topic | out_of_scope | junk)**, selection"; design column becomes "Design 1 + Design 1 §6 (SELECT+WEIGH v2)". §-1.3 reconciliation, one line: **credibility is the WEIGHT axis (never drop); off-topic (dual-anchor), out-of-user-scope (explicit RunConfig only), and junk are the ONLY drop triggers — decided per LINE, fail-open, disclosed; whole-drop stays two-key + marquee-protected; the faithfulness engine remains the only hard gate for claims.**
