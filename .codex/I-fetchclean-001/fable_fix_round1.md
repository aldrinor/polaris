# I-fetchclean-001 — Fable round-1 fix design (remaining 15 leaks, live retest round 0)

Author: Fable 5 (brain). Builder: Opus. Scope: `src/tools/access_bypass.py` (strip_markdown_nav_chrome) + `src/polaris_graph/retrieval/shell_detector.py` (vocab only). `live_retriever.py` needs NO change — both seams (refetch_for_extraction ~L3316-3373 and the `_fetch_content` winner probe ~L4231-4335) already run `clean_fetch_body` + `is_cited_span_shell`, so every fix below flows through automatically.

## Root causes (per leak, against the CURRENT code)

Two cross-cutting mechanisms explain 12 of 15:

**RC-A — heading fast-path + welded mega-lines.** Jina/crawl4ai weld a whole page region onto ONE line. `strip_markdown_nav_chrome` (access_bypass.py:2832-2837) keeps ANY line matching `_MD_HEADING_RE` unconditionally — a 2,000-char welded line that merely STARTS with `## ` bypasses every chrome rule. And the per-line nav drop's keep-guards (`_line_is_reference_like` year/vol(issue) anywhere in the line; `_line_is_prose_like` sentence-end) are evaluated over the WHOLE mega-line, so one year or one trailing period deep in a welded line keeps the entire nav head.

**RC-B — whole-line / vendor anchoring.** `_STANDALONE_CHROME_LINE_RE` is `^...$` (gov banner, reading-time, skip-nav fire only when the chrome is the ENTIRE line); `_COOKIEBOT_CHROME_RE` fires only on a line containing literal `cookiebot.com`; `_SKIP_NAV_LINK_RE` matches only the `[Skip to ...](url)` bracket form.

Per leak:

| ev | marker | root cause |
|---|---|---|
| ev_954 cacm.acm.org | cookie | IAB TCF banner (`[[#IABV2SETTINGS#]](self#)` + "We Use Cookies This website uses cookies…") — `_COOKIEBOT_MARKER_RE` needs `cookiebot.com`, absent here; banner line is 1-link + ends with punctuation ⇒ prose-like KEEP; no consent-vocab line rule exists. |
| ev_497 bls.gov mlr | gov_banner + crossref | Banner welded inline with real prose on one line ⇒ `^...$` standalone rule misses (RC-B). "Crossref 0" citation-count widget has no rule at all. |
| ev_688 uq.edu.au | bot_wall | Vocab gap: "solve a puzzle" / "Let's confirm you are human" / "Temporary error. Please try again" are in NO marker list ("confirm you are **a** human" ≠ "confirm you are human"); short-body markers also capped at 3000 chars and this PDF-wall body is longer. |
| ev_524 tandfonline | error_page | T&F PDF **citation cover sheet** (journal name + `(Print) 1466-4402 (Online)` + `Journal homepage: …`). `is_issue_front_matter` needs literal `issn` (regex `issn\s*:?…`) + contents vocab — cover sheet has neither; no dot-leaders. Welded `#`-heading line ⇒ RC-A keep. (Replay's `error_page` token itself is likely `\b404\b` noise; the junk class is the cover sheet.) |
| ev_583 yalelawjournal | error_page | Visible head is the GENUINE article abstract. `\b404\b` in the replay marker matches law-journal page/cite numbers ⇒ probable REPLAY false positive, not a production leak. Fix the replay regex, do NOT add a production strip. Verify full span before round 2. |
| ev_672 americanprogress | bot_wall | Visible head is a genuine event transcript. Probable match: "Enable JavaScript" video-embed chrome deeper in the span — covered by the video-chrome token below; verify full span. Do NOT strip transcript prose. |
| ev_272 bls.gov lawyers | bot_wall | Real page; junk is inline video-player chrome "Please enable javascript to play this video." + `[Video transcript available at …](…)` welded after `## Summary` ⇒ RC-A heading bypass + no video-chrome rule. |
| ev_661 doi.org/UNIBO | cookie | Italian consent banner ("Nel nostro sito utilizziamo sia cookie tecnici… il tuo consenso") — all consent vocab is English-only + cookiebot-anchored; banner is prose-like ⇒ KEEP. |
| ev_726 ec.europa.eu | cookie | "This **site** uses cookies. Visit our [cookies policy page](…)": vocab says "this **website** uses cookies"; 1 link ⇒ not a nav line; sentence-end ⇒ prose-like KEEP; SHELL_COOCCURRENCE chrome class correctly can't fire (body ≫ 800 chars, real article behind it). |
| ev_244 appunite | cookie | `## You control your data We and our business partners use technologies, including cookies…` — RC-A: heading fast-path keeps the whole welded banner line; "you control your data" / "we and our partners" vocab absent everywhere. |
| ev_957 cbreim | reading_time | "… 10 Minute Read Time …" welded inline with date+title+prose ⇒ `^...$` standalone rule misses (RC-B). |
| ev_258 growthlab.hks | skip_nav | Skip-nav emitted as paren-URL-with-TITLE form `(https://… "skip to main content")` — `_SKIP_NAV_LINK_RE` only matches the `[Skip to …](url)` bracket form. |
| ev_255 news.ycombinator | nav_link_density | Welded HN header (`[ ](url)**[Hacker News](…)**[new](…) \| [past](…) …`) on a line whose tail carries a year / sentence-end ⇒ whole-line keep-guards fire (RC-A guard-granularity). |
| ev_195 thehill | nav_link_density | Leading bare anchor `(url#content)` + `## Just In` + one-link-per-item news list welded; heading bypass + guards-over-whole-line + bare `(url)` anchors aren't `_MD_LINK_RE` links. |
| ev_748 ideas.repec | nav_link_density | Welded browse nav (`[Advanced search](…) ### Browse Econ Literature * [Working papers](…) …`); series listing tail carries years/vol(issue) ⇒ reference-like guard keeps the whole line (RC-A). |

## Incremental fix (all inside the existing default-ON flags; OFF ⇒ byte-identical)

All access_bypass changes live INSIDE `strip_markdown_nav_chrome` / its helpers, so the existing `PG_FETCH_MD_NAV_STRIP` (default-ON, "0" ⇒ never applied ⇒ byte-identical) gates everything. Shell-vocab additions ride the existing `PG_CITED_SPAN_SHELL_DETECT` / `PG_FETCH_SHELL_VOCAB_GATE`. No new flags, no caps, no targets.

### F1 — heading fast-path length cap (RC-A) — access_bypass.py
A line matching `_MD_HEADING_RE` is kept unconditionally ONLY when `len(line) <= PG_MD_HEADING_MAX_CHARS` (env, default 160 — real headings are short). Longer `#`-prefixed welded lines fall through to the token/segment rules below (heading marks preserved in whatever survives). `_MD_REFERENCE_HEADING_RE` handling unchanged (checked first, as now).

### F2 — new INLINE token-only removals (RC-B) — access_bypass.py
Applied at step-6 alongside `_SKIP_NAV_LINK_RE` (surrounding prose byte-preserved; a line that becomes whitespace-only was pure chrome and drops, as now):
1. `An official website of the United States government(\s+Here'?s how you know)?` — anywhere in line (ev_497).
2. `\b\d+\s*Minute Read Time\b` — widget phrasing, never prose (ev_957).
3. Skip-nav paren-title form: `\(\s*https?://[^)\s]+\s+"skip to (?:main )?content"\s*\)` (ev_258); plus LINE-LEADING bare anchor `^\(\s*https?://[^)\s]+#content\s*\)` (ev_195).
4. Video-player chrome: `Please enable javascript to play this video\.?` + `\[Video transcript available at [^\]]*\]\([^)]*\)` (ev_272, likely ev_672).
5. IAB consent anchor: `\[\[#IABV2SETTINGS#\]\]\([^)]*\)` (ev_954).
6. T&F cover-sheet tokens: `\(Print\)\s*\d{4}-\d{3}[\dxX]\s*\(Online\)` and `Journal homepage:\s*\S+` (ev_524) — these exact shapes never occur in article prose or reference lines (a real citation writes "ISSN 1466-4402", never the print/online pair token).
7. `\bCrossref\s+\d+\b` citation-count widget (ev_497) — GUARDED: skipped when the line is reference-like (`_line_is_reference_like`) or ref_mode, so a bibliography line naming Crossref near a year/DOI is untouched. (Same guard ordering as the cookiebot rule: check, then sub.)

### F3 — consent-banner LINE rule, multilingual, 2-signal (ev_954/661/726/244) — access_bypass.py
Drop a line iff: (a) a consent ANCHOR matches at line start (after optional `[#*\-\s]+` bullets/heading marks): `we use cookies | this (web)?site uses cookies | you control your data | we and our (business )?partners use (technologies|cookies) | nel nostro sito utilizziamo | questo sito utilizza( i)? cookie`; AND (b) ≥1 additional consent SIGNAL elsewhere in the line: `cookie(s)? policy | accept all | personaliz(e|ation of) content (and ads)? | analyz(e|ing) our traffic | il tuo consenso | cookie tecnici | withdraw (your )?consent | consent`. Precedence: ref_mode / `_line_is_reference_like` still WIN (a cited privacy-paper title with a year survives); this rule runs BEFORE the prose-like keep (banner text ends with a period — that is exactly why it leaked) and applies to long `#`-prefixed lines via F1. Two anchored signals on one line is not natural article prose; a genuine cookie-research SENTENCE quoting a banner verbatim with both signals is the accepted, disclosed residual risk (same posture as the existing cookiebot rule).

### F4 — nav-RUN token removal inside long lines (RC-A guard granularity; ev_255/195/748) — access_bypass.py
New inline pass (before the per-line density drop, after F2): find each MAXIMAL run of ≥3 markdown links — `_MD_LINK_RE` matches, including empty-anchor `[ ](url)`/`[](url)` — separated ONLY by whitespace and separator tokens (`|`, `*`, `**`, `•`, `>`, `·`). Remove the run iff ALL of: run link-density ≥ 0.8 over the run's own chars; NO citation signal INSIDE the run text (`_CITATION_SIGNAL_RES` on the run, not the whole line); not ref_mode; less than half of the runs' link TEXTS are pure digits (footnote-marker runs `[1](#fn1)[2](#fn2)` are citation apparatus — kept). Then collapse stray leftover separator runs (`\s*[|*•]\s*` repeats → single space). Key point: guards are evaluated per-RUN, so a year in the welded line's prose tail no longer shields the nav head (the exact ev_748/ev_255 mechanism). The existing per-line `_is_nav_link_line` drop is left byte-identical for the multi-line case it already handles.

### F5 — shell vocab (ev_688) — shell_detector.py
- `CHALLENGE_PAGE_COOCCURRENCE` += `("solve a puzzle", "confirm you are")`, `("before proceeding to your request", "solve a puzzle")` — ALL-of, any-length; never co-occur in article prose (fires even on the >3000-char UQ wall).
- `SHORT_BODY_SHELL_MARKERS` += `"let's confirm you are human"`, `"temporary error. please try again"` (short-body-gated, as the class requires).
- NO change to chrome ceilings / SHELL_COOCCURRENCE — the cookie leaks are inline-banner-inside-a-real-article; whole-source shell verdicts would violate §-1.3 (the sources are credible and on-topic; only the banner LINE goes, via F3).

### F6 — replay-harness note (not production): ev_583
`scripts/fetch_corpus_replay.py` `error_page` marker `\b404\b` matches legitimate law-review page/cite numbers. Tighten to `\b404\b(?=[^\d]{0,20}(error|not found|page))` or require adjacency to error vocab, so round-1 verdicts aren't polluted. ev_583 and ev_672 need a full-span read before any further production rule.

## Binding invariants honored
- **Citation-signal guard sacred**: F2.7/F3/F4 all check `_line_is_reference_like` / ref_mode / per-run citation signals BEFORE removing anything; reference/DOI/year/et-al lines survive every new rule. F2.1-2.6 tokens are shapes that cannot occur in a reference line.
- **Never strip legit prose**: every new rule is token-anchored or ≥2-signal co-occurrence; welded real prose around removed tokens is byte-preserved; a page nav-stripped to empty routes to the EXISTING `empty_after_clean` refusal (failed fetch, §-1.3.1a), never a source deletion.
- **Faithfulness engine untouched**; input hygiene only. Flags: existing `PG_FETCH_MD_NAV_STRIP` / `PG_FETCH_SHELL_VOCAB_GATE` / `PG_CITED_SPAN_SHELL_DETECT`, all default-ON, OFF ⇒ byte-identical.

## Test plan (RED first)
Fixture per leak (the 15 spans verbatim) → `strip_markdown_nav_chrome`/`is_cited_span_shell` assertions: junk token gone / wall refused. Negative fixtures: reference line with DOI+year+Crossref; footnote-marker run; privacy-paper sentence mentioning cookies once; short real heading; BLS prose after banner byte-identical. Then rerun `scripts/fetch_corpus_replay.py` (box2 retest) — expect 13/15 cleared, ev_583+ev_672 reclassified after F6.
