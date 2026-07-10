# DEFECT (tracked) — S2 chrome non-sources leak past line_screen into the grounding pool

**Filed:** 2026-07-10 (I-arch s4-outline fix wave, Fable item 6b)
**Section owner:** S2 (SELECT + WEIGH / line_screen + content-integrity stamp)
**Severity:** P1 — pollutes the grounding pool, bibliography, and corroboration counts of a clinical report.
**Faithfulness impact:** none directly (a claim citing a chrome row still FAILS strict_verify), but the
chrome rows inflate basket corroboration and waste the planner's attention. §-1.3.1(a) authorizes DELETE
with disclosure, but the delete only fires on an upstream stamp that is NOT being set for these rows.

## What was observed (drb_72 cp2/cp3, this run)
- **32 rows carry the TITLE "Just a moment..."** (the Cloudflare bot-interstitial page). These are
  FAILED fetches surfaced as a page, not sources.
- They **passed S2 `line_screen` with `n_dropped=0`** — the content-integrity detector did NOT stamp
  `content_integrity_junk` / `content_integrity_class="chrome"` on them.
- Several are **stamped T3 / T4** (a credible tier on a bot page), so they even carry weight.
- Downstream they **consolidate into whole baskets** (observed: B02 / B04 / B21 / B26 / B29 / B52 /
  B59 / B62 / B64 / B65 ...), because many share the identical "Just a moment..." title, so the
  corroboration counter reads them as a multi-source claim.

## Root cause (to confirm at S2)
The S2 line-screen / content-integrity detector is not classifying the known fetch-interstitial pages
("Just a moment...", "Access Denied", "Attention Required", bare "404") as chrome non-sources, so
`row["content_integrity_junk"]` is never set and `junk_deletion_gate` (which deletes only on that
affirmative stamp, fail-open) never fires. The detector likely inspects body text but not the
title/interstitial signature, or these rows bypass the detector entirely.

## Fix location (S2 section — NOT s4-outline)
Add exact/known-string fetch-interstitial detection to the S2 content-integrity stamp so these rows are
stamped `content_integrity_junk=True` + `content_integrity_class="chrome"` at the re-tier seam. Then the
existing `junk_deletion_gate` DELETES them with disclosure (deleted-row count + reason in Methods,
`PG_DELETE_CHROME_NONSOURCE` default-ON). Exact-string interstitial detection is content-integrity under
§-1.3.1(a), never a lexical quality guess — fail-open (unknown => KEEP).

## Interim mitigation already shipped (s4-outline, this wave — item 6c)
`outline_digest._is_chrome_interstitial` tags any digest line whose title is a known interstitial with
`[CHROME — failed fetch, do not anchor]` so the outline planner does not anchor on it. This is a DISPLAY
mitigation at s4 only (the row is KEPT for disclosure); it does NOT delete the row from the pool /
bibliography. The durable fix is the S2 stamp above.

## Acceptance for the S2 fix
- The 32 "Just a moment..." rows are stamped chrome at S2 and DELETED by `junk_deletion_gate` with a
  disclosed deleted-row count in Methods.
- No credible ON-TOPIC source is deleted (fail-open holds; only exact interstitial strings trigger).
- A follow-up GitHub issue should be opened per CLAUDE.md §-1.2 (`I-arch-...` — "S2 chrome-interstitial
  leak") linking this note.
