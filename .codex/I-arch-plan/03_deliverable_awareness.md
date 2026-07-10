# DESIGN 3 — DELIVERABLE-AWARENESS (dynamic, not hardcoded)

Author: FABLE 5 (architect brain). Date: 2026-07-10. Branch: `bot/I-deepfix-relaunch`.
Audit anchor: `.codex/I-arch-audit/fable_orchestration_audit.md` — stage RA row + section (b) "DELIVERABLE REQUIREMENTS — requirement-BLIND (hardcoded)" + ranked gap #5.
Standing mandates honored: §-1.3 weight-not-filter + basket faithfulness; faithfulness engine UNTOUCHED; MAX PARALLELISM; crash-resilient incremental + resume; requirement-aware not hardcoded; self-contained section with hamster loop + acceptance bar + checkpoint.

---

## 1. The problem, in one paragraph

POLARIS already parses the user's SCOPE (date window, language, source type, jurisdiction, named include/exclude) and bends retrieval + selection to it. It parses NOTHING about the DELIVERABLE. Tone, structure, deliverable type, audience, reference style, and length asks in the prompt are silently ignored. The outline runs a fixed template. The section prose runs a fixed rigor prompt with a hardcoded 10-18-sentence target. The references render as a fixed `[N]` bibliography. A user who asks for "a two-page plain-language policy memo with Harvard references and an executive summary first" gets the same clinical-review shape as everyone else. DRB-II scores instruction-following; this gap costs us directly against ChatGPT and Gemini, which both honor these asks.

## 2. Ground truth — where the prompt is parsed TODAY (real code, verified)

The intake pattern ALREADY EXISTS for scope. We extend it, we do not invent it.

| What | Where | Status |
|---|---|---|
| B10 hard-constraint extractor (date/language/journal-only) | `src/polaris_graph/retrieval/intake_constraint_extractor.py:1-24` (module), `:136-199` (`UserConstraints` dataclass), `:225-305` (regex primary), `:361-390` (`extract_user_constraints` with injected `llm_fn` fallback) | LIVE — called in scope gate, flag ON in slate (`run_gate_b.py:5831` sets `PG_EXTRACT_USER_CONSTRAINTS=1`) |
| I-scope-001 scope-facet extractor (source-type/jurisdiction/named include-exclude) | same module, `:782` (`extract_scope_constraints_enabled`) onward | LIVE — flag ON (`run_gate_b.py:619`) |
| Scope-gate call sites (FILL-not-override, protocol keys `user_constraints` + `scope_constraints`) | `src/polaris_graph/nodes/scope_gate.py:1010-1037` (B10), `:1045-1059` (scope facets), `:1071-1076` (language fold-in) | LIVE |
| **O2 instruction-slot extractor** ("include a section on X", "organize by Y", comparisons, enumerations) | `intake_constraint_extractor.py:478-503` (`InstructionSlot` dataclass), `:535` (regex primary), `:642` (`extract_instruction_slots` + LLM fallback), flag `PG_EXTRACT_INSTRUCTION_SLOTS` `:506-509` | **BUILT BUT UNWIRED — zero consumers.** `grep extract_instruction_slots\|instruction_slots` across `src/` and both `scripts/run_honest_sweep_r3.py` and `scripts/dr_benchmark/run_gate_b.py` finds only the defining module. The classic winner-built-not-wired pattern (memory 2026-06-28). |
| Deliverable spec (tone / audience / type / reference style / length / format) | NOWHERE | **MISSING — the gap this design closes** |
| Protocol persisted + SHA-pinned | `run_honest_sweep_r3.py:16242` ("Pre-registered protocol.json (SHA-256 ...)") | LIVE — the natural home for the new spec |
| Clean question threading (injection-stripped; raw `q["question"]` never mutated) | `run_honest_sweep_r3.py:9292-9302` region (per audit stage 1, `:10419`) | LIVE — the extractor input |

## 3. Ground truth — where outline and compose are configured TODAY (real code, verified)

| Seam | Where | What is hardcoded |
|---|---|---|
| Generator entry | `src/polaris_graph/generator/multi_section_generator.py:8845` `generate_multi_section_report(*, research_question, evidence, ..., domain: str = "" :8953, storm_outline :8960)` | No deliverable input exists at all. The only "requirement" kwarg is `domain`. |
| Sweep call site | `scripts/run_honest_sweep_r3.py:15169-15174` (`research_question=q["question"]`), `domain=str(q.get("domain",""))` at `:15306` | Threads the question and domain, nothing else about the ask |
| Outline call | `multi_section_generator.py:2547` `_call_outline(...)` — prompt built `:2630-2666` as `"Research question: ...\nEvidence summaries..."` | User prompt reaches the planner ONLY as the research question; no requirement block |
| Outline prompt selection | `:1481-1491` `_select_outline_system_prompt(domain)` → clinical `:1380` / generic `:1419` / facet `:1454` | Three FIXED system prompts; facet is the production non-clinical path (`PG_FACET_OUTLINE=1`, `run_gate_b.py:1288`) |
| Fixed title menus | `:784-793` clinical 8-title `_ALLOWED_SECTIONS`, `:800-807` generic 6-title, chooser `:810-817`; facet cap machinery `:832-859` | Clinical questions are LOCKED to 8 fixed titles; generic to 6 unless facet flag on |
| Section prose prompt | `:2889-3025` `SECTION_SYSTEM_PROMPT_TEMPLATE` (clinical), `:3038` field-agnostic; CONCISE style variants `:3186-3190` built by `_build_concise_variant`; selector `:3240-3260` `_select_section_system_prompt(use_field_agnostic, anti_verbosity)` | Rule 8 hardcodes "Target 10-18 sentences"; rule 9 hardcodes ">=5 distinct sources"; tone/audience never mentioned. NOTE: the CONCISE variant + `PG_ANTI_VERBOSITY` prove the codebase already supports STYLE-VARIANT section prompts — the selector just has no user-driven input. |
| Assembly | `run_honest_sweep_r3.py:5230` `assemble_report_md(title_md, abstract_md, body_md, conclusion_md)` | Fixed order: title → abstract → body → conclusion. No memo/brief/exec-summary-first shapes. |
| References | `run_honest_sweep_r3.py:3999-4017` `_render_bibliography_lines` emits fixed `"\n\n## Bibliography\n"` + numbered entries; numbering from `src/polaris_graph/synthesis/citation_mapper.py:595-627` `build_bibliography` (`citation_key = f"[{number}]"`) | ONE citation style, hardwired. Bib rows carry url/tier/title(`statement`)/evidence_ids; publication year is recoverable (`_m2_publication_year`, `run_honest_sweep_r3.py:3836`); AUTHORS are generally NOT captured. |
| Abstract/Conclusion/Key Findings | `src/polaris_graph/generator/abstract_conclusion.py:1-33` — VERBATIM extractive from verified body | Placement and labels fixed |
| V30 Report Contract | `src/polaris_graph/nodes/report_contract.py:1-54` | Operator-authored per-slug YAML spec. NOT parsed from the user prompt. Not a substitute — it is the proof the slot machinery exists. |

Conclusion: the pipe from "user asks" to "outline + compose + render obey" is missing exactly one structured object and three prompt/render seams. Everything else (intake pattern, protocol persistence, style-variant prompts, slot dataclass) already exists.

## 4. THE DESIGN

### 4.1 New component: `deliverable_spec_extractor`

New module `src/polaris_graph/retrieval/deliverable_spec_extractor.py` (own file per LAW V — `intake_constraint_extractor.py` is already 1069 lines). Same architecture as B10: deterministic regex primary + ONE injected-LLM semantic pass + merge, pure and offline-testable, fail-open.

```python
@dataclass
class DeliverableSpec:
    deliverable_type: str | None = None    # 'report'|'brief'|'memo'|'literature_review'|'white_paper'|'faq'|'letter'|free text
    audience: str | None = None            # 'clinician'|'policymaker'|'executive'|'general_public'|'academic'|free text
    tone: str | None = None                # 'formal'|'plain_language'|'critical'|'neutral'|free text
    reading_level: str | None = None       # e.g. 'lay', 'expert'
    reference_style: str | None = None     # 'numeric'|'author_year'|'apa'|'harvard'|'vancouver'|'footnote'|'inline_url'
    length_target_words: int | None = None # parsed number, e.g. "about 2000 words"
    length_target_pages: int | None = None # "two-page memo"
    length_strictness: str = "weight"      # 'weight' default; 'hard' only on explicit "no more than"/"strictly" (mirror of timeline_strictness, intake_constraint_extractor.py:154)
    summary_first: bool | None = None      # "start with an executive summary"
    recommendations_last: bool | None = None
    wants_tables: bool | None = None       # "include a comparison table"
    structure_slots: list[dict] = field(default_factory=list)  # O2 InstructionSlot.to_dict() — REUSED, finally wired
    output_format: str | None = None       # 'markdown'|'html'|'plain'
    raw_directives: list[str] = field(default_factory=list)    # VERBATIM trigger spans, one per parsed field
    source: str = "regex"                  # 'regex'|'llm'|'merged'
    def is_empty(self) -> bool: ...
    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, d) -> "DeliverableSpec": ...
```

Extraction split (this is the one place the B10 recipe changes, deliberately):
- **Regex primary for MECHANICAL fields** — named citation styles ("APA", "Harvard", "Vancouver", "numbered references", "footnotes"), numeric lengths ("~2000 words", "two-page", "no more than N pages"), explicit shape words ("executive summary", "memo", "policy brief", "literature review", "FAQ"), table asks. Regex wins on conflict, exactly like B10 `_merge` (`intake_constraint_extractor.py:307`).
- **LLM pass for SEMANTIC fields** — tone, audience, reading level, deliverable type when implied rather than named. Unlike B10 (where LLM is a fallback), the semantic fields NEED the LLM as co-primary: "write it so my board can act on it" has no regex. ONE call per run. Model: the mirror `z-ai/glm-5.1` per the runtime lock's `legacy_compat` (side judges that are not one of the 4 locked roles map to the mirror — CLAUDE.md §9.1.8). `max_tokens` at the model's real cap, reasoning effort max (§9.1.8: caps are free insurance). Injected as `llm_fn`, never imported — same testability contract as B10 (`intake_constraint_extractor.py:19-23`).
- **O2 wiring** — `extract_instruction_slots` (`intake_constraint_extractor.py:642`) is called and its slots land in `structure_slots`. This wires the built-but-orphaned winner instead of duplicating it.
- **Anti-invention rule (LAW II):** every populated field MUST carry its verbatim trigger span in `raw_directives`. A field with no span is rejected in `_merge`. The LLM prompt states: "Extract ONLY requirements the prompt explicitly states or unambiguously implies; when unsure, omit the field." Empty spec ⇒ pipeline behaves byte-identically to today. Fail-open: any LLM/parse error ⇒ regex-only spec + one disclosed log line, never an abort.

Flags (LAW VI, all read at call time): `PG_DELIVERABLE_SPEC` master (default OFF, slate ON), `PG_DELIVERABLE_SPEC_LLM` (semantic pass, default ON when master on), `PG_DELIVERABLE_RENDER` (render leg, separable kill-switch). Slate pins go next to the sibling flags in `run_gate_b.py` (`:619`, `:1288`, `:5831` cluster).

### 4.2 Threading — one object, four consumers

```
q["question"] (clean, injection-stripped)
   └─ scope_gate (nodes/scope_gate.py, new seam directly after :1059)
        └─ protocol["deliverable_spec"] = spec.to_dict()       ← pre-registered, SHA-pinned protocol.json (run_honest_sweep_r3.py:16242)
             └─ run_dir/deliverable_spec.json                  ← CHECKPOINT (see §7)
                  ├─ consumer 1: outline planner   (_call_outline prompt block)
                  ├─ consumer 2: section composer  (section system-prompt style block)
                  ├─ consumer 3: assembler/render  (ordering + reference style + labels)
                  └─ consumer 4: Methods adherence disclosure (DRB-II instruction-following credit)
```

- `scope_gate.py`: add the third extractor call in the same shape as the two existing ones (`:1010-1037`, `:1045-1059`) — gated, FILL-not-override, logged. Scope-rejected questions skip it (same `if not scope_rejected` guard).
- `run_honest_sweep_r3.py`: after the scope gate, write `run_dir/deliverable_spec.json` (checkpoint, §7); pass `deliverable_spec=_deliverable_spec` into `generate_multi_section_report(...)` at the `:15169` call site (and the `_reuse_postgen_reentry` resume path at `:15157` — resume must carry the spec too).
- `multi_section_generator.py`: new kwarg `deliverable_spec: dict | None = None` on `generate_multi_section_report` (`:8845`). `None` ⇒ every prompt string byte-identical to HEAD.

### 4.3 Consumer 1 — outline orchestrator becomes deliverable-aware

New pure function `render_outline_deliverable_block(spec) -> str`. When the spec is non-empty, the block is appended to WHICHEVER outline system prompt `_select_outline_system_prompt` (`:1481`) picked — clinical, generic, or facet — and the user's structural asks ride into `_call_outline`'s user prompt (`:2630-2666`) next to the research question. Concrete block:

```
USER DELIVERABLE REQUIREMENTS (parsed verbatim from the user's prompt; honor them):
- Requested sections (REQUIRED-IF-GROUNDED): {structure_slots titles}. Include each as a section
  WHEN the evidence supports it. If the corpus cannot ground a requested section, still emit it
  with "evidence_gap": true and an honest one-line focus stating the gap — NEVER silently drop
  a user-requested section, and NEVER invent evidence for it.
- Requested organization: {structure directives, e.g. "organize by region"}.
- Deliverable type / audience / tone: {type} for {audience}, {tone}. Choose section granularity
  and titles a {audience} reader expects.
- Length signal: {target}. This shapes SECTION COUNT AND PROSE BUDGET ONLY. It NEVER limits
  which evidence is considered or cited.
These requirements NEVER override the evidence rules above: sections still emerge from evidence,
ev_ids still come only from the corpus, and no facet is invented (§-1.3).
```

Hard rules baked into the design (not left to the model):
- **REQUIRED-IF-GROUNDED, additive.** A user-asked section is added to the allow-list surface, never used to REPLACE the clinical safety titles: on the clinical path the 8-title list (`:784-793`) is EXTENDED with the user titles; on the facet path (production non-clinical) the facet prompt takes them natively as named facets. `_parse_outline` (`:1494`) accepts the user titles by passing them in `allowed_sections`.
- **`evidence_gap` sections are render-safe.** A section the planner marks `evidence_gap: true` produces NO LLM prose call (nothing to cite — a prose call would just get every sentence dropped by strict_verify). The renderer emits the header + one deterministic disclosure sentence ("The prompt requested this section; the retrieved corpus does not contain evidence that grounds it."). Methods-class disclosure text, not a factual claim — zero faithfulness surface. Fail-loud, never silent.
- **No count forcing.** A length ask tunes the PROSE budget per section (consumer 2); it never caps section count, never truncates the outline, never thins the evidence menu. The §-1.3 day-waster ban stands: no new number-forcing knob is introduced; `PG_OUTLINE_MAX_EV` and facet caps are untouched.

### 4.4 Consumer 2 — compose stage becomes deliverable-aware

New pure function `render_section_style_block(spec, n_sections) -> str`, appended by `_select_section_system_prompt` (`:3240-3260` — grows a third parameter) to whichever template is active (clinical / field-agnostic / concise variants). Concrete block:

```
USER STYLE REQUIREMENTS (parsed from the user's prompt):
- Audience: {audience}. Tone: {tone}. Write for this reader.
- Sentence budget for this section: {derived range}.   [only when a length ask exists]
PRECEDENCE: the CRITICAL RULES above ALWAYS win over these style requirements. Every sentence
still ends with [ev_XXX] markers, numbers stay verbatim, hedging stays bound to evidence
strength. Style may change WORDING and LENGTH only — never a claim, a number, or a citation.
```

- **Length:** when `length_target_words/pages` is set, the hardcoded "10-18 sentences" numeral in rule 8 (`:2901`) is substituted with a derived per-section range: `total_target / n_sections` converted to sentences (≈20 words/sentence), floored at a minimum that keeps rule 9's citation-diversity floor satisfiable. `length_strictness='weight'` ⇒ a target the model aims at; `'hard'` (explicit "no more than") additionally lets the existing CONCISE variant machinery (`_build_concise_variant`, `:3186-3190`) be selected — the codebase's proven density style — instead of inventing a new trimming pass. No spec ⇒ the literal 10-18 stays byte-identical.
- **§-1.3 guarantee — brevity never drops sources.** A short prose ask compresses SENTENCES; multi-citation consolidation (rule 10, `:2903`) means the basket's sources still ride each surviving sentence, the bibliography still lists every cited source, and finding_dedup/corroboration are untouched. The spec has NO path into evidence selection, topic gating, junk deletion, or weights — enforced by construction (it is only ever read inside prompt-string builders and the renderer).
- **Verify-after-compose unchanged.** strict_verify, NLI, 4-role D8, provenance, span-grounding: zero edits. Styled prose that breaks grounding gets dropped exactly like any other prose — the style block cannot lower the bar, only change wording inside it.

### 4.5 Consumer 3 — render honors reference style and shape

- **Reference style:** `_render_bibliography_lines` (`run_honest_sweep_r3.py:3999`) gains a `reference_style` parameter. `numeric` (default) is byte-identical. `author_year`/APA/Harvard/Vancouver render from REAL captured metadata only: title (`statement`), year (`_m2_publication_year`, `:3836`), venue/domain, URL/DOI. Authors are mostly NOT captured (verified — `build_bibliography`, `citation_mapper.py:595-627`, carries url/tier/statement/evidence_ids); a row without authors renders `"{Title} ({Year}). {URL}"` and Methods discloses: "Author-name metadata is not captured for all sources; author-year entries fall back to title-year." NEVER fabricate an author or a year (LAW II). In-text `[N]` markers stay `[N]` in v1 for every style (the body's provenance-bound markers are load-bearing for the D8/redaction pipeline); the style governs the reference LIST + the section label ("References" vs "Bibliography"). Full in-text author-year is a disclosed v2 (it requires touching resolve_citations and the redactor's marker regex — out of the untouchable-core rule of this design).
- **Shape:** `assemble_report_md` (`:5230`) gains an `ordering` input: `summary_first` (already the default order — abstract sits after title) vs memo shapes (title block + "Purpose" lead), `recommendations_last` (moves the extractive Conclusion/Key-Findings block per `abstract_conclusion.py` labels). All re-ORDERING and re-LABELING of verbatim-extractive blocks — zero new claim text.
- **Consumer 4 — adherence disclosure:** the Methods block gains "Deliverable requirements" lines: each parsed directive (verbatim span) + status HONORED / PARTIAL(reason) / NOT-GROUNDED(evidence gap). This is the same disclosure discipline as B10's date-window banner (`intake_constraint_extractor.py:17`) and is direct DRB-II instruction-following credit.

### 4.6 What the spec may NEVER touch (binding guardrails)

| Never | Why |
|---|---|
| Retrieval, query-gen, fetch | Deliverable ≠ scope. Scope constraints already have their own lane. |
| Topic gate, junk deletion, selection weights, tier weighting | §-1.3: presentation asks must not become filters. |
| strict_verify / NLI / 4-role D8 / provenance / redactor | Faithfulness engine untouched — the mandate. CI check: the PR diff must show zero edits under `generator/provenance*`, `roles/`, `strict_verify` paths. |
| finding_dedup / fact_dedup / baskets | Consolidation is not a style concern. |
| Section count caps or evidence menu caps | No new number-forcing knobs (§-1.3 day-waster ban). |

## 5. Requirement-aware, not hardcoded — the test of the principle

There is no template registry and no fixed deliverable menu. Every field is free text parsed from THIS prompt with a verbatim span; unparsed = absent = today's behavior. The same binary honors "plain-language brief for parents" and "Vancouver-referenced systematic-review-style report" with zero code paths keyed to either phrase. The only enums are renderer capabilities (citation styles we can actually render), and unknown values fall back to default + disclosure, never to a crash or a silent guess.

## 6. SELF-CONTAINED SECTION — hamster loop, acceptance bar, checkpoint

### 6.a Fast isolation hamster loop (quick test → read every line → Fable investigates → Opus builds → retest, concurrent)

- **Level 0 — offline unit battery (seconds).** `tests/polaris_graph/test_deliverable_spec_extractor.py`: ~40 real prompt phrasings (drawn from the DRB-II prompt set already in the repo — they carry genuine format asks) → asserted spec fields + verbatim spans; empty prompt ⇒ empty spec; OFF flag ⇒ `render_*_block` returns "" and prompt-string SHA equals HEAD's (hash-pinned fixtures).
- **Level 1 — extractor live loop (~1 min/iter).** `scripts/deliverable_spec_harness.py --prompts <file>`: runs regex+LLM extraction over the battery at 32-concurrent (one cheap mirror call each), emits one JSON line per prompt. Fable reads EVERY line (§-1.1 forensic read: field-by-field vs the prompt's actual words — parsed-but-not-asked = INVENTED = fail; asked-but-not-parsed = MISS). Opus patches regex/prompt. Retest. Target cycle < 5 minutes.
- **Level 2 — compose behavioral loop (minutes, no retrieval).** `--banked <corpus_dir> --spec <fixture.json>`: loads a banked evidence pool (already in repo per memory `fact_competitor_outputs_already_in_repo`), runs `_call_outline` + ONE `_call_section` + `_render_bibliography_lines` + `assemble_report_md` with the spec injected — prints outline JSON, section prose, references. Multiple spec fixtures run concurrently (LLM stages 32-64 in flight per the parallelism mandate; the box takes it). Judge = the standing dual gate (Codex CLI + Fable), directive-by-directive per §-1.1: verdict per directive HONORED / PARTIAL / IGNORED / FAITHFULNESS-VIOLATION with the exact output line quoted. No counts-as-quality, no string-presence checks.
- **Loop exit:** two consecutive iterations with zero IGNORED and zero FAITHFULNESS-VIOLATION across the battery.

### 6.b Lock-down acceptance bar (all six required to close)

1. **OFF-path byte-identical:** master flag unset ⇒ outline + section prompt strings hash-equal to HEAD; banked replay produces byte-identical report.md.
2. **Extraction fidelity:** on the battery, 100% of explicit MECHANICAL directives extracted with verbatim spans; ZERO invented fields (every populated field has a span that appears in the prompt).
3. **Behavioral honoring:** 3 banked corpora × 3 spec fixtures (memo+author-year+page-cap / lay+exec-summary-first / academic+Vancouver+depth): dual-gate directive-by-directive verdicts show zero IGNORED; PARTIAL only with a disclosed reason in Methods.
4. **Faithfulness-neutral:** verified-sentence count and strict_verify drop-rate within noise (±2%) of the no-spec baseline on the same banked corpora; zero diff under the untouchable paths (§4.6 CI check).
5. **Fail-open proof:** corrupt LLM JSON and LLM timeout both ⇒ regex-only or empty spec + one disclosed log line + completed run.
6. **Disclosure present:** Methods lists every parsed directive with status; evidence-gap sections render the deterministic disclosure line.

### 6.c CHECKPOINT at the component boundary

- **Input boundary:** the clean question (post injection-strip; raw `q["question"]` never mutated — `run_honest_sweep_r3.py:9292-9302`) + the scope-gate protocol. Both already checkpointed (protocol.json, `:16242`).
- **Output boundary:** `run_dir/deliverable_spec.json` — written atomically right after the scope gate, SHA-256 recorded in the run manifest. Pattern precedent: `_STORM_OUTLINE_CHECKPOINT = "storm_outline.json"` (`run_honest_sweep_r3.py:6989`, persisted-before-fetch semantics `:9162`, fail-loud persist warning `:10121`).
- **Resume semantics:** on resume, if `deliverable_spec.json` exists it is LOADED, never re-extracted (pin — deterministic across resumes; an LLM re-extraction could differ). The `_reuse_postgen_reentry` path (`:15157`) receives the same pinned dict. All 32-64 concurrent section calls read the one pinned object — deterministic across cores by construction (read-only shared state, no per-worker LLM calls).
- **Pipeline resume point:** everything downstream of the scope gate can restart from `protocol.json + deliverable_spec.json + banked corpus` without re-running intake — which is exactly what the Level-2 harness exploits.

## 7. Performance / parallelism budget

One extra mirror-model call per RUN (~seconds, off the critical path — it can run concurrent with query decomposition since both consume only the clean question). Prompt blocks add constant ~10²-char overhead per outline/section call. Zero new sequential stages; zero impact on the 32-64-concurrent section fan-out; render changes are pure string work. Fast-subset mode = Level-2 harness (banked corpus, minutes); full run = slate flags on, unchanged wall-clock shape.

## 8. Build plan for Opus (ordered; ~LOC; respects the 200-LOC PR cap by splitting)

| PR | Content | Files | ~LOC |
|---|---|---|---|
| 1 | `DeliverableSpec` + regex primary + LLM co-primary + merge + O2 slot wiring + unit battery | `src/polaris_graph/retrieval/deliverable_spec_extractor.py`, tests | 180 code (+tests exempt) |
| 2 | scope-gate seam + protocol key + checkpoint write/load + resume-path threading + slate flags | `nodes/scope_gate.py` (after `:1059`), `run_honest_sweep_r3.py`, `run_gate_b.py` | 90 |
| 3 | `render_outline_deliverable_block` + `render_section_style_block` + kwarg threading through `generate_multi_section_report`/`_call_outline`/`_select_section_system_prompt` + evidence-gap section render | `generator/multi_section_generator.py` | 160 |
| 4 | reference-style renderer + assembler ordering + Methods adherence block + Level-1/2 harness | `run_honest_sweep_r3.py` (`:3999`, `:5230`, Methods block), `scripts/deliverable_spec_harness.py` | 180 |

DON'Ts for Opus (verbatim into the brief): no edits under strict_verify/provenance/roles/topic-gate/selection/junk-deletion; no fabricated reference metadata; no section-count caps from length asks; user structure asks are REQUIRED-IF-GROUNDED additive, never allow-list replacements on the clinical path; every new behavior behind its flag, OFF = byte-identical; Fable decides root cause on any loop failure, Opus builds (memory 2026-07-08).

## 9. Forward hooks

- DESIGN "holistic whole-report review" (audit gap #1): when the reflector pass is wired, hand it the same `deliverable_spec` so tone/structure adherence is CHECKED whole-report, not only requested per-section. The spec object is deliberately a plain dict in the protocol so that consumer costs nothing to add.
- Outline-refine round (audit gap #3): the basket-digest outline planner should keep the same deliverable block — the block is prompt-appended, so it survives that redesign unchanged.
