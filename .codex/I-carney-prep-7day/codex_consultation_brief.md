# Codex consultation — 7-day parallel-work plan for POLARIS Carney demo

This is a PLANNING consultation, not a diff/brief review. No 5-iter convergence cycle expected. Single round, free-form output. Goal: surface what's missing from my proposed parallel-work plan.

## Context

**Demo target window:** 2026-06-05 to 2026-06-09 (PM Mark Carney's office).

**Hardware procurement just kicked off (today, 2026-05-13):**
- OVH Canada BHS H200 GPU server (sovereign LLM inference) — 5-10 business day lead time
- Vexxhost Montréal VM (orchestrator) — 1 day to provision once subscribed
- Canadian DNS registrar (easyDNS or CIRA partner) — 1 day

**User directive 2026-05-13 verbatim:** "Full sovereign — no US company anywhere." Plus a clarification: "search provider is OK to stay serper, as I don't need to share confidential information in it." Serper remains as the search backend (US, disclosed in /transparency). Code-side Serper-stays revert is a small follow-up I owe but haven't shipped yet.

**Just shipped (today):** PR #488 I-carney-008 sovereign pivot. AWS archived. infra/vexxhost/* created. config/egress_allowlist.txt expanded for T1 corpus + bib/DOI + policy-domain hosts. scripts/egress_lockdown.sh rewritten for IPv4 + IPv6 dual-stack. scripts/egress_runtime_tighten.sh strips build-time US-corp hosts post-build. /transparency endpoint adds provider, region, build_time_hosts_pruned fields. Codex APPROVE iter 5/5.

**Prior demo substrate shipped (PRs #475-#485):**
- v6 backend: FastAPI + Dramatiq + Redis + run_store SQLite + SSE Redis Streams + Last-Event-ID resume
- Frontend: Next.js 16 + /api/v6/* rewrites + auth + bundle download
- Auth: static_accounts YAML + HS256 JWT 12h + passlib bcrypt
- Bundle signing: GPG detached signature over manifest.yaml; pubkey served from /transparency/pubkey.asc
- Pipeline-A end-to-end: scope gate → corpus adequacy → live retrieval → generator → strict_verify → manifest

## My proposed 7-day parallel-work plan

### Critical path (the demo content itself)

1. **Pre-run + audit the 10 demo questions** on current POLARIS (existing OpenRouter backend before vLLM cutover). Q1 tirzepatide / Q2 pharmacare / Q3 NORAD modernization / Q4 AI sovereignty / Q5 digital services tax + 5 staff-style variants. Line-by-line §-1.1 audit each (PRISMA 2020 / AMSTAR-2 / GRADE per claim; VERIFIED / PARTIAL / UNSUPPORTED / FABRICATED / UNREACHABLE per cited span).
2. **Build the demo binder** — collected reports + per-claim audit grid + signed manifest exemplar + /transparency export, as one PDF Carney's office can take home.

### Plumbing risk-reduction (cheap, catches bugs before hardware lands)

3. **Smoke-test infra/vexxhost/provision.sh in local Ubuntu 24.04 Docker container.** Script has never been executed end-to-end. Catch bugs offline, not on Vexxhost time.
4. **Smoke-test docker-compose.v6.yml end-to-end locally** — full pipeline-A on existing OpenRouter, real bundle.tar.gz round-trip, real GPG verify.
5. **GH#199 vLLM client code (offline-testable with mocked endpoint).** vLLM has OpenAI-compatible API. Write + unit-test the client now; flip POLARIS_LLM_BACKEND=vllm when OVH H200 lands.

### Cleanup owed to user

6. **Serper-stays revert PR** — re-add google.serper.dev to egress_allowlist.txt; close GH#487 as user-directive-WONTFIX; update transparency.md.

### Operator-side prep (parallel to admin's provisioning work)

7. **Generate demo GPG signing key** — bash scripts/bootstrap_gpg_demo_key.sh
8. **Author static_accounts.yaml** — bcrypt-hashed carney_office + operator + viewer
9. **Build encrypted offline secret bundle** — polaris_demo_secrets.tar.gz.gpg on operator YubiKey for fallback-laptop path

## My ask

You are a senior engineer reviewing this 7-day plan. **What am I missing?**

Specifically:

1. **What demo-day failure modes does my plan NOT hedge against?**
   For example: what if OpenRouter degrades during demo? What if the chosen non-US search provider has a different rate-limit shape than Serper? What if vLLM serves DeepSeek V4 Pro + Gemma 4 31B differently than OpenRouter does (token tokenizer mismatch, sampling drift, etc.)? What if the user's existing 10-question set produces abort_corpus_inadequate on the sovereign deploy because some T1 govt source DNS resolves to a different IP under the lockdown than during pre-audit on dev?

2. **What infrastructure has never been tested end-to-end in the configuration we'll demo?**
   - Has anyone ever actually run docker-compose.v6.yml with the I-carney-008 sovereign provisioning script applied?
   - Has the IPv6 lockdown actually been validated against an IPv6 capable test target?
   - Has the egress_runtime_tighten.sh build-time host stripping been validated to not break runtime fetches?
   - Has the GPG manifest verify path been validated against a bundle produced by the v6 stack (not slice-005 era)?

3. **What's the rollback plan if the demo deploy is dead at T-1?**
   - The §5 fallback laptop is documented. Has it been validated end-to-end?
   - Is the laptop's POLARIS_LLM_BACKEND fallback (openrouter) actually sufficient to serve 10 questions during a live demo, including the BPEI ambiguity flow, the Inspector pane, etc.?

4. **What demo-day operations questions am I not thinking about?**
   - Network resiliency: what if the venue Wi-Fi blocks WebSocket/SSE?
   - Browser caching: is there a stale-state problem if Carney's office reloads mid-demo?
   - User-account provisioning lag: how long does first-login take from cold cache?
   - Slack/email channel for live ops if anything goes wrong during demo?

5. **What §-1.1 audit prep am I missing?**
   - Should I be running the 10 questions through ChatGPT Deep Research + Gemini Deep Research in parallel for BEAT-BOTH comparison cred? Or has the user decided that's not the framing anymore?
   - For each canonical T1 source the demo cites (FDA labels, Health Canada DPD, NICE TA, etc.), do I have a fallback URL if the primary is paywalled/down on demo day?
   - Has the strict_verify gate been tuned for the actual content domains the demo will hit (clinical / policy / defense / ai_sovereignty / workforce)? I see 4 domain templates GH#196/#197/#198/#198 completed but defense + workforce may have corpus_inadequate risk under our specific question phrasings.

6. **What handover artifacts is Carney's office actually going to want?**
   - A static PDF? A live demo URL? Source code repo access? An audit binder?
   - SLAs on how long the deploy stays live post-demo (re-runnable for staff)?
   - Reproducibility: can a third-party audit firm reproduce our bundles bit-for-bit?

7. **What organizational / contractual risks haven't been addressed?**
   - Is there a written briefing document for Carney's office summarizing what POLARIS is, what it isn't, and what the boundary of its claims is?
   - Is there an NDA / acceptable-use stance documented so the office doesn't feed it confidential corpus we'd then have to handle under PIPEDA/Law 25?

Please respond with a numbered list of GAPS or MISSING work items, each tagged P0 (catastrophic if missed) / P1 (will hurt demo) / P2 (nice-to-have / hedge). Don't grade my existing plan; assume it ships. Just tell me what ELSE belongs in the 7-day window.

## Output schema

```yaml
identified_gaps:
  - id: G1
    severity: P0 | P1 | P2
    summary: "..."
    why_missed: "..."
    proposed_action: "..."
    estimated_effort_days: 0.5 | 1 | 2 | 3
  - id: G2
    ...
priority_ordering_for_7_day_window:
  - day_1: [G_id, G_id, ...]
  - day_2: [...]
  ...
demo_day_failure_modes_uncovered:
  - "..."
```
