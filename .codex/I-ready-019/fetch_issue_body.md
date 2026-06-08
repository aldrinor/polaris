## Context
Surfaced by the drb_72 re-run (#1146 / #1100). Legally-FREE journal full text is being silently dropped by the fetch layer.

## Evidence
- `aeaweb.org/articles/pdf/doi/10.1257/jep.33.2.3` (and `.15.1.25`, `.30.4.3`, `.24.4.187`) returned **1 char** via CRAWL4AI. The AEA Journal of Economic Perspectives is **publicly free** (https://www.aeaweb.org/journals/jep) — this is **anti-bot/User-Agent blocking of legally-free content**, not a paywall.
- Effect: a silent capability downgrade (LAW II / no-silent-downgrade). Legally-available evidence is dropped, starving the corpus.

## Fix
1. Fix the fetch mechanism for legally-free scholarly hosts: proper UA/headers, retry, and route through the OA URL when available.
2. Add a legal OA full-text fallback chain: **Unpaywall (discover) → CORE (fetch green-OA full text) → Semantic Scholar `openAccessPdf` → direct repository (NBER/RePEc/EconStor/SSRN)**. Exclude Sci-Hub (illegal) and publisher TDM APIs (subscription-gated, no free paywalled text).
3. **Provenance honesty:** when the recovered copy is a working-paper/preprint rather than the published Version of Record, RECORD which version was fetched (the WP can diverge from the VoR — a real faithfulness risk for a per-sentence-provenance pipeline).

## Acceptance
Legally-free journals (JEP etc.) fetch real content; corpus is not starved by anti-bot blocks; provenance records fetched version. MUST NOT weaken faithfulness gates. §-1.1 audit confirms cited spans match the fetched version.
