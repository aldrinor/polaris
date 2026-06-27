# I-wire-014 CHROME benchmark — results

## Gold augmentation
- Source: parsed `replay3_report_full.md` body-prose (sections `### Task-based …` →
  `## Methods`), segmented into 522 single-origin units on `[N]` citation boundaries.
- Labeled by **source meaning, BLIND to the candidate regexes** (regexes written
  separately, afterward). Rule: furniture-DOMINANT → chrome; a real assertional claim
  with an incidental welded chrome fragment → **content** ("when unsure → content").
- Merged with the original 177 basket-rep rows (deduped by `text[:120]`).
- **`chrome_gold_augmented.json` = 686 items: 128 chrome / 558 content.**
  Class counts (chrome): truncation 91, journal_html 23, paywall_preview 4,
  affiliation 4, dehyphenation 4, cookie_consent 2.
  Added body-prose rows: 24 chrome + 485 content controls (the content controls are the
  faithfulness gate — they include the many real claims carrying glued tokens like
  "decision- making", "short- and long-term" that a careless rule would gut).

## Scoring semantics (per-span `candidate(text)->cleaned_text`)
- **removed**   : cleaned has < 4 alphabetic words, OR ≤ 40% of the original's
  alphabetic-word occurrences survive (stripped to empty / near-empty).
- **preserved** : > 60% of the original's alphabetic-word occurrences survive
  (largely intact).
- `chrome_removed_rate` — GRADED (higher better).
- `content_preserved_rate` — **GATE, MUST = 1.0**; < 1.0 = a real-content span was
  gutted = LETHAL = AUTO-DISQUALIFY.
- Oracle self-check (empties exactly the gold-chrome spans) scores 1.0 / 1.0 → harness
  math validated.

## Candidate scores

| candidate | chrome_removed_rate | content_preserved_rate | gate |
|---|---|---|---|
| incumbent (`clean_fetch_body`) | 0.0234 (3/128) | **1.0000** (558/558) | PASS |
| **extended_deterministic** | **0.0938 (12/128)** | **1.0000** (558/558) | **PASS** |
| extended_symspell | 0.0938 (12/128) | 1.0000 (558/558) | PASS |

Per-class removed (extended_deterministic): journal_html 8/23, cookie_consent 2/2,
paywall_preview 1/4, affiliation 1/4, dehyphenation 0/4, truncation 0/91.

**New-classes-only graded score** (the 37 chrome units the markdown post-filters
actually target; the 91 truncation units are a mid-word cut = `is_truncated_fragment`'s
job, no markdown filter can or should remove them):
- incumbent: **3/37 = 0.0811**
- extended_deterministic: **12/37 = 0.3243** (a clean ~4×).

The all-chrome 9.4% headline understates the real effect because the denominator carries
the 91 untargetable truncation units.

## Insertion point — what was actually validated
The gold units come from the RENDERED report (post-composition), where chrome is welded
INTO claims. The winning candidate is **whole-unit-collapse** (return `""` or the span
unchanged) — which is exactly the **render-seam predicate** `is_render_chrome_or_unrenderable`'s
mode (return True = suppress the unit), **NOT** `clean_fetch_body`'s inline `.sub()` strip
on the raw fetch. So:
- The validated `_apply_extended` + near-empty containment test ports into
  `is_render_chrome_or_unrenderable` (via `_is_new_chrome_category` / `_contains_forensic_chrome`).
- Only the SELF-CONTAINED furniture signatures (whole-line) port into `clean_fetch_body`
  (extend `_WEB_BOILERPLATE_LINE_RE`) — never unit-level partial strips, which only
  caused the 0.9964 disqualification above.

## WINNER: `extended_deterministic`
Highest chrome_removed_rate (0.0938, ~4× the incumbent's 0.0234) among the candidates
whose `content_preserved_rate == 1.0`. The faithfulness gate held for all three.

### Why `extended_symspell` does NOT win
It ties `extended_deterministic` exactly (0.0938; dehyphenation 0/4). Dehyphenation is
**repair, not removal** — rejoining "Governan; ce"→"Governance" never empties a span, so
it flips ZERO removed/preserved verdicts on this gold. The symspell helper is proven
CORRECT (it rejoins genuine glued tokens — Governance / suggest / framework — and
PRESERVES real two-word phrases — "high risk", "short- and long-term", "routine-
replacing", "up- and reskilling" — via the wordfreq zipf validator), so it ships as a
separate input-hygiene helper, but it adds only gate-risk for no graded gain on this
benchmark. The winner is the simpler `extended_deterministic`.

### First design REJECTED by the gate
The first `extended_deterministic` did PARTIAL token-stripping of welded chrome
fragments and scored 0.1172 removed — but content_preserved dropped to 0.9964 (gutted 2
content spans where a chrome fragment was welded mid-prose: the "...complete this
challenge. If you are trying to perform text/data mining..." span and the "...2024 The
IZA@LISER Network..." span). DISQUALIFIED. Fix = **whole-unit-collapse-only**: the
extended layer removes furniture tokens only to TEST whether the unit is
furniture-dominant; if the residue is near-empty it returns "" (chrome), otherwise it
returns the span UNCHANGED. Glued-mid-prose chrome is then left to the render-seam
predicate, NOT `clean_fetch_body`. This makes content_preserved == 1.0 by construction.

## Files
- `chrome_gold_augmented.json` — augmented gold (686 items)
- `chrome_candidates.py` — the 3 candidates (signature `candidate(text)->cleaned_text`)
- `chrome_benchmark.py` — scoring harness (oracle self-check + loud gate flag)
- `chrome_benchmark_results.json` — machine-readable scores + violation/miss samples
- `prove_symspell.py` — symspell rejoin proofs + extended-collapse list
