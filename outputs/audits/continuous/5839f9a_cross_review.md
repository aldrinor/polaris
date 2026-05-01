# Cross-review — `5839f9a` batch (cycle 5, v2 protocol — first clean APPROVE)

**Cross-review of:** `outputs/audits/continuous/5839f9a_audit.md` (P0=0, P1=0, P2=2, P3=3)
**Subagent ID:** `a77c862710b7e3840`. Cost: ~120k tokens estimated.
**Lens:** correctness (cycle 5, v2 protocol round-robin start)

## Verdict alignment

| | Claude | Subagent |
|---|---|---|
| Verdict | (would have called APPROVE — F-13 cleanly fixes regression) | **APPROVE** |
| P0 / P1 | none | **none** |
| Honesty | OK on F-13. NOT OK on v2 protocol's "soft-lock" framing — caught by subagent. | NOT OK on protocol-doc rule equivalence (P2.1) |

**Subagent's strongest finding (P2.1) is meta-level.** They caught that my "soft-lock when all P2+" rule is mathematically identical to v1's "clean APPROVE" — both require P0=0 AND P1=0. The doc rationalized it as a "softening" but the rule didn't change. **This is exactly the kind of finding brief-blinding was designed to surface** — a brief-aware reviewer would have anchor-followed my framing instead of independently parsing the rule.

The subagent's reviewer-independence statement makes this explicit: "I caught the protocol-v2 doc inconsistency (P2.1) which an author-brief-reading reviewer would likely have anchor-followed past."

That's the v2 protocol earning its keep on its first invocation. Strong validation.

## Fix plan

| ID | Source | Fix | Tag |
|---|---|---|---|
| F-14 | P2.1 | Reword `.codex/AUDIT_CYCLE_PROTOCOL_v2.md` — restore honesty: v2 keeps the v1 lock criterion; what changed is the INPUTS (brief-blinding + lens rotation), not the BAR. | **guardrail** — meta-protocol clarity. |
| F-15 | P2.2 | Commit the working-tree edit on `bb60495_audit.md` so the audit file matches what cycle-4 read. | **guardrail** — repo cleanliness. |
| F-16 | P3.3 | Backfill the missing `3bac322_actors_coverage.md` per-commit brief with a "what this missed" note pointing at F-13. | **guardrail** — chain integrity. |
| Defer | P3.1 | RedisBroker leak in test_broker.py — latent (no warnings); acceptable until RedisBroker becomes eager. |
| Defer | P3.2 | conftest.py setdefault env var — cosmetic. |

## Locking math (ACTUAL, post-correction)

Per the corrected protocol (no math change, just honest naming): lock = 2 consecutive cycles with **APPROVE** (P0=0 AND P1=0).

- Cycle 1: APPROVE_WITH_FIXES (P1=3) → fixed.
- Cycle 2: APPROVE_WITH_FIXES (P1=1) → fixed.
- Cycle 3: APPROVE_WITH_FIXES (P1=1 + P2.3 root_cause) → fixed.
- Cycle 4: APPROVE_WITH_FIXES (P1=1) → fixed.
- **Cycle 5: APPROVE (P1=0).** ✓ First clean.
- Cycle 6 (target — with security lens): APPROVE → **LOCK**.

If cycle-6 also returns clean APPROVE, the triangle locks and the autoloop stops spending on subagents until something material changes.

## Closure

F-14 + F-15 + F-16 land in this turn (3 small commits). Counter for new batch: 1, 2, 3 of 5. Cycle-6 fires after 5/5 OR I fire it manually as the lock-attempt now that cycle-5 is clean (analogous to how I fired cycle-5 manually).

**Notable**: cycle-5's clean APPROVE happened on the smallest-batch invocation yet (3 commits, sub-K). That's evidence the v2 protocol concentrates findings rather than spreading them — fewer commits but tighter scrutiny per commit. Could justify shrinking the K=5 trigger to K=3 in v3 if we want faster lock attempts.
