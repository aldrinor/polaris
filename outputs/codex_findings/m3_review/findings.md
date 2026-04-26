# Codex review of M-3

## Verdict
PARTIAL

## Markdown renderer assessment
- Handles the current run-14 core well: headings, paragraphs, bullet lists, Trial Summary table citations, consecutive citations `[19][20]`, end punctuation, and HTML escaping in markdown text. The targeted markdown/router tests pass.
- Real V30 report still has one user-visible miss: the `---` separator before the retrieval-coverage disclosure renders as literal paragraph text because `markdown.js` has no horizontal-rule branch.
- Adjacent tables are not robust. The parser keeps consuming `|` lines as rows, so back-to-back tables only work if a blank line separates them. Run-14 is safe today, but this is not a stable contract.
- Nested constructs are intentionally unsupported. `- ### foo` renders as literal list text, and an indented heading inside a list breaks into a paragraph. Not present in run-14, but this is not a general-purpose markdown subset.

## Click-to-inspect contract
- `[N] -> bibliography` lookup is deterministic on run-14 and unresolved citations are guarded.
- Verified vs dropped sentences are visually separated clearly enough for Phase A.
- The pane does not deliver the full `FINAL_PLAN` promise. It shows tier + bibliography statement + sentence token offsets, but not exact PDF page/span.
- The contradiction section does not show the contradicting claims side-by-side. It only renders the clicked claim from each cluster.
- There is also ID drift between report bibliography IDs and contradiction claim IDs. Under the current exact-equality match, only 6 of 26 bibliography entries can ever surface contradiction rows in run-14; e.g. `[19]` resolves to `ev_235` and shows zero contradiction rows while adjacent `[20]` resolves to `ev_227` and does.

## Specific issues
- High: the “split-pane” is not actually laid out as a split pane. `aside.evidence-pane` lives outside `.inspector-main`, but the 2-column grid is applied only to `.inspector-main`; the pane is never a grid child and has no fixed/right positioning. `scripts/templates/inspector_shell.html:48`, `scripts/templates/inspector_shell.html:80`, `scripts/static/inspector/inspector.css:176`, `scripts/static/inspector/inspector.css:182`, `scripts/static/inspector/inspector.css:249`
- High: contradiction drilldown only shows the active claim, not the opposing claims in the cluster. `buildEvidenceIndex()` stores `{cluster, claim}` pairs, and `renderEvidencePane()` renders `c.claim` only; `c.cluster.claims` is ignored. That misses the plan’s “contradicting evidence with its own span/source” requirement. `scripts/static/inspector/inspector.js:111`, `scripts/static/inspector/inspector.js:209`
- High: provenance surface falls short of the acceptance text. View 1 shows sentence token offsets (`start-end`) and bibliography metadata, but no PDF page, no source snippet for the clicked evidence, and no canonical source-offset object shared with contradiction claims. Current IR has sentence char offsets and contradiction `context_snippet`, but not a unified page/span provenance record. `scripts/static/inspector/inspector.js:162`, `scripts/static/inspector/inspector.js:189`, `src/polaris_graph/audit_ir/loader.py:60`, `src/polaris_graph/audit_ir/loader.py:116`
- Medium: contradiction matching is exact `evidence_id` equality, but run-14 mixes namespaces (`surpass_1_primary` vs `ev_189`). That makes “contradictions involving this evidence” materially incomplete for many report citations. `scripts/static/inspector/inspector.js:110`, `outputs/full_scale_v30_phase2_run14/clinical/clinical_tirzepatide_t2dm/report.md:75`
- Medium: XSS hardening is incomplete. `tierBadge()` injects raw `tier` into HTML/class context, and bibliography URLs are only HTML-escaped, not protocol-sanitized, before going into `href`. With CSP currently allowing `'unsafe-inline'`, this is not just theoretical debt. `scripts/static/inspector/inspector.js:127`, `scripts/static/inspector/inspector.js:168`, `scripts/live_server.py:1410`
- Medium: keyboard support is partial, not complete. Enter/Space/Escape work, but citations have no `aria-label`, no `aria-controls`, no `aria-expanded`, and opening the pane does not move focus into it or return focus on close. Also `role="button"` is layered onto anchors instead of using a real button element. `scripts/static/inspector/markdown.js:25`, `scripts/static/inspector/inspector.js:255`
- Low: the real report’s `---` separator renders as literal text. `scripts/static/inspector/markdown.js:67`, `outputs/full_scale_v30_phase2_run14/clinical/clinical_tirzepatide_t2dm/report.md:156`
- Low: renderer/test coverage is still below the declared contract. There are no tests for the real `---` separator, adjacent tables, nested constructs, focus behavior, or hostile `javascript:` URLs in IR payloads. `tests/polaris_graph/test_inspector_markdown.py:24`, `tests/polaris_graph/test_inspector_router.py:125`

## Recommended changes
- Move `#evidence-pane` into the same layout container as the report, or make the page shell itself a 2-column grid/flex row. Do not rely on a grid defined on `main` when the pane is a sibling.
- Render contradiction rows from `cluster.claims`, with the clicked claim highlighted and the opposing claims visible beside it. Show at minimum `source_tier`, `source_url`, and `context_snippet`; otherwise M-4 will need to rebuild this path.
- Normalize provenance identity across views now. Either make bibliography and contradiction claims share the same canonical `evidence_id`, or add a resolver keyed by DOI/URL/source identity. Exact-ID matching is too brittle.
- Introduce a canonical provenance payload for UI use: `{evidence_id, source_url, page?, start, end, snippet}`. Without that, View 1 and M-4 cannot meet the plan’s span/page story.
- Replace string-built HTML for the evidence pane with DOM node construction or stricter escaping helpers. Validate `tier`/`severity` against an enum and only allow `http:`/`https:` URLs in anchors.
- Tighten a11y: real button semantics or labeled controls, `aria-controls`/`aria-expanded`, focus transfer to the pane close button or heading on open, and focus return on close.
- Add tests using real run-14 fragments: Trial Summary table cells, `[19][20]`, the bibliography separator, and a malicious `javascript:` URL / malformed tier.

## M-4 readiness
- IR is ready for a basic contradiction matrix list with filters over `predicate`, `dose`, `severity`, and `source_tier`.
- IR is not ready for the `FINAL_PLAN` version of M-4: both-source side-by-side with span highlights. You need normalized provenance identity plus per-claim page/offset/snippet data first.
- The current shell/controller structure is also not Phase-B-friendly. `wireCitationInteraction()` binds global listeners per render, and the report DOM does not preserve `claim_id` anchors, so progressive claim cards and cross-view back-links will force a refactor if not addressed now.

## Final word
PARTIAL with edits. Do not GREEN-lock M-3 as the canonical View 1 until the split-pane layout, contradiction drilldown completeness, and provenance/XSS gaps are fixed.
