# I-carney-010 brief — Serper stays: revert search-provider-deferred edits

**GH:** #490
**Branch:** `bot/I-carney-010-serper-stays`
**Head commit:** `c7fe9072`

## What

Revert the I-carney-008 (PR #488) edits that deferred the web search
provider and removed `google.serper.dev` from the egress allowlist. Per
user directive 2026-05-13: "search provider is OK to stay serper, as I
don't need to share confidential information in it." Serper stays;
disclosed plainly in `/transparency`.

## Why I-carney-008 over-reached

I-carney-008 applied a too-broad sovereignty threat model — it treated the
search-query egress as a sovereignty violation and deferred Serper to a
follow-up Issue (GH#487, now closed WONTFIX). The corrected threat model:
the sovereignty constraint protects the **LLM inference path and the
generated report data**. A web-search query is a short keyword string
carrying no confidential content; Serper returns only URLs + snippets; the
actual T1 evidence is fetched directly from the government corpus
endpoints. Serper-as-US is a deliberate, disclosed exception — not a
sovereignty failure.

## Changes — config + docs ONLY, zero `src/` change

`src/polaris_graph/retrieval/*` Serper code was NEVER removed by I-carney-008
— only the egress allowlist + docs changed. So this revert is also
config + docs only:

1. **`config/egress_allowlist.txt`** — re-add `google.serper.dev` under a
   "Live retrieval" section; header + section comments rewritten to
   disclose Serper as US, user-accepted, with the threat-model rationale.
2. **`infra/vexxhost/.env.example`** — `SERPER_API_KEY` documented as the
   active REQUIRED search backend (dropped the "fails the no-US bar / leave
   blank for no-search phase" framing; `REPLACE_ME` not `REPLACE_ME_OR_…`).
3. **`docs/transparency.md` §4** — `google.serper.dev` added to the
   allowlist bullet list; the "Web search provider" paragraph rewritten as
   a plain disclosed exception with the full rationale (queries
   non-confidential, reports sovereign, Serper sees only keyword→URL+snippet,
   reviewer CAN swap to a non-US provider but it's not required).
4. **`docs/carney_demo_runbook.md`** — stack table row + §0 prereqs row +
   §1 prereqs sentence: Serper (US, disclosed); `https://serper.dev/` signup.
5. **`infra/vexxhost/README.md`** — Search line, prereq #5, architecture
   diagram, sovereignty audit table row all updated to Serper (US, disclosed).

## Files I have ALSO checked and they're clean

- `src/polaris_graph/retrieval/live_retriever.py` + `real_fetcher.py` +
  `domain_backends.py` — Serper retrieval code intact, untouched by both
  I-carney-008 and this Issue. `SERPER_ENDPOINT = "https://google.serper.dev/search"`
  was never altered.
- `src/polaris_v6/api/transparency.py` — reads `config/egress_allowlist.txt`
  line-by-line (skip `#`/blank); `google.serper.dev` is a valid plain entry.
  No code change, no schema change.
- `tests/polaris_v6/api/test_transparency.py` — uses a tmp-file fixture for
  the allowlist, not the real file. No test change needed.
- `scripts/egress_lockdown.sh` — resolves each allowlist line to A/AAAA;
  `google.serper.dev` resolves fine. No change.
- Grep confirmed: zero remaining `GH#487` / `DEFERRED` / `Mojeek|Qwant|Ecosia`
  stale references across the 5 files — except one INTENTIONAL mention in
  transparency.md §4 ("a reviewer who wants zero US touch CAN swap to
  Mojeek/Qwant/Ecosia") which is disclosure context, not a stale deferral.

## Out of scope

- Bounded-retry / quota handling for Serper — that is prep task G9, separate.
- Any `src/` change — none needed.

## Direct questions for Codex

1. Is the `/transparency` §4 disclosure language honest and complete? It
   states the exception plainly, gives the threat-model rationale, and notes
   the reviewer CAN swap providers. Anything misleading or missing?
2. The egress allowlist header now says "Serper stays ... disclosed in
   /transparency" — does that + the §4 paragraph constitute adequate
   disclosure for a clinical-grade audit, or should there be a machine-
   readable `provider_jurisdiction` field on the `/transparency` JSON for
   the search provider? (Note: adding a JSON field would be a `src/` change
   — flag it as P2/follow-up if you think it's warranted, don't block.)
3. Anything else blocking APPROVE?

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
