# Codex V30 sweep integration audit — pass 3

**Verdict**: CONDITIONAL-blockers

## Pass-2 blockers resolved
- Verified in `src/polaris_graph/v30_sweep_integration.py:663-816`: the original shared-domain false pass is closed in the tested shape. Direct probe on the new path returned `fda_mounjaro_label=False` and `fda_zepbound_label=True` for the Zepbound-only `accessdata.fda.gov` report.
- Verified in `src/polaris_graph/v30_sweep_integration.py:663-681,777-783`: DOI superstrings no longer match. `10.1056/NEJMoa2107519` does not match `10.1056/NEJMoa2107519X`.
- Verified in `src/polaris_graph/v30_sweep_integration.py:780-783`: anchor superstrings no longer match. `SURPASS-1` does not match `SURPASS-10`.
- The new adversarial tests in `tests/polaris_graph/test_v30_sweep_integration.py:377-503` are aligned with the implemented branches.

## Third-round adversarial attempts
- **Still false-passes**: report same-line cross-clause leakage. Example:
  `Mounjaro Canadian Product Monograph: pdf.hres.ca; FDA Zepbound label: accessdata.fda.gov`
  This returns `True` for `fda_mounjaro_label`, because the report branch only requires `label_name` and `url_pattern` on the same line (`src/...:790-799`). Line scope is better than report-wide, but not enough when one line contains multiple entities.
- **Still false-passes**: bibliography comparison-title leakage. Example biblio entry with `url=https://...accessdata.fda.gov/.../zepbound...` and title `Comparison of Zepbound and Mounjaro prescribing information` returns `True` for Mounjaro (`src/...:754-772`). Shared-domain URL + title echo is not a sufficient disambiguator when the title mentions multiple entities.
- **False-negative**: report DOI / anchor matching is case-sensitive (`src/...:663-681,777-783`). `10.1056/nejmoa2107519` and `surpass-1` do not match the contract values.
- **False-negative**: Unicode-normalization mismatch. Precomposed `café` and decomposed `cafe\u0301` do not match under the current regex path. Probably low-risk here, but the edge exists.
- **Fallback is broader than comment says**: `src/...:812-816` fires for any entity with `label_name` and no `url_pattern`/`anchor`, even if `doi` exists and the report never cites that DOI. It is not limited to “statute-only” entities.

## Residual concerns
- `(?<!\w)needle(?!\w)` is correct for the two pass-2 exploits and works with punctuation because `re.escape()` protects literal metacharacters. Its main limitations are exact-byte matching, case sensitivity, and Unicode-normalization sensitivity.
- Between line / sentence / paragraph, line is the safest of those three for precision. Sentence or paragraph scope would make the cross-entity leakage worse, not better. If you want fewer false-negatives without reopening broad false-passes, the right upgrade is clause/item-level association, not paragraph-level association.
- For bibliography URL disambiguation, `biblio.url` matching `entity.url_pattern` is only sufficient when `url_pattern` is path-specific and unique. Given current shared-domain patterns, some extra disambiguator is necessary, but `title/name echoes label` is still defeatable by comparison titles.
- `_BOUNDARY_CACHE` is acceptable for serial sweep. In CPython, concurrent writes would at worst cause duplicate compilation; I do not see a practical sweep-scale issue unless this path becomes multi-threaded.
- I could not cleanly re-run the full 20-test file in this sandbox because `pytest` tempdir handling hits `PermissionError`; the semantic checks above were verified by direct function probes.

## Next
Do not launch task #28 yet. Tighten report/bibliography association beyond same-line/title-echo heuristics first; after that, re-run the adversarial cases and then proceed to live-run exercise with `PG_V30_ENABLED=1`.
