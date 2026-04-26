# V30 Phase-2 — Joint User-Wishlist Analysis (7 user-named wishes)

**Date:** 2026-04-26
**Status:** Pass-2 — Codex cross-review integrated (verdict: PARTIAL → green after fixes below)
**Source documents:**
- Codex (gpt-5.4 xhigh): `outputs/codex_findings/v30_user_wishlist_plan/findings.md`
- Claude framing (initial): `.codex/v30_user_wishlist_brief.md`
- Real-user research (35 + 32 primary sources): `outputs/codex_findings/v30_real_user_wishlist/SYNTHESIS.md`
- Joint commercialization plan: `outputs/codex_findings/v30_phase2_to_production_plan/JOINT_PLAN.md`
- **Codex cross-review** (PARTIAL verdict): `outputs/codex_findings/v30_joint_analysis_review/findings.md`

This document is the joint Claude+Codex analysis of the 7 user-named wishes.

## Pass-2 changes (Codex review integrated)

Codex returned PARTIAL with 7 specific edit recommendations. All 7 integrated:

1. **Wish #1 renamed** from "Workspace Brief" to "Question-Bound Corpus Brief" — the broader label over-promised. Living-wiki behavior remains Phase D.
2. **Wish #2 estimate raised** from 15-25 to 25-40 eng days. The 15-25 figure was parser/glue work; real Phase B work is workspace data model + permissions + retention + deletion + provenance mapping.
3. **Composition section rewritten** — canonical object is an "audit graph / claim-evidence IR" with Evidence Inspector as primary renderer; all other outputs are derivative projections with back-links to claim IDs.
4. **Memory split into 3 layers**: session memory / workspace memory / global-system memory. Only workspace memory may participate in the audit lane by default, with user-visible lineage + delete controls.
5. **1-click UX rewritten** — "immediate progress surface" was too weak. Audit-native progressive surfaces specified: pre-flight estimate, parse progress, live source discovery with tier mix, frame coverage filling in, contradiction queue before final synthesis, first verified claim cards.
6. **PRD bundle scope raised** from 52-86 to 70-110 eng days = 7-11 weeks. The lower range is only feasible if wish #1 stays extremely narrow.
7. **Sequencing note added**: if one derivative artifact moves into late Phase B, citation-bound deck beta is the better candidate than broader corpus-brief promise.

---

## TL;DR — the 7 verdicts at a glance (pass-2)

| # | Wish | V30 today | Trap? | Moat impact | Phase | In next ship? |
|--:|------|:---------:|:----:|:------------:|:-----:|:------:|
| 1 | WikiLLM → renamed **Question-Bound Corpus Brief** | partial | trap if free-form | amplify if bounded / dilute if open | B (narrow brief) / D (living wiki) | YES — narrow form, dependent on #2 |
| 2 | Massive data upload + analysis | partial | trap if 300+ PDFs/session | amplify if first-class evidence / dilute if fuzzy RAG | B (10-50 docs) / D (300+) | YES — bounded form, **25-40d (raised)** |
| 3 | Snowball memory — split into **passive notes** vs **retrieval-active memory** | partial | trap if silent latent | neutral-to-amplify if user-governed / dilute if invisible | B (passive notes) / C (retrieval-active) | PARTIAL — passive notes only |
| 4 | Chart / table / artifact | partial | NO | amplify | B | YES — cited tables + numeric charts (core) |
| 5 | Infographic | none | **TRAP** | **dilute** | D (or never) | NO |
| 6 | 1-click slide deck | none | conditional | amplify if citation-bound + appendix | C (late-B beta = better candidate than broad #1) | NO unless one slot opens |
| 7 | 1-click video/audio | none | **TRAP** | **dilute** | D (derivative only) | NO |

**Three explicit traps converged across both runs:** infographic, video/audio, massive-upload-at-scale.

**Independently confirmed by real-user research:** the wishlist sweep (35 + 32 primary sources) found that output-format commodities (slides/podcasts/infographics) have high user demand BUT low differentiation potential for audit-grade. NotebookLM and Manus already polished — V30 cannot win on visual polish, and audio/visual compression strips inline citations (V30's biggest moat becomes invisible).

---

## Per-wish deep dive

### Wish 1 — WikiLLM → renamed "Question-Bound Corpus Brief" (Codex correction)

**User expectation (NotebookLM/Perplexity Spaces bar):**
- Dump sources in, get a living knowledge page with clean summaries, FAQs, timelines
- Cross-document synthesis in minutes
- Wiki updates as new sources arrive
- System remembers corpus without manual prompt choreography

**Codex's naming correction (accepted):** "Workspace Brief" over-promised.
Users hear "living notebook/wiki summary of my corpus." V30 today can
plausibly support "answer one bounded question over this selected corpus
and emit a cited brief." That is narrower. Renamed accordingly.

**V30 today: PARTIAL**
- `src/polaris_graph/wiki/wiki_composer.py` exists
- Mesh compose/artifact rendering in `src/polaris_graph/wiki/mesh/compose/`
- BUT: product is still query/report-centric, not workspace-corpus-centric
- Uploaded docs currently injected into session state and chunked into ad-hoc GOLD evidence — NOT a persistent inspectable corpus-brief product

**Trap flag: CONDITIONAL**
- Free-form / unconstrained = TRAP
- Question-bound corpus brief = SAFE (every paragraph inline-cited OR labeled "insufficient support")
- Living-wiki framing = TRAP for now (Phase D)

**Moat impact:**
- AMPLIFY if shipped as "citation-bound question-bound corpus brief"
- DILUTE if shipped as open-ended ambient knowledge prose or framed as living wiki

**Phase: B (narrow question-bound brief), D (living corpus wiki)**
- 12-20 eng days for narrow citation-bound brief — **but explicitly dependent on wish #2 landing first**
- 30-45 eng days for true NotebookLM-class living corpus wiki (Phase D)

**Acceptance criteria:**
- Corpus is explicit, user-selected, user-visible; no hidden web mixing unless requested
- Brief is BOUND TO ONE USER QUESTION over that corpus (not autonomous summary)
- Every paragraph has inline citations OR explicit "insufficient support" language
- Clicking a citation shows document/page/span, not just URL (Evidence Inspector view 1)
- Regeneration after adding sources preserves prior source boundaries and contradiction disclosures

**Joint verdict (pass-2):** SHIP AS "QUESTION-BOUND CORPUS BRIEF" IN PHASE B, dependent on wish #2 (bounded upload) landing first. Defer the unconstrained living-wiki version to Phase D. Do NOT use "Workspace Brief" or "WikiLLM" labels in product copy — they import the wrong expectation.

---

### Wish 2 — Massive data upload + analysis

**User expectation:**
- "I can drop an entire diligence room or literature pack and the system will parse, index, answer, and generate artifacts without handholding"
- 300-500 PDFs/session (per the seed message)

**V30 today: PARTIAL — already substantial primitives**
- `src/polaris_graph/document_ingester.py` parses PDF/DOCX/PPTX/XLSX/TXT/HTML/images/audio locally
- `src/polaris_graph/memory/local_document_rag.py` creates session-scoped Chroma collections
- `scripts/live_server.py` exposes upload, list, import-url, import-text, source-brief APIs
- `src/polaris_graph/graph.py` loads `document_ids` into state and ingests them

**Trap flag: CONDITIONAL**
- "10-50 docs/workspace persistent" = SAFE
- "300-500 PDFs/session" interpreted as default user behavior = TRAP. Pulls roadmap into ingestion/RAG infrastructure product where parser QA, storage, permissions, retention dominate engineering.

**Moat impact:**
- AMPLIFY if uploads become first-class audited evidence (every chunk maps to document, page/slide/sheet/timecode, parser version)
- DILUTE if uploads are just fuzzy vector context with weak traceability

**Phase: B (bounded), D (massive)**
- **25-40 eng days (raised from 15-25 per Codex)** for solid beta corpus layer
  — 30-45 if page/slide/sheet lineage and delete semantics are included honestly
- 40-70 eng days for 300-500 PDFs/session with durable indexing, backpressure, dedupe, retention, ops safety

**Why the estimate was raised (Codex correction):**
- Current upload path is NOT workspace-scoped — repo stores docs globally under `data/documents/{doc_id}` with global list/detail/delete endpoints. This is a data-model change, not "more polish."
- Current retrieval is `LocalDocumentRAG("docs_{session_id}")` — session-scoped, not persistent workspace corpus retrieval.
- Uploaded docs are chopped into ~2000-char chunks and injected as GOLD evidence. That is materially weaker than "page/span/parser-version-grade corpus provenance" the audit-grade label requires.
- No real workspace manifest, permission model, parser-status pipeline, or uploaded-doc provenance map at product grade exists yet.
- The real Phase-B work = workspace scoping + auth + deletion semantics + provenance mapping + parser status UX. NOT just parser support.

**Acceptance criteria:**
- Upload status is per-document and per-parser-step, with failures surfaced
- Every retrieved chunk maps to document + page/slide/sheet/timecode + parser version
- User can filter analysis to uploaded corpus only / web only / blended mode
- Workspace persistence exists; session-only Chroma not enough
- Documents are deletable with audit trail (who/when/why)
- Per-workspace storage isolation enforced

**Joint verdict (pass-2):** SHIP BOUNDED FORM (10-50 docs/workspace) IN PHASE B at 25-40 eng-day budget. The Evidence Inspector views naturally extend to uploaded corpora — a clinical brief drawing from uploaded SAP/CSR/protocol PDFs is a winning V30 demo. Defer 300+ to Phase D or treat as separate ingestion product.

---

### Wish 3 — Snowball memory: split into PASSIVE NOTES vs RETRIEVAL-ACTIVE MEMORY (Codex correction)

**Codex's split (accepted):** "Memory" was conflated. There are two
distinct features here with different risk profiles:

| Feature | Phase | Risk | Description |
|---------|:----:|:----:|-------------|
| **Passive saved workspace notes** | B | low | User pins a source, saves a note, bookmarks a claim. Does NOT silently steer synthesis. |
| **Retrieval-active memory** | C | high | Prior facts retrieved into future runs, labeled as memory-derived, with inspect/delete controls. |
| **Global/system memory** | quarantined | severe if leaks | Operator/product priors. Should NOT silently influence the audit lane by default. |

**User expectation:**
- System remembers prior sources, notes, decisions, context across sessions
- No re-uploading or re-explaining
- Persistence + reuse + inspectability + edit/delete controls + low drift

**V30 today: PARTIAL — primitives exist, UX does not, AND multiple memory layers blur together**
- `src/polaris_graph/memory/cross_vector.py` promotes high-quality evidence to GLOBAL LTM in Chroma — this is global/system memory and is currently NOT quarantined from audit-lane runs
- `src/polaris_graph/memory/session_feedback.py` records strategy outcomes — session memory
- `src/polaris_graph/memory/evidence_hierarchy.py` stores L0/L1/L2 evidence summaries — session memory
- `src/agents/analyst_agent.py` enriches facts into a knowledge graph — currently mixed
- `scripts/static/js/memory_dashboard.js` UI concept exists but doesn't enforce the split

**Trap flag: CONDITIONAL — silent memory is the trap**
- USER-VISIBLE + LABELED + WORKSPACE-SCOPED + USER-GOVERNED = SAFE
- Silent latent bias mutating future outputs without provenance trail = TRAP
- Global/system memory bleeding into audit lane = SEVERE TRAP

**Real-user research convergence:** The wishlist sweep found wish #18 (cross-notebook / cross-workspace memory) is high-frequency. Atlasworkspace.ai users explicitly named the issue. Critical UX constraint: **must be USER-VISIBLE and DELETABLE**.

**Moat impact:**
- AMPLIFY if memory is split, labeled, workspace-scoped, user-governed, with global memory quarantined
- DILUTE if memory becomes silent latent bias
- DESTROYS MOAT if global/system memory silently injects priors into audit-lane runs

**Phase split:**
- **Phase B**: passive saved workspace notes only (5-10 eng days). User explicitly pins/saves; no synthesis influence.
- **Phase C**: retrieval-active workspace memory (10-18 eng days). User-visible, labeled in Evidence Inspector view 1 as "memory-derived."
- **Phase D**: autonomous accumulation (25-40 eng days). With freshness, invalidation, collaborative editing.

**Acceptance criteria (per layer):**
- *Passive notes (B)*: pins/notes/bookmarks visible in workspace UI, do not feed retrieval, never appear in audit-lane synthesis
- *Retrieval-active (C)*: every memory-derived retrieval is LABELED, attributable, removable; never blended invisibly
- *Global/system memory*: quarantined from audit lane by default; explicit user opt-in required to use; clearly labeled as operator-curated
- Workspace boundaries strict across all layers; no cross-customer leakage
- Freshness/staleness rules for time-sensitive topics

**Joint verdict (pass-2):** SHIP PASSIVE NOTES IN PHASE B (low risk). RETRIEVAL-ACTIVE MEMORY IN PHASE C (high risk, needs careful UX). GLOBAL/SYSTEM MEMORY QUARANTINED FROM AUDIT LANE BY DEFAULT — explicit opt-in required. This split closes the silent-memory-contamination risk Codex flagged.

---

### Wish 4 — Chart / table / artifact generation

**User expectation:**
- ChatGPT Code Interpreter or Gemini Visual Reports
- Real numeric extraction (not decorative charts from guessed values)
- Downloadable artifacts, clean layout, fast turnaround

**V30 today: PARTIAL — primitives in place**
- Deterministic text tables (trial summary, table builders)
- `src/tools/visual_generator.py` supports SVG chart/timeline/table specs
- `src/polaris_graph/tools/data_analyzer.py` can generate real charts/tables by executing Python
- `src/polaris_graph/synthesis/smart_art_generator.py` generates Mermaid diagrams
- Mesh artifact directives define `TABLE`, `CHART`, `FLOW`, `DECK`, `FLASHCARDS` — only `TABLE` renders today
- **Codex risk flag:** `anti_tunnel_view_test.py` flags that smart-art may not actually be injected into the final report path. Don't overcount artifact maturity.

**Trap flag: NO**
- This is the cleanest moat-amplifier on the list. Citation-bound charts where every plotted value comes from cited structured rows = uniquely V30.

**Moat impact: AMPLIFY**

**Phase: B**
- 8-15 eng days for trustworthy beta artifact pack (cited tables, numeric charts, Mermaid/flow diagrams, export wiring, failure/refusal rules)
- 20-30 eng days for polished HTML/DOCX/PDF product quality

**Acceptance criteria:**
- Every chart backed by machine-readable source table with evidence IDs
- Visuals fail closed when extraction confidence below threshold
- Contradictions and caveats carry into captions/footnotes
- User can export chart image + source table + citation appendix

**Joint verdict:** SHIP IN PHASE B. This is the highest-value, lowest-trap wish on the list. Charts must fail closed when evidence isn't numerically extractable — that refusal IS the moat. Integrates naturally with Evidence Inspector view 4 (Methods + Provenance Bundle).

---

### Wish 5 — Infographic generation

**User expectation:**
- Manus/Gemini-class polished, shareable, branded visual summaries
- Agency-made polish, narrative compression, one-glance comprehension
- Implicitly publishable

**V30 today: NONE in product sense**
- Chart and diagram primitives exist, but no real infographic system

**Trap flag: YES — explicit TRAP**
- Both Codex and Claude flagged this independently
- Real-user research convergence: wishlist sweep flagged "infographic" as TRAP #1 — output-format commodity, NotebookLM/Manus already polished, can't win on visual polish
- Audit conflict: infographics compress nuance aggressively. That's exactly where provenance, confidence bounds, contradictions, scope limitations get erased.

**Moat impact: DILUTE** unless heavily constrained to derivative visuals from already-approved structured claims

**Phase: D (and only as constrained "evidence poster")**
- 15-25 eng days for constrained "fact card / evidence poster" generator
- 40-80 eng days for anything approaching Manus/Gemini polish + template breadth

**Acceptance criteria (if eventually shipped):**
- Only allowed from already-verified structured facts, not raw prose
- Every panel has compact reference footer or appendix hook
- Refuses when there's not enough structure to compress without distortion
- Treated as derivative marketing artifact, NEVER canonical audit artifact

**Joint verdict:** TRAP — DEFER TO PHASE D. If shipped at all, only as constrained evidence poster. Treat the user's "Manus-class infographic" expectation as the wrong axis to compete on.

---

### Wish 6 — 1-click slide deck

**User expectation (Manus-class):**
- "Turn my research into a board-ready 12-20 slide deck with visuals, executive framing, almost no cleanup"
- Coherent storyline, visual hierarchy, charts, speaker notes, brand consistency
- Export to PPTX/PDF/HTML

**V30 today: NONE as finished product, primitives exist**
- Report assembly + DOCX export + chart generation + smart-art diagrams
- Mesh artifact directive for `DECK` exists but is deferred stub

**Trap flag: CONDITIONAL**
- Compressing aggressively for story smoothness = TRAP. Unsupported bullets, decontextualized numbers, dropped contradictions destroy the moat.
- Citation-bound deck with appendix slides + per-bullet source footnotes = SAFE.

**Moat impact: AMPLIFY** if slide bullets remain citation-bound AND each slide can drill down to appendix/source panel

**Phase: C (with narrow beta possible late in B)**
- 12-20 eng days for reliable beta deck composer using existing report + chart/diagram primitives
- 25-40 eng days for polished theme support, speaker notes, appendix automation, PPTX fidelity

**Acceptance criteria:**
- Generates 12-20 slide deck from verified report + structured data
- Every substantive slide has slide-level citations OR linked appendix slide
- Contradictions and limitations survive in main slide or speaker notes
- Export works in PPTX and HTML/PDF without breaking references

**Joint verdict:** PHASE C, NOT NEXT-SHIP. The deck is POWERFUL when downstream of a verified V30 audit artifact — but shipping it before the audit-only beta proves the engine = wrong-axis competition with Manus polish.

---

### Wish 7 — 1-click video / audio overview

**User expectation (NotebookLM Audio Overview / Gemini audio):**
- Click once, get compelling two-host or narrated summary
- Polished, trustworthy, fast generation, low cleanup
- Spoken content "safe to trust"

**V30 today: NONE**
- Repo can ingest audio, no script-to-TTS-to-mixed-output artifact lane

**Trap flag: YES — explicit TRAP**
- Audio strips away inline citations. V30's biggest moat becomes invisible.
- Spoken certainty tends to overstate evidence unless aggressively constrained.
- "Podcast confidence" is a bad fit for audit-grade research.
- Real-user research convergence: NotebookLM Audio Overview hallucination complaints are documented across multiple sources.

**Moat impact: DILUTE**

**Phase: D (and only as derivative)**
- 18-30 eng days for cautious script + transcript + TTS audio proof
- 45-90 eng days for NotebookLM-class two-host quality, editing, mixing, retries, safe citation carry-through

**Acceptance criteria (if eventually shipped):**
- Script generated only from already-approved report artifact
- Transcript and show notes include timestamps and references for every segment
- Spoken output hedges appropriately, never outruns evidence
- Audio/video clearly labeled derivative, NEVER canonical audit output

**Joint verdict:** TRAP — DEFER TO PHASE D. If shipped, only as chaptered transcript + show notes carrying citations. Audio cannot be the canonical audit surface.

---

## Citation-discipline carry-through (joint)

| Output format | Citation survival | Recommended form | Verdict |
|---------------|:-----------------:|------------------|---------|
| **Markdown report** (V30 native) | **Strong** — already shipped | Inline `[N]` + bibliography | Canonical audit artifact |
| **PDF/DOCX export** | **Strong** | Inline `[N]` preserved + bibliography + methods appendix | Phase A — ship in Evidence Inspector view 4 |
| **Structured tables (CSV/XLSX)** | **Strong** | Per-row `evidence_id` column + tier label column | Phase B |
| **Chart pack** | **Strong** | Source-table appendix + per-data-point evidence_id | Phase B |
| **Workspace Brief (bounded WikiLLM)** | **Strong** — design constraint | Per-paragraph inline citations OR "insufficient support" labels | Phase B |
| **Slide deck** | **Strong if designed deliberately** | Slide-level footnotes + appendix slide + clickable source panel in HTML + speaker notes for caveats | Phase C |
| **Infographic** | **Medium at best** | Panel footer references + QR/link to appendix + only numeric claims mapping cleanly to source tables | Phase D — if at all |
| **Video / Audio** | **Weak** | Chaptered transcript with source markers + companion show notes with timestamps + optional on-screen source IDs for video | Phase D — derivative only |

**The joint principle:** citation discipline is the moat. Output formats that preserve it amplify; output formats that strip it dilute. The Evidence Inspector UI is the unifier — every export format should round-trip back to inspector views.

---

## Composition-layer architecture (pass-2, REWRITTEN per Codex review)

**Codex correction (accepted):** The pass-1 framing — "report markdown
plus some exports" — was wrong. Under the audit-only + Evidence Inspector
pivot, the canonical product surface is NOT the report. It's the
**audit graph / claim-evidence IR rendered through the Evidence Inspector**.
Everything else is a derivative projection.

**Revised recommendation: ONE canonical audit IR, ONE primary renderer (Evidence Inspector), MANY derivative renderers — all with back-links to claim IDs.**

```
audit_graph_ir (canonical, downstream of verification)
├── Stable claim IDs
├── Evidence-span bindings (page/sheet/timecode/parser-version)
├── Contradiction edges (tier-labeled)
├── Frame / contract coverage mappings
├── Artifact element lineage (every chart point, deck bullet, brief
│   paragraph holds back-link to claim ID + evidence ID)
├── Bibliography map
└── Citation-to-span map

PRIMARY renderer:
└── Evidence Inspector (5 views) ← Phase A
    The canonical audit surface. Everything else is derivative.

DERIVATIVE renderers (must retain back-links to claim IDs):
├── markdown report ← Phase A (already exists, polish)
├── docx ← Phase A (already exists, polish)
├── pdf audit bundle ← Phase A
├── structured tables (CSV/XLSX) ← Phase B
├── chart pack ← Phase B
├── question-bound corpus brief ← Phase B (narrow form)
├── citation-bound deck (with appendix slides) ← late-B beta or Phase C
├── infographic / evidence poster ← Phase D (constrained, if at all)
└── audio script (chaptered transcript only) ← Phase D (constrained)
```

**Why this matters under the audit-only pivot:**
- Without artifact lineage, "round-trip back to inspector views" stays aspirational
- Every chart point, deck bullet, brief paragraph needs a stable pointer back to the same claim/evidence objects the Inspector renders
- This is what makes the Evidence Inspector the unifier across all output formats

**Why this fits the repo:**
- `report_assembler.py` and `report_assembler_v2.py` already prove assembly is a separate concern
- `docx_exporter.py` is already a renderer
- `smart_art_generator.py` is a renderer input producer (but Codex flagged: may not be wired into final report path — `anti_tunnel_view_test.py` confirms this gap)
- `visual_generator.py` and `data_analyzer.py` already generate visual artifacts
- `wiki/mesh/compose/artifact_directives.py` already models a directive-based artifact surface
- BUT: `src/agents/citefirst/report_composition.py` is missing despite audit-doc references — composition layer is conceptually present but not product-hardened

**Guardrails (non-negotiable):**
- Composition strictly downstream of verification
- No renderer invents facts
- Every renderer output element retains back-link to claim IDs in the audit IR
- Renderers may only compress, reorder, or visualize already-approved content
- Evidence Inspector is the canonical audit surface — every derivative output must be navigable BACK to inspector views

---

## Snowball + upload architecture (pass-2, REVISED per Codex review)

**Codex correction (accepted):** Pass-1 layering conflated different
kinds of memory and treated governance as a terminal layer when it's
really cross-cutting. Revised stack below.

```
1. Ingestion / parser orchestration
   ├── file upload, URL import, text import
   ├── parse, OCR, transcription, metadata capture
   └── content hashing, dedupe, retry, failure states

2. Document store + provenance map
   ├── workspace-scoped document manifests
   ├── extracted text + page/sheet/slide/timecode offsets
   ├── parser version + artifact retention metadata
   └── per-document permission model

3. Retrieval indexes
   ├── vector index PLUS lexical/doc filters
   ├── persistent workspace collections (NOT session-only)
   └── provenance-preserving chunk IDs

4. Run / session state (ephemeral)
   ├── current query context, scratch notes, partial progress
   └── garbage-collected at run completion

5. Workspace memory (user-visible, user-deletable)
   ├── pins, saved notes, bookmarks (passive — Phase B)
   ├── retrieval-active memory with explicit labels (Phase C)
   └── never blends invisibly with primary evidence

6. Retrieval / synthesis orchestration
   ├── uploaded corpus only / web only / blended retrieval modes
   ├── memory-derived retrieval explicitly labeled (Phase C)
   └── contradiction-aware synthesis treating uploaded docs as first-class evidence

7. Governance / auth / retention / audit (CROSS-CUTTING — not terminal)
   ├── per-workspace permissioning at every layer above
   ├── per-document deletion with audit trail
   ├── PHI gating + intended-use enforcement
   ├── retention policy
   └── audit log of who did what, when, why

QUARANTINED LAYER (separate from audit lane by default):
   Global / system memory
   ├── operator-curated priors
   ├── product-level memory
   ├── may NOT silently influence audit lane
   └── explicit user opt-in required to consult; clearly labeled
```

**Why the changes matter:**
- Splitting memory into session / workspace / global closes the silent-prior-injection risk Codex flagged
- Treating governance as cross-cutting (not terminal) is correct — every layer above needs permissioning, audit logs, retention rules
- Document store + provenance map is its own layer because that's where page/sheet/slide/timecode offsets live, and that's the audit-grade requirement

**Scope call:**
- IN-SCOPE for V30 Phase-2 era: persistent workspace upload + bounded corpus analysis (Phase B)
- IN-SCOPE Phase B: passive workspace notes layer (5-10 eng days)
- OUT-OF-SCOPE for V30 Phase-2 era: 300-500 PDFs/session as default behavior (Phase D or separate product)
- OUT-OF-SCOPE Phase B: retrieval-active memory (Phase C)

**Critical risks Codex flagged:**
1. **PHI creep** — once customers expect document uploads, PHI creep is likely unless the product blocks or strictly gates it. Deletion + access control + document lineage become product-critical, not future enterprise polish.
2. **Hidden global memory contamination** — once uploads and memory coexist, silent prior injection from global/system memory becomes a trust problem, not just a UX issue. One incident can damage the whole product story. This is why the global memory layer must be quarantined from the audit lane by default.
3. **Uploaded-document provenance gap** — current upload handling has char offsets and extracted HTML/text, but NOT product-ready provenance map for PDF page coordinates, slide references, sheet references, timecodes. Closing this gap is core Phase B work.

---

## "1-click magic" UX call (pass-2, EXPANDED per Codex review)

**Codex correction (accepted):** Pass-1 said "immediate progress surface"
which was directionally right but too weak. Under the audit-only
single-lane pivot, if the Evidence Inspector only appears at the END
of a 2h25m run, you have a real **2h25m blank-stare problem**. Time-to-first-value
cannot be a prose preview anymore — it has to be **progressive
audit-native surfaces**.

**Compatible with audit-grade ONLY in a split sense:**

| Aspect | 1-click compatible? |
|--------|:-:|
| Kickoff (user describes outcome, system runs) | **YES** |
| Blind trust (output good without inspection) | **NO** — system must expose scope, source set, confidence, contradictions |

**Progressive audit-native surfaces (NEW — REPLACES the Preview lane):**

The Evidence Inspector must come ALIVE during the run, not just at the end. Time-to-first-value milestones, in order:

| t (min) | Audit-native surface available |
|--------:|--------------------------------|
| 0 | **Pre-flight estimate**: scope, template, time, cost, source-count |
| 0-2 | **Upload/parse progress** per document (if upload step exists) |
| 2-15 | **Live source discovery** with tier mix (T1/T2/T3 bar fills in) |
| 15-45 | **Frame coverage manifest** fills in as evidence arrives — "Endpoint Y: 3/5 sources found" |
| 45-90 | **Contradiction queue** appears — disagreements visible BEFORE final synthesis |
| 90-120 | **First verified claim cards / evidence cards** as soon as they pass strict-verify |
| 120-145 | **Final synthesis + complete Evidence Inspector** |

**Why this matters:**
- The product goal is `first inspectable evidence state`, not `first draft prose`
- Users see the moat being built in real time — that's the demo
- Activation and trust are visible before completion
- Cancellation/redirection (top wishlist demand) is meaningful only if there's something to inspect

**Recommended UX pattern (pass-2):**
- One compose box (audit-grade input)
- Auto-template / auto-corpus selection in background
- Pre-flight scope/cost/time estimate before Run button enables
- Progressive Evidence Inspector state with named milestones above
- Cancel/pause/save-state at any milestone (top user-wishlist demand)
- Final output IS the Evidence Inspector at full state — no separate "result" page
- No "preview vs audit" toggle (cut per quality mandate)

**Short version:** "1 click to start" is good. "1 click to trust" is not. **Progressive Evidence Inspector state is what makes the trust visible at every milestone, not just at the end.** This is a core UX requirement, not polish.

---

## Recommended PRD bundle for next ship (Phase A → B, 7-11 weeks — RAISED per Codex)

**Convergent across:**
- Codex's user-wishlist plan (this doc)
- Real-user research (35+32 sources)
- Joint commercialization plan (`JOINT_PLAN.md`)

### IN the bundle (moat-amplifying)

From the 7 user-named wishes, ship these forms:

1. **Wish 4 — Chart / table / artifact generation (CORE Phase B scope)**
   - Phase B
   - 8-15 eng days
   - **Core scope = cited tables + numeric charts + export bundle**
   - Mermaid/flow polish = secondary (Codex correction)
   - Every chart fails closed when evidence not numerically extractable
   - Back-links to claim IDs in audit IR

2. **Wish 2 — Massive upload (BOUNDED form: 10-50 docs/workspace)**
   - Phase B
   - **25-40 eng days (raised from 15-25 per Codex)**
   - Persistent workspace corpus + workspace data model + permissions + retention + deletion semantics + provenance mapping
   - Page/sheet/slide/timecode provenance UI (NOT just char offsets)
   - Filter modes: uploaded-only / web-only / blended
   - Integrates with Evidence Inspector views 1, 3, 4

3. **Wish 1 — Question-Bound Corpus Brief (NARROW form, dependent on #2)**
   - Phase B, **explicitly dependent on wish #2 landing first**
   - 12-20 eng days
   - Per-paragraph inline citations OR explicit "insufficient support" labels
   - Built on top of bounded upload primitive (wish 2)
   - **NOT a "Workspace Brief" — that label over-promises (Codex correction)**
   - Back-links to claim IDs in audit IR

4. **Wish 3 — Passive workspace notes (THIN form, NOT retrieval-active)**
   - Phase B (NEW — Codex's split distinguishes this from full memory)
   - 5-10 eng days
   - User pins/saves/bookmarks; does NOT silently steer synthesis
   - Retrieval-active memory remains Phase C

### OUT of the bundle (deferred or trap)

5. **Wish 3 — Retrieval-active memory** → Phase C (10-18 eng days)
6. **Wish 6 — 1-click slide deck** → Phase C (better candidate than broader #1 for late-B beta if a slot opens)
7. **Wish 5 — Infographic** → Phase D (TRAP) — only as constrained evidence poster if at all
8. **Wish 7 — Video / audio** → Phase D (TRAP) — only as derivative chaptered transcript if at all

### Sequencing note (Codex addition)

If one additional derivative artifact is pulled forward into late Phase B, **citation-bound deck beta is the better candidate than a broader corpus-brief promise**. The deck is more bounded once a stable composition IR exists; the brief expansion is open-ended.

### Scope sanity check (pass-2, REVISED per Codex)

The next-ship bundle includes wishes 1-2-3(passive)-4 in their bounded forms + the Evidence Inspector centerpiece + progressive audit-native surfaces.

**Pass-1 estimate was 52-86 eng days = 5-9 weeks.** Codex flagged this as optimistic lower bound, not realistic planning number.

**Why pass-1 was low:**
- Wish #2 priced like parser/glue work, but real work is workspace data model + permissions + retention + deletion + provenance mapping
- Wish #1 not free once #2 exists — another synthesis surface with own QA burden
- Wish #4 trustworthy charting still needs source-table binding + refusal behavior + export integration
- Evidence Inspector in audit-only product needs progressive/live behavior, not just static final-state renderer (NEW UX requirement above)
- Editorial/template QA starts biting earlier than pass-1 admits — once you add brief/deck/chart surfaces, output QA is not only model QA anymore

**Pass-2 revised total:**

| Component | Eng days |
|-----------|---------:|
| Evidence Inspector (5 views, Phase A) | 17-26 |
| Evidence Inspector progressive surfaces (during-run state) | 8-12 |
| Wish 4 — chart/table/artifact (core scope) | 8-15 |
| Wish 2 — bounded upload (with workspace data model) | 25-40 |
| Wish 1 — Question-Bound Corpus Brief (narrow) | 12-20 |
| Wish 3 — Passive workspace notes | 5-10 |
| Queue + pause/resume + template router | 10-15 |
| **Total** | **85-138 eng days** |

**Realistic planning number: 70-110 eng days = 7-11 weeks for a small strong team.**

The lower range (~70 days) is achievable only if wish #1 stays extremely narrow and progressive Inspector behavior slips. To stay in the lower range, cut or narrow wish #1 first.

**The bundle deliberately defers wishes 5, 6, 7 and the retrieval-active half of #3.** That's not a hedge — it's the moat-amplification discipline. Every deferred wish is either a trap or premature.

---

## Risks Codex flagged that Claude missed (pass-1 + pass-2 review combined)

### Pass-1 risks (architectural)

1. **Existing UI/API may overpromise.** The repo already has partial UI/API for NotebookLM-style source import and source briefing. Users may assume full corpus intelligence already exists when the audit lane is still report-centric. Clear scope-limitation messaging is required.

2. **`src/agents/citefirst/report_composition.py` is missing** even though audit docs mention it as a stub. The composition layer is conceptually present but not product-hardened.

3. **`smart_art_generator.py` may not be wired into the final report path.** `anti_tunnel_view_test.py` flags this gap. Don't overcount artifact maturity.

4. **Session-scoped local document RAG is insufficient.** Without workspace persistence + memory deletion controls + provenance UI, the product will feel flakier than NotebookLM even if backend primitives are good.

5. **Uploads create privacy/retention obligations fast.** Once users believe they can upload internal corpora, deletion + access control + document lineage become product-critical.

6. **Audio/video adds tone risk + certainty inflation,** not just compute cost. Output is harder to inspect sentence-by-sentence than text.

### Pass-2 risks (Codex review of pass-1 framing)

7. **Workspace scoping is a data-model change, not polish.** The pass-1 estimate for wish #2 (15-25 days) priced parser/glue work; the real work is workspace data model + permissions + retention + deletion + provenance mapping. Estimate raised to 25-40 days.

8. **Page/span-grade provenance for uploads is not solved.** Current system has char offsets and extracted HTML/text, NOT product-ready provenance map for PDF page coordinates, slide references, sheet references, timecodes. This gap will make audit-grade claims ring hollow.

9. **Evidence Inspector should be the canonical renderer, not just another consumer.** Pass-1 framed it as a viewer over the report. Pass-2 framing: it IS the audit surface; everything else is a derivative projection with back-links to claim IDs.

10. **"Workspace Brief" label over-promises.** Users hear "living wiki summary." Realistic Phase-B form is question-bound and derivative. Renamed to "Question-Bound Corpus Brief."

11. **Passive notes vs retrieval-active memory are different products.** Pass-1 conflated them. Passive notes can ship Phase B (low risk); retrieval-active memory is Phase C (high risk, needs careful UX).

12. **Non-wishlist features from real-user research are closer to requirements than some named wishes.** Pause/save mid-run, pre-flight cost/time, locked evidence scopes, checkpoint/resume, human review queue — these are nearer-to-must-have than wishes 5/6/7.

13. **Hidden global/system memory is an audit-lane risk.** Once uploads and memory coexist, silent prior injection becomes a trust problem. Global/system memory must be quarantined from audit lane by default.

### Risk register with probability + impact (Codex pass-2)

| Risk | Probability | Impact | Phase |
|------|:----------:|:------:|:-----:|
| PHI creep once uploads ship | 70-90% | Severe | B |
| Editorial QA throughput becomes the bottleneck | 60-80% | High | B-C |
| Single-lane 2h25m blank-stare UX gap | 50-70% | High | A-B |
| Uploaded-document provenance gap | 70-85% | High | B |
| Hidden memory contamination (global → audit lane) | 30-50% | Severe | B-C |

---

## Joint bottom line (pass-2)

The 7 user-named wishes split cleanly into FOUR groups (pass-2 added the passive-notes split):

**Ship now (Phase B, bounded forms):**
- Wish 4 (cited tables + numeric charts — core scope)
- Wish 2 (10-50 docs bounded upload, with workspace data model)
- Wish 1 (Question-Bound Corpus Brief — narrow, dependent on #2)
- Wish 3 partial (passive workspace notes only)

**Ship later (Phase C, when audit lane proven):**
- Wish 3 retrieval-active (user-visible memory with explicit labels)
- Wish 6 (citation-bound deck with appendix slides) — better candidate than broader #1 if a slot opens late Phase B

**Trap — defer or never:**
- Wish 5 (infographic) — Phase D, only as constrained evidence poster if at all
- Wish 7 (video/audio) — Phase D, derivative chaptered transcript only if at all

**Quarantined (NEW — Codex correction):**
- Global/system memory — must NOT silently influence audit-lane runs by default; explicit user opt-in required

The audit-grade moat survives only if every shipped wish is constrained to the moat-amplifying form. Free-form wikis, fuzzy massive RAG, silent latent memory, polished infographics, conversational podcasts — all dilute. Citation-bound briefs, persistent workspace evidence, user-visible memory, citation-bound decks, evidence-grounded charts — all amplify.

**The user's seed message named 7 wishes. The pass-2 analysis says ship 3.5, defer 1.5, treat 2 as traps, quarantine 1 (the silent global memory).** That discipline IS the product.

**The Evidence Inspector is the canonical audit renderer**, not just a viewer over the report. Every wish that ships in any form is a derivative projection of the audit graph IR with back-links to claim IDs. **Progressive Inspector state during the run** (not just at the end) is what makes the moat visible in real time and closes the 2h25m blank-stare problem.

**Realistic Phase B ETA (raised from pass-1):** 7-11 weeks (70-110 eng days). Lower range only feasible if wish #1 stays extremely narrow.
