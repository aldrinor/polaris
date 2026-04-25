V30 Phase-2 strategic review — xhigh reasoning.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## User mandate

> "we fail too much, pls give me a proposal that you and codex are
> both fine"

## Failure pattern (3 consecutive runs)

| Run | Verdict | BB+BO+LB | Slot-level |
|-----|---------|----------|------------|
|  9  | CHECKPOINT | 1+4+2 | 15/15 cited gaps |
| 10  | ITERATE | 1+4+2 | release=True restored, SURMOUNT-2/Thomas regressed |
| 11  | ITERATE | 1+4+2 | SURMOUNT-2/Thomas/SURPASS-5 recovered, SURPASS-1 truncated |

Categorical scoreboard FROZEN at 1 BB + 4 BO + 2 LB despite ~10
hours of compute (3 sweeps × ~2.5h) and 6 architectural fixes
landing (M-68 + M-69 #1/#2/#4/#5 + bibliography label fixes).

## Root cause — Codex's run-11 own diagnosis

Two LB dimensions are persistent because they are
**architectural, not data**:

1. **Regulatory LB**: M-58 contract-slot extraction cannot
   synthesize substantive prose from HTML/PDF regulatory pages.
   5/6 regulatory subsections render as `not_extractable` stubs
   even with M-66a-R whitespace tolerance + M-66b-T full-text
   fetch. The fetched 25K char content is structurally noisy
   (nav + boilerplate + actual content). M-58's verbatim-
   substring contract is too rigid for prose synthesis.
   Codex's run-11 recommendation: "verified sentence-level
   synthesis from fetched label text".

2. **Narrative depth LB**: contract-slot prose is by-design
   terse (`Field: value [N].`). 3,112 words vs ChatGPT 4,830 /
   Gemini 6,835 (-35% / -55%). Word-count gains since run-7
   (+25%) all came from non-contract sections (Safety,
   Comparative, Population Subgroups). Codex's run-11
   recommendation: "propagate contradiction-aware hedging into
   Safety and Comparative body, not only the disclosure
   appendix".

## What I (Claude) want to ask Codex

The user wants a **mutually-agreed proposal**. I have three
candidate paths; I want Codex's strategic input on which (or
which combination) is highest-EV.

### Option A — Ship CHECKPOINT now + escalate V31/V32

Commit run-9 + run-11 architecture as PHASE2_CHECKPOINT. Open
two new architectural cycles:

  V31 — Regulatory substantive synthesis
    Add a new generator path (separate from M-58 contract
    slots) that takes a fetched regulatory page + a target
    extraction template and emits 2-4 verified prose sentences
    per subsection. Keeps M-58 for primary trials; adds M-70
    `regulatory_synthesizer` for FDA/EMA/NICE/HC. Sentences
    pass through strict_verify with whitespace tolerance.
    Target: Regulatory LB → BO.

  V32 — Narrative integration
    Pipe contradictions JSON + claim-frame uncertainty into
    the legacy section-prose LLM prompts (Safety, Comparative,
    Population Subgroups, Limitations). Specifically: each
    contradiction tier-labeled disagreement gets one
    appropriately-hedged sentence in the relevant body
    section, not just the appendix.
    Target: Narrative depth LB → BO.

  Estimated time: V31 ~6-8h (new prompt arch + tests + sweep).
  V32 ~4-6h (prompt edits + tests + sweep).
  Total: ~12-15h to next BEAT_BOTH_SHIP attempt.

### Option B — Continue M-69 narrow fix list

Codex's run-11 fix list has 5 items:
  - SURPASS-6 extraction from Rosenstock JAMA 2023
  - SURPASS-CVOT secondary-evidence downgrade (paywall)
  - Regulatory verified-sentence synthesis (overlaps V31)
  - Trial Summary + Timeline rebuild from body slots
  - SURPASS-1 truncation guard

Estimated time: ~4-5h. But: items 3-4 ARE V31 territory in
disguise. Items 1-2-5 are claim-frame BO refinements that
won't lift Regulatory or Narrative depth LB.

### Option C — Hybrid

Cherry-pick from B the items that lift dim count without
duplicating V31/V32:
  - Trial Summary + Timeline rebuild (Structure refinement,
    might lift BO→BB if clean enough)
  - SURPASS-1 truncation guard
  - SURPASS-6 extraction repair

Skip regulatory + CVOT items in B. Treat them as V31 scope.

Time: ~2-3h. Lower-risk run-12 attempt before committing to
the V31/V32 cycle.

## Codex strategic ask

1. Which option (A/B/C) maximizes expected dim-count progress
   per hour invested?
2. Is V31 (regulatory synthesizer as new module) the right
   architecture, or should regulatory just escape Phase-2
   entirely and route via M-61 human/licensed completion?
3. Is V32 (contradiction stream into prose prompts) more
   tractable than I think, or does it require deeper changes?
4. Is there a 4th option I'm missing — e.g., raise the
   acceptance bar (move BB threshold from "beats both" to
   "matches both") so the existing artifact already qualifies?
5. The ChatGPT/Gemini word-count gap (3K vs 5K vs 7K) —
   is that an honest synthesis gap or a verbosity-volume
   trick? Could a structural BB on Contradictions + Structure
   (already secured) plus 5 BO be enough for users who want
   audit-grade reports rather than narrative reports?

## What we both need to commit to

Whatever option we pick, write down the ship gate:
  - if BEAT_BOTH_SHIP = "≥5/7 BB/BO + zero LB" stays
    canonical, the path requires V31+V32
  - if we redefine ship gate to "≥6/7 ≥BO + ≤1 LB" or
    similar, run-9/11 already ships
  - clarity on what "ship" actually means for V30 Phase-2
    so we stop iterating against a moving target

## Output

Write to `outputs/codex_findings/v30_phase2_strategic_review/findings.md`:

```markdown
# Codex V30 Phase-2 strategic review

## Recommended path

<A | B | C | other>

## Reasoning

<why this option, what it costs, what it delivers>

## Ship gate clarification

<should we change the ship gate, or commit to BEAT_BOTH_SHIP
strictly?>

## Concrete next 3 actions

1. ...
2. ...
3. ...
```

Under 250 lines. Full xhigh budget. The user wants a proposal
"you and codex are both fine" — so be direct about
disagreements with my framing.
