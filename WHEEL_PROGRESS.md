# WHEEL PROGRESS — bot/s2s3-box

## 2026-07-12 — S2/S3 native metadata enrichment + duplicate merge (port of proven repair)

Root cause fixed AT THE SOURCE: S2 left doi/journal blank and mis-tiered good peer-reviewed
sources; the fix now lives in S2 stamping + S3 consolidation (no downstream band-aid).

New: `src/polaris_graph/retrieval/source_metadata.py` — deterministic DOI regex + journal
name/domain->venue map + domain->tier (ported verbatim-equivalent from the proven
outline_agent/scripts/repair_corpus_metadata.py). §-1.3 POPULATE-only: fills EMPTY metadata,
UPGRADES tier only from ''/'UNKNOWN' on a CLEAR signal (has-DOI => >=T2, known domain tier),
NEVER downgrades a real tier, never invents metadata.

Wired into: `line_screen.apply_result_to_row` (the S2 stamp site) + `s2_select_replay.py`
(un-screened pass-through + cp2 `metadata_enrichment_summary`). S3 (`s3_consolidate_replay.py`):
per-basket `member_dois`/`member_journals`, a payload `corpus_metadata_summary`, and a `--no-nli`
flag (deterministic, no-OOM; the same-work DUPLICATE merge is deterministic and unaffected).

MEASURED on the real 999-row corpus (paid_drb72_deep corpus_snapshot.json), S2 --stub
--no-topic-judge -> S3 --no-nli, kept pool 936 rows:

| metric            | before | AFTER | target        | repair floor |
|-------------------|--------|-------|---------------|--------------|
| DOI populated     | 5      | 241   | >=200  PASS   | 240          |
| journal populated | 5      | 339   | >=250  PASS   | 294          |
| tier=UNKNOWN      | 253    | 136   | <=150  PASS   | 145          |
| duplicate rows    | 76     | 90    | (detect)      | 83           |
| dupes MERGED      | —      | 126 members / 71 same-work groups (corroboration, NOT deleted) |

Invariant verified: 0 real-tier downgrades, 111 upgrades from UNKNOWN/empty.
Exemplar recovered: Acemoglu-Restrepo -> doi 10.1257/jep.29.3.3, Journal of Economic
Perspectives, T1 (was blank/UNKNOWN). 7/7 unit tests pass (tests/test_source_metadata_enrichment.py).
Corrected corpus: outputs/s2s3_meta/s3/cp3_basket_snapshot.json.
