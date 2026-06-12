# Codex BRIEF gate — I-perm-024 (#1216): beat-both scorer metric extension

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.

## ITER-2 CHANGES (addressing every iter-1 finding; code is already built + green)

- **iter-1 P1 (dedup input not in ClaimRow) — RESOLVED exactly as you recommended.**
  The metrics do NOT take bare `list[ClaimRow]`. The dedup-bearing entry point takes
  a typed AUDITED carrier `ScoredClaim(text: str, row: ClaimRow)` — the claim's prose
  text paired with its already-reconciled verdict. `run_scorecard` builds it by
  `zip(atoms, rows)` (score_atoms emits exactly one row per atom in order, so the
  pairing is faithful). The `text` is used ONLY by the Claimify dedup; every metric
  VALUE is still derived from the `ClaimRow` verdict + the rubric, never from text.
  No raw report text is ever passed. This is your "typed audited atom-row object that
  includes text plus verdict."
- **iter-1 P2 (mixed-verdict dedup could hide a bad verdict) — FIXED.** Dedup now
  collapses ONLY repeated VERIFIED claims; EVERY non-VERIFIED material claim is kept
  uncollapsed. Within a text cluster: keep the first VERIFIED row + all non-VERIFIED
  rows. A VERIFIED restatement can never hide an UNSUPPORTED/FABRICATED/PARTIAL/
  UNREACHABLE near-duplicate. Test `test_mixed_verdict_cluster_keeps_the_bad_verdict`
  proves precision = 1/2 (not 1/1) for a {VERIFIED, UNSUPPORTED}-same-fact cluster.
- **iter-1 P2 (diversity never a decision input) — GUARDED.** `diversity_score` is
  diagnostic-only with a loud note. Test `test_no_decision_path_consumes_diversity`
  asserts the string "diversity" appears in NEITHER `benchmark_scorecard.py` NOR
  `claim_audit_scorer.py` (the PASS/aggregate logic) — structurally no comparator can
  consume it.
- **iter-1 P2 (pin to JSON file hash) — DONE.** `safety_floor_elements_v3.json` pins
  `rubric_sha256 = 2a39d9ddd31386acf5c7c58f1f3e5befbfa5f5e4ed07baabef115d5d701ff140`
  (the actual frozen JSON file content hash), NOT the file's internal source-rubric
  markdown hash.
- **iter-1 P2 (force-on in broad run + archive the block) — DONE.** Slate entry
  `PG_BENCH_EXTENDED_METRICS: "1"` added to `_FULL_CAPABILITY_BENCHMARK_SLATE`; the
  scorecard attaches `card["extended"]` so the broad run archives it.
- **Build status:** 20 new tests pass; 36 existing scorer tests pass (no regression);
  flag-OFF `build_scorecard` byte-identical (`"extended"` key absent); integration
  smoke over the 10 real stored competitor reports produces well-formed extended
  blocks (rubric-based metrics report `pending` until the paid audit supplies rubric
  coverage — graceful, not a false 0).

Verdict request: APPROVE the (now-consistent) acceptance criteria; the diff gate
will verify the code line-by-line next.

---

(original iter-1 brief follows, retained for context)

HARD ITERATION CAP (iter-1 header, superseded above): 5 per document.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## What you are gating
This is a BRIEF gate (acceptance-criteria correctness), not a diff gate. Approve iff the
design below is sound, faithfulness-safe, and §-1.1-compliant. The diff gate comes after.

## Issue (#1216, I-perm-024)
Extend the claim-audit scorer (NOT counts/patterns) to report 5 claim-by-claim metrics:
`faithfulness_precision`, `required_entity_recall`, `safety_floor_recall`,
`citation_support_rate`, `diversity_score`; plus Claimify-style claim dedup so repetitive
obvious claims can't inflate. Run identically across POLARIS/ChatGPT/Gemini on the FROZEN
Q76 rubric. DoD: (1) default-OFF flag, byte-identical when off; (2) faithfulness gates
(strict_verify/4-role/D8) NEVER relaxed; (3) unit tests; (4) Codex diff-gate APPROVE;
(5) paid §-1.1 smoke (folded into the operator-gated broad beat-both run — see §6);
(6) wired into the Gate-B slate.

## §-1.1 (clinical, BANNED list) — the crux you must verify
BANNED as quality signals: word/citation/unique-source COUNTS; pattern presence
("does the report mention 'tirzepatide'?"); sample-based audits; string-presence PASS/FAIL;
metadata comparison. These are "lethal in clinical."

## Design (the corrected, honest one)

### Structural §-1.1 guarantee (the load-bearing claim)
All 5 metrics are computed ONLY from inputs that are ALREADY audited claim-by-claim:
- `list[ClaimRow]` (one reconciled verdict per atomic claim, each VERIFIED/PARTIAL/
  UNSUPPORTED/FABRICATED/UNREACHABLE against the FETCHED cited span — produced by the
  existing Claude+Codex dual §-1.1 audit, `fact_scorer.score_atoms`).
- `list[RubricElement]` (the frozen Q76 rubric elements; `.covered` + `.citation_supported`
  set by the SAME audit).
The new `extended_metrics` functions take ONLY these two typed inputs. They NEVER receive
raw report text. Therefore they CANNOT do string-presence / pattern-presence matching — it
is structurally impossible, enforced by a test asserting the module never imports/opens a
report. This is what keeps `required_entity_recall` / `diversity_score` out of the BANNED
"pattern-presence / unique-source-count" territory: every metric is a roll-up over the
per-claim audit LEDGER, not over raw text.

### The frozen rubric (NO new invented entity list)
CORRECTION to an earlier draft plan: I will NOT create a new `required_entities_q76.json`.
The pre-registered authority already exists: `outputs/dr_benchmark/rubric_v3_frozen.json`
(sha256 `2a39d9ddd31386acf5c7c58f1f3e5befbfa5f5e4ed07baabef115d5d701ff140`), with Q76-E1..E8
(and Q75/Q78/Q72/Q90). Inventing a parallel entity list would be fabrication + drift risk.
`required_entity_recall` = covered-AND-citation-supported frozen rubric elements / total.
This intentionally reuses the existing `claim_audit_scorer.lane2_coverage` semantics.

### safety_floor_recall (pre-registration, traceable, not invented)
A small companion `outputs/dr_benchmark/safety_floor_elements_v3.json` lists, per question,
which frozen rubric `element_id`s are patient-safety / harm / contraindication / honest-
framing-floor elements, EACH with a one-line justification QUOTING the rubric's own
`requirement_text`, and pinned to the rubric sha256. This is a transparent TAGGING of the
existing frozen rubric (the rubric already encodes safety, e.g. Q78 title says "El6 =
patient-safety"; Q76-E6 = genotoxic colibactin/BFT harms; Q76-E7 = "Penalize 'clinically
proven' overstatement"). `safety_floor_recall` = covered-AND-citation-supported safety
elements / total safety elements. NOT new claims; NOT a count proxy — it's recall over a
pre-registered safety subset of the audited rubric.

### The 5 metrics (all from audited inputs)
1. `faithfulness_precision` = VERIFIED / material(S0-S2) claims. (1 − unsupported_or_worse).
2. `citation_support_rate` = (VERIFIED claims carrying a RESOLVED citation_id) / material.
   (A VERIFIED claim with an unresolved/None citation does NOT count — traceability floor.)
3. `required_entity_recall` = covered+citation_supported frozen rubric elements / total.
4. `safety_floor_recall` = same, restricted to the pre-registered safety element subset.
5. `diversity_score` = distinct resolved sources among VERIFIED claims / VERIFIED claims,
   reported as a DIAGNOSTIC ONLY, with an explicit `methodology_note` that it is NOT a
   superiority/win signal (a §-1.1 guard against "unique-source count as quality"). It
   measures whether verified support is monocultured on one source, nothing more.

### Claimify-style dedup (anti-inflation) — `claim_dedup.py`
Before computing #1/#2/#5, collapse near-duplicate VERIFIED claim atoms so 5 restatements
of one obvious fact count ONCE. Dedup key = (normalized-claim-text-stem AND numeric
signature) reusing `fact_dedup.extract_signature` (percent/dollar/year regexes) + a
lowercased alphanumeric content-token key. Two claims merge iff same numeric signature AND
≥0.8 content-token Jaccard. The dedup is REPORTED (n_raw, n_deduped, collapsed groups) so it
is auditable, never silent. Dedup is applied identically to EVERY system (no POLARIS bias).

### Wiring (default-OFF, byte-identical)
- `extended_metrics.py` (NEW): pure functions, the 5 metrics + dedup orchestration.
- `claim_dedup.py` (NEW): the claim-atom dedup.
- `safety_floor_elements_v3.json` (NEW data): pre-registration described above.
- `benchmark_scorecard.build_scorecard(...)`: add optional `extended: dict | None = None`;
  when None (DEFAULT) the returned dict is BYTE-IDENTICAL to today; when provided, attach
  `card["extended"] = extended`. 2-line additive change.
- `scripts/dr_benchmark/run_scorecard.py`: add `extended: bool = False` (default → identical
  behavior). When True, compute extended metrics from the atoms+rows it already has per
  (system,qid) and pass to build_scorecard. Flag `PG_BENCH_EXTENDED_METRICS` read at the CLI
  edge only (LAW VI), default OFF.
- ZERO edits to: strict_verify, the 4-role evaluator, D8/safety-floor gate, the generator,
  retrieval. The scorer is pure downstream MEASUREMENT; it cannot relax any gate because it
  runs after the report exists and touches no gate code.

### Tests — `tests/dr_benchmark/test_extended_metrics_iperm024.py`
- faithfulness_precision / citation_support_rate exact on a hand-built ClaimRow ledger.
- citation_support_rate excludes VERIFIED-but-uncited (None citation_id).
- required_entity_recall / safety_floor_recall exact on frozen-rubric RubricElements.
- dedup collapses 3 restatements of one numeric fact → counted once; cross-system identical.
- diversity_score = distinct-sources/verified; monoculture (all one source) → low.
- §-1.1 structural test: extended_metrics functions accept only ClaimRow/RubricElement;
  a test asserts no report-text path (the module exposes no text-ingesting entry point).
- byte-identical: build_scorecard with extended=None == today's output.

## §6 — paid smoke honesty
The scorer is PURE aggregation over an already-produced §-1.1 audit ledger. The only billed
work (the span-fetch + evidence-locked judge that PRODUCES the ledger) is the SAME paid work
as the operator-gated broad beat-both run. So #1216's "paid §-1.1 smoke" is naturally folded
into that broad run — there is no separate spend that proves a scorer. What I prove NOW
(cash-free): the metric math + dedup are correct on real stored reports + a deterministic
fake judge. I will state this plainly, not claim a paid proof I did not run.

## Question for you
1. Is the structural §-1.1 guarantee (metrics from audited ClaimRows/RubricElements only,
   never raw text) sufficient to keep required_entity_recall/diversity_score off the BANNED
   list? Or do you want diversity_score gated/removed entirely?
2. Is reusing the frozen rubric + a pinned safety-tag companion the right call vs a new file?
3. Is the dedup key (numeric signature AND ≥0.8 content Jaccard) safe against
   over-merging DISTINCT claims (the fact_dedup populated-axis-conflict lesson)?
4. Is folding the paid proof into the broad run (vs a separate scorer smoke) acceptable?
