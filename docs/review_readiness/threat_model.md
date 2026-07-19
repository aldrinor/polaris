# POLARIS — Security / Privacy Threat Model

**Plan V4 item:** S4 — Security / Privacy Threat Model
**Audience:** Independent Telus code reviewer
**Scope:** `src/polaris_graph` deep-research pipeline + `src/polaris_v6/api` FastAPI surface
**Method:** Evidence-based static review. Every claim below cites a file/function/line actually read during this pass. No runtime code was modified.

---

## 0. Executive summary

| # | Axis | Severity of residual risk | One-line verdict |
|---|------|---------------------------|------------------|
| 1 | API authentication | **Med** | Production surface (v6) is JWT-gated by a global dependency with a fail-loud startup check — **but that startup check is fully bypassable by a single `POLARIS_AUTH_DISABLED=1` env var that is not blocked at production startup** (see §1). A separate legacy `src/auth/` HMAC system with insecure defaults also exists but is not wired into the production app. |
| 2 | Crawler SSRF | **HIGH → CRITICAL if API-reachable** | The vulnerable code (verbatim URL fetch, `follow_redirects=True`, **no private-IP / DNS-rebinding / metadata filter in the application layer**) is real. **But it is NOT reachable from the served polaris_v6 API** — the served `/api/retrieval` fetcher hits only fixed Serper/S2 endpoints and never fetches result-page bodies (§2.1). Exposure is via the **CLI/batch pipeline**. A network-layer egress lockdown is the only compensating control, and it **deliberately leaves `169.254.169.254` reachable** (§2.5). Rated **HIGH** as shipped; **CRITICAL** in any deployment that exposes a fetcher-reaching route with metadata access. |
| 3 | Prompt injection | **Medium** | Real defense exists (per-call random delimiters + evidence-text sanitization, §9.1.7), but coverage is per-call-site, not a single choke point; no output-side validation of injected instructions. |
| 4 | PII | **Medium–High** | Query + document + retrieved text are sent **verbatim** to third-party (largely US) providers (OpenRouter, Serper, Semantic Scholar). **No PII detection or redaction exists**, and there is **no consent capture, no DPA/data-retention control, and no provider-retention accounting in code** (§4). The only "scrubber" is a chain-of-thought remover, not a PII remover. |
| 5 | Log redaction | **Low** | API keys are not logged (only `bool(present)` / model / budget). A dedicated secret-scanner (`scripts/autoloop/scan_for_secrets.py`) guards commits. |
| 6 | Checkpoint retention | **Medium** | LangGraph SQLite checkpoints persist full pipeline state (including retrieved third-party content and drafts) at rest with **no automated retention/TTL/cleanup policy**; deletion is manual, per-vector only. |

**HIGHEST RESIDUAL RISK:** Axis 2 (Crawler SSRF) — HIGH as shipped, CRITICAL-conditional. The severity is now **conditional on deployment reachability**; the explicit condition is stated in §2.6. Axis 1 (the `POLARIS_AUTH_DISABLED` kill switch) is the second priority.

---

## 1. API authentication

### The production surface

The ASGI app the deployment serves is built by `create_app()` in
`src/polaris_v6/api/app.py:71`. Authentication is a **global** FastAPI
dependency applied to every route:

```
app = FastAPI(..., dependencies=[Depends(_require_auth)])   # app.py:79
```

`_require_auth` is `require_auth` from `src/polaris_v6/api/auth.py:129`. Design:

- **Scheme:** HS256 JWT signed with `POLARIS_JWT_SECRET`
  (`auth.py:88-96`, `issue_token` at `auth.py:113`). Login is
  `POST /auth/login` against a bcrypt-hashed static-accounts YAML
  (`auth.py:167`, `_pwd_ctx = CryptContext(schemes=["bcrypt"])` at `auth.py:50`).
- **Fail-loud startup:** `verify_app_startup()` (`auth.py:100`) is called
  at app construction (`app.py:73`). It raises `RuntimeError` if
  `POLARIS_JWT_SECRET` is missing or `< 32` chars (`auth.py:89-96`) or if
  the static-accounts YAML is missing/malformed (`auth.py:73-86`). The app
  refuses to boot with a broken auth gate.
- **Public allowlist** (`PUBLIC_PATH_PREFIXES`, `auth.py:35-42`):
  `/health`, `/transparency`, `/auth/login`, `/docs`, `/redoc`,
  `/openapi.json`. All other paths require a valid Bearer token.
- **SSE exception:** for `/stream/` paths only, the JWT may arrive as an
  `access_token` query param (because browser `EventSource` cannot set
  headers) — explicitly gated so lookalike paths and state-changing routes
  cannot use it (`auth.py:143-152`).

**Deployment secret hygiene:** `POLARIS_JWT_SECRET` is documented as a
64-byte URL-safe random value sourced from AWS Secrets Manager via
cloud-init, never in git (`docs/carney_secret_inventory.md:17`,
`docs/runbook.md:379`).

### The auth-disabled kill switch — **HIGH**

`require_auth` short-circuits to `None` (auth OFF) when
`POLARIS_AUTH_DISABLED=1` (`auth.py:106-107`), and `verify_app_startup()`
also skips its checks under the same flag (`auth.py:104-105`). This is
labelled "Phase-0 demo + tests".

**This is not merely a latent config risk — it is a HIGH-severity finding as
long as the switch is honoured at production startup.** The flag does two
things at once: it disables the per-request auth dependency *and* it disables
the fail-loud startup verification. The consequence is important for how the
"fail-loud startup" property above should be read:

- The startup check described above (raises if the JWT secret is missing /
  too short / accounts YAML malformed) is **only fail-loud when
  `POLARIS_AUTH_DISABLED` is unset**. Set the switch and `verify_app_startup`
  returns early (`auth.py:104-105`) — the app boots clean with **no JWT
  secret, no accounts file, and no auth on any route**. The "app refuses to
  boot with a broken auth gate" guarantee therefore holds *only* in the
  default configuration; the switch is an explicit, first-class bypass of it.
- **Nothing in `create_app()` / `verify_app_startup()` refuses this flag in a
  production context.** There is no environment/`ENV`/`is_production` guard
  that rejects `POLARIS_AUTH_DISABLED=1` when the app is not a demo (grep for
  the flag returns only the two read sites in `auth.py`; no production-mode
  gate). A single environment variable — one line in a compose file, one
  stray export in a deploy script, one copied `.env` — turns the entire API
  fully unauthenticated with no startup complaint.

**Rating: HIGH.** A remotely-reachable production API that can be silently
switched to zero-auth via one env var, with the safety startup check
switched off by the same var, is a High-severity authentication risk while
that path remains permitted at production startup. Remediation: refuse
`POLARIS_AUTH_DISABLED=1` unless an explicit `POLARIS_ENV in {demo,test}` (or
equivalent) is also set, so the switch physically cannot take effect in a
production boot.

### Legacy / non-production auth systems (NOT wired into the served app)

Two other auth implementations exist in the tree. A reviewer will find them
and should be told they are **not** on the production request path:

1. **`src/auth/` (HMAC-token system).**
   - `AUTH_ENABLED = os.getenv("POLARIS_AUTH_ENABLED","0") == "1"` — **off by
     default** (`src/auth/auth_manager.py:16`).
   - Hardcoded fallback secret:
     `AUTH_SECRET_KEY = os.getenv("POLARIS_AUTH_SECRET","polaris-dev-secret-change-in-production")`
     (`auth_manager.py:17`).
   - Default admin account created as `admin` / password `admin` if no users
     file exists (`_ensure_default_admin`, `auth_manager.py:135-152`;
     `POLARIS_ADMIN_PASSWORD` default `"admin"`).
   - Passwords hashed as **unsalted-per-user SHA-256** with a single static
     global salt (`_hash_password`, `auth_manager.py:155-159`) — fast hash,
     no bcrypt, weak against offline cracking.
   - **Grep confirms it is not imported by the served app:** no production
     module under `src/polaris_v6/` or the pipeline imports
     `src/auth/auth_routes` / `auth_manager` / `auth_middleware`.
2. **`src/polaris_graph/audit_ir/auth_middleware.py` (API-key + org/workspace
   RBAC).** A more rigorous per-resource, cross-tenant-scoped system
   (`require_authenticated_caller`, `require_org_member_of`, 403-not-404 to
   avoid existence leaks — `auth_middleware.py:262-276`). It has a test-only
   `X-Polaris-Caller` header gated behind `PG_AUTH_TRUSTED_TEST_HEADER`
   (default off, `auth_middleware.py:122-135`). **However**, the v6 facade
   `src/polaris_v6/api/inspector.py:15-19` *deliberately does NOT mount*
   `polaris_graph.audit_ir.inspector_router`, so this RBAC layer is also off
   the served path in the current demo build.

**Reviewer takeaway:** authentication on the shipped surface is coherent in
its default configuration, but the "fail-loud / production auth is sound"
characterization is **overstated while the `POLARIS_AUTH_DISABLED` switch
exists unguarded**: the same flag that disables auth also disables the
startup check, so "the app refuses to boot with a broken auth gate" is only
true when the switch is unset. Treat the auth posture as *"sound by default,
one env var from open, with the safety check on the same switch"* — not as
unconditionally fail-loud. Two further risks compound it: **three parallel
auth systems**, two dormant, one (`src/auth/`) carrying insecure defaults
(default admin/admin, hardcoded dev secret, SHA-256 passwords) that become
live if a future wiring change mounts `src/auth/` routes. Recommend (a)
gating `POLARIS_AUTH_DISABLED` behind an explicit non-production env marker,
and (b) deleting or clearly quarantining the dormant systems.

### CORS

`create_app()` sets CORS from `POLARIS_V6_CORS_ORIGINS` defaulting to
`localhost`/`127.0.0.1` dev ports, with `allow_credentials=False`,
`allow_methods=["*"]`, `allow_headers=["*"]` (`app.py:81-92`). With
credentials off and an explicit origin allowlist this is acceptable, but
the wildcard methods/headers should be tightened for a production origin.

---

## 2. Crawler SSRF — **HIGH (CRITICAL if reachable from an exposed API with metadata access)**

### The threat

The pipeline (a) issues search queries whose result URLs it then fetches for
page content, and (b) lets an LLM "harvest" seed URLs that are fetched
**verbatim**. If any of those URLs point at internal infrastructure
(`http://169.254.169.254/…` cloud metadata, `http://localhost:…`,
`http://10./172.16./192.168.` private ranges, or a redirect that lands
there), the server will fetch them and return their bodies into the
pipeline — classic Server-Side Request Forgery, leading to cloud-credential
theft, internal service enumeration, and internal data exfiltration.

### Evidence there is no SSRF control

I grepped the entire `src/` tree for the standard SSRF guards
(`is_private`, `ip_address`, `169.254`, `is_loopback`, `is_link_local`,
`gethostbyname`, `socket.getaddrinfo`, `ssrf`). **Zero of these appear in
any fetch path.** The only `urlparse(...).hostname` uses that exist are for
domain de-duplication and authority scoring, e.g.
`src/polaris_graph/generator/weighted_enrichment.py:504`,
`src/polaris_graph/synthesis/independence_collapse.py:173`,
`src/polaris_graph/retrieval/evidence_selector.py:1286` — none validate the
host against a blocklist before fetching.

### The vulnerable fetch code

- **Naive/fallback fetcher:** `_fetch_content_httpx_naive(url, max_chars)` in
  `src/polaris_graph/retrieval/live_retriever.py:2999` does
  `httpx.Client(timeout=..., follow_redirects=True, headers={...}).get(url)`
  (`live_retriever.py:3012-3025`) on a caller-supplied `url` with **no host
  validation** and **redirect-following enabled** — a redirect to
  `169.254.169.254` is followed.
- **Additional redirect-following fetchers with no host check:**
  `src/polaris_graph/retrieval/domain_backends.py:211,246`,
  `src/utils/ingest.py:1959`,
  `src/tools/core_client.py:215`, and the DOI resolver
  `src/tools/access_bypass.py:5590`
  (`aiohttp … session.get(url, allow_redirects=True)`).
- **LLM-controlled seed URLs:** `src/polaris_graph/retrieval/agentic_url_harvester.py:8`
  documents that harvested candidate URLs are *"fetched **verbatim** by
  `live_retriever.run_live_retrieval(seed_urls=…, seed_only=True)`"*
  (also lines 44, 157). This means a prompt-injection payload embedded in a
  fetched page can name an internal URL that the pipeline will then fetch —
  compounding axis 3 into an SSRF primitive.

### 2.1 End-to-end reachability / trust-boundary analysis

The application-layer defect above is real, but severity depends entirely on
**which inputs actually reach a vulnerable fetcher**. This section traces
every ingress. The decisive question a reviewer must answer is *"does the
served polaris_v6 API expose any path that reaches one of these fetchers?"* —
and the answer, on the code as shipped, is **no**.

**Trust boundaries and the three input classes:**

| Input class | Reaches a vulnerable fetcher? | Evidence |
|---|---|---|
| **Authenticated API params** (JWT-gated `/api/*` routes on the served app) | **No** (as shipped) | See §2.2 — the served retrieval route uses `real_fetcher`, which hits only fixed endpoints and returns URL *strings*, never fetching their bodies. |
| **Unauthenticated routes** (public allowlist: `/health`, `/transparency`, `/auth/login`, `/docs`, …) | **No** | Public routes are static/health/login/openapi only (`auth.py:35-42`); none invoke retrieval. |
| **LLM-harvested URLs** (a page the pipeline fetches names an internal URL that is then fetched verbatim) | **Yes — but only inside the CLI/batch pipeline** | `agentic_url_harvester.py:8,44,157` → `run_live_retrieval(seed_urls=…, seed_only=True)`. This ingress is real and is the worst case, but it is only driven by pipeline modules, not by any served route (§2.3). |

### 2.2 The served API does NOT reach a vulnerable fetcher

`create_app()` mounts the retrieval slice at `POST /api/retrieval`
(`app.py:127`). When `SERPER_API_KEY` is present it overrides the fetch
dependency with `build_real_fetcher()` (`app.py:119-126`). That fetcher is
**not** `live_retriever`:

- `real_fetcher.RealFetcher.__call__(query)` opens `httpx.Client()` and issues
  exactly two requests — `client.post(SERPER_ENDPOINT, …)`
  (`real_fetcher.py:101-102`) and `client.get(S2_ENDPOINT, …)`
  (`real_fetcher.py:139,148`). Both endpoints are **hardcoded constants**
  (`SERPER_ENDPOINT`/`S2_ENDPOINT`, `real_fetcher.py:42-43`). The caller's
  input (`query`) only populates the request *body/params*, never the
  destination host.
- The result URLs Serper/S2 return are packed into `FetchResult` objects as
  plain `url=` **strings** (`real_fetcher.py:112-118,159-172`) and handed back
  to `process_retrieval`. **Nothing in the served retrieval path then GETs
  those URLs' page bodies.** There is no content-fetch-of-result-URL step on
  the API path.
- Other served routes that could plausibly retrieve: `/upload` only reads the
  posted file bytes (`upload.py:155`, `await file.read()`) — no URL fetch;
  `/runs/{id}/followup` answers purely over the already-stored evidence
  contract (`followup/agent.py` imports only schema + regex, no HTTP client;
  its own copy explicitly tells the user to "start a new run to broaden
  retrieval", `agent.py:52`); `/api/runs/{id}/graph` reads AuditIR from disk
  (`graph_route.py`). None reach a fetcher.
- **Grep confirms the negative:** searching the entire served layer
  (`src/polaris_v6/**`, `src/polaris_graph/api/**`) for `run_live_retrieval`,
  `_fetch_content_httpx_naive`, `live_retriever`, `domain_backends`,
  `access_bypass`, or `utils.ingest` returns **zero hits**. No served route
  imports or transitively invokes any of the vulnerable fetchers.

### 2.3 Where the vulnerable fetchers ARE reached

The verbatim/redirect-following fetchers are called only by **pipeline-internal
modules** (generator, outline, nodes, retrieval, planning) —
`run_live_retrieval` callers include `generator/fetch_snapshot.py`,
`outline/outline_agent.py`, `nodes/crag_adequacy_loop.py`,
`retrieval/evidence_selector.py`, `retrieval/agentic_url_harvester.py`, etc.
Those modules are driven by the **CLI/batch entrypoints**
(`scripts/run_honest_full_cycle.py`, `scripts/run_live_honest_cycle.py`,
`scripts/run_honest_sweep_r3.py`, …), not by an HTTP handler. There is no
served route that imports `honest_pipeline` or the `graph.py` pipeline (grep
of `src/polaris_v6/**` returns nothing). **The trust boundary is therefore
operator-initiated batch runs, not the network-facing API.**

### 2.4 Redirect-following and DNS-rebinding

Both mechanisms that would defeat a naive host filter are present in the
vulnerable code, so if a fetcher-reaching route is ever exposed the defect is
fully weaponizable:

- **Redirect-following is on everywhere.** `follow_redirects=True`
  (`live_retriever.py:3015`, `domain_backends.py:211,246`) and
  `allow_redirects=True` (`access_bypass.py:5590`, aiohttp). An allowlisted or
  benign-looking first URL can 30x-redirect to `http://169.254.169.254/…`; the
  client follows it and returns the body. Any host-based check applied only to
  the *original* URL is bypassed by the redirect.
- **DNS-rebinding defeats a private-IP filter.** *A private-IP / metadata
  blocklist applied to the URL host string does not stop DNS-rebinding* — and
  it must be stated explicitly. httpx/aiohttp resolve the hostname themselves
  at connect time; an attacker controls a domain whose DNS returns a public IP
  on the validation lookup and a private/metadata IP on the connect lookup
  (or flips TTL=0 between the two). The only robust defenses are: resolve the
  host *once*, pin the connection to that resolved IP, and validate **that
  resolved IP** (not the hostname) — plus re-validate after every redirect
  hop. None of the fetchers do any of this; there is no resolve-then-validate,
  no IP pinning, no per-hop revalidation anywhere in `src/` (grep for
  `getaddrinfo`/`gethostbyname`/`is_private`/`ip_address` in fetch paths:
  zero).

### 2.5 Can internal responses be observed by the caller (exfiltration)?

**Yes, on the CLI/pipeline path.** Fetched bodies are not fire-and-forget:
`_fetch_content_httpx_naive` returns the response text as content
(`live_retriever.py`), and that content flows into evidence selection and then
into the generated report / evidence pool. An operator (or downstream reader
of the report) can therefore observe the body of whatever internal URL was
fetched — this is a **full read-SSRF with response exfiltration**, not a
blind SSRF, on the batch path. (On the served API path the question is moot,
because §2.2 shows no server route fetches such a URL in the first place.)

### 2.6 Does the runtime have network access to internal / metadata addresses?

This is a **deployment property, not a code property**, and it is the hinge
for the conditional rating. The repo ships one relevant control:

- **Network-layer egress lockdown.** `scripts/egress_lockdown.sh` +
  `config/egress_allowlist.txt` install iptables/ip6tables rules in `OUTPUT`
  (host) and `DOCKER-USER` (container) chains that **DROP all outbound tcp/80
  and tcp/443 except a resolved allowlist** of research domains
  (`egress_lockdown.sh:99-107`). This is a genuine defence-in-depth control:
  even with no application-layer SSRF filter, a fetch to an arbitrary internal
  host on 80/443 is dropped at the kernel.
- **But it does not close the metadata hole.** The lockdown **explicitly
  ACCEPTs `169.254.169.254/32`** — the cloud metadata endpoint — because
  OpenStack cloud-init needs it (`egress_lockdown.sh:87-91`). So the single
  highest-value SSRF target (instance-credential theft via IMDS) remains
  reachable *through the lockdown* if a fetcher can be pointed at it.
- **Two further limits.** (i) The rules only cover ports **80/443**; an
  internal service on 8080/6379/5432/etc. is not matched by these DROP rules
  at all. (ii) It is an **operator-run, deploy-time step** (must be run as
  root after `docker compose build`, `egress_lockdown.sh:20-33`) with no
  code-level guarantee it was applied — a host that skipped it has no egress
  restriction whatsoever. (iii) `egress_allowlist.txt:40-45` itself documents
  the DNS-rebinding weakness: iptables pins **one** resolved IP set per
  hostname, so it does not track rebinding either.

### 2.7 Conditional severity

**Rated HIGH as shipped; CRITICAL if the reachability condition holds.**
The explicit condition:

> **CRITICAL** iff a deployment exposes any route/entrypoint that reaches one
> of the vulnerable fetchers (`live_retriever`, `domain_backends`,
> `access_bypass`, `utils/ingest`) to attacker-influenced input **and** the
> runtime retains network access to internal/metadata addresses (i.e. the
> egress lockdown is absent, or — as shipped — leaves `169.254.169.254`
> reachable). **Otherwise HIGH**, pending deployment validation.

Why not simply CRITICAL: on the code as shipped, the network-facing
polaris_v6 API does **not** reach a fetcher (§2.2), so the remotely-triggered,
unauthenticated-attacker path that a CRITICAL implies is **not demonstrated**.
Why not lower than HIGH: the defect is fully weaponizable (redirect + rebind,
read-with-exfil, §2.4–2.5), it *is* reachable via LLM-harvested URLs on the
batch path (§2.1, so a poisoned upstream page reached in a normal run can pivot
to IMDS), and the one compensating control deliberately leaves the metadata
endpoint open (§2.6). This is a defect a reviewer must require fixed before the
pipeline is exposed behind any network-reachable fetch trigger.

**Deployment validation the reviewer should require (to resolve HIGH vs
CRITICAL):** confirm (a) no current or planned route mounts a
`run_live_retrieval`/pipeline entrypoint behind the API; (b) `egress_lockdown.sh`
is applied on every runtime host and the `169.254.169.254` ACCEPT line is
removed or tightened; (c) whether the batch pipeline runs on hosts with IMDS
reachable (IMDSv2 hop-limit / disabled metadata would also mitigate).

### Current application-layer mitigation

Partial and incidental only:
- `real_fetcher.py` (Serper/Semantic-Scholar) hits **fixed API endpoints**
  (`SERPER_ENDPOINT`, `S2_ENDPOINT`, `real_fetcher.py:42-43`), which is
  precisely why the served retrieval path is not SSRF-exposed (§2.2) — but
  the *content-fetch* step in the batch pipeline that follows returned URLs is.
- `access_bypass.py` has a domain **allowlist of low-quality Q&A sites to
  drop** (`access_bypass.py:154`) — that is a content-quality filter, not a
  security control; it does not block internal hosts.
- Fetches are timeout-bounded and there is a `fetch_limiter`
  (`src/polaris_graph/retrieval/fetch_limiter.py`), which caps concurrency but
  not destination.

**Recommended remediation (for the reviewer to require):** a single
choke-point `validate_fetch_target(url)` applied to *every* outbound fetch:
resolve the hostname **once**, pin the connection to that resolved IP, reject
any resolved IP in private/loopback/link-local/metadata ranges (including
`169.254.0.0/16`), reject non-http(s) schemes, and re-validate after each
redirect hop (or disable redirects and validate each hop manually). Pair it
with the network-layer lockdown *minus* the `169.254.169.254` ACCEPT (or
IMDSv2 with hop-limit 1). Until the application-layer check exists, treat the
crawler as SSRF-exploitable on any host where a fetcher can be driven.

---

## 3. Prompt injection

### The threat

Retrieved web pages, PDFs, and uploaded documents are untrusted text placed
inside LLM prompts. A page can contain "ignore previous instructions…" style
payloads that hijack the generator/classifier.

### Current mitigation (real, but per-call-site)

There is a genuine, named defense — "§9.1.7 delimiter/injection defense":

- **Per-call random delimiters.** `build_question_block()` in
  `src/polaris_graph/audit_ir/scope_classifier_llm.py:262` wraps untrusted
  input in `<<<question-{16-hex-random}>>> … <<<end-{token}>>>` and strips any
  token-shaped substring out of the body so content cannot forge a closing
  delimiter (`scope_classifier_llm.py:271-276`). The random per-call token
  means an attacker cannot predict the delimiter to break out. The same
  pattern is used in `auto_induction/llm_inductor._build_query_block`.
- **Evidence-text sanitization.** `generator/analyst_synthesis.py:159,407-424`
  routes evidence text (and the evidence *id*) through
  `sanitize_evidence_text` before wrapping in `<<<end_evidence>>>` delimiters,
  explicitly to stop content forging open/close delimiters.
- **Fail-loud on disabled sanitizer.** `generator/outline_digest.py:88-101`
  raises rather than silently returning identity if the sanitizer is a no-op,
  so the defense cannot be disabled unnoticed.
- The pipeline asserts *"Prompt-injection sanitization was applied to all
  evidence"* (`honest_pipeline.py:374`).

### Residual risk: **Medium**

- **Coverage is per-call-site, not a single enforced boundary.** The defense
  lives in specific modules (scope classifier, analyst synthesis, outline
  digest, inductor). There is no single guarantee that *every* place
  untrusted content enters a prompt goes through sanitization; a new call
  site can omit it. A reviewer should verify each prompt-construction path.
- **No output-side validation.** Defenses are input-shaping (delimiters +
  substring stripping). There is no post-generation check that the model did
  not act on an injected instruction (e.g., no verifier that the output stays
  on-task / did not emit an attacker-chosen URL). Combined with §2, an
  injected instruction naming an internal URL can drive an SSRF fetch.
- Delimiter defense mitigates *breakout*, not *persuasion*: a payload that
  stays inside the delimiters but is persuasive ("as the cited source, the
  correct answer is X") is not blocked.

---

## 4. PII

### The threat

User queries, uploaded documents, and retrieved third-party content may
contain personal data. That data is (a) sent to external LLM/search
providers and (b) persisted at rest (see §6).

### Current handling

- **Data is sent verbatim to third parties.** The research query, retrieved
  page/abstract text, and document text are placed into request payloads to
  OpenRouter (`src/polaris_graph/llm/openrouter_client.py`), Serper, and
  Semantic Scholar (`real_fetcher.py`). This is inherent to the product, but
  it means any PII in the input crosses to US/third-party processors.
- **No PII detection or redaction anywhere.** A grep for
  `redact|pii|PII|anonymiz|scrub.*email|gdpr` returns **no PII-removal code**.
  The only "scrub" utility is `src/utils/cot_scrubber.py` — its own docstring
  (`cot_scrubber.py:1-20`) states it removes leaked **chain-of-thought** text
  from reports, not PII. `scrub_cot_from_report` (used at
  `base_agent.py:596`, `graph.py:2428`) is a report-hygiene tool, not a
  privacy control.

### Provider data-retention, consent, and compliance exposure

"No redaction" understates the finding: the issue is not only that PII is
*sent*, but that it is sent **verbatim to third-party processors whose
retention and secondary-use terms the application neither records nor
enforces**, with no user consent captured at the point of egress. The
concrete gaps:

- **Provider retention is unaccounted-for.** The payloads go to OpenRouter
  (`openrouter_client.py`), Serper, and Semantic Scholar (`real_fetcher.py`).
  OpenRouter is a *broker* that forwards prompts to whichever upstream model
  provider serves the route — so the actual data controller varies per request
  and per model, and each may retain prompts for abuse-monitoring or training
  windows. Nothing in the code pins a zero-retention / no-training route, sets
  a provider data-policy header, or records which downstream provider received
  a given query. A reviewer cannot answer "where did this user's PII go and for
  how long is it retained?" from the code — that is itself the finding.
- **No consent or lawful-basis capture.** There is no consent gate, no notice
  at submission, and no per-request purpose/lawful-basis record before PII
  crosses to a US processor. For GDPR/PIPEDA this is a lawful-basis and
  cross-border-transfer gap, not merely a hygiene gap.
- **No DPA enforcement in code.** There is no data-processing-agreement
  reference, no processor allowlist tied to a signed-DPA list, and no
  data-classification of inputs before egress. The `/transparency` disclosure
  (§4 of that page) names the providers but disclosure is not consent and does
  not bound retention.
- **Sovereignty-brand mismatch.** For a Canadian-sovereignty-branded product
  ("Sovereign Canadian deep research AI", `app.py:77`), verbatim
  query/document PII crossing to US processors with unbounded, unrecorded
  retention is a material compliance and reputational exposure, distinct from
  the SSRF/injection technical risks.

### Residual risk: **Medium–High**

There is no data-classification, no PII redaction before egress, no consent
capture, no provider-retention control, and no DPA enforcement in code. The
severity sits above a plain "no redaction" Medium because the verbatim egress
is to processors with **unbounded, unaudited retention and no consent basis
recorded** — a compliance finding, not just a hygiene one. It stays below
CRITICAL only because it is an inherent, disclosed property of the product
(the data flow is intended and named in `/transparency`), not a covert leak.
Recommend, in priority order: (1) a DPIA documenting the full provider data
flow and each processor's retention/training terms; (2) contractual
zero-retention / no-training routing (e.g. an OpenRouter no-logging route or a
private vLLM backend — `POLARIS_LLM_BACKEND=vllm` already exists per
`egress_allowlist.txt:16-18`) and recording the chosen route per run; (3) a
consent/lawful-basis gate at submission; (4) optional input PII redaction
before egress.

---

## 5. Log redaction

### The threat

Secrets (`OPENROUTER_API_KEY`, `SERPER_API_KEY`, JWT secret, etc.) leaking
into logs or committed transcripts.

### Current handling — good

- **Keys are not logged as values.** The OpenRouter client logs only
  `model` and `budget` at init (`openrouter_client.py:1563-1567`); the key is
  placed solely into the `Authorization: Bearer` header
  (`openrouter_client.py:1587`), never into a log statement. The search agent
  logs only **presence** — `f"... API key present: {bool(api_key)}"`
  (`agents/search_agent.py:492`) — not the value.
- **TLS verification stays on.** The client shares a cert-verifying
  `SSLContext` (`openrouter_client.py:1583`, `get_shared_ssl_context`), so
  bearer tokens are not sent over unverified TLS.
- **Dedicated secret scanner.** `scripts/autoloop/scan_for_secrets.py`
  carries regexes for OpenAI/Slack/Google/Stripe keys, PEM private keys,
  `Authorization: Bearer` tokens, basic-auth URLs, and a vendor-agnostic
  `configured_secret_assignment` pattern that matches
  `POLARIS_JWT_SECRET`/`POLARIS_AUTH_SECRET`/vendor keys followed by a
  key-shaped value (`scan_for_secrets.py:40-71`). Matches are reported with
  the value redacted to an 8-char prefix (`scan_for_secrets.py:81`). A
  `pre-commit` config exists (`.pre-commit-config.yaml`).
- Secrets are documented as env-injected from AWS Secrets Manager, never
  committed (`docs/carney_secret_inventory.md`, `.env` is gitignored).

### Residual risk: **Low**

Two things to note rather than genuine holes:
- The scanner is a **best-effort regex**, not exhaustive — a novel key shape
  (e.g. a future provider) is caught only by the name-based
  `configured_secret_assignment` pattern, and only if the env var name is in
  its hardcoded list (`scan_for_secrets.py:63-68`).
- Third-party libraries (`httpx` at DEBUG, uvicorn access logs) could echo
  full URLs. The pipeline's own fetch URLs are truncated in logs
  (e.g. `url[:80]` at `live_retriever.py:2985`), but query strings on some
  API URLs may carry the S2/NCBI key as a param — worth confirming no fetch
  logs the full parameterized URL at INFO. Not observed leaking, but not
  provably absent.

---

## 6. Checkpoint retention

### The threat

The generation/pipeline checkpoint persists full pipeline state — including
the query, retrieved third-party content, and in-progress report drafts — to
disk. Sensitive data at rest with no lifecycle is a privacy and data-
retention exposure.

### Current handling

- **Store:** LangGraph `AsyncSqliteSaver` at
  `PG_CHECKPOINT_DIR/pg_checkpoints.sqlite`
  (`src/polaris_graph/checkpoint_manager.py:29-30`, `get_checkpointer` at
  line 37). Gated behind `PG_CHECKPOINT_ENABLED == "1"`
  (`checkpoint_manager.py:26`).
- **Contents are the full state snapshot.** `get_checkpoint_state()`
  returns the *complete* state values at a checkpoint
  (`checkpoint_manager.py:244-312`), and `rewind_to_checkpoint`
  (line ~337) resumes from them — i.e. drafts and retrieved evidence are
  stored verbatim.
- **Deletion is manual and per-vector only.** The only cleanup is
  `clear_checkpoint(vector_id)` (`checkpoint_manager.py:80-112`), which
  issues `DELETE FROM checkpoints/writes WHERE thread_id = ?` for one vector.
  There is **no TTL, no age-based prune, no purge job.** A grep for
  `retention|cleanup|ttl|expire|prune|purge|max_age` in the checkpoint
  manager returns nothing.
- No encryption-at-rest is applied by the application layer; the SQLite file
  is plaintext on the host volume.

### Residual risk: **Medium**

Checkpoints accumulate indefinitely unless an operator manually clears each
vector. They hold query text, retrieved (possibly copyrighted/PII-bearing)
third-party content, and draft reports, unencrypted at rest. There is no
data-retention policy expressed in code and no automated deletion after a run
completes. Recommend: an age-based retention sweep, opt-in
encryption-at-rest (or reliance on an encrypted volume, documented), and
auto-clear on successful run completion.

---

## 7. Consolidated findings table

| # | Finding | File / evidence | Severity |
|---|---------|-----------------|----------|
| F-1 | **Crawler fetches arbitrary/LLM-supplied URLs with `follow_redirects=True` and no private-IP / metadata (169.254.169.254) / loopback / DNS-rebinding filter — read-SSRF with response exfiltration.** No resolve-then-validate, no IP pinning, no `is_private`/`ip_address`/`169.254` guard anywhere in the fetch path. **Reachability (§2.1-2.3): NOT reachable from the served polaris_v6 API (served `/api/retrieval` uses fixed-endpoint `real_fetcher`, never fetches result-page bodies); reachable via CLI/batch pipeline + LLM-harvested seed URLs.** Network-layer egress lockdown is the only compensating control and it deliberately leaves `169.254.169.254` open (§2.6). | `live_retriever.py:2999-3025`; `domain_backends.py:211,246`; `access_bypass.py:5590`; `utils/ingest.py:1959`; verbatim seed fetch `agentic_url_harvester.py:8`; served path uses `real_fetcher.py:42-43,101-118,139`; served-layer grep for fetchers = 0 hits; `egress_lockdown.sh:87-91,99-107` | **HIGH; CRITICAL if a fetcher-reaching route is exposed with internal/metadata access** (condition stated §2.7) |
| F-2 | Prompt-injection defense is per-call-site, not a single enforced boundary, and has no output-side validation; a missed call site or persuasive-in-delimiter payload is undefended. Chains into F-1 on the batch path (injected internal URL → verbatim fetch). | `scope_classifier_llm.py:262-276`; `analyst_synthesis.py:159,407-424`; `honest_pipeline.py:374` | High |
| F-3 | **PII egress to third-party processors is verbatim, with no redaction, no consent/lawful-basis capture, and no provider-retention or DPA control in code** — a compliance finding, not just hygiene. Query + document + retrieved text go to OpenRouter (broker; downstream provider/retention unrecorded), Serper, S2. Only a CoT scrubber exists (not PII). | grep: no `redact/pii/anonymiz`; `cot_scrubber.py:1-20`; provider payloads `openrouter_client.py`, `real_fetcher.py`; `app.py:77` sovereignty brand | Medium–High |
| F-4 | Checkpoint store persists full state (drafts + retrieved content) unencrypted at rest with no automated retention/TTL; deletion is manual per-vector only. | `checkpoint_manager.py:26-30,80-112,244-312` | Medium |
| F-5 | Legacy `src/auth/` HMAC system carries insecure defaults (default admin/admin, hardcoded dev secret, SHA-256 passwords) — dormant but one wiring change from live. | `auth_manager.py:16-17,135-159` | Medium (latent) |
| F-6 | **`POLARIS_AUTH_DISABLED=1` kill switch disables all API auth AND the fail-loud startup check via the same flag, and is NOT blocked at production startup** (no env/prod guard). One env var makes the whole API zero-auth with the safety check silenced. | `auth.py:104-107`; no prod-mode guard in `app.py`/`auth.py` (grep) | **High** |
| F-7 | CORS uses wildcard methods/headers (credentials off, origins allowlisted). | `app.py:81-92` | Low |
| F-8 | Production auth surface is coherent **by default** (global JWT dependency, bcrypt logins, secrets from AWS SM) — but the "fail-loud startup" property is **conditional**: it is bypassed by F-6's switch, so it is not unconditionally sound. | `app.py:71-79`; `auth.py:100-167`; `carney_secret_inventory.md:17`; cf. F-6 | Low (positive, conditional) |
| F-9 | Secret hygiene in logs is good: keys never logged as values; dedicated commit-time secret scanner. | `openrouter_client.py:1563-1587`; `search_agent.py:492`; `scan_for_secrets.py:40-81` | Low (positive) |

---

## 8. Priority for the reviewer

1. **Block on F-1 (SSRF, HIGH → CRITICAL-conditional).** The application-layer
   fetchers have no destination validation and are fully weaponizable
   (redirect + DNS-rebinding, read-with-exfiltration). As shipped they are not
   reachable from the served API, which caps the rating at HIGH — but the
   reviewer must **validate the deployment condition in §2.7** before sign-off:
   confirm no route mounts a fetcher, that `egress_lockdown.sh` is applied on
   every host, and that its `169.254.169.254` ACCEPT is removed/tightened (or
   IMDSv2 hop-limit is set). Require the `validate_fetch_target()` choke point
   regardless — it is the durable fix.
2. **F-6 (auth kill switch, HIGH).** Refuse `POLARIS_AUTH_DISABLED=1` at
   production startup unless an explicit non-production env marker is set, so
   the switch cannot silently disable both auth and the startup check in a
   production boot.
3. **F-3 (PII, Medium–High).** Produce a DPIA of the provider data flow, pin
   zero-retention/no-training routing (or the private vLLM backend), record the
   route per run, and add a consent/lawful-basis gate before optional
   redaction.
4. Address F-2/F-4 (High/Medium) as fast-follows: centralize injection
   sanitization with output-side validation, and add a checkpoint
   retention/cleanup policy.
5. Housekeeping: delete or quarantine the dormant `src/auth/` system (F-5),
   tighten CORS (F-7).
