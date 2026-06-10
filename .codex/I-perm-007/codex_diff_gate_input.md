HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex DIFF review — I-perm-007 (#1201) numeric sanitizer — ITER 2 of 5

Iter-1: REQUEST_CHANGES, ZERO P0, 2 P1 + 1 P2. ALL resolved. VERIFY.

## P1-a (test depended on gitignored saved pool -> CI FileNotFoundError) — RESOLVED
The test now uses an INLINE tracked `_FIXTURE` dict (DOI-cruft / legit-percent / numeric-range / CI-bounds / no-space-citation rows) for all core assertions. The real-pool test is now `@pytest.mark.skipif(... not pool.is_file())` so clean CI skips it cleanly.

## P1-b (over-filtered legitimate numeric ranges -> real clinical-data loss) — RESOLVED
`_ACCESSION_RE` retightened to `[A-Za-z]\d|-\d[\d.]*-\d`: an accession needs a LETTER adjacent to a digit (s41586-020-2080-8) OR TWO-or-more internal hyphens (978-3-16-148410-0). A numeric RANGE / CI bound ("0.4-6.7", "0.47-0.89", "10-100") has NO letter and a SINGLE hyphen -> NEVER matched. EVIDENCE: on the real drb_76 pool, ON now KEEPS ev_560's `6.7` (from `0.4-6.7%`) while still dropping the DOI prefix.

## P2 (no-space markdown citation folded into the token) — RESOLVED
`_token_around` now breaks on whitespace AND `([])`, so `58%([_9_](https://x))` -> token `58%` (kept); a number never absorbs a trailing markdown-link URL.

## Evidence pack (ran this session)
- unit cases (parametrized): DOI / accession / ISBN / URL-path -> FLAGGED; range endpoint / CI bound / integer range / clean-percent-with-later-URL / no-space-citation / plain decimal -> KEPT.
- `pytest test_numeric_sanitizer_iperm007.py test_quantified_tradeoff_phase7.py test_run11_010_degraders.py` -> **57 passed** (inline fixture + 44 existing extractor/quantified tests, flag OFF byte-identical).
- real pool ON: DOI cruft gone, ev_560 6.7% kept.

VERIFY the 3 iter-1 findings are closed (no range/CI false-drop; CI-safe fixture; token boundary). Note: the extractor only emits unit-bearing numbers (percents), so bare HR/CI decimals are out of its scope (the unit test covers that they are not FLAGGED). APPROVE if closed.

## Output schema (REQUIRED — last `verdict:` line parsed by CI)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

========== THE UPDATED DIFF UNDER REVIEW ==========

diff --git a/src/polaris_graph/tools/evidence_extractor.py b/src/polaris_graph/tools/evidence_extractor.py
index ed9e0766..20f8de0d 100644
--- a/src/polaris_graph/tools/evidence_extractor.py
+++ b/src/polaris_graph/tools/evidence_extractor.py
@@ -15,6 +15,11 @@ import os
 import re
 from typing import Optional
 
+from src.polaris_graph.tools.numeric_sanitizer import (
+    is_structural_identifier_number,
+    numeric_sanitizer_enabled,
+)
+
 logger = logging.getLogger("polaris_graph")
 
 _MAX_EVIDENCE = int(os.getenv("PG_EXTRACT_MAX_EVIDENCE", "500"))
@@ -102,6 +107,8 @@ def extract_numbers_from_evidence(
     """
     data_points = []
     processed = 0
+    # I-perm-007 (#1201): read the sanitizer flag ONCE (default OFF -> byte-identical).
+    _sanitize_numbers = numeric_sanitizer_enabled()
 
     for ev_id, ev in evidence_store.items():
         if processed >= max_evidence:
@@ -140,6 +147,15 @@ def extract_numbers_from_evidence(
                 if value is None:
                     continue
 
+                # I-perm-007 (#1201): drop a number EMBEDDED in a structural identifier
+                # (DOI/URL/accession) — cruft parsed as clinical data (e.g. the DOI prefix
+                # `10.1038` extracted as a percent). Default OFF -> byte-identical; keeps a clean
+                # number that merely has a trailing citation URL in a later token.
+                if _sanitize_numbers and is_structural_identifier_number(
+                    text_to_scan, match.start(), match.end()
+                ):
+                    continue
+
                 # Handle multipliers
                 if unit and unit.lower() in ("billion", "million", "thousand"):
                     multipliers = {"billion": 1e9, "million": 1e6, "thousand": 1e3}
diff --git a/src/polaris_graph/tools/numeric_sanitizer.py b/src/polaris_graph/tools/numeric_sanitizer.py
new file mode 100644
index 00000000..7164ef4e
--- /dev/null
+++ b/src/polaris_graph/tools/numeric_sanitizer.py
@@ -0,0 +1,75 @@
+"""Numeric extraction sanitizer (I-perm-007 #1201).
+
+The quantified differentiator parses cruft-polluted scraped text: DOI prefixes, URL fragments,
+accession numbers, and reference markers get extracted as clinical data points (proof: drb_76
+yields ``value=10.1038 unit="%"`` — a DOI prefix parsed as a percent; ``8.0 M3`` from the
+accession ``s41586-020-2080-8``). This sanitizer drops a numeric match ONLY when the number's OWN
+whitespace-delimited token is a structural identifier (DOI / URL / accession / PMID / ISSN), NOT
+merely when a URL sits ELSEWHERE in the window — so a legitimate ``99%`` or ``30 days`` followed
+by a trailing citation URL is KEPT. Over-filtering is impossible to turn into a fabrication: the
+sanitizer only REMOVES candidate data points, never invents one (a dropped real datapoint is a
+fail-closed no-op, surfaced as a coverage gap, never a wrong number).
+
+DEFAULT OFF: ``PG_SWEEP_NUMERIC_SANITIZER`` unset/falsey -> the sanitizer is a no-op (the caller
+keeps every match; byte-identical extraction).
+"""
+
+from __future__ import annotations
+
+import os
+import re
+
+_FLAG = "PG_SWEEP_NUMERIC_SANITIZER"
+_OFF_VALUES = frozenset({"", "0", "false", "no", "off"})
+
+# A structural identifier the number is EMBEDDED IN (checked against the number's own token):
+#   - a URL scheme / host / path:           http://  https://  www.  /article/  /eid/
+#   - a DOI:                                 doi=  doi:  doi.org/  10.<4-9 digits>/
+#   - URL-encoded slash in a DOI/path:       %2f
+#   - a database identifier:                 pmid  issn  scholar_lookup
+_STRUCTURAL_ID_RE = re.compile(
+    r"https?://|www\.|/article/|/eid/|doi[:=/]|doi\.org|10\.\d{4,9}/|%2f|pmid|issn|scholar_lookup",
+    re.IGNORECASE,
+)
+# An accession / catalogue token has EITHER a LETTER adjacent to a digit (e.g. "s41586-020-2080-8",
+# "PMC123") OR TWO-OR-MORE internal hyphens (e.g. "978-3-16-148410-0"). A numeric RANGE or CI bound
+# ("0.4-6.7", "0.47-0.89", "10-100") has NO letter and a SINGLE hyphen between numbers, so it is
+# NEVER matched — dropping a real range/CI is a clinical-data loss (Codex slice-1 P1: ev_560 6.7%).
+_ACCESSION_RE = re.compile(r"[A-Za-z]\d|-\d[\d.]*-\d")
+
+
+def numeric_sanitizer_enabled() -> bool:
+    """``PG_SWEEP_NUMERIC_SANITIZER`` (default OFF -> no-op, byte-identical extraction)."""
+    return os.environ.get(_FLAG, "").strip().lower() not in _OFF_VALUES
+
+
+# Token boundaries: whitespace PLUS markdown-link / citation delimiters, so an immediately-adjacent
+# no-space citation like "58%([_9_](https://x))" does NOT fold its URL into the number's token
+# (Codex slice-1 P2).
+_TOKEN_BREAK = "([])"
+
+
+def _token_around(text: str, start: int, end: int) -> str:
+    """The maximal token spanning ``[start, end)``, bounded by whitespace or ``([])``."""
+    left = start
+    while left > 0 and not text[left - 1].isspace() and text[left - 1] not in _TOKEN_BREAK:
+        left -= 1
+    right = end
+    while right < len(text) and not text[right].isspace() and text[right] not in _TOKEN_BREAK:
+        right += 1
+    return text[left:right]
+
+
+def is_structural_identifier_number(text: str, start: int, end: int) -> bool:
+    """True if the numeric match at ``[start, end)`` is EMBEDDED in a structural identifier
+    (DOI / URL / accession / PMID / ISSN) — i.e. the number is plumbing, not clinical data.
+
+    Checks the number's OWN token only, so a clean ``99%`` followed by a citation URL in a later
+    token is NOT flagged.
+    """
+    token = _token_around(text, start, end)
+    if _STRUCTURAL_ID_RE.search(token):
+        return True
+    if _ACCESSION_RE.search(token):
+        return True
+    return False
diff --git a/tests/polaris_graph/tools/test_numeric_sanitizer_iperm007.py b/tests/polaris_graph/tools/test_numeric_sanitizer_iperm007.py
new file mode 100644
index 00000000..6115f2c9
--- /dev/null
+++ b/tests/polaris_graph/tools/test_numeric_sanitizer_iperm007.py
@@ -0,0 +1,122 @@
+"""I-perm-007 (#1201) numeric sanitizer — drop numbers embedded in DOI/URL/accession identifiers.
+
+Offline, self-contained (an INLINE fixture, not the gitignored saved pool — Codex slice-1 P1):
+ON drops the DOI-prefix / accession cruft (e.g. `10.1038` extracted as a percent) while KEEPING
+legit clinical numbers — including numeric RANGES and CI bounds (`0.4-6.7%`, `0.47-0.89`) and a
+clean percent with a no-space trailing citation; OFF is byte-identical.
+"""
+
+from __future__ import annotations
+
+import os
+from pathlib import Path
+
+import pytest
+
+from src.polaris_graph.tools import evidence_extractor as ee
+from src.polaris_graph.tools.numeric_sanitizer import is_structural_identifier_number
+
+_FLAG = "PG_SWEEP_NUMERIC_SANITIZER"
+
+# Inline, tracked fixture — each direct_quote is >=20 chars (the extractor skips shorter text).
+_FIXTURE = {
+    "doi_cruft": {
+        "direct_quote": "see scholar_lookup?doi=10.1038%2fnrgastro.2014.66&pmid=24912386 for the source",
+        "source_url": "https://scholar.google.com/x",
+    },
+    "legit_percent": {
+        "direct_quote": "the treatment reduced colorectal cancer risk by 99% in the cohort population",
+        "source_url": "https://example.org/a",
+    },
+    "numeric_range": {
+        "direct_quote": "cereal fibre relative risk ranged 0.4-6.7% per 10 g/day across the studies",
+        "source_url": "https://example.org/b",
+    },
+    "ci_bounds": {
+        "direct_quote": "the hazard ratio was 0.65 (95% CI 0.47-0.89) in the pooled analysis cohort",
+        "source_url": "https://example.org/c",
+    },
+    "trailing_citation": {
+        "direct_quote": "the meta-analysis reported a 58%([_9_](https://x.org/p)) reduction overall",
+        "source_url": "https://example.org/d",
+    },
+}
+
+
+@pytest.fixture(autouse=True)
+def _clear_flag():
+    os.environ.pop(_FLAG, None)
+    yield
+    os.environ.pop(_FLAG, None)
+
+
+# --- unit: structural-identifier detection (token-scoped, never a numeric range) -------------
+
+
+@pytest.mark.parametrize(
+    "text, frag, embedded",
+    [
+        ("scholar_lookup?doi=10.1038%2fnrgastro.2014.66", "10.1038", True),
+        ("DO - 10.1038/s41586-020-2080-8 M3 - Article", "s41586-020-2080-8", True),  # accession
+        ("isbn 978-3-16-148410-0 ref", "978-3-16-148410-0", True),  # multi-hyphen id
+        ("see https://wwwnc.cdc.gov/eid/article/27/8", "27", True),  # number inside the URL path
+        ("relative risk 0.4-6.7% per 10 g", "6.7", False),  # numeric RANGE endpoint -> KEEP
+        ("95% CI 0.47-0.89 pooled", "0.47", False),  # CI bound -> KEEP
+        ("range 10-100% across arms", "100", False),  # integer range -> KEEP
+        (">99% genomic relatedness ([_8_](https://x))", "99", False),  # clean, URL later -> KEEP
+        ("a 58%([_9_](https://x)) reduction", "58", False),  # no-space citation -> KEEP
+        ("hazard ratio 0.65 (95% CI ...)", "0.65", False),  # plain decimal -> KEEP
+    ],
+)
+def test_structural_identifier_detection(text, frag, embedded):
+    start = text.index(frag)
+    end = start + len(frag)
+    assert is_structural_identifier_number(text, start, end) is embedded
+
+
+# --- inline fixture: OFF byte-identical, ON drops cruft + keeps legit (incl. ranges/CI) ------
+
+
+def _values(dps):
+    return {(d["value"], d["unit"]) for d in dps}
+
+
+def test_off_is_byte_identical():
+    os.environ.pop(_FLAG, None)
+    baseline = ee.extract_numbers_from_evidence(dict(_FIXTURE))
+    for falsey in ("0", "false", "no", "off"):
+        os.environ[_FLAG] = falsey
+        assert ee.extract_numbers_from_evidence(dict(_FIXTURE)) == baseline
+    # fixture sanity: the DOI cruft IS extracted with the flag off.
+    assert any(d["value"].startswith("10.10") for d in baseline)
+
+
+def test_on_drops_doi_keeps_legit_and_ranges():
+    os.environ[_FLAG] = "1"
+    out = ee.extract_numbers_from_evidence(dict(_FIXTURE))
+    vals = {d["value"] for d in out}
+    # DOI prefix parsed as data -> dropped.
+    assert not any(v.startswith("10.10") for v in vals)
+    # legit clinical percents kept — INCLUDING a numeric RANGE endpoint (no over-filter; the
+    # range "0.4-6.7%" must not be mis-read as an accession). (The extractor only emits
+    # unit-bearing numbers like percents — bare HR/CI decimals are out of its scope, so they
+    # never appear with OR without the sanitizer; the structural-id unit test covers them.)
+    assert "99.0" in vals  # plain percent
+    assert "6.7" in vals  # range endpoint of 0.4-6.7% — the Codex P1 over-filter case
+    assert "58.0" in vals  # percent with a no-space trailing citation
+
+
+@pytest.mark.skipif(
+    not (Path(__file__).resolve().parents[3] / "outputs/audits/beatboth8/drb_76/evidence_pool.json").is_file(),
+    reason="saved beatboth8 pool not present (gitignored) — inline fixture covers CI",
+)
+def test_real_drb76_pool_doi_dropped_range_kept():
+    import json
+
+    pool = Path(__file__).resolve().parents[3] / "outputs/audits/beatboth8/drb_76/evidence_pool.json"
+    rows = json.loads(pool.read_text(encoding="utf-8"))
+    store = {r.get("evidence_id") or f"ev_{i}": r for i, r in enumerate(rows)}
+    os.environ[_FLAG] = "1"
+    out = ee.extract_numbers_from_evidence(store)
+    assert not any(d["value"].startswith("10.10") for d in out)  # DOI cruft gone
+    assert any(d["value"] == "6.7" for d in out)  # ev_560 real range endpoint KEPT
