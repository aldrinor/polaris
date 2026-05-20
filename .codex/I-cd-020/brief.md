HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1.
- "Don't pick bone from egg" — P1 only for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex brief review — I-cd-020 (#630) — Option D scope (rescoped per Codex scope-consult 2026-05-20)

## §A Scope (Option D picked by Codex)

Iter-1 of this brief proposed Option A (build full EvidenceContract from real-run artifact). Codex's scope-consult ranked **D > C > A > B** because pipeline-A's `evidence_pool.json` lacks span char-offsets and `verification_details.json` lacks per-sentence provenance — fabricating those would violate LAW II + CLAUDE.md §-1.1 (clinical-safety line-by-line audit standard).

**Option D** (Codex-picked):
- Acceptance is ALREADY met by the existing `GET /runs/{run_id}/bundle.tar.gz` route (I-arch-001d, in production) + Inspector wiring on the BundleManifest v1.0 schema (I-cd-012 froze the I-A-02b schema as BundleManifest v1.0, NOT EvidenceContract).
- Capability gap for full EvidenceContract is **carved to follow-up Issue #680** (just filed).

This PR ships:

1. `src/polaris_v6/api/bundle.py:55` — `get_bundle` for non-golden real runs returns **HTTP 404 with an enriched detail** that:
   - Distinguishes real-run UUID (recognized via `run_store.get_run`) from truly unknown id.
   - Points the caller to `/bundle.tar.gz` (which serves real-run signed bundles via slice-chain).
   - References follow-up Issue #680 for the JSON-EvidenceContract gap.
2. `docs/runbook.md` — short subsection "Run bundle export" documenting the two endpoints + the EvidenceContract follow-up.
3. `tests/v6/test_api_bundle.py` — 2 new tests:
   - Unknown UUID → 404 with generic detail.
   - Real completed run UUID → 404 with enriched detail mentioning `bundle.tar.gz` + #680.

Estimated canonical diff: **~70 LOC** (well under halt).

## §B Acceptance check

| Criterion | Met by |
|---|---|
| Real completed run reachable via SOME bundle endpoint conforming to the I-A-02b BundleManifest v1.0 schema | EXISTING `GET /runs/{run_id}/bundle.tar.gz` (I-arch-001d) — confirmed by `src/polaris_v6/api/bundle.py:68-end` |
| Inspector frontend (`web/lib/inspector_bundle_loader.ts`) consumes the same bundle shape | YES — loader is the swap-seam; live route consumption lands at Seq 21 / #631 |
| `GET /runs/{run_id}/bundle` no longer silently 404s without explanation for real runs | bundle.py:get_bundle enriched detail |
| EvidenceContract data-gap captured as a separate Issue with full traceable acceptance | #680 filed 2026-05-20 |
| 200-LOC halt respected | ~70 LOC canonical diff |
| Zero data fabrication (LAW II + CLAUDE.md §-1.1) | confirmed — no synthesized span offsets, no synthesized sentence_text |

## §C Codex Red-Team checklist

1. The phrase "real run → signed bundle conforming to the I-A-02b schema" in #630 — Codex scope consult confirmed this maps to BundleManifest v1.0 (I-cd-012) NOT EvidenceContract.
2. `bundle.tar.gz` is already auth-protected via app-level `dependencies=[Depends(_require_auth)]`.
3. The Inspector frontend at I-cd-013a was explicitly noted as "Real-bundle backend wiring lands at I-B-08 (Seq 20)" — interpret as wiring of the bundle.tar.gz consumer (Seq 21 / #631), not the deprecated EvidenceContract JSON.
4. The enriched 404 detail must NOT leak the run-existence boolean for unknown auth contexts (auth is already enforced at app level, so this is post-auth — operator-only).
5. docs/runbook.md update is the minimal documentation surface; the two endpoints exist and now have a clear mental model.
6. Test naming: `test_bundle_real_run_returns_enriched_404_pointing_to_tar_gz` + `test_bundle_unknown_run_returns_generic_404`.
7. No frontend change in this PR (Inspector wiring is Seq 21 / #631).
8. response_model=EvidenceContract stays on get_bundle (back-compat for golden fixtures + future I-cd-020-followup #680).

## §D Files I have ALSO checked and they're clean

- `src/polaris_v6/api/bundle.py:55-65` — golden fixture path untouched; real-run branch is NEW.
- `src/polaris_v6/api/bundle.py:67+` — `bundle.tar.gz` route already wired via `build_slice_chain`.
- `src/polaris_v6/api/artifact_to_slice_chain.py:201` — `build_slice_chain` produces BundleManifest-conformant content.
- `src/polaris_v6/audit_bundle/conformance.py` (I-cd-012) — the 12-layer BundleManifest v1.0 conformance check.
- `web/lib/inspector_bundle_loader.ts` — frontend loader; consumes BundleManifest v1.0; explicit "Real-bundle backend wiring lands at I-B-08 (Seq 20)" comment.
- `outputs/honest_sweep_r3/clinical/clinical_tirzepatide_t2dm/evidence_pool.json` — real-run shape confirmed list of `{direct_quote, evidence_id, source_url, tier in T1-T7, ...}`. Lacks span offsets — the gap reason for #680.
- `outputs/honest_sweep_r3/clinical/clinical_tirzepatide_t2dm/verification_details.json` — has `{drop_reason_counts, sections, totals}`. Per-section counters only. Lacks sentence-level data — the gap reason for #680.

## §E Smoke test

```bash
PYTHONPATH=src python -m pytest tests/v6/test_api_bundle.py -v
```

## §F Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
