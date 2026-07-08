# box2 credibility-pass SPEED fix — design + diff (I-deepfix-001)

## The problem (root-caused separately, confirmed)
The advisory credibility pass (`run_credibility_analysis`, called at
`multi_section_generator.py:9118` via `asyncio.to_thread`) is deterministically
slow-to-wedged on a resume corpus (999 rows). It has TWO sub-legs, BOTH
bottlenecked on the shared side-judge semaphore pinned to **2**
(`PG_SIDE_JUDGE_MAX_CONCURRENCY=2`, run_gate_b slate):

- **Leg A — source scoring.** `score_source_credibility` (credibility_skill.py)
  fires ONE GLM-5.2 credibility-judge POST per row (~999 calls, ~24–40s each).
  This is the leg box2 froze in first (it runs before basket assembly, right
  after the W9 log — matching the freeze signature). ADVISORY.
- **Leg B — basket-member verify.** `_assemble_baskets` →
  `_run_member_verifies` fires ONE **entailment**-judge POST per claim
  (`build_claim_graph` guarantees ≥1 claim/row → ~999 calls, ~30s each).
  FAITHFULNESS-LOAD-BEARING: its `SUPPORTS` verdicts are consumed at render
  (corroborator citations + breadth enrichment) WITHOUT re-verification
  (credibility_pass.py:1316-1320), so its model + count are NOT changeable.

At cap=2 each leg is ~999×30/2 ≈ 4.2h → the 26-min freeze / eventual
3000s-wall degrade.

## Constraints (from the operator, in priority order)
1. Do NOT worsen OpenRouter 429 load (box1 generation live, account loaded,
   other campaigns share the key). 429 is a request-RATE limit.
2. Keep EVERY source credibility-weighted; no downstream backfire on
   selection / ranking / weighting / disclosure. No depth loss.
3. Faithfulness-neutral: strict_verify / NLI / 4-role / span-grounding frozen.
4. Commercial time: cred pass ≈ ≤10–15 min ideal; whole resume run ≤1–1.5 h (firm).
5. Stand alone WITHOUT a dedicated key; benefit MORE if one is supplied.

## Key code facts that shape the fix (verified, not assumed)
- **Selection/ranking do NOT consume the LLM credibility.** `weight_mass.py:5,
  67,161-167` (plan §148, Codex #1155 P1): breadth/selection ordering =
  `authority_score(canonical origin)` ONLY; credibility is a DISCLOSED side-
  field, explicitly NOT a mass factor. So cutting/deferring LLM judging does
  NOT move selection or ranking. The operator's belief that "selection ranking
  consumes the LLM tiering" is, per the code, only partly true — ranking is
  authority; the LLM feeds the **disclosure** + a conservative demotion.
- **Every source still gets a weight either way.** `_priors_only_judgment`
  (credibility_skill.py:183) = reliability from `authority_score`,
  relevance neutral 1.0, weight = authority. High for .gov/T1, low for
  T7/junk (so the demotion still fires). Missing-credibility ⇒ promote-NEUTRAL
  (kept), the §-1.3 keep direction.
- **The judge model is independently configurable** (`PG_CREDIBILITY_JUDGE_MODEL`,
  credibility_judge_caller.py:43) and family-checked (evaluator vs generator).
  Slate already runs same-family GLM with `PG_PERMIT_GENERATOR_EVALUATOR_SAME_FAMILY=1`.
- **Real drb_72 tier mix** (529-row corpus_snapshot): T1 17.8% + T2 8.5%
  (clear-high) = 26%; T6 6% + T7 13.8% (clear-low) = 20%; **T3/T4/T5/UNKNOWN =
  54%** (T4 alone 45% — the ambiguous news/web band where LLM relevance
  actually matters). ⇒ a tier-band hybrid skips ~46% of Leg-A calls.

## Decision — the surgical combination (each lever independent, default-OFF)

**Leg A (advisory, reducible + model-swappable) — attack request COUNT + per-call cost:**
1. **Tier-band hybrid** (`PG_CREDIBILITY_JUDGE_HYBRID_TIERS=T1,T2,T6,T7`,
   default empty=OFF): LLM-judge only the AMBIGUOUS tiers; clear-high and
   clear-low tiers take their deterministic authority prior. Cuts ~46% of
   Leg-A requests. Every source keeps a real weight; the disclosure stays
   complete (coverage assertion `credibility_pass.py:1400` holds — all rows
   have a judgment); selection/ranking untouched (authority). The prior rows
   carry a disclosing rationale.
2. **Fast small OPEN judge model** (`PG_CREDIBILITY_JUDGE_MODEL=z-ai/glm-4.5-air`
   or similar): tiering is a classification, not deep reasoning; ~4s vs
   ~30s/call. Sovereign (Zhipu, MIT), same `glm` family ⇒ two-family-consistent.
   Advisory ⇒ faithfulness-neutral. (Confirm the exact slug via
   `GET /models` before launch; code default stays glm-5.2, the slate sets it.)
3. **Optional dedicated endpoint** (`PG_CREDIBILITY_JUDGE_API_KEY` /
   `PG_CREDIBILITY_JUDGE_BASE_URL`, default = the OpenRouter values ⇒ byte-
   identical): a second key / direct Zhipu endpoint puts Leg A on its OWN
   rate limit ⇒ zero impact on box1's OpenRouter load. Helps if supplied,
   not required.

**Leg B (faithfulness-critical, fixed model + count) — the only lever is concurrency:**
4. **Phase-scoped side-judge concurrency**
   (`PG_CREDIBILITY_PASS_SIDE_JUDGE_CONCURRENCY`, default 0=OFF ⇒ byte-
   identical): raises the side-judge cap ONLY for the duration of the cred
   pass (both legs), leaving the composition-time entailment cap at its
   protected 2. The cred pass is a bounded-pool phase (not the 178-way
   composition gather that stormed), so a MODEST lift is storm-safe with the
   existing free-route + burst-spread + rotation + retry already in the slate.

**Both legs — safety + observability (pure win):**
5. **Bounded `acquire_judge_slot(timeout=…)`** (`PG_CREDIBILITY_JUDGE_SLOT_WAIT_S`,
   default None=unbounded ⇒ byte-identical; only the credibility caller passes
   it): a wedged slot degrades THAT advisory row to a disclosed `judge_error`
   priors fallback instead of freezing. Leg B's wedge stays bounded by the
   existing 3000s pass wall.
6. **Progress log** (`PG_CREDIBILITY_JUDGE_PROGRESS_EVERY=50`, default 0=OFF):
   the pass can never again read as a dead run.

## Wall-clock math (real counts; ~999 rows)
Leg A (fast model ~4s):  hybrid ~540 calls → C=10 ⇒ **~3.6 min**; all-999 → C=10 ⇒ ~6.7 min.
Leg B (entailment ~30s, ~999 calls, UNREDUCIBLE):
  C=8 ⇒ 62 min · C=10 ⇒ 50 min · C=16 ⇒ 31 min · C=24 ⇒ 21 min · C=32 ⇒ **15.6 min**.

**Leg B is the binding constraint.** Honest conclusion:
- **Standalone, shared loaded account** — set phase-C=8–10 (storm-safe):
  Leg A ~4 min + Leg B ~50–62 min ⇒ cred pass ≈ **~55–65 min**. Fits the FIRM
  ≤1.5 h run target; misses the ≤15 min stretch.
- **With a dedicated key / OpenRouter top-up** (raises the rate tier so a high
  entailment concurrency is safe) — phase-C=24–32 ⇒ cred pass ≈ **~16–21 min**,
  and drop the hybrid to judge all 999 at max quality with zero box1 impact.
- The ONLY way to hit ≤15 min on the shared account without a storm is to also
  **reduce Leg B's count** (verify only members that will render — bound +
  top-authority unbound). That is a faithfulness-adjacent reorder of the pass
  and is filed as the **follow-up issue**, not this surgical diff.

## Downstream safety (no backfire)
- Selection / breadth ordering = authority `weight_mass` (verified) → untouched.
- Disclosure coverage assertion holds (every row has a judgment).
- Hybrid clear-tier rows carry a real authority weight + a disclosing rationale;
  the demotion of near-zero members still fires (low prior for T7/junk).
- Every new behavior is env-gated, default values reproduce today byte-for-byte.

## Offline proof (real drb_72 corpus, no network)
`python` harness (in the final report): OFF hybrid = 529/529 judge calls; ON
(`T1,T2,T6,T7`) = 285/529 (**−46.1%**, 244 clear-tier priors), every row still
carries a real credibility_weight. Phase override: base 2 → 16 during the pass
→ 2 after (byte-identical when bound≤0). Bounded acquire: `JudgeSlotTimeout` at
0.5s under contention instead of wedging; unbounded (`timeout=None`) unchanged.

## NOTE — the phase cap only BINDS if the two pool caps are >= it
The side-judge phase override caps the shared semaphore; each leg also has its
own pool: Leg A = `PG_CREDIBILITY_JUDGE_CONCURRENCY` (default 12), Leg B =
`PG_CREDIBILITY_PASS_MAX_INFLIGHT` (slate 20). Effective C = min(pool, phase).
So a phase-C ABOVE those pools must ALSO raise them.

## Relaunch env — box2
STANDALONE (shared loaded account, no dedicated key) — pools already >=10:
```
PG_CREDIBILITY_JUDGE_MODEL=z-ai/glm-4.5-air          # confirm slug via GET /models first
PG_CREDIBILITY_JUDGE_HYBRID_TIERS=T1,T2,T6,T7
PG_CREDIBILITY_PASS_SIDE_JUDGE_CONCURRENCY=10
PG_CREDIBILITY_JUDGE_SLOT_WAIT_S=180
PG_CREDIBILITY_JUDGE_PROGRESS_EVERY=50
# leave PG_SIDE_JUDGE_MAX_CONCURRENCY=2 (composition storm protection unchanged)
# expect: Leg A ~3-4 min, Leg B ~50 min -> cred pass ~55 min (fits <=1.5h run).
```
IDEAL (operator supplies a dedicated judge key AND/OR OpenRouter top-up):
```
PG_CREDIBILITY_JUDGE_API_KEY=<second/dedicated key>  # Leg A off the main account
PG_CREDIBILITY_JUDGE_MODEL=z-ai/glm-4.5-air
PG_CREDIBILITY_PASS_SIDE_JUDGE_CONCURRENCY=32        # Leg B fast; safe only with headroom
PG_CREDIBILITY_JUDGE_CONCURRENCY=32                  # raise Leg A pool so phase-C binds
PG_CREDIBILITY_PASS_MAX_INFLIGHT=32                  # raise Leg B pool so phase-C binds
PG_CREDIBILITY_JUDGE_SLOT_WAIT_S=180
PG_CREDIBILITY_JUDGE_PROGRESS_EVERY=50
# drop the hybrid here to judge all 999 at max quality (Leg A is off-account).
# expect: cred pass ~16-20 min.
```
Note: `PG_CREDIBILITY_JUDGE_API_KEY` relieves Leg A (advisory) only. Leg B is
the binding entailment gate on the main account; its C=32 is safe only with real
OpenRouter headroom (top-up) — do NOT set phase-C=32 while box1 is hammering the
same account without it.

## Tests to add (dual-gate)
- `test_credibility_hybrid_partition`: OFF => all rows judged; ON => only non-skip
  tiers judged, all rows returned + weighted, clear rows carry the prior rationale,
  order preserved.
- `test_credibility_pass_concurrency_override`: base env cap restored on exit
  (success AND exception); bound<=0 is a no-op.
- `test_acquire_judge_slot_timeout`: contended slot raises `JudgeSlotTimeout`
  within the deadline; `timeout=None` stays unbounded (byte-identical).
- `test_credibility_judge_separate_endpoint`: `PG_CREDIBILITY_JUDGE_API_KEY` /
  `_BASE_URL` chosen over OPENROUTER_*; a non-OpenRouter base omits the `provider`
  routing block; defaults unset => byte-identical endpoint/key.
- `test_credibility_progress_log`: emits every N; 0 => silent.

## Follow-up issue (files the path to <=15 min on the shared account)
Reduce Leg B's call count by verifying only members that will RENDER (contract-
bound + top-authority unbound, ranked by the deterministic weight_mass), instead
of all ~999 claims. Faithfulness-adjacent (reorders the advisory verify) => its
own issue + gate, not this surgical diff.
