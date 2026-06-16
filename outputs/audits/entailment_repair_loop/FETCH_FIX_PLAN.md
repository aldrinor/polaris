Excellent guidance. The advisor confirms the structure and surfaces five content-correctness must-haves that keep the ranking honest against my own forensic evidence. I'll fold all five in: Fix #0 instrumentation prerequisite, reframe Zyte from my forensic (not the task's loose "rescue every fetch"), flag OA may outrank Zyte for this biomedical workload, add curl_cffi Tier 2.5, and not fabricate the 831 cause-split. Writing the final plan now.

```markdown
# POLARIS Fetch-Reliability Fix Plan â€” Consolidated, Ranked, Actionable

**Status:** Lead-architect consolidation of (1) 2025/26 web best-practice research, (2) primary-source code+data forensic (file:line), (3) Codex independent review.
**Anchor run:** `outputs/audits/beatboth8/drb_76` (Q76 gut-microbiota/CRC). Fetch yield **29 / 740 candidates = 3.9%**; 711 failed.
**Architecture invariant (CLAUDE.md Â§-1.3):** fetch is WEIGHT-AND-CONSOLIDATE upstream of the faithfulness gates. Raising fetch yield = more real sources in each claim-basket = richer corroboration. **No faithfulness gate is touched by anything below.**

---

## Honesty preamble â€” read before the ranking

My own DATA FORENSIC of drb_76 found that **the per-cause failure breakdown does not exist in the manifest**: `retrieval.drop_reasons = {}` (empty); the only decomposition is coarse worker-tally `parallel_fetch_errored=709`, `timeout=1`, `success=30`. We **cannot currently tell** whether the 709 generic errors are SSL / 403-anti-bot / paywall / 404 / DNS.

Therefore the yield numbers in the ranking below are **expected-given-the-visible-architecture + web-research base rates, NOT measured**. They are confirmed only by **Fix #0 (instrumentation) + a fresh Q76 run** (PART C). The ranking is ordered by *expected* yield per the task; where my forensic suggests a different order for *this biomedical workload*, I flag it explicitly (see Fix #4 note).

---

# PART A â€” RANKED FIXES (by expected fetch-yield impact)

## Fix #0 â€” Instrument per-failure cause (`drop_reasons`) â€” PREREQUISITE, not a yield item
- **Type:** CODE. **Cost:** near-zero. **Direct yield:** 0% (it measures, doesn't fetch). **Why first:** every fix below is currently *untargeted guessing* â€” you cannot target a 96% fetch-loss without knowing its composition.
- **File:line / current behaviour:** `live_retriever.py:4188-4194` increments `failed_fetch` and calls `_trace_drop(url, "fetch_failed")` with a single flat reason. `retrieval.drop_reasons` ships **empty**; `parallel_fetch.py:514-524` collapses every exception to `ERRORED` with no class/status retained. No `tool_trace.jsonl` written (`tool_utilization.total_tool_calls=0`).
- **Change:** at the worker (`parallel_fetch.py:_run_task` ~514) and the post-fetch loop (`live_retriever.py:4188`), record `{exception_class, http_status, host}` per failed URL into `retrieval.drop_reasons` (counts) and emit the already-referenced `tool_trace.jsonl`. Split the 709 `errored` into SSL / 403-antibot / paywall(401/403+paywall-detect) / 404 / DNS / connreset / read-timeout buckets.
- **Expected gain:** unlocks correct prioritization of Fixes #1â€“#5 on the *next* run. This is the single highest-leverage action because it converts "711 failed" into an actionable target.

## Fix #1 â€” Zyte rescue: trigger EARLY on classified failure + budget-partition + connect the shell detector (LEAD FIX)
- **Type:** CODE (env-only partial exists). **Expected yield:** **high** for the anti-bot + slow-host + non-OA-publisher classes â€” the largest single lever *if* those classes dominate (Fix #0 confirms).
- **Reframe (important â€” the task's "wire Zyte to rescue EVERY failed fetch" misframes the evidence):** Zyte is **already** wired as the dead-last resort for every fully-failed URL â€” `access_bypass.py:1701-1707`, gated only on `ZYTE_API_KEY`. On Q76 the key was present and Zyte **fired and still lost**. So the fix is NOT "wire it in." It is three concrete gaps:

  **1a. Slow free chain eats the budget before Zyte runs.** Last-resort Zyte at 1701 sits behind the concurrent free group (`PG_BACKEND_FETCH_TIMEOUT=60s` + grace, `access_bypass.py:1265-1305`) + direct + Archive + retry, all racing the **90s AccessBypass worker wall** (`live_retriever.py:2490`, `worker.join(timeout=90)`) â€” which Codex confirmed sits *inside* the 120s outer per-task wall. A slow free chain abandons the worker (`access_bypass_timeout_90s`) before execution reaches line 1701.
  - **Change:** trigger Zyte **early/reserved** the moment a fetch is *classified* (via Fix #0) as SSL / timeout / anti-bot, AND **partition the budget** so the free chain cannot consume the whole 90s â€” reserve a Zyte headroom slice (e.g. free chain capped at ~55s, Zyte guaranteed ~25s inside the 90s wall). Env knobs that *partially* help today: `PG_FETCH_DEADLINE_SECONDS`, `PG_BACKEND_FETCH_TIMEOUT`, `PG_ZYTE_PAYWALL_FIRST=1` (paywall-publisher hosts only). Full fix is code.

  **1b. A thin SHELL preempts Zyte (the structural gap).** A 200â€“700-char abstract/landing shell survives the weak in-cascade `_detect_paywall` (`access_bypass.py:3451-3515`), wins the quality-score at `access_bypass.py:1597-1622`, and `fetch_with_bypass` **returns success there** â€” counted as "fetched", Zyte at 1701 never reached. The strong detectors (`is_content_starved`/`_is_landing_or_abstract_page`, `live_retriever.py:4346-4350`) run *downstream* and are **disconnected from Zyte**.
  - **Change:** connect the strong starved/landing detector to a Zyte/OA **upgrade** â€” either move the strong check *inside* candidate-acceptance at `access_bypass.py:1592-1597`, or arm the F14 upgrade gate by setting `PG_FETCH_MIN_BODY_CHARS=1000` (`live_retriever.py:146-148`, default `0` = gate OFF; F14 at `live_retriever.py:2696-2723`). Note even armed, F14's upgrade is **DOI-gated** (`live_retriever.py:2700-2701`) â€” DOI-less shells still need a direct shellâ†’Zyte route.

  **1c. Honest ceiling.** Zyte bypasses **bot-blocks, not paywalls** (`access_bypass.py:2487-2488`) and rejects content `<500` chars or paywalled (`_try_zyte` `_usable` gate, `access_bypass.py:2550-2555`). On Q76 the ~247 `no_content` URLs were largely **tried-and-failed by Zyte** â€” a genuine retrieval ceiling, not a wiring bug. "Rescue every fetch" is aspirational; for hard paywalls the lever is Fix #4 (legal OA), not Zyte.
- **Blast radius:** medium (paid calls, latency, quota). Spend authorized per standing memory.

## Fix #2 â€” curl_cffi TLS-impersonation tier (Tier 2.5) â€” cheapest 403-killer
- **Type:** CODE. **Expected yield:** medium-high on the **anti-bot/403 class at near-HTTP cost** â€” far cheaper than escalating to a browser or paying Zyte.
- **Current behaviour / gap:** the SSL/TLS grep over `access_bypass.py` returned **no TLS-impersonation** anywhere. Plain `httpx`/`requests`/`curl` get a 403 from Cloudflare v9 *before the User-Agent is read*, because the OpenSSL JA3/HTTP-2 fingerprint â‰  Chrome. This entire 403 class is currently unrecoverable until the expensive tiers.
- **Change:** insert `curl_cffi` (`impersonate="chrome131"`) as a **Tier-2.5** backend in the cascade â€” after direct HTTP, before browser/Zyte. Mimics real Chrome JA3/TLS + HTTP-2 frame order; defeats pure-TLS-fingerprint 403s cheaply.
- **Expected gain:** recovers the pure-fingerprint 403 subset (web-research: "the large class of 403s that are pure TLS-fingerprint blocks") before any paid call. Pairs with Fix #1 (Zyte still needed for IP-reputation + behavioral blocks curl_cffi can't beat).
- **Blast radius:** low (new dependency `curl_cffi`; per-URL provenance records which tier won).

## Fix #3 â€” Retry + exponential backoff with full jitter, honor `Retry-After`, retry-only-retryable
- **Type:** CODE. **Expected yield:** **low marginal** â€” most anti-bot/SSL failures are *deterministic* (a 403 doesn't become a 200 on identical retry). Real but bounded gain on the transient (429/5xx/connreset/read-timeout) subset.
- **Current behaviour:** exactly **ONE** real retry in the whole pipeline â€” direct-HTTP timeout-only, `access_bypass.py:1661-1670` (`sleep(3)` then one `_direct_fetch`). `parallel_fetch.py:514` calls `fetcher.fetch()` exactly once, zero backoff. The cascade is fallthrough, not retry.
- **Change:** on **429/500/502/503/504/connreset/read-timeout only**, retry with **exponential backoff + full jitter** (`sleep=random.uniform(0, min(cap, base*2**attempt))`, cap 60â€“120s), **max 3 attempts**, and **parse `Retry-After` verbatim** on 429/503 (overrides computed backoff). **Never** retry 400/401/403/404/410 on the same method (a 403 means *escalate the tier*, not retry identically). Add a **per-host retry budget + circuit breaker** so retries don't burn the exact 90s budget Zyte (Fix #1) needs.
- **Expected gain:** modest; web research notes <20% of pipelines do backoff correctly so it's a "stay-ahead" hygiene win, but it is **not** the dominant lever here (failures are mostly deterministic).
- **Blast radius:** medium â€” naive retry can *cannibalize* the budget for Fixes #1/#2; keep it strictly retryable-only and budgeted.

## Fix #4 â€” DOI/PMID â†’ legal OA full-text resolver cascade (config + code)
- **Type:** config (Unpaywall/PMC live) + CODE (OpenAlex/CORE routing). **Expected yield:** **high for paywalled-journal failures** â€” exactly the class Zyte *cannot* crack.
- **âš  For THIS biomedical workload (Q76 = gut microbiota/CRC), this may be the true #1.** Much of the failed set is plausibly paywalled journals with legally-hosted free copies (PMC/Europe PMC JATS, Unpaywall green/gold, OpenAlex, CORE). Codex independently ranked this **#1 by safety** for the same reason. The task asked me to lead with Zyte; I honor that in ordering, but flag explicitly: **Fix #0 settles whether OA outranks Zyte for this workload.**
- **Current behaviour:** Unpaywall OA-swap + PMC-BioC exist (`access_bypass.py:1414-1438`, default-on with `PG_UNPAYWALL_ENABLED=1`). **Codex correction (cheap config win):** the Unpaywall email env var is **split** â€” `live_retriever.py` reads `PG_UNPAYWALL_EMAIL`, but `AccessBypass._try_unpaywall` reads `UNPAYWALL_EMAIL`. If only one is set the resolver **silently underperforms**. â†’ **Set/unify BOTH.**
- **Change:** build the resolver **cascade** (stop at first fetchable full text), prefer **JATS XML > publisher PDF > repository PDF > landing page** and `publishedVersion > acceptedVersion > submittedVersion`:
  1. **Unpaywall** `v2/{DOI}` â†’ `best_oa_location.url_for_pdf` (prefer `host_type=publisher`, `version=publishedVersion`); else walk `oa_locations[]`.
  2. **OpenAlex** `works/doi:{DOI}` â†’ `best_oa_location.pdf_url` / `open_access.oa_url` (needs free API key, 100k credits/day; independent second opinion + covers DOIs Unpaywall lacks).
  3. **Europe PMC / PMC** â€” if PMCID (via **NCBI ID Converter** `idconv/api/v1`, up to 200 IDs/call) â†’ `/{PMCID}/fullTextXML` (**JATS preferred over any PDF for claim-grounding**).
  4. **Semantic Scholar** `paper/DOI:{DOI}?fields=openAccessPdf,externalIds` â†’ `openAccessPdf.url`.
  5. **CORE** `/search/works` + `_exists_:fullText` â†’ `downloadUrl`, **only after CrossRef-title-anchor match** (CORE mis-tags DOIs â€” POLARIS already learned this, I-faith-002; never trust DOI-equality alone).
  6. **Preprint** (arXiv/bioRxiv/medRxiv) via alternate DOI.
- **Expected gain:** high on the academic subset; legal (no paywall scraping), low blast radius, highest safety. Carry `email`/`tool`/keys for politeness-pool quotas; de-dup preprint-vs-published DOI before fetch.
- **Blast radius:** low.

## Fix #5 â€” Scoped SSL-verify relaxation for cert-EXPIRED hosts only
- **Type:** CODE. **Expected yield:** medium for the *exact* cert-expired bucket (common on long-tail gov/institutional hosts), narrow otherwise. **Sized by Fix #0.**
- **Current behaviour:** the grep for `verify=False|SSLError|CERTIFICATE|cert` in `access_bypass.py` returned **no matches** â€” cert-expired hosts fail normally with **zero targeted recovery**.
- **Change (surgical, NEVER global â€” Codex + NIST-grounded):** on a TLS failure, inspect the OpenSSL reason. **If and ONLY if** the sole reason is `X509_V_ERR_CERT_HAS_EXPIRED` / `CERT_NOT_YET_VALID` **and hostname matches and the chain is otherwise valid**, re-attempt **once** with a custom `ssl.SSLContext` that keeps **hostname + chain verification ON** but ignores the expiry bit (NOT `verify=False`). Try refreshing the CA bundle (`certifi`/`REQUESTS_CA_BUNDLE`) first to fix the missing-intermediate subclass without weakening anything. Treat untrusted-CA / hostname-mismatch / self-signed / revoked as **hard, non-recoverable**.
- **Constraints (must hold):** per-host, per-reason (expired-only), second-attempt-only, read-only public fetch, **log host+count+final-URL every time**, weight resulting content lower-trust in provenance. Enforce TLS 1.2 min.
- **Blast radius:** medium (TLS authenticity weakened for those specific origin fetches only) â€” the strict scoping is what keeps it safe.

### Ranking summary
| # | Fix | Type | Class it rescues | Expected yield | Blast |
|---|---|---|---|---|---|
| 0 | Instrument `drop_reasons` + `tool_trace.jsonl` | CODE | (measures all) | prerequisite | none |
| 1 | Early/reserved Zyte + budget-partition + shellâ†’Zyte upgrade | CODE | anti-bot, slow-host, thin-shell, non-OA publisher | high* | med |
| 2 | curl_cffi TLS-impersonation Tier 2.5 | CODE | pure-fingerprint 403 (cheap) | med-high | low |
| 3 | Retry+full-jitter backoff, honor Retry-After | CODE | transient 429/5xx/timeout | low | med |
| 4 | DOIâ†’legal OA resolver cascade (+ unify Unpaywall email) | CFG+CODE | **paywalled journals** | high* | low |
| 5 | Scoped cert-expired SSL relaxation | CODE | expired-cert long-tail hosts | med | med |

\*Fixes #1 and #4 compete for #1 by *yield*; **Fix #0 settles the order empirically.** For the biomedical Q76 workload, #4 (legal OA) plausibly leads.

---

# PART B â€” WHY IT IS SAFE (zero faithfulness risk)

**Fetch is strictly UPSTREAM of verification.** Per CLAUDE.md Â§-1.3 (WEIGHT-AND-CONSOLIDATE) and Â§9.1: every fetched body still flows through the **same extractor â†’ strict_verify (provenance token + numeric-match + â‰¥2 content-word overlap) â†’ NLI entailment â†’ 4-role D8 â†’ span-grounding**. None of those gates is touched by any fix above. Raising fetch yield can only *help* faithfulness:

- **More real fetched sources â†’ richer claim-baskets â†’ better strict_verify survival + multi-source corroboration** (Â§-1.3 basket faithfulness). drb_76 was starved at the *fetch* stage (29 docs â†’ 15 verified sentences â†’ 5 biblio entries), not the verify stage. Feeding the verifier more *real* evidence strengthens it; it never relaxes a gate.
- **Hard invariants preserved (Codex-confirmed "what must not change"):**
  1. Fetch returns ONLY content actually retrieved from a real URL â€” **no synthetic/fabricated sources** (LAW II).
  2. **No illegal paywall circumvention** â€” Sci-Hub stays OFF (`PG_SCIHUB_ENABLED=0`); only **legal OA resolvers** (Fix #4) + **licensed Zyte** (Fix #1).
  3. Downstream faithfulness gates **byte-untouched**.
  4. SSL relaxation (Fix #5) is origin-host-scoped, expired-only, second-attempt-only, never global, logged + trust-flagged every time.
- **Provenance:** every fix records *which tier won*, *whether SSL was relaxed*, *retry count* â€” fully auditable, and the relaxed-SSL / repository-version content carries a lower credibility weight into the basket (weight, don't drop).

**Net:** these fixes change *how much real evidence reaches the verifier*, never *what the verifier accepts*. That is the definition of a safe upstream change.

---

# PART C â€” SMOKE PLAN (requires a FRESH run â€” resume will NOT exercise the fix)

**Why fresh:** all fixes live *before* `corpus_snapshot`. A resume replays the cached corpus and **will not re-run the fetcher** â€” it would show no change and falsely "pass." The replay-harness/resume smoke does **not** apply here. This is a longer loop than the resume-based verify smoke; budget accordingly.

**Cheapest valid test:** ONE question â€” **Q76** (the known-bad 3.9% run), single fresh run, before/after comparison.

**Exact env slate the fresh test MUST set (or the fixes won't fire):**
```
PG_FETCH_MIN_BODY_CHARS=1000      # arms F14 shellâ†’OA/Zyte upgrade (default 0 = OFF)
ZYTE_API_KEY=<from polaris_run/.env>   # verify it FIRES: grep -ci zyte run.log > 0
PG_UNPAYWALL_EMAIL=<addr>  +  UNPAYWALL_EMAIL=<same>   # Codex: unify the split var
PG_UNPAYWALL_ENABLED=1
PG_ZYTE_PAYWALL_FIRST=1           # (or the new early-Zyte flag once Fix #1 lands)
PG_SWEEP_FETCH_CAP=<high, no-downgrade slate>   # let all candidates through
# Fix #0 instrumentation active so drop_reasons populates
```

**Procedure:**
1. **Baseline (already have):** drb_76 = `fetched=29 / candidates=740` (3.9%), `drop_reasons={}`.
2. **Run fresh Q76** with the slate above on a free box (cost ~$7/run, spend authorized per standing memory â€” announce the paid launch).
3. **Measure before vs after:**
   - `retrieval.fetched / retrieval.candidates_total` (fetch-success rate â€” primary metric).
   - **NEW: `retrieval.drop_reasons` breakdown** (Fix #0) â€” confirm the 709 `errored` now split into SSL/403/paywall/404/DNS, and confirm *which fix* each bucket responds to.
   - `grep -ci zyte run.log` > 0 (Zyte actually fired); count Zyte rescues.
   - downstream: `finding_dedup.distinct_finding_count`, `generator.sentences_verified`, biblio entries â€” confirm **corpus richer + report less fragmentary**.
4. **Pass criteria:** fetch-success rate materially up (target â‰« 3.9%); `drop_reasons` populated and explains the residual; report shows more verified sections / multi-source baskets. **Faithfulness gates must show identical strictness** (no drop in strict_verify rigor â€” only more *input* survives).

**Honest caveat:** per web research, success is **per-site not global** â€” a residual hostile-domain tail (Shein/G2-class, and genuine hard paywalls) resists even the best unblocker. Don't expect 100%; expect the funnel chokepoint to move off the fetch stage.

---

# PART D â€” Systemic vs Q76-specific (the 29/740 vs 831 variance)

**What the data actually shows:** I forensically hold **only drb_76** (29/740 = 3.9%). The "831 fetched on another run" figure is referenced but I do **not** have that run's manifest. **I will not fabricate a cause-split for either run** â€” drb_76's `drop_reasons` is empty, and the 831 run was never forensically opened. Honest statement: **the per-cause composition is currently UNKNOWN for both runs.**

**Likely drivers of the variance (evidenced, not fabricated):**
1. **Candidate host-mix differs per question.** drb_76's 740 candidates likely skewed toward paywalled journals + anti-bot + cert-expired hosts that the free chain can't crack; the 831 run's mix was likely friendlier. This is the dominant structural explanation and is consistent with the web-research finding that success is per-site.
2. **Module-global crawl4ai circuit breaker = variance amplifier** (Codex correction: threshold defaults to **6**, not the docstring's 3; cooldown 120s, `access_bypass.py:154-157`). Once N consecutive crawl4ai failures trip it, **all** fetches skip crawl4ai for 120s â€” if a question's full-text depends heavily on crawl4ai-only pages, yield collapses for that window. Bad runs cascade after early subprocess failures.
3. **Slow-chain-starves-rescue.** When the free chain runs slow, the 90s AccessBypass wall (`live_retriever.py:2490`) abandons the worker *before* Zyte runs (`access_bypass_timeout_90s`) â€” so a slow host-mix gets *no* paid rescue, amplifying the bad-run dip.

**How the fix addresses BOTH runs:**
- **Fix #0** makes the variance *diagnosable* for the first time â€” future 29-vs-831 swings come with a cause-split instead of a mystery.
- **Fix #1 budget-partition + early Zyte** stops the slow-chain-starves-rescue mechanism, so a hostile host-mix still gets the paid rescue it currently misses â€” directly compressing the low tail.
- **Fix #4 OA cascade** is host-mix-robust: a paywalled-journal-heavy question (the drb_76 failure mode) is exactly where legal OA copies rescue what Zyte cannot.
- **Breaker tuning** (raise threshold / make per-host not module-global) damps the amplifier so one bad early window doesn't sink the whole run.

**Bottom line:** the variance is most consistent with a **per-question host-mix interacting with rescue mechanisms that arrive too late or are absent for whole failure classes** â€” not a single bug. The plan raises the *floor* (early/reserved rescue + OA + curl_cffi + cert handling) and makes the variance *visible* (Fix #0), addressing both the systemic chokepoint and the run-to-run swing. The cause-split that would let us rank #1 vs #4 with certainty is exactly what Fix #0 produces on the next fresh Q76 run.
```

Key file:line anchors verified live this session: `access_bypass.py:1701-1707` (last-resort Zyte), `:1597-1622` (shell wins quality-score, preempts Zyte), `:1690-1730` (exhaustion + F14 warning); `live_retriever.py:2490-2562` (90s worker wall + abandonment), `:146-150` (`PG_FETCH_MIN_BODY_CHARS` default 0). Codex corrections folded in: inner 90s wall before outer 120s, crawl4ai breaker threshold defaults to 6, split `PG_UNPAYWALL_EMAIL`/`UNPAYWALL_EMAIL`. Advisor's five must-haves all incorporated: Fix #0 instrumentation prerequisite, Zyte reframed from forensic (already fires; fix the starvation + shell-preempt, not "wire it"), OA flagged as plausible true-#1 for biomedical workload, curl_cffi Tier 2.5 added, no fabricated 831 cause-split.