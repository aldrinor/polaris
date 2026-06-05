# Codex BRIEF review — I-ready-012 (#1079): semantic/NLI cross-document contradiction layer — ITER 2

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

**REVIEW ONLY — do not modify any file. Judge this revised brief's acceptance criteria; return the YAML verdict block ONLY. Claude authors the diff after APPROVE.**

---

## 0. Your iter-1 findings — all accepted, addressed below

iter-1 was REQUEST_CHANGES with 2 P1 + 2 P2. Both P1s were correct and material — thank you. Corrections:

**P1-1 (pairing was blind to the target rows).** You were right: deriving the subject key from `extract_numeric_claims`/`extract_qualitative_assertions` is self-defeating — those extractors emit NO tuple for the reproduced no-number/no-cue survival pair, and the drug subject extractor does not recognize "adjuvant chemotherapy." **Fix:** the semantic pre-filter is now a RECALL-oriented lexical clustering over the raw text of ALL evidence rows (independent of the rule extractors), and there is a test that asserts the reproduced rows land in the SAME candidate cluster BEFORE any judge is invoked. See §2.1.

**P1-2 (routing overstated; only numeric flows to disclosure+PT08).** Verified against the code: the report disclosure loop `run_honest_sweep_r3.py:4480-4494` iterates `for c in contradictions` (numeric ONLY); the generator arg `:4019` and the evaluator/PT08 arg `:4825` are both `[asdict(c) for c in contradictions]` (numeric ONLY); qualitative records get a SEPARATE block `:4542` and are NOT PT08-counted. So writing semantic records to `contradictions.json` does NOT surface or gate them. **Fix:** semantic records are EXPLICITLY routed into (a) a dedicated report disclosure block and (b) the PT08 evaluator input. See §2.2.

**P2-1 (budget).** The reused entailment judge re-raises `BudgetExceededError` by design. **Fix:** the semantic loop catches it, stops calling the judge, keeps records found so far, fail-open — with an explicit acceptance test (§4.6).

**P2-2 (record shape).** **Fix:** explicit `SemanticConflictRecord` shape (§2.3) with `subject`/`predicate` (for PT08 substring check) and a finite, audit_ir.loader-compatible claim shape.

## 1. The gap (unchanged, reproduced offline this branch)

Prose-only directional contradiction, no shared number, no NegEx cue → passes both rule detectors. Reproduced: two T1 rows "adjuvant chemotherapy improved overall survival in stage II colon cancer" vs "...provided no overall survival benefit..." → `numeric=0, qualitative=0`. The NLI pass must turn this green WITHOUT regressing the rule detectors.

## 2. Corrected design (additive, fail-open, default OFF `PG_SWEEP_NLI_CONFLICT`)

### 2.1 Pairing — recall-oriented, independent of the rule extractors (P1-1)

New module `src/polaris_graph/retrieval/semantic_conflict_detector.py`:
- `cluster_candidate_rows(evidence_rows) -> list[list[row]]`: groups rows by shared SALIENT content words computed directly from each row's `direct_quote`/text (lowercase, stopword-stripped, ≥`PG_SWEEP_NLI_CONFLICT_MIN_OVERLAP` default 2 shared content words → same candidate cluster). This is RECALL-oriented (the cheap pre-filter to bound O(n²)); the JUDGE provides precision. It does NOT call the numeric/qualitative extractors. For the reproduced pair, both rows share {adjuvant, chemotherapy, overall, survival, stage, colon, cancer} → same cluster.
- `extract_pairs(clusters, max_pairs)` → same-cluster row pairs only, hard-capped `PG_SWEEP_NLI_CONFLICT_MAX_PAIRS` (default 60), highest-tier pairs first.
- `detect_semantic_conflicts(pairs, judge) -> list[SemanticConflictRecord]`: for each pair, ask the judge (claim A vs claim B → entail/neutral/contradict + confidence); keep `contradict ≥ PG_SWEEP_NLI_CONFLICT_MIN_CONFIDENCE` (default 0.7). Subject/predicate derived from the pair's shared salient terms.
- `semantic_conflict_enabled()` reads `PG_SWEEP_NLI_CONFLICT`, **default OFF**.

### 2.2 Routing — explicit, three points (P1-2)

A third fail-open `try` block after the qualitative block (`run_honest_sweep_r3.py:3119`), default-OFF, builds `semantic_records`. Then:
1. **contradictions.json** — append `semantic_records` to the merged list (`:3120-3127`) — for auditability (the raw dump), as today.
2. **Report disclosure** — a NEW dedicated block "## Semantic contradiction disclosures (cross-document NLI)" rendered parallel to the qualitative block (`:4542`), printing per record: subject, predicate, the TWO conflicting claims with their evidence_ids + tiers, and the NLI label/confidence. This is what makes the user SEE it AND what makes PT08's substring(subject)+substring(predicate) check find it in report text.
3. **PT08 evaluator input** — extend the evaluator/PT08 `contradictions` arg (`:4825`) to include `[asdict(r) for r in semantic_records]` so PT08 actively gates: a detected semantic contradiction whose subject+predicate is absent from report text → `pt08=False` → `abort_evaluator_critical`. Semantic records are NOT mixed into the numeric renderer loop `:4480-4494` (which expects numeric value ranges) — they render via their own block (point 2), so the numeric path is byte-identical.
   - The generator arg `:4019` stays numeric-only (the numeric-shaped hedging gate expects value ranges; semantic records have none). Semantic surfacing is via the disclosure block + the Limitations prompt that already requires naming disagreements — NOT via the numeric hedging path. (Open question for you: do you want semantic records ALSO fed to a separate generator hedging path, or is disclosure-block + PT08-gate sufficient surfacing for this issue? My lean: disclosure + PT08 is the correct, minimal, faithfulness-safe surface; a generator-hedging extension is a separate enhancement.)

### 2.3 Record shape (P2-2)

```python
@dataclass
class SemanticConflictRecord:
    subject: str          # shared salient subject (for PT08 substring + disclosure)
    predicate: str        # the disagreement axis (e.g. "overall survival benefit")
    claims: list[dict]    # len>=2: [{evidence_id, text, tier, nli_label}]
    type: str = "semantic"
    severity: str = "review"
    nli_confidence: float = 0.0
```
`asdict` yields finite JSON; no numeric `value` field is required by the numeric path (semantic records never enter the numeric renderer/hedging). I will add a test that `audit_ir.loader` ingests a `contradictions.json` containing a semantic record without error (P2-2 loader-compat).

## 3. Faithfulness safety

ADDITIVE only: more contradictions disclosed + PT08 can only become STRICTER (a newly-detected semantic conflict that isn't disclosed → abort). It does NOT touch strict_verify / provenance / 4-role / the numeric+qualitative detectors / the numeric renderer. Default-OFF ⇒ byte-identical. Fail-open ⇒ never aborts the sweep on a detector/judge/budget error.

## 4. Acceptance criteria (GREEN for #1079)

1. **Recall hole closes:** the reproduced prose-only pair + a FAKE judge returning `contradict` → `cluster_candidate_rows` puts both rows in one cluster (asserted BEFORE the judge) AND `detect_semantic_conflicts` emits one `type:"semantic"` record with both evidence_ids + subject + predicate.
2. **Routing proven:** an integration-style offline test (FAKE judge) asserts a semantic record reaches BOTH the rendered report disclosure block (subject+predicate present in report text) AND the PT08 evaluator `contradictions` input; and that a semantic record whose disclosure is suppressed drives `pt08=False` (gate actually bites).
3. **Flag-OFF byte-identical:** `PG_SWEEP_NLI_CONFLICT` unset → `contradictions.json`, report text, and the PT08 input are byte-identical to today (no judge constructed, no network, numeric+qualitative unchanged).
4. **Precision:** an entail/neutral pair → no semantic record.
5. **Fail-open on detector/judge/import error:** logs + skips; numeric+qualitative records + the sweep are unaffected.
6. **Fail-open on BudgetExceededError:** the loop catches it, keeps records found so far, does not abort the sweep — explicit test.
7. **Cost-bounded:** same-cluster pairs only, capped at `PG_SWEEP_NLI_CONFLICT_MAX_PAIRS`; test asserts the judge is never called when OFF and pair count never exceeds the cap.
8. **audit_ir.loader compat:** a `contradictions.json` with a semantic record loads without error.
9. Faithfulness machinery untouched; offline smoke green; production diff additive.

## 5. Files I have ALSO checked and they're clean (adjacent-file scan)

- `run_honest_sweep_r3.py:3093-3127` (numeric+qualitative detect + merged json), `:4019` (generator arg, numeric), `:4480-4494` (numeric disclosure loop), `:4542` (qualitative disclosure block — my template for the semantic block), `:4825` (evaluator/PT08 arg, numeric). Verified the numeric-only flow you flagged.
- `src/polaris_graph/llm/entailment_judge.py` — `_EntailmentJudge` substrate I reuse (Decision A confirmed). I ADD a contradiction-prompt sibling call; I do NOT modify the strict_verify entailment path. Family-seg + cost-ledger + off-mode-no-network inherited.
- `src/polaris_graph/evaluator/external_evaluator.py:578-593` (PT08) — substring(subject)+substring(predicate); my record carries both; I add semantic records to its input.
- `src/polaris_graph/retrieval/contradiction_detector.py` + `qualitative_conflict_detector.py` — the dataclass+`asdict`+`*_enabled()` pattern I mirror. Unchanged.
- `src/polaris_graph/audit_ir/` loader — I will add a loader-compat test (P2-2).
- `tests/polaris_graph/test_contradiction_detector.py` — harness + row shape I mirror.

## 6. Smoke plan (offline, no spend, no model — §8.4-clean; FAKE judge)

`tests/polaris_graph/test_semantic_conflict_detector_iready012.py`: (1) cluster groups the reproduced rows; (2) FAKE judge=contradict → one semantic record; (3) entail/neutral → none; (4) flag-OFF inert + byte-identical merged json; (5) detector/judge error → fail-open; (6) BudgetExceededError → fail-open keep-partial; (7) pair cap honored + judge never called OFF; (8) routing: record appears in rendered disclosure + PT08 input + suppressed-disclosure → pt08 False; (9) audit_ir.loader ingests a semantic record.

## 7. Output schema (return EXACTLY this; loose prose rejected)

```yaml
verdict: APPROVE | REQUEST_CHANGES
routing_approach_ok: yes | no            # §2.2 three-point routing (disclosure block + PT08 input, numeric path untouched)
pairing_approach_ok: yes | no            # §2.1 recall lexical clustering independent of rule extractors
generator_hedging_needed: yes | no       # the §2.2 open question
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
