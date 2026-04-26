# Codex review of V30 joint user-wishlist analysis

## Verdict
PARTIAL

The moat logic is mostly right. The trap calls are mostly right. The main problems are sequencing and undercounted product-hardening cost: `JOINT_ANALYSIS.md` treats bounded upload, Workspace Brief, and the Evidence Inspector as more Phase-B-ready than the current architecture really is, and it does not fully adapt the composition story to the audit-only single-lane product shape.

## Per-wish triage assessment

### Wish 1 — WikiLLM / Workspace Brief

- Claude's call: ship-now in Phase B, but only as bounded `Workspace Brief`.
- Codex's call: ship-now only if it is narrowed further to a `question-bound corpus brief` or `post-run workspace brief`; otherwise ship-later.
- Agreement / disagreement / nuance: partial.
- Reasoning: the repo has real composition primitives (`wiki_composer.py`) and a lightweight source-briefing endpoint, but the product is still query/report-centric, not workspace-corpus-centric. Uploaded docs are currently injected into session state and chunked into ad hoc GOLD evidence; that is not the same thing as a persistent, inspectable corpus-brief product.
- Reasoning: the label `Workspace Brief` over-promises. Users will hear "living notebook/wiki summary of my corpus." The current architecture can plausibly support "answer one bounded question over this selected corpus and emit a cited brief." That is narrower.
- Recommended fix: rename the bounded Phase B form to `Question-Bound Corpus Brief` or `Post-Run Workspace Brief`.
- Recommended fix: make it explicitly dependent on wish #2 landing first. Do not present it as equal-scope parallel work.

### Wish 2 — Massive upload + analysis

- Claude's call: ship-now in Phase B for 10-50 docs/workspace; 15-25 eng days.
- Codex's call: ship-now in bounded form, but the estimate is low.
- Agreement / disagreement / nuance: agreement on category, disagreement on cost/risk.
- Reasoning: current upload/storage is global disk persistence under `data/documents/{doc_id}` with global list/detail/delete endpoints, not workspace-scoped product storage. Current retrieval is `LocalDocumentRAG("docs_{session_id}")`, not persistent workspace corpus retrieval.
- Reasoning: current analyzer behavior is a useful prototype, not a product-hard provenance stack. Uploaded docs are chopped into ~2000-char chunks and injected as GOLD evidence. That is materially weaker than "page/span/parser-version-grade corpus provenance."
- Reasoning: there is no real workspace manifest, permission model, parser-status pipeline, or uploaded-doc provenance map at product grade yet.
- Recommended fix: raise the bounded-upload estimate to roughly 25-40 eng days, possibly 30-45 if page/slide/sheet lineage and delete semantics are included honestly.
- Recommended fix: call out that workspace scoping, auth, deletion, and provenance mapping are the real Phase-B work, not just parser support.

### Wish 3 — Snowball memory + knowledge accumulation

- Claude's call: ship-later in Phase C.
- Codex's call: ship-later in Phase C for retrieval-active memory; thin passive notebook features can come earlier.
- Agreement / disagreement / nuance: mostly agree.
- Reasoning: full memory that actively influences future outputs must be user-visible, workspace-scoped, attributable, and deletable. That is Phase C product work.
- Reasoning: a thinner Phase-B feature is possible: saved notes, pinned sources, bookmarks, and manual annotations that do not silently steer synthesis.
- Recommended fix: distinguish `passive saved workspace notes` from `retrieval-active memory`. Only the latter belongs in the current wish #3 category.

### Wish 4 — Chart / table / artifact generation

- Claude's call: ship-now in Phase B.
- Codex's call: ship-now in Phase B.
- Agreement / disagreement / nuance: agree, with scope caution.
- Reasoning: this is still the cleanest moat-amplifier. The strongest version is not "AI visuals"; it is cited tables plus numeric charts where every value traces back to structured evidence rows.
- Reasoning: do not overcount current maturity. Some artifact primitives exist, but not all of them are fully wired into the final report path.
- Recommended fix: make `cited tables + numeric charts + export bundle` the core Phase-B artifact scope. Treat Mermaid/flow polish as secondary.

### Wish 5 — Infographic generation

- Claude's call: trap, defer to Phase D.
- Codex's call: trap, possibly never except as a constrained evidence poster.
- Agreement / disagreement / nuance: agree.
- Reasoning: the compression pressure is exactly wrong for V30. It hides caveats, contradictions, uncertainty, and provenance.
- Recommended fix: none beyond making it even more explicitly non-canonical.

### Wish 6 — 1-click slide deck

- Claude's call: ship-later in Phase C, with a narrow late-Phase-B beta possible.
- Codex's call: ship-later overall, but explicitly preserve `late-B beta` as a serious option.
- Agreement / disagreement / nuance: partial.
- Reasoning: once a stable composition IR exists, a minimal deck renderer is mostly derivative composition/export work. In practice, that may be more bounded than wish #1.
- Reasoning: the wrong version is "board-ready Manus deck." The right version is "appendix-heavy citation-bound deck export from a verified report."
- Recommended fix: keep full deck polish in Phase C, but add an explicit note that if one additional derivative artifact is pulled into late Phase B, deck beta is the better candidate than a broader Workspace Brief.

### Wish 7 — 1-click video / audio overview

- Claude's call: trap, Phase D derivative only.
- Codex's call: trap.
- Agreement / disagreement / nuance: agree.
- Reasoning: the audit moat becomes invisible in audio/video, and review burden rises because spoken confidence is harder to inspect than text.
- Recommended fix: none beyond keeping it derivative-only if it ever exists.

## Composition architecture

Yes, `one composition core, multiple renderers` still holds.

What changes under the audit-only + Evidence Inspector pivot is the canonical surface.

- The canonical product surface should not be thought of as `report markdown` plus some exports.
- The canonical product surface should be the `audit graph / audit IR` rendered through the Evidence Inspector.
- The report, PDF, DOCX, charts, brief, and deck are projections of that audit IR.

The current write-up is directionally correct but underspecified. The IR needs more than sections and chart specs. It needs:

- Stable claim IDs.
- Evidence-span bindings.
- Contradiction edges.
- Frame / contract coverage mappings.
- Artifact element lineage.

Without artifact lineage, the "round-trip back to inspector views" claim stays aspirational. A chart point, deck bullet, or brief paragraph needs a stable pointer back to the same claim/evidence objects the Inspector renders.

Recommended wording change:

- Keep `one core, many renderers`.
- Add: `Evidence Inspector is the primary audit renderer over the canonical claim/evidence graph; all other renderers are derivative projections that must retain back-links to claim IDs.`

## Snowball + upload

The layering is mostly right, but it conflates different kinds of memory and treats governance like a terminal layer when it is really cross-cutting.

My recommended split is:

1. Ingestion / parser orchestration.
2. Document store + provenance map.
3. Retrieval indexes.
4. Run/session state.
5. Workspace memory.
6. Retrieval/synthesis orchestration.
7. Governance/auth/retention/audit as a cross-cutting plane.

The key correction is the memory split.

- `Session memory` is ephemeral run state, scratch notes, current query context, and partial progress.
- `Workspace memory` is user-visible, user-deletable, scoped retained knowledge.
- `System/global memory` is operator or product memory and should not silently influence the audit lane.

That split matters because the current repo already has multiple memory-like mechanisms. Some are run-local. Some are cross-run. Some are global. For an audit-grade product, those cannot all sit under one vague "memory layer."

My call on the user's specific question: yes, the memory layer should be split explicitly into `session memory` and `workspace memory`, and global/system memory should be called out separately and quarantined from the audit lane by default.

## 1-click UX

`1 click to start yes; 1 click to trust no` still holds.

What changes under the audit-only single-lane pivot is that the time-to-first-value mechanism cannot be a prose preview anymore. If the Evidence Inspector only appears at the end, then yes, you have a real 2h25m blank-stare problem.

What should replace the Preview lane is not a weaker answer. It should be progressive audit-native surfaces:

- Pre-flight scope, template, time, cost, and source-count estimate.
- Upload/parse progress per document.
- Live source discovery with tier mix.
- Frame coverage manifest filling in as evidence arrives.
- Contradiction queue appearing before final synthesis.
- First verified claim cards or evidence cards as soon as they exist.

The product goal should be: `first inspectable evidence state`, not `first draft prose`.

That is the missing adjustment in `JOINT_ANALYSIS.md`. It says "immediate progress surface," which is directionally right but too weak. In an audit-only product, progressive Inspector state is a core UX requirement, not polish.

## PRD bundle scope

The stated `52-86 eng days = 5-9 weeks` is an optimistic lower bound, not the realistic planning number.

Why it is low:

- Wish #2 is priced like parser/product glue, but the real work is workspace data model, permissions, retention, deletion, and provenance mapping.
- Wish #1 is not free once wish #2 exists. It is another synthesis surface with its own QA burden.
- Wish #4 is promising, but trustworthy charting still needs source-table binding, refusal behavior, and export integration.
- Evidence Inspector in an audit-only product needs progressive/live behavior, not just a static final-state renderer.
- Editorial/template QA starts biting earlier than the doc admits, because once you add brief/deck/chart surfaces, output QA is not only model QA anymore.

My revised scope call:

- `52-86 eng days` is possible only if the bounded brief is extremely narrow and some live/progressive Inspector behavior slips.
- A more realistic committed range is roughly `70-110 eng days`, or about `7-11 weeks` for a small strong team.
- If you want to stay inside the lower range, cut or narrow wish #1 first.

## What Claude missed

1. The current upload path is not workspace-scoped. The repo stores documents globally and indexes them per session. That means bounded upload is not just "more polish"; it is a data-model change.

2. Page/span-grade provenance for uploaded documents is not solved by the current document path. The current system has char offsets and extracted HTML/text, but not a product-ready provenance map for PDF page coordinates, slide references, sheet references, and timecodes.

3. The Evidence Inspector should be treated as the canonical renderer over an audit graph, not just another consumer of report output.

4. `Workspace Brief` is too broad a label for the feasible Phase-B artifact. The realistic Phase-B form is question-bound and derivative, not a living corpus wiki.

5. There is an important distinction between passive saved notes and retrieval-active memory. The former can ship earlier; the latter should not.

6. The non-wishlist features from the real-user synthesis are closer to requirements than some of the named wishes: pause/save mid-run, pre-flight cost/time, locked evidence scopes, checkpoint/resume, and human review queue.

7. Hidden global/system memory is a real audit-lane risk. Once uploads and memory coexist, silent prior injection becomes a trust problem, not just a UX issue.

## Risks Claude undercounts

| Risk | Probability | Impact | Assessment |
|---|---:|---:|---|
| PHI creep once uploads ship | 70-90% | Severe | In a clinical product, users will try to upload patient-adjacent material quickly. Blocking text alone is not enough. This becomes policy, product, and enterprise-governance work immediately. |
| Editorial QA throughput becomes the bottleneck | 60-80% | High | As soon as you ship multiple audited output surfaces, template quality, artifact rules, appendix carry-through, and contradiction handling become curator/medical-writer throughput problems, not just engineering problems. |
| Single-lane 2h25m blank-stare UX gap | 50-70% | High | If the Inspector is mostly a completion-time artifact, activation and trust will suffer before users ever see the moat. |
| Uploaded-document provenance gap | 70-85% | High | Current upload handling is useful but not yet product-grade provenance. This is exactly the kind of defect that will make an audit-grade claim ring hollow. |
| Hidden memory contamination | 30-50% | Severe | Session memory, workspace memory, and global/system priors can silently blur together unless explicitly separated and labeled. One silent prior-injection incident can damage the whole product story. |

## Recommended fixes to JOINT_ANALYSIS.md

1. Change wish #1 wording from `Workspace Brief` to `Question-Bound Corpus Brief` or `Post-Run Workspace Brief`, and say explicitly that true workspace/wiki behavior remains later.

2. Raise wish #2 bounded-upload estimate. The current `15-25 eng days` underprices workspace scoping, deletion semantics, auth, provenance mapping, and parser-status UX.

3. Rewrite the composition section so that the canonical object is an audit graph / claim-evidence IR, with Evidence Inspector as the primary renderer and all other outputs as derivative projections with back-links.

4. Split the memory section into `session memory`, `workspace memory`, and `global/system memory`, and say that only workspace memory may participate in the audit lane by default, with user-visible lineage and delete controls.

5. Expand the `1-click magic` section to specify the audit-native progressive surfaces that replace the Preview lane. "Immediate progress surface" is not enough.

6. In the scope sanity check, either raise the total estimate to a more realistic range or explicitly say the lower estimate assumes wish #1 is narrower than the current wording implies.

7. Add one explicit sequencing note: if a late-Phase-B derivative artifact is pulled forward, deck beta is the better candidate than a broader corpus-brief promise.
