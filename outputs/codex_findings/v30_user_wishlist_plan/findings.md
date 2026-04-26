# Codex user-wishlist deep dive: V30 Phase-2 → top-tier feature parity

Assumption for sequencing: `Phase A/B/C/D` below reuses the existing roadmap in `outputs/codex_findings/v30_phase2_to_production_plan/findings.md`:
- `Phase A` = demo-grade
- `Phase B` = beta
- `Phase C` = production-grade vertical product
- `Phase D` = top-tier parity / broad feature maturity

## Per-wish analysis

### 1. WikiLLM — wiki-style synthesis from internal corpus

- Strategic class: `nice-to-have`, but only if constrained to citation-bound corpus synthesis. Unconstrained "free wiki" is a moat leak.
- User expectation: when users say "WikiLLM," they mean NotebookLM/Perplexity Spaces behavior: dump sources in, get a living knowledge page with clean summaries, FAQs, timelines, and cross-document synthesis in minutes.
- Imported quality bar: coverage feels broad, summaries feel natural, and the wiki updates as new sources arrive. Users assume the system remembers the corpus and does not require manual prompt choreography.
- V30 today: `partial`. `src/polaris_graph/wiki/wiki_composer.py` exists, and mesh compose/artifact rendering exists under `src/polaris_graph/wiki/mesh/compose/`, but V30 Phase-2 itself is contract-anchored and report-centric, not corpus-wiki-centric.
- Audit-grade conflict: NotebookLM-style prose tolerates uncited connective tissue and loose synthesis. V30's moat requires that the wiki stay source-locked, abstain on unsupported claims, and preserve citation density.
- Moat impact: `amplify` if shipped as "citation-bound workspace brief/wiki." `dilute` if shipped as open-ended ambient knowledge prose.
- Build cost: `12-20 eng days` for a narrow, citation-bound wiki brief/page on top of current upload + compose primitives. `30-45 eng days` if it must behave like a real multi-page living wiki.
- Phase placement: `B` for bounded workspace briefing/wiki page. `D` for true NotebookLM-class living corpus wiki.
- Anti-pattern flag: `no`, but only if the wiki is a derivative artifact of verified evidence rather than a new free-form answer surface.
- Specific competitor benchmark: NotebookLM briefing doc / FAQ / timeline; Perplexity Pages.
- Acceptance criteria:
- Corpus is explicit and user-visible; no hidden web mixing unless requested.
- Every paragraph has inline citations or explicit "insufficient support" language.
- Clicking a citation shows document/page/span, not just a URL.
- Regeneration after adding sources preserves prior source boundaries and contradiction disclosures.

### 2. Massive data upload + analysis

- Strategic class: `need-to-have` in bounded form. "300-500 PDFs per session" is a different product tier.
- User expectation: users hear "upload massive data" as "I can drop an entire diligence room or literature pack and the system will parse, index, answer, and generate artifacts without handholding."
- Imported quality bar: ingestion progress, OCR fallback, dedupe, page-level provenance, persistent corpora, and no silent parsing failures.
- V30 today: `partial`. The repo already has real upload/ingest primitives:
- `src/polaris_graph/document_ingester.py` parses PDF/DOCX/PPTX/XLSX/TXT/HTML/images/audio locally.
- `src/polaris_graph/memory/local_document_rag.py` creates session-scoped Chroma collections.
- `scripts/live_server.py` exposes upload, list, import-url, import-text, and source-brief APIs.
- `src/polaris_graph/graph.py` loads `document_ids` into state and ingests them into session RAG.
- Audit-grade conflict: generic RAG products tolerate opaque chunk retrieval. V30 cannot. Every answer must trace back to a specific uploaded artifact, parser version, page/span, and confidence level.
- Moat impact: `amplify` if uploads become first-class audited evidence. `dilute` if uploads are just fuzzy vector context with weak traceability.
- Build cost: `15-25 eng days` for a solid beta corpus layer with 10-50 docs/workspace, persistent indexing, provenance UI, retry/parse status, and workspace filters. `40-70 eng days` for 300-500 PDFs/session with durable indexing, backpressure, dedupe, retention, and ops safety.
- Phase placement: `B` for bounded upload. `D` for truly massive corpora. "300-500 PDFs per session" is effectively `D` or a separate ingestion product.
- Anti-pattern flag: `yes`, if interpreted as "become generic RAG-as-a-service now."
- Specific competitor benchmark: NotebookLM source notebooks; Perplexity Spaces.
- Acceptance criteria:
- Upload status is per-document and per-parser-step, with failures surfaced.
- Every retrieved chunk maps to document, page/slide/sheet/timecode, and parser version.
- User can filter analysis to uploaded corpus only, web only, or blended mode.
- Workspace persistence exists; session-only Chroma is not enough.

### 3. Snowball memory + knowledge accumulation

- Strategic class: `nice-to-have` now, `need-to-have` later. Hidden mutable memory is a trap.
- User expectation: NotebookLM/Manus-style memory means the system remembers prior sources, notes, decisions, and context across sessions without re-uploading or re-explaining everything.
- Imported quality bar: persistence, reuse, inspectability, edit/delete controls, and low drift. Users expect memory to help, not silently overwrite the answer.
- V30 today: `partial`. The repo already has real memory primitives:
- `src/polaris_graph/memory/cross_vector.py` promotes high-quality evidence to global LTM in Chroma.
- `src/polaris_graph/memory/session_feedback.py` records strategy outcomes.
- `src/polaris_graph/memory/evidence_hierarchy.py` stores L0/L1/L2 evidence summaries.
- `src/agents/analyst_agent.py` enriches facts into a knowledge graph.
- `scripts/static/js/memory_dashboard.js` shows there is already a UI concept for memory.
- Audit-grade conflict: user-visible memory implies cross-run prior injection. If that prior changes an answer without an explicit provenance trail, V30 loses the core trust property.
- Moat impact: `neutral-to-amplify` if memory is retrieval-only, labeled, workspace-scoped, and user-governed. `dilute` if memory becomes silent latent bias.
- Build cost: `10-18 eng days` for workspace-scoped saved notes, pinned prior sources, and inspect/delete controls over existing memory primitives. `25-40 eng days` for a real persistent workspace knowledge graph with freshness, invalidation, and collaborative editing.
- Phase placement: `C` for user-visible workspace memory. `D` for strong autonomous accumulation.
- Anti-pattern flag: `yes`, if memory silently mutates future outputs or mixes unsupported priors into the audit lane.
- Specific competitor benchmark: NotebookLM saved notes; Manus memory; Perplexity Spaces.
- Acceptance criteria:
- Memory items are visible, attributable, and removable by the user.
- Retrieved priors are labeled as memory-derived, not blended invisibly into primary evidence.
- Workspace boundaries are strict; no leakage across customers or projects.
- Freshness and staleness rules exist for time-sensitive topics.

### 4. Chart / table / artifact generation

- Strategic class: `need-to-have`.
- User expectation: users mean ChatGPT Code Interpreter or Gemini Visual Reports: ask for a comparison table, trend chart, or artifact and get a polished output, not just markdown prose.
- Imported quality bar: real numeric extraction, not decorative charts from guessed values; downloadable artifacts; clean layout; fast turnaround.
- V30 today: `partial`.
- V30 already has deterministic text tables like the trial summary/table builders.
- `src/tools/visual_generator.py` supports SVG chart/timeline/table specs.
- `src/polaris_graph/tools/data_analyzer.py` can generate real charts/tables by executing Python.
- `src/polaris_graph/synthesis/smart_art_generator.py` generates Mermaid diagrams.
- Mesh artifact directives already define `TABLE`, `CHART`, `FLOW`, `DECK`, `FLASHCARDS`, but only `TABLE` renders today; the rest are deferred stubs in `artifact_directives.py`.
- Audit-grade conflict: the chart cannot be a visual paraphrase of prose. Every plotted value must come from cited structured rows, with explicit refusal when the evidence is not numerically extractable.
- Moat impact: `amplify`.
- Build cost: `8-15 eng days` for a trustworthy beta artifact pack: cited tables, numeric charts, Mermaid/flow diagrams, export wiring, and failure/refusal rules. `20-30 eng days` if it must be polished across HTML/DOCX/PDF at product quality.
- Phase placement: `B`.
- Anti-pattern flag: `no`.
- Specific competitor benchmark: ChatGPT Code Interpreter + Canvas; Gemini visual reports.
- Acceptance criteria:
- Every chart is backed by a machine-readable source table with evidence IDs.
- Visuals fail closed when extraction confidence is below threshold.
- Contradictions and caveats carry into captions/footnotes.
- User can export chart image plus source table plus citation appendix.

### 5. Infographic generation

- Strategic class: `trap`.
- User expectation: users mean Manus/Gemini-class polished, shareable, branded visual summaries that look agency-made, not "AI chart with icons."
- Imported quality bar: high design polish, narrative compression, and one-glance comprehension. Users implicitly expect the infographic to be publishable.
- V30 today: `none` in the product sense. There are chart and diagram primitives, but not a real infographic system.
- Audit-grade conflict: infographics compress nuance aggressively. That is exactly where provenance, confidence bounds, contradictions, and scope limitations get erased.
- Moat impact: `dilute` unless heavily constrained to derivative visuals from already-approved structured claims.
- Build cost: `15-25 eng days` for a constrained "fact card / evidence poster" generator. `40-80 eng days` for anything approaching Manus/Gemini polish and template breadth.
- Phase placement: `D`.
- Anti-pattern flag: `yes`.
- Specific competitor benchmark: Gemini Canvas visual reports; GPT image-gen-infographic workflows; Manus deliverables.
- Acceptance criteria:
- Only allowed from already-verified structured facts, not from raw prose.
- Every panel has a compact reference footer or appendix hook.
- Refuses when there is not enough structure to compress without distortion.
- Treated as a derivative marketing artifact, never the canonical audit artifact.

### 6. 1-click slide deck

- Strategic class: `need-to-have`, but as a derivative enterprise output, not as a first ship.
- User expectation: when users say Manus-class deck, they mean "turn my research into a board-ready 12-20 slide deck with visuals, executive framing, and almost no cleanup."
- Imported quality bar: coherent storyline, visual hierarchy, charts, speaker notes, brand consistency, and export to PPTX/PDF/HTML.
- V30 today: `none` as a finished product. Relevant primitives exist:
- report assembly
- DOCX export
- chart generation
- smart-art diagrams
- mesh artifact directives with a deferred `DECK` directive
- Audit-grade conflict: decks compress aggressively. Unsupported bullets, decontextualized numbers, and contradictions dropped for story smoothness will destroy the moat.
- Moat impact: `amplify` if slide bullets remain citation-bound and each slide can drill down to an appendix/source panel.
- Build cost: `12-20 eng days` for a reliable beta deck composer using existing report output plus chart/diagram primitives. `25-40 eng days` for polished theme support, speaker notes, appendix automation, and PPTX fidelity.
- Phase placement: `C`, with a narrow beta possible late in `B`.
- Anti-pattern flag: `no`, but only if the deck is downstream of the verified artifact.
- Specific competitor benchmark: Manus deck generation.
- Acceptance criteria:
- Generates a 12-20 slide deck from a verified report plus structured data.
- Every substantive slide has slide-level citations or a linked appendix slide.
- Contradictions and limitations survive in either the main slide or notes.
- Export works in PPTX and HTML/PDF without breaking references.

### 7. 1-click video / audio overview

- Strategic class: `trap`.
- User expectation: users mean NotebookLM Audio Overview or Gemini audio conversion: click once, get a compelling two-host or narrated summary that sounds polished and trustworthy.
- Imported quality bar: humanlike pacing, strong script, memorable framing, fast generation, and low cleanup. Users assume the spoken content is safe to trust.
- V30 today: `none`. The repo can ingest audio, but there is no script-to-TTS-to-mixed-output artifact lane.
- Audit-grade conflict: audio strips away inline citations. The most differentiated thing V30 has becomes invisible. Spoken certainty also tends to overstate the evidence unless aggressively constrained.
- Moat impact: `dilute`.
- Build cost: `18-30 eng days` for a cautious script + transcript + TTS audio proof. `45-90 eng days` for NotebookLM-class two-host quality, editing, mixing, retries, and safe citation carry-through.
- Phase placement: `D`.
- Anti-pattern flag: `yes`.
- Specific competitor benchmark: NotebookLM Audio Overview; Gemini audio report conversion.
- Acceptance criteria:
- Script is generated only from an already-approved report artifact.
- Transcript and show notes include timestamps and references for every segment.
- Spoken output hedges appropriately and never outruns the evidence.
- Audio/video is clearly labeled derivative, not canonical audit output.

## Trap detection

### Trap 1 — Infographic generation

- Why it hurts V30: it pushes the team toward compressive polish instead of provenance. The likely result is visually impressive but epistemically weaker output.
- What to ship instead: cited charts, evidence posters, and contradiction-aware visual briefs with explicit reference appendices.

### Trap 2 — 1-click video / audio overview

- Why it hurts V30: the citation layer does not survive naturally in speech, and "podcast confidence" is a bad fit for audit-grade research.
- What to ship instead: narrated transcript plus chaptered audio summary as a derivative export, only after the written artifact is approved.

### Trap 3 — "Massive upload" if interpreted as 300-500 PDFs/session right now

- Why it hurts V30: this shifts the roadmap from audit-grade research product into ingestion/RAG infrastructure product, with parser QA, storage, permissions, and retention becoming the dominant engineering problem.
- What to ship instead: bounded workspace corpora first: 10-50 docs/workspace in beta, persistent, source-locked, and provenance-rich.

## Critical UX call

- "1-click magic" is compatible with audit-grade discipline only in a split sense.
- It is compatible for `kickoff`: user asks for an outcome once, the system auto-selects the right workflow, and the complexity is hidden.
- It is not compatible for `blind trust`: the system still has to expose scope, source set, confidence, contradictions, and artifact type.
- Recommended UX:
- One compose box.
- One visible mode selector the user rarely touches: `Preview` or `Audit`.
- Auto-template / auto-corpus selection in the background.
- Immediate progress surface and time-to-first-artifact in minutes.
- Final output clearly labeled as `Preview artifact` or `Audit artifact`.
- Short version: `1 click to start` is good. `1 click to trust` is not.

## Proposed composition layer

- Recommendation: `one composition core, multiple renderers`.
- Do not build separate end-to-end stacks for chart, infographic, deck, and audio.
- Build a single `artifact_composer` layer that consumes verified report state and emits a normalized intermediate representation:
- sections
- claim blocks
- contradiction blocks
- structured data tables
- chart specs
- diagram specs
- bibliography map
- citation-to-span map
- Then add per-format renderers:
- markdown/html report
- docx
- deck
- chart pack
- infographic/fact poster
- audio script

Why this is the right fit for the repo:
- `report_assembler.py` and `report_assembler_v2.py` already prove assembly is a separate concern.
- `docx_exporter.py` is already a renderer.
- `smart_art_generator.py` is already a renderer input producer.
- `visual_generator.py` and `data_analyzer.py` already generate visual artifacts.
- `wiki/mesh/compose/artifact_directives.py` already models a directive-based artifact surface, and its `CHART` / `DECK` / `FLOW` stubs show where the fan-out should happen.

Guardrail:
- composition must be downstream of verification.
- no renderer gets to invent facts.
- renderers may only compress, reorder, or visualize already-approved content.

## Citation-discipline carry-through

### Deck

- Citation survival: `strong, if designed deliberately`.
- Recommended form:
- slide-level footnotes for the main claims
- appendix slide with expanded references
- clickable source panel in HTML export
- speaker notes carrying caveats/contradictions
- Verdict: compatible with the moat.

### Infographic

- Citation survival: `medium at best`.
- Recommended form:
- panel footer references
- QR/link to full appendix
- only use numeric claims that map cleanly to source tables
- Verdict: only safe as a derivative, constrained artifact.

### Video / audio

- Citation survival: `weak`.
- Recommended form:
- chaptered transcript with source markers
- companion show notes with timestamps
- optional on-screen source IDs for video
- Verdict: not suitable as the canonical audit surface.

## Snowball + upload architecture

- Recommended architecture for wishes 2 + 3:
- Ingestion service:
- file upload, URL import, text import
- parse, OCR, transcription, metadata capture
- content hashing, dedupe, retry, failure states
- Corpus store:
- workspace-scoped document manifests
- extracted text + page/span offsets
- parser version and artifact retention metadata
- Index layer:
- vector index plus lexical/doc filters
- persistent workspace collections, not session-only collections
- provenance-preserving chunk IDs
- Memory layer:
- promote verified evidence to workspace memory
- support pins, notes, approvals, expiry, and delete
- keep global/system LTM separate from workspace memory
- Retrieval layer:
- uploaded corpus only / web only / blended retrieval modes
- contradiction-aware synthesis that treats uploaded docs as first-class evidence
- Governance layer:
- retention, deletion, permissioning, audit log, and stale-memory invalidation

- Scope call:
- In-scope for V30 Phase-2 era: persistent workspace upload + bounded corpus analysis.
- Out of scope for V30 Phase-2 era: 300-500 PDFs per session as default user behavior.
- Honest call: that latter version is close to a separate product, or at minimum a late `Phase D` capability.

## Recommended PRD bundle for the next ship

- Best 4-12 week bundle:
- bounded upload + analysis
- constrained WikiLLM workspace brief
- chart/table/artifact pack
- basic citation-bound slide deck export

Why this bundle wins:
- It strengthens the moat instead of chasing consumer-polish theatrics.
- It turns `report.md` into multiple usable enterprise deliverables.
- It creates clear user moments that NotebookLM and Manus do not own as well:
- upload a diligence packet, ask one question, get a citation-bound brief
- generate a decision table/chart from verified evidence
- hand an executive a deck that still traces back to primary sources

- Explicitly exclude from the next ship:
- infographic polish
- 1-click video/audio
- fully autonomous snowball memory
- 300-500 PDF/session ingestion promises

## Risks Codex sees that Claude missed

- The repo already has partial UI/API for NotebookLM-style source import and source briefing. That is useful, but it also raises product-risk: users may assume full corpus intelligence already exists when the audit lane is still report-centric.
- `src/agents/citefirst/report_composition.py` is missing even though audit docs mention it as a stub. That is a warning that the composition layer is conceptually present but not product-hardened.
- `smart_art_generator.py` exists, but `anti_tunnel_view_test.py` flags a known gap that smart-art may not actually be injected into the final report path. Do not overcount artifact maturity.
- Existing session-scoped local document RAG is not enough for the wishlist. Without workspace persistence, memory deletion controls, and provenance UI, the product will feel flakier than NotebookLM even if the backend primitives are good.
- Uploads create privacy and retention obligations fast. The moment users believe they can upload internal corpora, deletion, access control, and document lineage become product-critical rather than future enterprise polish.
- Audio/video does not just add compute cost. It adds tone risk, certainty inflation, and a much harder review burden because the output is harder to inspect sentence-by-sentence than text.
