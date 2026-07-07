# Morning handoff — I-deepfix-001 beat-both fix campaign (overnight 2026-07-07)

Plain-English summary of the autonomous overnight run. Read this first.

## What I finished and committed (all on branch bot/I-wire-001-integration)

Every wave below was reviewed by BOTH the real Codex CLI AND the real Fable 5 model. Both had to APPROVE
(zero P0, zero P1) before I committed. Every wave keeps the faithfulness engine byte-for-byte untouched, and
every new flag is OFF by default so the old behaviour is byte-identical when the flag is off.

| Wave | Commit | What it does |
|---|---|---|
| 5 | `e55637b3` | Retired an UNSOUND truncation rule (it was deleting good, checked sentences) and shipped the SOUND one (FF3). Both reviewers proved the old rule over-deleted; I removed it instead of patching it a 4th time. |
| 6a | `593b0b3b` | Expanded the summary-table country/field/risk word-lists so the 5 missing study countries (Belgium, Netherlands, Poland, Saudi Arabia, Bahrain) can appear. Then pruned nationality words that are also common English words (polish/danish/turkey/etc.) that were showing FALSE countries. A word only appears if it is literally in the verified text — nothing is faked. |
| 6b | `1f3d2ced` | Put the summary table into the fail-loud safety check, so a broken/removed table CRASHES the paid run instead of silently shipping. Fixed a real gap Codex found (the check treated the table's switch as OFF-when-unset, but it is ON by default). |
| 6c | `a09fe434` | Added a general "look at all sides" search lane: for each subtopic it also searches from supporting / opposing / challenges / opportunities angles. Off by default, only ADDS searches, fails safe. Fixed a real honesty bug: the log now reports how many searches actually ran, not how many were attempted. |
| 7 | `f9173615` | Turned ON a finished-but-hidden "repetition guard" (it was built + already reviewed in an earlier session, but never saved to git and never connected). When the same fact repeats word-for-word across sections, it keeps the fullest copy + a "see above" note that keeps every citation. It NEVER deletes a fact and never merges two different facts. Render-only, runs after the faithfulness engine. |

Tracking docs (checklist + ledger) were committed alongside each wave. The two anti-dark documents are
`.codex/I-deepfix-001/MASTER_LIVENESS_LEDGER.md` and `.codex/I-deepfix-001/WAVE_LIVENESS_ROBUSTNESS_CHECKLIST.md`.

The big Wave-6 discovery: the 5-column summary table the benchmark wants was ALREADY built and wired in the
pipeline — I did not need to build it, only make it score (vocab) and prove it fires (canary). That is exactly
the "built but hidden" pattern the whole campaign is about.

## What I deliberately DID NOT do overnight (needs your call or daylight care)

I stopped short of three items on purpose — rushing them at 5am would risk a faithfulness or pipeline bug that
a tired build could miss. Each is a real judgment call, per your own campaign map:

1. **Wave 8 — archival pass. DEFERRED.** The map lists: drop stash@{1} (only AFTER salvaging its
   clause-chrome-screen + recall-first ideas into a fix3 follow-up), retire the `source_necessity_disclosure`
   orphan builder, and clean superseded worktrees. But: the orphan is kept importable FOR TESTS (its own
   docstring says so), so archiving it breaks tests — it needs the "archive vs wire once" decision you flagged.
   The stash needs a salvage first. And the worktrees include ACTIVE workflow worktrees that are unsafe to
   remove while workflows run. None of this is a safe rushed-overnight deletion. **Your call: archive-vs-wire the
   orphan; what to salvage from stash@{1}.**

2. **Wave 7b — pureshell (PG_CONTENT_SHELL_REFETCH). DEFERRED.** It lives in stash@{0} and touches
   `live_retriever.py`, which changed in committed Wave 4 — a blind stash-apply conflicts. It is retrieval-side
   and needs a careful conflict-safe re-implement, best with daylight review.

3. **Wave 6d — Brynjolfsson NBER citation repoint. HELD for you.** This is a faithfulness-sensitive attribution
   change (which source a citation points at). Per your bundled-decision list I did not implement it autonomously.

## Decisions I need from you (bundled, non-blocking)

- **Do the two new default-OFF flags run ON in the paid VM run?** `PG_STANCE_DIVERSIFY_SEEDS` (Wave 6c search
  seeds) and `PG_CROSS_SECTION_REPETITION_GUARD` (Wave 7). They are quad-pinned to force ON on the gate-B slate,
  so they WILL run ON in the official run as it stands — confirm you want that, or set either OFF. Their real
  benefit is only measurable in a real run (I could not prove the retrieval-seed payoff offline — I said so honestly).
- **kimi judge lock**, **Brynjolfsson NBER repoint**, **hard-mask-vs-weight** — your earlier bundled decisions, still open.
- **Archive-vs-wire the `source_necessity_disclosure` orphan** (Wave 8).

## One pre-existing test failure I found (NOT from my work)

`tests/polaris_graph/test_gateb_containment_slate.py::test_credibility_pass_wall_and_inflight_pinned_as_a_pair`
asserts `PG_CREDIBILITY_PASS_MAX_INFLIGHT == 16`, but the slate already pins `20` (a prior 16→20 concurrency
resize). The build agent PROVED it fails on HEAD without my changes. It is a stale locked-pair assertion someone
should reconcile — I left it alone (out of scope, and it is a locked pair I should not touch unasked).

## The paid VM run is still HELD for your go

Per Rule #2 (anti-dark) the paid drb_72 run only counts as success when EVERY flag in the ledger fires with a
real count from the actual run log — the `assert_activation_markers_fired` canary CRASHES the run if any ON flag
goes dark. Per Rule #3 I will forensic-monitor the run line-by-line and resume from the closest checkpoint on any
problem. But I did NOT launch a paid run — heavy runs are VM-only and the paid run waits for your go.
