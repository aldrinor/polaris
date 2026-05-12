HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-carney-001 — Carney 1-week production deploy DECISION brief (Codex 5.5)

GH#462 (umbrella issue). You are the decision-maker per CHARTER §1.

## Boss directive 2026-05-12 (verbatim quotes)

> "my boss want to speed it up, we want to find a Canadian server, upload the whole thing on it, and run it, and let Mark Carney to use it, are you ready?"

User clarified (3 follow-up answers):

1. **Vendor pick re-opened**: "I need you to help me to find the most suitable one" — the May 3 OVH BHS H200 lock is reconsidered, not assumed.
2. **Production-grade, not a demo prop**: "Not a stupid demo, it need to be real, any person around Mark can really use it"
3. **Timeline**: Carney demo within **1 week** (~2026-05-19)

## The fork you must pick (the load-bearing question)

"Canadian server" is ambiguous on sovereignty strictness. Three options with very different 1-week feasibility profiles:

- **(a) App-hosted-in-Canada**: VPS in Montréal/Toronto, Postgres + Redis + ChromaDB in Canada, but model inference calls go to OpenRouter (US) and Serper (US). No GPU needed. **Feasible 1-2 days deploy + 3-4 days hardening.** This is what most "sovereign Canadian AI" demos actually mean in practice.
- **(b) Full sovereign**: zero foreign network egress. vLLM/SGLang on Canadian GPU, no OpenRouter, no Serper (replace with SearXNG self-hosted or DuckDuckGo), no Semantic Scholar fallback. **Not feasible in 1 week.** That's the entire I-phase0-007/008 + I-sov-001..004 chain that's been sitting pending. Two-family-segregation re-verify on a sovereign LLM stack alone is multi-day.
- **(c) Hybrid-no-sensitive-data**: app in Canada, inference touches US APIs but scope is public-policy research (no PHI, no client docs, only Tier-1 public sources). Sovereignty-preserved-via-no-sensitive-data + Carney's office briefing makes this an explicit policy choice. **Feasible 1 week**, but needs an explicit public-statement of the sovereignty posture so the demo doesn't overclaim.

Most "sovereign Canadian AI to PM" framings politically need (b). The 1-week budget only fits (a) or (c). Pick one and justify.

## Vendor pick (consistent with sovereignty pick)

Per memory `feedback_no_cost_mentions.md`: rank by quality, NOT by price. Quality dimensions:

- **GPU class** (only if (b)): H100 80GB / H200 141GB / L40S 48GB / A100 80GB
- **GPU memory bandwidth** (matters for 70B+ model inference latency)
- **Canadian DC location** (Montréal QC, Toronto ON, Calgary AB, Vancouver BC)
- **Network bandwidth + uplink** (concurrent users)
- **Provisioning lead time** (this is the binding constraint for 1-week)
- **Security certifications** (SOC 2 / ISO 27001 / Canadian government posture)
- **Support SLA** (24/7 phone, response time)
- **Maturity** (production deployments, not a startup with 3 H100s)

Known Canadian-DC GPU candidates (research the current state via web search if your knowledge is stale):

- **OVH Beauharnois (Québec)** — H200, locked May 3. Verify 2026-05 lead time to provision today.
- **AWS ca-central-1 (Montréal)** — H200/H100 on-demand p5/p4d, instant provisioning if quota approved.
- **GCP northamerica-northeast1 (Montréal)** — A100/H100 a3/a4 instances.
- **Azure Canada Central (Toronto)** — ND-series H100/H200.
- **GenesisCloud (Montréal)** — H100 sovereign-cloud option, smaller player.
- **CoreWeave (Toronto if available)** — H100 dense, GPU-first.
- **Vultr Toronto** — A100 on bare metal.
- **Paperspace (Toronto)** — A100/H100.

Known Canadian-DC non-GPU VPS candidates (sufficient if option (a) or (c)):

- **AWS ca-central-1** — EC2 m6i/m7i + Fargate + RDS Postgres.
- **GCP northamerica-northeast1** — Cloud Run + Cloud SQL.
- **OVH Public Cloud Montréal** — managed Postgres, GPU optional.
- **DigitalOcean Toronto** — droplets + managed Postgres.
- **Vultr Toronto** — VPS + managed Postgres.

The May 3 OVH lock has 9 days of staleness. Either re-affirm or substitute.

## 1-week phasing (your call)

Day-by-day calendar (today is Tue 2026-05-12, demo target ~Tue 2026-05-19):

- **Day 1 (Wed 5-13)**: provision server, DNS, TLS, baseline container deploy, smoke
- **Day 2 (Thu 5-14)**: auth model wired (invite tokens? magic link? SSO?), env secrets, OpenRouter/Serper keys
- **Day 3 (Fri 5-15)**: multi-user concurrency (`MAX_CONCURRENT_RESEARCH` raised, queue tested), observability (M-PROD-3 already shipped — verify it actually emits)
- **Day 4 (Sat 5-16)**: canonical-question rehearsal — run the 5 Carney questions (canonical_question.txt) end-to-end, audit-grade output per §-1.1 line-by-line standard
- **Day 5 (Sun 5-17)**: regression fix from rehearsal, second rehearsal pass
- **Day 6 (Mon 5-18)**: demo runbook, fallback plan, 30-min walkthrough rehearsal with internal user, monitoring alerts wired
- **Day 7 (Tue 5-19)**: Carney office demo

## What's deferred post-demo (your call which of these are NOT deferred)

- F-snowball claim-graph (already shipped today — INCLUDE in demo)
- Inspector 5-view UI (shipped, INCLUDE)
- BPEI ambiguity detector (shipped, INCLUDE)
- F3b upload backend (shipped, INCLUDE)
- F15 audit bundle export (shipped, INCLUDE)
- Sovereign vLLM migration (defer to post-demo Phase 2)
- SGLang vs vLLM bakeoff (defer)
- Gemma 4 license sign-off (defer if option (a) or (c))
- Paid evaluator scoring loop (already done GH#195)
- Handover package (post-demo)

## Repo readiness facts (no inference, only verified)

- `Dockerfile`: python:3.11-slim, WeasyPrint, FastAPI/uvicorn, health check, ENTRYPOINT `/entrypoint.sh`, CMD `serve`. Production-shaped.
- `docker-compose.yml`: `web` + `chromadb` services exposed on 8000 + 8100. Optional `searxng` + `vllm` under `--profile sovereign`. `web` has memory limit 4G / reservation 2G — adequate for app, NOT for inference (inference goes to OpenRouter).
- `src/auth/auth_manager.py`: `AUTH_ENABLED` env flag, Bearer JWT, Role enum, AuthManager class — looks real, not stubs.
- `src/auth/auth_middleware.py`: FastAPI dependencies, `get_current_user`, `require_role` decorator — looks real.
- `src/auth/session_manager.py`: `MAX_CONCURRENT_RESEARCH=1` default. **For multi-user concurrent demo, must raise; needs queue verification.**
- `.env.example` 7.9KB — verify covers all foreign-API keys + DB connection strings + auth secret + observability endpoints.
- Foreign-API call sites:
  - `src/polaris_graph/llm/openrouter_client.py` — `https://openrouter.ai/api/v1` (env-driven `OPENROUTER_BASE_URL`)
  - `src/polaris_graph/retrieval/live_retriever.py` — `https://google.serper.dev/search`
  - Semantic Scholar (need to grep)
- F-snowball claim-graph view: shipped this session (6 PRs, GH#447/456/458/459/460/461), includes `/runs/[runId]/graph` page + PNG/JSON export.

## Direct questions you must answer

1. **Sovereignty bar**: (a) / (b) / (c) — pick one with justification. If you pick (b), how do you fit it in 1 week, or do you push the demo date? If you pick (a) or (c), what's the public-facing sovereignty narrative for Carney's office?
2. **Vendor**: ONE Canadian-DC vendor. Verify lead time today (you have web-search). If OVH BHS provisions today, confirm OVH. If not, name the substitute.
3. **Phasing**: any day-by-day reordering / scope adds / scope cuts. Hard constraint: 7 days.
4. **Auth model for the demo**: invite-token email link? Static admin/user accounts pre-provisioned? SSO? RBAC roles in code support all of these — pick the one that fits Carney's office workflow.
5. **Concurrency target**: how many concurrent active research runs the deploy must support (Carney + 5 staff? 20 staff? 100?). This sets MAX_CONCURRENT_RESEARCH + queue depth + provisioned resources.
6. **Fallback plan**: if the deploy goes wrong on demo morning, what's the local-laptop backup? (Currently demo could run from user's machine via existing `scripts/live_server.py`.)
7. **Sub-issues**: name the 4-6 sub-issues that need to be opened off GH#462 with day-by-day owners. Claude implements; you review per Issue.
8. **Anything blocking**: hidden dependency, license issue, infrastructure gap, data-sovereignty regulation (PIPEDA, AIDA, provincial sovereignty bills like Québec Law 25) that I haven't surfaced?

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
decisions:
  sovereignty_bar: "a" | "b" | "c"
  sovereignty_justification: ...
  vendor: <name + region + GPU class if applicable>
  vendor_justification: ...
  vendor_lead_time_today: <verified via web search>
  phasing: [day1: ..., day2: ..., day3: ..., day4: ..., day5: ..., day6: ..., day7: ...]
  auth_model: <invite_token | static_accounts | sso | other>
  concurrency_target: <integer>
  fallback_plan: ...
  sub_issues_to_open: [{id: I-carney-002, title: ..., scope: ...}, ...]
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
convergence_call: continue | accept_remaining
remaining_blockers: [...]
```

Use web search to verify current 2026-05 vendor lead times. Don't extrapolate from training data.
