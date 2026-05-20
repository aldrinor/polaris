HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1.
- "Don't pick bone from egg" — P1 only for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex diff review — I-cd-020 (#630) — Option D

Brief APPROVE'd at iter 2 (Option D adopted post-scope-consult). 3 files / +128 LOC. Canonical-diff-sha256: `fc1d220c25453ac9d977076e95adca9427b5beda67c5cdb08d11a3882381939f`.

## §A Canonical diff summary

- `src/polaris_v6/api/bundle.py:55-92` — `get_bundle` now: (1) returns golden EvidenceContract when fixture exists; (2) for real completed runs (verified via `run_store.get_run`) returns 404 with enriched detail pointing to `/bundle.tar.gz` + #680 follow-up; (3) for truly unknown ids returns the original generic 404 listing golden fixtures.
- `tests/v6/test_api_bundle.py` — 2 new tests + 2 new fixtures (auth_disabled + db_path) seeded run helper. Confirms enriched-404 wording AND that unknown UUIDs still get the original generic 404.
- `docs/runbook.md` — new "Run bundle export — two endpoints" subsection documenting bundle.tar.gz (real runs, BundleManifest v1.0) vs /bundle (EvidenceContract, golden fixtures only) + the #680 rationale.

## §B Acceptance check

| Criterion | Met by |
|---|---|
| Real-run UUID disambiguated from unknown-id at /bundle | `bundle.py:get_bundle` + 2 tests |
| Enriched 404 mentions bundle.tar.gz + #680 + BundleManifest v1.0 | test_bundle_real_run_returns_enriched_404_pointing_to_tar_gz asserts all three substrings |
| Backwards-compat: all 4 pre-existing tests pass unchanged | 6/6 passed in smoke |
| No fabrication of provenance fields (LAW II + CLAUDE.md §-1.1) | confirmed — no synthesized span offsets or sentence_text |
| `response_model=EvidenceContract` decorator unchanged (back-compat) | `bundle.py:55` |
| Inspector frontend wiring is a SEPARATE Issue (Seq 21 / #631) | no frontend change in this PR |
| EvidenceContract pipeline-A capability extension carved to #680 | filed 2026-05-20 |

## §C Red-team checklist

1. The `run is not None and run.lifecycle_status == "completed" and run.artifact_dir` check guards the enriched-404 branch — correct semantic: only completed-with-artifact_dir runs deserve the bundle.tar.gz pointer (in_progress, aborted-without-artifact runs get the generic 404).
2. The `_GOLDEN_RUN_INDEX` lookup happens BEFORE the run_store query — golden fixtures take priority, no DB query for known fixtures.
3. The enriched-404 message exposes the run_id in the response — fine since auth is enforced at app level (`dependencies=[Depends(_require_auth)]`).
4. The two tests use the SAME `auth_disabled` + `db_path` fixture pattern proven 2026-05-20 in `tests/v6/test_pins_route.py`.
5. The pre-existing tests do NOT use the new fixtures, so client is created without seeded DB — those still pass because /bundle for golden_clinical_001 etc. hits the fixture branch FIRST.
6. The follow-up Issue #680 captures the pipeline-A capability extension with explicit acceptance + sequencing (post-demo).
7. `docs/runbook.md` change is documentation-only, no executable substrate.

## §D Smoke test

```
$ PYTHONPATH=src python -m pytest tests/v6/test_api_bundle.py -v
6 passed in 3.43s
```

## §E Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
