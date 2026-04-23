# True Root Cause — Claude + Codex Cross-Review

**Audit date**: 2026-04-23 (post V29 halt, §7 #9 fired)

## Agreement (both auditors)

1. **V29 did not move the scoreboard because V28's diagnosis was
   wrong.** Custody was fixed; dimensional outcome identical.
2. **POLARIS is corpus-driven; competitors are frame-driven.** The
   generator emerges a frame from whatever landed in evidence_pool,
   rather than instantiating a required-report schema.
3. **`strict_verify` is NOT the root cause and must not be relaxed.**
   It's doing the right thing (refusing ungrounded claims). The
   problem is upstream — nothing reserves frame slots before
   retrieval/generation, so retrieval failure becomes silent
   content absence rather than explicit "field not extractable"
   language.
4. **7/7 BEAT_BOTH is NOT achievable autonomously without licensed
   primary access.** Architecture can eliminate self-inflicted
   failure; it cannot conjure inaccessible NEJM/Lancet full text.
5. **Engineering cost for the fix: 12-16 days** (Codex), 12-15 days
   (Claude). Converged around 2-3 weeks.

## Codex's sharper framing I'm adopting

Where Claude called it "frame-driven," Codex names it precisely:
**REPORT CONTRACT**. This is the missing layer, not just "a frame".

The contract has four required elements:
1. **Required entities**: SURPASS-1..6, SURPASS-CVOT, SURMOUNT-2,
   mechanism primary, per-jurisdiction regulatory sources.
2. **Required fields per entity**: N, population, comparator,
   endpoint, timepoint, effect size, uncertainty, study design,
   sponsor, limits.
3. **Required rendering slots**: one subsection or table row per
   entity, even if partially empty.
4. **Required evidence binding**: each slot is bound to one or
   more designated evidence rows BEFORE generation starts.

Codex's one-line characterization: "from `retrieve then narrate`
to `instantiate report schema then fill it`".

That's the correct architectural move. I had the right direction;
Codex defined it with more operational precision.

## Disagreement: "complementary positioning" as an option

**Claude**: Offered "complementary positioning" as a valid
non-architectural alternative — ship V28 as rigorous transparency
reference, position as verification companion to ChatGPT/Gemini DR,
zero further engineering.

**Codex (stricter)**: "Stop setting 'ChatGPT-DR replacement on
clinical' as the near-term product claim unless you also solve
licensed-access coverage. Without that, POLARIS should be
positioned as the transparent, auditable synthesis system, not
the maximal-richness system."

Codex is arguing that positioning change should follow
architectural change, not substitute for it. The product claim
needs to change REGARDLESS of whether we build frame-first,
because licensed access is a real ceiling.

**Adjudication**: Codex's position is more honest. The two aren't
mutually exclusive — rather:
- Build frame-first to eliminate SELF-INFLICTED failure (which V29
  proved is material — 4 anchors silently lost at generator stage
  despite custody fixes)
- Position as "transparent auditable synthesis system" regardless
  of where the build goes, because maximal-richness positioning
  against licensed-access competitors is dishonest.

## Convergent recommendation

### The non-band-aid fix: Report Contract Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Layer 1: Report contract (YAML per research question)  │
│   - required_entities[] with DOI/PMID                   │
│   - required_fields per entity                          │
│   - required_rendering_slots (subsection / row)         │
│   - required_evidence_binding (pre-gen slot→row)        │
└────────────────────────┬────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│  Layer 2: Deterministic frame retrieval                 │
│   - CrossRef /works/{doi} for metadata                  │
│   - Unpaywall /v2/{doi} for OA PDF                      │
│   - PubMed efetch for abstract fallback                 │
│   - Existing regulatory_expander for jurisdiction docs  │
│   - Explicit `frame_gap_unrecoverable: true` on failure │
│   - Output: frame_retrieved_rows with frame_role tags   │
└────────────────────────┬────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│  Layer 3: Schema-instantiated outline                   │
│   - Efficacy decomposes per-trial from frame            │
│   - Mechanism binds to mechanism_primary row            │
│   - Regulatory one paragraph per present jurisdiction   │
│   - Empty slots generate "field not extractable" text   │
│     rather than silent omission                         │
└────────────────────────┬────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│  Layer 4: Slot-bound generation                         │
│   - Per-slot prompt binds to specific evidence row      │
│   - Required-field extraction mandatory                 │
│   - NEW validator: slot-completion, not trial-mention   │
│   - strict_verify unchanged (still refuses ungrounded)  │
└────────────────────────┬────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│  Layer 5: Enrichment (existing POLARIS)                 │
│   - M-42 bundle, contradiction detection, tier audit    │
│   - Runs ATOP the frame-bound skeleton                  │
│   - POLARIS's transparency + regulatory + contradiction │
│     wins all preserved                                  │
└─────────────────────────────────────────────────────────┘
```

### Scope (12-16 engineering days, both auditors converged)

Breaking down from Codex's list:

1. **Schema design** (2 days): YAML contract + validator for
   template authoring.
2. **Deterministic DOI/PMID retrieval** (3 days): CrossRef +
   Unpaywall + PubMed clients + fallback chain + cache.
3. **Frame compiler** (2 days): from query to report contract,
   with domain-template inheritance.
4. **Planner changes** (2 days): outline-planner gates on contract
   slots; deterministic subsection assignment.
5. **Generator prompt changes** (2 days): per-slot prompt binding
   to evidence row + required-field extraction contract.
6. **Slot-completion validator** (2 days): new validator fires on
   slot creation (not on prose trial-mention).
7. **Explicit gap reporting** (1 day): "field not extractable"
   convention + manifest tagging.
8. **Regression tests on non-clinical slug** (2 days): prove
   architecture isn't drug-specific.

Total: **16 days**. Codex's upper estimate.

### Projected outcome

- Dims 1, 4, 5 lift to BEAT_ONE or BEAT_BOTH (primary custody +
  slot completion solve the V28/V29 failure mode)
- Dim 7 (Narrative depth) PARTIALLY lifts — content that exists in
  retrievable OA/abstract form extracts cleanly; content locked
  behind paywall (Thomas clamp paper, full-text NEJM) hits honest
  gap-reporting
- Dims 2, 3, 6 preserved at BEAT_BOTH (enrichment layer)

Aggregate projection: **5-6 BB + 1-2 BO + 0 LB**. Off the current
3/0/4 plateau.

**7/7 BEAT_BOTH requires licensed primary access** — either
institutional subscriptions (infrastructure, not engineering) OR
human-in-loop evidence completion for inaccessible primaries.

### Codex's hybrid alternative

Codex's stronger non-band-aid alternative: "frame-first autonomous
pipeline plus optional licensed/human evidence completion for
inaccessible primaries".

This is architecturally cleaner than "pretend architecture solves
paywall". For 7/7 BEAT_BOTH goal:
- 16 days frame-first architecture
- Plus: institutional license budget OR human-in-loop curation
  for paywalled primaries

The licensed/human completion would be a new pipeline stage: after
frame-first retrieval runs, any `frame_gap_unrecoverable: true`
entries get human attention (a clinician confirms the primary
ETDs from their licensed copy, returns a structured quote that
enters the pipeline as a tagged row).

## Positioning regardless of architecture choice

Codex is right that POLARIS's public positioning must change
regardless:
- **Honest positioning**: "transparent, auditable clinical synthesis
  system" — per-sentence provenance, 4-jurisdiction regulatory,
  machine-readable contradictions, zero fabrication.
- **Not honest**: "ChatGPT-DR replacement on clinical trial
  narrative" — requires licensed primary access POLARIS doesn't
  have.

## Three honest paths for user

| Path | Effort | Projected outcome | Honest product claim |
|---|---|---|---|
| **A. Frame-first architecture alone** | 16 days | 5-6 BB + 1-2 BO + 0 LB | "Transparent clinical synthesis system with best-in-class regulatory + provenance" |
| **B. Frame-first + hybrid licensed completion** | 16 days + ongoing license/human cost | 7/7 BB achievable | "Transparent clinical synthesis with full primary-trial coverage" |
| **C. Ship V28 + positioning change, no further architecture** | 0 days | 3 BB + 0 BO + 4 LB (accepted ceiling) | "Complementary verification tool for ChatGPT/Gemini DR — transparency + regulatory breadth + contradiction enumeration" |

**Codex's implicit ranking**: A or B for true-quality goal. C if
user wants to ship now and correctly position.

**Claude's reconciled ranking**: Same. I over-softened "complementary
positioning" as a zero-eng alternative; Codex correctly pointed out
it should be concurrent with architecture work (positioning is not a
substitute for fixing self-inflicted failure).

## User input required

Options A/B/C above. My consolidated recommendation: **A** if goal
is "best quality achievable autonomously with current accessible
evidence"; **B** if goal is "best quality regardless"; **C** if
goal is "ship now and position honestly".

Band-aid alternatives explicitly REJECTED:
- Relax strict_verify (Codex: "`strict_verify` is doing what it
  should")
- More prompt tweaks alone (V28/V29 already proved insufficient)
- Another "custody" cycle (V29 proved custody alone ≠ content)

Root cause is architectural: no report contract. Fix is
architectural: build one.
