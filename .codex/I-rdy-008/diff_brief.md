# Codex diff review — I-rdy-008 (#504): wire live runs into the rich UI

## §0. Iteration cap directive (CLAUDE.md §8.3.1, verbatim, binding)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

This is iter 1 of 5.

## §1. What you are reviewing

The **diff** for Issue #504 / I-rdy-008 against its APPROVED brief
(`.codex/I-rdy-008/brief.md`, verdict APPROVE iter-2 — rulings: `pattern-a-only-correct`,
`fallback-ok`, `single-pr-exemption-ok`, evidence_pool span `clamp`).

Diff: `.codex/I-rdy-008/codex_diff.patch` — canonical `origin/polaris...HEAD`,
**6 files, 707 insertions / 18 deletions**, commit `7b4c441b`.

## §2. What the brief authorized

Implement the I-rdy-007 contract: a `live_run_adapter` (resolver +
`artifact_dir → EvidenceContract` adapter) + rewire the 4 fixture-bound endpoints
(`bundle.py` `/bundle` JSON, `charts.py`, `followup.py`, `compare.py`) live-first
with `_GOLDEN_RUN_INDEX` fallback. Pattern A only — memory (#508) and pin-replay
(carved follow-up) out of scope. **Single-PR cap exemption** was ruled
`single-pr-exemption-ok` at brief iter-2 — the 707-LOC diff is one inseparable
reviewable unit (adapter + rewiring + tests; ~290 LOC is the test file).

## §3. Files

- NEW `src/polaris_v6/api/live_run_adapter.py` (~270 LOC) — `resolve_run`,
  `artifact_dir_to_evidence_contract`, `live_run_evidence_contract`, and the 6
  decision helpers.
- `bundle.py` (+2 lines import + a 4-line live-first block in `get_bundle`),
  `charts.py` / `followup.py` / `compare.py` (live-first, golden fallback).
- NEW `tests/v6/test_live_run_adapter.py` (~290 LOC) — 9 adapter unit tests + 5
  endpoint live-path tests.

## §4. Review focus — verify against the repo

1. **The 6 adapter decisions** match the APPROVED brief §3.2 + the I-rdy-007
   contract §4: model-identity fallback chain → 422; verifier local/global both ←
   `is_verified`; frame rollup by `(section, slot_id)`; contradiction projection
   (>2 claims → `evidence_b`); tier `_normalize_tier`; evidence_pool envelope-span
   clamp → 422 on no overlap.
2. **Error matrix** in `resolve_run` matches I-rdy-007 §6 / `bundle.py:89-152`.
3. **Fallback correctness** — `live_run_evidence_contract` returns `None` only when
   `run_store.get_run` is `None`; a real-but-non-serviceable run raises (never
   silently falls back to a golden fixture). Golden ids cannot collide with real
   run_ids.
4. **No regression** — `bundle.tar.gz`, `_FIXTURE_DIR`, `memory.py` untouched;
   existing golden-fixture endpoint tests' contract preserved.
5. **`EvidenceContract` validity** — every constructed `SourceSpan` /
   `VerifiedSentence` / `FrameCoverage` / `ContradictionRecord` satisfies the
   pydantic constraints (`source_tier` Literal, `span_end>0`, `span_text` min 1,
   `coverage_percent` 0-100).

## §5. Deliberate calls flagged for your ruling

- **707-LOC diff** — Codex iter-2 brief ruled the single-PR exemption; confirm the
  diff stays within that one-feature scope (no unrelated drive-by changes).
- **Endpoint tests gpg-gated** — the 5 live-path endpoint tests `pytest.skip` when
  the `gpg` binary is absent (`create_app()` eagerly builds the GPG signer at
  `app.py` module scope). `tests/v6/test_api_bundle.py` errors identically on a
  gpg-less host — this is pre-existing, not a #504 regression. `pytest
  tests/v6/test_live_run_adapter.py` here → **9 passed, 5 skipped**; in CI (gpg
  present) all 14 run. Confirm the skip is acceptable or rule otherwise.
- **`_GOLDEN_RUN_INDEX` retained** as a production-code fallback (per your iter-2
  `fallback-ok` ruling).

## §6. Output schema (CLAUDE.md §8.3.9 — bind to this)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
verdict_reasoning: <text>
```
Loose prose without the schema → resubmit.
