HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Output schema (return EXACTLY this, no prose verdict):
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

---

# Brief — I-cap-002 feature 4/4 (#1060): NLI entailment as an additive verification annotation

## 0. What this gate reviews
BRIEF gate (design correctness). Two things to red-team hardest: (a) **no silent degrade** — if NLI is
requested but the model/deps are unavailable, the run must FAIL LOUD / surface it, never silently pass (LAW
II + the operator's standing no-downgrade directive); (b) **NLI is ADDITIVE/advisory**, not a new binding
release gate (the 4-role D8 seam must remain the single binding gate).

## 1. Context
Final feature of #1060 ("B then A"). Wire the four Tier-B capabilities into the benchmark (Pipeline A), then
run the 1000-URL beat-both. Features 1/4 STORM (#1061), 2/4 depth-gate (#1062), 3/4 agentic (#1063) are DONE
(Codex-approved). This is **feature 4/4: NLI entailment**.

## 2. The capability today (Pipeline B only) + the silent-fallback hazard
`src/polaris_graph/agents/nli_verifier.py` is a full minicheck-based entailment checker:
- `load_nli_model()` → a MiniCheck scorer (default `flan-t5-large`, 75% LLM-AggreFact; `MiniCheck-7B` /
  `faithlens` options). Heavy deps: `torch` + `transformers` + `minicheck`.
- The scorer API is `scorer.score(docs=[premise…], claims=[hypothesis…]) → (labels, probs, chunks,
  chunk_probs)` — `probs[i]` is P(claim_i entailed by doc_i).
- Flags: `PG_NLI_ENABLED`, `PG_NLI_MODEL`, `PG_NLI_DISPUTE_THRESHOLD` (0.25), `PG_NLI_BATCH_SIZE` (16).
- Consumed only in Pipeline B (`nodes/synthesize.py`, `nodes/assemble.py`, `clinical_generator/strict_verify`).

**THE HAZARD:** `verify_evidence_nli` (L666-668) does `scorer = await load_nli_model(); if scorer is None:
return []  # Signal caller to fall back` — a SILENT fallback. If we reuse that in the benchmark, a missing
model would silently produce "no NLI findings" that reads as "NLI verified clean". That is exactly the
silent-degrade the operator forbids. The benchmark wiring MUST fail loud instead.

Why NLI matters for beat-both: strict_verify is regex/numeric. Per `feedback_qualitative_negation_escapes_
regex`, qualitative-negation hallucinations ("X did NOT reduce mortality") can pass the numeric/content-word
checks. NLI is the **second validator path** that catches a delivered sentence NOT entailed by its cited
span — a real faithfulness backstop.

## 3. Goal of feature 4/4
Behind a default-OFF flag (Gate-B activates), run NLI entailment on the **delivered verified sentences**:
for each kept sentence, score whether its CITED evidence span entails it. Record per-sentence entailment
probs + a disputed list (prob < threshold) as an **ADVISORY** `manifest['nli_verification']` + sidecar — a
machine-readable "NLI agrees these sentences are grounded" signal for the beat-both audit. It does NOT change
`release_allowed`/`status` (the 4-role D8 seam stays the single binding gate). If NLI is requested but the
model can't load, the run records `nli_status: "unavailable"` LOUDLY (surfaced in manifest + a loud log),
never a silent clean pass.

## 4. Design

### 4.1 New module `src/polaris_graph/retrieval/nli_benchmark_annotator.py`
```python
class NliUnavailableError(RuntimeError): ...

async def annotate_nli_entailment(pairs: list[dict], *, threshold: float) -> dict:
    """pairs: [{"sentence": str, "span": str, "evidence_id": str, "section": str}].
    Loads the NLI model via nli_verifier.load_nli_model(); if it returns None -> raise
    NliUnavailableError (FAIL LOUD — NO silent []). Scores span⊨sentence via scorer.score(
    docs=[span…], claims=[sentence…]); returns:
    {nli_status:"ok", model, sentences_checked, disputed_count,
     disputed:[{section, evidence_id, prob, sentence}], min_prob, mean_prob, threshold}."""
```
Reuses `nli_verifier.load_nli_model` + the exact `scorer.score(docs=, claims=)` call shape used at
`nli_verifier.py:804`. No new dependency (minicheck/torch are already optional deps of nli_verifier). The
ONLY behavioral difference from `verify_evidence_nli` is: **raise instead of returning `[]`** when the model
is unavailable.

### 4.2 Wire into `run_one_query` (success path, advisory) — near the depth annotation
After the report is assembled + verif_details built (so the kept sentences + their cited spans are known),
behind `PG_NLI_IN_BENCHMARK` (default OFF), fail-open-for-FAULTS but fail-LOUD-for-unavailable:
1. Build `pairs` from `multi.sections` kept sentences: for each kept `SentenceVerification` `sv`, take
   `sv.sentence` and its cited span text = `ev_pool[token.evidence_id][<quote field>][token.start:token.end]`
   (ev_pool already built at L~4177; the quote field is the same one strict_verify slices — confirm
   `direct_quote`/`statement`). One pair per kept sentence (first/primary token span).
2. `try: result = await annotate_nli_entailment(pairs, threshold=PG_NLI_DISPUTE_THRESHOLD)` then write
   `nli_verification.json` sidecar FIRST, then `manifest['nli_verification'] = result` (advisory; carries
   `nli_status:"ok"`), and log `[nli] checked=… disputed=… min_prob=…`.
3. `except NliUnavailableError as e:` — FAIL LOUD: log `[nli] WARN model UNAVAILABLE (…) — NLI annotation
   NOT produced; this is surfaced, NOT a silent clean pass` and set
   `manifest['nli_verification'] = {"nli_status":"unavailable","reason":str(e)}` (surfaced in the manifest).
   The run still COMPLETES (NLI is advisory, not a binding gate) but the unavailability is explicit.
4. `except Exception as e:` (other faults, e.g. a scoring error on a single batch) — log loud + record
   `nli_status:"error"` with the reason; never abort the run.
Placement mirrors the depth annotation; runs AFTER status/release are final; NEVER mutates them.

### 4.3 Gate-B activation
`run_gate_b_query`: `os.environ.setdefault("PG_NLI_IN_BENCHMARK", "1")` (+ the model env, e.g.
`os.environ.setdefault("PG_NLI_MODEL", "flan-t5-large")`). The live model loads on the VM (heavy deps); per
CLAUDE.md §8.4 the model is NOT loaded in the autonomous dev loop — offline tests MOCK the scorer.

### 4.4 Invariants the diff MUST hold
1. **No silent degrade** — model unavailable → `NliUnavailableError` → `nli_status:"unavailable"` surfaced in
   manifest + loud log. NEVER an empty/clean result that reads as "NLI verified".
2. **Additive/advisory** — only ADDS `manifest['nli_verification']` + sidecar; NEVER changes
   `release_allowed`/`status`/abort. The 4-role D8 seam stays the single binding gate.
3. **Faithfulness direction** — NLI scores span⊨sentence on ALREADY-delivered sentences; it produces no
   evidence and can only FLAG (advisory), never inject content.
4. **Flag default OFF → byte-unchanged** legacy manifest; Gate-B turns it ON.
5. **Heavy deps isolated** — the new module imports `nli_verifier` lazily inside the function; torch/minicheck
   load only when the flag is ON and the model is requested (never at import). Offline tests mock the scorer;
   no torch in CI.
6. **Fail-open for transient faults** — a per-batch scoring error logs + records `nli_status:"error"`; the
   run completes (advisory). Only the MODEL-UNAVAILABLE case is the loud "unavailable" surface.

## 5. Files I have ALSO checked
- `nli_verifier.py`: `load_nli_model()` (L149), the silent `return []` (L666-668) I deliberately do NOT
  replicate, `scorer.score(docs=,claims=)` shape (L804), flags (L34-38).
- `run_honest_sweep_r3.py`: `ev_pool` built L~4177; kept sentences + tokens in `verif_details` (L~4198,
  `kept:[{sentence,tokens:[{evidence_id,start,end}]}]`); the depth annotation (feature 2) is the placement
  precedent (ON-mode-only manifest key + sidecar, after status final).
- Gate-B activation precedent: `run_gate_b.py` L436-465 (quantified/V30/depth/agentic setdefaults).
- `nodes/synthesize.py:251` consumes `verify_evidence_nli` (Pipeline B) — untouched.

## 6. Open questions for the gate
- **Span source:** use the kept sentence's PRIMARY cited token span (`ev_pool[id][quote][start:end]`), or the
  full evidence `direct_quote` for that id? (I lean PRIMARY span — that is exactly what strict_verify checked,
  so a low NLI prob there is the cleanest "regex passed but entailment fails" signal. A sentence with
  multiple tokens → score against the concatenation of its cited spans?)
- **Advisory vs soft-gate:** keep strictly advisory (recommended — D8 single gate), or ALSO surface a
  `nli_disputed_fraction` that a FUTURE issue could wire as a soft gate? I propose advisory-only now.
- **Which quote field** does strict_verify slice for the span — `direct_quote` or `statement`? (I will read
  the strict_verify slice site to match it exactly in the diff.)

## 7. Acceptance (GREEN)
- New `nli_benchmark_annotator.py` (raise-not-silent on unavailable; reuses load_nli_model + scorer.score).
- `run_one_query` advisory block: flag OFF default; advisory manifest key + sidecar; fail-LOUD on unavailable
  (manifest `nli_status:"unavailable"`); fail-open on transient faults; never changes release/status.
- `run_gate_b_query` activates `PG_NLI_IN_BENCHMARK` (+ model env).
- Tests (offline, MOCK the scorer — no torch): ok-path disputed detection; unavailable-path raises →
  manifest records `unavailable` (NOT clean); flag-OFF → no key.
- ≤ ~200 LOC.

## 8. Smoke plan (offline, NO torch per §8.4)
1. `pytest` the annotator tests with a FAKE scorer (monkeypatch `load_nli_model`): a low-prob pair is
   flagged disputed; `load_nli_model→None` raises `NliUnavailableError`.
2. Extend + run the benchmark-stack activation test (asserts `PG_NLI_IN_BENCHMARK` == "1").
3. `py_compile`/`ast.parse` the touched files; import-smoke the annotator (must NOT import torch at module
   load).
4. (The live flan-t5-large run is the Tier-A VM run, not this offline gate.)
