# Compose-Contract-Injection — Consolidated Plan (OPUS)

Commit ground truth: `/home/polaris/wt/outline_agent` @ `b67506a`
(`b67506a399b6102223cf9aad0be4b5e9b9828544`). Every code claim below was
cross-checked against the real tree; line numbers are from that commit.

## Which models returned

- **codex.md** — returned (full). ("The fix is mostly wiring, not a generator
  rewrite…"). Its content is byte-identical to the tail of `codex.err`.
- **kimi.md** — returned (full). Kimi K3, self-labeled, with usage block.
- **fable.md** — **DID NOT RETURN.** No `fable.md` exists in the pack directory
  (`ls` confirms absence). Nothing in this plan is attributed to Fable.
- **pack.md** — the grounded context pack (not a model); used as the code map and
  re-verified against source.

Both returning models (codex, kimi) independently converge on the same shape:
the plumbing already exists and is starved at one call site; the fix is ~80%
threading + a drop-point repair, ~20% projection glue. I agree, **with one
correction neither model made** (see Adjudication §1).

---

## KEY CORRECTION vs. both models — the compose projection object already exists

Both codex and kimi propose **building a new object** — codex a
`ComposeProjection(...)` bundle; kimi a new `ResearchContract.to_compose_projection()`
returning a new frozen `ComposeProjection`. **This is redundant and would be
over-engineering.** The real tree already ships the compile method and object:

`src/polaris_graph/planning/compose_render_projection.py`
- `class ComposeRenderProjection` (line 118) — plain-data compose+render view.
- `from_contract(contract)` (line 201) — pure, fail-open compiler. It **already**
  populates:
  - `tone/audience/point_of_view/hedging` from `_TONE_DIMS/_AUDIENCE_DIMS/_POV_DIMS/_HEDGING_DIMS`
  - `doc_type` from `_DOCTYPE_DIMS` (line 94: includes `deliverable.kind`,
    `deliverable.document_type`, `deliverable.structure`, `document_type`, `kind`)
  - `required_titles` + `ordered` from `contract.sections` — **only** sections with
    `exact_title_lock=True` (lines 225-256; a required *topic* is never a heading)
  - `length_note` (planning context, never a cap)
- `voice_advisory()` (line 142) — the prose-only voice advisory string.
- `document_type()` (line 169), `required_titles`, `render_plan()` (line 179).
- `compose_voice_advisory(proj)` (line 294) — the generator-seam entrypoint; the
  generator already calls it (multi_section_generator.py line 9836).

So the minimal plan **reuses `from_contract`**; it does NOT add a new projection
class or a new `to_compose_projection()` method. What is genuinely missing:

1. The **gate drop-point** still drops `deliverable.kind` and voice dims and never
   populates `contract.sections` → so `from_contract` reads an empty projection.
2. The **call site** (scripts/run_honest_sweep_r3.py line 15861) threads none of
   `compose_projection` / `deliverable_spec` / `scope_spec`.
3. The **section advisory** carries voice only — no doc-type framing line, no
   per-section role. `voice_advisory()` must gain an additive doc-type preamble;
   per-section role is a separate additive append.
4. `ComposeRenderProjection` has no `deliverable_spec` / `scope_spec` view the
   outline seam wants (`_call_outline` reads `_spec_read(deliverable_spec,
   "required_sections", [])` and `build_requirements_block(deliverable_spec,
   scope_spec)`). We expose thin adapters, not a new object.

---

## (a) Contract-carry change — unblock kind, populate sections, carry voice

**File:** `src/polaris_graph/planning/research_planning_gate.py` (degraded /
`compiler_degraded` constructor, ~lines 460–519). The admit tuple today (line 491):

```python
if cand.dimension not in (
    "deliverable.format", "deliverable.length", "rhetoric.tone",
):
    continue
```

Two defects: (i) `deliverable.kind` and voice dims are absent → dropped; (ii) it
matches on **raw** `cand.dimension` while appending `cand.canonical_dimension()`
(line ~486) — so a `document_type`/`kind` variant is dropped even after "adding
kind" unless we match on the canonical form (kimi's point #1, verified against the
constructor: it does append `cand.canonical_dimension()`).

**Change — one source of truth, matched on the canonical dimension:**

```python
# Single admit set, reconciled with the dims the compose projection reads
# (compose_render_projection._TONE_DIMS/_AUDIENCE_DIMS/_POV_DIMS/_HEDGING_DIMS/
#  _DOCTYPE_DIMS) + format/length. Importing those frozensets keeps admit and
# projection from silently diverging (a half-fix no task-72 test catches).
from src.polaris_graph.planning.compose_render_projection import (
    _TONE_DIMS, _AUDIENCE_DIMS, _POV_DIMS, _HEDGING_DIMS, _DOCTYPE_DIMS,
)
_DELIVERABLE_ADMIT_DIMS = frozenset(
    {"deliverable.format", "deliverable.length"}
    | _DOCTYPE_DIMS | _TONE_DIMS | _AUDIENCE_DIMS | _POV_DIMS | _HEDGING_DIMS
)
...
if cand.canonical_dimension() not in _DELIVERABLE_ADMIT_DIMS:
    continue
```

(If importing the underscored frozensets is judged too intimate, promote them to a
public name in `compose_render_projection.py` and import that. Do **not** copy the
sets — two hand-maintained tables will drift.)

**Kind force:** admitted `deliverable.kind` stays `force=FORCE_PREFER` exactly like
the other deliverable candidates (the constructor already sets FORCE_PREFER, line
~509). This is correct and lossless: an inferred kind *cannot* be hard anyway
(`HARD_ELIGIBLE_ORIGINS` invariant). Do NOT add `deliverable.kind` to
`_AUTHORITATIVE_DIMENSIONS` (line ~296) — that frozenset feeds the monotonic
retrieval merge; a deliverable preference there is a category leak across
`STAGE_OWNERS`. (kimi #3; confirmed `_AUTHORITATIVE_DIMENSIONS` is source/date/
exclusion only.)

**Sections:** admit **explicit, user-named** section-title candidates into
`SectionRequirement` objects. Preserve verbatim: title term (with real
origin/span), encounter order (unless an explicit order was stated), purpose,
`required`, coverage links. `exact_title_lock` **only** when the title term's
origin ∈ `HARD_ELIGIBLE_ORIGINS` — reuse `SectionRequirement.from_dict`'s existing
downgrade rule; the constructor must not bypass it (codex; kimi). **Do not
manufacture `contract.sections` from the kind** — "decision memo" does not prove
the user typed headings "Options"/"Recommendation"; kind→section skeletons are
*preferences*, routed through the soft outline channel (§c), never `sections`
with locks (codex explicit; kimi allows an *inferred, unlocked, disclosed* default
skeleton only when kind itself is explicit — I adjudicate to **codex's stricter
line**: keep `sections` for explicit user titles only; kind-derived roles live in
the projection's preference channel. Simpler, and it removes an invention surface).

**Voice:** already handled by the admit-set expansion above — voice terms are
deliverable terms on the tone/audience/pov/hedging dims; once admitted,
`from_contract` reads them. No separate work.

**SHA honesty (both models, correct — surface it, do not smuggle it):** admitting
kind/voice/sections changes the *degraded* contract's `to_dict()` → its
`contract_sha256` changes vs. today. That is the fix landing, not a regression.
State it in the change note. Assert the invariant that `to_scope_terms()` output
is **unchanged** by deliverable admission (deliverable terms don't enter scope), so
retrieval behavior does not drift even when caches key on the SHA. Legacy
non-degraded contracts are unaffected (generic-IR fields still serialize only when
non-default → their SHAs are stable).

## (b) Compose projection + injection point into the section-writer prompt

**Object / builder:** REUSE `ComposeRenderProjection.from_contract(_shape_contract)`.
No new class.

**Build once, thread at the call site.** `scripts/run_honest_sweep_r3.py`: the
contract is already in scope as `_shape_contract` (line 14396, assigned from the
gate artifact at 14412). Immediately before the `generate_multi_section_report`
call (line 15861), compile the projection and thread three kwargs:

```python
from src.polaris_graph.planning.compose_render_projection import from_contract
_compose_proj = from_contract(_shape_contract)   # empty/inert if contract is None/shapeless
...
multi = await generate_multi_section_report(
    research_question=q["question"],
    evidence=evidence_for_gen,
    ...
    compose_projection=_compose_proj,
    deliverable_spec=_deliverable_spec_from(_compose_proj),
    scope_spec=_scope_spec_from(_shape_contract),
    ...
)
```

`_deliverable_spec_from` / `_scope_spec_from` are **thin adapters** (see §c) — a
dict `{"required_sections": proj.required_titles, ...}` and a scope-emphasis view.
They are the only new glue and are trivially testable.

**Injection point — file:function and exact seam:**
`src/polaris_graph/generator/multi_section_generator.py`, function `_call_section`,
line **4071–4072**:

```python
if voice_advisory_text:
    system = f"{system}\n\n{voice_advisory_text}"
```

This is the additive prompt-preamble seam. It appends AFTER the frozen
`SECTION_SYSTEM_PROMPT_TEMPLATE` (selected at 4055) and after the domain advisory
(4066). Voice/compose guidance is therefore strictly a suffix on the system prompt;
the faithfulness contract (rules 1–8: evidence-only, every-sentence-cited, verbatim
numbers, "do not write a heading") is the unchanged prefix.

**Two additive layers into the advisory the generator computes at line 9830-9838:**

1. **Doc-type framing (global, per-report).** Extend `voice_advisory()` (or a new
   sibling `compose_advisory()` called at the same seam) so the string returned to
   `_voice_advisory_text` ALSO carries a doc-type framing line when
   `proj.doc_type` resolves. The framing prose is **DATA, not control flow** —
   store a per-archetype `compose_directive` string next to
   `report_skeleton.ARCHETYPES`, looked up by the resolved archetype key (reuse
   `report_skeleton.KIND_SYNONYMS` to resolve `doc_type` → key; unmapped ⇒ opaque
   ⇒ generic/default directive + disclosure). No `if kind == "memo"` in code.

2. **Per-section role (per-section).** The once-built `_voice_advisory_text` cannot
   carry "this is section 2 of N, 'Options Compared', its job: …". Append the role
   line at the `_run_section` → `_call_section` boundary from
   `proj` keyed by the current `section.title`. Still one additive append; still
   `""` ⇒ inert. (kimi #6; codex "compose_section_advisory(projection, section)".)

**Hard rules for the preamble (both models, and I enforce them as tests in §f):**
- **Directive-only, zero content.** No claims, no numbers, no `ev_\d+`, no canned
  sentences ("In this memo we recommend…"). A canned content sentence has no span
  ⇒ `strict_verify` drops it ⇒ retry churn. Invariant test: rendered advisory
  matches neither `\d` nor `ev_`.
- **Length precedence.** `SECTION_SYSTEM_PROMPT_TEMPLATE` rule 8 targets 10–18
  sentences; `length_note` is already worded as "planning context (not a hard
  cap)" (line 285) — keep it advisory; if a compose length directive is added it
  must explicitly supersede rule 8 or say nothing, never silently contradict it.
- **Coverage > Insight > Readability.** Voice may never reduce evidence coverage.
- Do NOT restructure `SECTION_SYSTEM_PROMPT_TEMPLATE`, touch citation rules, or ask
  for headings. Additive suffix only.

## (c) Outline-agent prompt injection

`_call_outline` already implements the full governance mechanism (pack §5;
verified): reads `_spec_read(deliverable_spec, "required_sections", [])`, swaps to
`OUTLINE_SYSTEM_PROMPT_REQUIRED` when non-empty, uses required titles as the parse
allow-list, and appends `build_requirements_block(deliverable_spec, scope_spec)`
(`src/polaris_graph/generator/outline_digest.py` line 909) to the user prompt. The
work is **routing discipline**, not new prompt code.

**Two-channel routing (the trap both models flag; I adopt it):**
- **Hard channel → `required_sections`:** ONLY sections with `title.origin ∈
  HARD_ELIGIBLE_ORIGINS`, `required=True`, `exact_title_lock=True`. This is exactly
  what `from_contract` already puts in `proj.required_titles` (lines 225-256), so
  the adapter is `{"required_sections": proj.required_titles}`. Feeding
  inferred/kind-derived titles here is a **force leak** — `OUTLINE_SYSTEM_PROMPT_REQUIRED`
  treats the list as authoritative/verbatim/"exactly those, no more, no fewer,"
  making an inferred term act HARD.
- **Soft channel → guidance line in `build_requirements_block`:** kind-derived /
  prefer structure ("Deliverable kind: decision memo — plan bottom-line-first,
  options, tradeoffs, recommendation") leaves the domain-selected system prompt and
  the default allow-list intact. This is where the kind→role *preferences* live.

**Precedence:** (1) explicit ordered contract sections; (2) other hard coverage
obligations; (3) kind-profile preferred roles; (4) generic outline behavior.

**Coverage-vs-exact-set conflict (kimi's subtlest point; adopt):** `FORCE_PREFER`
may never starve coverage, but "EXACTLY those sections, no more" can. Use exact-set
semantics only when the union of the required sections'
`coverage_requirement_ids` covers all required `CoverageRequirement`s; otherwise
allow the outline to append coverage-derived sections after the required ones
(disclosed). `SectionRequirement.coverage_requirement_ids` is the resolution key
already on the schema. The REQUIRED prompt's undersupply rule ("STILL emit it…
disclosed downstream") handles the inverse. **Over-engineering watch:** if the
current corpus never exercises this conflict, ship the exact-set path and leave a
disclosed TODO — do not build the union-coverage arbiter speculatively.

**Gap search** consumes the same stable section/coverage IDs: a gap is "required
obligation X is undersupplied," never "the doc is a review, search journals." No
kind literal in query control flow.

## (d) report_skeleton demoted to safety-net

`report_skeleton.py` stays PURE (no I/O, no provenance import) and the post-hoc
application in `scripts/run_honest_sweep_r3.py` (~line 17605, `_resolve_archetype`
/ `order_report_blocks` / `build_framing_md`, verified present) remains — but
**demoted to a fallback / block-order safety layer**:
- Outline (§c) determines which substantive sections are composed.
- Section advisory (§b) determines how they read.
- `order_report_blocks` only PERMUTES already-produced opaque blocks (the multiset
  permutation invariant + fail-loud/never-abort fallback to legacy concat is
  intact).
- `DEFAULT_ARCHETYPE="review"` is used only when no kind resolves (silent contract,
  opaque/unmapped kind), disclosed in `assumptions_ledger`. An unmapped raw kind is
  preserved verbatim in the projection AND in `resolve_archetype`'s opaque return;
  the fallback must not erase it.

**Duplicate-structural-section guard (codex; kimi):** a contract-shaped outline may
already produce a "Key Findings"/"Bottom Line" or a framing section, while
`build_framing_md` / the pipeline Key-Findings block also inject one. Two mitigations:
1. **Framing heading** — low risk: template rule 7 forbids the *writer* from
   emitting headings, and `build_framing_md` is a claim-free `## {framing_title}`
   paragraph. But an *outline required title* equal to the framing title
   ("Introduction and Scope") CAN collide. Before adding renderer-owned framing,
   check the contract/planned headings and skip the injection if an equivalent
   block exists (reuse the Methods-carve-out pattern at line 17636,
   `_contract_requires_section`). Contract sections take precedence; skeleton fills
   only missing renderer structure.
2. **Key Findings / Bottom Line** — reserve those titles for the pipeline KF block;
   reject/downgrade a required outline section that duplicates them in section
   routing, rather than adding dedup machinery to the skeleton.

Do not claim "no conflict" without this guard — that claim would be false (codex).

## (e) Faithfulness-safety + OFF byte-identical

**`provenance_generator.py` 0-diff.** No signature, call-site, or import change to
`strict_verify` / `verify_sentence_provenance` / `require_number_match=True` / span
grounding / D8 / comparative-atom recovery. `strict_verify` is a pure function of
(sentences, evidence); this design changes neither input. The evidence pool is
untouched; the injected advisory contains no checkable atoms (enforced by the
no-`\d`/no-`ev_` test in §f). If the model parrots advisory prose, the sentence
carries no `[ev_XXX]` marker and the **unchanged** gate drops it — the gate is the
backstop, not a casualty. All steering is **upstream** (system-prompt suffix +
outline title governance), never a new drop/keep rule.

The only two corruption vectors, both closed by construction: (a) injecting factual
content into the advisory — forbidden, test-enforced; (b) placing guidance in the
*evidence region* of the user prompt where it reads as instruction — avoided by
using the **system-prompt** seam (line 4071) exclusively.

**Honest scope of "byte-identical":** the *verifier implementation and its
treatment of any given (draft, evidence) pair* is unchanged. Prompt steering can
change the *draft the model proposes*, so final prose is not guaranteed identical
to a prior blind-composition run — say this plainly (codex §5; kimi §5). What IS
byte-identical is the **OFF path**.

**OFF byte-identical argument:**
- `compose_projection=None` ⇒ generator guard at line 9831 skips ⇒
  `_voice_advisory_text=""` ⇒ line 4071 `if voice_advisory_text:` false ⇒ system
  prompt unchanged.
- The projection compiler must yield an **inert** projection (empty strings / empty
  lists), and `voice_advisory()` already returns `""` when no voice
  (line 161-162) and the doc-type/role additions must return `""` when
  `doc_type`/role absent. `from_contract(None)` returns an empty projection
  (line 208). Equivalent to passing `None`.
- `deliverable_spec=None` ⇒ `_required_sections=[]` ⇒ domain system prompt + default
  allow-list + empty requirements block (`build_requirements_block` returns "").
- `PG_REPORT_SHAPE=0` ⇒ legacy machinery-first concat (sweep else-branch).
- Generic-IR fields serialize only when non-default ⇒ legacy contract SHAs stable.
- **Do not** append empty labels ("COMPOSITION CONTRACT:") — even whitespace breaks
  the champion prompt hash (codex §6; kimi). Golden-string test asserts byte
  equality to HEAD with all three specs None.
- Precise claim (kimi): the degraded-path fix INTENTIONALLY changes
  *degraded-contract* SHAs (one-time cache miss on `contract_sha256`-keyed
  scoping). Disclose it; do not smuggle it as "no change."

## (f) Metamorphic cross-deliverable-kind tests + anti-hardcode grep

Same question + same evidence; vary ONLY `deliverable.kind`. Assert projection
contents AND captured outline/section prompt strings.

| Kind | Expected adaptation (archetype key) |
|---|---|
| `literature review` / `survey` | `review` — Intro & Scope framing, thematic synthesis directive |
| `systematic review` / `meta-analysis` | `systematic_review` — review-question/method/synthesis/limitations roles; NO invented PRISMA claim |
| `memo` / `decision memo` | `memo` — Bottom-Line/BLUF-first directive, options, tradeoffs, decision-oriented voice |
| `policy brief` / `brief` | `brief` — executive-summary framing, concise implications |
| `comparison` / `market scan` | `comparison` — Scope & Criteria, symmetric comparison dimensions |
| `primer` / `overview` / `explainer` | `explainer` — Overview, concepts/mechanisms, explanatory voice |
| `slide deck` (unmapped) | opaque_kind preserved verbatim + DEFAULT review + assumptions-ledger disclosure |

Additional assertions:
1. **Negative-literal (kills task-72 bleed-through):** memo preamble must NOT
   contain "thematic"/"Introduction and Scope"; review preamble must NOT contain
   "Bottom Line". Each archetype's directive contains only its own framing.
2. **Routing:** explicit locked sections ⇒ `OUTLINE_SYSTEM_PROMPT_REQUIRED` + exact
   allow-list; kind-only (no locked sections) ⇒ guidance line in requirements block,
   domain system prompt + default allow-list UNCHANGED (no force leak).
3. **Force-leak guard:** an inferred/kind-derived title never appears in
   `required_sections`; `exact_title_lock` honored only for
   `origin ∈ HARD_ELIGIBLE_ORIGINS`.
4. **OFF golden:** all specs None ⇒ section system prompts + outline user prompts
   byte-equal to HEAD capture.
5. **Advisory hygiene:** rendered advisory matches neither `\d` nor `ev_`.
6. **Coverage-not-a-heading:** a required *topic* (CoverageRequirement) never
   becomes a `required_titles` entry (already enforced by `from_contract`; regress-test it).
7. **Skeleton:** permutation multiset invariant holds per kind; duplicate-KF guard
   fires when a required section is titled "Bottom Line"/"Key Findings".
8. **`strict_verify` call unchanged:** assert it still receives
   `require_number_match=True` and the same evidence pool (spy/argument capture).
9. **Empty contract == all-None:** `from_contract(empty)` prompts byte-equal to the
   None-spec prompts.

**Anti-hardcode grep (CI gate):**
```bash
# No per-kind literal in compose/outline control flow. Kinds live as DATA in
# report_skeleton.ARCHETYPES / KIND_SYNONYMS and the compose_directive table.
grep -nE '"(memo|brief|review|comparison|explainer|systematic_review|policy brief|market scan|decision memo|literature review)"' \
  src/polaris_graph/generator/multi_section_generator.py \
  src/polaris_graph/generator/outline_digest.py \
  src/polaris_graph/planning/compose_render_projection.py \
  | grep -vE 'ARCHETYPES|KIND_SYNONYMS|import|# data|compose_directive'
# Expect: zero hits. Also assert no kind detection off the raw prompt:
grep -nE 'prompt.*\.lower\(\).*(review|memo|brief)|in prompt\b' \
  src/polaris_graph/planning/research_planning_gate.py
# Kind must come from _first_deliverable_kind_value / _DOCTYPE_DIMS off the
# contract, never regex on the prompt (kimi #3: "review whether to renew" is a memo).
```

---

## Disagreements + adjudication

1. **New projection object vs. reuse (codex `ComposeProjection`; kimi
   `to_compose_projection()`) — ADJUDICATE: reuse `ComposeRenderProjection.from_contract`.**
   Neither model saw that the object + compiler already exist and already read
   doc_type/voice/sections. Building a second one is redundant and risks a second
   synonym/dim table that drifts. Extend the existing `voice_advisory()`/add a
   sibling; add thin `deliverable_spec`/`scope_spec` adapters. This is the single
   biggest correction and it shrinks the diff.

2. **Kind-derived default sections — codex (never manufacture `sections`) vs. kimi
   (allow inferred, unlocked, disclosed skeleton when kind is explicit) —
   ADJUDICATE: codex's stricter line.** Keep `contract.sections` for explicit user
   titles only; kind→role preferences ride the soft outline channel (§c) as
   guidance, not as `SectionRequirement`s. Removes an invention surface and is
   simpler; `from_contract` already ignores non-locked sections for
   `required_titles`, so an inferred skeleton would only muddy the object.

3. **Global advisory string vs. per-section role — codex/kimi agree it must be
   per-section; the pack's current seam threads one global `_voice_advisory_text`.
   ADJUDICATE: two additive layers** — global doc-type framing in
   `_voice_advisory_text`, per-section role appended at the `_run_section`
   boundary. Both inert when empty.

4. **Coverage-vs-exact-set arbiter — kimi builds it; codex doesn't mention it.
   ADJUDICATE: specify it, gate on need.** Correct and real, but only if the corpus
   exercises the conflict. Ship exact-set + disclosed fallback; build the
   union-coverage arbiter only when a test actually hits it (over-engineering watch).

## Over-engineering watch

- **Do NOT** add a new `ComposeProjection` class / `to_compose_projection()` method
  — reuse `from_contract`. (Both models would have.)
- **Do NOT** manufacture `contract.sections` from the kind — invention surface.
- **Do NOT** build the union-coverage / exact-set arbiter until a test hits it.
- **Do NOT** promote `_DOCTYPE_DIMS`/voice dims into a *third* copy in the gate —
  import the one in `compose_render_projection.py` (or publicize it), single source.
- **Do NOT** hoist `ARCHETYPES`/`KIND_SYNONYMS` into a new shared module unless the
  import from `report_skeleton.py` (pure) proves circular — a plain import is
  cheaper than a new module.
- **Do NOT** add dedup machinery to `report_skeleton` — reserve KF/Bottom-Line
  titles upstream in routing instead.
- Keep `length_note` advisory; do not turn it into a truncation gate.
- Resist expanding the section advisory into paragraphs — a few directive lines;
  every extra sentence is prompt-hash surface and verbosity risk.

## Faithfulness/OFF verdict

`faithfulness_safe = true` — all steering upstream; no claims/citations injected;
`provenance_generator.py` 0-diff; gate is the unchanged backstop.
`off_byte_identical = true` — for the OFF path (all specs None / `PG_REPORT_SHAPE=0`).
Degraded-contract SHAs intentionally change (disclosed), and steered drafts are not
guaranteed prose-identical to prior blind runs — the byte-identical claim is scoped
to the OFF path and to the verifier's treatment of a fixed (draft, evidence) pair.
