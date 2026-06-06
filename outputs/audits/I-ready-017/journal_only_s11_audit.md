# §-1.1 audit — journal_only corpus-quality filter (#1134)

**Standard:** §-1.1 line-by-line on the REAL held drb_72 artifacts (not synthetic
fixtures). The filter is flag-gated default-OFF; the paid live RERUN (which
produces the report-level claim-vs-cited-span §-1.1) is operator-gated. This audit
verifies the FILTER BEHAVIOR claim-by-claim against the real corpus the held
drb_72 run actually produced + fed to the generator.

Artifacts: `outputs/honest_sweep_r3/workforce/drb_72_ai_labor/evidence_pool.json`
(the 23 rows the generator actually saw — the billed set), `manifest.json`
(`/adequacy/tier_counts`, full 242-source corpus), `config/scope_templates/workforce.yaml`
(the real drb_72 report contract). Harness: ran `journal_only_filter` against these.

## Finding 1 — the held billed set was 65% non-journal (the contamination the fix removes)

Of the **23 rows the held drb_72 generator actually saw**, 15 (65%) were
non-journal — exactly the content the locked question forbids ("only ... journal
articles"). journal_only's source-filter DROPS every one, per-row decision:

| evidence_id | tier | decision | reason | url |
|---|---|---|---|---|
| ev_023 | T4 | DROP | tier_not_journal | en.wikipedia.org/wiki/Fourth_Industrial… |
| ev_009 | T6 | DROP | tier_not_journal | **youtube.com/watch?v=…** |
| ev_011 | T5 | DROP | tier_not_journal | anthropic.com/research/labor-market… |
| ev_008 | T4 | DROP | tier_not_journal | preprints.org/manuscript/… |
| ev_022 | T4 | DROP | tier_not_journal | weforum.org/stories/2016/01/the-four… |
| ev_003 | T4 | DROP | tier_not_journal | chicagobooth.edu/review/ai-is-going… |
| ev_020 | T4 | DROP | tier_not_journal | news.harvard.edu/gazette/story/2025/… |
| ev_001 | T4 | DROP | tier_not_journal | budgetlab.yale.edu/research/… |
| ev_014 | T4 | DROP | tier_not_journal | digitaleconomy.stanford.edu/news/… |
| ev_013 | T4 | DROP | tier_not_journal | michaelwebb.co/webb_ai.pdf |
| ev_002 | T4 | DROP | tier_not_journal | laweconcenter.org/resources/… |
| ev_006 | T4 | DROP | tier_not_journal | tcf.org/content/commentary/… |
| ev_025 | T4 | DROP | tier_not_journal | ci.unt.edu/computational-humanities… |
| ev_000 | T7 | DROP | tier_not_journal | sciencedirect.com (stub) |
| ev_021 | UNKNOWN | DROP | tier_not_journal | oecd.org/en/publications/2021/… |

A YouTube video, Wikipedia, and an Anthropic blog post reached the generator in
the held run. journal_only removes all 15.

## Finding 2 — the WEF non-journal contract entity WAS leaking (Codex P1-1, confirmed real)

`fourth_industrial_revolution_framing` (type `policy_report`, S3,
`url_pattern: weforum.org`) **is present in the held billed set** (verified:
v30_entity_id match) — i.e. the WEF non-journal source was reaching the generator
via the contract path, exactly the leak Codex flagged. The contract pruner drops
it. On the real `workforce.yaml` drb_72 contract:

- **kept journal entities (6):** acemoglu_restrepo_automation_tasks, autor_why_still_jobs,
  acemoglu_restrepo_robots_jobs, frey_osborne_computerisation, brynjolfsson_genai_at_work,
  eloundou_gpts_are_gpts
- **dropped non-journal entities (1):** fourth_industrial_revolution_framing (WEF)
- **required-slot conflicts: [] (none)** — the WEF slot `theory_4ir_framing` is
  `required: false`, so it prunes cleanly; no `abort_journal_only_contract_conflict`.

## Finding 3 (BUG caught by this §-1.1, fixed) — adequacy anchor check vs contract-only anchors

3 of the 4 S1 adequacy anchors (Acemoglu-Restrepo JPE `10.1086/705716`,
Brynjolfsson QJE `10.1093/qje/qjae044`, Eloundou Science `10.1126/science.adj0998`)
exist in the held billed set ONLY as V30 contract frame rows (empty `source_url`,
injected AFTER the source-filter gate). A retrieved-only anchor check would
therefore FALSELY abort the RERUN for "missing anchors" the contract guarantees.
Unit tests (synthetic rows with URLs) missed this. **Fix:**
`assess_journal_only_adequacy(..., contract_guaranteed_dois=...)` credits the kept
journal contract entities; verified the anchor `missing` set is now empty for
drb_72. The distinct-journal-COUNT floor still measures retrieved breadth only.

## Finding 4 — distinct-journal floor (full corpus, not the billed 23)

The ≥12-distinct-journal floor is assessed on the full classified corpus, not the
downselected billed 23. The held full corpus (`manifest.json /adequacy/tier_counts`)
had **T1 = 54, T2 = 16 = 70 journal-tier sources** — comfortably above the 12 floor.
On the LIVE path the predicate uses OpenAlex `is_peer_reviewed` directly (the held
artifacts predate the sidecar; this audit reconstructs it conservatively from
doi+journal+tier), so the live citeable count is expected ≥ the reconstruction.

## Faithfulness verdict

The filter does exactly what the journal-restricted question demands: it removes
the 65% non-journal contamination (incl. a YouTube video) that the held run fed
the generator, drops the leaking WEF contract source, keeps the 6 journal anchors,
and fail-closes (uncertain→exclude, required-non-journal-slot→abort, leak→abort,
thin-corpus→abort). No strict_verify / provenance / 4-role / two-family change.
Default-OFF byte-identical. The report-level claim-vs-cited-span §-1.1 runs on the
operator-gated paid RERUN.

## Offline evidence
`pytest tests/polaris_graph/test_journal_only_filter_iready017.py` → 21 passed.
`pytest tests/polaris_graph/retrieval/test_saturation_phase4.py` → 27 passed
(taxonomy). Targeted regression (approval + enforcement + tier) → 48 passed.
py_compile clean. Harness: `/tmp/jo_s11_audit.py` (per-row table above).
