# Postmortem: The lost day — breadth-hacks bolted on instead of executing the approved design

- **Date:** 2026-06-13 (root cause written and rule locked; approved design dated 2026-06-07)
- **Theme:** process / architecture
- **Severity:** high (named as a root of months of stalled progress)
- **Evidence:** `pipeline_redesign_master_plan.md` §7 "Honest root cause of the lost day" and §2.2; forensic design doc 2026-06-13

## What happened

The correct credibility-weighted retrieval and selection design was authored and
Codex-APPROVED on 2026-06-07. Instead of executing that approved design,
hardcoded caps, targets, and thinners were bolted onto the pipeline to make a
breadth NUMBER go up:

- `PG_BREADTH_CANARY_MIN`
- `PG_LEGACY_SECTION_BREADTH_TARGET`
- `PG_SECTION_SOURCE_BREADTH_TARGET`
- a scope hard-filter

Two new drop-knobs were added just one day before the forensic write-up that
condemned drop-knobs. These bolt-ons fight the architecture: the design is
weight-and-consolidate, and a hard cap or target is a filter-and-drop.

## Root cause

Breadth and quality are emergent properties of honest weighted multi-attribution
— every credible source flows through carrying a credibility weight, and
repetition is corroboration. They cannot be forced by a number. When a knob is
added to make a metric hit a target, the knob is optimizing the metric instead
of the design, and it works against the design that would have produced the
metric honestly. The approved design already existed; the day was lost chasing a
number rather than executing it.

## Contributing factors

- A breadth metric was treated as the goal rather than as a read-out of an
  honest process, so moving the number felt like progress.
- Each knob was locally plausible ("push breadth up a bit") but globally a
  regression against the weight-and-consolidate architecture.
- The approved design and the number-chasing work ran close together in time, so
  the contradiction (adding drop-knobs the day before condemning them) was not
  caught until the forensic pass.

## Lessons (promoted to)

- If you find yourself adding a cap, target, or thinner to make a number move,
  that is the bug — stop and go execute the approved design. Breadth and quality
  EMERGE from honest weighted multi-attribution; they are never forced.
- Promoted to CLAUDE.md §-1.3 (deep-research pipeline DNA: WEIGHT-AND-CONSOLIDATE,
  not FILTER-AND-CAP — weight don't filter, consolidate don't drop, basket
  faithfulness; the named number-forcing bolt-ons are the banned day-waster
  anti-pattern) and the §-1.3.1 junk-deletion carve-out.
- Promoted to memory: `feedback_pipeline_dna_weight_not_filter_2026_06_13.md`.
