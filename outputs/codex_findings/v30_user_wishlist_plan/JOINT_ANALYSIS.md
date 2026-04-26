# V30 Phase-2 — Joint User-Wishlist Analysis (7 user-named wishes)

**Date:** 2026-04-26
**Source documents:**
- Codex (gpt-5.4 xhigh): `outputs/codex_findings/v30_user_wishlist_plan/findings.md`
- Claude framing (initial): `.codex/v30_user_wishlist_brief.md`
- Real-user research (35 + 32 primary sources): `outputs/codex_findings/v30_real_user_wishlist/SYNTHESIS.md`
- Joint commercialization plan: `outputs/codex_findings/v30_phase2_to_production_plan/JOINT_PLAN.md`

This document is the joint Claude+Codex analysis of the 7 user-named wishes.

---

## TL;DR — the 7 verdicts at a glance

| # | Wish | V30 today | Trap? | Moat impact | Phase | In next ship? |
|--:|------|:---------:|:----:|:------------:|:-----:|:------:|
| 1 | WikiLLM (wiki-style internal-corpus synthesis) | partial | trap if free-form | amplify if bounded / dilute if open | B (bounded) / D (living) | NO — Phase B as "Workspace Brief", not Phase A |
| 2 | Massive data upload + analysis | partial | trap if 300+ PDFs/session | amplify if first-class evidence / dilute if fuzzy RAG | B (10-50 docs) / D (300+) | YES — bounded form |
| 3 | Snowball memory + knowledge accumulation | partial | trap if silent latent | neutral-to-amplify if user-governed / dilute if invisible | C (visible) / D (autonomous) | NO — Phase C |
| 4 | Chart / table / artifact | partial | NO | amplify | B | YES — structured tables + cited charts |
| 5 | Infographic | none | **TRAP** | **dilute** | D | NO |
| 6 | 1-click slide deck | none | conditional | amplify if citation-bound + appendix | C (late B beta possible) | NO — Phase C |
| 7 | 1-click video/audio | none | **TRAP** | **dilute** | D | NO |

**Three explicit traps converged across both runs:** infographic, video/audio, massive-upload-at-scale.

**Independently confirmed by real-user research:** the wishlist sweep (35 + 32 primary sources) found that output-format commodities (slides/podcasts/infographics) have high user demand BUT low differentiation potential for audit-grade. NotebookLM and Manus already polished — V30 cannot win on visual polish, and audio/visual compression strips inline citations (V30's biggest moat becomes invisible).

---

## Per-wish deep dive

### Wish 1 — WikiLLM (wiki-style synthesis from internal corpus)

**User expectation (NotebookLM/Perplexity Spaces bar):**
- Dump sources in, get a living knowledge page with clean summaries, FAQs, timelines
- Cross-document synthesis in minutes
- Wiki updates as new sources arrive
- System remembers corpus without manual prompt choreography

**V30 today: PARTIAL**
- `src/polaris_graph/wiki/wiki_composer.py` exists
- Mesh compose/artifact rendering in `src/polaris_graph/wiki/mesh/compose/`
- BUT: V30 Phase-2 is contract-anchored and report-centric, not corpus-wiki-centric

**Trap flag: CONDITIONAL**
- Free-form / unconstrained = TRAP. NotebookLM-style prose tolerates uncited connective tissue and loose synthesis. V30's strict-verify discipline cannot tolerate that.
- Citation-bound workspace BRIEF = SAFE. Every paragraph either inline-cited or labeled "insufficient support."

**Moat impact:**
- AMPLIFY if shipped as "citation-bound workspace brief / wiki page"
- DILUTE if shipped as open-ended ambient knowledge prose

**Phase: B (bounded brief), D (living corpus wiki)**
- 12-20 eng days for narrow citation-bound brief on top of existing upload + compose primitives
- 30-45 eng days for true NotebookLM-class living corpus wiki

**Acceptance criteria:**
- Corpus is explicit and user-visible; no hidden web mixing unless requested
- Every paragraph has inline citations OR explicit "insufficient support" language
- Clicking a citation shows document/page/span, not just URL (Evidence Inspector view 1)
- Regeneration after adding sources preserves prior source boundaries and contradiction disclosures

**Joint verdict:** SHIP AS "WORKSPACE BRIEF" IN PHASE B. Defer the unconstrained living-wiki version to Phase D.

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
- 15-25 eng days for solid beta corpus layer (10-50 docs/workspace, persistent indexing, provenance UI, retry/parse status, workspace filters)
- 40-70 eng days for 300-500 PDFs/session with durable indexing, backpressure, dedupe, retention, ops safety

**Acceptance criteria:**
- Upload status is per-document and per-parser-step, with failures surfaced
- Every retrieved chunk maps to document + page/slide/sheet/timecode + parser version
- User can filter analysis to uploaded corpus only / web only / blended mode
- Workspace persistence exists; session-only Chroma not enough

**Joint verdict:** SHIP BOUNDED FORM (10-50 docs/workspace) IN PHASE B. The Evidence Inspector views naturally extend to uploaded corpora — a clinical brief drawing from uploaded SAP/CSR/protocol PDFs is a winning V30 demo. Defer 300+ to Phase D or treat as separate ingestion product.

---

### Wish 3 — Snowball memory + knowledge accumulation

**User expectation:**
- System remembers prior sources, notes, decisions, context across sessions
- No re-uploading or re-explaining
- Persistence + reuse + inspectability + edit/delete controls + low drift

**V30 today: PARTIAL — primitives exist, UX does not**
- `src/polaris_graph/memory/cross_vector.py` promotes high-quality evidence to global LTM in Chroma
- `src/polaris_graph/memory/session_feedback.py` records strategy outcomes
- `src/polaris_graph/memory/evidence_hierarchy.py` stores L0/L1/L2 evidence summaries
- `src/agents/analyst_agent.py` enriches facts into a knowledge graph
- `scripts/static/js/memory_dashboard.js` shows there's already a UI concept

**Trap flag: CONDITIONAL — silent memory is the trap**
- USER-VISIBLE + LABELED + WORKSPACE-SCOPED + USER-GOVERNED = SAFE
- Silent latent bias mutating future outputs without provenance trail = TRAP. V30 loses its core trust property if memory becomes invisible.

**Real-user research convergence:** The wishlist sweep found wish #18 (cross-notebook / cross-workspace memory) is high-frequency. Atlasworkspace.ai users explicitly named the issue. Critical UX constraint: **must be USER-VISIBLE and DELETABLE**.

**Moat impact:**
- NEUTRAL-TO-AMPLIFY if memory is retrieval-only, labeled, workspace-scoped, user-governed
- DILUTE if memory becomes silent latent bias

**Phase: C (user-visible workspace memory), D (autonomous accumulation)**
- 10-18 eng days for workspace-scoped saved notes, pinned prior sources, inspect/delete controls
- 25-40 eng days for real persistent workspace knowledge graph with freshness, invalidation, collaborative editing

**Acceptance criteria:**
- Memory items are visible, attributable, and removable by user
- Retrieved priors are LABELED as memory-derived, not blended invisibly into primary evidence
- Workspace boundaries strict; no cross-customer leakage
- Freshness/staleness rules for time-sensitive topics

**Joint verdict:** PHASE C. Visible workspace memory with explicit "memory-derived" provenance flag, integrated into Evidence Inspector view 1 (when a claim cites memory, show the memory item's lineage). Phase D for autonomous accumulation.

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

## Composition-layer architecture (joint, per Codex)

**Recommendation: ONE composition core, MULTIPLE renderers.**

Do NOT build separate end-to-end stacks for chart, infographic, deck, audio. Build a single `artifact_composer` that consumes verified report state and emits a normalized intermediate representation:

```
artifact_composer (input: V30 verified report + manifest)
├── normalized intermediate representation
│   ├── sections
│   ├── claim blocks (with evidence_id bindings)
│   ├── contradiction blocks
│   ├── structured data tables
│   ├── chart specs
│   ├── diagram specs
│   ├── bibliography map
│   └── citation-to-span map
└── renderers (per format)
    ├── markdown/html report ← Phase A (already exists)
    ├── docx ← Phase A (already exists, polish)
    ├── pdf audit bundle ← Phase A
    ├── structured tables (CSV/XLSX) ← Phase B
    ├── chart pack ← Phase B
    ├── workspace brief (bounded wiki) ← Phase B
    ├── deck ← Phase C
    ├── infographic / fact poster ← Phase D (constrained)
    └── audio script ← Phase D (constrained)
```

**Why this fits the repo:**
- `report_assembler.py` and `report_assembler_v2.py` already prove assembly is a separate concern
- `docx_exporter.py` is already a renderer
- `smart_art_generator.py` is a renderer input producer
- `visual_generator.py` and `data_analyzer.py` already generate visual artifacts
- `wiki/mesh/compose/artifact_directives.py` already models a directive-based artifact surface

**Guardrail (non-negotiable):**
- Composition must be downstream of verification
- No renderer gets to invent facts
- Renderers may only compress, reorder, or visualize already-approved content

---

## Snowball + upload architecture (joint, per Codex)

For wishes 2 + 3 combined, the recommended layered architecture:

```
1. Ingestion service
   ├── file upload, URL import, text import
   ├── parse, OCR, transcription, metadata capture
   └── content hashing, dedupe, retry, failure states

2. Corpus store
   ├── workspace-scoped document manifests
   ├── extracted text + page/span offsets
   └── parser version + artifact retention metadata

3. Index layer
   ├── vector index PLUS lexical/doc filters
   ├── persistent workspace collections (NOT session-only)
   └── provenance-preserving chunk IDs

4. Memory layer
   ├── promote verified evidence to workspace memory
   ├── support pins, notes, approvals, expiry, delete
   └── keep global/system LTM separate from workspace memory

5. Retrieval layer
   ├── uploaded corpus only / web only / blended retrieval modes
   └── contradiction-aware synthesis treating uploaded docs as first-class evidence

6. Governance layer
   ├── retention, deletion, permissioning, audit log
   └── stale-memory invalidation
```

**Scope call:**
- IN-SCOPE for V30 Phase-2 era: persistent workspace upload + bounded corpus analysis (Phase B)
- OUT-OF-SCOPE for V30 Phase-2 era: 300-500 PDFs/session as default behavior (Phase D or separate product)

**Codex risk Claude missed:** Once customers expect document uploads, **PHI creep is likely** unless the product blocks or strictly gates it. Deletion + access control + document lineage become product-critical, not future enterprise polish.

---

## "1-click magic" UX call (joint)

**Compatible with audit-grade ONLY in a split sense:**

| Aspect | 1-click compatible? |
|--------|:-:|
| Kickoff (user describes outcome, system runs) | **YES** |
| Blind trust (output good without inspection) | **NO** — system must expose scope, source set, confidence, contradictions |

**Recommended UX pattern:**
- One compose box (audit-grade input)
- Auto-template / auto-corpus selection in background
- Immediate progress surface + time-to-first-artifact display
- Final output **always** routes through Evidence Inspector
- No "preview vs audit" toggle (we cut the dual-lane per quality mandate)

**Short version:** "1 click to start" is good. "1 click to trust" is not. The Evidence Inspector is what makes the trust visible, not just claimed.

---

## Recommended PRD bundle for next ship (Phase A → B, 5-9 weeks)

**Convergent across:**
- Codex's user-wishlist plan (this doc)
- Real-user research (35+32 sources)
- Joint commercialization plan (`JOINT_PLAN.md`)

### IN the bundle (moat-amplifying)

From the 7 user-named wishes, ship these forms:

1. **Wish 4 — Chart / table / artifact generation (FULL form)**
   - Phase B
   - 8-15 eng days
   - Cited tables + numeric charts + Mermaid diagrams
   - Every chart fails closed when evidence not numerically extractable
   - Round-trips to Evidence Inspector view 4

2. **Wish 2 — Massive upload (BOUNDED form: 10-50 docs/workspace)**
   - Phase B
   - 15-25 eng days
   - Persistent workspace corpus
   - Page/span provenance UI
   - Filter modes: uploaded-only / web-only / blended
   - Integrates with Evidence Inspector views 1, 3, 4

3. **Wish 1 — Workspace Brief (BOUNDED form: citation-bound brief, NOT free-form wiki)**
   - Phase B
   - 12-20 eng days
   - Per-paragraph inline citations OR explicit "insufficient support" labels
   - Built on top of bounded upload primitive (wish 2)
   - Round-trips to Evidence Inspector view 1

### OUT of the bundle (deferred or trap)

4. **Wish 3 — Snowball memory** → Phase C (user-visible workspace memory)
5. **Wish 6 — 1-click slide deck** → Phase C (citation-bound deck with appendix slides)
6. **Wish 5 — Infographic** → Phase D (TRAP) — only as constrained evidence poster if at all
7. **Wish 7 — Video / audio** → Phase D (TRAP) — only as derivative chaptered transcript if at all

### Scope sanity check (joint)

The next-ship bundle = wishes 1-2-4 in their bounded forms + the Evidence Inspector centerpiece. Total Phase B work = 35-60 eng days for the wishlist contribution + 17-26 days for the Evidence Inspector = **52-86 eng days = 5-9 weeks for a small team**. Matches the joint plan ETA.

**The bundle deliberately defers wishes 3, 5, 6, 7.** That's not a hedge — it's the moat-amplification discipline. Every deferred wish is either a trap or premature.

---

## Risks Codex flagged that Claude missed

1. **Existing UI/API may overpromise.** The repo already has partial UI/API for NotebookLM-style source import and source briefing. Users may assume full corpus intelligence already exists when the audit lane is still report-centric. Clear scope-limitation messaging is required.

2. **`src/agents/citefirst/report_composition.py` is missing** even though audit docs mention it as a stub. The composition layer is conceptually present but not product-hardened.

3. **`smart_art_generator.py` may not be wired into the final report path.** `anti_tunnel_view_test.py` flags this gap. Don't overcount artifact maturity.

4. **Session-scoped local document RAG is insufficient.** Without workspace persistence + memory deletion controls + provenance UI, the product will feel flakier than NotebookLM even if backend primitives are good.

5. **Uploads create privacy/retention obligations fast.** Once users believe they can upload internal corpora, deletion + access control + document lineage become product-critical.

6. **Audio/video adds tone risk + certainty inflation,** not just compute cost. Output is harder to inspect sentence-by-sentence than text.

---

## Joint bottom line

The 7 user-named wishes split cleanly into three groups:

**Ship now (Phase B, bounded forms):** wishes 1 (Workspace Brief), 2 (10-50 docs upload), 4 (chart/table/artifact)

**Ship later (Phase C, when audit lane proven):** wishes 3 (visible memory), 6 (citation-bound deck)

**Trap — defer or never:** wishes 5 (infographic), 7 (video/audio)

The audit-grade moat survives only if every shipped wish is constrained to the moat-amplifying form. Free-form wikis, fuzzy massive RAG, silent latent memory, polished infographics, conversational podcasts — all dilute. Citation-bound briefs, persistent workspace evidence, user-visible memory, citation-bound decks, evidence-grounded charts — all amplify.

**The user's seed message named 7 wishes. The joint analysis says ship 3, defer 2, treat 2 as traps.** That discipline IS the product.

The Evidence Inspector UI is the unifier — every wish that ships in any form must round-trip back to inspector views, so the moat stays visible in every output format.
