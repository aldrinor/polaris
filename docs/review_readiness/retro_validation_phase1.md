# Retro-Validation — Phase 1 Migration Against the Pinned Oracle

**Status:** normative evidence. This document records the empirical proof that Plan V4
safety-rule-1 demanded: the pinned deterministic oracle was replayed against the Phase 1
migrated code, and the canonical artifact was byte-compared to the pinned golden.

**Codex verdict:** `MIGRATION-VALIDATED-ON-COVERED-PATH`

---

## What was replayed

- **Pinned oracle golden SHA-256:**
  `9c0a3d438da943242c98e2fe714494c342d42d02102202d75a61a4554339db98`
- **Migrated code under test:** Phase 1 migration commit `dd96ceb` — the `os.getenv(...)` →
  `resolve(...)` config migration across **832 sites**.
- **Setup verification:** HEAD `c5448ec` has `dd96ceb` as an ancestor; the migrated modules
  import `from src.polaris_graph.settings import resolve`; all three cassette/golden files are
  present in `/home/polaris/wt/retrovalidate/tests/oracle/cassettes/` and are byte-identical
  (SHA-matched) to the phase0 source worktree.

## Coverage — read this before trusting the verdict

The oracle exercises the **acceptance loop on the THIN + SATURATED outline paths only**. The
byte-identical guarantee below holds **exactly on that covered path** and makes **no claim** about
the ~832 migrated sites that this path does not execute. "MIGRATION-VALIDATED-ON-COVERED-PATH"
means precisely: on the code the oracle runs, the Phase 1 migration is byte-for-byte
indistinguishable from the pre-migration reference. Sites outside the covered path are not
validated by this evidence and remain governed by the comparison protocol going forward.

## Replay result

```json
{
  "replay_completed": true,
  "artifact_sha": "9c0a3d438da943242c98e2fe714494c342d42d02102202d75a61a4554339db98",
  "sha_matches_golden": true,
  "positive_control_pass": true,
  "negative_control_pass": true,
  "divergence_detail": "No divergence. Replay ran to completion in mode=replay (retrieval-cassette=replay, llm-cassette=replay; no network) with ZERO cassette misses — a MISS would raise CassetteError (tests/oracle/cassette.py:183-184) and abort, but the run reached ACCEPTANCE PASSED with exit code 0. The harness computed golden SHA-256 9c0a3d438da943242c98e2fe714494c342d42d02102202d75a61a4554339db98 and reported \"replay artifact BYTE-IDENTICAL to recorded golden\". The pinned golden pre-existed on disk (same SHA), so the write-bootstrap branch (acceptance_portable.py:477-482) was skipped and the byte-compare at lines 486-492 was a genuine comparison of migrated-code output vs the pinned reference — no sys.exit(3) mismatch path taken. Both controls valid: positive (THIN) valid_positive_control=True with search_more_evidence_calls=3 and outline_mutated=True; negative (SATURATED) valid_negative_control=True with full_loop_ran=True, section_count=3, finish_outline ACCEPTED at turn 1, zero searches. Setup verified: HEAD c5448ec has dd96ceb as ancestor; migrated modules import \"from src.polaris_graph.settings import resolve\"; all three cassette/golden files present in /home/polaris/wt/retrovalidate/tests/oracle/cassettes/ and byte-identical (SHA-matched) to the phase0 source worktree. The Phase 1 832-site os.getenv->resolve() migration is byte-identical on the oracle's covered path."
}
```

## Interpretation

The replay artifact SHA-256 **equals** the pinned golden
`9c0a3d438da943242c98e2fe714494c342d42d02102202d75a61a4554339db98` **exactly**. Because the
golden pre-existed on disk at the same SHA, the write-bootstrap branch
(`acceptance_portable.py:477-482`) was skipped, so the byte-compare at
`acceptance_portable.py:486-492` was a genuine comparison of the migrated code's output against
the pinned reference — not a self-write that would trivially match.

Both controls are valid, which proves the oracle actually ran the loop rather than passing
vacuously:

- **Positive control (THIN):** `valid_positive_control=True`, `search_more_evidence_calls=3`,
  `outline_mutated=True` — the loop demonstrably searched and mutated when evidence was thin.
- **Negative control (SATURATED):** `valid_negative_control=True`, `full_loop_ran=True`,
  `section_count=3`, `finish_outline` ACCEPTED at turn 1, zero searches — the loop demonstrably
  short-circuited when evidence was saturated.

**Conclusion:** SHA matched → **the migration is byte-identical on the covered path.** This is
the empirical proof Plan V4 safety-rule-1 demanded, scoped to the THIN + SATURATED outline paths
the oracle covers. No divergence was found; there is no divergence finding to document.
