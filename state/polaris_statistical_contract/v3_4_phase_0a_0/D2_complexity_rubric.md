# D2 — Composite Complexity Rubric (draft for Codex review)

**Deliverable**: Phase 0a.0 / D2 — the complexity-tier (C1/C2/C3) rubric.
**Status**: LOCKED (Codex §-1.1 APPROVE 2026-05-27 "Lock D2", no blocking findings; pending operator sign-off).
**Parent**: contract v3.3 (complexity is a stratification axis); depends on D1a.
**Plan**: `PHASE_0a_0_PLAN.md` (D2 composite rubric, dominant-trigger + additive — Codex plan round-2 answer 2 + round-3).
**Version**: 0 (draft)

**Why this exists**: `complexity_tier` (C1/C2/C3) is a stratification axis in the gold-set construction (0a.-1.C `construction_manifest`, D8 allocation). The plan-review established that complexity must be a COMPOSITE pre-construction rubric (NOT source count — source count is the orthogonal D3 evidence-pool axis), scored dominant-trigger + additive. This deliverable locks that rubric so a constructor assigns C1/C2/C3 reproducibly BEFORE any claim is built.

**Orthogonality (locked)**: complexity (D2) is INDEPENDENT of evidence-pool size (D3). A simple question answered from 60 sources is C1/E4; a hard cross-jurisdiction synthesis from 4 sources is C3/E1. Source count belongs to D3 ONLY.

---

## §1. The seven complexity axes (locked)

Each axis is scored on a small pre-construction scale by the constructor, from the research question + intended claim (NOT from the retrieved corpus — complexity is a property of the question, assigned before retrieval).

| # | Axis | What it measures | Per-axis score |
|---|---|---|---|
| A1 | **Claim facets** | number of separately-verifiable sub-assertions in the claim | 0 (single facet) / 1 (2-3) / 2 (4+) |
| A2 | **Entity span** | distinct jurisdictions / trials / drug-classes / regimes the claim spans | 0 (one) / 1 (2-3) / 2 (4+) |
| A3 | **Conflict resolution** | do the relevant sources disagree, requiring adjudication? | 0 (no) / 1 (minor) / 2 (sources materially disagree) |
| A4 | **Temporal instability** | is the evidence base actively changing (recent/contested/superseded)? | 0 (stable) / 1 (some recency) / 2 (actively shifting) |
| A5 | **Reasoning operation** | lookup vs single-source synthesis vs cross-source/cross-domain inference | 0 (lookup) / 1 (synthesis) / 2 (cross-domain inference) |
| A6 | **Evidence-extraction modality + interpretive burden** | prose vs structured-record vs table/figure REQUIRING cross-row interpretation / unit conversion / subgroup selection | 0 (prose / simple structured) / 1 (structured needing light interpretation) / 2 (table/figure needing cross-row/unit/subgroup interpretation) |
| A7 | **Statistical / measurement nuance** | does correct interpretation require CI / p-value / HR / effect-size / measurement reasoning? | 0 (none) / 1 (single simple stat) / 2 (multi-stat or subtle measurement reasoning) |

Per-axis scoring criteria are illustrative anchors; the dominant-trigger + additive rule (§2) is binding.

## §2. Scoring rule — dominant-trigger + additive (Codex plan round-3)

**NOT equal-weighted.** Complexity = the HIGHER of (a) any solo C3-forcing trigger, or (b) the additive band.

### §2.1 Solo C3 triggers (any one forces C3)

A claim is **C3** if ANY of these holds, regardless of additive score:
- **A3 = 2** (sources materially disagree → conflict resolution required), OR
- **A4 = 2** (evidence base actively shifting → temporal adjudication required), OR
- **A5 = 2** (cross-domain / cross-source inference required), OR
- **A6 = 2** (table/figure requiring cross-row interpretation / unit conversion / subgroup selection — i.e. modality PLUS interpretive burden; prose extraction and simple structured records do NOT solo-trigger), OR
- **A7 = 2** (multi-statistic or subtle measurement reasoning).

Rationale (Codex round-3): these five are each individually sufficient to make a claim hard to verify correctly, irrespective of the others. A6 solo-triggers ONLY with interpretive burden — "modality alone" (a prose claim, a simple structured record) is NOT C3.

### §2.2 Additive band (when no solo trigger fires)

Sum the seven axis scores (range 0-14). Bands:
- **C1 (low)**: total ≤ 2
- **C2 (medium)**: total 3-6
- **C3 (high)**: total ≥ 7

### §2.3 Final tier

`complexity_tier = C3 if any §2.1 solo trigger else band(§2.2)`.

The constructor records the seven axis scores + the resulting tier in the construction metadata (the per-axis scores are retained for audit; the tier is the `complexity_tier` field in `construction_manifest`, 0a.-1.C §1.1).

## §3. Worked examples (illustrative)

- **C1**: "What is the FDA-approved starting dose of tirzepatide in T2DM adults?" — A1=0, A2=0, A3=0, A4=0, A5=0 (lookup), A6=0, A7=0 → total 0 → C1.
- **C2**: "Summarize 52-week HbA1c reduction for tirzepatide vs semaglutide from their pivotal trials." — A1=1, A2=1 (2 drugs), A3=1, A4=0, A5=1 (synthesis), A6=1 (trial tables), A7=1 (effect sizes) → total 6 → C2 (no solo trigger).
- **C3 (via solo trigger)**: "Reconcile the differing SGLT2i HFpEF recommendations across FDA, EMA, and Health Canada labels." — A3=2 (materially disagree) → solo-triggers C3 regardless of band.
- **C3 (via band)**: a multi-facet, multi-jurisdiction, table-heavy, multi-statistic synthesis with no single axis at 2 but total ≥7.

## §4. Definition of done (D2)

Locked: 7 complexity axes + per-axis anchors, dominant-trigger solo-C3 set (5 triggers, A6 only with interpretive burden), additive bands (C1 ≤2 / C2 3-6 / C3 ≥7), final-tier rule, orthogonality with D3 (complexity ≠ source count). Codex §-1.1 APPROVE. Operator sign-off (domain SMEs may refine per-axis anchors — anchors illustrative, the §2 rule is binding).

## §5. Dependencies + forward notes

- Needs D1a (domains) — DONE. Independent of D3 (evidence-pool) by design (§ orthogonality).
- `complexity_tier` enum {C1,C2,C3} is consumed by `construction_manifest` (0a.-1.C §1.1, currently a forward placeholder) and D8 allocation (stratification axis).
- Per-axis scores retained in construction metadata for audit; the constructor assigns them pre-retrieval from question + intended claim.
- Anchors may be refined by domain SMEs during calibration (governed amendment per contract §P4; anchors illustrative, §2 rule binding → refinement is Category-1/2 not Category-4).
