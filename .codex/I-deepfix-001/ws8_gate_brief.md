HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings. Reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero P1.

# Codex diff gate — I-deepfix-001 WS-8 (D4): journal-only genre re-rank recency leg

Review `.codex/I-deepfix-001/ws8_diff.patch` (scripts/run_honest_sweep_r3.py). Read the touched region for context. Repo root C:/POLARIS, read-only.

## The defect (D4, drb_72)
A 1986 pre-AI robotics paper (J. Operations Mgmt) HEADLINED an AI-labor review. The journal-only genre re-rank (`_m2_bib_genre`, gated by the `_m2_journal_pref_active` double gate = PG_DOCUMENT_TYPE_WEIGHT=1 AND the template's `document_type_preference: journal_article`) weighted only by `tier_prior * document_type_weight` — no recency, so a high-tier ancient paper out-ranked recent journals for headline ordering.

## The fix (verify it does exactly this, nothing more)
- New `_m2_publication_year(b)` (explicit year field, else first plausible 4-digit year parsed from statement/title/url/doi; None if none — never guessed), `_m2_reference_year(bibliography)` (the CORPUS-NEWEST year — deterministic, no wall-clock), `_m2_recency_factor(b, reference_year)` (in [floor, 1.0], 1.0 within `grace` years of newest, linear `decay` per year older, FLOORED so an old source is DEMOTED not zeroed).
- `_m2_bib_genre` now returns `tier_prior * document_type_weight * recency_factor` with a new optional `reference_year` param (default None => factor 1.0 => byte-identical). The corroboration re-rank call site computes `_m2_reference_year(bibliography)` ONCE and passes it.
- Env-tunable (LAW VI): PG_M2_RECENCY_RERANK (default ON), PG_M2_RECENCY_DECAY_PER_YEAR (0.02), PG_M2_RECENCY_GRACE_YEARS (5), PG_M2_RECENCY_FLOOR (0.25).

## Confirm
1. §-1.3 WEIGHT-and-DISCLOSE: this is a DISPLAY re-rank multiplier only — NO source is dropped/capped/filtered; the floor guarantees an old source stays rankable (never 0). Confirm.
2. Faithfulness-neutral: it changes ordering/label weight only — no strict_verify / NLI / 4-role / span verdict touched; frozen engine untouched (git diff --name-only over the 11 engine files empty). Confirm.
3. Safe-direction: the recency leg is INERT when `journal_preference_active` is False (the genre re-rank is only applied there) AND byte-identical when PG_M2_RECENCY_RERANK OFF or the year is unknown/absent (never guesses a year, never penalizes on missing). Confirm no path penalizes a source whose year cannot be parsed.
4. Determinism: reference_year is corpus-relative (max over the bibliography), not wall-clock — so the same corpus yields the same ordering. Confirm.
5. Any way this could DEMOTE a legitimately-important recent source, or fail to demote the 1986 case? Any magic number not env-backed?
6. SCOPE HONESTY: the diff does the bibliography/corroboration re-rank recency leg only. The commit notes (a) journal-class activation (PG_DOCUMENT_TYPE_WEIGHT=1) is a run-config item + (b) the composition-ranking recency in weighted_enrichment is a follow-on. Is deferring those acceptable, or is the bib re-rank alone insufficient to stop a headline breach (i.e. does the headline come from composition, not bib order)?

## Output schema (REQUIRED)
```yaml
verdict: APPROVE | REQUEST_CHANGES
s13_display_rerank_no_drop: true | false
faithfulness_neutral: true | false
byte_identical_when_off_or_unknown_year: true | false
bib_rerank_sufficient_or_needs_composition: string
novel_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
```
