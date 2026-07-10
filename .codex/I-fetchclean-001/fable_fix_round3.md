# I-fetchclean-001 — Fable round-3 fix design (fetch-junk leaks, live retest round 2)

Author: Fable 5 (brain). Builder: Opus (hands). Gate: Codex + Fable dual gate.
Scope: `src/tools/access_bypass.py` (strip_markdown_nav_chrome + clean_fetch_body inline
patterns) and `src/polaris_graph/retrieval/shell_detector.py` (short-body chrome vocab).
`live_retriever.py` needs NO change — the A3 winner probe + span path already call
`clean_fetch_body`, so every fix below flows through both seams automatically.

BINDING (unchanged): never strip legit article prose. Never strip a reference /
citation line — a line with a DOI / year / et-al / pp. in its VISIBLE text must
survive byte-for-byte. Faithfulness engine untouched. All changes ride the existing
default-ON flags (`PG_FETCH_MD_NAV_STRIP`, `PG_FETCH_COOKIE_CHROME_STRIP`); flag OFF
("0") stays byte-identical to today.

---

## 1. Root causes — six mechanisms explain all 15 leaks

### RC-1 — Heading lines bypass EVERY chrome check
`strip_markdown_nav_chrome` (access_bypass.py:2824-2837): any line matching
`_MD_HEADING_RE` is appended byte-identical and `continue`s BEFORE the standalone-chrome,
cookie, and nav-density checks. Jina welds nav/cookie blocks onto heading lines
(`### Cookies on this website We use cookies…`, `## Just In [link](url)[link](url)…`,
`### O*NET [link](https:…`). The whole welded junk line is kept unconditionally.
Leaks: ev_865, ev_244 (hit 1), ev_195, ev_441 (hit 1), ev_296, ev_461.

### RC-2 — Cookie vocab is whole-line-anchored and English-only
`_WEB_BOILERPLATE_LINE_RE` cookie patterns (2321-2325) all start `^\s*` ("We use
cookies…", "This (website|site) uses cookies…"). When the consent text sits mid-line
(Jina inline collapse: ev_726 EC banner) or behind a welded heading (ev_865), the `^`
anchor never matches. There is NO inline cookie-sentence removal in
`_INLINE_SOCIAL_CHROME_RE` (2592-2664 — social/login/masthead only). And there is zero
non-English coverage: the Italian AMS-Bologna banner ("Nel nostro sito utilizziamo sia
cookie tecnici… con il tuo consenso", ev_661) matches nothing. Cookie Information CMP
("We and our business partners use technologies, including cookies…", "Functional -
[x] Statistical - [x] Marketing Powered by: [Cookie Information…]", ev_244) and the
AMA variant ("cookies, pixels and other technology…", ev_441 hit 2) are also absent —
`_COOKIEBOT_MARKER_RE` (2766) gates on `cookiebot.com` only, so cookieinformation.com
chrome is never touched. Shell vocab side: `SHELL_COOCCURRENCE` (shell_detector.py:143)
has ("we use cookies","accept all") but ev_865 says "allow all cookies" and ev_726 says
"[Accept all cookies]" mid-markdown — near-miss vocabulary.
Leaks: ev_865, ev_661, ev_726 (hit 1), ev_244, ev_441 (hit 2).

### RC-3 — Citation-signal keep-guard scans URLs, so nav lines with a year in the href are kept
`_line_is_reference_like` (2774-2776) runs `\b(19|20)\d{2}\b` (and the other signals)
over the FULL line INCLUDING markdown link URLs. Any nav link whose href contains
`/2026/`, `?year=`, a dated news path, etc. flips the whole nav line to "reference-like
→ KEEP" (2802). News/portal navs (thehill "2 hours ago" rails, OECD/EC promo links,
calbar "Proposed Amendments to …") routinely carry dates in hrefs or visible nav text.
Leaks: ev_726 (hit 2), ev_195, ev_275 (hit 2).

### RC-4 — Per-physical-line density: welded nav+prose dilutes below 0.5; 2-link floor misses single-link bullet navs
`_is_nav_link_line` (2790-2806) needs `len(links) >= 2` AND link-chars/line >= 0.5 on
ONE physical line. Jina inline collapse welds a nav run onto real prose → density
dilutes below 0.5 → whole line kept, nav included (ev_726 hit 2, ev_944 context,
ev_441 hit 1). Bullet menus emit ONE link per line (`* [Public](url)`,
`* [Open submenu](…#mm-24)`) → under the 2-link floor → kept (ev_275 hit 1).
Leaks: ev_275, ev_726 (hit 2), ev_441 (hit 1), plus contributes to ev_195/296/461.

### RC-5 — Missing inline micro-chrome tokens
No pattern anywhere covers: the EMPTY markdown anchor `[](url)` welded as a prose
prefix (ev_944 federalreserve — line is prose-like so it is kept whole, empty anchor
included); the `Crossref 0` citation-count widget welded before real BLS prose
(ev_497 — existing crossref vocab is only the short-body ("download citation",
"crossref") tuple and the "Crossref reports the following…" line); breadcrumb `>`
link-runs (ev_461).

### RC-6 — Three uncovered junk classes
(a) EMPTY markdown table skeleton — header row + `| --- | --- |` separator with ZERO
data rows (ev_1242 pwc). Nothing detects tables. (b) Journal running-header / CONTACT
masthead furniture welded inline — "CONTACT Magnus Soderlund magnus.Soderlund@hhs.se >
THE INTERNATIONAL REVIEW OF … 2022, VOL. 32, NO" (ev_524; ev_583 same class from
yalelawjournal front-matter). Note honestly: the retest `error_page` marker
(`\b404\b`) can also fire on a page-range "404–424" inside this furniture — the
production fix is the masthead strip; the harness should ALSO get the same
citation-signal exemption for `\b404\b` that nav_link_density already has, so round-4
judges cleanly. (c) A bot-wall phrase welded INSIDE a long kept real body (ev_672
americanprogress transcript) — `ACCESS_DENIAL_MARKERS` fire only as whole-body/span
verdicts, short-body gated (3000), so a long real page correctly passes as a SOURCE,
but the interstitial LINE inside it is never stripped.

---

## 2. The incremental fix (surgical; extends existing seams only)

All edits inside `strip_markdown_nav_chrome` / `clean_fetch_body` inline regexes unless
marked shell_detector. Order preserved: whole-line allowlist → inline tokens → nav line
filter.

**F1 — Heading lines go through the chrome checks (fixes RC-1).**
In `strip_markdown_nav_chrome`, keep the reference-heading tracking exactly as is, but
for a NON-reference heading do NOT `continue` blindly: strip the leading `#{1,6}\s*`
into `rest` and (a) if `rest` fails the nav-density test (`_is_nav_link_line` on
`rest`) → drop the whole line (a "## Just In [..](..)[..](..)" rail is chrome, not a
heading); (b) run the F4 inline cookie-sentence stripper on the line (so
"### Cookies on this website We use cookies…" loses the consent block); (c) otherwise
keep byte-identical. A real heading ("## Results", "### 2.3 Methods") has no 2-link
0.5-density tail and no cookie anchor — byte-preserved.

**F2 — Citation-signal guard measured on VISIBLE text (fixes RC-3, and STRENGTHENS the
sacred guard rather than weakening it).**
Add `_visible_text(line)`: replace every `[text](url)` with `text` (keep link text,
drop hrefs). `_line_is_reference_like` evaluates its signals on the visible text. A
real reference line carries its DOI / year / et-al in visible text (incl. link TEXT
like "[WHO 2020 report](…)") → still KEPT. A nav link whose ONLY year lives in the
href no longer masquerades as a reference. No signal regex changes.

**F3 — Inline nav-RUN stripper + single-link bullet-nav rule (fixes RC-4).**
(a) Nav-RUN: inside any kept line, find a maximal run of >=3 markdown links where each
inter-link gap is <=30 chars and contains no sentence-ending punctuation; if the run's
VISIBLE text has no citation signal, remove the RUN token-only — flanking prose stays
byte-for-byte. (b) Bullet-nav line: a whole line that is only `[*>-]` bullets/breadcrumb
+ 1-2 links + <=4 visible words, with NO citation signal, NO sentence-ending
punctuation, and not in ref_mode → drop ("* [Public](url)", "* [Open submenu](…)").
Reference bullets ("* [Smith et al., 2019](doi…)") carry a signal or a long title →
kept.

**F4 — Inline cookie-consent sentence stripper + CMP vocab (fixes RC-2).**
New `_INLINE_COOKIE_SENTENCE_RE` applied under `PG_FETCH_COOKIE_CHROME_STRIP`
(default-ON): from a consent ANCHOR phrase to the end of its sentence/segment
(bounded, max ~300 chars, token-only — surrounding prose preserved). Anchors (all
multi-token, structure-anchored): "We use cookies to ensure", "This site uses
cookies", "This website uses cookies", "The cookie settings on this website", "If you
continue without changing your settings", "cookies, pixels and other technolog",
"We and our business partners use technologies", "consent to the use of cookies",
markdown CTA `[Accept all cookies](url)` / `[cookies policy page](url)`,
`Powered by:? [Cookie Information…](…)`, category checkbox run
`(?:Necessary|Functional|Preferences|Statistical|Statistics|Marketing)\s*-\s*\[[x ]\]`
(>=2 repeats). Non-English CMP anchors (multi-token co-occurrence, never single
words): IT "utilizziamo … cookie" + ("consenso"|"tracciamento"); ES "utilizamos
cookies"; FR "nous utilisons des cookies"; DE "wir verwenden Cookies". Extend
`_COOKIEBOT_MARKER_RE` → `cookiebot\.com|cookieinformation\.com`.

**F5 — Micro-chrome inline tokens (fixes RC-5).**
Add to the nav-strip pass (PG_FETCH_MD_NAV_STRIP): (a) empty anchor `\[\]\([^)]*\)` —
zero visible text is always pure chrome, unconditionally safe; (b) Crossref count
widget `(?:^|(?<=\s))Crossref\s+\d{1,3}(?=\s|$)` with a negative guard for 4-digit
years (so "Crossref 2019" in a reference line survives); (c) breadcrumb glue: a `>`
-separated run of links with <=2 visible words per crumb, stripped token-only.

**F6 — Empty markdown table skeleton (fixes RC-6a).**
In the line loop: on seeing a table separator row (`^\s*\|?(\s*:?-{2,}:?\s*\|)+`),
look back to the header row and ahead for a data row (`|`-bearing line with a
non-separator cell); if NO data row follows, drop the header+separator pair. A table
WITH any data row is byte-preserved.

**F7 — Masthead running-header / CONTACT furniture (fixes RC-6b).**
Inline token-only removals: `CONTACT\s+\S+(?:\s+\S+){0,3}\s+\S+@\S+\.\S+` (CONTACT +
name + email, all three required) and journal running-header
`(?:>\s*)?THE\s+[A-Z][A-Z ,&]{10,}\s+(?:19|20)\d{2},\s*VOL\.?\s*\d+,\s*NO\b[.\d\s,–-]{0,20}`
(all-caps journal title + year + VOL/NO structure — a prose sentence can never match).
The visible-text reference guard does NOT protect these because they are stripped as
inline TOKENS, not whole lines — a real reference to the same journal (title-case,
comma-authored) never matches the all-caps+VOL/NO structure.

**F8 — Line-level bot-wall interstitial strip (fixes RC-6c, precision-first).**
In the line filter: drop a LINE (never a whole body) iff it matches an
`ACCESS_DENIAL_MARKERS` phrase AND is <=300 chars AND has no citation signal in visible
text AND is not prose-like. A long welded transcript line (ev_672) is NOT dropped —
for that case the honest residual is harness-side: give `bot_wall`/`error_page` hits
the same citation-signal/prose exemption nav_link_density already has in
`fetch_corpus_replay.py:_real_high_hits`, because "not a bot" / `\b404\b` inside long
real prose (an AI-jobs corpus!) is a detector FP class, not a production leak.

**F9 — shell_detector vocab increments (span-gate backstop; short-body ceilings
unchanged).** Append to `SHELL_COOCCURRENCE`: ("cookies on this website", "allow all
cookies"), ("cookie settings on this website", "continue without changing"),
("we and our business partners use technologies", "cookies"), ("utilizziamo",
"cookie", "consenso"). No `ACCESS_DENIAL_MARKERS` / `CHALLENGE_PAGE_COOCCURRENCE` /
ceiling changes — those are correct today.

## 3. What is deliberately NOT done
No whole-source deletion changes (§-1.3.1 path untouched). No new hard gates. No
faithfulness-engine edits. No harness/production vocabulary sharing (independence
preserved). No ratio knobs, no breadth targets.

## 4. Test plan (RED first)
Fixtures: the 15 leak spans above → each junk fragment gone after `clean_fetch_body`.
Adversarial KEEP set (must be byte-identical): a reference line "Smith et al. (2019).
Title. J Retail. 32(4), 404–424. doi:10.1080/…"; bullet reference
"* [Marmot Review 2010](https://…)"; prose "users must verify they are not a bot"
inside a 5k-char article; a data-bearing markdown table; "Crossref 2019 metadata"
prose; Italian clinical prose mentioning "cookie" without consent anchors; headings
"## Results" / "### 2.3 Methods"; the ev_037 bipartisanpolicy reference-mode case.
Flag-OFF (`PG_FETCH_MD_NAV_STRIP=0`, `PG_FETCH_COOKIE_CHROME_STRIP=0`): byte-identical
on every fixture. Then rerun `scripts/fetch_corpus_replay.py` round 3 on box 2.
