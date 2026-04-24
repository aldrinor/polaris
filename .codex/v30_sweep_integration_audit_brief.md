V30 sweep integration audit — xhigh reasoning.

**Skip git status.** Three files only.

## Scope

Commit `714b937`. Phase 1 of V30 sweep integration. Files:

1. `src/polaris_graph/v30_sweep_integration.py` (~380 lines) —
   new integration module with run_v30_post_generation() entry.
2. `scripts/run_honest_sweep_r3.py` — ~75 lines added inside
   the success-path manifest-write block. Grep for
   `"v30_enabled"` or `run_v30_post_generation` to find the
   insertion point.
3. `tests/polaris_graph/test_v30_sweep_integration.py`
   (~550 lines, 9 tests in 7 classes).

Codex at gpt-5.4 + xhigh (default).

## Context

V30 architecture (M-54..M-62) is complete, each layer Codex-
APPROVED across up to 6 passes. 296 unit tests pass. This is
the integration that wires those layers into the actual sweep
runner for live running.

Phase 1 scope: coverage reporting only. Phase 2 (separate
cycle) will replace the multi_section_generator prompts with
M-58 slot-bound prompts. Phase 1 adds:
  - `frame_coverage_report` block to manifest.json
  - Methods disclosure appended to report.md
  - human_gap_tasks.json written to run_dir
  - Operator completions optionally merged from
    human_gap_completions.json

V30 is opt-in via PG_V30_ENABLED=1. When disabled → no-op.

## Questions

1. **Opt-in gating safety**: PG_V30_ENABLED=0 (default) → the
   integration module returns V30SweepResult(enabled=False,
   ...) immediately. Sweep runner checks `if v30_result.enabled`
   before mutating manifest. Is that the right gating pattern,
   or can you find a code path where V30 affects the sweep
   when disabled?

2. **Exception containment**: run_v30_post_generation wraps
   _run_inner in a broad try/except. The sweep runner also
   has its own try/except around the whole integration call
   (belt + suspenders). An exception anywhere in V30 logs +
   adds manifest["v30_error"] but does NOT abort the sweep.
   Sufficient, or can V30 still corrupt the existing manifest?

3. **Ordering vs existing pipeline**: V30 runs AFTER the
   legacy generator produces report.md + manifest. It only
   READS the outputs (none) and WRITES new fields. Could V30
   run racy with any other sweep post-processing step?

4. **Compile_frame non-migrated slug**: when a slug has no
   per_query_report_contract in the template,
   compile_frame returns None → V30 logs + returns (still
   enabled=True, coverage=None). Manifest gets only
   `v30_enabled=True`, no `frame_coverage_report` key. Is that
   the right shape — or should we emit an explicit
   `v30_skipped_reason: no_contract` field?

5. **Phase-1 validation synth**: _synthesize_phase1_validation
   marks all non-gap rows PASS and all gap rows FAIL_MIN_FIELDS.
   This is a placeholder until Phase 2 wires real M-58 payloads.
   Two concerns:
   a) Is "non-gap → PASS" an overstatement in the manifest? The
      legacy generator might have dropped the entity for
      off-topic / verification reasons — V30 coverage report
      would still claim PASS.
   b) Should phase-1 integration CROSS-CHECK against the
      legacy generator's actual output (e.g. was the entity's
      DOI cited in the verified report prose) before claiming
      PASS?

6. **Operator completions workflow**: _merge_human_completions
   uses a "task-equivalent" list built from the current sweep's
   evidence_bindings + entity.doi. This lets an operator drop
   completions into the directory and run again. But the
   operator workflow plan says "run1 emits tasks → operator
   writes completions → run2 merges". Does validating against
   current-run evidence_bindings correctly implement that
   flow, or is there an edge case with the two-pass semantics?

7. **DOI mismatch via current-run bindings**: the tasks_equiv
   list uses `entity.doi` from the CONTRACT (via
   entities_by_id), not from the M-56 FrameRow. This means
   even if M-56 retrieval failed (gap row with doi=None),
   validate_against_tasks still checks against the contract's
   original DOI. Correct, or should it use the row's DOI
   (which might be stale / None)?

8. **JSON serializability of the manifest changes**: all V30
   fields added to manifest are either plain dicts or strings;
   the coverage report passes through to_manifest_dict() which
   the M-60 tests already verify JSON-round-trips. No new
   serialization concern, right?

9. **report.md append**: the integration appends a V30
   disclosure block to report.md with a "\n\n---\n\n" separator.
   If report.md doesn't exist (abort path), V30 doesn't write
   (the existing check is `if report_path.exists()`). Is that
   the right boundary?

10. **Network fetch cost**: Phase 1 enabled means M-56
    fetches 15 entities per clinical sweep via CrossRef +
    Unpaywall + PubMed. All three are free APIs. No API key
    needed for CrossRef. Unpaywall needs PG_UNPAYWALL_EMAIL
    (default polaris@example.org — unsuitable for live runs).
    Did I miss any other external dependency?

11. **Test coverage for the runner edit**: the 9 integration
    tests exercise run_v30_post_generation in isolation. The
    actual sweep runner integration is NOT directly tested
    (would require running the full sweep, which hits network).
    Is that the right test boundary, or should there be a
    smoke test for the runner edit path?

12. **Full-sweep cost impact**: at PG_V30_ENABLED=1, the
    incremental cost per sweep is:
      - +~30 HTTP requests (3 sources × ~10-15 entities)
      - +0 LLM tokens (no generator wiring in Phase 1)
      - +~2 seconds elapsed (per-request retry schedule
        is deterministic 1s/2s/4s, typical 1 attempt each)
    Acceptable for Phase 1? Any concern about rate limits
    at the full-scale-sweep scale (8 domains × 10-15
    entities each = 80-120 entities)?

## Output

Write to `outputs/codex_findings/v30_sweep_integration_audit/findings.md`.

Format:
```markdown
# Codex V30 sweep integration audit

**Verdict**: APPROVED | CONDITIONAL-no-blockers | CONDITIONAL-blockers | REJECT

## Answers
[1..12]

## Findings
<blockers, mediums, nits with file:line>

## Next
On APPROVED / CONDITIONAL-no-blockers: sweep integration is
ready for live-run exercise. On CONDITIONAL-blockers: Claude
iterates before launching a full sweep.
```

Keep under 180 lines. Use xhigh reasoning to find anything that
could affect a live sweep run (not just test passes).
