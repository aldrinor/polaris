# POLARIS — Security / Privacy Threat Model

**Plan V4 item:** S4 — Security / Privacy Threat Model
**Audience:** Independent Telus code reviewer
**Scope:** `src/polaris_graph` deep-research pipeline + `src/polaris_v6/api` FastAPI surface
**Method:** Evidence-based static review. Every claim below cites a file/function/line actually read during this pass. No runtime code was modified.

---

## 0. Executive summary

| # | Axis | Severity of residual risk | One-line verdict |
|---|------|---------------------------|------------------|
| 1 | API authentication | **Low–Med** | Production surface (v6) is JWT-gated by a global dependency with a fail-loud startup check; a **separate legacy `src/auth/` HMAC system with insecure defaults exists but is not wired into the production app**. |
| 2 | Crawler SSRF | **CRITICAL (UNRESOLVED)** | Arbitrary URLs from search results and LLM-harvested seeds are fetched verbatim with `follow_redirects=True` and **no private-IP / metadata-address filtering anywhere in the fetch path**. |
| 3 | Prompt injection | **Medium** | Real defense exists (per-call random delimiters + evidence-text sanitization, §9.1.7), but coverage is per-call-site, not a single choke point; no output-side validation of injected instructions. |
| 4 | PII | **Medium** | Query + document + retrieved text are sent verbatim to third-party providers (OpenRouter, Serper, etc.). **No PII detection or redaction exists.** The only "scrubber" is a chain-of-thought remover, not a PII remover. |
| 5 | Log redaction | **Low** | API keys are not logged (only `bool(present)` / model / budget). A dedicated secret-scanner (`scripts/autoloop/scan_for_secrets.py`) guards commits. |
| 6 | Checkpoint retention | **Medium** | LangGraph SQLite checkpoints persist full pipeline state (including retrieved third-party content and drafts) at rest with **no automated retention/TTL/cleanup policy**; deletion is manual, per-vector only. |

**UNRESOLVED CRITICAL:** Axis 2 (Crawler SSRF). See §2.

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

### The auth-disabled trap door

`require_auth` short-circuits to `None` (auth OFF) when
`POLARIS_AUTH_DISABLED=1` (`auth.py:106-107`), and `verify_app_startup()`
also skips its checks under the same flag (`auth.py:104-105`). This is
labelled "Phase-0 demo + tests". **Residual risk:** if this flag ever ships
enabled to a non-demo environment, the entire API is unauthenticated. It is
a single env-var away from open.

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

**Reviewer takeaway:** authentication on the shipped surface is coherent and
fail-loud. The risk is **three parallel auth systems**, two of which are
dormant, one of which (`src/auth/`) carries insecure defaults (default
admin/admin, hardcoded dev secret, SHA-256 passwords). If a future wiring
change mounts `src/auth/` routes, those defaults become live. Recommend
deleting or clearly quarantining the dormant systems.

### CORS

`create_app()` sets CORS from `POLARIS_V6_CORS_ORIGINS` defaulting to
`localhost`/`127.0.0.1` dev ports, with `allow_credentials=False`,
`allow_methods=["*"]`, `allow_headers=["*"]` (`app.py:81-92`). With
credentials off and an explicit origin allowlist this is acceptable, but
the wildcard methods/headers should be tightened for a production origin.

---

## 2. Crawler SSRF — **UNRESOLVED CRITICAL**

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

### Current mitigation

Partial and incidental only:
- `real_fetcher.py` (Serper/Semantic-Scholar) hits **fixed API endpoints**
  (`SERPER_ENDPOINT`, `S2_ENDPOINT`, `real_fetcher.py:41-43`), so the
  *search* step itself is not SSRF-exposed — but the *content-fetch* step
  that follows the returned URLs is.
- `access_bypass.py` has a domain **allowlist of low-quality Q&A sites to
  drop** (`access_bypass.py:154`) — that is a content-quality filter, not a
  security control; it does not block internal hosts.
- Fetches are timeout-bounded and there is a `fetch_limiter`
  (`src/polaris_graph/retrieval/fetch_limiter.py`), which caps concurrency but
  not destination.

### Residual risk: **CRITICAL**

No allow/deny list on destination host, no DNS-resolution-then-IP check, no
private-range block, no redirect-target revalidation. On any cloud host with
a metadata service, a single attacker-controlled URL (planted in a web page
the pipeline fetches, or a poisoned search result) can exfiltrate instance
credentials.

**Recommended remediation (for the reviewer to require):** a single
choke-point `validate_fetch_target(url)` applied to *every* outbound fetch:
resolve the hostname, reject any resolved IP in private/loopback/link-local/
metadata ranges, reject non-http(s) schemes, and re-validate after each
redirect hop (or disable redirects and validate each hop manually). Until
this exists, treat the crawler as SSRF-exploitable.

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

### Residual risk: **Medium**

There is no data-classification, no PII redaction before egress to providers,
and no data-processing-agreement enforcement in code. For a Canadian-
sovereignty-branded product ("Sovereign Canadian deep research AI",
`app.py:77`) this is a notable gap: query/document PII leaves the boundary to
third-party (largely US) providers with no scrubbing. Recommend documenting
the provider data flow in a DPIA and adding optional input redaction.

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
| F-1 | **Crawler fetches arbitrary/LLM-supplied URLs with `follow_redirects=True` and no private-IP / metadata (169.254.169.254) / loopback filtering — SSRF.** No `is_private`/`ip_address`/`169.254` guard anywhere in the fetch path. | `live_retriever.py:2999-3025`; `domain_backends.py:211,246`; `access_bypass.py:5590`; `utils/ingest.py:1959`; verbatim seed fetch documented `agentic_url_harvester.py:8` | **CRITICAL (unresolved)** |
| F-2 | Prompt-injection defense is per-call-site, not a single enforced boundary, and has no output-side validation; a missed call site or persuasive-in-delimiter payload is undefended. Chains into F-1. | `scope_classifier_llm.py:262-276`; `analyst_synthesis.py:159,407-424`; `honest_pipeline.py:374` | High |
| F-3 | No PII detection/redaction; query + document + retrieved text sent verbatim to third-party providers; only a CoT scrubber exists (not PII). | grep: no `redact/pii/anonymiz`; `cot_scrubber.py:1-20`; provider payloads in `openrouter_client.py`, `real_fetcher.py` | Medium |
| F-4 | Checkpoint store persists full state (drafts + retrieved content) unencrypted at rest with no automated retention/TTL; deletion is manual per-vector only. | `checkpoint_manager.py:26-30,80-112,244-312` | Medium |
| F-5 | Legacy `src/auth/` HMAC system carries insecure defaults (default admin/admin, hardcoded dev secret, SHA-256 passwords) — dormant but one wiring change from live. | `auth_manager.py:16-17,135-159` | Medium (latent) |
| F-6 | Single-env-var kill switch: `POLARIS_AUTH_DISABLED=1` disables all API auth and the startup check. | `auth.py:104-107` | Medium (config) |
| F-7 | CORS uses wildcard methods/headers (credentials off, origins allowlisted). | `app.py:81-92` | Low |
| F-8 | Production auth surface is coherent: global JWT dependency, bcrypt logins, fail-loud startup, secrets from AWS SM. | `app.py:71-79`; `auth.py:100-167`; `carney_secret_inventory.md:17` | Low (positive) |
| F-9 | Secret hygiene in logs is good: keys never logged as values; dedicated commit-time secret scanner. | `openrouter_client.py:1563-1587`; `search_agent.py:492`; `scan_for_secrets.py:40-81` | Low (positive) |

---

## 8. Priority for the reviewer

1. **Block on F-1 (SSRF, CRITICAL).** This is the one finding that is
   remotely exploitable to credential theft on a cloud host and has **no**
   current control. Require a destination-validation choke point before any
   sign-off.
2. Address F-2/F-3/F-4 (Medium) as fast-follows: centralize injection
   sanitization, add optional PII redaction before provider egress, and add a
   checkpoint retention/cleanup policy.
3. Housekeeping: delete or quarantine the dormant `src/auth/` system (F-5),
   guard the `POLARIS_AUTH_DISABLED` flag out of production configs (F-6),
   tighten CORS (F-7).
