# CODEX ARCHITECTURE REVIEW — POLARIS Permanent-Fix Migration Blueprint (I-perm-000)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## What this review IS (read carefully — this is NOT a code-diff review)

This is an **ARCHITECTURE review** of an **operator-directed strategic reframe**, not a review of a code diff. No code has been written yet. You are pressure-testing a *design blueprint* (`docs/permanent_fix_migration_blueprint.md`) that proposes migrating the POLARIS deep-research pipeline from one governing posture to another:

- **FROM:** WITHHOLD-when-imperfect — ~7 stacked aggregate gates (scope-reject, corpus-inadequate, corpus-approval-denied, per-section <40%-verified drop, four-role <70%-coverage hold, S0-must-cover hold, zero-verified abort) can each withhold, abort, or thin a research report even after deep research succeeded.
- **TO:** ALWAYS-RELEASE with honest **per-claim confidence + provenance**, and let the human reader judge.

**The ONLY hard line** (operator-locked, NOT negotiable, NOT relaxable by you): **never assert an *ungrounded* claim as fact.** An unsupported claim ships as a transparent "no grounded source found" label — never silently, never as confident prose. Safety caveats are shown PROMINENTLY. This radical-transparency posture is also the deliberate differentiator vs ChatGPT/Gemini deep-research (which ship confident-looking unsupported citations).

The blueprint's core safety claim is a **RELOCATION, not a relaxation**: *aggregate/report-level* gates move from trap-doors to DISPLAYED labels and always release; *per-CLAIM* faithfulness gates (strict_verify numeric-in-span + ≥2 content-word overlap + entailment; the FABRICATED occurrence latch; the zero-grounding abort) stay BINDING and byte-unchanged. No per-claim threshold is lowered.

## The empirical keystone this program is built on (verify the logic, not just trust it)

`outputs/audits/beatboth8/drb_76/` is a fully-rendered clinical report that was **BLOCKED** (`status=abort_four_role_release_held`, `release_allowed=False`, `coverage_fraction=0.40`, `held_reasons=['d8_unsupported_residual_below_coverage','d8_s0_must_cover_missing:contraindications','d8_pending_rewrite']`) — yet the report **shipped the exact contraindication safety fact** ("*S. boulardii* probiotics are not recommended for patients who are immunocompromised, critically ill, or have indwelling catheters") as a VERIFIED claim on the page. The must-cover gate fired `missing:contraindications` *while the safety fact was present and verified*. Zero fabrication defects; the user never saw the report. That false-withhold is the bug class this 9-issue program kills.

---

## THE ASK (what you must rule on, with evidence)

Emit your verdict in the §8.3.9 YAML schema (below) PLUS two extra blocks. Be concrete and cite file:line / blueprint-section where you can.

### 1. RULE ON EACH OF THE 6 OPEN TENSIONS (blueprint Section 6) — `tension_rulings:` block, one ruling each.
The two HIGHEST-STAKES are #1 and #2; spend most of your judgement there.
- **Tension 1 — caveat PROMINENCE vs the clinical hard line.** Is top-of-report caveat placement an *empirically sufficient* structural guarantee, or merely assumed? Is there a class of report (e.g. ALL S0 safety categories are disclosed-gaps) where ABORT is still the correct behavior rather than always-release? Do we need a stronger structural guarantee (interstitial acknowledgement, or refuse-to-release-clinical-when-all-safety-categories-are-gaps)?
- **Tension 2 — is `has_any_verified_claim` (1-of-N, per-REPORT) the right release floor?** A report with 1 verified claim of 37 where the other 36 are all safety-critical would release. Should the floor be **per-SECTION** (a Safety section with zero verified claims is a hard-block even if other sections are rich), not per-report? This is the single highest-stakes parameter in the reframe and interacts with I-perm-001's `hard_block` definition. RULE on per-section-vs-per-report explicitly.
- **Tension 3 — credibility-as-weight + `independent_origin_count` echo risk.** Can 3 low-credibility sources echoing one unsupported claim render "moderate · 3 sources" and read as corroborated? Must "independent origin" be gated on credibility, and must the chip never exceed "low" for a non-VERIFIED claim regardless of origin count?
- **Tension 4 — pooled cross-document re-anchor (I-perm-002 reusing I-perm-004's argmax over the whole pool).** Is the title-anchor guard sufficient to prevent re-pointing a claim to a coincidental match in an UNRELATED paper, or is a same-population/same-intervention check required before crediting cross-document satisfaction of a *safety* category?
- **Tension 5 — `released_with_disclosed_gaps` as a success-adjacent status weakening the regression signal.** Once a True→False `release_allowed` flip is no longer auto-CRITICAL, what `release_quality_score`-drop magnitude should trip the alert, and is detection of a *new systematic withholding* bug lost?
- **Tension 6 — I-perm-003's honest no-op.** Acceptable to merge I-perm-003 with only synthetic-pool proof (the selector drops 0 on beatboth8), or must it be sequenced strictly AFTER I-perm-007 grows a real pool?

### 2. CONFIRM THE NO-FABRICATION HARD LINE IS PRESERVED.
Specifically verify the design keeps: (a) per-claim gates untouched (strict_verify, provenance entailment, report_redactor refuse-in-place); (b) the FABRICATED occurrence latch byte-unchanged (`release_policy.py:200-205`); (c) the zero-grounding abort retained (narrowed to true zero-verified-AND-zero-evidence, rendering an honest report). Flag ANY place in the 9-issue design where the reframe could let an UNSUPPORTED or FABRICATED claim ship as confident fact.

### 3. CHECK THE BUILD-ORDER / DEPENDENCY PLAN IS SOUND (blueprint Section 4).
Especially: is **Decision B (the shared per-claim confidence + `ReleaseDisclosure` schema) landing BEFORE I-perm-004/005** correctly sequenced so 004 (populates) and 005 (renders) don't deadlock? Is the keystone-first ordering (001 → {002,004,005,006}) right? Are the CORE-lane serialization (release_policy.py / native_gate_b_inputs.py hot files) and the I-perm-008 Key-Findings-ordering-fix-can-land-early calls correct?

### 4. `required_design_changes:` block — anything that MUST change before any code is written.

### 5. Output schema (§8.3.9) — emit EXACTLY this, plus the two extra blocks above:
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
tension_rulings:
  tension_1_caveat_prominence_vs_clinical_floor: "<ruling>"
  tension_2_per_section_vs_per_report_floor: "<ruling>"
  tension_3_credibility_echo: "<ruling>"
  tension_4_cross_document_reanchor: "<ruling>"
  tension_5_regression_signal: "<ruling>"
  tension_6_iperm003_no_op_sequencing: "<ruling>"
required_design_changes: [...]
```

---


## DOCUMENT 1 (FULL TEXT) — `docs/permanent_fix_migration_blueprint.md`

```markdown
# POLARIS Permanent Fix — Migration Blueprint (I-perm-001 … I-perm-009)

**Status:** Architecture synthesis, ready for Codex review. Authored 2026-06-10.
**Charter:** `docs/permanent_fix_9_issues.md` (9 issues, operator-directed).
**Governing reframe (the spine):** the pipeline changes from **WITHHOLD-when-imperfect → ALWAYS-RELEASE with honest per-claim confidence + provenance; the user judges.** The ONLY hard line: **never assert an *ungrounded* claim as fact** — an unsupported claim ships as a transparent "no grounded source found," never silently; safety caveats are PROMINENT. This is also the differentiator vs ChatGPT/Gemini (radical transparency, not a confident oracle).

> **Empirical keystone (verified against saved data, not asserted).** `outputs/audits/beatboth8/drb_76/` is a fully-rendered report (`report.md` on disk, report_redaction.redacted_count=14) that was **BLOCKED** with `status=abort_four_role_release_held`, `release_allowed=False`, `coverage_fraction=0.40`, `held_reasons=['d8_unsupported_residual_below_coverage','d8_s0_must_cover_missing:contraindications','d8_pending_rewrite']`. The contraindication safety claim `03-001-1595ee4d` ("…*boulardii* probiotics are not recommended for patients who are immunocompromised, critically ill, or have indwelling catheters [#ev:probiotic_immunocompromised_contraindication:23400-24200]") **ships verified content** yet carries `s0_categories=[]` and `covered_element_ids=[]` — so the must-cover gate fired `missing:contraindications` **while the exact safety fact was on the page.** Zero fabrication defects; the user never saw the report. That is the bug class this program kills.

---

## 1. TARGET ARCHITECTURE — the always-release+label model, end to end

This is one coherent path, **not** 9 silos. The single invariant that makes the reframe safe:

> **Aggregate / report-level gates are RELOCATED to DISPLAYED labels and ALWAYS release. Per-CLAIM faithfulness gates are UNTOUCHED and remain binding.** No threshold is lowered — each is moved from a trap-door to a label. The hard floor stays exactly where the SOTA puts it (per claim).

### 1.1 The end-to-end spine (left to right)

```
  scope_gate                fetch + extract            evidence selection
  (review-not-reject)  ─▶    (I-perm-007 grows    ─▶    (I-perm-003 best-ranked,
  unsupported_domain =       the real pool:             corpus-scaled, LITM
  loud config error          GROBID/openFDA/            reorder; no fixed cap)
  still loud)                DailyMed; honest
                             unreachable disclosure)
        │                          │                          │
        ▼                          ▼                          ▼
  generation (multi_section / clinical_generator)
  low-confidence sections SHIP as LABELED stubs, never drop-to-nothing
        │
        ▼
  ┌─────────────────────────  PER-CLAIM FLOOR (BINDING, UNCHANGED)  ─────────────────────┐
  │  strict_verify (numeric-in-span + ≥2 content-word overlap + entailment)              │
  │  span_resolver re-anchor to the best ENTAILING substantive span (I-perm-004)         │
  │  FABRICATED occurrence latch (release_policy.py:200-205) — HARD BLOCK, byte-unchanged │
  └──────────────────────────────────────────────────────────────────────────────────────┘
        │
        ▼
  corpus-wide satisfaction (I-perm-002): a required element/S0 category is SATISFIED iff
  SOME verified claim ANYWHERE in the pool ENTAILS its requirement hypothesis (pooled,
  polarity-aware NLI) — not a single-source exact-string match.
        │
        ▼
  ┌──────────────────  4-ROLE BECOMES A LABELER (I-perm-001 + I-perm-005)  ───────────────┐
  │  held_reasons  ──▶  disclosed_reasons   (same audit strings, no longer block)          │
  │  coverage_fraction  ──▶  release_quality_score   (DISPLAYED, identical value)          │
  │  S0-missing  ──▶  prominent caveat ("No grounded source found for <category>")         │
  │  pending_rewrite  ──▶  removed (I-perm-006: the rewrite the architecture never runs)   │
  │  release_allowed = NOT fabricated_latched  AND  has_any_verified_claim   (ONLY blocks) │
  └────────────────────────────────────────────────────────────────────────────────────────┘
        │
        ▼
  render (I-perm-005): per-claim confidence chip {high|moderate|low|no-source-found} +
  provenance inline in report.md AND web Proof-Replay; prominent top-of-report safety caveats
        │
        ▼
  report_redactor  ──▶  annotator (I-perm-008 wording + I-perm-005 verb):
  a non-VERIFIED claim is KEPT and LABELED, not deleted; only a truly UNGROUNDED claim
  (no resolvable token) renders the explicit "No grounded source was found" line
        │
        ▼
  bundle.py: ships the report. 422 ONLY on hard_block (fabricated OR zero-grounding),
  never on release_allowed=False-for-a-disclosed-gap.
```

### 1.2 How the ~7 gates become labels

| # | Gate (today) | File:line | Today's block | Becomes (label mode) |
|---|---|---|---|---|
| 1 | scope_gate reject | `nodes/scope_gate.py:428-435` (unsupported_domain), `:541-552` (clinical_pico_unscoped) | `abort_scope_rejected`, returns before retrieval | unsupported_domain = **stays a loud config error** (no template = real error). clinical_pico_unscoped → `scope_decision='review'` + needs_user_review note, **proceed with disclosure** |
| 2 | corpus_adequacy critical | `nodes/corpus_adequacy_gate.py:242-247` | `abort_corpus_inadequate` (tier-COUNT proxy) | weighted-corpus disclosure becomes DEFAULT path under label mode (planner + legacy); tier-count critical → disclosure; `has_usable_corpus` is the retained zero-floor |
| 3 | corpus_approval deny | `nodes/corpus_approval_gate.py:374-423` | `abort_corpus_approval_denied` | **already migrated** (I-cred-006b `weighted_corpus_gate.py`): PROCEED + credibility disclosure. Make it default-on under label mode |
| 4 | per-section <0.40 verified | `clinical_generator/generator.py:56`, multi_section drop | section dropped | DISPLAYED per-section confidence on the `is_gap_stub` path (BB5-C07 #1178 already exists); never drop-to-nothing |
| 5 | four-role coverage <0.70 | `roles/release_policy.py:241-253` | `d8_unsupported_residual_below_coverage` hold | `release_quality_score` (DISPLAYED, same fraction) |
| 6 | S0 must-cover missing | `roles/release_policy.py:255-273` | `d8_s0_must_cover_missing:<cat>` hold | corpus-wide satisfaction (I-perm-002) credits it correctly; residual → prominent caveat |
| 7 | zero-verified abort | `clinical_generator/generator.py:290` | `abort_no_verified_sections` | **RETAINED** as the only true-zero-grounding abort, BUT renders an honest "insufficient grounded evidence" report (not a stub) |

The **template** for all of this already exists in-repo: I-cred-006b's `weighted_corpus_gate.py` converted gate 3 from BLOCK → PROCEED+disclose. The program generalizes that pattern to gates 1,2,4,5,6.

### 1.3 The two hard blocks that survive (the no-fabrication hard line)

1. **FABRICATED occurrence latch** — `release_policy.py:200-205`. One-way, rewrite does not clear it. **Byte-unchanged.** A fabricated identity is never a disclosure.
2. **Zero-grounding** — zero VERIFIED claims AND zero usable evidence → still aborts, but renders an honest "insufficient grounded evidence" report. "Always release" narrows abort to true zero-grounding; it does not remove it.

Everything else (coverage shortfall, S0-missing, pending-rewrite, PARTIAL advisory) moves from `held_reasons` into `disclosed_reasons` + per-category status + caveats.

---

## 2. CROSS-CUTTING DECISIONS (resolved here, binding on all 9)

The per-issue research proposed three contracts that **collide**. As synthesis lead I resolve them once so downstream issues do not build the split-brain that is literally I-perm-001's own risk #6.

### DECISION A — ONE master flag: `PG_ALWAYS_RELEASE`
The I-perm-001 research proposed `PG_RELEASE_MODE='label'`; I-perm-005 proposed `PG_ALWAYS_RELEASE`; both describe the *same* switch. **Binding: the single master flag is `PG_ALWAYS_RELEASE`** (1 = the reframe is live for the whole stack; unset/0 = current block behavior, byte-identical for rollback per LAW VI). It is **defined and owned by I-perm-001**. No per-gate label flags. Per-*feature* sub-flags stay distinct **under** the master:
- `PG_CORPUS_SATISFACTION` (I-perm-002 pooled-entailment, residual-only)
- `PG_PROVENANCE_REANCHOR` (I-perm-004 re-anchor; default-on under the reframe once Codex-approved)
- `PG_SPAN_RESOLVE_TOPK` (I-perm-004 judge-call bound, default 4)
- `PG_SELECT_CROSS_ENCODER`, `PG_SELECT_LITM_REORDER` (I-perm-003, default OFF until smoke-proven)
- `PG_SECTION_REPAIR` (I-perm-006 generator regen loop, default 0/OFF)
- `PG_GROBID_URL`, `PG_QUANTIFIED_SPEC_MAX_TOKENS` (I-perm-007)

### DECISION B — ONE shared per-claim confidence schema (co-designed BEFORE 001/004/005 land)
I-perm-001 emits it, I-perm-004 populates it, I-perm-005 renders it — so the dataclass is a cross-cutting contract that must exist **before** any of the three merges, or 004 and 005 deadlock on each other. **Binding contract** (extend the existing `SentenceVerification` dataclass + a new `ReleaseDisclosure`):

```python
# per-claim (on SentenceVerification + claim_confidence.json)
verdict: str               # VERIFIED | PARTIAL | UNSUPPORTED | UNREACHABLE | FABRICATED | NO_SOURCE
span_verdict: str          # SUPPORTS | UNSUPPORTED      (existing disclosure_population field)
credibility_weight: float | None   # MIN over cited sources (existing)
independent_origin_count: int      # distinct Phase-4 origin clusters (existing)
provenance_quality: str    # prose | title | header | affiliation | nav_link | url | altmetric | reference_list
confidence: float          # f(argmax entailment strength, boilerplate penalty, numeric-verbatim match)
confidence_bucket: str     # high | moderate | low | no-source-found   (the rendered chip)
best_span: tuple[int,int]  # the re-anchored span (I-perm-004)

# per-report (ReleaseDisclosure, the I-perm-001 data contract)
released: bool
release_quality_score: float            # = coverage fraction, DISPLAYED not gated
per_category_status: dict[str,str]      # category -> covered | disclosed_gap
prominent_caveats: list[str]            # one per missing S0 safety category
hard_block: bool                        # TRUE only if fabricated_latched OR zero-verified-and-zero-evidence
disclosed_reasons: list[str]            # the old held_reasons strings, audit-preserved
```

`confidence_bucket` rule (clinical-safety invariant): **a non-VERIFIED claim can NEVER render `high`.** `high` requires `verdict==VERIFIED AND credibility>=high AND origins>=2`. Unknown credibility → `low` (never inflates). Zero resolvable cited evidence → `no-source-found`. The bucket is a **pure deterministic function** of the fields above — no LLM call, no spend.

### DECISION C — `released_with_disclosed_gaps` is a new non-abort terminal status
Add to `src/polaris_v6/schemas/run_status.py` `PipelineStatus` Literal + the `_UNIFIED`/`_SUMMARY_TO_UNIFIED` maps in `run_honest_sweep_r3.py:209-252`. `four_role_released`→`success` stays for clean runs; the hard-block path (fabricated/zero-verified) → `abort_no_verified_sections` rendering the honest report. `abort_four_role_release_held` is **retired for the non-fabrication case**.

---

## 3. PER-ISSUE MIGRATION

Each block: best-practice adopted (+ cited source) → concrete our-code edits at file:line → risks → smoke posture. Smoke detail is consolidated in §5.

### I-perm-001 (#1195) — Release-model reframe (the keystone)
**Best practice:** SAFE (DeepMind, arXiv:2403.18802) — decompose to atomic facts, REPORT the supported/not-supported counts (F1@K) rather than suppressing the answer. CRAG (arXiv:2401.15884) / Self-RAG — a confidence degree drives {use / caveat / corrective-retrieve} ACTIONS, never a whole-answer withhold. Conformal/soft abstention ("Knowing When to Abstain: Medical LLMs Under Clinical Uncertainty", arXiv:2601.12471) — the clinical literature distinguishes HARD abstention (refuse) from SOFT abstention (hedged + labeled); the clinical floor is satisfied by CLAIM-level abstention + a prominent caveat, **not** by withholding a grounded report. In-repo template: I-cred-006b `weighted_corpus_gate.py` (BLOCK→LABEL already done for the corpus gate).

**Our-code edits:**
- **NEW** `src/polaris_graph/roles/release_disclosure.py` — `build_release_disclosure(...) -> ReleaseDisclosure` (Decision B fields). This is the data source I-perm-005 renders.
- `roles/release_policy.py` — add `apply_d8_release_policy_label(...)` gated on `PG_ALWAYS_RELEASE`. Label mode: `held_reasons`→`disclosed_reasons` (same strings, audit-preserved); `release_allowed = NOT fabricated_occurrence_latched AND has_any_verified_claim`. Coverage-shortfall (`:241-253`), S0-missing (`:255-273`), pending-rewrite (`:296-297`) move into disclosed_reasons + per_category_status + caveats. **Keep the FABRICATED latch (`:200-205`) byte-unchanged.**
- `roles/sweep_integration.py:654-672` — when `PG_ALWAYS_RELEASE`, call the label path; carry `disclosed_reasons` + `per_category_status` into `FourRoleEvaluationResult`.
- `run_honest_sweep_r3.py:7120-7131` — map `released==True` + non-empty disclosed_reasons → `released_with_disclosed_gaps`; keep hard-block → `abort_no_verified_sections` rendering the honest report; attach `manifest.release_disclosure`.
- `src/polaris_v6/api/bundle.py:116,215` — stop 422-refusing on `release_allowed=False` alone; refuse ONLY on `hard_block`.
- `src/polaris_graph/audit_ir/regression_alerts.py:47` — under label mode, a `release_allowed` True→False flip is no longer auto-CRITICAL; the new regression signal is a `release_quality_score` drop or a NEW fabrication.
- `report_redactor.py` STAYS as the per-claim faithfulness enforcer (made always-release-safe by I-perm-008 wording + I-perm-005 verb).

**Risks:** (1) accidentally relaxing a per-CLAIM check — mitigated: only the aggregate decision + bundle 422 change; strict_verify / provenance entailment / report_redactor refuse-in-place are untouched. (2) FABRICATED folded into disclosure — mitigated: stays a hard block. (3) the clinical one — a missing safety category ships silently — mitigated: the missing S0 category becomes a PROMINENT top-of-report caveat (louder than the old generic abort stub). (4) "always release" read as "release with zero grounding" — mitigated: hard_block on zero-verified-and-zero-evidence still aborts (honest report). (5) regression-alert split-brain — mitigated by the alert-semantics update. (6) env split-brain — mitigated by the single `PG_ALWAYS_RELEASE` (Decision A).

### I-perm-002 (#1196) — Corpus-wide satisfaction (kill tunnel vision)
**Best practice:** MiniCheck (EMNLP 2024, arXiv:2404.10774) — grounded entailment primitive `score(docs, claims)→(label,prob)`, GPT-4-level at ~400× lower cost; the correct posture is "supported iff SOME doc supports it: max_j M(D_ij, c_i)". SciFact / SciFact-Open (EMNLP 2020 `2020.emnlp-main.609`; arXiv:2210.13777) — claim verification is multi-document by definition. FActScore (arXiv:2305.14251) / SAFE (arXiv:2403.18802) — ratio over a SOURCE SET, not one doc.

**The seam (verified on saved drb_76):** `native_gate_b_inputs.py:478` `_resolve_evidence` returns records from ONLY this claim's cited tokens (the tunnel). `:312-328` `_content_requirements_satisfied` does `all(token.lower() in claim_text.lower())` — the contraindication entity requires `[contraindicated, immunocompromised]`; the shipped claim has "immunocompromised" but NOT the literal "contraindicated" → False (the proximate blocker). `:331-352` `_claim_covers_entity` returns False → `s0_categories=[]` (confirmed: claim `03-001` cites the entity, ships the safety content, carries `s0_categories=[]`). `release_policy.py:255-273` then fires `d8_s0_must_cover_missing:contraindications`.

**Our-code edits:**
- **NEW** `src/polaris_graph/roles/corpus_satisfaction.py` (PURE, no network, DI) — `satisfy_residual_requirements(*, kept_verified_claims, required_entities, residual_element_ids, residual_s0_categories, entailment_fn) -> PooledSatisfaction`. For each RESIDUAL element/S0 category (still uncovered after the existing exact-match pass), build an NL hypothesis from a NEW per-entity config field `coverage_claim` (fallback `label_name`); run `entailment_fn` over EVERY kept VERIFIED claim in the WHOLE pool; credit iff SOME returns ENTAILED (max-entailment). NEUTRAL/CONTRADICTED never credit (fail-closed, polarity-aware). Base satisfaction on verified-claim CONTENT only — **never pooled identifiers**.
- `sweep_integration.run_four_role_evaluation` — AFTER the per-claim loop, compute residuals; if non-empty call `satisfy_residual_requirements` with `entailment_fn` = adapter over the existing `_EntailmentJudge` (GPU-free via OpenRouter); add returned ids to `internal_ledger.covered_element_ids`.
- `release_policy.apply_d8_release_policy` — add param `additionally_covered_s0_categories: set[str]`; union into `verified_categories` before `:256-262`. Pure function stays pure.
- `config/scope_templates/*.yaml` — add `coverage_claim` per required entity (LAW VI).
- Env `PG_CORPUS_SATISFACTION` (under `PG_ALWAYS_RELEASE`); residual-only → flag-off / all-exact-matched is byte-identical.

**Why residual-only:** bounds spend (no O(elements×claims) blowup — drb_76 fires for exactly 1 category), gives flag-off byte-identity, still catches the cross-document case.

**Risks:** over-crediting a safety category — mitigated: only ENTAILED credits, the supporting claim is itself VERIFIED, polarity-aware (a "probiotics are safe in immunocompromised patients" claim does NOT credit). Identifier pollution (`normalize_evidence_pool_lookup:201-211` scrapes a wrong DOI/PMID from reference boilerplate) is an I-perm-004 dependency — satisfaction is content-based to stay safe regardless. No-fabrication untouched: it only credits coverage of an EXISTING verified claim; never injects content, never lowers 0.70.

### I-perm-003 (#1197) — Selection done right (HONEST: preventative on beatboth8)
**CRITICAL HONESTY (verified):** the selector discards **nothing** on this data. drb_76 `evidence_selected=46, dropped_count=0` (pool ≤ max_ev so the short-pool no-drop branch fired). The issue's "keeps ~46 of ~500" premise is **misattributed** — the real ~90% loss is UPSTREAM (fetch→row, owned by I-perm-007). I-perm-003 owns "selection done right," which on CURRENT pools is **preventative/enabling**, load-bearing only once I-perm-007 + I-perm-002 deliver a genuinely large pool. **This must be stated plainly to Codex or the fix is a no-op that cannot be proven on beatboth8.**

**Best practice:** ICLR 2025 "Long-Context LLMs Meet RAG" (arXiv:2410.05983) — more passages can HURT via hard negatives; retrieval REORDERING (highest-scored at BEGINNING and END, weakest in the MIDDLE) "significantly and consistently" helps for LARGE sets. Two-stage retrieve→cross-encoder-rerank→top-K (Ailog 2025 reranking guide). RAGChecker (arXiv:2408.08067) — pack per-section at claim granularity, not a global top-5. A small `ms-marco-MiniLM-L-6-v2`-class cross-encoder (~22M params) is CPU-runnable, deterministic, open-weight (§8.4 no-CUDA + sovereignty).

**Our-code edits:**
- **NEW** `src/polaris_graph/retrieval/evidence_budget.py` — `compute_generation_budget(n_rows, n_sections, env) -> int = clamp(ceil(coverage_frac*n_rows), floor=legacy_max_ev, ceiling=token-budget-derived)`. Wire `run_honest_sweep_r3.py:4508` to call it instead of a raw env int. **KEEP `PG_LIVE_MAX_EV_TO_GEN` as the hard ceiling** (no silent removal).
- **NEW** `src/polaris_graph/retrieval/cross_encoder_reranker.py` — small CPU cross-encoder behind `PG_SELECT_CROSS_ENCODER` (default OFF), fail-LOUD (no silent lexical fallback), model load gated + `gc`-released per §8.4, single load per run. Replaces lexical `_row_relevance` (`evidence_selector.py:406-423`) as the ranking key; tier quotas / jurisdiction / primary-anchor floors STAY.
- **NEW** pure `reorder_for_long_context(rows)` — U-shaped placement, applied in `multi_section_generator.py` per-SECTION right before prompt assembly, behind `PG_SELECT_LITM_REORDER`. Selector's final sort untouched (telemetry/determinism stays).

**Risks:** the dominant risk is the INVERSE of fabrication — a completeness/recall loss (fixed tiny cap drops a dose/contraindication; lexical ranking buries the pivotal RCT; no LITM reorder buries mid-context evidence). All three layers PROTECT recall. Reranker must be deterministic + open-weight/CPU; flag-gated OFF + fail-LOUD. Budget ceiling must respect the writer context window. No silent cap removal.

### I-perm-004 (#1198) — Verification recovery + label-not-delete
**Best practice:** RARR (ACL 2023, arXiv:2210.08726) — retrofit attribution: research + REVISE the attribution, "preserving the original output" rather than deleting. ALCE (EMNLP 2023, `2023.emnlp-main.398`) — citation RECALL (cited span entails the sentence) + PRECISION (each cited span is precisely cited); a claim on a span that doesn't entail it is a precision failure (idx 9). MiniCheck max-over-evidence (arXiv:2404.10774) — argmax over candidate chunks, not verify-against-one-bound-span. NLI directional asymmetry ("Entailed Between the Lines", arXiv:2501.07719; "NLI under the Microscope", arXiv:2502.08080) — NLI is lexical-overlap biased and misses the case where the HYPOTHESIS generalizes beyond the PREMISE (#1180 scope-widening); remedy is atomic-hypothesis decomposition + explicit directional prompting validated on a labeled set.

**The structural root (two divergent, both-wrong span paths in `provenance_generator.py`):**
- ACCEPT path (gap-#18, `:1811-1917`) — on a NEUTRAL narrow-span verdict it re-judges a 400-char local window and PASSES the sentence but **never re-points the [#ev] token** (logs "span_imprecise but locally grounded; passing"). This is how idx 9 ("pks+ E. coli strongly linked to CRC") shipped KEPT, bound to an altmetric/badge span (4900-5700) while the real support sits at 9700-10500/14500-15300 in the SAME row.
- DROP path (#1189 `_try_reanchor`, `:1063`) — single-token only (`:1107`), accepts the FIRST passing candidate with no boilerplate filter and no best-span ranking (drb_76 has "reanchored:...0-76" = the TITLE). Flag-OFF by default.
- Over-drop magnitude (drb_76 verification_details): 40 verified / 41 dropped of 81; 29 `entailment_failed` on the narrow bound span while support exists elsewhere IN-ROW.

**Our-code edits:**
- **NEW** `src/polaris_graph/generator/span_resolver.py` — `resolve_best_entailing_span(...)`: (1) candidate generation (harden `_reanchor_candidate_spans`); (2) NEW deterministic `classify_span(text)→{prose|title|header|affiliation|nav_link|url|altmetric|reference_list}` (boilerplate = DEPRIORITIZATION + confidence penalty, NOT hard exclude); (3) cheap lexical pre-rank → top-k (`PG_SPAN_RESOLVE_TOPK` default 4) → judge only top-k → ARGMAX; (4) RARR re-point: ALWAYS rewrite the [#ev] token to the argmax span; (5) emit per-claim `{verdict, confidence, provenance_quality, best_span}` (Decision B schema).
- Wire into `verify_sentence_provenance` — replace the gap-#18 accept block with the resolver (re-point, not just pass); replace `_try_reanchor` first-passing loop with the SAME argmax; make `PG_PROVENANCE_REANCHOR` default-on under the reframe (it can only ever bind to a span passing the SAME full gate → no new fabrication path).
- Wire into `clinical_generator/strict_verify.verify_sentence` — on NEUTRAL/CONTRADICTED, resolve over bound rows before the drop.
- `#1180` widening — add a specific→general directional clause to `entailment_judge._ENTAILMENT_PROMPT`, SELECTED by a bakeoff over a labeled directional set (`tests/fixtures/widening_labeled_set.json`) maximizing directional accuracy without regressing the VERIFIED-15.
- `#1176` qualifier-drop: I-perm-004 scope = DETECT/LABEL via the widening rule; PRESERVING the qualifier is a generator-contract concern (filed as the generator companion, not built here).

**Hard-line boundary:** label-not-delete applies to recoverable/imperfect-but-grounded claims. DROP→"no source found" REMAINS for: no provenance token, evidence_not_in_pool, OR no substantive entailing span anywhere in the corpus.

**Risks:** re-anchor must never manufacture support — mitigated: every re-pointed token passes the SAME full gate with `allow_local_window_fallback=False`; argmax only CHOOSES among passing candidates. Boilerplate as deprioritization (a title-only-supported claim ships LABELED low-confidence, never silently VERIFIED). #1180 widening TIGHTENS the shared prompt (drops more) — net-positive ONLY co-delivered with the recovery; prove on the labeled set the VERIFIED-15 don't regress. Confidence must be dominated by "final bound span verbatim-entails", not lexical similarity. Process: do NOT relax any assertion to pass; brief Codex with the RESOLVED span text per claim (not a conclusion).

### I-perm-005 (#1199) — Per-claim render + 4-role→LABELER + credibility = WEIGHT-and-DISCLOSE
**Best practice:** RA-RAG (arXiv:2410.22954) — estimate per-source reliability by cross-source agreement; aggregate by weighted majority voting; "low-reliability sources are RETAINED but DOWNWEIGHTED — they do not disappear." SAFE/LongFact (arXiv:2403.18802) — long-form factuality = F1 of PRECISION and RECALL; deleting a checkable claim tanks recall (the exact completeness lever to beat ChatGPT). "Cited but Not Verified" (arXiv:2605.06635) — frontier DR ships ~23-61% factually-unsupported citations with a confident [N]; POLARIS's edge is to KEEP the claim but LABEL its support honestly. Progressive confidence ("Towards Trustworthy Report Generation", arXiv:2604.05952) + abstention survey (Wen et al., TACL 2024) + SimpleQA tri-state — "no grounded source" is a first-class DISPLAYED outcome. UX precedent: Consensus "Consensus Meter", scite Smart Citations (supporting/mentioning/contrasting) — a discrete per-claim chip.

**Our-code state (verified):** the disclosure DATA pipeline is ALREADY BUILT + faithfulness-safe (`synthesis/disclosure_population.py:85-115` emits span_verdict / credibility_weight / independent_origin_count / certainty_label via `dataclasses.replace`, never mutating `is_verified`; `synthesis/credibility_pass.py:222-296` is the shared populate; `run_honest_sweep_r3.py:300-338` writes `claim_disclosure.json` as a SIDECAR). What's missing/wrong: (i) the RENDER (data never reaches report.md or UI), (ii) the VERB at the 4-role seam (`report_redactor.py:85-88` DELETEs to the gap stub; drb_76 redacted 14 claims). Credibility-as-weight is mostly DONE (`weighted_corpus_gate.py` I-cred-006b; `authority/credibility_skill.py:241-258` advisory-only), but a residual journal-only FILTER (`JOURNAL_ONLY_BENCHMARK_SLUGS`, #1146/#1147) still hard-excludes non-journal sources for some slugs.

**Our-code edits:**
- **NEW** `src/polaris_graph/generator/claim_labeler.py` (PURE) — `confidence_bucket(...)` (Decision B rule) + `annotate_report_against_verdicts(...)`: for each non-VERIFIED claim, KEEP the sentence + append a compact inline marker (reuse `report_redactor`'s tiered sentence-location logic, refactored into a shared `_locate` module to carry the byte-safe neighbor-citation invariants). Only a genuinely UNGROUNDED claim → "No grounded source was found for this statement; it is shown unverified."
- FLIP the call site `run_honest_sweep_r3.py:7190-7293` — under `PG_ALWAYS_RELEASE`, call `annotate_*` not `reconcile_*`; status → `released_with_labels`/`released_with_disclosed_gaps`; add `manifest.confidence_summary`. Keep the OLD redactor path when OFF.
- RENDER inline chips in report.md body (`:6298-6318`) from `disclosure_by_claim`; soften `key_findings.py:100-104` preamble; emit `claim_confidence.json` as the single machine-readable contract.
- UI — `web/lib/inspector_bundle_loader` surfaces the 4 fields + bucket; **NEW** `web/components/verdict/confidence_chip.tsx` (color-coded {high/moderate/low/no-source-found} with credibility + origin + tier in an **accessible aria-label** — operator is blind, text-first); `proof_replay.tsx:23-79` replaces the binary `verified:boolean` with `confidence_bucket`.
- Credibility = weight everywhere: under the reframe make the residual journal-only FILTER DISCLOSE-not-exclude (reuse `weighted_corpus_gate.build_corpus_credibility_disclosure`); coordinate corpus-side with I-perm-002.

**Risks:** a "low" chip must read as NOT asserted-as-fact (unmistakable wording "low — UNSUPPORTED by cited source"); strict_verify stays the binding gate (never flipped). A withheld contraindication is more dangerous than a labeled one, BUT a wrongly-confident one is lethal — keep an S0/safety rule that PROMOTES (not deletes) low-confidence safety claims to a prominent "Safety — verify independently" block. Credibility weight can't promote an unverified claim (`high` requires VERIFIED). The chip is a pure deterministic function (no LLM). Single source `claim_confidence.json` prevents render drift. Whole change behind `PG_ALWAYS_RELEASE`.

### I-perm-006 (#1200) — Kill the pending-rewrite loop + speed
**Best practice:** "LLMs Cannot Self-Correct Reasoning Yet" (ICLR 2024, arXiv:2310.01798) — intrinsic self-correction without external feedback does NOT help, often DEGRADES. "Is Self-Repair a Silver Bullet?" (ICLR 2024, arXiv:2306.09896) — repair budget is often better spent on independent resampling; gains plateau after 1-2 rounds. FAIR-RAG (arXiv:2510.22344) — the valuable repair is on EVIDENCE SUFFICIENCY (iterate retrieval until sufficient, then generate ONCE), not on prose. SURE-RAG (arXiv:2605.03534) — when support is absent, ABSTAIN/LABEL, never regenerate.

**Verified facts:** (1) `d8_pending_rewrite` is a PHANTOM — `native_gate_b_inputs.py:529` hardcodes `rewrite_already_attempted=False`; `grep rewrite_already_attempted=True` → ONLY tests/, zero src/scripts; there is NO outer loop re-running the seam on hold. So it blocks release for an attempt the architecture **structurally never executes**. (2) `multi_section_generator.py:2296-2329` tighter_retry regen is intrinsic self-correction (negative EV, doubles cost on weak sections). (3) the ~2h is the 4-role seam itself (37 claims × 3 roles × effort=xhigh × 900s/call), not a regen loop — drb_76 window ~1h48m.

**Our-code edits:**
- `release_policy.py:296-297` — REMOVE the `_REASON_PENDING_REWRITE` append. `needs_rewrite` stays a pure REPORTING channel. Remove the now-vestigial `rewrite_already_attempted` param from `apply_d8_release_policy`, `run_four_role_evaluation`, `run_four_role_seam`, `FourRoleEvaluationInputs`, `native_gate_b_inputs.py:529`.
- The surviving `report_redactor.reconcile_*` becomes the I-perm-005 annotator (one pass, deterministic, zero new spend).
- `multi_section_generator.py:2296-2329` — gate tighter_retry behind `PG_SECTION_REPAIR` (default 0/OFF), byte-identical first-pass behavior.
- Speed: parallelize the seam role-calls (worker pool already exists); document `PG_FOUR_ROLE_REASONING_EFFORT`, `PG_VERIFIER_LLM_TIMEOUT_SECONDS`, `PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS` as supervised levers. Do NOT lower effort silently.
- Net code is mostly **deletion** (the strongest permanent fix). `abort_four_role_release_held` retired for the non-fabrication case.

**Risks:** removing `d8_pending_rewrite` must not let an UNSUPPORTED/FABRICATED claim ship as bare fact — mitigated: FABRICATED stays a latch; UNSUPPORTED ships only via the annotator with a prominent label. Do NOT relax 0.70 or S0 as a side effect (those become DISPLAYED scores under I-perm-001 — must be present before this lands). Turning loop #2 OFF can't silently drop a section the retry would rescue (the retry only re-prompts for tighter citations on the SAME evidence — per Huang-2024 it can't add faithful content it didn't have). Effort/timeout surfaced, never silently lowered.

### I-perm-007 (#1201) — Quantified differentiator + hard-publisher extraction
**Best practice:** GROBID (CPU Java microservice → TEI XML, 4GB RAM, no GPU) + grobid-quantities (measurement+unit triples) is the only SOTA structure extractor fitting CPU-only OVH (Nov-2025 bench arXiv:2511.16134 shows Docling 10× slower + OOMs; Nemotron-Parse/Nougat/Marker need GPU → excluded). SciEx (arXiv:2512.10004) / PARSE (arXiv:2510.08623) / SLOT (`2025.emnlp-industry.32`) — schema-CONSTRAINED decoding + unit-aware matching replaces regex. openFDA drug/label + DailyMed SPL (JSON, named sections: contraindications/dosage/warnings) BYPASS the publisher PDF entirely. Zyte browserHtml geolocation recovers BOT-BLOCKED pages, NOT true paywalls (the 904 doi.org exhaustions are predominantly true paywalls — scraping must NOT claim to defeat them; OA-first + structured APIs + honest unreachable disclosure is the legitimate path).

**HONESTY (verified):** drb_76 quantified = `no_spec_returned` (392 numbers available), drb_75 = `spec_validation_rejected` (2251 extracted, 0 survived). Both share ONE root: cruft-polluted text (DOIs/altmetric-URLs/share-buttons/reference fragments) parsed as clinical data. `evidence_extractor.py:117` scans the FULL raw markdown with 13 regexes and zero boilerplate stripping (proof: drb_76 conflicts contain `value=10.1038 unit="%"` — a DOI prefix parsed as a percent). **The `no_spec_returned` mechanism is UNDER-DETERMINED from saved logs** — the provider never persists raw response/finish_reason, so the precise cause cannot be reconstructed offline; that missing instrumentation IS part of the defect.

**Our-code edits:**
- **NEW** `src/polaris_graph/tools/numeric_sanitizer.py` — drop any numeric match whose 40-char window contains a DOI/URL/host/reference-marker/affiliation token; require a real unit OR a clinical anchor (HR/OR/RR/CI/p=/n=/mg/%/mmHg/months). Apply inside `extract_numbers_from_evidence` (`evidence_extractor.py:130`).
- `tradeoff_modeler.py:447` `_matches_datapoint` — relax to `ev_id + unit-normalized value + unit`; DROP byte-exact label/context equality (tie-breakers only); KEEP `len(cand)==1` + `_locate_unique_literal` (value verbatim in span).
- `run_honest_sweep_r3.py:5986` `_q_spec_provider` — raise max_tokens (`PG_QUANTIFIED_SPEC_MAX_TOKENS` default ~4000), one retry, brace-balanced JSON extractor, **PERSIST raw response + finish_reason + parse-outcome** (`quantified_spec_provider_debug.json`); split `no_spec_returned` into distinct `spec_provider_empty | spec_provider_truncated | writer_declined`.
- **NEW** `src/tools/grobid_client.py` (gated `PG_GROBID_URL`, OFF by default) — POST PDF to GROBID before PyMuPDF in `access_bypass._extract_pdf_text`; recovers tables/forest-plots. Remove the dead docling branch (docling not in requirements.txt). **Does NOT fix drb_75/76** (HTML-origin).
- **NEW** `src/polaris_graph/retrieval/structured_label_client.py` — openFDA/DailyMed SPL JSON client → citeable evidence rows (contraindications/dosing recovered without the paywalled PDF). Wire at `domain_backends.py:642`.
- Hard-fetch residue → OA-first (Unpaywall, wired) + structured APIs; everything still unreachable → honest per-source "unreachable/unextractable" disclosure under I-perm-001.

**Risks:** the migration FIRES MORE FROM CLEANER INPUTS, never from RELAXED verification — `_matches_datapoint` relaxation is safe because `_locate_unique_literal` still requires the value VERBATIM in-span + `len(cand)==1`. The sanitizer only REMOVES junk (can't invent a datapoint; over-filter is a fail-closed no-op). GROBID/openFDA text still flows through strict_verify + 4-role. openFDA labels can lag the current FDA label → carry the SPL effective-date into the citation.

### I-perm-008 (#1202) — Kill the cruft (WORDING + NOISE only)
**Scope guard:** I-perm-008 owns WORDING + NOISE. The redact-vs-label MECHANISM is I-perm-001; content-surfacing is I-perm-002; per-claim confidence render is I-perm-005.
**Best practice:** grounded-abstention wording (GRACE arXiv:2601.04525; "When Silence Is Golden" arXiv:2602.04755) — explicit abstention in NON-TECHNICAL language, claim-scoped, no promise of a future human fix. NN/g Error-Messages Rubric (G5 jargon-free, G6 factual, G7 actionable-not-over-promising, G8 system-accountability) + Empty-States guidance — self-contained, no machinery references.

**Verified defects:** (a) `contract_section_runner.py:993-1009` LYING stub ("did not survive strict verification … curator-actionable gap. See manifest.frame_coverage_report and human_gap_tasks.json") leaks entity_id + artifact paths AND lies (the same contraindication ships verified [3] in Safety). (b) `report_redactor.py:85-88` `_GAP_REPLACEMENT` — drb_76 has ~14 of these, 5 in one Efficacy paragraph. (c) `key_findings.py:100-104` over-claims "verbatim, span-verified"; `_SENTENCE_RE:21` DOTALL glues a `### heading` into the bullet (reproduced: bullet startswith "###"). (d) **ORDERING/FAITHFULNESS LEAK** — `build_key_findings` at `run_honest_sweep_r3.py:6313` runs BEFORE the 4-role redaction at `:7239`, so a 4-role-flipped claim is asserted at the TOP of the report (the exact hard line the reframe forbids).

**Our-code edits:**
- **NEW** `src/polaris_graph/generator/gap_disclosure_wording.py` — single source of truth + a `GAP_DISCLOSURE_MARKER` (stable machine token, HTML-comment-style, kept SEPARATE from human prose so validators key on it, not English): `claim_unsupported_phrase()`, `subtopic_no_source_phrase(subtopic_label)` (uses the human subsection title, NOT entity_id), `section_no_grounded_content_phrase()`, `slot_primary_unavailable_phrase()`, `is_gap_disclosure(text)`.
- Rewire each literal to the module: `report_redactor.py:85-88`, `contract_section_runner.py:993-1009`, `multi_section_generator.py:143-158`, `slot_fill.py:566-591` (keep `GAP_PROSE_MARKER` re-export for M-59 back-compat).
- Coalesce repetition: post-pass `_coalesce_consecutive_disclosures(report_text)` merging runs of identical disclosure sentences (mechanism-neutral).
- key_findings: rework the preamble; STRIP `#`-leading lines before `_SENTENCE_RE` (kills the glue at source); `_GAP_MARKER_RE` → import `is_gap_disclosure`.
- **ORDERING FIX (safety-load-bearing):** MOVE `build_key_findings` to AFTER `reconcile_report_against_verdicts`, OR pass `final_verdicts`+`audit_map` so each bullet stem is filtered against non-VERIFIED claims. Closes the ungrounded-as-fact leak; forward-compatible with I-perm-005.
- `honest_sweep_integration.py:413-414` — drop "curator-actionable"; aggregate per-slot WARN spam to one summary log.
- Update the pinning tests + 2 report.md fixtures **deliberately** (tests are the contract; do NOT relax asserts).

**Risks:** the Key-Findings ordering leak is itself a no-fabrication violation — the ordering fix is the one safety-load-bearing change here. Marker/prose split: if a consumer (M-59 `GAP_PROSE_MARKER`, `key_findings._GAP_MARKER_RE`, `frame_manifest`, `_GAP_DISCLOSURE_MARKER`) still keys on the OLD English literal, a gap could leak into Key Findings or flip an honest gap into a false pass (FX-07b honesty override depends on `_GAP_DISCLOSURE_MARKER`) — mitigate by centralizing detection in `is_gap_disclosure()` + updating every consumer in the SAME PR. Stay in the wording+noise lane (PR <200 LOC).

### I-perm-009 (#1203) — Proof & measurement (the pre-spend gate)
**Best practice:** deterministic record-and-replay (arXiv:2505.17716; Sakura Sky "Deterministic Replay") — the harness behaves like a pure function of the saved trace; LLM/tool calls served from a FAKE transport. FActScore (arXiv:2305.14251) decompose-then-verify + report PRECISION and RECALL separately. ALCE — cited-span attribution. RACE / DeepResearch Bench (arXiv:2506.11763) + ResearchRubrics (arXiv:2511.07685) — criteria-driven completeness with citation-SUPPORTED coverage, NO metadata/count proxies.

**In-repo substrate (verified, reuse — don't rebuild):** `scripts/dr_benchmark/offline_e2e.py` already runs the REAL 4-role seam over canned claims through an INJECTED FAKE `RoleTransport` (zero LLM, zero socket) — the exact replay primitive. `native_gate_b_inputs.build_native_gate_b_inputs` is a PURE function. `benchmark/claim_audit_scorer.py:98-110` `lane2_coverage` is the frozen completeness scorer; `outputs/dr_benchmark/rubric_v3_frozen.json` is the Q-keyed gold rubric (drb_76 → Q76). `audit_pack.json` carries 24 claims with resolved `cited_span_text`.

**Our-code edits (all at PROOF altitude — read-only on pipeline gates):**
- **NEW** `tests/dr_benchmark/replay/saved_run_loader.py` — typed loader for a beatboth8 run dir (PURE, no network).
- **NEW** `tests/dr_benchmark/replay/d8_replay_harness.py` — reconstruct the D8 decision via the REAL `build_native_gate_b_inputs` + `apply_d8_release_policy` over the saved verdicts (FAKE-RoleTransport). Must MATCH the saved manifest TODAY (baseline lock) and FLIP after each fix.
- **NEW** `tests/dr_benchmark/replay/cited_span_audit.py` — the §-1.1 content auditor: pull `cited_span_text`, check report prose against THAT span (never the verdict label).
- **NEW** `scripts/dr_benchmark/completeness_score.py` (thin) — wire the saved report + frozen Q76 rubric into `lane2_coverage`; NO counts.
- **NEW** `tests/dr_benchmark/test_beatboth8_replay_smoke.py` — the binding stress smoke; each assert tagged REPLAYABLE-OFFLINE or RE-RUN-REQUIRED; xfail-locked to the pre-fix baseline, flipping green as each fix merges (the cross-issue proof ledger). Wired to CI as a required check.

**Reframe alignment:** under always-release there is no "held"/abort, so the B2 assert is dual-vocabulary: (pre-I1) recomputed held_reasons no longer contains `d8_s0_must_cover_missing:contraindications`; (post-I1) the content ships labeled, NOT a false gap.

**Risks:** the FALSE-GREEN trap is the bug this issue exists to kill — every assert is tagged REPLAYABLE-OFFLINE vs RE-RUN-REQUIRED; RE-RUN-REQUIRED ones FAIL LOUDLY as "not provable offline" rather than passing vacuously. NEVER trust manifest status — re-derive the verdict from `cited_span_text`. Calibrate verdicts to the CROSS-REVIEWED `DRB76_FORENSIC.md` adjudications (don't encode reviewer over-strictness as ground truth). Reuse the frozen scorer (no parallel re-implementation). Dual-vocabulary asserts so I-perm-001 doesn't break the harness.

---

## 4. DEPENDENCY-ORDERED BUILD PLAN

**Foundational truth:** I-perm-001 is the keystone — it defines the master flag `PG_ALWAYS_RELEASE`, the `released_with_disclosed_gaps` status vocabulary, and the `ReleaseDisclosure`/per-claim schema (Decision B) that 004 and 005 populate/render. Nothing that consumes the reframe can land coherently before 001's contract exists.

### Wave 0 — Contract + harness skeleton (parallel, start immediately)
- **Co-design Decision B schema** (the shared per-claim dataclass + `ReleaseDisclosure`). This is a 3-way contract (001 emits, 004 populates, 005 renders); it must be agreed BEFORE any of the three merges or 004/005 deadlock. Land the dataclass extension first (can be an empty-field stub merged with 001).
- **I-perm-009 skeleton** — `saved_run_loader.py` + `d8_replay_harness.py` + `cited_span_audit.py`, **xfail-locked to the drb_76 baseline.** Built in parallel with 001; the proof ledger that flips green per fix. Finishes last (wires to CI), but starts now.

### Wave 1 — The keystone
- **I-perm-001** (#1195). Defines `PG_ALWAYS_RELEASE`, `release_disclosure.py`, the label-mode release decision, the status vocabulary, bundle-422-on-hard-block, regression-alert semantics. **Everything downstream consuming the reframe waits on this.**

### Wave 2 — Coverage correctness + recovery (after 001; co-design with each other)
- **I-perm-002** (#1196) — corpus-wide satisfaction. Fixes coverage CORRECTNESS (clears the false `missing:contraindications`). Safe regardless of mode but composes with 001's relabel.
- **I-perm-004** (#1198) — span recovery. Populates the per-claim confidence schema. **Shares the `span_resolver` argmax primitive with I-perm-002** (build the interface to take a single row OR the pool); co-design the confidence field name/scale with I-perm-005.

### Wave 3 — Render + cleanup (after 001/004; consume the schema)
- **I-perm-005** (#1199) — render the per-claim confidence + 4-role→labeler + credibility weight-not-filter. Consumes 001's flag + 004's confidence. Land 004's schema first or co-design.
- **I-perm-008** (#1202) — wording + the ORDERING fix. Coordinate the exact gap strings with I-perm-005 (edit once); 005's "no source found" supersedes the "curator-actionable" stub. **The Key-Findings ordering fix is safety-load-bearing and can land independently early** (it closes a no-fabrication leak regardless of the reframe).

### Wave 4 — Loop removal + features (after 001; mostly independent)
- **I-perm-006** (#1200) — kill pending-rewrite. DEPENDS on 001 (removing pending_rewrite alone just shifts the hold to the other two reasons unless they're also relabeled). Mostly deletion.
- **I-perm-003** (#1197) — selection. Independent build, but PROOF is on a SYNTHETIC enlarged pool (selector drops 0 on beatboth8); load-bearing only once I-perm-007 grows the pool. Ship behind flags.
- **I-perm-007** (#1201) — extraction recovery + quantified. Owns the ACTUAL ~90% bleed (fetch→row). Independent; composes with 003 (bigger pool → corpus-scaled cap matters).

### Parallelization summary
- **Can parallelize:** Wave-0 (009 harness ∥ schema co-design); Wave-2 (002 ∥ 004 with a shared primitive); Wave-4 (003 ∥ 006 ∥ 007 are largely independent of each other). I-perm-008's ordering fix can jump early.
- **Strictly sequential:** 001 → {002,004,005,006}. 004's schema → 005's render. 007 (pool) → 003 (cap bites).
- **CORE lane (serialize):** anything editing `release_policy.py` (001, 006) or `native_gate_b_inputs.py` (002) touches the same hot files — serialize those to avoid merge churn. INDEP lane (003, 007, 008-wording, 009) can run ≤3 parallel per §8.4.

---

## 5. CONSOLIDATED SERIOUS BEHAVIORAL-SMOKE SPEC (proves the 9 on saved beatboth8 BEFORE any paid run)

Runs inside the I-perm-009 harness on `outputs/audits/beatboth8/drb_76/` (and drb_75/drb_72 where present). **Every assert is tagged.** The spend-gate is GREEN-offline-subset + named-residual-re-run — **NOT "all 9 proven offline."**

> **HONESTY (binding, per §-1.1 + the task):** the following are **NOT** fully provable on beatboth8 and FAIL LOUDLY rather than pass vacuously: I-perm-003's ">46 selected from a 500-source corpus" (the selector dropped 0; the 500 pre-selection bodies are not serialized — only the 46-row post-selection pool + the 1.7MB raw log); the four-role coverage-RISES assert (needs a 4-role re-eval over recovered claims); I-perm-007's `no_spec_returned` exact-mechanism (under-determined from saved logs). "Beats ChatGPT on completeness" is a HYPOTHESIS pending a clean run, not a result.

### REPLAYABLE-OFFLINE (deterministic; these gate the spend)
- **B2 false-hold (headline)** — replay `build_native_gate_b_inputs` + `apply_d8_release_policy` over saved `four_role_claim_audit.json`. BASELINE-LOCK: recomputed `held_reasons` == saved `['d8_unsupported_residual_below_coverage','d8_s0_must_cover_missing:contraindications','d8_pending_rewrite']`. POST-I-perm-002: contraindications credited from the surviving VERIFIED Safety claims (`03-001`/`03-002`/`03-005`, evidence_id `probiotic_immunocompromised_contraindication`) → `missing:contraindications` GONE. (Do NOT assert `release_allowed==True` here — the other two reasons are I3/I6.)
- **I-perm-001 release** — with `PG_ALWAYS_RELEASE` on, replaying drb_76 yields status NOT `abort_four_role_release_held`, `release_allowed=True` (held_reasons empty for the non-fabrication case), `release_quality_score==0.40` (DISPLAYED, same value).
- **FABRICATED hard-line** — inject a synthetic FABRICATED row → `release_allowed=False`, `hard_block=True`, status maps to an abort (never `released_with_disclosed_gaps`).
- **ZERO-GROUNDING** — synthesize all-UNSUPPORTED/zero-VERIFIED + zero-usable-evidence → `abort_no_verified_sections` AND a report.md whose text contains the honest "insufficient grounded evidence" disclosure.
- **I-perm-004 idx 9 cited-span** — pull idx 9's cited span (4900-5700) from `audit_pack.json`; assert it does NOT entail "strongly linked" (it contains the hedged "not been demonstrated … direct role"); assert 14500-15300 DOES. POST-fix: re-points to the entailing span OR softens; NEVER silently KEPT on 4900-5700.
- **I-perm-004 boilerplate-no-silent-keep** — NO shipped claim's final [#ev] span is classified boilerplate (title/altmetric/nav/url/header). Regression-locks idx 9 + the "reanchored:...0-76" title binds.
- **I-perm-006 phantom hold** — after the edit, `ReleaseDecision.held_reasons` contains NO `d8_pending_rewrite`; `needs_rewrite` still populated (10 ids, reporting only).
- **I-perm-006 loop-off** — `_run_section` with `PG_SECTION_REPAIR=0` + a call-counting mock → section LLM called EXACTLY once; `=1` → can call twice.
- **I-perm-005 zero-deletion** — re-rendered report.md has ZERO occurrences of "did not survive 4-role verification and was redacted"; all 14 redacted_claim_ids have their verbatim sentence PRESENT, each carrying a confidence label.
- **I-perm-005 per-claim confidence** — `claim_confidence.json` exists; every kept claim has a `confidence_bucket ∈ {high,moderate,low,no-source-found}`; the JSON labels == the body inline labels, count-for-count.
- **I-perm-005 non-VERIFIED never high** — each of the 14 non-VERIFIED claims has bucket ∈ {low,moderate,no-source-found}, NONE high.
- **I-perm-008 cruft zero-strings** — report.md + gaps.json + frame_coverage_report contain ZERO of {curator, operator can, human_gap_tasks, frame_coverage_report, manifest., 4-role, strict verification, contract-bound} in the user-facing prose AND ZERO raw entity_id `probiotic_immunocompromised_contraindication`. *(String-presence is legitimate HERE — cruft is wording, not grounding.)*
- **I-perm-008 Key-Findings leak** — for every claim whose `final_verdict != VERIFIED`, its normalized stem does NOT appear in the Key Findings block (proves Key Findings is built post-redaction / verdict-filtered).
- **I-perm-008 no `###` in bullets** + consecutive-disclosure coalescing (Efficacy paragraph drops from 5 disclosure sentences to ≤1).
- **I-perm-007 extractor-clean** — `extract_numbers_from_evidence(evidence_pool.json)` TODAY yields ≥1 entry with a DOI-prefix value / URL label; AFTER the sanitizer, ZERO such entries; ≥1 real (value,unit,clinical-label) whose value is verbatim in its cited span.
- **I-perm-007 provider-disambiguated** — replay stubbed empty / truncated / `model_id:none` responses → THREE distinct statuses (`spec_provider_empty` / `spec_provider_truncated` / `writer_declined`), not the collapsed `no_spec_returned`.
- **§-1.1 ZERO-FABRICATION INVARIANT (must stay GREEN through ALL fixes)** — for every shipped numeric/dose/HR/CI/contraindication in report.md, the value appears VERBATIM in its cited span (`audit_pack.json`). This re-confirms `DRB76_FORENSIC.md` "zero fabrications" mechanically; if any fix introduces a fabrication, this fails loudly. *(This is a content/cited-span entailment check, not string-presence-of-a-keyword.)*
- **OFF = byte-identical** — with `PG_ALWAYS_RELEASE` unset, drb_76 replay reproduces `abort_four_role_release_held` / `release_allowed=False` / the current redacted report.md byte-for-byte.

### RE-RUN-REQUIRED (flagged, fail loudly — NOT silently green)
- **I-perm-003 ">46 selected"** — provable only on an I-perm-003 pre-selection corpus fixture OR a canary re-run. Offline we assert ONLY the RECORDED funnel (`evidence_selected=46`, and the upstream 510-fetched / 57-ish-row collapse owned by I-perm-007).
- **I-perm-003 LAYER-A/B/C** — corpus-scaled budget, cross-encoder best-not-first-N, LITM reorder — proven on a SYNTHETIC enlarged ~500-row pool (replicated beatboth8 rows), since the real selector drops 0.
- **four-role coverage RISES above 0.40** — needs a 4-role re-eval over recovered claims; replayable only if I-perm-004 saves recovered-claim fixtures, else canary-gated.
- **I-perm-002 / I-perm-004 ONE live-judge call** — `_EntailmentJudge` end-to-end on the real drb_76 phrasing (one non-stub call to prove the stub matches live behavior).
- **I-perm-007 structured-clinical** — openFDA/DailyMed recovery proven against a SAVED JSON fixture (no live spend); live recovery is canary-gated.

---

## 6. OPEN DESIGN QUESTIONS — pressure-test with Codex (be honest about uncertainty)

These are genuine tensions, not rubber-stamps. The reframe is operator-directed and the right strategic call, but it carries real clinical-safety risk that I cannot fully resolve from the saved data alone.

1. **Always-release vs the clinical hard line — is caveat PROMINENCE empirically sufficient, or merely assumed?** A polished, confident-looking always-release report that is *silent on contraindications* (with a caveat at the top) may induce MORE false confidence in a clinician than a blunt abort. The SOTA (arXiv:2601.12471) says soft-abstention + a prominent caveat satisfies the clinical floor — but "prominent" is a UX claim we have not tested with a real reader. **Question for Codex:** do we need a stronger structural guarantee than top-of-report placement (e.g. an interstitial the reader must acknowledge, or refusing to release a clinical report whose S0 *safety* categories are all disclosed-gaps)? Is there a class of report (all safety categories missing) where abort is still correct?

2. **Is `has_any_verified_claim` (1-of-N) the right release floor for a clinical safety section?** The proposed hard floor is "release iff NOT fabricated AND ≥1 verified claim." On drb_76 that's 23 verified — fine. But a report with 1 verified claim out of 37, where the 36 unverified ones are all safety-critical, would release. **Question:** should the floor be per-SECTION (a Safety section with zero verified claims is a hard-block even if other sections are rich), not per-REPORT? This interacts with I-perm-001's `hard_block` definition and is the single highest-stakes parameter in the whole reframe.

3. **Credibility-as-weight + `independent_origin_count` — can echoing low-credibility sources fake "moderate (3 sources)"?** RA-RAG downweights but RETAINS low-reliability sources. If 3 low-credibility sources echo the same unverified claim, does `independent_origin_count=3` let it display "moderate · 3 sources" and read as corroborated? **Question:** must "independent origin" be gated on credibility (3 *credible* independent origins), and must the chip never upgrade a non-VERIFIED claim above "low" regardless of origin count? (The current Decision-B rule already blocks credibility from promoting an unverified claim to "high" — but "moderate" with a 3-source count may still over-signal.)

4. **Pooled cross-document re-anchor (I-perm-002 reusing the I-perm-004 argmax over the whole pool) is the dangerous widening.** Re-pointing a claim to a coincidental match in an UNRELATED paper is a fabrication risk. The blueprint keeps I-perm-004 row-scoped and gates cross-source behind I-perm-002's title-anchor guard — **Question:** is the title-anchor guard sufficient, or do we need a same-population/same-intervention check before crediting cross-document satisfaction of a *safety* category?

5. **`released_with_disclosed_gaps` as a "success-adjacent" status — does it weaken the regression signal?** Once a True→False `release_allowed` flip is no longer a CRITICAL alert (I-perm-001 edit to `regression_alerts.py`), the new signal is a `release_quality_score` drop. **Question:** what score-drop magnitude trips the alert, and does removing the binary flip lose our ability to detect a *new* systematic withholding bug introduced by a future change?

6. **I-perm-003's honest no-op.** On beatboth8 the selector drops 0, so the whole issue is preventative. **Question for Codex:** is it acceptable to merge I-perm-003 with only synthetic-pool proof, or should it be sequenced strictly AFTER I-perm-007 grows a real pool so the corpus-scaled cap can be proven on real data? (My recommendation: merge behind flags with synthetic proof, but do not claim the 90% fix until 007 lands.)

```


## DOCUMENT 2 (FULL TEXT) — `docs/permanent_fix_9_issues.md` (the operator charter)

```markdown
# POLARIS Permanent Architecture Fix — THE 9 ISSUES (pinned, hard)

**Status:** ACTIVE program (operator-directed 2026-06-10). No band-aids. Each issue: research frontier best-practice → line-by-line study of OUR code → design permanent migration → build → SERIOUS stress smoke → Codex review with evidence → iterate-or-approve. After ALL 9 Codex-approved → serious preflight → present summary → operator go for the full beat-both run.

**Governing principle (the root reframe):** the pipeline today is built to **WITHHOLD when imperfect**. It must become: **ALWAYS RELEASE, with honest per-claim confidence + provenance, and let the user judge.** The ONLY hard line: never assert an *ungrounded* claim as fact — an unsupported claim ships as a transparent "no source found," never silently, and safety caveats are shown PROMINENTLY. This reframe is also the differentiator vs ChatGPT/Gemini (radical transparency, not a confident oracle).

**Process per issue (binding):**
1. Research how the latest frontier DR/RAG/faithfulness systems + best-practice literature handle it (WebSearch the current SOTA; cite sources).
2. Investigate OUR related code line-by-line (file:line); list every call site + consumer.
3. Design the permanent migration (best-practice → our code), stable + quality, not a patch.
4. Build it; wire to the MAIN pipeline with full function.
5. SERIOUS stress smoke (real adversarial test on real data — NOT a trivial pass-through).
6. Codex reviews everything with solid evidence → iterate or APPROVE (Codex is the only gate).

---

## I1 — Release-model reframe + the WHOLE gate stack
**Problem:** ~7 stacked gates can withhold/abort/thin a report: scope-reject, corpus-inadequate, corpus-approval-denied, per-section "≥40% verified or drop," four-role "≥70% or hold," S0 must-cover hold, "zero-verified → abort run." Any one kills or thins output even after deep research.
**Our code:** `src/polaris_graph/nodes/` (scope/adequacy/approval gates), `clinical_generator/strict_verify.py` (per-section floor), `roles/release_policy.py` + `roles/native_gate_b_inputs.py` + the four-role D8 seam (coverage 0.70, S0 must-cover), `generator/report_redactor.py`, manifest status `abort_*` (architecture.md §9.3).
**Research:** how do frontier DR systems (OpenAI/Google DR, Elicit, Consensus, Ai2 OLMoE/paper-QA, FacTool/RARR/SAFE) handle low-confidence — withhold vs label? Calibrated abstention vs transparent confidence.
**Permanent fix:** convert every gate from BLOCK → LABEL. No "held." Each claim/section carries a confidence + provenance; thresholds become DISPLAYED quality scores, not trap-doors. Keep abort ONLY for true zero-grounding (and even then render an honest "insufficient grounded evidence" report).

## I2 — Corpus-wide satisfaction (kill tunnel vision)
**Problem:** a requirement is checked against ONE bound source; if that exact source doesn't extract, it holds — even though the same fact sits in another URL we already fetched for a different query (the drb_76 contraindication was IN the corpus under a different source).
**Our code:** `roles/native_gate_b_inputs.py` (`_entity_canonical_match`, must-cover binding), `retrieval/frame_fetcher.py` (url_pattern bind), `retrieval/required_entity_retrieval.py`.
**Research:** evidence aggregation / multi-document grounding; how SOTA verifies a claim against a CORPUS not a single doc (cross-document NLI, claim→pooled-evidence retrieval).
**Permanent fix:** before declaring any requirement unmet, search the ENTIRE fetched evidence pool across all queries for satisfying content; bind to whatever genuinely supports it.

## I3 — Stop discarding the research (selection)
**Problem:** selector keeps ~46 of ~500 fetched sources (~90% thrown away before the writer sees them). The deep STORM research is wasted.
**Our code:** `generator/multi_section_generator.py` (evidence_selection), the rerank/dedup path, `evidence_selected` cap (#1078).
**Research:** retrieval→generation context scaling, long-context evidence packing, best-of-N evidence selection, rerankers (cross-encoder/ColBERT) at scale.
**Permanent fix:** scale selection with corpus size; feed BEST-ranked evidence (not first-N); raise/remove the fixed cap; quality rerank.

## I4 — Verification recovery + label-not-delete
**Problem:** the verifier wrongly drops real, checkable claims — mis-pointed citations (claim bound to abstract-intro / author-header / badge-URL), clinical qualifier-drop (#1176), general↔specific widening mis-judged (#1180), the span-window logic shaky BOTH ways (passes imprecise spans / rejects valid ones, gap-#18).
**Our code:** `generator/provenance_generator.py` (re-anchor, span-binding, `allow_local_window_fallback`), `clinical_generator/strict_verify.py`, `llm/entailment_judge.py`, span extraction (skip boilerplate).
**Research:** claim-grounding precision, attribution (RARR/ALCE/AttributedQA), span selection, NLI calibration; specific-vs-general entailment.
**Permanent fix:** re-anchor each citation to the genuinely-entailing span; skip boilerplate spans; when verification is imperfect, LABEL the claim (confidence + source), don't delete it.

## I5 — Per-claim confidence & provenance render + 4-role becomes a LABELER + credibility = weight not filter
**Problem:** the reframe forces a build: every claim must show answer + source(s) + confidence; the 4-role verifier must change job from gatekeeper to labeler; source credibility must WEIGHT + DISCLOSE, not silently FILTER (journal-only tunnel vision #1146/#1147).
**Our code:** `report_redactor.py`, `multi_section_generator.py` render, `key_findings.py`, the 4-role seam output, credibility modules (I-cred-*), web Proof-Replay UI.
**Research:** evidence-grounded UX (per-claim citations + confidence), calibrated confidence display, source-credibility weighting (not exclusion).
**Permanent fix:** per-claim confidence+provenance render in report + UI; 4-role emits per-claim labels; credibility weights + discloses.

## I6 — Kill the pending-rewrite loop + speed
**Problem:** when held, the pipeline re-generates to try to pass (d8_pending_rewrite) — the slow loop that made drb_90 take ~2h. The reframe makes it largely redundant.
**Our code:** the four-role rewrite path, `contract_section_runner.py`, the regenerate-on-hold logic.
**Research:** single-pass vs iterative-repair generation; where repair adds value vs churn.
**Permanent fix:** remove/simplify the rewrite-to-pass loop under always-release; keep at most one bounded repair; faster runs.

## I7 — Features that aren't delivering
**Problem:** (a) the quantified trade-off differentiator frequently no-ops (spec rejected / nothing returned, #1184); (b) hard publisher PDFs (NEJM/Lancet/AJCN viewers) fail extraction even with paid Zyte (#954) → lost authoritative sources.
**Our code:** `generator/quantified_analysis.py` + `run_honest_sweep_r3.py` `_q_spec_provider`; `tools/access_bypass.py` + PDF/table extraction (Docling/Surya/structured).
**Research:** structured quantitative extraction from papers; robust scholarly-PDF parsing (GROBID/Docling/Nougat/Surya), table extraction.
**Permanent fix:** harden the quantified-spec so it fires; add structured PDF/table extraction for hard publisher PDFs.

## I8 — Kill the cruft
**Problem:** "curator/operator will fix" wording (no curator, #1193), the lying "did not survive verification" stub, the Key-Findings over-claim ("verbatim span-verified" while carrying headers/stubs), noisy logs.
**Our code:** `multi_section_generator.py`, `contract_section_runner.py`, `report_redactor.py`, `key_findings.py`, `slot_fill.py`, `honest_sweep_integration.py` (human_gap_tasks), warning sites.
**Permanent fix:** factual self-contained gap wording; relabel internal artifacts (no human refs); fix the carry-up; quiet warnings.

## I9 — Proof & measurement tooling
**Problem:** we keep discovering bugs only on a paid run; no behavioral proof before spend; no repeatable completeness score; the audit-by-status habit hid the false hold.
**Our code:** new `tests/` behavioral replay harness on saved beatboth8 evidence; reuse `claim_audit_scorer` for completeness; §-1.1 content-audit discipline.
**Research:** offline replay/eval harnesses for RAG/DR; faithfulness + completeness metrics (RAGAS, FActScore, ALCE, RACE) that are honest (no metadata proxies).
**Permanent fix:** a serious behavioral stress smoke on real saved data (proves each fix before any run); a repeatable completeness scorer; audit content claim-by-claim, never status.

---

## The target (outcome, not a build item)
**Completeness vs ChatGPT** — provable only AFTER I1–I9 + one clean run. We already beat Gemini and never fabricate; the game is becoming complete enough to beat ChatGPT while staying faithful.

## Watches (monitor, not in the 9)
- Provider flakiness (mitigated by #1191 retries; permanent = robust multi-provider).
- Reasoning-first structured-output timeouts (retry-handled).

```


## GROUNDING CODE (current tree, for verifying the design against reality)


> NOTE for Codex: the blueprint cites `generator/report_redactor.py`, but the file actually lives at `src/polaris_graph/roles/report_redactor.py` (path discrepancy — flag if you think it matters; the line content matches the blueprint's `_GAP_REPLACEMENT` claim at :85-88).


### `src/polaris_graph/roles/release_policy.py` lines 180-300 (the D8 release decision — FABRICATED latch :200-205, coverage floor :241-253, S0 must-cover :255-273, pending-rewrite :296-297)

```python
  180	    *,
  181	    required_s0_categories: list[str],
  182	    coverage_ledger: CoverageLedger,
  183	    coverage_threshold: float,
  184	    rewrite_already_attempted: bool,
  185	    prior_fabricated_latched: bool = False,
  186	) -> ReleaseDecision:
  187	    """Apply the D8 production release policy to one pass of claim rows.
  188	
  189	    Every gate is evaluated (no short-circuit) so `gaps` / `held_reasons` are complete.
  190	    `release_allowed` is True iff `held_reasons` is empty; `gaps` and `needs_rewrite` are
  191	    separate reporting channels and do NOT by themselves block release.
  192	    """
  193	    held_reasons: list[str] = []
  194	    gaps: list[Gap] = []
  195	    needs_rewrite: list[str] = []
  196	
  197	    material_rows = [row for row in d8_rows if row.is_material]
  198	
  199	    # (a) FABRICATED occurrence LATCH — one-way; rewrite does NOT clear it.
  200	    fabricated_this_pass = any(
  201	        row.verdict == _VERDICT_FABRICATED for row in material_rows
  202	    )
  203	    fabricated_occurrence_latched = prior_fabricated_latched or fabricated_this_pass
  204	    if fabricated_occurrence_latched:
  205	        held_reasons.append(_REASON_FABRICATED_OCCURRENCE)
  206	
  207	    # (b) UNSUPPORTED residual + (b2) genuine UNREACHABLE residual — SAME path.
  208	    # First pass: route material UNSUPPORTED/UNREACHABLE rows to a rewrite/refuse-in-place
  209	    # attempt. Post-attempt: emit a VISIBLE residual gap for any that remain (never a silent
  210	    # drop). The coverage HOLD below is computed from the ledger alone — NOT from whether a
  211	    # residual row is still present — so dropping/refusing the row cannot dodge the gate
  212	    # (Codex diff P1-b).
  213	    for row in material_rows:
  214	        if row.verdict not in (_VERDICT_UNSUPPORTED, _VERDICT_UNREACHABLE):
  215	            continue
  216	        if not rewrite_already_attempted:
  217	            needs_rewrite.append(row.claim_id)
  218	        else:
  219	            if row.verdict == _VERDICT_UNREACHABLE:
  220	                note = (
  221	                    "genuine fetch-miss (UNREACHABLE) remained after one rewrite attempt; "
  222	                    "visible residual gap, not silently passed"
  223	                )
  224	            else:
  225	                note = "unsupported claim remained after one rewrite/refuse-in-place attempt"
  226	            gaps.append(
  227	                Gap(
  228	                    ref=row.claim_id,
  229	                    kind=_GAP_RESIDUAL_UNSUPPORTED,
  230	                    severity=row.severity,
  231	                    note=note,
  232	                )
  233	            )
  234	    # Coverage floor — UNCONDITIONAL on the fixed-denominator ledger. A run whose required-
  235	    # element coverage is below threshold is never releasable, whether the shortfall is caused
  236	    # by an UNSUPPORTED/UNREACHABLE row that is still present, one that was dropped/refused, or
  237	    # a required element that never had a claim at all. This closes the "drop the row to dodge
  238	    # the gate" hole (Codex diff P1-b): the denominator is the required set, so removing a claim
  239	    # lowers the fraction. On the first pass a low fraction is additionally caught by the
  240	    # pending-rewrite hold below; once the rewrite is exhausted, this is the binding gate.
  241	    if coverage_ledger.fraction() < coverage_threshold:
  242	        held_reasons.append(_REASON_UNSUPPORTED_RESIDUAL_BELOW_COVERAGE)
  243	        gaps.append(
  244	            Gap(
  245	                ref="__coverage__",
  246	                kind=_GAP_COVERAGE_SHORTFALL,
  247	                severity="S0",
  248	                note=(
  249	                    f"required-element coverage {coverage_ledger.fraction():.3f} is below the "
  250	                    f"{coverage_threshold:.3f} threshold (fixed required-set denominator)"
  251	                ),
  252	            )
  253	        )
  254	
  255	    # (c) S0 must-cover gate — category covered iff a VERIFIED claim carries it.
  256	    verified_categories: set[str] = set()
  257	    for row in d8_rows:
  258	        if row.verdict == _VERDICT_VERIFIED:
  259	            verified_categories.update(row.s0_categories)
  260	    for category in required_s0_categories:
  261	        if category not in verified_categories:
  262	            held_reasons.append(f"{_REASON_S0_MUST_COVER_MISSING_PREFIX}{category}")
  263	            gaps.append(
  264	                Gap(
  265	                    ref=category,
  266	                    kind=_GAP_UNCOVERED_S0,
  267	                    severity="S0",
  268	                    note=(
  269	                        "required S0 must-cover category has no VERIFIED claim "
  270	                        "(PARTIAL/citation-only does not satisfy it)"
  271	                    ),
  272	                )
  273	            )
  274	
  275	    # (d) PARTIAL S0/S1 — one rewrite, then visible advisory gap.
  276	    for row in d8_rows:
  277	        if row.verdict != _VERDICT_PARTIAL:
  278	            continue
  279	        if row.severity not in _PARTIAL_REWRITE_SEVERITIES:
  280	            continue
  281	        if not rewrite_already_attempted:
  282	            needs_rewrite.append(row.claim_id)
  283	        else:
  284	            gaps.append(
  285	                Gap(
  286	                    ref=row.claim_id,
  287	                    kind=_GAP_PARTIAL_ADVISORY,
  288	                    severity=row.severity,
  289	                    note="PARTIAL claim ships as a visible advisory after one rewrite attempt",
  290	                )
  291	            )
  292	
  293	    # A pass with pending rewrites is NOT releasable — the required rewrite/refuse-in-place
  294	    # attempt has not happened yet (Codex diff P1-a: release_allowed previously ignored
  295	    # needs_rewrite, letting a first-pass run release before the attempt).
  296	    if needs_rewrite:
  297	        held_reasons.append(_REASON_PENDING_REWRITE)
  298	
  299	    release_allowed = not held_reasons
  300	    return ReleaseDecision(
```


### `src/polaris_graph/roles/native_gate_b_inputs.py` lines 300-360 (the tunnel-vision seam: `_content_requirements_satisfied` exact-string match :312-328, `_claim_covers_entity` :331-352)

```python
  300	    for entity_key, record_key in _CANONICAL_MATCH_PAIRS:
  301	        entity_value = entity.get(entity_key)
  302	        if entity_value in (None, ""):
  303	            continue
  304	        record_value = record.get(record_key)
  305	        if record_value in (None, ""):
  306	            continue
  307	        if str(entity_value).strip() == str(record_value).strip():
  308	            return True
  309	    return False
  310	
  311	
  312	def _content_requirements_satisfied(claim_text: str, entity: dict) -> bool:
  313	    """All `coverage_content_requirements` present in the claim (case-insensitive, exact).
  314	
  315	    FAIL CLOSED (Codex P1): if the requirements list is empty — or somehow all-blank — return
  316	    False rather than vacuously True. A bare canonical-evidence citation must NEVER earn S0
  317	    credit without a real deterministic content match. (Validation in `validate_entity_severity`
  318	    already blocks empty/blank S0 requirements at load; this is the matcher-side backstop.)
  319	    """
  320	    lowered = claim_text.lower()
  321	    requirements = [
  322	        token
  323	        for token in entity.get(_KEY_ENTITY_CONTENT_REQS) or []
  324	        if isinstance(token, str) and token.strip()
  325	    ]
  326	    if not requirements:
  327	        return False
  328	    return all(token.lower() in lowered for token in requirements)
  329	
  330	
  331	def _claim_covers_entity(
  332	    claim_evidence_records: list[Mapping[str, Any]],
  333	    claim_text: str,
  334	    entity: dict,
  335	    *,
  336	    is_s0: bool,
  337	) -> bool:
  338	    """Coverage test (§7.D, Codex-tightened + P2 #4).
  339	
  340	    ENTITY coverage: True iff the claim cites evidence whose CANONICAL identifier EXACTLY
  341	    matches the entity's. anchor-string-in-sentence alone does NOT grant coverage.
  342	
  343	    S0 SAFETY-CATEGORY coverage (stricter): an S0 entity is covered ONLY when BOTH (a) the
  344	    canonical evidence match holds AND (b) the claim text deterministically satisfies the
  345	    entity's `coverage_content_requirements`. A broad source citation without the content
  346	    match does NOT satisfy an S0 safety category.
  347	    """
  348	    if not any(_entity_canonical_match(entity, rec) for rec in claim_evidence_records):
  349	        return False
  350	    if is_s0 and not _content_requirements_satisfied(claim_text, entity):
  351	        return False
  352	    return True
  353	
  354	
  355	# FX-03 / I-ready-017 (#1107): the 4-role seam (Sentinel decomposition + Judge) joins each
  356	# EvidenceDocument.text as the SPAN the claim is checked against. Pre-FX-03 the WHOLE record text
  357	# was passed, so a claim could be graded VERIFIED on support living ANYWHERE in the document, not
  358	# in the cited [start:end] window (BUG-02: confirmed out-of-span false-accept, claim 06-004).
  359	_GATE_B_CITED_SPAN_ENV = "PG_GATE_B_CITED_SPAN"
  360	_GATE_B_SPAN_WINDOW_ENV = "PG_GATE_B_SPAN_WINDOW_BYTES"
```


### `src/polaris_graph/roles/native_gate_b_inputs.py` lines 470-540 (claim build + coverage attribution + `rewrite_already_attempted=False` hardcode :529)

```python
  470	            digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:_CLAIM_HASH_HEX_LEN]
  471	            claim_id = f"{section_index:02d}-{sentence_index:03d}-{digest}"
  472	
  473	            evidence_ids = [token.evidence_id for token in verification.tokens]
  474	            # FX-03 (#1107): pass the TOKENS (carrying start/end), not just the ids — _resolve_evidence
  475	            # slices each EvidenceDocument.text to the cited bounded window so the seam judges the
  476	            # claim against the cited SPAN, not the whole source doc (BUG-02 out-of-span false-accept).
  477	            # evidence_ids is retained above for the audit_map trail.
  478	            documents, records = _resolve_evidence(verification.tokens, evidence_lookup)
  479	
  480	            covered_element_ids: list[str] = []
  481	            covered_s0_categories: list[str] = []
  482	            best_rank = _SEVERITY_RANK[_DEFAULT_OBSERVE_ONLY_SEVERITY]
  483	            for entity, severity, s0_category in validated:
  484	                is_s0 = severity == _SEVERITY_S0
  485	                if not _claim_covers_entity(records, sentence, entity, is_s0=is_s0):
  486	                    continue
  487	                covered_element_ids.append(entity[_KEY_ENTITY_ID])
  488	                best_rank = max(best_rank, _SEVERITY_RANK[severity])
  489	                if is_s0 and s0_category is not None:
  490	                    covered_s0_categories.append(s0_category)
  491	
  492	            claim_severity = next(
  493	                sev for sev, rank in _SEVERITY_RANK.items() if rank == best_rank
  494	            )
  495	            s0_categories = sorted(set(covered_s0_categories))
  496	
  497	            claims.append(
  498	                FourRoleClaim(
  499	                    claim_id=claim_id,
  500	                    claim_text=sentence,
  501	                    evidence_documents=documents,
  502	                    severity=claim_severity,
  503	                    s0_categories=s0_categories,
  504	                    covered_element_ids=covered_element_ids,
  505	                )
  506	            )
  507	            audit_map[claim_id] = {
  508	                "section_index": section_index,
  509	                "section_title": getattr(section, "title", ""),
  510	                "sentence": sentence,
  511	                "evidence_ids": evidence_ids,
  512	                "covered_element_ids": covered_element_ids,
  513	                "severity": claim_severity,
  514	                "s0_categories": s0_categories,
  515	            }
  516	
  517	    if not claims:
  518	        raise ValueError(
  519	            "build_native_gate_b_inputs: zero kept (verified) sentences; a 4-role "
  520	            "evaluation over no claims cannot produce a release decision (fail-closed, "
  521	            "no vacuous input)."
  522	        )
  523	
  524	    inputs = FourRoleEvaluationInputs(
  525	        claims=claims,
  526	        coverage_ledger=CoverageLedger(required_element_ids=required_element_ids),
  527	        required_s0_categories=sorted(required_s0_categories_set),
  528	        model_slugs=model_slugs,
  529	        rewrite_already_attempted=False,
  530	    )
  531	    return NativeGateBBundle(inputs=inputs, audit_map=audit_map)
```


### `src/polaris_graph/roles/report_redactor.py` lines 60-120 (the redact-to-gap-stub mechanism the reframe turns into a labeler: `_NON_VERIFIED_VERDICTS` :77-79, `_GAP_REPLACEMENT` :85-88)

```python
   60	claim is recorded in ``redacted`` exactly ONCE regardless of how many physical spans were removed.
   61	
   62	Pure function (string ops only; no network, no I/O). The CALLER reads/writes report.md.
   63	"""
   64	
   65	from __future__ import annotations
   66	
   67	import re
   68	from dataclasses import dataclass, field
   69	
   70	# REDACTION IS SEVERITY-INDEPENDENT (I-faith-003 #1174). Any claim the 4-role seam did NOT
   71	# mark VERIFIED — PARTIAL/UNSUPPORTED/FABRICATED/UNREACHABLE — must not ship as asserted prose,
   72	# regardless of severity. Severity ("S0".."S3") governs the RELEASE LATCH in release_policy.py
   73	# (a non-required-entity S3 claim does not BLOCK release), NEVER this redaction path: previously
   74	# the S3 "observe-only" scope guard wrongly let 26 UNSUPPORTED claims (incl. clinical-safety
   75	# guidance) ship across the 5 beat-both questions (BB5-F01). VERIFIED survives; every other
   76	# verdict is a leak if it ships as prose.
   77	_NON_VERIFIED_VERDICTS = frozenset(
   78	    {"UNSUPPORTED", "FABRICATED", "UNREACHABLE", "PARTIAL"}
   79	)
   80	_VERDICT_VERIFIED = "VERIFIED"
   81	
   82	# The visible gap sentence a redacted claim is replaced with. Mirrors the existing gap
   83	# language already used by contract_section_runner ("did not survive strict
   84	# verification; curator-actionable gap.") so a redacted body reads consistently.
   85	_GAP_REPLACEMENT = (
   86	    "A claim previously stated here did not survive 4-role verification and was "
   87	    "redacted; this is a curator-actionable gap."
   88	)
   89	
   90	# gaps.json kind for a post-gate redaction (mirrors release_policy._GAP_RESIDUAL_UNSUPPORTED
   91	# vocabulary but is distinct so the audit trail shows the redaction happened in report.md).
   92	GAP_KIND_REDACTED_UNSUPPORTED = "redacted_unsupported"
   93	
   94	# POLARIS provenance token: [#ev:evidence_id:start-end].
   95	_PROVENANCE_TOKEN_RE = re.compile(r"\[#ev:[^\]]+\]")
   96	# Rendered numbered citation marker: [1], [12]. The final report converts each provenance
   97	# token into one of these, so the stem matcher must ignore them on BOTH sides.
   98	_NUMBERED_MARKER_RE = re.compile(r"\[\d+\]")
   99	_WHITESPACE_RE = re.compile(r"\s+")
  100	
  101	
  102	class ReportRedactionError(RuntimeError):
  103	    """Raised when a material non-VERIFIED claim is present-but-unlocatable for a discrete
  104	    rendered-sentence replacement. The caller MUST fail closed (do NOT ship the report).
  105	    """
  106	
  107	
  108	@dataclass
  109	class RedactedClaim:
  110	    """One claim whose verbatim sentence was removed from report.md (-> gaps.json)."""
  111	
  112	    claim_id: str
  113	    severity: str
  114	    verdict: str
  115	    claim_text: str  # the verbatim sentence (with its original provenance token)
  116	
  117	
  118	@dataclass
  119	class RedactionResult:
  120	    """Outcome of reconciling report.md against the 4-role verdicts."""
```


---

**END OF REVIEW INPUT. Emit the YAML verdict + tension_rulings + required_design_changes now. Front-load all findings (iter 1 of 5).**
