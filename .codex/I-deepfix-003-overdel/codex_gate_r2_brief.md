[HARD ITERATION CAP 5. Front-load ALL findings. APPROVE iff zero P0 AND zero P1. Test results are the ground.]

You are the CODEX GATE (round 2, diff gate) for the I-deepfix-003 (#1374) OVER-DELETION fix. Verdict rules: APPROVE iff zero P0 AND zero P1. Front-load every real finding in this one pass. Do not drip-feed. Reserve P0/P1 for real execution/correctness/clinical-safety risk; classify anything smaller as P2/P3. Output the schema at the bottom; the LAST `verdict:` line is parsed by CI.

## What you are reviewing

Branch `bot/od-seam-complete` diffed against its base `bot/I-deepfix-004-frontmatter-core` (merge-base `d7206e3f`). 7 files, +1265/-42. This is the SIX-FIX build for a confirmed over-deletion bug: the prior pass deleted 588 of 787 grounding rows (75%), ~240-280 of them WRONGLY — credible on-topic sources (St. Louis Fed T3, 2x OECD T3, ILO T3, McKinsey, HBS, HBR, WEF, World Bank, PwC, BCG, Wikipedia, 23 T1 journal papers) were hard-deleted because a WEIGHT/reranker label (`content_relevance_label in {demoted, escalated_demoted}`) was reused as a DELETE trigger. A T6 Substack survived — the inversion symptom.

To read the ACTUAL reviewed code (the working tree is NOT checked out to this branch — do not read files directly, use git):
- Full diff: `git --no-pager diff bot/I-deepfix-004-frontmatter-core...bot/od-seam-complete`
- Full file at the reviewed state: `git show bot/od-seam-complete:src/polaris_graph/generator/junk_deletion_gate.py` (and same for the other paths)
The three core source diffs are embedded below so you have them without running git; the two new test files are large — read them with `git show bot/od-seam-complete:tests/polaris_graph/test_od_seam_complete.py` and `...:tests/polaris_graph/test_topic_gate_subject_aspect_split_od.py` and `git --no-pager diff bot/I-deepfix-004-frontmatter-core...bot/od-seam-complete -- tests/polaris_graph/test_junk_deletion_gate.py`.

## THE BINDING RULE (this is the contract the diff must satisfy)

A source may be DELETED from the grounding pool ONLY when:
- it is a CHROME non-source (failed fetch: bot/captcha/cookie/404/login/empty), OR
- the topic judge produced a FRESH `OFF_SUBJECT` verdict THIS run.

And ALL of these must hold:
1. A weight/reranker label (`content_relevance_label = demoted` / `escalated_demoted`) can NEVER trigger a delete. It is a weight-demote-to-0.25 KEEP label (a Qwen3-Reranker numeric score / a GLM "INSUFFICIENT" entailment), not a topic verdict.
2. A positive relevance verdict (`content_relevance_label in {relevant, escalated_relevant}`) VETOES deletion unconditionally — even against a stale/false OFF stamp. When the two judges disagree, positive relevance wins.
3. FRESH-VERDICT-ONLY: a stale `OFF_SUBJECT` stamp reloaded from an earlier run's `corpus_snapshot` (judge did NOT re-run this pass) must demote-KEEP, never delete.
4. `OFF_ASPECT` (same subject entity, wrong aspect — a topic-adjacent hub) is demote-KEEP, NEVER deletable. Only `OFF_SUBJECT` (clearly different subject) is deletable. A legacy bare `OFF` maps to `OFF_ASPECT` (conservative).
5. FAIL-OPEN on ANY uncertainty / missing verdict / stale-only stamp / error / non-Mapping row => KEEP. A predicate bug must never delete a source.
6. No credible ON-TOPIC source is deletable — not by tier, lexical guess, or a breadth number.
7. Disclosure is DURABLE + per-source + lands on the Methods section + the manifest summary; a deletion is never silent (§-1.3.1 fail-loud).
Chrome is a SEPARATE leg from off-topic (both a stamp-side clear and a topic-side skip) so a garbled/bot body can never be mislabeled `confirmed_offtopic`.
Faithfulness engine (strict_verify / NLI / 4-role D8 / provenance) must be BYTE-UNTOUCHED. Every fix must be a default-ON flag that is byte-identical when OFF. No caps/targets/thinners (the §-1.3 day-waster ban).

## Per-file summary vs the Fable fix plan (Fixes 1-6)

`src/polaris_graph/generator/junk_deletion_gate.py` — Fix 1 + Fix 2 + Fix 5 (records):
- NEW `is_row_deletable_offtopic(row, fresh_off_subject_ids=None)`: the default-ON delete predicate. Deletes ONLY on `_stamped_off_subject(row)` (topic judge OFF_SUBJECT). Positive `content_relevance_label` returns False (unconditional veto) BEFORE any OFF check. `content_relevance_label` is NEVER read as a delete trigger. Fresh-set gate (Fix 2): a concrete `fresh_off_subject_ids` set + `PG_DELETE_OFFTOPIC_FRESH_VERDICT_ONLY` ON => a row whose `evidence_id` is not in the set demote-KEEPs. `None` => freshness un-enforced (byte-identical Fix-1). Wrapped in try/except => fail-open KEEP.
- `_stamped_off_subject`: True only on `topic_off_subject is True` / string tokens / `topic_relevance_verdict == "off_subject"`. Legacy `topic_offtopic_demoted` alone does NOT count.
- `partition_rows` gains `fresh_off_subject_ids`; chrome-first if/elif preserved; default-ON branch calls `is_row_deletable_offtopic` and emits reason `confirmed_offtopic_subject`; legacy `is_row_confirmed_offtopic` reachable ONLY behind `PG_DELETE_OFFTOPIC_TOPIC_JUDGE_ONLY=0`.
- `disclosure_records`: adds `tier`, `signal`, `judge_verdict` per source.
Two new kill-switches (`topic_judge_only_deletion_enabled`, `fresh_verdict_only_deletion_enabled`), both default ON.

`src/polaris_graph/retrieval/topic_relevance_gate.py` — Fix 3 + Fix 4 (topic-side):
- Fix 3: `PG_TOPIC_GATE_SUBJECT_ASPECT_SPLIT` (default ON). `_build_batch_prompt(..., subject_aspect_split=)` returns a 3-verdict contract (`ON | OFF_ASPECT | OFF_SUBJECT`) when ON; the else-branch reproduces the legacy 2-verdict prompt byte-for-byte. NEW `_parse_batch_verdicts_split` (bare `off` -> OFF_ASPECT conservative; separator-tolerant; fail-open None on count mismatch). In `classify_topic_relevance`: OFF_SUBJECT rows get `topic_off_subject=True`; OFF_ASPECT + ON rows `pop("topic_off_subject", None)` to CLEAR a STALE True baked into corpus_snapshot (Codex-P1 gate-fix — prevents a stale True re-entering the fresh set).
- Fix 4 (topic-side): `PG_JUNK_CHROME_BEFORE_OFFTOPIC` (default ON). `_row_is_chrome_nonsource` uses the pure content-integrity detector on the widest body; a chrome row is skipped from the judge entirely (never stamped off_subject), kept in `sources` for the chrome-delete leg. `chrome_skipped=N` added to notes.

`scripts/run_honest_sweep_r3.py` — Fix 2 seam + Fix 4 (stamp-side) + Fix 5 + Fix 6 token:
- Fix 2 seam: `_fresh_off_subject_ids` bound to `set()` BEFORE the gate block (always bound on every path to the seam); filled from `_topic_result.demoted_rows where topic_off_subject is True`; threaded into `partition_rows(..., fresh_off_subject_ids=_fresh_off_subject_ids)`.
- Fix 4 stamp-side: on a confirmed chrome row set `topic_off_subject = False` (belt-and-suspenders to partition_rows' chrome-first) so chrome_nonsource stays honest.
- Fix 5: NEW `_attach_junk_deletion_disclosure(manifest, run_dir)` reads the durable `junk_deletion_disclosure.json`, splits `deleted_chrome_nonsources` (reason startswith `content_integrity_junk`) vs `deleted_offtopic_sources` (reason startswith `confirmed_offtopic` — catches BOTH `confirmed_offtopic_subject` AND legacy `confirmed_offtopic`; the OLD success-only filter used `== "confirmed_offtopic"` and silently MISSED the Fix-1 reason). Called inside `_attach_tool_utilization` (single pre-write chokepoint) so it lands on EVERY manifest write. The timeout finalizer now also routes through `_attach_tool_utilization`. Durable `junk_deletion_disclosure.json` written at the seam on every exit path. Report `## Methods — source hygiene` line appended to the reliability APPENDIX (not the scored body).
- Fix 6 token: topic judge `max_tokens` now `PG_SCOPE_TOPIC_MAX_TOKENS` (default 1200 byte-identical; manifest sets 16000) to un-starve a reasoning scope model (§9.1.8).

`.codex/I-deepfix-001/LAUNCH_READINESS_BOTH_BOXES.md` — Fix 6 launcher hygiene (BOTH box1 + box2 halves): removed `PG_OFFTOPIC_RELEVANCE_OVERRIDE=0`; added `PG_DELETE_OFFTOPIC_TOPIC_JUDGE_ONLY=1 PG_DELETE_OFFTOPIC_FRESH_VERDICT_ONLY=1 PG_TOPIC_GATE_SUBJECT_ASPECT_SPLIT=1 PG_JUNK_CHROME_BEFORE_OFFTOPIC=1` explicit; kept `PG_RESUME_RUN_TOPIC_JUDGE=1` (a plain resume must re-stamp fresh OFF_SUBJECT verdicts or Fix 2 suppresses ALL off-topic deletion); added `PG_SCOPE_TOPIC_MAX_TOKENS=16000`.

Tests: `tests/polaris_graph/test_junk_deletion_gate.py` (+143), `test_od_seam_complete.py` (new +217), `test_topic_gate_subject_aspect_split_od.py` (new +278).

## MOST CRITICAL to verify (the 4 items the operator flagged)
1. `content_relevance_label` can no longer reach ANY delete path on the default-ON build. (It appears only in the positive-veto branch and in the OFF-only legacy path behind `PG_DELETE_OFFTOPIC_TOPIC_JUDGE_ONLY=0`. Confirm there is no third reachable path.)
2. A STALE off-topic stamp does NOT delete (fresh-verdict-only): confirm the seam binds an empty `_fresh_off_subject_ids` on a plain resume, and the OFF_ASPECT/ON `pop` clears a stale `topic_off_subject=True` so it cannot re-enter the fresh set.
3. Chrome is separated from the off-topic leg on BOTH halves (topic-side skip + stamp-side clear), and partition_rows' chrome-first ordering holds.
4. No credible on-topic source (Fed/OECD/McKinsey/ILO/World Bank/journal papers) is deletable under this build — trace an ON verdict and an OFF_ASPECT verdict to KEEP.
Also confirm: every new flag is default-ON and byte-identical OFF; the faithfulness engine is untouched; no cap/target/thinner was added; fail-open holds on every predicate error.

## TEST EVIDENCE (the build agent's report — verify against the code, do not take on faith)

Build: done=true. Commits: Fix 2 (330103b6) fresh-verdict-only + seam threading; Fix 4 (f225fdfb) chrome routing both halves; Fix 5 (43cb126a) durable disclosure + `_attach_junk_deletion_disclosure` in `_attach_tool_utilization` (fixes the success-only `== confirmed_offtopic` filter that missed `confirmed_offtopic_subject`) + report `## Methods` line; Fix 6 (7944eca4) launcher hygiene + un-starve topic judge; Tests (0543a38d).

tests_green=true. Targeted suite GREEN: 59/59 pass across test_junk_deletion_gate.py, test_od_seam_complete.py (new), test_topic_gate_subject_aspect_split_od.py, test_topic_gate_aspect_ff4.py, test_drb72_chrome_offtopic_bullets.py. New coverage proves: a stale OFF_SUBJECT stamp (empty fresh set) is NOT deleted while a fresh-set id IS; fresh=None is byte-identical Fix-1; a real-shaped chrome row is not judged with the guard ON and IS with it OFF; `_attach_junk_deletion_disclosure` splits chrome vs off-topic (including `confirmed_offtopic_subject`) and adds no keys when the durable file is absent; the DRB-72 contract resolves the 5-column table, the renderer emits the exact header, and check_contract_scaffold passes.

Build agent NOTE (verify this claim): the broad `-k` filter also surfaces 12 PRE-EXISTING FAILURES (e.g. `test_topic_gate_disabled_default` asserting the topic gate default is OFF, and `test_b1_semantic_relevance_scorer` expecting a hard-drop). The agent claims these assert SUPERSEDED defaults (gate flipped ON 2026-06-30; off-topic is now demote-not-drop per §-1.3) and fail IDENTICALLY on the base branch `bot/I-deepfix-005-overdel`, i.e. ZERO regressions introduced by these six fixes. If you can, spot-check whether these 12 failures pre-exist on the base and are truly unrelated to this diff; if you believe any is a real regression introduced here, that is a P0/P1 finding.

You MAY run the targeted tests yourself if useful (offline, no key):
`python -m pytest tests/polaris_graph/test_junk_deletion_gate.py tests/polaris_graph/test_od_seam_complete.py tests/polaris_graph/test_topic_gate_subject_aspect_split_od.py -q` against a `bot/od-seam-complete` checkout. Note the working tree is currently on a different branch; do not assume the working tree matches the reviewed diff.

## Embedded core diffs

### junk_deletion_gate.py
```diff
@@ is_row_deletable_offtopic (new default-ON predicate) @@
def is_row_deletable_offtopic(row, fresh_off_subject_ids=None):
    try:
        if not isinstance(row, Mapping):
            return False
        label = str(row.get("content_relevance_label", "") or "").strip().lower()
        if label in _POSITIVE_RELEVANCE_LABELS:   # {relevant, escalated_relevant}
            return False  # positive relevance — KEEP (unconditional veto)
        if not _stamped_off_subject(row):
            return False
        if fresh_off_subject_ids is not None and fresh_verdict_only_deletion_enabled():
            eid = str(row.get("evidence_id", "") or "")
            if eid not in {str(e) for e in fresh_off_subject_ids}:
                return False  # stale stamp — demote-keep
        return True
    except Exception:
        return False  # fail-open KEEP

@@ partition_rows off-topic branch @@
elif offtopic_on:
    if topic_judge_only_deletion_enabled():        # default ON
        if is_row_deletable_offtopic(row, fresh_off_subject_ids=fresh_ids):
            reason = "confirmed_offtopic_subject"
    elif is_row_confirmed_offtopic(row):           # legacy, only when flag OFF
        reason = "confirmed_offtopic"
```

### topic_relevance_gate.py
```diff
@@ classify_topic_relevance — chrome skip + split stamping + stale-clear @@
chrome_skip = junk_chrome_before_offtopic_enabled()   # default ON
for row in sources:
    if _is_exempt(row): exempt_rows.append(row); continue
    if chrome_skip and _row_is_chrome_nonsource(row):
        n_chrome_skipped += 1; continue               # never judged, never off_subject
    ...
# per-verdict (split ON):
if v == "OFF_SUBJECT": offtopic_rows.append(row); offsubject_rows.append(row)
elif v == "OFF_ASPECT": offtopic_rows.append(row); offaspect_rows.append(row)
elif v == "ON": ontopic_rows.append(row)
# after batches (split ON):
for row in offsubject_rows: row["topic_off_subject"] = True
if split:
    for row in offaspect_rows: row.pop("topic_off_subject", None)  # clear STALE True
    for row in ontopic_rows:   row.pop("topic_off_subject", None)
```

### run_honest_sweep_r3.py
```diff
@@ seam @@
_fresh_off_subject_ids: set[str] = set()   # bound before the gate block, all paths
...
_fresh_off_subject_ids = {str(r.get("evidence_id","") or "")
    for r in _topic_result.demoted_rows
    if isinstance(r, dict) and r.get("topic_off_subject") is True}
_fresh_off_subject_ids.discard("")
...
# chrome stamp-side (Fix 4):
_r["content_integrity_junk"] = True; _r["content_integrity_class"] = _cls
if _chrome_before_offtopic: _r["topic_off_subject"] = False
...
_jd_kept, _junk_deleted_for_disclosure = _junk_gate.partition_rows(
    evidence_for_gen, exempt_ids=_jd_exempt_ids, fresh_off_subject_ids=_fresh_off_subject_ids)
...
# durable disclosure written at the seam (every exit path)
(run_dir / "junk_deletion_disclosure.json").write_text(...)

@@ _attach_junk_deletion_disclosure — split by reason prefix @@
manifest["deleted_chrome_nonsources"] = [r for r in _recs
    if str(r.get("deletion_reason","")).startswith("content_integrity_junk")]
manifest["deleted_offtopic_sources"] = [r for r in _recs
    if str(r.get("deletion_reason","")).startswith("confirmed_offtopic")]   # catches _subject too
# called inside _attach_tool_utilization (every manifest write); timeout finalizer routed through it too
```

## Output schema (emit exactly this; the LAST `verdict:` line is parsed by CI)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
