# I-cred-002 (#1151) — Phase 2: adaptive LLM credibility skill (reliability × relevance) — BRIEF for Codex review

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

You are reviewing a DESIGN BRIEF (acceptance-criteria correctness), not a diff. ITER-1 returned REQUEST_CHANGES with 2 P1 (anti-fabrication rule undefined; judge payload underspecified) + P2 refinements; ALL are addressed below in §3a + the revised ACs. Judge whether the contract is now precise/testable and the faithfulness invariants hold.

## 0. HARD CONSTRAINTS (operator-locked — NOT relaxable, do not offer the relaxed option)

- **Advisory only.** The credibility skill NEVER becomes a faithfulness gate. `strict_verify`'s six per-sentence checks in `src/polaris_graph/generator/provenance_generator.py` remain the ONLY binding faithfulness gate. A credibility weight/rationale is a side-output to disclose, never a reason to keep or drop a sentence.
- **Default-OFF byte-identical.** Gated by `PG_SWEEP_CREDIBILITY_SKILL`. Flag-off (and no caller wiring) ⇒ production output byte-identical. No production caller is added in this phase.
- **NO fixed domain rubrics.** Per operator (2026-06-08, plan §9.1): users ask 10,000+ fields; ONE generic credibility skill; the detected domain is a HINT the skill reasons over, NOT a branch that swaps rubrics.
- **Weight = evidence quality, never headcount.** The skill scores a single source's reliability×relevance; it does not count sources.
- **No network in off-mode / no judge.** The LLM call is dependency-injected; with no injected judge, zero httpx client, zero spend. Mirrors `semantic_conflict_detector`.
- **No row mutation, no faithfulness-file edit.** Returns a separate result object; does not mutate evidence rows or touch provenance_generator / strict_verify / 4-role / two-family / corpus_approval.
- **Pure, snake_case, explicit imports, LAW VI** (every threshold env-overridable named constant, no magic numbers, no hardcoded model/endpoint).

## 1. Goal

Build `src/polaris_graph/authority/credibility_skill.py`: one generic, domain-agnostic LLM "credibility skill" that, per research question, scores EACH candidate source on **reliability × relevance** with a written, inspectable rationale, consuming POLARIS's already-computed deterministic authority signals as its priors. Layer-1 scorer of the credibility-weighted sourcing redesign (`docs/credibility_weighted_sourcing_redesign_plan_2026_06_07.md` §9.1, research `docs/credibility_adaptive_weighting_and_bothsides_recs_2026_06_08.md`).

## 2. Mechanism (JudgeRank-style 3-step, each step inspectable = the audit template)

The injected judge is asked, for the question + one source at a time, to produce:
1. **query_need** — what THIS question needs; what would count as strong evidence (string).
2. **source_assessment** — query-aware GENERIC SIFT + lateral-reading + provenance heuristics (prefer primary/official over aggregator/SEO; original over secondary summary; corroborate laterally; weigh incentives/track record; downgrade stale/superseded/retracted). NOT a domain table.
3. **two-axis judgment** — `reliability_score ∈ [0,1]` × `relevance_score ∈ [0,1]`, a `credibility_weight`, a `rationale`, and `signals_cited`.

The skill's PRIORS are the deterministic `authority_model` signals. The judge may up- OR down-weight them with a stated reason (it is NOT bounded below by the prior); it MAY NOT FABRICATE authority where `authority_confidence == "LOW"` / signals are thin — see the exact cap in §3a.

## 3. Module contract

```python
PG_SWEEP_CREDIBILITY_SKILL  # flag; credibility_skill_enabled() helper, _OFF_VALUES frozenset (match supersession.py / claim_graph.py)

@dataclass
class CredibilityJudgment:
    evidence_id: str
    reliability_score: float        # [0,1] AFTER the §3a anti-fabrication cap
    relevance_score: float          # [0,1]; unknown => 1.0 (multiplicative-neutral)
    credibility_weight: float       # [0,1] = clamp01(reliability_score * relevance_score) — FIXED product
    rationale: str
    signals_cited: list[str]        # subset of signals present on the row
    query_need: str
    judge_error: bool = False       # True iff the injected judge errored/returned malformed for this source

def score_source_credibility(
    research_question: str,
    rows: list[dict],               # evidence rows carrying authority_score / source_class / corroboration_count / authority_confidence / signal_scores / junk_class / predatory_oa + text
    *,
    domain: str | None = None,      # HINT only; never a branch
    judge: Callable[[str, dict], dict] | None = None,  # injected (question, payload_dict) -> judgment dict
) -> list[CredibilityJudgment]:
    ...
```

- `judge=None` ⇒ NO network: priors-only judgment per row (reliability = `clamp01(authority_score)` or 0.0 if absent, relevance = 1.0, rationale="no judge wired", `signals_cited` from present signals, `judge_error=False`). Off-mode no-op + offline-testable.
- The judge callable is wired by the CALLER (a future phase), like `get_default_judge()` in `semantic_conflict_detector.py`; this pure library constructs no client. Model/endpoint/key from env (`OPENROUTER_API_KEY`, `PG_CREDIBILITY_SKILL_MODEL`), never hardcoded.

## 3a. Exact anti-fabrication rule + judge payload (resolves iter-1 P1-1 / P1-2)

**Anti-fabrication cap (the LOW/thin guardrail — exact + testable):**
- Applied ONLY when `authority_confidence == "LOW"` OR signals are thin (`authority_score is None` or empty `signal_scores`):
  `reliability_score = clamp01( min( judge_reliability, clamp01(authority_score or 0.0) + PG_CREDIBILITY_MAX_UPLIFT ) )`.
  `PG_CREDIBILITY_MAX_UPLIFT` default **0.15** (env-overridable, LAW VI).
- For non-LOW / non-thin rows the judge's reliability passes through (clamped to [0,1]); the judge MAY down-rate BELOW the prior freely (a high-authority but irrelevant/weak source can score low). The prior is **not** a lower bound.
- The priors-only judgment is the fallback ONLY on `judge_error` (or `judge=None`) — NOT a universal floor that blocks judge down-rating.
- `relevance_score` unknown (priors-only, or judge omits it) = **1.0** (multiplicative-neutral; 0.5 would silently halve authority). `credibility_weight = clamp01(reliability_score * relevance_score)` — the product is FIXED; only `PG_CREDIBILITY_MAX_UPLIFT` (and, if added, a single named combiner knob) are env-tunable.

**Judge payload (so relevance is actually judgeable — exact shape):** a pure `_build_judge_payload(research_question, row, domain) -> dict` produces, per source, WITHOUT mutating the row:
`{evidence_id, title, url, snippet, authority_score, source_class, corroboration_count, authority_confidence, signal_scores, junk_class, predatory_oa, domain_hint}` — where `snippet` is bounded to `PG_CREDIBILITY_SNIPPET_CHARS` (default 1200) drawn from `direct_quote`/`statement`/`text`. The injected judge signature is `judge(research_question, payload_dict) -> judgment_dict`; it sees ONLY the payload (title/url/snippet give it relevance context). `domain_hint` is a single string field — NOT a branch, NOT a rubric table.

## 4. Acceptance criteria (each maps to an offline test, deterministic fake judge — no network, no live data)

1. Flag default-OFF: `credibility_skill_enabled()` False unset; truthy on (parametrized off/on, case/space-insensitive) — matches supersession/claim_graph.
2. `judge=None` ⇒ priors-only: one judgment per row, no exception, reliability = `clamp01(authority_score or 0.0)`, relevance 1.0, `judge_error=False`, no client built.
3. Injected fake judge ⇒ its reliability/relevance/rationale flow through; `credibility_weight == clamp01(reliability_score*relevance_score)`.
4. **Anti-fabrication cap (exact):** a fake judge returning reliability=0.99 for a row with `authority_confidence == "LOW"` and `authority_score=0.30` yields `reliability_score == clamp01(0.30 + PG_CREDIBILITY_MAX_UPLIFT)` (== 0.45 at default). And a fake judge that DOWN-rates a HIGH-authority row (reliability=0.10) passes through to 0.10 (prior is not a floor).
5. `signals_cited` is a SUBSET of the signals present on the row (cited-but-absent dropped).
6. **Malformed judge output:** out-of-range (`1.7`, `-0.2`) clamped to [0,1]; `NaN`/`inf` and a malformed/missing-key judgment dict ⇒ treated as a judge error for that row (`judge_error=True`, priors-only fallback) — never a NaN weight, never a crash.
7. A judge that RAISES for one row sets `judge_error=True` for THAT row only + priors fallback; other rows unaffected (isolation, recall-first).
8. **No fixed rubric (strong):** `domain` appears ONLY as the `domain_hint` payload field; there is NO domain-keyed branch / rubric table / branch-swapped scoring in the module. Test: `domain="clinical"` vs `"policy"` produce identical control flow + identical judgments for the SAME injected judge (the only difference is the `domain_hint` string in the captured payload).
9. **Env knobs scoped:** the product formula is FIXED; only `PG_CREDIBILITY_MAX_UPLIFT` (and `PG_CREDIBILITY_SNIPPET_CHARS`) are env-overridable. Test: changing `PG_CREDIBILITY_MAX_UPLIFT` changes a LOW-row capped reliability; it does NOT change a non-capped row's weight.
10. Purity: no faithfulness file imported; `score_source_credibility` and `_build_judge_payload` mutate no input row (assert rows unchanged by content).
11. **Judge payload shape:** a fake judge that captures its `payload_dict` asserts ALL §3a fields present, `snippet` ≤ `PG_CREDIBILITY_SNIPPET_CHARS`, `domain_hint` == the passed domain (or "" when None), and the source row is not mutated by payload construction.

## 5. Files I have ALSO checked and they're clean (substrate scan — please VERIFY)

- `src/polaris_graph/authority/source_class.py:71-90` — `AuthorityResult`: `authority_score: float`, `source_class: SourceClass`, `corroboration_count: int`, `authority_confidence: AuthorityConfidence`, `reasons: list[str]`, `signal_scores: dict`, `junk_class: str = ""`, `predatory_oa: bool = False`. The priors P2 consumes.
- `src/polaris_graph/authority/authority_model.py:84-205` — `score_source_authority(signals, *, corpus_ctx=None) -> AuthorityResult` (producer; unchanged).
- `src/polaris_graph/retrieval/tier_classifier.py:2030-2040` — rows carry `authority_score/source_class/corroboration_count/authority_confidence` as additive keys; absent key ⇒ priors-unknown, never crash.
- `src/polaris_graph/nodes/scope_gate.py:192-220, 387-413` — `run_scope_gate(..., domain=DEFAULT_DOMAIN)` + `load_scope_template(domain)`; domain is an EXPLICIT caller param, never inferred. P2 takes it as an optional hint string.
- `src/polaris_graph/retrieval/semantic_conflict_detector.py:208-272, 320-487` — injected-judge precedent: `detect_semantic_conflicts(pairs, judge, ...)`, `get_default_judge()` lazy singleton, `OPENROUTER_API_KEY` read only at construct time, off-mode never builds a client. P2 mirrors this.
- `src/polaris_graph/authority/supersession.py:21-67` — `SupersessionResult` dataclass-result precedent + `PG_SWEEP_SUPERSESSION` + `_env_float/_env_int`. P2 follows it.
- `src/polaris_graph/synthesis/claim_graph.py:75-109` — `PG_SWEEP_CLAIM_GRAPH` + `_OFF_VALUES` frozenset + `claim_graph_enabled()`; P2's flag matches in shape.
- No existing code scores sources by reliability×relevance (grepped credibility/reliability/relevance/weight under `src/polaris_graph/`): authority_model is domain-AGNOSTIC signal scoring, supersession is TEMPORAL, claim_graph is STANCE. P2 is orthogonal — REUSES authority signals, does not duplicate.

## 6. Output schema (return this YAML)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## 7. Iter-1 resolutions (for your verification)

- P1-1 (anti-fabrication) → §3a exact bounded-delta cap `reliability ≤ clamp01(authority_score)+PG_CREDIBILITY_MAX_UPLIFT` for LOW/thin only; prior is NOT a floor (judge may down-rate); priors-only is the judge-error/None fallback. AC-4.
- P1-2 (judge payload) → §3a `_build_judge_payload` exact field list incl. title/url/snippet for relevance; AC-11.
- Q1 → unknown relevance = 1.0 (multiplicative-neutral). §3a + AC-2.
- Q3 → per-source calls (AC-7 isolation). Confirmed.
- AC-6 → now covers NaN/inf + malformed dict ⇒ judge_error fallback.
- AC-8 → strengthened: no domain branch/rubric table; identical control flow across domains.
- AC-9 → product FIXED; only the uplift + snippet bound env-tunable; test isolates a capped vs non-capped row.

Open question for you: is `PG_CREDIBILITY_MAX_UPLIFT` default 0.15 the right magnitude, or should the LOW/thin cap be harder (e.g. 0.0 uplift = the judge cannot exceed the deterministic prior at all for LOW-confidence sources)?
