V28 fix plan pass-2 review — closes pass-1 CONDITIONAL findings.

## Pass-1 verdict (what you raised)

CONDITIONAL. 1 approved (M-48 with minor tweak), 5 needs_revision:
- M-46: launcher knob not root cause — selector early-exit bypasses floors
- M-45: AccessBypass cascade already exists — diagnose, don't add
- M-44: duplicates M-20 prompt rule — needs scorer/subset boost
- M-47: regex-only validator brittle — needs evidence-linked
- M-49: preservation_guard classification + normalized matchers

Plus 1 NEW item requested: M-50 per-trial subsection generator
for 4th BEAT_BOTH (you noted M-45 table + M-50 subsections together
reach 4-5 BEAT_BOTH instead of just killing LOSE_BOTH).

## Pass-2 revision summary

**M-48** — tightened per your revision #7:
- Per-anchor first-author variants (Rosenstock/Frías/Ludvik/Del Prato/
  Dahl/Nicholls/Jastreboff/Garvey/Wadden/Aronne) instead of single
  generic
- Population-scope labels: SURMOUNT-2 direct (T2D+obesity);
  SURMOUNT-1/3/4 indirect (obesity-only) so weight-loss claims don't
  merge non-T2D estimates into T2D efficacy prose

**M-46** — revised per your verbatim language:
- Causal stage moved to `evidence_selector.py` early-exit policy (not
  launcher knob)
- Floor computation + ranking + telemetry fire EVEN when
  pool_size <= max_rows
- Acceptance now includes your fixture test: pool=50, max_rows=100,
  anchors configured → notes present + order correct
- V28 launcher still sets cap=300 but as sweep-size control, not the
  primary mechanism

**M-44** — revised per your revisions #3 and #4:
- Scorer boost (+0.3) for is_primary_trial=True rows in Efficacy/
  Comparative/Safety/Weight Loss/CV sections (anchor-section focus
  match required)
- Same-sentence / adjacent-sentence validator replaces "every
  section every ev_id" rule
- Distinct from M-20 (scorer pre-prompt pressure vs prompt rule)

**M-45** — revised per your revision #2:
- Diagnostics phase first: refetch_diagnostics.json with backend +
  char count + content-type + eligibility per URL
- Targeted fix branches depending on whether AccessBypass invoked
  Jina/Firecrawl (wire explicitly if not) vs provider returns non-
  abstract content (use head + decimal-windows) vs all paywall
  (skip with strict contract maintained)
- No contract reversal. No statement fallback.

**M-47** — revised per your revision #5:
- Evidence-linked validator: extract candidate values from cited
  clamp/PK row's direct_quote; normalize units (mg/dL ↔ mmol/L;
  pp ↔ %); require ≥3 of those SAME values in verified Mechanism
  prose with clamp ev_id citation
- Broad numeric counts no longer satisfy the rule
- Fuzzy numeric matching (±5%) for paraphrases

**M-50** — NEW, per your completeness review:
- Outline-template extension in multi_section_generator
- Per-trial subsections for SURPASS-2, SURPASS-4, SURPASS-CVOT,
  SURMOUNT-2 when M-42e primary available
- Each subsection: N + population + comparator + endpoint + timepoint
  + effect-estimate-with-uncertainty + safety caveat (your 7 elements)
- Strict gating: ≥2 primaries required, else no subsections

**M-49** — revised per your revision #6:
- Classification fixed to `preservation_guard`
- `test_surpass_2_primary_etd_present` uses normalized matchers with
  unit variants AND requires SURPASS-2 primary bibliography citation
  in same sentence (prevents copy-from-derivative passing)
- Added parallel tests for SURPASS-4 (N=1,995 OR 104-week), SURPASS-
  CVOT (HR 0.92 + noninferiority), SURMOUNT-2 (Garvey + T2D-obesity
  label), SURMOUNT-1/3/4 indirect labeling
- Preserves partial-run skip behavior (existing M-42 suite pattern)

## AMSTAR-2 / GRADE / PRISMA additions

Your completeness review flagged three possible V28 additions:
- GRADE-style certainty per claim → deferred to V29 (out of M-44..M-50
  scope)
- Compact risk-of-bias table → partial coverage via existing
  contradiction enumeration; explicit ROB table deferred to V29
- PRISMA flow diagram → not in V28 scope

V28 bundle stays focused on the 7 content items.

## Projected outcome (revised)

3 BB + 4 BO pass-1 → **5 BB + 2 BO + 0 LB** pass-2 with M-50 added.
Dimensions flipped to BEAT_BOTH: Citations (M-44 scorer), Claim frames
(M-44+M-45+M-50), Structural depth (M-45+M-50). Regulatory +
Jurisdictional + Contradictions preserved as BEAT_BOTH. Narrative depth
remains BEAT_ONE (Gemini still deeper on receptor pharmacology; V29
scope to close).

## Your pass-2 task

Read `outputs/audits/v27/fix_plan_v28.md` (pass-2 revision,
committed after this brief). Verify every pass-1 concern is resolved
in pass-2. Write your verdict to
`outputs/codex_findings/v28_fix_plan_review_pass2/findings.md`.

Per-item: approve | still_needs_revision | reject.

Ping-pong budget: you have 1 remaining pass of 3 per §7 #11. On
pass-2 APPROVED: Claude begins M-48 implementation immediately.
On still CONDITIONAL: pass-3 or surface to user.
