# FORENSIC VERDICT — content_integrity_deletion_gate (WIP, /home/polaris/wt/faithoff)

**Auditor:** Fable (faithfulness/corpus-subtraction counterweight) — read/run only, no repo files modified.
**Date:** 2026-07-24

## VERDICT: SAFE-TO-BASELINE (operator-authorized under §-1.3.1; judge-only; fail-open; anchors exempt; faithfulness engine untouched) — with two minor residual notes for the record, neither blocking.

Critically: **the WIP diff is NOT new gate logic.** The gate logic was already committed at HEAD as
`junk_deletion_gate.py`; the uncommitted work is a pure RENAME:

- `git show HEAD:src/.../junk_deletion_gate.py` vs untracked `content_integrity_deletion_gate.py` diff =
  exactly 3 hunks: function rename `is_row_content_junk` → `is_row_content_integrity_violation`, a
  backward-compat alias `is_row_content_junk = is_row_content_integrity_violation` (:120-124), and one
  log-prefix string. **Zero behavior change.**
- `junk_deletion_gate.py` is now a 28-line shim that does `sys.modules[__name__] = _canonical`
  (:28) — the old name IS the same module object, same globals. Confirmed a true alias, not a copy.
- The `multi_section_generator.py` diff is ONE line (:12045): the import path renamed. The call site
  `is_row_deletable_offtopic(_row)` at :12060 is committed code.

So the re-baseline champion runs the SAME deletion behavior as HEAD whether or not this WIP is included.

---

## 1. What the two deletion classes actually delete

**(a) Chrome non-sources** — `is_row_content_integrity_violation` (gate :105-117) fires ONLY on an
upstream stamp `row["content_integrity_junk"]` (truthy, non-off-token). The stamp is set at the
run-level seam (`run_honest_sweep_r3.py:~15860-15905`) by `detect_content_integrity_junk`
(`src/tools/access_bypass.py:916`): block_page / empty / 404 / cookie_error / login_wall /
nonarticle_stub, judged from title+body, with a **>=200-char body guard** (:952 — any substantial
Zyte-recovered body ⇒ NOT junk regardless of a stale bot title), an `is_row_genuinely_recovered`
skip, and one final Zyte re-fetch attempt (`PG_JUNK_DELETE_FINAL_ZYTE`, default ON) before stamping.
This is lexical, but §-1.3.1(a) explicitly authorizes exactly this class (failed fetches, not sources),
and the operator's recover-before-delete directive is honored in code.

**(b) Confirmed-off-topic sources** — `is_row_deletable_offtopic` (:163-209) fires ONLY on the topic
judge's affirmative OFF_SUBJECT stamp (`topic_off_subject is True` or verdict string `OFF_SUBJECT`,
`_stamped_off_subject` :146-160). The judge is a semantic LLM classifier
(`topic_relevance_gate.classify_topic_relevance`, prompt at :280-315: three-way ON / OFF_ASPECT /
OFF_SUBJECT, "if unsure choose OFF_ASPECT", legacy bare OFF parses as OFF_ASPECT :479-481 —
conservative).

## 2. Safety story — TRUE in code, verified by execution

Ran the predicates on adversarial fixtures (direct module load; all 20 checks pass):

- **Fail-open**: no verdict / missing field / non-Mapping row / predicate exception ⇒ KEEP (:187-209, :109-117). Confirmed.
- **Judge-only**: `content_relevance_label` `demoted`/`escalated_demoted` (reranker/weight labels) can
  NEVER delete (:192-194 checks only the positive set; `_stamped_off_subject` never reads weight
  labels). `OFF_ASPECT` and legacy `topic_offtopic_demoted` can NEVER delete. Confirmed on fixtures.
- **Positive-relevance veto**: `relevant`/`escalated_relevant` vetoes even against an OFF_SUBJECT
  stamp (:193-194). Confirmed.
- **No lexical/tier/number path** for off-topic: none exists in the default path. T7 on-topic row KEPT
  in partition fixture. The banned weight-label path (`is_row_confirmed_offtopic`, the one that deleted
  197 on-topic rows in I-deepfix-003) is reachable ONLY behind `PG_DELETE_OFFTOPIC_TOPIC_JUDGE_ONLY=0`
  (:259-263); **no script/env in the repo sets any PG_DELETE_* flag** — defaults (safe path) govern.
- **Anchors exempt**: `partition_rows` exempt_ids checked before any predicate (:245-248); run-level
  caller passes marquee anchors + `v30_entity_id` rows (`run_honest_sweep_r3.py:15925-15930`).
  Confirmed: exempt row with a fresh OFF_SUBJECT stamp is KEPT.
- **Freshness (Fix 2)**: stale snapshot stamp not in this run's `_fresh_off_subject_ids`
  (built :13964-13969 from THIS run's judge output only) demote-KEEPs. Confirmed.
- **Disclosed**: every deletion carries `deletion_reason`, per-row disclosure record with signal +
  judge-verdict trail + tier (:306-329); run-level commit is atomic (disclosure computed before the
  pruned pool is committed, `run_honest_sweep_r3.py:15938-15960`).

**Can any path delete a good source?** Exactly one: the LLM topic judge issues a confident but WRONG
OFF_SUBJECT verdict on a non-anchor row that carries no positive relevance label, in the same run.
That is the irreducible residual of any semantic filter — it is precisely the risk §-1.3.1(b)
authorizes ("Judge verdict ONLY, FAIL-OPEN"), it is per-row disclosed in the manifest, and every
structural path to the historical 197-row over-deletion is closed by default.

## 3. Faithfulness

- Gate imports: `logging`, `os`, `typing` only (lazy `weighted_enrichment._is_confirmed_offtopic` on
  the OFF legacy path only). **No import/touch of `provenance_generator.py` or
  `clinical_generator/strict_verify.py`.** WIP diff stat contains no faithfulness-engine file.
- GHOST_BAN mechanical grep on the gate: 2 hits, both doc lines naming entailment/weight labels **to
  exclude them as delete triggers** — permitted "naming-to-exclude" hits. No admission/binding/
  post-gen apparatus. All five structural checks pass (no emitted-vs-admitted compare, no
  producer-to-render content-drop predicate — deletion is strictly BEFORE generation, no frozen-module
  import, no admission-field dataclass).
- The shrink-only claim is **correct and monotone**: removing a row from `evidence_for_gen` before
  generation can only reduce the set of verifiable anchors; it can never make a claim PASS
  strict_verify that would otherwise fail. (Moot in practice for the champion: `run_raw_a.sh` runs
  `PG_STRICT_VERIFY_OFF=1`.)
- Classification: **PRE-generation pool curation** (run-level seam sits after topic judge/re-tier,
  before snapshot save + generator; compose-time use shapes section routing before the section LLM
  calls). Not a post-generation edit. Allowed class, operator-authorized.

## 4. Corpus-subtraction vs scope-contract

Yes, it subtracts from the built pool rather than excluding at SEARCH — but that is exactly the shape
§-1.3.1 (CLAUDE.md :67-73, operator-authorized 2026-07-09) explicitly carves out: chrome non-sources
and semantically-confirmed OFF_SUBJECT whole sources, judge-only, fail-open, disclosed. The gate does
not overreach: OFF_ASPECT (same subject, wrong aspect) demote-keeps; credible on-topic low-tier rows
are untouchable; off-topic SPANS are handled at compose per the rule, not here. The compose-time
router leg additionally only affects PLACEMENT (an all-OFF_SUBJECT orphan basket / OFF_SUBJECT
singleton is not given a section home, `verified_compose.py:3952-3957, 3977-3980`) — those rows stay
in the pool/provenance; that is weaker than deletion.

## 5. RACE direction

Expected **helps or neutral**:
- Chrome deletions remove zero real content (failed fetches) while cleaning the bibliography and
  per-claim corroboration counts → Readability/credibility up, Comprehensiveness unaffected (nothing
  citable was lost), FACT unsupported-cite pressure down.
- OFF_SUBJECT deletions remove sources that cannot earn Comprehensiveness credit against the research
  question (RACE judges relative to the query); removing them sharpens on-topic focus (Insight/IF).
  Risk of lost coverage exists only via a judge false positive (bounded as in §2).
- The SAME wiring's other half is coverage-ADDITIVE: the router gives unassigned T1-T3 singletons
  (Acemoglu-Restrepo/Autor class) a compose-time home — that is the pro-Comprehensiveness side of
  this seam.
- FACT supported-pair count could tick down marginally if an off-topic row previously produced
  verifiable pairs, but per the batch-1 finding the rate is the honest metric and junk-anchored pairs
  are what depress it.

## 6. Wired + active under the champion

Confirmed: `PG_ROUTE_ALL_BASKETS` defaults to `'1'` in `config_defaults.py:803` (single-sourced;
`run_raw_a.sh:49` intentionally does not override), so `route_all_baskets_enabled()` is TRUE and the
compose-time leg at `multi_section_generator.py:12044-12078` runs in the champion. The run-level
`partition_rows` seam (`run_honest_sweep_r3.py:15932`) is committed, default-ON, and identical with
or without this WIP.

## Residual notes for the operator (non-blocking)

1. **Compose call site omits `fresh_off_subject_ids` and `exempt_ids`** (`multi_section_generator.py:12060`
   calls `is_row_deletable_offtopic(_row)` bare) — on a RESUME from an old corpus_snapshot, a stale
   OFF_SUBJECT stamp can exclude a row from orphan ROUTING (not from the pool). Zero impact on a
   fresh baseline run (all stamps are fresh); anchors are separately protected by the topic judge's
   own anchor exemption and by already sitting in plans' ev_ids. Cosmetic inconsistency with Fix-2
   intent; worth a follow-up, not a baseline blocker.
2. If the operator wants an ON/OFF ablation anyway, the clean lever is
   `PG_DELETE_CHROME_NONSOURCE=0 PG_DELETE_OFFTOPIC_SOURCE=0` (verified byte-identical no-delete on
   fixtures) — but since the gate is committed at HEAD and defaults ON, "OFF" is the deviation from
   the standing champion recipe, not "ON".
3. Guard for the baseline env: never set `PG_DELETE_OFFTOPIC_TOPIC_JUDGE_ONLY=0` — that resurrects
   the 197-row weight-label deleter. Currently nothing in the repo sets it.
