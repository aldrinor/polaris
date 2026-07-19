# Phase 2 — NEEDS-ALIAS rename class: DEFERRED to human review

**Status:** held back (not committed). An autonomous, codex-gated pass attempted all 48 rows (32 worklist NEEDS-ALIAS + 16 SAFE rows reclassified as dynamic). Codex verdict: **ALIASES-REVISE**. This class needs human/deployment judgment — the exact reason Plan V4 rings control-surface renames.

## Why (codex's blocking findings)

- Q1 (every old reference preserved?): NO — not proven. Object identity (`is` checks) is insufficient for monkeypatch compatibility. With a normal re-export shim, `old_module.run_benchmark = fake` does NOT update `new_module.run_benchmark`, so consumers that migrated to the new module bypass the patch. Same defect for simple symbol rebinds like `_ARTIFACT_KIND_REFUSAL = _ARTIFACT_KIND_DECLINED`.
- Q2 (score-safe?): YES in the narrow reported sense — collection byte-identical to baseline, oracle SHA unchanged (9c0a3d43...), positive+negative controls pass, and the 11 noisy failures in test_b11_b20 are confirmed pre-existing (not caused by the batch).
- Q3 (any cosmetic-only alias that doesn't truly preserve the old reference?): YES. (a) Module shims (row 1 beat_both_scorer) are cosmetic-only for monkeypatch REBINDING unless old and new imports return the SAME module object, or a mutation-through-old-path test proves it — an `is`-identity check on the exported names does not. (b) row 4: storing the old value in LEGACY_MODE_LABEL_LEGACY_ALIAS does NOT preserve OUTPUT behavior unless that value is still actually EMITTED. Recognizing both migration-marker keys protects new readers of old data, but does not preserve the old KEY for downstream readers unless it is still WRITTEN.
- Q4 (skip-vs-alias boundary correct?): The skip principle is correct for env-var names, exact literals, source-grep/AST targets, and persisted dict-keys; the conflict rows were prudently deferred. BUT: the migration value/key (row 4) and the persisted run-ID prefix should be RETAINED or DUAL-WRITTEN, not just aliased. And a repository grep CANNOT establish that an output filename or run-ID prefix has no operator/external consumer — absence of a test assertion is not proof of no consumer.
- Required fixes before merge: (1) Add behavioral MUTATION tests for every module/symbol alias — patch via the OLD path and assert the new-path consumer sees the patch (do not rely on `is` identity). If old and new imports are not the same module object, the monkeypatch alias is broken. (2) For row 4 migration label/marker and the run-ID prefix, DUAL-WRITE the old value/key (keep emitting/writing it), not merely keep a dormant alias constant. (3) Do not treat 'grep found no assertion' as proof that a persisted output filename or run-ID prefix has no external/operator consumer.

## What each remaining row needs (33 skipped, categorized)

A rename here is only safe once the matching condition is met:

**env-var control strings (KEEP the string; rename only the Python symbol if any, keep os.getenv literal):**
  - PG_V2_ENABLED
  - PG_JUNK_SOURCE_SCREEN
  - PG_S15_CORROBORATED_HONEST_LABEL
  - PG_CONTRADICTION_RENDER_HONEST
  - PG_V30_ENABLED

**source-grep / AST-extraction harness assertions (update the TEST, not the code — an alias can't satisfy a source-text/def-name check):**
  - GEMINI-ARCH structured_data
  - _WINNER_SLATE_ON_PAID_PATH_ENV
  - _PAID_PATH_WINNER_FLAGS
  - winner_slate_on_paid_path_enabled
  - apply_winner_slate_on_paid_path
  - W4-CANARY log tag
  - smart_art_diagrams state key

**persisted string VALUES asserted by exact equality (needs a contract-version decision + dual-write):**
  - slice_005_beat_both_benchmark
  - rubber_stamp_suspect
  - token_explosion
  - token_honesty manifest key
  - BEAT-BOTH verdict tag
  - POLARIS BEAT-BOTH title
  - S1V1_..._RUN_V1 vector_id

**CONFLICTING worklist targets (pick ONE canonical name first):**
  - HonestSweepJobRunner cluster (SweepJobRunner vs V30SweepJobRunner)
  - is_row_content_junk (low_quality vs integrity_violation)
  - junk_deletion_gate file (3 candidate module names)

**cross-module persisted dict-KEY (multi-reader contract; migrate all readers together):**
  - content_integrity_junk

## The 15 that were applied but need hardening before they can ship

Codex accepted them as score-safe (collection + oracle byte-identical) but flagged that module re-export shims are cosmetic for `monkeypatch.setattr(old_module, name, ...)` compatibility (a migrated consumer bypasses the patch), and persisted values must be dual-**written** (old still emitted), not merely recognized. Before shipping any of these, add **behavioral mutation tests** (patch the old name, assert the new path observes it) rather than `is`/identity checks.

## Recommendation

- The high-value naming cleanup (the `honest`/`junk`/`lethal`/`v10–v30` families) already shipped as **95 SAFE renames** (PR #1384, oracle-validated).

- This NEEDS-ALIAS remainder is low-value (aliases add shim complexity) and high-judgment. Finish it human-in-the-loop: resolve the conflicting canonical names, decide the persisted-value contract bumps, update the source-grep/AST test harnesses, and confirm no operator consumes the renamed run-ID prefixes / output filenames (a repo grep cannot establish that).
