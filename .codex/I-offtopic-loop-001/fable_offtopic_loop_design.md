# OFF-TOPIC isolation test→fix loop — Fable design (I-offtopic-loop-001)

Author: Fable 5 (architect). Builder: Opus. Gate: the operator's read-every-line test — NO Codex gate.
Branch: `bot/I-deepfix-relaunch`. Date: 2026-07-09.

Mission: do for the TOPIC GATE what `scripts/fetch_corpus_replay.py` did for fetch junk.
Run the REAL production topic judge over the REAL drb_72 corpus (999 rows / 921 unique
`source_url` in `outputs/paid_drb72_deep/workforce/drb_72_ai_labor/corpus_snapshot.json`
on VM box2, ssh6.vast.ai:38794) and READ EVERY VERDICT. The over-deletion fix
(I-deepfix-005 #1376) passed unit tests; it has never been read over the real corpus.

---

## 0. The seam under test (real code, read on this branch)

The production path this loop validates end-to-end:

1. **The judge** — `classify_topic_relevance()` in
   `src/polaris_graph/retrieval/topic_relevance_gate.py:481-739`.
   - Prompt built by `_build_batch_prompt()` (`topic_relevance_gate.py:261-391`); the
     three-verdict subject/aspect split prompt is lines 281-309; the date-blind rule is
     lines 369-373; the fail-open instruction ("When in doubt, answer ON") is lines 375-376.
   - Parser `_parse_batch_verdicts_split()` (`topic_relevance_gate.py:433-478`): recognises
     `ON` / `OFF_ASPECT` / `OFF_SUBJECT`; a legacy bare `OFF` maps to `OFF_ASPECT`
     (never deletable, lines 471-474); any count mismatch returns `None` = the WHOLE batch
     fails OPEN (kept, lines 476-477 and 630-635).
   - Exemptions before judging (lines 549-564): marquee anchors
     (`_row_is_marquee_anchor`, lines 238-258), chrome non-sources
     (`_row_is_chrome_nonsource`, lines 152-177, flag `PG_JUNK_CHROME_BEFORE_OFFTOPIC`
     default ON per lines 131-141), and empty title+snippet rows (fail-open keep).
   - Verdict stamping (default keep-all + demote path, lines 673-708):
     `topic_offtopic_demoted=True` on every confident OFF (line 679); rescue
     `topic_offtopic_demoted=False` on confident ON (lines 683-685, flag
     `PG_TOPIC_GATE_RESCUE_ON_STAMP` default ON); the DELETABLE sidecar
     `topic_off_subject=True` ONLY on OFF_SUBJECT rows (lines 690-691); the sidecar is
     POPPED off rows re-verdicted ON / OFF_ASPECT (lines 704-708, the Codex-P1 stale-stamp fix).
   - Judge input per row = title + snippet only: `_row_title_text` (lines 215-225,
     precedence title > statement > source_title) and `_row_snippet_text` (lines 228-235,
     snippet / direct_quote / summary capped at `_MAX_SNIPPET_CHARS = 320`, line 54).
   - Batching: `topic_batch_size()` lines 180-191, `PG_SCOPE_TOPIC_BATCH` default 25;
     plain range-slice batching at lines 606-608.

2. **The delete predicate** — `is_row_deletable_offtopic()` in
   `src/polaris_graph/generator/junk_deletion_gate.py:156-202`. Deletes ONLY on the fresh
   affirmative OFF_SUBJECT stamp; a positive `content_relevance_label`
   (`relevant`/`escalated_relevant`) vetoes unconditionally (lines 185-187); a stale
   snapshot stamp not in `fresh_off_subject_ids` demote-KEEPs (lines 192-195). Fail-open on
   any error (lines 197-202). `_stamped_off_subject` is lines 139-153. The seam-level split
   is `partition_rows()` lines 205-263 (exempt ids honored at lines 239-241, chrome leg
   first at lines 243-246, off-topic elif at lines 247-256); disclosure via
   `disclosure_records()` lines 299-322.

3. **The orchestrator wiring** — `scripts/run_honest_sweep_r3.py`:
   - Production LLM callable `_topic_llm` (lines 13262-13321): `OpenRouterClient` with
     `model = PG_SCOPE_TOPIC_MODEL or PG_GENERATOR_MODEL` (lines 13273-13275),
     `max_tokens = PG_SCOPE_TOPIC_MAX_TOKENS` default 1200 (lines 13284-13291),
     `temperature=0.0` (line 13297).
   - The call: `classify_topic_relevance(evidence_for_gen, q["question"], _topic_llm, ...)`
     (lines 13329-13335).
   - Fresh deletable-id set: `_fresh_off_subject_ids = {evidence_id for r in
     _topic_result.demoted_rows if r.get("topic_off_subject") is True}` (lines 13345-13350).
   - Deletion seam: `_jd_exempt_ids` = marquee OR `v30_entity_id` rows (lines 14982-14987);
     `partition_rows(evidence_for_gen, exempt_ids=..., fresh_off_subject_ids=...)`
     (lines 14988-14994); durable disclosure file `junk_deletion_disclosure.json`
     (lines 15032-15044).

4. **The corpus** — `save_corpus_snapshot` payload carries top-level `"question"`
   (`src/polaris_graph/generator/corpus_snapshot.py:117`) and `"evidence_for_gen"`
   (line 121). So the harness reads the research question FROM the snapshot itself —
   no hardcoded question text (LAW VI).

**The harness REUSES all of 1-3 and reimplements NONE of it.** The only production logic it
mirrors (does not import) is the ~40-line async `_topic_llm` plumbing, because that callable
is a closure inside the sweep script — the mirror pins the SAME model env, SAME max_tokens
env, SAME temperature 0.0 (grounded above), so the judge behaves identically.

---

## 1. The harness: `scripts/offtopic_corpus_replay.py` (NEW)

Mirror of `scripts/fetch_corpus_replay.py`'s shape (argparse `--snapshot --parallel --limit
--urls-file --out`, lines 118-127 there; `results.json` + `summary.json` + `report.md` +
next-round subset file, lines 211-251 there; subset match by url OR evidence_id, line 141).

### 1.1 Inputs
- `--snapshot` (required): corpus_snapshot.json path. Rows = payload `evidence_for_gen`
  (the existing `load_rows` first-list heuristic in fetch_corpus_replay.py:107-114 already
  finds it); question = payload `"question"` — with `--question` override arg.
- `--controls` (default `tests/fixtures/offtopic_controls_drb72.json`): the marquee control
  set + known-junk seeds (§1.4). Per-question data file, LAW VI-compliant location.
- `--urls-file`: newline urls OR evidence_ids — fast subset re-test round.
- `--limit`, `--parallel` (shard count, default 8), `--out`, `--compare-to` (a prior round's
  `results.json` for verdict-stability diff).

### 1.2 What it does per run
1. Load rows, dedupe by `source_url` (keep the first row per url — one judge verdict per
   SOURCE, matching the loop's whole-source deletion semantics; all sibling rows of that url
   are listed in the record so nothing is hidden).
2. **Strip stale sidecars from the loaded copies** (`topic_off_subject`,
   `topic_offtopic_demoted`, `topic_relevance_verdict`) after RECORDING their old values
   per row. Rationale: these are OUTPUT stamps of the earlier run; the judge input is
   title+snippet only (topic_relevance_gate.py:215-235), so stripping cannot change what the
   LLM sees, and it makes every post-run stamp unambiguously FRESH. The recorded stale
   values go into the report as a stale-vs-fresh drift column (free regression signal).
   `content_relevance_label` and `content_integrity_junk` are NOT stripped — the delete
   predicate and chrome-skip read them in production and must see them here too.
3. Shard the deduped row list into contiguous chunks whose size is a MULTIPLE of
   `topic_batch_size()` (so batch membership inside each shard is byte-identical to what
   production's range-slice batching at topic_relevance_gate.py:606-608 would form), and run
   `classify_topic_relevance(shard, question, recording_llm, primary_trial_anchors=None,
   anchor_predicate=None)` on a thread pool — the gate module is UNTOUCHED; parallelism
   lives entirely in the harness. `anchor_predicate=None` is honest here: the sweep's
   predicate (run_honest_sweep_r3.py:13323-13327) needs `_primary_anchors` run state we
   don't have; the marquee exemption (`_row_is_marquee_anchor`) still applies inside the
   gate, and the harness separately reports which rows were exempt.
4. **Recording LLM callable**: mirrors `_topic_llm` (grounded §0.3) AND captures every
   (prompt, raw_response) pair to `llm_transcript.jsonl`. This is how the report quotes the
   judge's ACTUAL raw output, and how fail-open batches are precisely attributed: a batch
   whose captured response `_parse_batch_verdicts_split(raw, expected)` returns `None` for
   is a FAIL-OPEN batch — every row in it is recorded `UNJUDGED_FAILOPEN` with the raw
   response head quoted. (The harness calls the gate's own parser on the captured text for
   attribution only; the gate's live decision is still the gate's.)
5. Reconstruct the per-row fresh verdict from the gate's own outputs (identical expressions
   to the orchestrator):
   - `OFF_SUBJECT`: row in `result.demoted_rows` AND `row.get("topic_off_subject") is True`
     — the EXACT fresh-id expression of run_honest_sweep_r3.py:13345-13349.
   - `OFF_ASPECT`: row in `demoted_rows` without the sidecar.
   - `ON`: `row.get("topic_offtopic_demoted") is False` (the rescue stamp,
     topic_relevance_gate.py:683-685).
   - `EXEMPT_MARQUEE` / `SKIPPED_CHROME` / `SKIPPED_EMPTY`: re-derived with the gate's own
     helpers (`_row_is_marquee_anchor`, `_row_is_chrome_nonsource`, `_row_title_text`,
     `_row_snippet_text` — imported, not reimplemented). Cross-check: the derived counts
     MUST equal the gate's telemetry note (topic_relevance_gate.py:713-718); mismatch =
     harness fails LOUD (its own reconstruction is wrong, stop).
   - remainder: `UNJUDGED_FAILOPEN` (must equal the fail-open batches from step 4).
6. **Deletability, through the REAL seam**: build `fresh_off_subject_ids` exactly as
   run_honest_sweep_r3.py:13345-13350; build `exempt_ids` exactly as lines 14982-14987
   (marquee OR `v30_entity_id`); call
   `junk_deletion_gate.partition_rows(rows, exempt_ids, fresh_off_subject_ids)` and
   `disclosure_records(deleted)`. Record per row: `deletable` (deleted with reason
   `confirmed_offtopic_subject`), `chrome_deleted` (reason `content_integrity_junk:*` —
   the fetch loop's jurisdiction, reported separately as a cross-check only), and the veto
   trail (OFF_SUBJECT rows KEPT because of the positive-relevance veto
   junk_deletion_gate.py:185-187 or the exemption 239-241 — these must be visible).
7. Per-row record in `results.json`: evidence_id, source_url, tier, title, journal, year,
   `judge_input` (the exact title+snippet string sent, ≤320-char snippet as production
   truncates it), `content_head` (first 300 chars of the widest content field — the
   operator's independent side-by-side read, §-1.1), fresh verdict, stale stamps,
   `deletable`, veto trail, control-set hit, known-junk-seed hit, suspect-marker hits,
   batch id + raw-response pointer.

### 1.3 The 4-bucket verdict oracle (the §-1.1 read)

| Bucket | Definition | Machine navigation | Binding decision |
|---|---|---|---|
| 1 — correctly KEPT | fresh ON or OFF_ASPECT on a real AI-labor source | full list, one head-line each | operator read |
| 2 — correctly FLAGGED | fresh OFF_SUBJECT on genuine wrong-domain junk (poultry / sports-management / space / religion scholar-mill) | known-junk-seed hits highlighted | operator reads ALL OFF_SUBJECT rows |
| 3 — OVER-DELETION regression (**#1 danger, must be ZERO**) | a credible on-topic source stamped OFF_SUBJECT and `deletable=True` | control-set hit ⇒ automatic FAIL banner | operator reads ALL OFF_SUBJECT rows — every one quoted |
| 4 — under-catch | obviously off-subject source left ON | independent suspect markers flag ON rows for priority read (flag, never verdict) | operator read |

Buckets 2 vs 3 are the SAME machine set (fresh OFF_SUBJECT + deletable); only the read
splits them — that is why the read is the gate. Counts are navigation only (§-1.1 bans
count-based verdicts). The suspect-marker list for bucket 4 is the harness's OWN independent
lexical list (mirroring fetch_corpus_replay's HIGH/MED marker independence,
fetch_corpus_replay.py:39-68 — a gate cannot validate itself): wrong-domain cues (poultry,
veterinary, theology, astrophysics, tourism, dentistry, aquaculture, …) that ORDER the
operator's read of the ON list. A marker hit is never a verdict.

### 1.4 The marquee control set — `tests/fixtures/offtopic_controls_drb72.json` (NEW)

Two lists, both quoted into the report:
- `must_keep` (the over-deletion incident's own victims, junk_deletion_gate.py:167-169:
  St. Louis Fed, OECD, ILO, McKinsey, HBS, World Bank, Wikipedia, the 23 T1 journal
  papers): matched by url-domain pattern (stlouisfed.org, oecd.org, ilo.org, mckinsey.com,
  worldbank.org, imf.org, nber.org, brookings.edu, hbs.edu, …) plus the 23 papers pinned by
  evidence_id/url extracted from the earlier run's deletion disclosure
  (`junk_deletion_disclosure.json` of the I-deepfix-003 pass on box2). Rule: a `must_keep`
  row with fresh verdict OFF_SUBJECT **and** `deletable=True` ⇒ the round FAILS
  automatically (bucket 3 > 0), loud banner at the top of report.md. A `must_keep` row
  verdicted OFF_ASPECT ⇒ WARNING (demote-keep is §-1.3-safe but still flagged for the read).
- `known_junk` (seeded from the prior forensic reads of drb_72: the poultry /
  sports-management / space / religion scholar-mill sources, pinned by evidence_id/url):
  each MUST land fresh OFF_SUBJECT; one left ON or OFF_ASPECT ⇒ under-catch finding
  (bucket 4), listed by name.

COMPLIANCE FENCE: the control set lives in the HARNESS ONLY. It is an alarm, never a
production exemption or deletion trigger — wiring a name-list into the gate would violate
§-1.3.1 ("judge verdict ONLY, never by tier, lexical guess, or a breadth number").

### 1.5 Outputs (mirror the fetch loop)
- `results.json` — every row's full record (§1.2.7).
- `llm_transcript.jsonl` — every prompt + raw judge response (the quoted evidence).
- `summary.json` — machine counts: n_sources, n_on, n_off_aspect, n_off_subject,
  n_deletable, n_vetoed, n_controls_broken, n_known_junk_missed, n_failopen_batches,
  n_exempt, n_chrome_skipped, effective env (model, max_tokens, batch, all five gate flags),
  question hash.
- `report.md` — the operator's read, in reading order: FAIL/PASS banner + broken controls
  first; then EVERY OFF_SUBJECT row (verdict + judge_input + content_head + veto trail,
  side by side — the §-1.1 independent check); then all OFF_ASPECT; then suspect-flagged ON
  rows; then the full ON list (one line each); then UNJUDGED (exempt / chrome / empty /
  fail-open, each fail-open batch's raw response head quoted); then the stale-vs-fresh
  drift table; then the stability diff when `--compare-to` is given.
- `next_flags.txt` — urls/evidence_ids of all OFF_SUBJECT + broken controls + missed
  known-junk + suspect-ON rows: the subset for the next hamster round.

### 1.6 Environment parity (recorded, not assumed)
The harness records into summary.json the EFFECTIVE values of `PG_SCOPE_TOPIC_GATE`,
`PG_TOPIC_GATE_SUBJECT_ASPECT_SPLIT`, `PG_JUNK_CHROME_BEFORE_OFFTOPIC`,
`PG_TOPIC_GATE_RESCUE_ON_STAMP`, `PG_DELETE_OFFTOPIC_TOPIC_JUDGE_ONLY`,
`PG_DELETE_OFFTOPIC_FRESH_VERDICT_ONLY`, `PG_SCOPE_TOPIC_MODEL`,
`PG_SCOPE_TOPIC_MAX_TOKENS`, `PG_SCOPE_TOPIC_BATCH`. All six gate flags default ON /
production values (grounded at topic_relevance_gate.py:57-141 and
junk_deletion_gate.py:73-102). A mis-set env cannot silently change the test — it is
printed at the top of the report.

---

## 2. Stop condition + fix loop (the hamster shape)

### 2.1 Stop condition (ALL must hold; the binding decision is the operator's read)
1. `n_controls_broken == 0` — no `must_keep` source is OFF_SUBJECT+deletable.
2. Operator's line-by-line read of EVERY OFF_SUBJECT row confirms each is genuine
   off-subject junk ⇒ bucket 3 is zero BY READ, not by count.
3. Every `known_junk` seed is fresh OFF_SUBJECT, AND the operator's read of the
   suspect-flagged ON list finds no obvious junk left ON ⇒ bucket 4 clean.
4. Stability: the confirm round (§2.3) reproduces the OFF_SUBJECT set — an LLM judge is
   not deterministic even at temperature 0.0 (provider-side nondeterminism), so a row that
   FLAPS between OFF_SUBJECT and ON/OFF_ASPECT across rounds is an instability finding: it
   may not be deleted on a flapping verdict. Fail-open direction: a flapper is treated as
   NOT-confirmed (kept) and investigated.
5. `n_failopen_batches` is read and explained. Fail-open is the designed safety direction
   (topic_relevance_gate.py:28-35) but a HIGH rate means the output contract is failing on
   real batches (e.g. max_tokens starvation, run_honest_sweep_r3.py:13278-13291) and the
   judge is silently not judging — that is an under-catch root cause, not a pass.

### 2.2 Fix loop (Fable investigates → Opus builds → retest)
When a bucket fires, Fable's investigation map (all seams already grounded in §0):
- **Bucket 3 (over-deletion)** — in likelihood order: (a) the OFF_ASPECT vs OFF_SUBJECT
  rubric wording (`_build_batch_prompt` lines 282-309: is "unsure ⇒ OFF_ASPECT" strong
  enough?); (b) judge input too thin — the 320-char snippet cap (line 54) + title-only rows
  starving the judge into a wrong-subject guess; (c) the date-blind rule regressing
  (lines 369-373); (d) the deletable predicate / veto (junk_deletion_gate.py:156-202);
  (e) batch-size context dilution (`PG_SCOPE_TOPIC_BATCH`).
- **Bucket 4 (under-catch)** — (a) fail-open batches eating verdicts (starved
  `PG_SCOPE_TOPIC_MAX_TOKENS` on a reasoning model ⇒ empty content ⇒ whole batch kept,
  run_honest_sweep_r3.py:13278-13283); (b) the model emitting legacy bare `OFF`, which the
  parser maps to OFF_ASPECT = never deletable BY DESIGN (parser lines 471-474) — a real
  under-catch channel to weigh deliberately; (c) the fail-open bias line itself
  (lines 375-376); (d) chrome misclassification keeping junk unjudged (lines 152-177).
- Opus builds the fix (gate edit is IN scope ONLY when the loop has found a bug — otherwise
  the gate is not touched), pushes to `bot/I-deepfix-relaunch`, retest per §2.3.

### 2.3 Retest rules (what a round must re-run)
- Predicate-only / harness-only change ⇒ subset round on `next_flags.txt` is enough,
  PLUS one final FULL-corpus round before declaring the loop passed.
- ANY judge-prompt or parser change ⇒ the confirm round is the FULL 921-source corpus.
  A prompt change can flip previously-ON rows to OFF; a subset re-test of old flags is
  structurally blind to new over-deletion — the exact blind-spot the banked-replay lesson
  (I-wire-013) taught.

### 2.4 Box2 retest helper — `scripts/offtopic_hamster_retest.sh` (NEW)
Mirror of `scripts/hamster_retest.sh` (lines 1-19): `git pull --ff-only origin
bot/I-deepfix-relaunch`, `pkill -f offtopic_corpus_replay`, source `/workspace/POLARIS/.env`
(Zyte/OpenRouter keys live there), run the harness with `--urls-file next_flags.txt`
(arg 1 = round tag, arg 2 = parallel), grep the FAIL/verdict lines, cat `summary.json`.
Full-round variant via arg 3 = `full` (drops `--urls-file`). VM specifics stay in the shell
helper (as in the fetch loop); the python takes everything by arg/env (LAW VI).

---

## 3. Exact files Opus builds

| File | Status | Content |
|---|---|---|
| `scripts/offtopic_corpus_replay.py` | NEW | the harness (§1). Imports `classify_topic_relevance`, `topic_batch_size`, `_row_is_marquee_anchor`, `_row_is_chrome_nonsource`, `_row_title_text`, `_row_snippet_text`, `_parse_batch_verdicts_split` from `topic_relevance_gate`; `partition_rows`, `disclosure_records`, `is_row_deletable_offtopic` from `junk_deletion_gate`. Read-only vs `src/`. |
| `scripts/offtopic_hamster_retest.sh` | NEW | box2 retest helper (§2.4). |
| `tests/fixtures/offtopic_controls_drb72.json` | NEW | `must_keep` + `known_junk` control set (§1.4); the 23-paper pins extracted from the box2 deletion disclosure of the I-deepfix-003 pass. |
| `src/polaris_graph/retrieval/topic_relevance_gate.py` | **NO EDIT** | unless the loop finds a bug (§2.2). |
| `src/polaris_graph/generator/junk_deletion_gate.py` | **NO EDIT** | unless the loop finds a bug. |
| `scripts/run_honest_sweep_r3.py` | **NO EDIT** | the harness replicates its two seam expressions read-only. |

---

## 4. Sequencing: after the fetch loop, before the compose loop

1. **Fetch-junk loop first** (running now): stop at `summary.json real_junk == 0`
   (fetch_corpus_replay.py:201-209). Grounded reason it MUST come first: the topic gate
   SKIPS chrome non-sources using the same content-integrity detector the fetch loop
   hardens (topic_relevance_gate.py:131-141 and 549-555). While fetch junk is dirty, chrome
   garble rows either consume judge verdicts or get mislabeled — topic verdicts are only
   meaningful over a fetch-clean corpus.
2. **This off-topic loop**: round r0 full corpus → operator read → fix rounds on
   `next_flags.txt` → final full confirm round → stop condition §2.1.
3. **Compose loop last**: the compose-side off-topic SPAN screen and the composition read
   assume whole-source verdicts are trustworthy (§-1.3.1: off-topic span in an on-topic
   source ⇒ drop the span, keep the source). Validating span-level behavior before
   source-level verdicts are proven would blame the wrong layer.

Cost honesty: one judge call per ~25 sources ⇒ ≈37 LLM calls per full round
(921 sources minus chrome/marquee/empty), temperature 0.0, on the locked OpenRouter models
— bounded, minutes per round with 8 shards, run on box2 next to the corpus. Subset rounds
are a handful of calls.

---

## 5. Compliance checklist

- **§-1.3.1 fail-open preserved and VALIDATED**: the harness changes no deletion behavior;
  it proves the fail-open contract holds over the real corpus (bucket 3 == 0 IS the
  "never delete a credible on-topic source" rule, tested for real).
- **Judge-verdict-only deletion untouched**: deletability is computed through the real
  `partition_rows` seam with the real fresh-id + exempt-id expressions — no tier / lexical /
  number path can delete, in the harness or anywhere.
- **Every verdict disclosed + quoted**: results.json carries every row; report.md quotes
  judge input, content head, raw judge response, veto trail, and every deletion — no
  sample-based audit, no count-as-verdict (§-1.1).
- **Independent check for the operator**: the judge's verdict and the actual source content
  sit side by side; the suspect markers and control set are harness-owned, not
  gate-owned (a gate cannot validate itself — I-wire-013).
- **Controls are alarms, never production logic**: the `must_keep` list never enters the
  gate; §-1.3.1's "judge verdict ONLY" stays intact.
- **Faithfulness engine untouched**: the harness never touches composition, strict_verify,
  NLI, D8, or provenance; it exercises selection-side gates only
  (topic_relevance_gate.py:22-26 FAITHFULNESS LOCK holds).
- **Fail loud**: reconstruction-vs-telemetry count mismatch aborts the harness; fail-open
  batches are named and quoted, never folded into "kept".
- **LAW VI**: no hardcoded paths/models/thresholds in the python — snapshot, controls,
  question, parallelism by arg; model/tokens/batch by the SAME env vars production uses.
