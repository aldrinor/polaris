# Wave-1 V30 / Gate-B retarget verdict

## Executive verdict

Wave 1 must be retargeted to the V30 contract runner, but it cannot be retargeted to
`build_slot_narrative_prompt` alone. Gate-B force-enables both V30 switches
(`scripts/dr_benchmark/run_gate_b.py:5736-5747`) and the live sweep passes the compiled
`_phase2_contract_plans` into `generate_multi_section_report`
(`scripts/run_honest_sweep_r3.py:16123-16135`). The generator then dispatches
`ContractSectionPlanExt` objects to `run_contract_section` and plain `SectionPlan` objects to
the legacy writer (`src/polaris_graph/generator/multi_section_generator.py:12232-12240`).
Crucially, V30 **prepends contract plans and retains every unmatched legacy enrichment plan**
(`multi_section_generator.py:11467-11489`). Therefore the live V30 report is a **hybrid
contract-slot + legacy-enrichment report**, despite the stronger “EVERY section” comment in
`contract_section_runner.py:2403-2410`.

The substantive Wave-1 goals remain valid, with these deltas:

* **U1 remains a real gap**: both the V30 narrative system contract and its user prompt
  expressly forbid any new inference. It needs a typed, pre-admitted exception and exact
  emitted/admitted binding.
* **U12 remains real but moves to the actual Gate-B driver**. The standalone compose
  preamble is not on the Gate-B path. V30 already preserves slot headings, and Gate-B already
  owns one synthesized report-level Limitations field; the remaining work is final-render
  layout, pre-generation ownership of the single Limitations role, and optional omission of
  the actual report-shape framing/summary surfaces.
* **U14b is already stated on the normal V30 narrative route**, so adding the same sentence
  to that prompt alone is moot. The gap is route completion and enforcement: regulatory
  prose, deterministic multi-sentence values, legacy enrichment/regeneration, and later
  rewrites are not uniformly one-fact/one-cited-sentence.

There is also a blocking benchmark-lineage ambiguity. Gate-B force-binds
`drb_72_ai_labor` to the DeepResearch-Bench-II **idx 56 Generative-AI question**
(`run_gate_b.py:5645-5687`; `scripts/dr_benchmark/gate0_lineage.py:27-43`), while the only
RACE wrapper in this tree packs its report under the legacy
`third_party/deep_research_bench` **task-id 72 prompt**
(`scripts/score_report_race.py:44-68`). The wrapper itself says that the score is
apples-to-apples only when the report answered that exact prompt
(`scripts/score_report_race.py:62-64`). Those questions are not the same. No score produced
by combining the current Gate-B command with `score_report_race.py --task-id 72` is valid
until the operator chooses one question/scorer lineage.

---

## 1. V30 active-writer map

### 1.1 Entry and dispatch

1. Gate-B applies the full-capability slate before importing the sweep
   (`scripts/dr_benchmark/run_gate_b.py:5616-5627`), force-enables V30 Phase 2 and Phase 1
   (`:5736-5747`), and calls the real `run_one_query` entry
   (`:5715`, `:5950-5961`).
2. `run_one_query` passes `_phase2_contract_plans` to
   `generate_multi_section_report` (`scripts/run_honest_sweep_r3.py:16012-16020`,
   `:16123-16135`).
3. V30 does **not** replace the entire outline. It prepends the contract plans and keeps
   unmatched legacy enrichment plans (`multi_section_generator.py:11467-11489`).
4. At dispatch, `is_contract_section` selects the contract runner; plain plans use
   `_run_section` (`multi_section_generator.py:12232-12240`, `:12379-12415`,
   `:12439-12526`; `contract_section_runner.py:2873-2877`).

This is the decisive correction to the prior Wave-1 seam map: the contract runner is the
primary producer for contract sections, but it is not the only authored producer in a V30
Gate-B report.

### 1.2 JSON slot-fill stream versus narrative stream

The two LLM streams have different contracts and must remain distinct:

| stream | prompt/system | call | enforcement/output |
|---|---|---|---|
| JSON slot fill | `_SYSTEM_PROMPT` says extract or mark not-extractable and emit the exact JSON schema (`slot_fill.py:207-213`); `build_slot_fill_prompt` supplies the direct quote and requires `value == source_span` (`:216-315`) | `_m63_llm_call`, whose system message is JSON-only (`multi_section_generator.py:12247-12303`) | `parse_slot_fill_response` verifies the status, source substring, and value/span equality (`slot_fill.py:321-513`). Non-regulatory payloads are rendered deterministically by `render_slot_prose` (`:789-879`). |
| slot narrative | `build_slot_narrative_prompt` receives the already-parsed payload (`slot_fill.py:703-786`); `PG_NARRATIVE_PROSE_SYSTEM_MESSAGE` is prose-only (`multi_section_generator.py:776-807`) | `_m63_narrative_llm_call` uses that prose system and `response_format=None` (`:12305-12372`). Relation framing may be appended before this call (`:12382-12399`). | The returned paragraph is placed only in the narrative stream (`contract_section_runner.py:1909-1929`), then rewritten to span tokens and strict-verified sentence by sentence with `allow_rescue=False` (`:150-231`, `:2121-2143`). |

The deterministic JSON path is not narrative generation. Its strong invariant is
`value == source_span`: `_value_matches_span` treats the value as a source substring
(`slot_fill.py:115-162`), the prompt requires identical strings (`:287-314`), and the parser
enforces the binding (`:419-484`). `render_slot_prose` then emits those extracted values
without an LLM (`:789-879`).

The narrative path is the prose the design should target for U1 and the normal U14b
directive. `run_contract_section` explicitly maintains deterministic, regulatory, and
narrative block lists (`contract_section_runner.py:1715-1744`), fills each entity
(`:1819-1829`), generates the narrative when extracted fields exist (`:1893-1929`), and
verifies each stream separately (`:2064-2143`). Narrative and regulatory prose are
rescue-ineligible; only deterministic prose can use the contract-entity rescue
(`:150-231`).

### 1.3 Narrative system and user contract

The current narrative system says to restate only the supplied field values, introduce no
new number/concept/claim, and emit one paragraph
(`multi_section_generator.py:796-807`). The user prompt:

* deduplicates extracted fields before composing (`slot_fill.py:743-758`);
* orders the contextual prose and requires one paragraph (`:771-776`);
* already says “each extracted field ... as ONE ... sentence” and each factual sentence
  gets the bound citation (`:767-769`);
* forbids new named concepts, mechanisms, outcomes, or causal claims (`:778-784`);
* applies a fact-count-derived sentence ceiling (`:685-700`, `:786`).

Thus the existing U1 behavior is not merely absent: it conflicts with both the system and
user contracts and, without an AC-on allowance, can also exceed the current sentence
ceiling.

### 1.4 Per-sentence verification and contract-section assembly

The narrative text flows through these exact stages:

1. Citation markers are rewritten to span tokens, then `strict_verify_fn` runs
   (`contract_section_runner.py:189-200`).
2. Narrative verification is explicitly `allow_rescue=False`
   (`contract_section_runner.py:2121-2143`).
3. The three verified streams are merged (`:2145-2163`).
4. A sibling-basket repair may re-anchor a dropped contract claim to an independently
   entailing sibling and therefore change its marker (`:2193-2299`). The code itself calls
   this the “PRIMARY LIVE BENCHMARK PATH” at `:2193-2195`.
5. Intra-contract keep-first consolidation can remove redundant sentences
   (`:2304-2359`), and fragment/prose consolidation can remove the deterministic duplicate
   while never dropping the prose copy (`:2360-2401`).
6. Provenance is resolved to local `[N]` citations (`:2432-2437`), but that flat result is
   not authoritative. The inline slot regroup strips/rebuilds each emitted sentence and its
   marker list (`:2439-2537`).
7. Slot headings and bodies are assembled into `verified_blocks`
   (`:2587-2599`), joined into `verified_text` (`:2799-2803`), and stored in the
   `SectionResult` (`:2828-2869`).

### 1.5 Complete V30 authored/rewrite route inventory

The following routes can create, replace, suppress, or rewrite prose that can reach the
on-disk report scored by the external RACE wrapper.

#### A. Inside one contract section

1. **Deterministic slot prose** from parsed JSON payloads:
   `render_slot_prose` (`slot_fill.py:789-879`).
2. **Regulatory synthesis**, a separate JSON LLM whose `value` is multi-sentence prose:
   prompt (`regulatory_synthesizer.py:283-350`), parser (`:446-500`), renderer
   (`:511-532`).
3. **Narrative LLM prose**:
   builder (`slot_fill.py:703-786`), adapter
   (`multi_section_generator.py:12305-12372`), call/append
   (`contract_section_runner.py:1909-1929`).
4. **A1 same-claim basket fallback**: when bound entities are shells, it rebinds and reruns
   fill/render (`contract_section_runner.py:1955-2034`). This fallback emits deterministic
   or regulatory prose; it does **not** invoke the narrative builder for the fallback
   payloads.
5. **Deterministic rescue** in `_verify_one_stream` (`:203-230`).
6. **Fragment snap**, which replaces a verified fragment with a reverified full source
   sentence (`:669-704`).
7. **Sibling-basket re-anchor**, which may replace the citation carrier
   (`:2193-2299`).
8. **Intra-contract consolidation** (`:2304-2359`) and **fragment/prose consolidation**
   (`:2360-2401`).
9. **Inline provenance/citation regroup**, which strips tokens and rebuilds exact marker
   lists (`:2439-2537`).
10. **Zero-survivor authored alternatives**: synthesized bibliography support and fallback
    handling (`:2601-2639`), verified K-span fallback (`:2640-2685`), same-work B5 re-anchor
    (`:2686-2715`), and the explicit gap-disclosure sentence (`:2716-2749`). The K-span
    helper itself reconstructs prose from passing source sentences (`:414-533`).

#### B. Multi-section routes after contract generation

11. **Legacy enrichment sections** remain live because unmatched plain plans survive V30
    injection (`multi_section_generator.py:11467-11489`) and are composed through
    `_run_section` (`:12439-12513`).
12. **Per-section crash/no-evidence stubs** can replace failed authored sections; the
    fixed gap/no-evidence/transient sentences are declared at
    `multi_section_generator.py:983-1012` and are used by the isolated gather path
    (`:12424-12429`).
13. **Cross-section fact-dedup LLM rewrite** runs after all sections and before assembly
    (`:12533-12570`), re-verifies rewrite candidates (`:12615-12666`), then re-resolves
    and mutates `sr.verified_text` (`:12690-12720`). If it empties a section, it authors a
    gap stub (`:12750-12763`).
14. **M-44 regeneration** constructs a plain `SectionPlan` and calls the legacy bounded
    writer (`:12822-12908`); **M-47 regeneration** does the same
    (`:13035-13071`) and can replace the original section (`:13098-13103`). Thus an
    eligible contract result can be replaced by legacy-generated prose unless the v4 route
    explicitly prevents it or preserves the typed carrier.
15. **Cross-section repetition guard** rewrites repeated verified text into richest-copy
    plus back-references (`:13133-13147`).
16. **Global bibliography remap** changes the section marker text and writes it back to
    `SectionResult.verified_text` (`:13149-13175`).
17. **Evidence-base / low-relevance-ledger sections** are appended after global remap
    (`:13178-13241`).
18. **Atom-refusal strict mode** can replace `verified_text`
    (`:13243-13280`).
19. **Report-level Limitations** is an LLM call with deterministic fallback
    (`:13281-13305`).
20. **Analyst Synthesis**, when enabled and not suppressed, authors a separately labeled,
    unverified block (`:13307-13373`).

#### C. Actual Gate-B driver and on-disk report routes

21. The sweep renders every surviving `SectionResult` as a `###` heading plus
    `verified_text` (`scripts/run_honest_sweep_r3.py:16281-16306`). Optional trial
    table/timeline/per-trial blocks (`:16307-16331`), Analyst Synthesis
    (`:16470-16481`), quantified trade-off (`:16482-16715`), and one synthesized
    Limitations block (`:16717-16724`) can add judged text.
22. The driver creates verbatim Abstract and Conclusion rollups from already-verified
    section prose (`:17601-17650`) and an H1 title (`:17713-17715`).
23. Report shaping can add a claim-free framing paragraph, relabel/reorder blocks, and move
    machinery into the appendix (`:17752-17850`). `assemble_report_md` then performs the
    final body assembly and paragraph/Limitations dedup (`:17853-17871`; helper definition
    at `:5310-5363`).
24. Post-assembly suppress/rewrite passes can remove garbled headers, relabel headers,
    suppress chrome/truncated units, scrub block-page sentences, and normalize GFM tables
    (`:17872-17965`).
25. The on-disk artifact is not identical to `final_report`: summary-table rendering is
    applied to an artifact copy (`:18125-18192`), then reliability/methods/machinery
    appendices are composed and written (`:18201-18258`).
26. After that write, four-role render reconciliation can suppress or replace claims/body
    text (`:19970-20105`, `:20187-20235`); V30 can append a Methods disclosure
    (`:20267-20340`); the required-entity ledger can append Coverage gaps
    (`:20380-20441`); an unadjudicated-fabrication hold can replace the entire report
    (`:21168-21200`); a D8 banner can be inserted (`:21336-21375`); and the final
    render-only repetition pass can rewrite the on-disk Markdown (`:21381-21410`).
27. If no real report exists, the universal finalizer writes a named backstop artifact
    (`:21620-21649`).

`run_external_evaluation` consumes the in-memory `final_report`
(`scripts/run_honest_sweep_r3.py:18624-18631`), but the separate RACE wrapper reads the
finished path supplied by the caller (`scripts/score_report_race.py:44`). Consequently,
RACE sees the **final on-disk `report.md`**, including artifact-only and post-write changes,
not merely the pre-write `final_report`.

The standalone `scripts/compose_agentic_report_s3gear329.py` is not the Gate-B V30 driver.
Its generator call supplies no `v30_contract_plans`
(`compose_agentic_report_s3gear329.py:629-648`), and its own preamble/assembly/write path is
at `:670-774`. It produced the old RACE baseline, but setting V30 environment variables
around that script does not construct or thread V30 plans.

---

## 2. U1 attach point: typed licensed inference before generation

### 2.1 Producer/admission seam

The correct carrier is a typed, pre-admitted `LicensedInference`, not an untyped prompt
suffix. It should be computed before `run_contract_section` calls the narrative builder and
be associated with the owning contract block/slot. The narrow transport seam is the call at
`contract_section_runner.py:1909-1914`, and the narrow prompt seam is the
`build_slot_narrative_prompt` signature/body at `slot_fill.py:703-708`, `:759-786`.

The typed value needs, at minimum:

* stable inference/block/slot identity;
* the exact ordered candidate text/tokens admitted by the canary;
* the exact ordered premise claim identities;
* the exact marker identity/union admitted for those premises;
* admission disposition and canary evidence.

When the single `analytical_contract_active` predicate is false, the builder must be called
with exactly its current arguments and return its current bytes. When true, the typed
carrier should be rendered in a delimited `LICENSED INFERENCE CANDIDATE` block after the
extracted fields/source-marker material and before `TASK` (`slot_fill.py:764-769`). The
system message needs the same narrowly typed exception at
`multi_section_generator.py:796-807`. It must say that the model may emit **only that
admitted candidate**, as the paragraph-closing sentence, with its exact admitted marker
binding. It is not a general license to derive arbitrary consequences.

The AC-on prompt also has to reconcile `_narrative_length_guidance`: today it sets the hard
ceiling from the number of extracted facts (`slot_fill.py:685-700`). A licensed closing
sentence otherwise conflicts with the ceiling and the output contract at `:786`.

The later relation wrapper appends untyped relation text after the builder
(`multi_section_generator.py:12382-12399`). It is not an admission seam and must not be
treated as one. The typed licensed inference must already have passed its canary before
reaching that wrapper.

### 2.2 Exact post-generation binding seam

`EMITTED == ADMITTED` must mean exact ordered content-token equality **and exact ordered
marker binding**. A set/subset test is unsafe: it would allow new words, reordered
qualifiers, missing premises, or a marker from the wrong source.

There are two required audit layers:

1. **Contract-local audit.** Audit after all contract-local authored changes and marker
   selection—after the inline regroup has built `stripped + markers`
   (`contract_section_runner.py:2526-2537`) and before that text is accepted into
   `verified_blocks` (`:2587-2599`). This is the first point at which the exact emitted
   sentence and exact local marker sequence are known.
2. **Document-final audit.** Preserve the typed carrier as non-rendered metadata on the
   `SectionResult`, then audit again after every multi-section mutator that can replace or
   rewrite the sentence: fact dedup (`multi_section_generator.py:12533-12763`), M-44/M-47
   regeneration (`:12822-13103`), repetition guard (`:13133-13147`), global remap
   (`:13149-13175`), and atom replacement (`:13243-13280`). A final pre-assembly audit
   belongs after those operations and before the result is returned at `:13628-13649`.
   Because the judged artifact then goes through suppressors, redaction, and final
   repetition dedup, the report writer also needs a read-only/fail-closed on-disk binding
   check immediately before the final artifact is declared scoreable. It may reject or
   disclose a missing/mutated inference; it may not repair prose post-generation.

The current cross-section repetition guard intentionally edits `verified_text`
(`multi_section_generator.py:13133-13147`), and M-44/M-47 can replace a contract result with
a legacy result. For an AC-bearing sentence, v4 must make those routes carrier-aware:
preserve it exactly, skip that sentence/section, or reject the rewrite and keep the
pre-rewrite result. Silently letting the typed sentence traverse an untracked rewrite is
not compliant.

The existing per-sentence verifier remains untouched and is still authoritative for
source support (`contract_section_runner.py:2121-2143`). The new audit is an additional
licensed-inference identity invariant implemented without importing or editing
`provenance_generator.py` or `clinical_generator/strict_verify.py`.

### 2.3 Fallback coverage

The A1 basket fallback currently reruns slot extraction/rendering but not the narrative
builder (`contract_section_runner.py:1955-2034`). Therefore an inference obligation attached
to a slot can disappear on that route. The v4 spec must choose explicitly:

* make a licensed inference inapplicable when the typed premise block falls to A1/gap
  fallback; or
* run the same typed narrative consumer over the admitted fallback premise set.

It must not silently count the main narrative path as coverage of the fallback.

---

## 3. U12-lite attach point

### 3.1 Actual judged-string assembly

Under Gate-B, the relevant assembly is in `run_honest_sweep_r3.py`, not the standalone
compose script:

* section headings + `SectionResult.verified_text`: `:16281-16306`;
* one report-level Limitations append: `:16717-16724`;
* H1 title and optional report-shape framing: `:17713-17715`, `:17752-17799`;
* block ordering and final assembly: `:17807-17859`;
* suppressive/render normalization: `:17872-17965`;
* artifact-only summary table/reliability/Methods and first write: `:18125-18258`;
* later redaction/disclosures/final repetition rewrite: `:19970-20441`,
  `:21168-21410`.

The ordered-token layout normalizer should operate at the final render seam, after all
claim-bearing blocks and headings have been selected but before the first `report.md`
write. The existing GFM normalizer at `:17951-17965` is the closest precedent. The Wave-1
normalizer's canary must prove that the ordered non-layout token stream and ordered citation
markers are identical before/after; it may only add/remove layout whitespace or split a
heading from prose. It may not delete or rewrite words.

Because later post-write routes can still rewrite the artifact, the final scoreability
check should rerun the ordered-token canary after the last on-disk repetition pass
(`:21381-21410`). That is an audit, not another content editor.

### 3.2 Preamble

The hardcoded preamble identified in the Phase-3 audit belongs to the standalone compose
script (`compose_agentic_report_s3gear329.py:680-694`). Gate-B does not use that call path,
because that script never threads V30 plans (`:629-648`).

The actual Gate-B front surfaces are:

* the H1 question title (`run_honest_sweep_r3.py:17713-17715`);
* optional verbatim Abstract/Conclusion rollups (`:17601-17650`);
* an optional claim-free report-shape framing paragraph produced by
  `build_framing_md` (`:17752-17799`).

Thus “gated preamble omission” must gate those actual producers under
`analytical_contract_active`; it must not delete their text after assembly. The operator
must decide whether U12-lite omits only the claim-free framing paragraph, or also the
Abstract/Conclusion recap. The H1 is a title, not a preamble.

### 3.3 Single Limitations role

V30 already has a report-level Limitations producer:
`generate_multi_section_report` calls it once (`multi_section_generator.py:13281-13305`) and
the driver appends it once (`run_honest_sweep_r3.py:16717-16724`). However, V30 also retains
unmatched legacy plans such as “Limitations” (`multi_section_generator.py:11467-11489`), so
a separate body section can coexist with the report-level block. The assembly helper has a
dedup/orphan-heading cleanup (`run_honest_sweep_r3.py:5310-5363`), but that is downstream
repair rather than role ownership.

The clean U12-lite attachment is at plan merge: when AC is active and the report-level
Limitations role is selected, exclude/merge a legacy dedicated Limitations plan at
`multi_section_generator.py:11479-11484` before it is authored. Preserve the single
report-level producer and its append. Per-section caveats remain ordinary body prose, not
repeated dedicated `### Limitations` headings.

---

## 4. U14b attach point

For the normal slot narrative, the directive is already present:

> “Restate each extracted field above as ONE clear, plain, declarative sentence” and make
> each factual sentence end in the bound marker (`slot_fill.py:769`).

The normal builder also deduplicates identical extracted fields (`:743-758`) and derives
the sentence ceiling from distinct facts (`:685-700`). Therefore adding another generic
one-fact/one-citation sentence only to this prompt is not a meaningful Wave-1 change.

The AC-on narrative contract can strengthen the rule in both the system message
(`multi_section_generator.py:796-807`) and user prompt (`slot_fill.py:769`) by defining an
atomic proposition and forbidding the folding of distinct source-specific facts. But the
real U14b fix is complete route coverage plus a structural post-generation audit:

* Regulatory synthesis explicitly asks for 2–4 sentences per field
  (`regulatory_synthesizer.py:292-345`), while its renderer appends one marker after the
  whole multi-sentence value (`:511-529`). Its parser validates only one source-span phrase
  and retains the complete LLM value (`:446-490`). This route does not satisfy U14b.
* Deterministic values can contain multiple source sentences. Per-sub-sentence citation is
  conditional in `render_slot_prose` (`slot_fill.py:827-878`), so the active configuration
  must be audited, not assumed.
* A1 fallback, legacy enrichment, M-44/M-47 regeneration, fact-dedup rewrite, repetition
  back-reference, and atom replacement are independent authored/rewrite routes identified
  in §1.5.

The directive should attach before every relevant authored producer, while the acceptance
check sits after the producer's final rewrite. It must check that each factual sentence
contains one complete atomic proposition and its immediate citation carrier. It must not
change the existing verifier or split/rewrite prose after generation.

---

## 5. OFF path and V30-on baseline/champion preservation

### 5.1 Single predicate

Every Wave-1 behavior must be subordinate to one semantic predicate,
`analytical_contract_active`. It should be true only when the semantic analytical contract
is enabled **and** a valid non-empty typed contract/carrier is present. An environment flag
alone must not activate partial behavior.

When false:

* `build_slot_narrative_prompt` receives the same arguments and emits the same bytes;
* `PG_NARRATIVE_PROSE_SYSTEM_MESSAGE` remains exactly the current string;
* narrative length guidance remains unchanged;
* no typed metadata is attached to `SectionResult`;
* A1, regulatory, legacy enrichment, regeneration, dedup, repetition, marker remap,
  Limitations, framing, summary, and final render routes remain unchanged;
* no layout normalizer, preamble omission, Limitations-plan filtering, or
  emitted/admitted audit runs;
* no new import—especially no import of either frozen faithfulness module—occurs on the
  OFF path.

This is the required byte-for-byte preservation target: **V30 on, AC empty/off**, not
V30 off.

### 5.2 What the V30-on baseline is

There is no established V30-on RACE champion in this tree. The baseline that must now be
measured is:

* current repository revision;
* `scripts/dr_benchmark/run_gate_b.py` as the launcher;
* its complete full-capability slate, applied with force/floor semantics
  (`run_gate_b.py:4242-4273`, `:5616-5627`);
* `PG_V30_PHASE2_ENABLED=1` and `PG_V30_ENABLED=1`, which Gate-B force-sets
  (`:5736-5747`);
* default-on V30 narrative paragraphs (`contract_section_runner.py:1893-1900`);
* Gate-B's forced consolidation flags (`run_gate_b.py:5842-5843`) and repetition guard
  (`:1794-1799`);
* `PG_ANALYTICAL_CONTRACT` absent/empty and no typed analytical contract supplied;
* the same frozen corpus snapshot, model/provider configuration, judge model, and scorer
  prompt for all compared draws.

The old `mf_baseline` is not this baseline. Its summary identifies the prebuilt cp4 corpus
and legacy task-72 composition (`outputs/race_max_focus/mf_baseline-20260723T152731Z/draw_3/compose_summary.json:1-6`);
its resolved state has section structure and most Wave levers off and strict verification
off (`:8982-9084`); and the three scores average 0.500900
(`outputs/race_max_focus/mf_baseline-20260723T152731Z/measurement.log:37048-37060`).
It was produced by `run_race_max_focus.sh` using `data/cp4_corpus_s3gear_329.json` and a
standalone runner (`scripts/run_race_max_focus.sh:14-18`, `:32-38`), not by Gate-B's V30
contract-plan path.

---

## 6. Re-baseline recipe

### 6.1 Precondition: resolve the question/scorer lineage

Current Gate-B force-enables the official-question override
(`run_gate_b.py:5659-5687`) and maps `drb_72_ai_labor` to DRB-II idx 56
(`gate0_lineage.py:32-43`). The output contract confirms that this is the Generative-AI
question with four required sections and a five-column table
(`config/benchmark/task_output_contracts.yaml:11-48`).

The local canonical file required by that loader is
`third_party/DeepResearch-Bench-II/tasks_and_rubrics.jsonl`
(`gate0_lineage.py:27-30`, `:99-123`), but this checkout contains only
`third_party/DeepResearch-Bench-II/uv.lock`. Therefore a live Gate-B run for this slug will
fail before generation until the canonical gold file is restored.

Separately, `scripts/score_report_race.py` reads the legacy
`third_party/deep_research_bench/data/prompt_data/query.jsonl` by task id
(`score_report_race.py:44-56`) and packs that exact prompt with the target article
(`:58-68`). The registered sweep question still shows the older “Fourth Industrial
Revolution / English-language journal articles” wording
(`run_honest_sweep_r3.py:7919-7934`), whereas Gate-B replaces it with the idx-56 question.
The repository's own lineage guard requires packed == answered == canonical
(`gate0_lineage.py:156-177`).

Therefore:

* If the canonical benchmark is **DRB-II idx 56**, restore its gold file and use the
  DRB-II scorer/rubric pack for idx 56. The repository currently exposes no demonstrated
  RACE wrapper for that pack.
* If the canonical benchmark is **legacy RACE task 72**, the generated report must answer
  that exact legacy prompt; the current forced Gate-B override must not silently replace
  it.

Do not run `score_report_race.py --task-id 72` on a current official-question Gate-B report
and call it a valid score.

### 6.2 Generation command after that precondition is fixed

From the repository root, with the paid-run credentials already in the environment:

```bash
set -a
. ./.env
set +a
env -u PG_ANALYTICAL_CONTRACT \
  python -u scripts/dr_benchmark/run_gate_b.py \
  --only drb_72_ai_labor \
  --out-root outputs/wave1_v30_baseline_draw1
```

`--only` and `--out-root` are the supported Gate-B arguments
(`run_gate_b.py:6341-6359`). The output tree is
`<out_root>/<domain>/<slug>` (`:6357-6359`), and this slug's domain is `workforce`
(`run_honest_sweep_r3.py:7927-7929`), so the report lands at:

```text
outputs/wave1_v30_baseline_draw1/workforce/drb_72_ai_labor/report.md
```

The fresh run writes `corpus_snapshot.json` at the final pre-generation seam
(`run_honest_sweep_r3.py:15818-15842`). The snapshot includes the fully constructed
generation evidence, including V30 preparation (`:15818-15824`).

### 6.3 Frozen-corpus replicated draws

For draws 2 and 3, place an exact copy of draw 1's `corpus_snapshot.json` under the same
`workforce/drb_72_ai_labor/` relative path in a new output root, then invoke the same
command with `--resume`. The resume loader prefers `corpus_snapshot.json`, checks that its
question matches the launched question, and re-enters generation while rerunning all
faithfulness gates (`run_honest_sweep_r3.py:9460-9478`, `:9516-9548`). Gate-B exposes the
resume flag at `run_gate_b.py:6385-6400`.

Example for each cloned root:

```bash
env -u PG_ANALYTICAL_CONTRACT \
  python -u scripts/dr_benchmark/run_gate_b.py \
  --only drb_72_ai_labor \
  --out-root outputs/wave1_v30_baseline_draw2 \
  --resume
```

Use a distinct output root/model label for every independent generator draw. Do not score
one frozen report three times.

### 6.4 Scoring command and score location

Only after the scorer has been made question-identical to the generated report, the
existing legacy RACE wrapper is invoked as:

```bash
python -u scripts/score_report_race.py \
  --report outputs/wave1_v30_baseline_draw1/workforce/drb_72_ai_labor/report.md \
  --task-id 72 \
  --model-name wave1_v30_baseline_draw1 \
  --race-model '<operator-pinned OpenRouter RACE judge>'
```

The wrapper requires `OPENROUTER_API_KEY` (`score_report_race.py:40-42`), sets the
OpenRouter backend, invokes the official legacy harness (`:82-99`), validates that the
cleaned artifact is the report actually scored (`:101-128`), and writes:

```text
third_party/deep_research_bench/results/race/<model-name>/race_result.txt
```

(`score_report_race.py:82-96`, `:130-136`). Its current default judge is
`openai/gpt-5.5` (`:36`); a valid comparison must pin one operator-approved judge and use
that exact judge for every baseline and candidate draw.

Gate-B itself does **not** invoke this RACE wrapper. It generates/runs its native gates and
checks the on-disk report contract (`run_gate_b.py:5950-5961`, `:5983-5997`). Generation
and RACE scoring are two explicit commands.

### 6.5 Minimum valid measurement

The Phase-3 audit requires paired, same-judge, same-corpus, otherwise-identical
**at least 3v3** draws and a paired-mean decision
(`docs/race_fact_initiative/PIPELINE_GAP_AUDIT.md:802-806`).

Minimum:

1. three independent V30-on / AC-off generator draws on one frozen Gate-B corpus, each
   scored once — this establishes the new baseline/champion candidate;
2. three independent V30-on / AC-on Wave-1 draws on the identical snapshot/config, each
   scored once;
3. compare the paired per-dimension means, not a single score.

That is six generated reports and six judge scores for the first valid 3v3 probe. A single
V30-on draw is only a smoke/artifact check, not a champion.

### 6.6 Seed verdict

`outputs/full_scale_v30_phase2_run14` is **not** a usable seed in this checkout. It contains
only `SHIP_MANIFEST.md`; the manifest points to a missing
`clinical/clinical_tirzepatide_t2dm/` artifact and records an old clinical run/commit
(`outputs/full_scale_v30_phase2_run14/SHIP_MANIFEST.md:1-20`). It is the wrong domain and
has no `corpus_snapshot.json`.

No `corpus_snapshot.json` exists anywhere under the current `outputs/` tree. The file
`data/cp4_corpus_s3gear_329.json` exists, but Gate-B `--resume` loads its own versioned
`corpus_snapshot.json` from the run directory (`run_honest_sweep_r3.py:9541-9548`);
the code provides no direct Gate-B `--corpus data/cp4...` argument. The cp4 file is
therefore not an established drop-in Gate-B resume seed.

---

## 7. Phase-3 audit delta

### U1 — licensed paragraph-closing inference

**Finding still holds; transport and acceptance change.**

The Phase-3 audit found that the legacy writer forbids derived implications
(`PIPELINE_GAP_AUDIT.md:86-127`). The V30 writer is at least as restrictive:
the narrative system allows only verbatim-extracted values
(`multi_section_generator.py:796-807`), and the user contract forbids new mechanisms,
concepts, outcomes, and causal claims (`slot_fill.py:778-784`). Relation framing exists
(`multi_section_generator.py:12382-12399`) but is untyped and does not create an admitted
candidate or exact binding audit.

The fix is different from the legacy spec: inject a typed, pre-admitted candidate at the
slot/block narrative seam, adjust the AC-on length contract, preserve the carrier through
all hybrid rewrites, and audit exact emitted text/markers after local regroup and again
after document-level rewrites.

### U12 — structure/preamble/Limitations

**Partly moot, partly narrower, and attached elsewhere.**

The old finding is at `PIPELINE_GAP_AUDIT.md:546-592`.

* The standalone hardcoded preamble defect is moot for Gate-B V30: that script neither
  creates nor receives V30 plans (`compose_agentic_report_s3gear329.py:629-648`). Gate-B's
  real framing/summary producers are in `run_honest_sweep_r3.py:17601-17650`,
  `:17713-17799`.
* Contract slots already preserve one `###` heading followed by one body block
  (`contract_section_runner.py:2587-2599`). The legacy “active producer loses all block
  boundaries” diagnosis does not directly describe the normal slot route.
* The report remains hybrid, so legacy enrichment can still exhibit the old structural
  defects (`multi_section_generator.py:11467-11489`, `:12439-12513`).
* A report-level Limitations producer/append already exists
  (`multi_section_generator.py:13281-13305`;
  `run_honest_sweep_r3.py:16717-16724`). The remaining issue is unique ownership versus
  an unmatched legacy Limitations plan, not inventing a new Limitations mechanism.
* Final report suppressors, artifact additions, redaction, disclosure appenders, and the
  last repetition rewrite mean the ordered-token layout proof belongs on the actual
  on-disk Gate-B render path, not the old compose driver.

### U14 — FACT atomic supported-pair volume

**Normal narrative directive is already present; complete-route enforcement is not.**

The original finding and proposed one-fact/one-cited-sentence rule are at
`PIPELINE_GAP_AUDIT.md:626-664`. V30's normal narrative prompt already says one distinct
field per cited sentence (`slot_fill.py:743-769`), so that prompt-only part is moot.

The gap survives on other V30-authored paths:

* regulatory values can be 2–4 sentences with one trailing citation
  (`regulatory_synthesizer.py:314-345`, `:511-529`);
* deterministic multi-sentence values depend on the sub-sentence-citation mode
  (`slot_fill.py:827-878`);
* legacy enrichment and M-44/M-47 legacy regeneration remain live;
* fact-dedup, repetition back-references, and atom replacement can alter atomicity after
  initial generation.

U14b should therefore become a typed pre-generation atomicity obligation plus
post-producer structural audit over all authored routes. U14a—retrieval/deepening to
increase the number of distinct admitted works—remains a later stage and is not solved by
the V30 writer.

The Phase-3 architectural sentence that names `_compose_section_per_basket` as the sole
active producer (`PIPELINE_GAP_AUDIT.md:59-68`, `:810-820`) must be replaced for v4 with
the hybrid dispatch described in §1.

---

## Retargeted Wave-1 stage map

| stage | V30/Gate-B file:function | Wave-1 responsibility |
|---|---|---|
| **Stage 1 — typed transport** | producer/planner into `contract_section_runner.run_contract_section` (`contract_section_runner.py:1627-1651`), then `slot_fill.build_slot_narrative_prompt` (`slot_fill.py:703-786`) | Carry the pre-admitted `LicensedInference` and atomic proposition obligations as typed data. Render them into the narrative prompt only when `analytical_contract_active`. Preserve byte identity when false. |
| **Stage 2 — inference production** | `build_slot_narrative_prompt` (`slot_fill.py:759-786`); `PG_NARRATIVE_PROSE_SYSTEM_MESSAGE` (`multi_section_generator.py:796-807`); `_m63_narrative_llm_call` (`:12305-12372`) | Add the narrow AC-on licensed-inference exception, exact candidate/marker instructions, and AC-on sentence-budget allowance. Do not alter JSON extraction or the frozen verifier. |
| **Stage 3 — consumption and binding** | narrative append/verify (`contract_section_runner.py:1909-1929`, `:2121-2143`); local regroup (`:2439-2537`); multi-section rewrite seams (`multi_section_generator.py:12533-13280`) | Require exact ordered emitted/admitted candidate and marker binding after local regroup; preserve/audit the carrier through dedup, regen, repetition, remap, and atom replacement. Reject/disclose mismatch; never repair prose post-generation. Cover or explicitly exclude A1 fallback and legacy enrichment. |
| **Stage 5 — U12 layout/final report** | section/Limitations assembly (`run_honest_sweep_r3.py:16281-16306`, `:16717-16724`); framing/order/final assembly (`:17601-17965`); artifact/write/post-write (`:18125-18258`, `:19970-21410`) | Attach ordered-token-proven layout normalization; gate the actual framing/summary producers at source; enforce one Limitations owner at the plan merge; rerun a read-only token/binding canary on the final on-disk artifact. |
| **Stage 6 — U14b** | normal narrative contract (`slot_fill.py:743-786`); regulatory prompt/render (`regulatory_synthesizer.py:283-350`, `:511-532`); deterministic render (`slot_fill.py:789-879`); hybrid legacy/regeneration routes (`multi_section_generator.py:11467-11489`, `:12822-13103`) | Keep/strengthen the existing narrative atomicity directive, extend it to every authored producer, and structurally audit one complete atomic fact per immediately cited sentence after each route's final rewrite. |

## Single biggest open question for the operator before v4

**Which question/scorer lineage is canonical for the Wave-1 RACE gate: DeepResearch-Bench-II
idx 56 (the question Gate-B force-answers), or legacy RACE task 72 (the prompt
`score_report_race.py --task-id 72` force-packs)?**

Until that is decided—and the missing DRB-II gold file or matching scorer is restored—the
team can build and byte-canary the V30 transport, but it cannot establish a valid
“Gate-B-generated, RACE-scored” V30 champion. Combining the current two commands would
violate the repository's own packed == answered == canonical invariant
(`gate0_lineage.py:156-177`).
