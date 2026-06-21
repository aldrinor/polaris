# Faithful Abstractive Writer — Research + Design (GitHub #1282, I-beatboth-005)

**Status:** RESEARCH + DESIGN ONLY. No source edits. Awaiting advisor + operator sign-off before any build.
**Umbrella:** #1270 (beat-both campaign). Track: UNCERTAIN (research 2026 best practice → design → review BEFORE build).
**Author:** Claude. **Date:** 2026-06-20.
**Design iter:** 2 (of the §8.3.1 5-cap). **iter-1 Codex review:** 4 × P1, all resolved IN THE DESIGN TEXT below + the §4 harness fixtures (no code yet). Resolution summary:
- **P1-1 (entailment not load-bearing):** the writer path now treats `res.judge_error` (the durable `SentenceVerification` field, provenance_generator.py:637) as a WRITER FAILURE — a transport judge-error that `PG_ENTAILMENT_JUDGE_ERROR_ADVISORY=1` keeps as `is_verified=True` is forced to `is_verified=False` by the writer-specific verify wrapper → retry → K-span. We never accept an advisory judge-error paraphrase. (§3.2a, §3.4, §4 W6.)
- **P1-2 (local-window loophole):** the writer path verifies with `allow_local_window_fallback=False` via a writer-specific verify wrapper, so a NEUTRAL/CONTRADICTED bound span can no longer pass on a same-row local window. The shared `_compose_one_basket` default (`allow_local_window_fallback=True`) stays unchanged for the K-span path — the seam is the `verify_fn` parameter. (§3.2b, §4 W7.)
- **P1-3 (numeric completeness = REQUIRED v1):** a WRITER-MODULE completeness guard (span→sentence: every substantive span numeric appears verbatim in the rewrite, else `is_verified=False`) is now required, not optional. Engine untouched — the guard lives in the writer wrapper, never in `verify_sentence_provenance`. (§3.2c, §4 W8, §5.1 RESOLVED to option (b).)
- **P1-4 (async vs sync API):** an explicit async pre-pass (`_abstractive_pre_pass`, `await`-ed in the already-async `_run_section` before `_compose_section_per_basket`) precomputes one verified draft per basket; the sync `writer_fn` reads the precomputed draft by basket key. The compose functions stay sync + unchanged. (§3.1, §3.4a.)

---

## 0. One-paragraph thesis

The "Corroborated Weighted Findings" dump — ~79% of run7's report — is produced by `build_short_member_sentence`, a deterministic span-copy stub that ships SPAN-FAITHFUL but BROKEN prose (dangling markdown link fragments, mid-document section boilerplate like "3.3 Recommender Systems", Reddit/HR chrome). It is "faithful by surrender": near-perfect citation faithfulness, near-zero readability/synthesis → it kills DRB-II coverage/analysis and readability. The fix is **surgical** (§-1.3): the `writer_fn → strict_verify → verbatim-fallback` loop in `_compose_one_basket` ALREADY EXISTS and the stub is ALREADY injected through a `writer_fn=` lambda. We replace ONLY the `writer_fn`: an LLM (GLM-5.2 via OpenRouter, env-configurable per LAW VI) rewrites each verified-span dump entry into clean declarative news-style prose carrying the EXACT canonical provenance token(s) and every numeric verbatim; each rewritten sentence is RE-RUN through the UNCHANGED `verify_sentence_provenance` (+ the existing region gate); on PASS we keep the clean prose, on FAIL we fall back to today's verbatim K-span. Default-OFF behind a new flag; byte-identical when off. No new model class, no faithfulness-engine change.

---

## 1. 2026 research findings (FRONTIER-TECH mandate: dated, primary-source, ≥2024 adopted)

Method note (LAW III): WebSearch was intermittently unavailable; sources below were retrieved and confirmed via the arXiv API + arXiv abstract pages (primary source) and dated from the abstract metadata. Each adopted idea is tagged PROVEN vs PATTERN-INSPIRATION.

### Adopted (2024–2026, in-window)

1. **Schreieder, Schopf, Färber — "Attribution, Citation, and Quotation: A Survey of Evidence-based Text Generation with LLMs."** arXiv:2508.15396, v1 2025-08-21, v2 2026-04-16. https://arxiv.org/abs/2508.15396
   - *Adopted idea:* the three evidence-based-generation modes (attribution / citation / quotation) form a faithfulness spectrum; QUOTATION (verbatim extraction) is the strongest-grounded form, citation+attribution add fluency at the cost of a verification burden. Our design sits deliberately at "attributable rewrite with a quotation FALLBACK": rewrite for fluency, but if the rewrite cannot be re-verified, degrade to the quotation (verbatim K-span) that is grounded by construction.
   - *Honest caveat (LAW III, corrects the codebase docstring):* the survey is a taxonomy/evaluation-practice synthesis over 134 papers and 300 metrics. My WebFetch of the abstract could NOT confirm it makes the specific normative claim "quotation is faithful-by-construction." The existing `verified_compose.py` docstring asserts that with an inline `arXiv:2508.15396` cite — that attribution is STRONGER than the abstract supports. The faithful-by-construction property of OUR K-span fallback rests on the deterministic argument (a verbatim substring re-passes strict_verify trivially), NOT on this survey. Treat the survey as taxonomy support, not as the proof. **PROVEN (taxonomy); the normative claim is UNVERIFIED.**

2. **"GenerationPrograms: Fine-grained Attribution with Executable Programs."** arXiv:2506.14580, 2025-06-17. https://arxiv.org/abs/2506.14580
   - *Adopted idea:* decompose generation into (a) a PLAN over evidence then (b) an EXECUTION that emits attributed text, so every output unit traces to a specific evidence operation. Our analog: the basket IS the plan (its verified SUPPORTS members are the operands); the LLM writer EXECUTES a constrained "rephrase these verified spans into one declarative sentence, carry their tokens" operation. The decompose-plan-then-attribute shape is why per-sentence re-verification is tractable. **PROVEN (in-window).**

3. **"A review of faithfulness metrics for hallucination assessment in Large Language Models."** arXiv:2501.00269, 2025-01. https://arxiv.org/abs/2501.00269
   - *Adopted idea:* faithfulness is multi-axis — entailment (NLI) and fact-overlap are complementary, neither alone is sufficient. This directly motivates the design's reliance on the ENTAILMENT leg (`PG_STRICT_VERIFY_ENTAILMENT=enforce`) as the SEMANTIC gate on a paraphrase, with numeric-match + content-overlap as the SYNTACTIC floor (see §3.4 / §4). **PROVEN (in-window, used as the "why entailment is load-bearing for paraphrase" citation).**

### Lineage / pattern-inspiration ONLY (pre-2024 — cited for provenance, NOT as frontier adoption per the mandate)

4. **RARR — "Researching and Revising What Language Models Say."** arXiv:2210.08726, 2022-10-17. https://arxiv.org/abs/2210.08726
   - The canonical generate-then-RESEARCH-then-REVISE loop: post-edit unsupported content while PRESERVING the original output. Our rewrite-then-RE-VERIFY-then-fallback is the same family with one hard difference: RARR revises toward attribution and trusts the revision; WE re-run the UNCHANGED deterministic verifier and DROP-to-quotation on any failure. **PATTERN-INSPIRATION (pre-window) — not counted as a 2026 adoption.**

5. **"Think&Cite: Attributed Text Generation with Self-Guided Tree Search."** arXiv:2412.14860, 2024-12-19. (Borderline window.) https://arxiv.org/abs/2412.14860
   - Frames attributed generation as search with a per-step "attribution reward." We do NOT adopt the tree search (cost-prohibitive at ~hundreds of baskets); we adopt only the principle that each emitted unit must clear an attribution check before it is kept. **PATTERN-INSPIRATION.**

6. **"Localizing Factual Inconsistencies in Attributable Text Generation" (QASemConsistency).** arXiv:2410.07473, 2024-10-09. https://arxiv.org/abs/2410.07473
   - Fine-grained (QA-decomposed) localization of hallucination. Inspiration for the numeric-completeness concern (now RESOLVED §5.1 / P1-3): the bare per-sentence engine gate is coarser than QA-decomposition and does not catch a DROPPED source numeric — closed for the writer path by the writer-module completeness guard (§3.2c). **PATTERN-INSPIRATION.**

**Net frontier finding:** the 2026 consensus is *generate-then-verify with a verbatim/quotation safety net*, where verification is multi-axis (entailment + fact/numeric overlap). POLARIS already implements the strongest version of this (a deterministic span verifier + a quotation fallback); the only missing piece is the FLUENT writer in front of it. The design adds exactly that and nothing else.

---

## 2. Current-writer code map (file:line, read-only)

### 2.1 The broken stub
`src/polaris_graph/generator/verified_compose.py:191-218` — `build_short_member_sentence(basket, evidence_pool) -> str`.
It takes the FIRST sentence of the basket's strongest isolated-`SUPPORTS` member's verified span, tags it with that member's REAL global offsets, returns a verbatim PREFIX of the span. The module docstring itself calls it a "RENDER PROBE … DETERMINISTIC, NO-LLM short writer" whose purpose was to PROBE the render path before "the real PR-c writer." It was never meant to be the production writer.

### 2.2 How the broken prose reaches the report (the dump render)
`src/polaris_graph/generator/multi_section_generator.py:3910-3942` — the `_verified_compose_enabled()` branch of `_run_section`:
```
3925  from src.polaris_graph.generator.verified_compose import (
3926      build_short_member_sentence as _vc_short_writer,
3932  _vc_composed = _compose_section_per_basket(
3933      _vc_baskets, evidence_pool,
3934      writer_fn=lambda _b, _p: _vc_short_writer(_b, evidence_pool), verify_fn=_vc_verify,
3935  )
3936  raw = "\n".join(c for c in _vc_composed if c and c.strip())
```
The stub is ALREADY swapped in via a `writer_fn=` lambda. The raw draft then flows through the UNCHANGED `_rewrite_draft_with_spans` + strict_verify tail (multi_section_generator.py:7234), exactly like every other section.

### 2.3 The verified-span / verbatim fallback that exists today (the analog to replicate)
- `src/polaris_graph/generator/verified_compose.py:162-188` — `build_verified_span_draft(basket, evidence_pool)` — the basket-id-bound VERBATIM K-span fallback (strongest `SUPPORTS` member's `direct_quote`, per-sentence units, each tagged with the member's own global-offset token). This IS today's verbatim fallback and STAYS the fallback.
- `src/polaris_graph/generator/verified_compose.py:228-267` — `_compose_one_basket(...)` — the loop we plug into: `writer_fn` drafts → `split_into_sentences` → per-sentence `verify_fn` (strict_verify) against the BASKET-SCOPED pool → `_tokens_within_basket_regions` region gate → keep passing sentences; on the FIRST failure FALL BACK to `build_verified_span_draft`; if none, `_insufficient_evidence_disclosure`. **This is the contract we reuse unchanged.**
- `src/polaris_graph/generator/verified_compose.py:397-412` — `_compose_section_per_basket(...)` — iterates baskets, calls `_compose_one_basket` per basket. Unchanged.

### 2.4 The strict_verify entrypoint (UNCHANGED — the only hard gate)
`src/polaris_graph/generator/provenance_generator.py:1765-1772`:
```
def verify_sentence_provenance(sentence, evidence_pool, *, require_number_match=True,
    quantified_models=None, allow_local_window_fallback=True) -> SentenceVerification
```
Checks: (1) evidence-id in pool; (2) span bounds valid; (3) every numeric IN THE SENTENCE appears in a cited span (sentence→span direction); content-word overlap ≥ `MIN_CONTENT_WORD_OVERLAP`; optional ENTAILMENT leg gated by `PG_STRICT_VERIFY_ENTAILMENT` (off|warn|enforce, default **enforce** — `src/polaris_graph/clinical_generator/strict_verify.py:26,187`). The `_compose_one_basket` loop ALSO applies `_tokens_within_basket_regions` (verified_compose.py:143-159) as a second gate.

### 2.5 The GLM-5.2 OpenRouter call pattern + env-knob convention
- LLM call pattern (canonical generator-role): `multi_section_generator.py:2748-2762`:
  ```
  client = OpenRouterClient(model=model)
  response = await client.generate(prompt=..., system=..., max_tokens=..., temperature=..., reasoning_max_tokens=...)
  ... finally: await client.close()
  ```
- GLM-5.2 slug + env-knob convention: `src/polaris_graph/generator/relevance_judge.py:70,84` — `_ENV_MODEL = "PG_RELEVANCE_MODEL"`, `_DEFAULT_MODEL = "z-ai/glm-5.2"`. Model env knobs: `openrouter_client.py:577-616` (`PG_GENERATOR_MODEL`, `PG_MIRROR_MODEL=z-ai/glm-5.1`, etc.). max_tokens/reasoning env convention: `evidence_distiller.py:128,157` (`_reduce_max_tokens`, `PG_DISTILL_REDUCE_REASONING_TOKENS`), `multi_section_generator.py:447` (`PG_SECTION_MAX_TOKENS`).

### 2.6 The broken prose, quoted (motivating evidence — run7 render-probe output)
From `outputs/prc_render_probe/workforce/drb_72_ai_labor/report.md:61` ff, the `### Corroborated Weighted Findings` block:
> ### Corroborated Weighted Findings
>
> Six Facts about the Recent Employment Effects of Artificial Intelligence](https://digitaleconomy.stanford.edu/publications/canaries-in-the-coal-mine/)," provided some of the earliest large-scale evidence … [11] … **3.3 Recommender Systems** Recommender Systems (RS) represent another major application area … [12] … **2.1 Research problem** How does the implementation of AI influence job structures …

Note the dangling markdown-link fragment (`...Artificial Intelligence](https://...)`), the orphaned section numbers (`3.3`, `2.1`), and the HR-paper chrome — span-faithful, unreadable. This is exactly what the stub emits because it copies the strongest member's raw span prefix verbatim.

---

## 3. The buildable design

### 3.1 Surface area (minimal — §-1.3 surgical)
All NEW code lives in a NEW module `src/polaris_graph/generator/abstractive_writer.py` (one responsibility, §4.2). It exports four things: (a) an ASYNC pre-pass `_abstractive_pre_pass(baskets, evidence_pool) -> dict[basket_key -> draft_str]`, (b) the async per-basket LLM writer call it drives, (c) a SYNC `make_abstractive_writer_fn(precomputed)` that returns the `writer_fn` the compose loop reads, (d) a SYNC `make_writer_verify_fn(base_verify)` that returns the writer-specific verify wrapper (P1-1/P1-2/P1-3 seam). Plus the flag `PG_ABSTRACTIVE_WRITER`, the model knob `PG_ABSTRACTIVE_WRITER_MODEL` (default = the GENERATOR-role alias from `polaris_runtime_lock.yaml`, §5.6 / Q6 — env-overridable per LAW VI), and the bound knobs `PG_ABSTRACTIVE_WRITER_MAX_RETRIES`, `PG_ABSTRACTIVE_WRITER_MAX_TOKENS`, `PG_ABSTRACTIVE_WRITER_CONCURRENCY`.

- **NEW:** the four exports above. The writer-specific verify wrapper is pure (verify-only, no retry, no LLM); the retry lives in the async pre-pass (§3.4a).
- **CHANGED (one branch only):** the `_verified_compose_enabled()` branch of `_run_section` (`multi_section_generator.py:3910-3942`). When `PG_ABSTRACTIVE_WRITER` is ON, BEFORE the `_compose_section_per_basket(...)` call it `await`s `_abstractive_pre_pass(_vc_baskets, evidence_pool)` (legal — `_run_section` is already async; line 3944 `await _call_section` confirms), then passes `writer_fn=make_abstractive_writer_fn(precomputed)` and `verify_fn=make_writer_verify_fn(_vc_verify)` instead of the stub lambda + bare `_vc_verify`. OFF ⇒ the existing `build_short_member_sentence` lambda + bare `_vc_verify` are byte-identical.
- **UNCHANGED:** `verify_sentence_provenance`, NLI/entailment, 4-role D8, provenance, `build_verified_span_draft`, `_compose_one_basket` (still sync; still receives `writer_fn`+`verify_fn` as params and is the authoritative re-verify + partial-fallback gate), `_compose_section_per_basket` (still sync), `_tokens_within_basket_regions`, the region gate, the section tail. The wrapper is injected THROUGH the existing `verify_fn` parameter — `_compose_one_basket` never learns it is wrapped.

### 3.2 The token-attachment mechanism (THE crux — how a paraphrase passes the UNCHANGED verifier)
An LLM paraphrase is NOT a substring of the span, so the writer CANNOT compute valid byte offsets — and must never try (an invented offset would be an unverified claim). Resolution:

**The writer is GIVEN the canonical token and instructed to APPEND IT VERBATIM; it never invents offsets.** For each basket, `_compose_one_basket` already builds the BASKET-SCOPED pool from the SUPPORTS-only members. The writer prompt is constructed from those members, and for each member it is given the member's exact canonical token `[#ev:<id>:<start>-<end>]` (the SAME token `build_verified_span_draft` would emit — computed deterministically by `_member_global_span`, verified_compose.py:104-122). The writer's contract: produce ONE declarative sentence that rephrases the member's verified span and ends with that exact token, copied character-for-character. The offsets therefore stay anchored to the member's real verified span; strict_verify re-resolves the token against the GLOBAL row exactly as for the K-span.

Why this is safe and not a loophole:
- The numeric check (provenance_generator.py:1969-2002) re-confirms every numeric in the PARAPHRASE is in the cited span. A fabricated/altered numeric ⇒ `number_not_in_any_cited_span` ⇒ FAIL ⇒ fallback (empirically confirmed, §4 fixture C).
- The content-overlap floor + the ENTAILMENT leg (provenance_generator.py:2011-2049, gated `PG_STRICT_VERIFY_ENTAILMENT=enforce`) re-confirm the paraphrase still ENTAILS from the span. A fluent paraphrase that DISTORTS meaning is caught here — this is the load-bearing semantic gate for abstraction (arXiv:2501.00269). **The run MUST set `PG_STRICT_VERIFY_ENTAILMENT=enforce` for the abstractive writer to be safe; with entailment OFF, a meaning-distorting paraphrase clearing the ≥2-content-word floor would PASS (§4 fixture D). This is stated as a binding precondition, not an assumption.**
- The region gate `_tokens_within_basket_regions` re-confirms the appended token's [start,end] lands inside the member's own verified-span region — so a copied-but-wrong token, or a foreign basket's token, fails closed to the K-span (the existing P1-1/P1-2 contract, untouched).

**Optional re-anchor:** `PG_SPAN_RESOLVER` / `_try_reanchor` (provenance_generator.py:1841) can re-point a token to the genuinely-entailing window. We do NOT depend on it; the append-the-canonical-token mechanism is the primary path and works with the resolver OFF. If the resolver is ON it only tightens.

#### 3.2a P1-1 — entailment IS load-bearing on the writer path (judge-error = WRITER FAILURE)

The shared `verify_sentence_provenance` keeps a TRANSPORT entailment judge-error as a soft pass under `PG_ENTAILMENT_JUDGE_ERROR_ADVISORY=1` (the default, I-arch-010 FIX-1): when the judge times out / hangs / returns blank, the verdict is surfaced as `(ENTAILED, "judge_error: ...")`, the result keeps `is_verified=True`, and `SentenceVerification.judge_error=True` is set as the durable machine-readable marker (provenance_generator.py:637, 2329-2347; the soft-warning `entailment_unverified_judge_error:<ev_ids>` is the human-readable twin). That advisory keep is CORRECT for the deterministic K-span path (a verbatim substring is grounded by construction; an unreachable judge must not strand it). It is WRONG for an ABSTRACTIVE paraphrase: a paraphrase's only semantic guarantee IS the entailment leg, so accepting it on an *un-run* judge would ship un-entailment-checked rewritten prose — the exact "entailment not load-bearing" hole P1-1 names.

**Fix — the writer-specific verify wrapper inspects the field and fails the sentence closed.** `make_writer_verify_fn(base_verify)` returns a callable used as `_compose_one_basket`'s `verify_fn`. After calling the REAL verifier it inspects the returned `SentenceVerification`:

```
res = base_verify(sentence, scoped_pool, allow_local_window_fallback=False, ...)   # P1-2, see 3.2b
if getattr(res, "judge_error", False):                                             # P1-1: durable field, not string-match
    res = dataclasses.replace(res, is_verified=False,
                              failure_reasons=[*res.failure_reasons, "writer_judge_error_fail_closed"])
```

We read the `judge_error` BOOL FIELD (not the `soft_warnings` string) because the field is the canonical marker (its own comment: "the durable machine-readable marker"). Forcing `is_verified=False` makes the keep-condition at `_compose_one_basket` (verified_compose.py:253 — `bool(res.is_verified) and _tokens_within_basket_regions(...)`) fail → the basket exhausts the writer retry (§3.4a) → on continued failure falls back to the verbatim K-span. The K-span is then re-verified by the SHARED bare `verify_fn` path's semantics (judge-error advisory-kept, correct for a substring). **Net: an advisory judge-error never ships as a writer paraphrase; it only ever ships as the grounded-by-construction K-span.** The engine is untouched — the demotion is in the wrapper, not in `verify_sentence_provenance`.

(Q5 call-time tie-in, §5.5: this per-call `judge_error` check IS the call-time enforcement of entailment for the writer path. The env-activation guard — refuse to activate unless `PG_STRICT_VERIFY_ENTAILMENT=enforce` — is necessary but NOT sufficient, because env-enforce still permits the advisory judge-error keep; the wrapper's `judge_error` demotion is what closes that residual on the writer path.)

#### 3.2b P1-2 — close the local-window loophole on the writer path (`allow_local_window_fallback=False`)

`_compose_one_basket` calls `verify_fn(sentence, scoped_pool)` with only two positional args (verified_compose.py:245), so the bare verifier runs with its default `allow_local_window_fallback=True` (provenance_generator.py:1765-1772). With local-window fallback ON, a sentence whose bound span is NEUTRAL/CONTRADICTED for the whole span can still PASS by entailing a SAME-ROW local window — acceptable for the deterministic K-span (its text is a substring of the bound span, so the window it entails is its own span) but a real loophole for a paraphrase (the writer could anchor to a token whose claim is only locally true).

**Fix — the writer wrapper passes `allow_local_window_fallback=False`** (the `base_verify(..., allow_local_window_fallback=False, ...)` call shown in §3.2a). The paraphrase must entail the FULL bound span the writer was told to rephrase, not a cherry-picked sub-window. This is intentionally STRICTER than the K-span path; a paraphrase that only entailed a local window fails closed → retry → K-span. The region gate `_tokens_within_basket_regions` (already run by the loop) is the second, independent guard (the token must also land inside this basket's own member region); `allow_local_window_fallback=False` is the belt to its suspenders.

**The seam (why the shared default stays untouched):** the flag is a per-call kwarg, not a module global. The K-span path keeps calling the bare `_vc_verify` (default `True`); ONLY the writer path injects `make_writer_verify_fn(_vc_verify)` (which pins `False`). `_compose_one_basket`'s signature and body are byte-identical — it just receives a different `verify_fn`. No shared default changes; the K-span behaviour is preserved exactly.

#### 3.2c P1-3 — numeric COMPLETENESS guard (span→sentence), REQUIRED v1, engine untouched

The shared verifier's numeric check is ONE-DIRECTIONAL (sentence→span: every numeric IN the sentence must appear in a cited span). It catches a FABRICATED numeric but NOT a DROPPED span numeric — a paraphrase that silently omits a dose/percent/HR PASSES. In clinical context (§-1.1) a dropped dose is a real harm. P1-1 review escalates this from "optional" (the iter-1 §5.1 open question) to **REQUIRED for v1**.

**Fix — a writer-MODULE completeness guard inside `make_writer_verify_fn`, AFTER the base verifier passes:**

```
# span→sentence completeness (the reverse direction the engine does NOT check)
span_numerics = _substantive_numerics(cited_span_text_for(res.tokens, scoped_pool))   # writer-module helper
if not all(_numeral_appears_verbatim(n, sentence) for n in span_numerics):
    res = dataclasses.replace(res, is_verified=False,
                              failure_reasons=[*res.failure_reasons, "writer_numeric_dropped"])
```

`_substantive_numerics` reuses the engine's OWN substantive-numeral definition (the decimal/percent/dose pattern at provenance_generator.py:708-711 + the study-marker exclusions) so "substantive" means the same thing in both directions — the guard never demands study-marker integers the engine itself ignores. The check runs ONLY for the writer path (it is in `make_writer_verify_fn`, never in `verify_sentence_provenance`), so the engine and the K-span path are byte-identical. A drop ⇒ `is_verified=False` ⇒ retry (with the failure reason "you dropped numeric X from the span; carry every span numeric verbatim") ⇒ K-span fallback (the K-span is the verbatim span, so it is complete by construction). This makes numeric completeness a verified guarantee for v1, not a prompt-only hope.

**The section-TAIL hop survives the paraphrase (CONFIRMED empirically, advisor catch 2026-06-20).** After `_compose_section_per_basket`, the composed draft becomes `raw` (multi_section_generator.py:3936) and flows through the section tail `_rewrite_draft_with_spans` (live_deepseek_generator.py:352-403) + strict_verify — this tail, NOT the internal `_compose_one_basket` loop, is the gate that decides what actually renders. The crux: the stub renders fine because its text IS the span (a verbatim substring); a PARAPHRASE is NOT a substring. Read of `_rewrite_draft_with_spans` (lines 365-401) shows it ONLY touches sentences carrying a LEGACY `[ev_XXX]` marker (`_EV_MARKER_RE`); a sentence with **no legacy marker is passed through UNCHANGED** (lines 366-369). Our writer emits the CANONICAL `[#ev:<id>:<start>-<end>]` token (NOT a legacy `[ev_XXX]` marker), so the tail passes the paraphrase through untouched to strict_verify with the token intact. **Verified by running it 2026-06-20:** an already-`[#ev:ev1:0-97]`-tokened paraphrase returns `passed_through_unchanged=True, converted=0, unverifiable=0` — it survives the tail verbatim and is then re-verified by the unchanged strict_verify exactly as the K-span is. (Alternative mechanism: if the writer instead emitted legacy `[ev1]` markers, the tail RE-ANCHORS them via the paraphrase-tolerant `_find_best_span_for_sentence` content-aware finder — `converted=1` — also viable. We choose the canonical-token mechanism because it is offset-exact to the member's verified span and does not depend on the finder picking the right window.) **The feature does NOT silently no-op at the tail.** The harness (§4) MUST assert the paraphrase survives to the rendered `raw` AFTER `_rewrite_draft_with_spans`, not only to the compose-loop output — closing the config-fired-not-output-fired gap.

### 3.3 The prompt contract (writer system + user)
Plain declarative news-style per the operator's standard (`feedback_plain_declarative_writing_standard_2026_06_18.md`). The contract:
- **MUST** rephrase ONLY the verified span(s) provided — assert no fact not in a provided span (a fabrication is caught by re-verify, but the prompt discourages it to keep the fallback rate low).
- **MUST** carry every numeric (decimal, percent, integer, dose) VERBATIM from the span — copy digits exactly, never round, never convert units.
- **MUST** end each sentence with the exact provenance token supplied for the member it rephrases, copied character-for-character. Never invent or edit a token.
- **MUST** be plain declarative sentences: subject-verb-object, name the specific finding/number/actor. BANNED: markdown, links, bullet/heading fragments, section numbers, "this study"/"the framework" academic chrome, caption fragments, folksy or clever phrasing.
- **MUST** output exactly one sentence per member span (so per-sentence re-verify is 1:1 and the fallback is per-member, not whole-basket).
- One member ⇒ one sentence; N members in a basket ⇒ N sentences (one per member). The per-cluster co-located multi-cited sentence via the EXISTING `compose_multicited_sentence` path is a DEFERRED follow-up (§5.3 resolution: v1 is per-basket).

### 3.4 The re-verify loop + retry-then-fallback (faithful-by-construction)
Faithful-by-construction is split across TWO seams: the async pre-pass (§3.4a) does best-effort prose generation + the bounded retry; `_compose_one_basket` (UNCHANGED) remains the AUTHORITATIVE re-verify + fallback gate. The pre-pass never decides what renders — it only proposes a draft; the unchanged loop verifies it and falls back if it fails.

The per-basket lifecycle:

1. **Pre-pass (async, §3.4a):** for the basket, call the LLM writer (attempt 1). Verify the candidate WITH the writer wrapper (§3.2a/b/c — `allow_local_window_fallback=False`, `judge_error`→fail, numeric-completeness→fail) against the basket-scoped pool + region gate.
2. If ALL sentences pass ⇒ that draft is the precomputed draft for the basket (done).
3. If ANY sentence fails ⇒ **retry the LLM writer up to `PG_ABSTRACTIVE_WRITER_MAX_RETRIES` times** (default **1** → 2 total attempts, §5.2/Q2), feeding the specific wrapper failure reason back ("you dropped numeric X from the span; carry every span numeric verbatim" / "your token did not match; append the supplied token exactly" / "your sentence did not entail the full span"). RARR-style revise, bounded.
4. If still failing after the retry budget ⇒ the precomputed draft for the basket is left as the writer's last (failing) attempt — and the SYNC compose loop, on re-verifying it, falls back to the basket's verbatim K-span. (The pre-pass does NOT itself emit the K-span; it hands the loop the prose and lets the unchanged loop be the single fallback authority.)
5. **Compose loop (sync, UNCHANGED):** `_compose_one_basket` re-verifies the precomputed draft with the SAME writer wrapper (`verify_fn=make_writer_verify_fn(_vc_verify)`), keeps passing sentences, and on the first failing sentence falls back to `build_verified_span_draft`. Never empty; never stranded; always-release.

#### 3.4a P1-4 — the async-vs-sync adapter (async pre-pass + sync `writer_fn`)

The writer is async (OpenRouter, §2.5) but `_compose_one_basket` calls `writer_fn(basket, scoped_pool)` SYNCHRONOUSLY (verified_compose.py:241). Making the compose functions async would touch the engine (rejected — §-1.3 surgical). Resolution: **an async PRE-PASS computes every basket's draft up front; the sync `writer_fn` is a pure dict lookup.**

- `_run_section` is ALREADY async (it `await`s `_call_section` at multi_section_generator.py:3944), so the pre-pass is `await`-able at the exact call site, BEFORE `_compose_section_per_basket`:
  ```
  precomputed = await _abstractive_pre_pass(_vc_baskets, evidence_pool)   # async: LLM + retry, bounded-parallel
  _vc_composed = _compose_section_per_basket(
      _vc_baskets, evidence_pool,
      writer_fn=make_abstractive_writer_fn(precomputed),     # SYNC: precomputed[_basket_key(b)] lookup
      verify_fn=make_writer_verify_fn(_vc_verify),           # SYNC: §3.2 wrapper
  )
  ```
- `_abstractive_pre_pass` runs the writer calls + retries across baskets under a `PG_ABSTRACTIVE_WRITER_CONCURRENCY` semaphore (default 8, §3.5) with a per-call total deadline (force-close → that basket's draft is left failing → K-span). It is keyed by a stable `_basket_key(basket)` (the basket's canonical id) so the sync lookup is deterministic.
- `make_abstractive_writer_fn(precomputed)` returns `lambda b, _p: precomputed.get(_basket_key(b), "")` — a MISSING key returns `""`, which the loop treats as a writer-empty basket ⇒ K-span fallback (never a crash). So a pre-pass that skipped/failed a basket degrades safely.

This is concrete enough to execute: no async creeps into `_compose_one_basket`/`_compose_section_per_basket`; the single `await` lives at the already-async section call site.

#### 3.4b Granularity decision (CORRECTED — the loop ALREADY does PARTIAL keep)

Retry/fallback granularity is PER BASKET (matching `_compose_one_basket`). **Correction to the iter-1 text (Codex P1 fold-in + advisor catch):** the claim that we "do NOT mix a half-rewritten basket" was FACTUALLY WRONG against the code. `_compose_one_basket` ALREADY does PARTIAL keep — verified_compose.py:261-265 keeps the sentences that passed BEFORE the first failing sentence and then APPENDS the verbatim K-span ("never lose already-verified prose"). Because the engine is untouched, the design MUST match that behavior, not contradict it.

**Q3 resolution (§5.3) — per-basket, PARTIAL fallback (all-or-partial DEFINED explicitly):**
- The pre-pass produces ONE draft per basket (N sentences for N SUPPORTS members).
- The sync loop verifies sentences in order. Sentences passing before the first failure are KEPT; at the first failing sentence the loop appends the basket's verbatim K-span and stops (verified_compose.py:258-265).
- **Consequence (disclosed, not "fixed"):** the appended strongest-member K-span MAY re-state a member already covered by a kept paraphrase. We DISCLOSE this rather than dedup it, because deduping the kept-prose-vs-K-span overlap would require changing `_compose_one_basket` (an engine change — forbidden here). The overlap is a minor redundancy, never a faithfulness or completeness loss (both halves are verified). If a future issue wants to dedup, it is a separate, engine-touching PR.
- All-passing basket ⇒ pure clean prose (no K-span). All-failing first sentence ⇒ pure K-span. Partial ⇒ kept prose + K-span. This is exactly the existing contract; the writer adds only the upstream retry.

### 3.5 Cost / latency bound (load-bearing — the dump is ~79%, hundreds of baskets)
The driver is the per-basket LLM call COUNT. Bound it:
- **Bounded parallelism:** compose baskets concurrently with a semaphore `PG_ABSTRACTIVE_WRITER_CONCURRENCY` (proposed default **8**, matching the campaign's bounded-verify fan-out), reusing the campaign's MAX-PARALLELISM directive. Each call is small (1 span in, 1 sentence out) so latency per call is low.
- **Per-call token budget:** small `max_tokens` (proposed `PG_ABSTRACTIVE_WRITER_MAX_TOKENS` default ~2048) + a modest reasoning budget — this is a rephrase, not a section essay; a generous-but-bounded cap per the token-MAX governance (a cap is free insurance, billed by actual usage).
- **Retry amplification:** worst case = `(1 + MAX_RETRIES) × baskets` calls. With default retries=1 (§5.2 resolution) that is ≤2× baskets. Per-CLUSTER granularity (the §5.3 deferred follow-up) would reduce the call count by the corroboration factor (one call per cluster instead of one per member) — the main future cost lever; v1 is per-basket.
- **Hard wall:** a per-call total deadline (the campaign's proven force-close pattern) so a hung judge/writer socket FAILS LOUD to the K-span, never hangs the run.

### 3.6 Default-OFF / byte-identical guarantee + fail-closed activation
`PG_ABSTRACTIVE_WRITER` unset/`0`/`off` ⇒ the `multi_section_generator.py:3934` lambda keeps `build_short_member_sentence` and the bare `_vc_verify`; the new module is never imported on the hot path; the output is byte-identical to today. The flag is the ONLY thing that activates the LLM writer (LAW VI).

**Fail-closed activation guard (§5.5 / Q5, resolved YES).** When `PG_ABSTRACTIVE_WRITER` is ON, the writer module REFUSES to activate (raises, fail-LOUD per LAW II — no silent downgrade) unless `PG_STRICT_VERIFY_ENTAILMENT` resolves to `enforce` (read via the engine's own `_entailment_mode()`, strict_verify.py:176). Rationale: the writer's ONLY semantic guarantee for a paraphrase is the entailment leg (§3.2/§3.2a); activating it with entailment `off`/`warn` would ship un-entailment-checked rewritten prose. The env guard is the ACTIVATION precondition; the per-call `judge_error` demotion (§3.2a) is the per-sentence call-time enforcement — env-enforce is necessary but not sufficient because it still permits the advisory judge-error keep, which the wrapper closes. Both checks are required.

**Model lock (§5.6 / Q6).** `PG_ABSTRACTIVE_WRITER_MODEL` is NOT a free default. It defaults to the GENERATOR-role model resolved from `config/architecture/polaris_runtime_lock.yaml` (the writer is a generator-role call, §9.1.8) — i.e. it ALIASES the locked generator slug rather than hardcoding `z-ai/glm-5.2`. The campaign's all-GLM-5.2 single-family override (if in force) flows through the lock, not through this knob. Token caps (`PG_ABSTRACTIVE_WRITER_MAX_TOKENS`, reasoning budget) go to the model's REAL OpenRouter limit reconciled against the serving provider cap, per the §9.1.8 token-MAX governance / conformance — never a guessed value. The lock-vs-all-GLM-5.2 family decision belongs to the lock owner, not this design.

---

## 4. The §-1.4 fail-loud replay-harness shape

New harness `scripts/iarch_beatboth005_abstractive_writer_replay_harness.py`, matching the existing PR-c harness convention (`scripts/iarch011_prc_verified_compose_replay_harness.py`): the LLM writer is FAKE/injected (no network, no spend); strict_verify is the REAL production `verify_sentence_provenance`; the writer-specific verify wrapper (`make_writer_verify_fn`, §3.2) is the REAL wrapper under test; runs on a REAL banked `corpus_snapshot.json` under `PG_PRD_REQUIRE_REAL=1` (a missing corpus FAILS, never silently synthetic); exits non-zero naming the first failure. It folds into `scripts/iarch011_composition_replay_harness.py` as a new component.

**Two injection seams (the harness fakes the WRITER and, for W6 only, the JUDGE — everything else is real).** The writer is always faked (a fixture-controlled string, no network). For W6 (judge-error-advisory, P1-1) a transport `judge_error` cannot arise offline — the entailment judge would have to time out / blank — so W6 ALSO injects a fake entailment judge that returns `(ENTAILED, "judge_error: injected")` under `PG_STRICT_VERIFY_ENTAILMENT=enforce` + `PG_ENTAILMENT_JUDGE_ERROR_ADVISORY=1`, exercising the REAL `verify_sentence_provenance` advisory-keep path (it sets `is_verified=True, judge_error=True`) and then the REAL writer wrapper (which must flip it to `is_verified=False` → K-span). W4 (meaning-distortion) is DISTINCT: it injects NO judge fake — it relies on the real entailment leg returning NEUTRAL/CONTRADICTED on a genuinely-distorted paraphrase under `enforce`. Keep both fixtures; they exercise different mechanisms (transport failure vs semantic failure).

**MUST exercise the TAIL hop, not just the compose loop (advisor catch — the config-fired-not-output-fired trap).** The PR-c harness convention tests `_compose_section_per_basket` in isolation; that is INSUFFICIENT here because a paraphrase (unlike the verbatim stub) is not a substring of its span, so the real render gate is the section tail `_rewrite_draft_with_spans` + strict_verify (multi_section_generator.py:3936→7234), not the internal loop. The harness MUST run each fixture's compose output THROUGH `_rewrite_draft_with_spans(raw, evidence_pool)` and assert the post-tail text, so a fixture that passes the loop but is dropped/re-anchored-away at the tail FAILS LOUD. (Empirically the canonical-token paraphrase survives the tail unchanged — §3.2 — but the harness must PROVE that on the real corpus, not assume it.)

**The fixtures encode the EMPIRICALLY-VERIFIED strict_verify directionality (tested 2026-06-20, §0 of this note's evidence):**

| # | Fake writer returns | Expected | Why |
|---|---|---|---|
| W1 | a clean faithful paraphrase carrying every span numeric + the supplied verbatim token | **PASS → clean prose renders** | the happy path; effect ACTUALLY APPEARS in output |
| W2 | a paraphrase with a **FABRICATED/ALTERED** numeric (e.g. "27%" when the span says "13%") | **FAIL strict_verify → verbatim K-span fallback fires** | `number_not_in_any_cited_span` (confirmed: fixture C is_verified=False) |
| W3 | a paraphrase that **drops/garbles the citation token** (or appends a FOREIGN basket's token) | **FAIL region gate → K-span fallback fires** | `no_provenance_token` / `_tokens_within_basket_regions` False (confirmed) |
| W4 | a fluent paraphrase that **DISTORTS meaning** but keeps ≥2 content words + a real token, run under `PG_STRICT_VERIFY_ENTAILMENT=enforce` (NO judge fake — the real entailment leg returns NEUTRAL/CONTRADICTED) | **FAIL entailment → K-span fallback fires** | the semantic gate; proves entailment-enforce is load-bearing for abstraction (TRANSPORT-error case is W6) |
| W5 | garbage / empty | **K-span fallback fires; never empty** | always-release / never-strand |
| **W6** (P1-1, NEW) | a clean faithful paraphrase **+ a fake entailment judge injected to return `(ENTAILED, "judge_error: injected")`** under `PG_STRICT_VERIFY_ENTAILMENT=enforce` + `PG_ENTAILMENT_JUDGE_ERROR_ADVISORY=1` | **the REAL verifier advisory-keeps (`is_verified=True, judge_error=True`); the REAL writer wrapper FLIPS it to `is_verified=False` → K-span fallback fires** | proves a TRANSPORT judge-error is a WRITER FAILURE, not an accepted advisory paraphrase (§3.2a). Must fire THROUGH `make_writer_verify_fn`, not by reading env. |
| **W7** (P1-2, NEW) | a paraphrase that **entails only a same-row LOCAL WINDOW** of the bound span but NOT the full span (NEUTRAL/CONTRADICTED whole-span) | **PASS under `allow_local_window_fallback=True` (proving the loophole exists) but FAIL under the writer wrapper's `allow_local_window_fallback=False` → K-span fallback fires** | proves the writer path closes the local-window loophole (§3.2b). The fixture asserts BOTH directions to show the wrapper is what closes it. |
| **W8** (P1-3, NEW) | a fluent paraphrase that is sentence→span clean (every sentence numeric is in-span) **but DROPS a substantive span numeric** (e.g. span has "13% and 27%", rewrite states only "13%") | **PASS the bare engine (one-directional) but FAIL the writer wrapper's completeness guard (`writer_numeric_dropped`) → retry → K-span fallback fires** | proves numeric COMPLETENESS is REQUIRED v1 and fires THROUGH `_rewrite_draft_with_spans` to the rendered output, not just the loop (§3.2c). The K-span is complete by construction. |

**Harness honesty — CORRECTED (P1-3 fold-in, supersedes the iter-1 note).** The iter-1 design said a dropped-source-numeric fixture "does NOT fail and we do NOT assert it." That was correct ONLY for the bare engine (the engine's numeric check is one-directional, sentence→span). P1-1 review escalated numeric completeness to REQUIRED v1, so the writer WRAPPER now adds the reverse (span→sentence) check (§3.2c). Fixture **W8 therefore ASSERTS the dropped-numeric case AS A FAILURE — through the wrapper, not the engine.** The engine stays one-directional and untouched; the new completeness contract is the writer wrapper's, and W8 proves it fires end-to-end through `_rewrite_draft_with_spans`. (The honest distinction remains: the BARE engine still cannot catch a dropped numeric; we catch it in the writer module, leaving the engine byte-identical.)

Harness acceptance = **the effect appears in the real output** (run THROUGH `_rewrite_draft_with_spans`, not just the compose loop — §4 above): on a real corpus, W1 yields a clean rendered sentence in the post-tail draft AND W2/W3/W4/W5/W6/W7/W8 yield the verbatim K-span (so faithfulness AND numeric-completeness hold when the writer misbehaves). The consolidated gate must FAIL LOUD (non-zero) if W1 never renders clean prose (writer silently no-ops) OR any of W2–W8 renders unverified / numeric-incomplete text.

---

## 5. Resolved questions (iter-1 open questions, closed at iter-2)

The iter-1 review's six open questions are RESOLVED below (P1-3 + the Codex open-question fold-ins). Each is now a binding design decision baked into §3/§4; only the two genuinely-external items (§5.4 scope confirm, §5.6 lock-owner family call) remain operator/owner sign-offs.

1. **§5.1 — Numeric COMPLETENESS gap → RESOLVED: option (b), REQUIRED v1 (P1-3).** The one-directional strict_verify catches a FABRICATED numeric but not a DROPPED span numeric — clinical-safety relevant (§-1.1). RESOLUTION: add the writer-MODULE completeness guard (§3.2c) — every substantive span numeric must appear verbatim in the rewrite, else `is_verified=False` → retry → K-span. It lives in `make_writer_verify_fn`, NOT in `verify_sentence_provenance`, so the engine and the K-span path stay byte-identical. This is REQUIRED for v1 (not gated on clinical-vs-not). Harness fixture **W8** proves it fires through `_rewrite_draft_with_spans`. (Was: open option (a)/(b)/(c).)

2. **§5.2 — Retry count → RESOLVED: `PG_ABSTRACTIVE_WRITER_MAX_RETRIES=1` (2 total attempts).** One bounded RARR-style revise (feeding the specific wrapper failure reason back), then K-span fallback. 1 balances prose quality against cost/latency (the retry amplifies the call count ≤2× baskets, §3.5); env-overridable to 0 (cheapest) or higher if a run wants it. The retry lives in the async pre-pass (§3.4a), never in the engine.

3. **§5.3 — Rewrite granularity → RESOLVED: per-BASKET, PARTIAL fallback explicitly DEFINED.** Per-basket matches `_compose_one_basket`. The fallback is PARTIAL, not all-or-nothing — corrected against the code (§3.4b): the loop keeps sentences passing before the first failure and appends the verbatim K-span (verified_compose.py:261-265). All-pass ⇒ pure prose; first-sentence-fail ⇒ pure K-span; partial ⇒ kept prose + K-span (the appended K-span may re-state a kept member — disclosed, not deduped, because deduping would touch the engine). Per-CLUSTER (one multi-cited sentence via the existing `compose_multicited_sentence`, verified_compose.py:350) is deferred to a follow-up that reuses F1-1 — it serves DRB-II synthesis and is the main cost lever, but it overlaps the F1-1 multicited path and the relational-quantifier guard (F1-2, deferred). v1 = per-basket.

4. **§5.4 — Dump section STRUCTURE → SCOPED OUT (operator confirm).** This issue is WRITER-PROSE ONLY (§3.3). A clean writer drops the orphaned `3.3`/`2.1` heading fragments because it rephrases the span instead of copying it; but the section HEADERS (`### Corroborated Weighted Findings`, per-source subheads) are a separate render concern in `weighted_enrichment.py`/`multi_section_generator.py` and are LEFT to a separate issue to keep the PR ≤200 LOC (§3.0 cap). **Operator: confirm the writer-only scope.**

5. **§5.5 — `PG_STRICT_VERIFY_ENTAILMENT=enforce` precondition → RESOLVED: YES, fail-closed activation guard + call-time check (Q5 fold-in).** TWO mechanisms, both required: (i) the writer module REFUSES to activate (raises, fail-LOUD) unless `_entailment_mode()` resolves `enforce` (§3.6) — the activation precondition; (ii) the per-call `judge_error` demotion in the wrapper (§3.2a) — the call-time enforcement, because env-enforce alone still permits the advisory judge-error keep. Env-check is necessary but NOT sufficient; the call-time check closes the residual. Harness fixture **W6** proves the call-time mechanism fires.

6. **§5.6 — Model lock → RESOLVED to the lock, family call deferred to the owner (Q6 fold-in).** `PG_ABSTRACTIVE_WRITER_MODEL` is NOT a free `z-ai/glm-5.2` default — it ALIASES the GENERATOR-role model resolved from `config/architecture/polaris_runtime_lock.yaml` (the writer is a generator-role call, §9.1.8), and its token caps go to the model's real OpenRouter limit reconciled against the serving-provider cap (token-MAX conformance, §3.6). The campaign's all-GLM-5.2 single-family override (if in force) flows through the LOCK, not this knob. The lock-vs-all-GLM-5.2 family decision is the lock owner's call, not this design's.

---

## 6. Faithfulness invariants (binding — restated)
- `verify_sentence_provenance` / NLI / 4-role D8 / provenance / span-grounding / `build_verified_span_draft` / the region gate / `_compose_one_basket` / `_compose_section_per_basket` are UNTOUCHED (engine byte-identical). The new behavior lives ENTIRELY in the writer module + the ONE `_run_section` branch (§3.1).
- Every abstractive rewrite is RE-RUN through the unchanged verifier + region gate; fabrication (altered numeric, wrong/missing token, meaning distortion under entailment-enforce) ⇒ verbatim K-span fallback.
- **The writer path is STRICTER than the K-span path (the four P1 closures, all in the writer wrapper / pre-pass — engine untouched):**
  - **P1-1:** a TRANSPORT entailment `judge_error` is a WRITER FAILURE — the wrapper forces `is_verified=False` → retry → K-span. An advisory judge-error never ships as a paraphrase, only ever as the grounded-by-construction K-span (§3.2a).
  - **P1-2:** the writer path verifies with `allow_local_window_fallback=False` (the K-span path keeps the `True` default via the unwrapped `verify_fn`); a NEUTRAL/CONTRADICTED bound span cannot pass on a same-row local window (§3.2b).
  - **P1-3:** numeric COMPLETENESS is REQUIRED v1 — every substantive span numeric must appear verbatim in the rewrite, else `is_verified=False` → retry → K-span. The span→sentence guard is in the writer wrapper, NOT the one-directional engine check (§3.2c). The numeric-completeness gap from iter-1 is CLOSED for the writer path.
  - **P1-4:** the async writer is adapted to the sync compose loop via an `await`-ed pre-pass at the already-async `_run_section` call site; the compose functions stay sync and unchanged (§3.4a).
- **Fail-closed activation (§3.6 / §5.5):** the writer refuses to activate unless `PG_STRICT_VERIFY_ENTAILMENT=enforce`; the per-call `judge_error` check is the call-time enforcement.
- Always-release; never strand; never empty. Default-OFF, byte-identical when off.
- NO grandfather tools; the adopted ideas are 2024–2026 frontier (§1), pre-2024 cited as lineage only.
