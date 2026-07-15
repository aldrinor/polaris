# S2/S3 metadata-loss post-mortem (root cause)

**Verdict: the DOI/journal/tier extractor for the S2/S3 path was NEVER WRITTEN.**
Not written-but-uncalled, not silently-excepted, not populated-then-dropped. The S2 SELECT+WEIGH
stage and the S3 CONSOLIDATE stage carried each row's `direct_quote` + `source_url` (which contain
the DOI and the journal name) end-to-end but never parsed them into the `doi` / `journal` / `tier`
fields. Rows entered with those fields blank and left with them blank. Completely silent — nothing
failed, nothing warned, and the stage summaries did not even *measure* DOI/journal/tier population.

All line numbers below are the **committed HEAD** of `/home/polaris/wt/s2s3` (the bug state). The
working tree is currently being edited by the fix wheel (it adds `enrich_row_metadata` +
`src/polaris_graph/retrieval/source_metadata.py`, which are untracked/new), so read HEAD to see the
defect, not the working tree.

---

## The mechanism, at file:line

### S2 — `scripts/s2_select_replay.py` (HEAD)
S2 builds the cp2 kept-row pool in one loop and **applies no metadata enrichment at all**:

- Line 248–252 — pass-through rows (`res is None`) are appended RAW:
  ```py
  for row in rows:
      ...
      if res is None:
          kept_rows.append(row)          # raw row, no enrichment
  ```
- Line 268 — screened rows get only a body rewrite + sidecar:
  ```py
  kept_rows.append(ls.apply_result_to_row(row, res))
  ```
- There is **no import of any metadata extractor** at HEAD (no `source_metadata`, no
  `enrich_row_metadata`). `apply_result_to_row` is defined in
  `src/polaris_graph/retrieval/line_screen.py:1361-1386` and does exactly two things: rewrites the
  widest body field to the kept lines and attaches `new_row["line_screen"] = result.sidecar()`. It
  copies the row with `dict(row)`, so it **preserves** any doi/journal already present but **never
  derives** them. It touches doi/journal/tier nowhere.

Net: S2 was purely a body screener. The DOI sitting in `source_url`
(`.../doi/10.1257/jep.33.2.3`) and the "Journal of Economic Perspectives" string in `direct_quote`
were in hand on every row and never read.

### S3 — `scripts/s3_consolidate_replay.py` (HEAD)
S3 only *reads back* the fields S2 never populated, and hard-codes the wrong default:

- Line 101–102 — the tier accessor:
  ```py
  def _tier(i):
      return (str(rows[i].get('tier', '') or 'UNKNOWN')) if 0 <= i < len(rows) else 'UNKNOWN'
  ```
  This is a **wrong-default**: any row whose `tier` is blank/missing is silently coerced to
  `'UNKNOWN'`, even when the domain (`aeaweb.org`, `tandfonline.com`, `nber.org`, …) makes the tier
  trivially derivable. That single `or 'UNKNOWN'` is why 253/995 read UNKNOWN.
- There is **no `_doi` and no `_journal` accessor at HEAD, and no `member_dois` / `member_journals`
  in the basket dict** — DOI and journal were never even surfaced to the basket level. S3 could not
  have propagated metadata it never looked at.

So the two stages compose into: never-extract (S2) → read-blank-and-default-to-UNKNOWN (S3).

---

## Why it was totally silent
- HEAD S2 `summary.json` and HEAD S3 `consolidation_summary` had **no DOI/journal/tier lock-bar** —
  no `metadata_enrichment_summary`, no `corpus_metadata_summary`. (Confirmed: the shipped
  `outputs/s2s3_repass/s2/cp2_corpus_snapshot.json` has `metadata_enrichment_summary` absent, and
  `outputs/s2s3_repass/s3/cp3_basket_snapshot.json` has no `corpus_metadata_summary` and baskets
  with no `member_dois`.) The stages never asserted anything about metadata, so blank fields were
  indistinguishable from a healthy run.
- Nothing raised or warned. There is no code path that even *attempts* extraction, so there was no
  exception to swallow.

## Not "dropped in transform"
The ~5 rows that *did* arrive with metadata upstream (e.g. `acemoglu_restrepo_automation_tasks`
carries `doi=10.1257/jep.33.2.3`, `journal=Journal of Economic Perspectives`, `tier=T1`) flowed
through S2/S3 **intact** — `dict(row)` in `apply_result_to_row` preserves them. So the loss is not a
transform/serialization drop of populated fields; it is a total absence of population for the
~99.5% of rows that entered blank. Measured on the cp2 that fed the reported cp3:
728 rows, only 5 with `doi`, only 5 with `journal`, 177 `UNKNOWN`; **723 blank-doi rows, of which
156 have a DOI directly regex-recoverable from their own `source_url`/`direct_quote`** and far more
have a domain-derivable journal — exactly what the downstream repair pass recovered.

## Proof the data was in hand
`repair_corpus_metadata.py` (the proven recovery) does nothing S2/S3 couldn't have done inline: one
DOI regex over `direct_quote`+`source_url`, a domain→venue map, a journal-name regex over the quote,
and a domain→tier map. It lifted doi 3→240, journal 3→294, UNKNOWN 253→145. The inputs it used
(`direct_quote`, `source_url`, `title`, domain) are the same fields S2 already had on every row at
line 253 and S3 had at every `rows[i]` accessor. Nothing needed re-fetching.

---

## Other spots in S2/S3 that can silently drop data the same way
1. **`scripts/s3_consolidate_replay.py:102` — `_tier(...) or 'UNKNOWN'`** — the wrong-default itself;
   any future missing tier is silently laundered into UNKNOWN rather than surfaced.
2. **`scripts/s2_select_replay.py` topic-judge `except Exception` (fail-open, ~line 221 working
   tree / HEAD equivalent)** — on any judge error it prints and continues with zero off-subject
   stamps; a real defect degrades silently to "kept everything, stamped nothing".
3. **`scripts/s3_consolidate_replay.py` `_stmt` bare `except Exception` around
   `extract_numeric_claims` (~line 142)** — swallows extraction failures and silently falls back to
   a weaker representative sentence with no disclosure.
4. **`scripts/s3_consolidate_replay.py` `_nli_score_stats` `except Exception` (~line 63)** — returns
   `{'available': False}`; the semantic-merge telemetry can silently vanish.
5. **`scripts/s3_consolidate_replay.py` unified-deletion-disclosure `except Exception` (~line 351)** —
   swallows S2 `summary.json` read/parse errors into an `{'error': ...}` blob rather than failing.
6. **Row schema by omission** — blank rows do not even carry a `doi`/`journal` key (e.g. `ev_454`
   has neither key, only `tier`). Every consumer using `.get('doi','')` sees empty and no S2/S3 code
   backfills, so the gap is invisible unless someone measures population — which HEAD never did.

## Fix direction (already being applied by the wheel, for reference)
Run the deterministic extractor at the S2 stamp site so cp2 carries correct doi/journal/tier, and
add a DOI/journal/tier population lock-bar to both stage summaries so a blank corpus fails loud
instead of looking fine. The working tree already wires `enrich_row_metadata`
(`src/polaris_graph/retrieval/source_metadata.py`) into `s2_select_replay.py:248-257` and adds
`member_dois`/`member_journals` + `corpus_metadata_summary` to `s3_consolidate_replay.py`.

---

# PREVENTION — a fail-loud, query-agnostic metadata invariant

## The gap that still remains after the wheel's fix
The wheel restored the extractor and added lock-bar **measurements**
(`metadata_enrichment_summary` in `s2_select_replay.py:275-299`, `corpus_metadata_summary` in
`s3_consolidate_replay.py:223-251`). But those blocks only **count and print** — grep for
`assert`/`raise`/`FAIL` around them returns nothing. A measurement is not a guard: a run that
silently reverts the extractor (import removed, call skipped, a refactor that drops the
pass-through branch) still writes a summary and passes. Worse, you **cannot** turn the counts into
a guard with a threshold, because population is query-dependent: a legitimate finance/policy corpus
can correctly have very few DOIs. A threshold on `doi_populated` would false-fire on honest
non-journal corpora and still miss a partial regression. The guard must be **per-row structural**,
not aggregate.

## The invariant (structural residual, recomputed independently)
Re-derive the structural signal from each row's OWN `direct_quote`/`source_url` using the SAME
detector the extractor uses, then assert the extracted field is populated. Two rules, both
query-agnostic (DOI regex + domain class only — zero topic keywords):

- **R1 (DOI residual = 0):** if `DOI_RE.search(direct_quote OR source_url)` matches, then `doi`
  MUST be non-empty. A match with an empty `doi` means enrichment never ran on that row.
- **R2 (known-journal-domain tier residual = 0):** if `domain_of(url)` is in `DOMAIN_TIER`
  (the known scholarly/gov/venue set), then `tier` MUST NOT be `UNKNOWN`/blank.

Because the invariant recomputes with the **exact same `DOI_RE` / `DOMAIN_TIER`** the extractor
uses, extractor and check can never disagree by construction: a non-zero residual is a proof that
`enrich_row_metadata` did not run (or was bypassed) on those rows — i.e. it reproduces the HEAD
bug's signature directly. It FAILS LOUD with the offending counts and a few example evidence_ids.

```python
# src/polaris_graph/retrieval/source_metadata.py  (add next to enrich_rows)
def assert_metadata_invariants(rows, *, stage: str) -> dict:
    """FAIL LOUD if any row structurally carries a DOI but has doi blank, or sits on a known
    journal/venue domain yet is tier=UNKNOWN. Query-agnostic: DOI regex + domain class only.
    Raises SystemExit (non-zero) with offending counts + example ids. Returns the audit dict on pass."""
    doi_viol, tier_viol = [], []
    for r in rows:
        if not isinstance(r, dict):
            continue
        url = str(r.get('source_url') or r.get('url') or '')
        quote = str(r.get('direct_quote', '') or '')
        if extract_doi(quote, url) and not str(r.get('doi', '') or '').strip():
            doi_viol.append(str(r.get('evidence_id', '')))
        if domain_of(url) in DOMAIN_TIER and str(r.get('tier') or 'UNKNOWN') == 'UNKNOWN':
            tier_viol.append(str(r.get('evidence_id', '')))
    audit = {'stage': stage, 'n_rows': len(rows),
             'doi_residual_violations': len(doi_viol), 'tier_residual_violations': len(tier_viol)}
    if doi_viol or tier_viol:
        raise SystemExit(
            f"[{stage}] METADATA INVARIANT VIOLATED — extractor did not run on all rows.\n"
            f"  rows with a DOI in their own quote/url but doi BLANK: {len(doi_viol)} "
            f"(e.g. {doi_viol[:8]})\n"
            f"  rows on a known-journal domain but tier=UNKNOWN:      {len(tier_viol)} "
            f"(e.g. {tier_viol[:8]})\n"
            f"  This is the S2/S3 silent-metadata-loss class. Enrich before banking the corpus.")
    return audit
```

## WHERE it runs — so it fires on EVERY future corpus build
Call it at **both** stage boundaries, on the exact pool that gets banked, guaranteeing coverage no
matter which stage a future regression lands in:

1. **S2 — `scripts/s2_select_replay.py`**, immediately after the lock-bar block (right after
   line 293, before `cp2["evidence_for_gen"] = kept_rows` at ~297): 
   `cp2["metadata_invariant"] = assert_metadata_invariants(kept_rows, stage="s2")`.
   This gates cp2 at the write site — the pass-through branch (the original blank-row source) is
   inside `kept_rows`, so a dropped/bypassed enrich cannot slip a blank corpus to disk.
2. **S3 — `scripts/s3_consolidate_replay.py`**, right after `corpus_metadata_summary` is built
   (after line 251, before consolidation output): 
   `assert_metadata_invariants(rows, stage="s3")` over the full cp2 evidence pool S3 consumed.
   This catches the case where cp2 was produced by an OLD/rogue S2 that predates the guard — S3
   refuses to consolidate a structurally-blank corpus rather than laundering blanks into UNKNOWN
   at `_tier(...) or 'UNKNOWN'`.

## Proof it is query-agnostic and catches the exact failure (measured, this pipeline)
Ran the R1/R2 residual over all 7 shipped `cp2_corpus_snapshot.json` on disk:

| corpus | enrich_summary | R1 DOI residual | R2 tier residual | legit no-DOI rows (must NOT trip) |
|---|---|---|---|---|
| s2s3_repass/s2 (the reported bug corpus) | absent | **156** | **47** | 570 |
| s2s3_i1/s2 | absent | **240** | **52** | 754 |
| s2s3_i3/s2 | absent | **172** | **46** | 480 |
| s2s3_iter1/s2 | absent | **173** | **48** | 479 |
| s2s3_repass/iter6/s2 | absent | **151** | **45** | 569 |
| s2s3_repass/iter7/s2 | absent | **140** | **44** | 545 |
| s2s3_meta/s2 (post-fix, enriched) | present | **0** | **0** | 698 |

Every bug-state corpus trips the guard (140–240 DOI + 44–52 tier residuals → hard SystemExit); the
enriched corpus reads 0/0 and passes. The signals are purely structural (`10.\d{4,9}/…` DOI regex
and a domain set), so this holds identically for a finance, medical, or any other query — a medical
DOI `10.1056/NEJM…` on `pmc.ncbi.nlm.nih.gov` is caught by the same rule that catches
`10.1257/jep.33.2.3` on `aeaweb.org`. No topic keyword appears anywhere in the check.

## False-positive risk (bounded, and measured to zero here)
- **A genuine non-journal source correctly having no DOI does NOT trip R1.** R1 fires *only* when a
  DOI is literally present in the row's own text/url. The 480–754 "legit no-DOI" rows per corpus
  above (blogs, press releases, gov landing pages) are all silently accepted — confirmed 0 false
  positives.
- **R2 is a whitelist, so unknown domains never false-fire.** A finance/medical domain not yet in
  `DOMAIN_TIER` simply isn't checked by R2 (it is still fully protected by the universal R1). The
  only residual R2 risk is a known-journal domain whose specific URL is a non-article page (a
  publisher's "About" page) — acceptable, because tiering that host as its publisher tier is still
  defensible, and the extractor assigns it deterministically so check and extractor agree.
- **Extractor/check can never disagree by construction** (shared `DOI_RE`/`DOMAIN_TIER`), so the
  guard has no independent-regex drift class of false positive.

## Regression test (reproduces the HEAD failure; keeps catching it)
Place at `tests/test_s2s3_metadata_invariant.py`. It builds a row set that mirrors the exact bug
(Acemoglu-class row: DOI in `direct_quote`, JEP on `aeaweb.org`, but `doi`/`journal` blank and
`tier` absent) plus a legitimate DOI-less blog row, then asserts three things.

```python
import pytest
from src.polaris_graph.retrieval.source_metadata import (
    enrich_row_metadata, assert_metadata_invariants)

BUGGY = [
    {   # the exact HEAD failure: metadata in hand, fields blank
        'evidence_id': 'ev_acemoglu',
        'source_url': 'https://www.aeaweb.org/articles/doi/10.1257/jep.33.2.3',
        'direct_quote': 'Published in the Journal of Economic Perspectives (DOI 10.1257/jep.33.2.3) ...',
        # no 'doi', no 'journal', no 'tier'  <-- the bug state
    },
    {   # query-agnostic: a MEDICAL DOI on a medical domain, same blank state
        'evidence_id': 'ev_nejm',
        'source_url': 'https://pmc.ncbi.nlm.nih.gov/articles/PMC123/',
        'direct_quote': 'randomized trial ... doi:10.1056/NEJMoa2035389 ...',
    },
    {   # FALSE-POSITIVE GUARD: a legit non-journal source with genuinely no DOI must NOT trip
        'evidence_id': 'ev_blog',
        'source_url': 'https://example-startup.com/blog/our-take',
        'direct_quote': 'We think AI will change hiring. No DOI here.',
    },
]

def test_head_bug_state_fails_loud_without_enrichment():
    # BEFORE the fix (extractor never ran): the invariant MUST fail loud, naming the counts.
    with pytest.raises(SystemExit) as e:
        assert_metadata_invariants([dict(r) for r in BUGGY], stage="s2")
    msg = str(e.value)
    assert "doi BLANK: 2" in msg and "tier=UNKNOWN: 2" in msg  # 2 scholarly rows, blog excluded

def test_enrichment_then_invariant_passes():
    rows = [enrich_row_metadata(dict(r)) for r in BUGGY]
    audit = assert_metadata_invariants(rows, stage="s2")   # must NOT raise
    assert audit['doi_residual_violations'] == 0 and audit['tier_residual_violations'] == 0
    assert rows[0]['doi'] == '10.1257/jep.33.2.3' and rows[0]['journal'] == 'Journal of Economic Perspectives'
    assert rows[1]['doi'] == '10.1056/NEJMoa2035389'   # medical DOI recovered — query-agnostic
    assert rows[2].get('doi', '') == ''                # blog stays DOI-less, not invented

def test_blog_never_false_positives():
    # The DOI-less blog alone must always pass, enriched or not.
    assert_metadata_invariants([enrich_row_metadata(dict(BUGGY[2]))], stage="s2")
```

`test_head_bug_state_fails_loud_without_enrichment` is the reproduction: it constructs the precise
HEAD condition (blank doi/journal/tier with metadata present) and proves the guard raises — had
this test existed at HEAD, CI would have been red. `test_enrichment_then_invariant_passes` proves
the fix path is green and is query-agnostic (medical DOI recovered by the same code).
`test_blog_never_false_positives` locks the false-positive boundary so a future tightening can't
start flagging honest non-journal sources.
