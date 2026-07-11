"""Offline unit tests for the S2/S3 re-pass iter-4 (Fable) pure detectors.
Question-agnostic: no drb_72 entity/basket is hardcoded. CPU-only, no model load."""
import os, sys, types
from pathlib import Path
_REPO = Path(__file__).resolve().parents[0]
sys.path.insert(0, str(_REPO))

from src.polaris_graph.synthesis import finding_dedup as fd


def _claim(value=0.0, unit=""):
    c = types.SimpleNamespace()
    c.value = value; c.unit = unit; c.subject=""; c.predicate=""
    return c


def test_letter_spaced():
    assert fd._is_extraction_degraded("W e i n v e s t i g a t e t h e p o t e n t i a l o f")
    assert not fd._is_extraction_degraded("We investigate the potential of large language models on labor.")
    assert fd._collapse_letter_spacing("W e i n v e s t i g a t e the topic").startswith("Weinvestigate")
    # a normal sentence is untouched
    s = "AI raises productivity by 14% across firms."
    assert fd._collapse_letter_spacing(s) == s


def test_measurement_gate_year():
    # bare release year -> non-measurement (no unit, year token present)
    assert fd._is_nonmeasurement_numeral(_claim(2016.0), "PyTorch initial release in 2016; version 2.0")
    # a real percentage on the same kind of line stays a measurement
    assert not fd._is_nonmeasurement_numeral(_claim(14.0, "%"), "AI raised output by 14% in 2016")
    assert not fd._is_nonmeasurement_numeral(_claim(14.0), "AI raised output by 14% overall")


def test_measurement_gate_section_and_id():
    assert fd._is_nonmeasurement_numeral(_claim(4.0), "Section 4 presents our results")
    assert fd._is_nonmeasurement_numeral(_claim(3.0), "3. Main findings from the consultation")
    assert fd._is_nonmeasurement_numeral(_claim(164.0), "IMF Working Paper WP/21/164 Finance")
    assert fd._is_nonmeasurement_numeral(_claim(30957.0), "NBER working paper w30957 language models")
    assert fd._is_nonmeasurement_numeral(_claim(514.0), "IZA World of Labor izawol.514 automation")
    # a real dollar economic figure is NOT suppressed (fail-open on measurement marker)
    assert not fd._is_nonmeasurement_numeral(_claim(4.4, "$"), "contribute $4.4 trillion annually")


def test_measurement_gate_zip():
    assert fd._is_nonmeasurement_numeral(_claim(2138.0), "Cambridge, MA 02138 United States")
    # a bare 5-digit count without address context is NOT a zip (fail-open keep)
    assert not fd._is_nonmeasurement_numeral(_claim(12000.0), "the survey covered 12000 respondents")


def test_derivative_press_host_path():
    assert fd._is_derivative_press({"source_url": "https://news.stthomas.edu/generative-ai-impact"})
    assert fd._is_derivative_press({"url": "https://fintech.stanford.edu/events/ai-and-work"})
    assert fd._is_derivative_press({"source_url": "https://example.com/press-release/new-study"})
    assert fd._is_derivative_press({"source_url": "https://medium.com/@x/ai-explainer"})
    # a primary journal / working paper is NOT derivative
    assert not fd._is_derivative_press({"source_url": "https://www.imf.org/-/media/files/publications/wp/2024/wpiea"})
    assert not fd._is_derivative_press({"source_url": "https://www.mdpi.com/1999-4893/18/9/554"})


def test_row_any_url_backfill():
    assert fd._row_any_url({"source_url": "", "url": "https://a.org/x"}) == "https://a.org/x"
    assert fd._row_any_url({"link": "https://b.org/y"}) == "https://b.org/y"
    assert fd._row_any_url({}) == ""


def test_unknown_bucket_pools_for_nli():
    # S2/S3 re-pass Fable Fix 1(b) REVERSES the iter4 isolate-unknowns policy: POOLING IS NOT
    # MERGING. Two valueless __unknown__ clusters now SHARE the qualitative NLI pool bucket so the
    # bidirectional cross-encoder GETS to compare them; the MERGE is still decided by entailment
    # downstream (an infra None / no-edge => no merge, fail-open). The default flag is ON.
    assert fd._unknown_nli_pool_enabled() is True
    k1 = ("__unknown__", "ev_1", 0)
    k2 = ("__unknown__", "ev_2", 0)
    b1 = fd._cluster_value_bucket(k1, [], [])  # no recoverable value -> shared qualitative pool
    b2 = fd._cluster_value_bucket(k2, [], [])
    assert b1 == b2 == ("__unk_qual__",), (b1, b2)
    # a value-bearing unknown pools by its RECOVERED numeric value (same-value unknowns compare).
    row = {"evidence_id": "ev_v", "direct_quote": "The rate rose 15% year over year."}
    bv = fd._cluster_value_bucket(("__unknown__", "ev_v", 0), [row], [0])
    assert bv == 15.0, bv
    # a real numeric key still buckets by value
    assert fd._cluster_value_bucket(("subj","pred",15.0,"%","","",""), [], []) == 15.0
    # with the legacy isolate flag, two unknowns get UNIQUE buckets (byte-identical old behaviour)
    import os as _os
    _os.environ["PG_UNKNOWN_NLI_POOL"] = "0"
    try:
        assert fd._cluster_value_bucket(k1, [], []) != fd._cluster_value_bucket(k2, [], [])
    finally:
        _os.environ.pop("PG_UNKNOWN_NLI_POOL", None)


def test_is_real_work_titlealone(tmp=None):
    # a titlealone / arxiv group must now be a REAL work (Fix 2a) — exercised via consolidate
    rows = [
        {"evidence_id":"e1","source_url":"https://a.org/doc.pdf","direct_quote":"A long discriminative title about generative artificial intelligence and labor markets. Body one."},
        {"evidence_id":"e2","source_url":"https://a.org/doc.pdf","direct_quote":"A long discriminative title about generative artificial intelligence and labor markets. Body two differs."},
    ]
    res = fd.consolidate_same_work(rows)
    # both rows fetched from the identical URL -> ONE work id populated for both
    assert res.work_id_by_index.get(0) == res.work_id_by_index.get(1) is not None, res.work_id_by_index


def test_subject_title_like():
    # a paper title / full clause named as the subject is NOT a subject
    assert fd._subject_is_title_like("The Projected Impact of Generative AI on Future Productivity")
    assert fd._subject_is_title_like("exploring the implications of chatgpt for language learning in higher education")
    # a genuine short subject noun phrase is kept
    assert not fd._subject_is_title_like("generative artificial intelligence")
    assert not fd._subject_is_title_like("employment")
    assert not fd._subject_is_title_like("labor productivity")
    # a URL/filename SLUG folded to one long token is a title-fold, not a subject
    assert fd._subject_is_title_like("projectedimpactofgenerativeaionfutureproductivity")
    # a genuine single long-ish word stays a subject
    assert not fd._subject_is_title_like("telecommunications")
    assert not fd._subject_is_title_like("entrepreneurship")


def test_samework_url_fold_mixed_keys():
    # two chunks of ONE document at the identical URL: one carries a long discriminative title
    # (titlealone key), the other does not (url key). They MUST fold to one work (Fix 2b).
    url = "https://budgetlab.yale.edu/research/evaluating-impact-ai-labor-market-current-state"
    rows = [
        {"evidence_id": "e1", "source_url": url,
         "direct_quote": "Evaluating the Impact of Artificial Intelligence on the Labor Market Current State of Affairs. Body chunk one about exposure."},
        {"evidence_id": "e2", "source_url": url,
         "direct_quote": "short tail chunk two."},
        {"evidence_id": "e3", "source_url": url,
         "direct_quote": "another middle chunk three of the same document with different words."},
    ]
    res = fd.consolidate_same_work(rows)
    ids = {res.work_id_by_index.get(i) for i in range(3)}
    assert len(ids) == 1 and None not in ids, (ids, res.work_id_by_index)


if __name__ == "__main__":
    fns = [v for k,v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed=0
    for f in fns:
        try:
            f(); print("PASS", f.__name__); passed+=1
        except Exception as e:
            print("FAIL", f.__name__, "->", repr(e))
    print(f"\n{passed}/{len(fns)} passed")
    sys.exit(0 if passed==len(fns) else 1)
