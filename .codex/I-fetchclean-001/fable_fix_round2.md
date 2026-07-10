# I-fetchclean-001 — Fable round-2 fix design (15 residual leaks from live retest)

Author: Fable 5. Scope: `src/tools/access_bypass.py` (strip_markdown_nav_chrome + clean_fetch_body),
`src/polaris_graph/retrieval/shell_detector.py` (vocab), `src/polaris_graph/retrieval/live_retriever.py`
(`_build_provenance_quote` window hygiene). Faithfulness engine untouched. All additions flag-gated
DEFAULT-ON, OFF = byte-identical to round-1.

## The four root causes (every leak maps to one or more)

**RC1 — heading-line bypass.** `strip_markdown_nav_chrome` step 1: any line matching
`_MD_HEADING_RE` (`^#{1,6}\s`) is kept **byte-identical** via early `continue`. Jina/crawl4ai
space-collapse welds nav tickers, breadcrumbs, image markdown, and CMP consent blocks onto ONE
heading-prefixed line, so the whole welded line skips every chrome rule.
Leaks: ev_880 wharton (`#### … # Updates # … ![Image 1: …`), ev_195 thehill (`## Just In [news](…)[News](…) 2 hours ago`), ev_244 appunite (`## You control your data We and our business partners use technologies, including cookies…`), ev_441 ama (welded `##` heading).

**RC2 — body-line vs span-line granularity mismatch (density dilution).** Production measures
link density on the FULL welded body line; long real prose on the same line dilutes density
below 0.5, so the embedded nav/CTA link-run survives. The stored `direct_quote` is then a
**window slice** (`_build_provenance_quote`: head + 500-char decimal windows) of that line — the
slice IS link-dense, and the retest scanner (correctly) flags it. No per-line threshold change
can fix this; the chrome must be removed **inside** kept lines, token-only.
Leaks: ev_011 commerce.nc.gov (prose + inline study links — real prose, the junk is the raw
`](https://…)` URL chrome in the span), ev_896 oa.mg (related-posts link-run welded after blog
prose), ev_045 oecd (prose + welded TOC/share link-run), ev_191 oska (prose + `[Key finfings](…pdf)`
download-CTA run), ev_891 punku (prose + `- [Title](/blog/…)- description` related-posts list),
ev_037 bipartisanpolicy (endnote line correctly KEPT by ref-mode; the junk is the footnote
back-link fragment `…/#4468eeee-…-link)` — see also RC4).

**RC3 — vocab gaps.** No production pattern exists for: login-wall sentences ("You must be logged
in to download this publication" + `[Download as guest](url)`) — ev_117 nationalacademies (also
only ONE md link on the line, so the `>=2 links` floor never fires); `Crossref N` citation-count
widget welded before real prose — ev_497 bls.gov; EU/CMP cookie-banner sentences ("This site uses
cookies. Visit our [cookies policy page](…)", IAB copy "We and our business partners use
technologies, including cookies, to collect information about you…") — ev_726 social-economy-gateway,
ev_244 appunite; empty-anchor links `[](url)` / `[ ](url)` and bare parenthesized URL echoes
`(https://… )` / `(url#site-content)(url#page-footer)` — ev_933 scale.stanford, ev_441 ama,
ev_726; image markdown `![alt](…` — ev_880; `N hours ago` ticker tokens — ev_195; RePEc
serial-index chrome ("Printed from https://ideas.repec.org" + "Follow this serial" — a journal
INDEX page, not an article; bare text labels carry no md links so density is blind) — ev_748.

**RC4 — span windows cut mid-markdown-link.** `_build_provenance_quote` decimal windows and the
head cap slice at raw char offsets, leaving dangling URL debris (`…-link)`, `…-100-feet/ "…")`)
at span boundaries. Leaks: ev_037, ev_896, ev_933.

Scanner-side note (report to operator, no production change): `fetch_corpus_replay.py` stores
`line[:220]` and runs the citation-signal FP filter on the TRUNCATED text — ev_037's year was cut
to "October 202" and `et.al` (no space) misses `\bet\s+al\b`, so a kept-by-design reference line
was counted as junk. Recommend the scanner test the FULL line and add `et\.?\s*al`. The leading
back-link fragment on ev_037 is still real junk — fixed by RC4/Fix-2c below.

## Incremental fix (5 parts, surgical)

**Fix 1 — process heading lines (RC1).** In `strip_markdown_nav_chrome`, heading-matched lines no
longer `continue` untouched: run the SAME inline token removals (Fix 2 + Fix 3) on the heading
line before appending. Heading TEXT is always kept; ref-mode open/close logic unchanged.

**Fix 2 — inline markdown-link policy on kept lines (RC2, the core).** New pure helper applied to
every kept line NOT in ref-mode and NOT `_line_is_reference_like` (the sacred guard: reference /
citation lines — DOI, year, et-al, pp., vol(issue) — are byte-identical, links preserved):
  a. **Delete** empty-anchor links `\[\s*\]\([^)]*\)` (no anchor text = pure chrome).
  b. **Delete** image tokens `!\[[^\]]*\]\([^)]*\)` plus a dangling line-trailing `!\[[^\]]*$`.
  c. **Delete** whole links whose target is site-nav: relative (`](/…)`), pure fragment (`](#…)`),
     or same-page `#…` fragment with an empty/symbolic/≤2-char anchor (footnote back-links).
     Exception: (c) also runs inside ref-mode for the empty/symbolic-anchor back-link form ONLY —
     it carries zero citation content (ev_037).
  d. **Unwrap** every remaining inline link to its anchor text (`[business writing](url)` →
     `business writing`): prose byte-preserved, URL chrome gone. This structurally closes the
     nav_link_density class outside references — commerce/oecd/oska/punku/oa.mg spans become
     link-free prose (residual related-post TITLE text may remain; it is plain text, no longer
     junk chrome, and the off-topic judge owns whole-source relevance).
  Order: existing whole-line `_is_nav_link_line` DROP runs FIRST (unchanged), then a-d on survivors.

**Fix 3 — chrome vocab additions (RC3),** all structure-anchored token-only inline removals in
access_bypass (never whole-line unless already whitespace-only after removal):
  - Login-wall: `You must be logged in to \w+ this publication\.?`, `\[Download as guest\]\([^)]*\)`.
  - Line-leading citation-count widget: `^\s*Crossref\s+\d+\s+(?=\S)` (token only; prose after kept).
  - Cookie/CMP sentence runs, CTA-anchored so prose ABOUT cookies never matches:
    `This site uses cookies\.\s*Visit our \[cookies policy page\]\([^)]*\)[^.]*\.?`;
    `We and our (?:business )?partners use technologies, including cookies,.*?(?:\.|:)` through the
    first sentence/colon; standalone heading text `You control your data` (exact, case-insensitive).
  - Ticker token: `\d+\s+(?:hour|minute|day)s?\s+ago` deleted inline.
  - Bare-paren URL echo: standalone `\(\s*https?://[^)\s]+\s*\)` NOT preceded by `]` (so real md
    links untouched), skipped on reference-like lines.
  - shell_detector: add any-length co-occurrence tuple `("printed from https://ideas.repec.org",
    "follow this serial")` to `CITED_SPAN_ANY_LENGTH_COOCCURRENCE` (a RePEc serial index page is a
    non-article; the pair never occurs in real prose). ev_748's whole source is then refused at the
    existing `is_cited_span_shell` fetch seam (§-1.3.1a chrome non-source, disclosed).

**Fix 4 — density counts bare URLs (RC3/ev_748 partial, ev_933).** In `_is_nav_link_line` and the
prose-like ratio, count bare `https?://\S+` runs as link chars and toward the ≥2-link floor.
Reference-like keep-guards unchanged, so citation URLs still protect their lines.

**Fix 5 — span-window boundary snap (RC4).** In `_build_provenance_quote`, after slicing each
window: trim a LEADING fragment ending at the first `)` when it contains `://` or a `#…` fragment
and has no opening `[` before it (dangling link tail); symmetrically trim a TRAILING incomplete
`[anchor](partial…` token. Pure string hygiene at quote build; grounding offsets are computed from
the stored quote afterwards, so no verifier contract changes.

## Flags / guards / acceptance
- New env `PG_FETCH_MD_NAV_STRIP_V2` (default ON) gates Fixes 1-4 additions; `PG_SPAN_WINDOW_LINK_SNAP`
  (default ON) gates Fix 5. Either OFF ⇒ byte-identical to round-1. Existing
  `PG_FETCH_MD_NAV_STRIP` / `PG_FETCH_SHELL_VOCAB_GATE` semantics unchanged.
- Sacred guard restated: ref-mode + citation-signal lines are byte-identical (sole exception:
  empty/symbolic-anchor same-page back-links, which carry no citation content). No new drop of any
  credible on-topic SOURCE; all deletions are line/token chrome or §-1.3.1a shell refusals, disclosed.
- Tests: unit fixtures = the 15 quoted leak lines (each must clean to junk-free) + guard fixtures
  (ev_037 endnote text minus back-link survives byte-identical; a prose line with 2 inline citation
  links keeps its anchor text; a DOI reference line untouched). Then rerun
  `scripts/fetch_corpus_replay.py` — acceptance: zero real-junk HIGH leaks on these 15 URLs.
