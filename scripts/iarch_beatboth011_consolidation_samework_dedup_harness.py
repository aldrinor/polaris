#!/usr/bin/env python3
"""FAIL-LOUD offline harness — I-beatboth-011 #7 CORE same-work consolidation (#1289).

Proves the same-work consolidation in
``src/polaris_graph/synthesis/finding_dedup.py`` BEHAVIOURALLY (not a config /
green-tests proxy — §-1.4): the SAME work appearing at multiple URLs is GROUPED
into ONE unit that KEEPS ALL the URLs as corroborating locators (§-1.3 keep-all)
but COUNTS / PRESENTS as ONE source, never inflating breadth.

Cases (sys.exit(1) LOUDLY on any regression; sys.exit(0) only if ALL pass):
  (a) 4 members, SAME DOI, 4 different URLs  -> ONE same-work unit retaining all
      4 URLs as corroborators (keep-all) and ONE canonical row.
  (b) 2 members, SAME folded title + SAME discriminator (year+author), no DOI
      -> ONE same-work unit (title + discriminator fold).
  (b2) OVER-MERGE NEGATIVE CONTROL (#4): 2 members, SAME folded title but DIFFERENT
      year AND author, no DOI -> NOT merged (title-alone never merges; §-1.3).
  (b3) 2 members, SAME folded title, NO shared discriminator (different hosts) ->
      NOT merged (a title-only fingerprint is not a same-work key).
  (c) a CAPTCHA / anti-bot security stub       -> DROPPED (no real claim).
  (d) two GENUINELY different works (different DOI AND title) -> NOT merged.
  (e) LIVE ACCOUNTING (advisor's required pin): 4 same-work rows asserting the
      SAME numeric finding across 4 DIFFERENT domains -> the finding cluster's
      ``corroboration_count`` counts them as ONE origin (today the raw
      independent-host count would be 4 — that is the breadth inflation #7 fixes).

Run: python scripts/iarch_beatboth011_consolidation_samework_dedup_harness.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Run from anywhere: put the repo root (this file's parent's parent) on sys.path
# so ``import src.polaris_graph...`` resolves without an installed package.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# The same-work fold annotates rows and folds the cluster origin count in BOTH
# modes, but the keep-all (non-rep survive) path is the redesign one — pin it ON
# so the harness exercises the live benchmark configuration.
os.environ.setdefault("PG_SWEEP_CREDIBILITY_REDESIGN", "1")

from src.polaris_graph.synthesis.finding_dedup import (  # noqa: E402
    consolidate_same_work,
    dedup_by_finding,
)

_FAILURES: list[str] = []


def _check(condition: bool, message: str) -> None:
    if not condition:
        _FAILURES.append(message)
        print(f"FAIL: {message}")
    else:
        print(f"ok:   {message}")


def _group_for_index(result, ri: int):
    """The SameWorkGroup that owns original row index ``ri`` (or None)."""
    canon = result.canonical_index_by_index.get(ri)
    if canon is None:
        return None
    for g in result.groups:
        if g.canonical_index == canon:
            return g
    return None


def case_a_same_doi_four_urls() -> None:
    """4 members, SAME DOI, 4 distinct URLs -> ONE unit, all 4 URLs kept."""
    rows = [
        {"evidence_id": "ev_1", "source_url": "https://nber.org/papers/autor",
         "doi": "10.1257/jep.29.3.3", "source_title": "Why Are There Still So Many Jobs",
         "direct_quote": "Autor argues automation complements labor in many tasks."},
        {"evidence_id": "ev_2", "source_url": "https://aeaweb.org/articles/autor",
         "doi": "https://doi.org/10.1257/JEP.29.3.3", "source_title": "Why Are There Still So Many Jobs?",
         "direct_quote": "Autor argues automation complements labor in many tasks across sectors."},
        {"evidence_id": "ev_3", "source_url": "https://jstor.org/stable/autor",
         "doi": "DOI:10.1257/jep.29.3.3", "source_title": "Why Are There Still So Many Jobs",
         "direct_quote": "Automation complements labor in many tasks, Autor finds."},
        {"evidence_id": "ev_4", "source_url": "https://econpapers.org/autor",
         "doi": "http://dx.doi.org/10.1257/jep.29.3.3", "source_title": "Why are there still so many jobs",
         "direct_quote": "Autor: automation complements labor in many tasks economy-wide."},
    ]
    res = consolidate_same_work(rows)
    # Exactly ONE same-work group spanning all 4 rows.
    real_groups = [g for g in res.groups if g.same_work_id.startswith(("doi:", "title:"))]
    _check(len(real_groups) == 1,
           f"(a) 4 same-DOI rows form exactly ONE same-work group (got {len(real_groups)})")
    if real_groups:
        g = real_groups[0]
        _check(g.same_work_id.startswith("doi:"),
               f"(a) the group is keyed by DOI (got {g.same_work_id!r})")
        _check(sorted(g.member_evidence_ids) == ["ev_1", "ev_2", "ev_3", "ev_4"],
               f"(a) keep-all: ALL 4 evidence_ids retained as corroborators (got {sorted(g.member_evidence_ids)})")
        _check(len(g.member_urls) == 4,
               f"(a) keep-all: ALL 4 distinct URLs retained as locators (got {len(g.member_urls)})")
    # All four map to ONE canonical index (count as one source).
    canon_set = {res.canonical_index_by_index.get(i) for i in range(4)}
    _check(len(canon_set) == 1 and None not in canon_set,
           f"(a) all 4 members share ONE canonical index (got {canon_set})")
    _check(not res.dropped_indices,
           f"(a) no member dropped (keep-all) (got dropped={sorted(res.dropped_indices)})")


def case_b_same_title_no_doi() -> None:
    """2 members, SAME folded title, no DOI, but a SHARED discriminator (same
    year AND same first author) -> ONE unit.

    I-beatboth-011 #4 (#1289): the no-DOI branch no longer merges on title ALONE —
    a shared discriminator (here year=2017 + author Frey, on different hosts) is
    required. This is the spec's positive case for the title branch."""
    rows = [
        {"evidence_id": "ev_10", "source_url": "https://site-one.org/frey",
         "source_title": "The Future of Employment: How Susceptible Are Jobs?",
         "year": 2017, "authors": ["Frey C", "Osborne M"],
         "direct_quote": "Frey and Osborne estimate 47 percent of US jobs are at risk."},
        {"evidence_id": "ev_11", "source_url": "https://site-two.org/frey",
         "source_title": "the future of employment   how susceptible are jobs",
         "year": 2017, "authors": ["Frey C", "Osborne M"],
         "direct_quote": "Frey and Osborne estimate that 47 percent of US jobs are at risk of automation."},
    ]
    res = consolidate_same_work(rows)
    real_groups = [g for g in res.groups if g.same_work_id.startswith(("doi:", "title:"))]
    _check(len(real_groups) == 1,
           f"(b) 2 same-title+same-year rows form exactly ONE same-work group (got {len(real_groups)})")
    if real_groups:
        g = real_groups[0]
        _check(g.same_work_id.startswith("title:"),
               f"(b) the group is keyed by folded title + discriminator (got {g.same_work_id!r})")
        _check("|y:2017" in g.same_work_id,
               f"(b) the title key carries the shared YEAR discriminator (got {g.same_work_id!r})")
        _check(sorted(g.member_evidence_ids) == ["ev_10", "ev_11"],
               f"(b) keep-all: both evidence_ids retained (got {sorted(g.member_evidence_ids)})")


def case_b2_same_title_different_discriminator_not_merged() -> None:
    """OVER-MERGE NEGATIVE CONTROL (I-beatboth-011 #4, #1289): two records with the
    SAME folded title but DIFFERENT year AND different first author (and no DOI) are
    two genuinely DIFFERENT works and MUST stay distinct — title-alone never merges.

    Two distinct conference papers can share a generic title ("Deep Learning for
    Vision") yet be unrelated works; collapsing them would lose a distinct
    corroborator (§-1.3 over-merge violation)."""
    rows = [
        {"evidence_id": "ev_t1", "source_url": "https://venue-a.org/dl",
         "source_title": "Deep Learning Methods for Computer Vision",
         "year": 2019, "authors": ["Smith J", "Lee K"],
         "direct_quote": "A 2019 survey of deep learning methods for computer vision tasks."},
        {"evidence_id": "ev_t2", "source_url": "https://venue-b.net/dl",
         "source_title": "deep learning methods for computer vision",
         "year": 2023, "authors": ["Garcia R", "Patel S"],
         "direct_quote": "A 2023 survey of deep learning methods for computer vision tasks."},
    ]
    res = consolidate_same_work(rows)
    c1 = res.canonical_index_by_index.get(0)
    c2 = res.canonical_index_by_index.get(1)
    _check(c1 != c2,
           f"(b2) same-title BUT different year+author => NOT merged (canon idx {c1} vs {c2})")
    real_groups = [g for g in res.groups if g.same_work_id.startswith(("doi:", "title:"))]
    _check(len(real_groups) == 2,
           f"(b2) over-merge guard: same title + different discriminator => TWO works "
           f"(got {len(real_groups)})")
    _check(not res.dropped_indices,
           "(b2) nothing dropped (two clean distinct works, keep-all)")


def case_b2b_single_weak_signal_not_merged() -> None:
    """#4 P2 over-merge negatives (#1289): a SINGLE agreeing weak signal must NOT
    merge two distinct same-title works.

    (a) SAME folded title + SAME year (2020) + DIFFERENT first author, no DOI -> the
        year agrees but the strong signal (author) disagrees -> NOT merged. (The OLD
        first-available rule keyed on year FIRST and would have WRONGLY merged here.)
    (b) SAME folded title + SAME host + DIFFERENT year, no DOI, no strong signal ->
        the two weak signals (year, host) do NOT both agree (year differs) -> NOT
        merged. Host alone is never a key; year alone is never a key.
    """
    # (a) same title + same year + DIFFERENT author surname.
    rows_a = [
        {"evidence_id": "ev_y1", "source_url": "https://venue-x.org/rpa",
         "source_title": "Robotic Process Automation in Financial Operations",
         "year": 2020, "authors": ["Nguyen T", "Park J"],
         "direct_quote": "Nguyen reports a 31 percent cut in routine ledger postings."},
        {"evidence_id": "ev_y2", "source_url": "https://venue-y.net/rpa",
         "source_title": "robotic process automation in financial operations",
         "year": 2020, "authors": ["Ibrahim A", "Costa L"],
         "direct_quote": "Ibrahim reports an 18 percent cut in routine ledger postings."},
    ]
    res_a = consolidate_same_work(rows_a)
    ca1 = res_a.canonical_index_by_index.get(0)
    ca2 = res_a.canonical_index_by_index.get(1)
    _check(ca1 != ca2,
           f"(b2b-a) same title + same YEAR but DIFFERENT author => NOT merged "
           f"(canon idx {ca1} vs {ca2}); a single matching weak signal is not enough")
    real_a = [g for g in res_a.groups if g.same_work_id.startswith(("doi:", "title:"))]
    _check(len(real_a) == 2,
           f"(b2b-a) same title + same year + different author => TWO works (got {len(real_a)})")

    # (b) same title + same host + DIFFERENT year, no strong signal.
    rows_b = [
        {"evidence_id": "ev_h1", "source_url": "https://shared-host.example.org/clerical-2018",
         "source_title": "Clerical Employment Trends in the Mountain Region",
         "year": 2018,
         "direct_quote": "Clerical employment contracted 9 percent in the earlier window."},
        {"evidence_id": "ev_h2", "source_url": "https://shared-host.example.org/clerical-2022",
         "source_title": "clerical employment trends in the mountain region",
         "year": 2022,
         "direct_quote": "Clerical employment contracted 14 percent in the later window."},
    ]
    res_b = consolidate_same_work(rows_b)
    cb1 = res_b.canonical_index_by_index.get(0)
    cb2 = res_b.canonical_index_by_index.get(1)
    _check(cb1 != cb2,
           f"(b2b-b) same title + same HOST but DIFFERENT year => NOT merged "
           f"(canon idx {cb1} vs {cb2}); host alone is never a key and year differs")
    real_b = [g for g in res_b.groups if g.same_work_id.startswith(("doi:", "title:"))]
    _check(len(real_b) == 2,
           f"(b2b-b) same title + same host + different year => TWO works (got {len(real_b)})")


def case_b3_title_only_no_shared_discriminator_not_merged() -> None:
    """Title matches but NO discriminator AGREES (no DOI, no year/author/venue, and
    DIFFERENT hosts) must NOT merge — with no SHARED present discriminator the records
    stay singletons (title-alone never merges)."""
    rows = [
        {"evidence_id": "ev_n1", "source_url": "https://host-one.org/a",
         "source_title": "Automation and the Labor Market in 2024",
         "direct_quote": "First distinct work on automation and the labor market."},
        {"evidence_id": "ev_n2", "source_url": "https://host-two.net/b",
         "source_title": "automation and the labor market in 2024",
         "direct_quote": "Second distinct work on automation and the labor market."},
    ]
    res = consolidate_same_work(rows)
    c1 = res.canonical_index_by_index.get(0)
    c2 = res.canonical_index_by_index.get(1)
    # P2 hardening (#1289): host-only (no year) is no longer a usable discriminator,
    # so each title-only row yields an EMPTY same-work key => a per-row __singleton__
    # bucket with NO canonical_index_by_index entry (None). "NOT merged" therefore means
    # they are NOT co-grouped: they never share the SAME non-None canonical index.
    not_co_grouped = (c1 is None) or (c2 is None) or (c1 != c2)
    _check(not_co_grouped,
           f"(b3) title matches but hosts differ + no other discriminator => NOT merged "
           f"(canon idx {c1} vs {c2})")
    # The two rows must NOT share a same-work group (each is its own title-only
    # singleton, so no single group spans BOTH rows).
    spanning = [g for g in res.groups if len(g.member_indices) >= 2]
    _check(not spanning,
           f"(b3) title-only with NO SHARED discriminator => no group merges both rows "
           f"(got spanning groups {[g.same_work_id for g in spanning]})")


def case_c_captcha_stub_dropped() -> None:
    """A CAPTCHA / anti-bot security stub is DROPPED — but ONLY when the trigger phrase
    co-occurs with a strong WAF/security co-token (I-beatboth-011 #7 P1, #1289).

    POSITIVE: "Just a moment... Performing security verification... Cloudflare Ray ID"
    carries the trigger AND co-tokens => a genuine anti-bot stub => DROPPED.

    NEGATIVE CONTROL (§-1.3 keep-all): "Just a moment, the unemployment rate fell to 3.5%
    in 2023 according to BLS" carries the bare trigger but NO security co-token — it is
    real substantive prose and MUST NOT be dropped.
    """
    rows = [
        {"evidence_id": "ev_real", "source_url": "https://good.org/a",
         "doi": "10.1000/realwork", "source_title": "A Real Paper",
         "direct_quote": "Real substantive finding about labor markets and automation."},
        {"evidence_id": "ev_030", "source_url": "https://blocked.org/b",
         "source_title": "Just a moment...",
         "direct_quote": "Just a moment... Performing security verification... Cloudflare Ray ID: abc123"},
        {"evidence_id": "ev_bare", "source_url": "https://realnews.org/c",
         "doi": "10.1000/barework", "source_title": "Labor Market Update",
         "direct_quote": "Just a moment, the unemployment rate fell to 3.5% in 2023 according to BLS"},
    ]
    res = consolidate_same_work(rows)
    _check(1 in res.dropped_captcha_indices,
           f"(c) the CAPTCHA stub row (index 1, trigger + WAF co-tokens) is dropped "
           f"(got captcha-dropped={sorted(res.dropped_captcha_indices)})")
    _check(0 not in res.dropped_indices,
           "(c) the REAL row (index 0) is NOT dropped")
    _check(2 not in res.dropped_indices,
           "(c) NEGATIVE CONTROL: bare 'just a moment' with NO security co-token (index 2) "
           "is real prose and is NOT dropped (§-1.3 keep-all)")
    # And the stub is excluded from the emitted deduped_rows of the full pass while the
    # bare-phrase real row survives.
    out = dedup_by_finding(rows, gov_suffixes=())
    emitted_eids = {str(r.get("evidence_id")) for r in out.deduped_rows}
    _check("ev_030" not in emitted_eids,
           f"(c) the CAPTCHA stub never enters deduped_rows (got {sorted(emitted_eids)})")
    _check("ev_real" in emitted_eids,
           "(c) the real row IS emitted")
    _check("ev_bare" in emitted_eids,
           f"(c) NEGATIVE CONTROL: the bare-'just a moment' real prose IS emitted "
           f"(got {sorted(emitted_eids)})")


def case_d_distinct_works_not_merged() -> None:
    """Two GENUINELY different works (different DOI AND title) are NOT merged."""
    rows = [
        {"evidence_id": "ev_x", "source_url": "https://a.org/paper1",
         "doi": "10.1111/aaa", "source_title": "Automation and Wages in Germany",
         "direct_quote": "German automation lowered routine-task wages measurably."},
        {"evidence_id": "ev_y", "source_url": "https://b.org/paper2",
         "doi": "10.2222/bbb", "source_title": "Robots and Manufacturing in Japan",
         "direct_quote": "Japanese robotics raised manufacturing output substantially."},
    ]
    res = consolidate_same_work(rows)
    cx = res.canonical_index_by_index.get(0)
    cy = res.canonical_index_by_index.get(1)
    _check(cx != cy,
           f"(d) two distinct works are NOT merged (canon idx {cx} vs {cy})")
    real_groups = [g for g in res.groups if g.same_work_id.startswith(("doi:", "title:"))]
    _check(len(real_groups) == 2,
           f"(d) two distinct works => TWO same-work groups (got {len(real_groups)})")
    _check(not res.dropped_indices,
           "(d) nothing dropped for two clean distinct works")


def case_e_corroboration_count_one_origin() -> None:
    """LIVE ACCOUNTING: 4 same-work rows asserting the SAME numeric finding across
    4 DIFFERENT domains -> the finding cluster counts ONE origin, not 4."""
    same_doi = "10.5555/sharedwork"
    quote = "Automation raised productivity by 12.5 percent in manufacturing."
    rows = [
        {"evidence_id": "ev_p1", "source_url": "https://domain-one.com/p",
         "doi": same_doi, "source_title": "Productivity and Automation",
         "direct_quote": quote, "statement": quote,
         "authority_score": 0.9, "selection_relevance": 0.9},
        {"evidence_id": "ev_p2", "source_url": "https://domain-two.org/p",
         "doi": same_doi, "source_title": "Productivity and Automation",
         "direct_quote": quote, "statement": quote,
         "authority_score": 0.5, "selection_relevance": 0.5},
        {"evidence_id": "ev_p3", "source_url": "https://domain-three.net/p",
         "doi": same_doi, "source_title": "Productivity and Automation",
         "direct_quote": quote, "statement": quote,
         "authority_score": 0.4, "selection_relevance": 0.4},
        {"evidence_id": "ev_p4", "source_url": "https://domain-four.edu/p",
         "doi": same_doi, "source_title": "Productivity and Automation",
         "direct_quote": quote, "statement": quote,
         "authority_score": 0.3, "selection_relevance": 0.3},
    ]
    out = dedup_by_finding(rows, gov_suffixes=())
    # The 4 rows assert the same finding -> exactly one finding cluster.
    finding_clusters = [c for c in out.clusters if len(c.member_indices) >= 2]
    _check(len(finding_clusters) >= 1,
           f"(e) the 4 same-finding rows form a finding cluster (clusters={len(out.clusters)})")
    if finding_clusters:
        c = max(finding_clusters, key=lambda c: len(c.member_indices))
        _check(len(c.member_indices) == 4,
               f"(e) the cluster keeps all 4 member rows (keep-all) (got {len(c.member_indices)})")
        _check(c.corroboration_count == 1,
               f"(e) same-work fold => corroboration_count is ONE origin, NOT 4 "
               f"(got {c.corroboration_count}) -- this is the breadth-inflation fix")
        _check(len(c.member_hosts) == 1,
               f"(e) member_hosts collapses to the ONE canonical origin host "
               f"(got {c.member_hosts})")


def main() -> int:
    print("=== I-beatboth-011 #7 CORE same-work consolidation harness ===")
    case_a_same_doi_four_urls()
    case_b_same_title_no_doi()
    case_b2_same_title_different_discriminator_not_merged()
    case_b2b_single_weak_signal_not_merged()
    case_b3_title_only_no_shared_discriminator_not_merged()
    case_c_captcha_stub_dropped()
    case_d_distinct_works_not_merged()
    case_e_corroboration_count_one_origin()
    print("=" * 60)
    if _FAILURES:
        print(f"HARNESS FAILED: {len(_FAILURES)} assertion(s) regressed:")
        for f in _FAILURES:
            print(f"  - {f}")
        return 1
    print("HARNESS PASSED: same-work members group to ONE source, keep all URLs, "
          "CAPTCHA dropped, distinct works preserved, corroboration de-padded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
