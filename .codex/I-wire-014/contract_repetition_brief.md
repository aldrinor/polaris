HARD ITERATION CAP: 5 per document. This is iter 3 of 5.

## ITER-3 CHANGES (addressing your iter-2 findings — both fixed)
- **iter-2 P1 (numeric-signature exact dups within ONE section don't collapse):** FIXED. Root
  cause confirmed: `build_groups`' numeric path emits ONLY cross-section groups
  (fact_dedup.py:891 `distinct_sections < 2` skip) and the prose/Jaccard + NLI paths skip
  non-empty signatures, so a `%`/`$`/year sentence restated verbatim in one section forms no
  group. ADDED a contract-local EXACT-OCCURRENCE pass: group `kept_sentences` by normalized
  text (citation tokens stripped via `_CITATION_TOKEN_RE`, whitespace collapsed, lowercased);
  for any 2+ identical-text occurrences, the SURVIVOR is the one with the SUPERSET citation set
  (ties→earliest), and a duplicate is dropped by INDEX only when its cite-set ⊆ survivor's and
  it is not any build_groups primary. Byte-identical text ⇒ same claim ⇒ zero false-merge risk;
  the architecture's deliberate intra-section numeric DISTINCT-claim protection (different text
  sharing a number) is untouched. Drops still go through the single index-keyed `drop_idx`.
- **iter-2 P2 (stale caller comment / unused LLM bridge):** FIXED. Removed the dead
  `_contract_dedup_llm_callable` closure; caller now passes `dedup_llm_callable=None` with an
  updated comment describing the keep-first-verbatim path.
- **NEW validation (VM, full prod flags):** 6/6 stress PASS — PROSE x3→1; NUMERIC verbatim
  x3→1 (the iter-2 gap); whitespace-variant dup collapses; NUMERIC distinct-number NOT merged
  (faithfulness); exact-dup keeps superset-cite occurrence (no source lost); superset-first
  keeps superset/drops subset. Gold regression: 60% collapse, 0 true-keep dropped.

## ITER-2 CHANGES (addressing your iter-1 findings — both fixed)
- **iter-1 P1 (exact duplicates cannot collapse):** FIXED. Drops are now keyed by OCCURRENCE
  INDEX (`SentenceLocation.index`, which all three clusterer paths set per-occurrence from
  `enumerate(section_list)`), not by sentence string. The section list is positionally aligned
  with `kept_sentences` (index i ↔ kept_sentences[i]). Guards: drop only when `r.index !=
  primary.index` AND `r.index not in primary_idxs` (the set of ALL groups' primary indexes, so
  no verbatim primary is ever dropped even by a cross-path group) AND cite-set ⊆ AND nums ⊆.
  The `sv_by_sentence` string-keyed dict (which silently lost duplicate-string SVs) is removed.
- **iter-1 P2 (stale docstring):** FIXED. Docstring rewritten to describe keep-first-verbatim
  index drops; the removed `dedup_pass`/re-verify flow is gone from it.
- **NEW validation (VM, full production flags):** exact-dup stress — `[A,A,A,B]`→`[A,B]`
  (operator's ×17-verbatim case collapses); `[A, A+extra_cite]`→both kept (faithfulness:
  redundant carrying an extra citation is NEVER dropped); `[A+extra_cite, A]`→keep the superset,
  drop the subset (no citation lost). Gold regression unchanged: 56% collapse, 0 true-keep dropped.

---
ORIGINAL iter-1 BRIEF BELOW (context unchanged except the diff is now index-based):

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

REVIEW MODE: STATIC review only. Do NOT run pytest, do NOT run the pipeline, do NOT request user input, do NOT explore the repo broadly. Read the diff below and the one function it changes. Emit the verdict schema at the end.

# I-wire-014 #4b — contract-section repetition keep-first-verbatim dedup

## What this fixes
GH #1336. On the contract path (`contract_section_runner.py`), degenerate intra-section
restatements were NOT collapsing. Forensic reconfirm2 showed
`Empirical_Displacement` section with "probability of computerisation" restated x17
(and the exposure-measure sentence, identification-strategy sentence, etc.).

## Root cause (PROVEN)
`_consolidate_contract_section_sentences` previously called `fact_dedup.dedup_pass`,
whose LLM cross-reference REWRITE drifts on the *terse contract slot* sentences and
then FAILS `strict_verify`. The Codex-gated P1 fallback (correctly) reverts the whole
cluster to the originals on any failed rewrite. Net effect: on the contract path EVERY
cluster reverted and NOTHING collapsed. (The multi_section path's fuller prose survives
the rewrite, which is why FIX-D works there but the same call fails on contract slots.)

## The fix (keep-first-VERBATIM, NO LLM rewrite)
Use the redundancy GROUPS directly (`build_groups` = the gated Jaccard + bidirectional-NLI
prose clusterers — the SAME clusterers the certified multi_section path uses) and KEEP
the PRIMARY restatement VERBATIM. The primary already passed upstream `strict_verify`, so
it can NEVER fail a re-verify (there is no rewrite). DROP only a redundant whose
- citation SET is a SUBSET of the primary's (`_cite_set(r) <= p_cites`), AND
- numbers are a SUBSET of the primary's (`_num_set(r) <= p_nums`).

Because the kept primary already carries every citation and every number the dropped
redundant had, §-1.3 CONSOLIDATE-KEEP-ALL holds: nothing distinct, cited, or numeric is
ever lost, the cluster collapses to one verbatim sentence, and there is no rewrite that
can fail the faithfulness gate. `strict_verify` / NLI / 4-role / span-grounding: UNCHANGED.

## The diff (the ONLY code change — INDEX-based + exact-occurrence pass, iter-3)
READ the committed diff: `.codex/I-wire-014/contract_repetition.diff` (272 lines, 1 file) — it is
the AUTHORITATIVE source and includes the iter-3 exact-occurrence pass below.
Exact-occurrence pass (added iter-3, runs after the build_groups index loop, before telemetry):
```python
    from .fact_dedup import _CITATION_TOKEN_RE as _cite_strip_re   # added to the import block
    def _exact_norm(_s):
        return " ".join(_cite_strip_re.sub(" ", _s).split()).lower()
    by_norm = {}
    for i, sv in enumerate(kept_sentences):
        by_norm.setdefault(_exact_norm(sv.sentence), []).append(i)
    for norm_text, idxs in by_norm.items():
        if not norm_text or len(idxs) < 2: continue
        cites_by_idx = {i: _cite_set(kept_sentences[i].sentence) for i in idxs}
        survivor = max(idxs, key=lambda i: (len(cites_by_idx[i]), -i))   # superset cites, tie->earliest
        s_cites = cites_by_idx[survivor]
        for i in idxs:
            if (i != survivor and i not in drop_idx and i not in primary_idxs
                    and cites_by_idx[i] <= s_cites):
                drop_idx.add(i)
```
Key build_groups index logic (iter-2, unchanged):
```python
    sentence_strs = [sv.sentence for sv in kept_sentences]            # aligned: index i <-> kept[i]
    sections_for_dedup = {section_title: sentence_strs}
    from .fact_dedup import (build_groups as _build_groups, _nli_cite_set as _cite_set, _nli_num_set as _num_set)
    n_kept = len(kept_sentences)
    groups = _build_groups(sections_for_dedup, section_order=[section_title])
    primary_idxs = {g.primary.index for g in groups
                    if g.primary.section == section_title and 0 <= g.primary.index < n_kept}
    drop_idx = set(); n_groups_used = 0
    for g in groups:
        primary = g.primary
        if primary.section != section_title or not (0 <= primary.index < n_kept): continue
        p_cites = _cite_set(primary.sentence); p_nums = _num_set(primary.sentence)
        grp_dropped = 0
        for r in g.redundants:
            if (r.section == section_title and 0 <= r.index < n_kept
                and r.index != primary.index and r.index not in primary_idxs
                and r.index not in drop_idx
                and _cite_set(r.sentence) <= p_cites and _num_set(r.sentence) <= p_nums):
                drop_idx.add(r.index); grp_dropped += 1
        if grp_dropped: n_groups_used += 1
    telemetry = {"n_groups": n_groups_used, "n_redundants": len(drop_idx),
                 "n_rewrites_applied": 0, "n_rewrites_verified_drop": 0,
                 "contract_dedup_mode": "keep_first_verbatim"}
    if not drop_idx: return list(kept_sentences), telemetry
    new_kept = [sv for i, sv in enumerate(kept_sentences) if i not in drop_idx]
    return new_kept, telemetry
```

## Validation evidence (VM, full production flag set PG_CONSOLIDATION_NLI=1 +
PG_CONSOLIDATION_NLI_PROSE=1 + PG_FACT_DEDUP_PROSE=1, on the iwire014 dedup_gold)
- repeats=23, collapsed=13 (56%) — matches the certified multi_section path's ~50%.
- TRUE-keep dropped = 0. (One gold item flagged was the proven `**Tension** <same sentence>`
  chrome-prefixed exact duplicate whose citations [4,5,6] are a SUBSET of the primary's
  [4,5,6,7] — i.e. a gold MISLABEL, no source lost; reclassified by an objective
  chrome-strip + citation-subset rule, not hand-picking.)

## Things to verify (be adversarial)
1. FAITHFULNESS: can this drop a genuinely-distinct claim? The drop requires (a) the NLI/
   Jaccard clusterer put r in primary's `.redundants` (same-claim proven), AND (b) r's
   citations ⊆ primary's, AND (c) r's numbers ⊆ primary's. Is there ANY path where a
   distinct claim or a unique citation/number is lost? If yes → P0/P1.
2. The kept primary is the upstream-verified SV verbatim — confirm no re-verify is needed
   and none is skipped that should run.
3. `_cite_set` / `_num_set` are imported as private names from fact_dedup. Confirm they
   operate on the PRE-resolve `[#ev:id:start-end]` / `[N]` token forms present in
   `sv.sentence` here (the contract SVs carry pre-resolve tokens).
4. The function still takes `strict_verify_fn` and `dedup_llm_callable` params, now UNUSED.
   They are intentionally retained for call-site stability; the caller's
   `_contract_dedup_llm_callable` closure constructs nothing until invoked (it is never
   invoked now) — zero cost. Acceptable, or do you require their removal? (Classify
   severity honestly — this is cosmetic unless it causes a real cost/behavior issue.)
5. Telemetry keys consumed by the caller (line ~1492): `n_groups`, `n_redundants`,
   `n_rewrites_applied`, `n_rewrites_verified_drop` — all still present?
6. The outer gate `_contract_dedup_enabled()` (PG_FACT_DEDUP_PROSE OR PG_CONSOLIDATION_NLI_PROSE)
   is unchanged; default-OFF ⇒ this block self-skips. Confirm no behavior change when OFF.

## Output schema (REQUIRED, last lines)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
