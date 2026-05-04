# POLARIS Tracer Demo Runbook

**Audience:** non-developer operator running the Sep 6 tracer demo for Carney's office.

This runbook walks the demo end-to-end through all five slices in fresh-browser
order: scope discovery → retrieval → generation → audit bundle → BEAT-BOTH benchmark.

---

## 0. Prerequisites

| Requirement | Where it comes from |
|---|---|
| `OPENROUTER_API_KEY` | OpenRouter account, $5+ balance |
| `SERPER_API_KEY` | serper.dev account, free tier OK |
| `POLARIS_GPG_KEY_ID` | local GPG keypair (`gpg --gen-key`); export the key id |
| `POLARIS_BENCHMARK_RESULTS_DIR` | absolute path to seeded benchmark dir (see step 3) |
| Python 3.11+ + `pip install -r requirements.txt` | repo root |
| Node 20 + `npm install --prefix web` | repo root |

Place all four env vars in `.env` at repo root. The FastAPI app loads `.env`
via `python-dotenv` at `create_app()` time.

---

## 1. Boot the backend

```bash
python -c "from dotenv import load_dotenv; load_dotenv(); import uvicorn; uvicorn.run('polaris_v6.api.app:app', host='127.0.0.1', port=8000, log_level='info')"
```

Health check:

```bash
curl http://127.0.0.1:8000/api/intake/health
curl http://127.0.0.1:8000/api/retrieval/health
curl http://127.0.0.1:8000/api/generation/health
curl http://127.0.0.1:8000/api/audit-bundle/health
curl http://127.0.0.1:8000/api/benchmark/health
```

Each route returns `200` with a JSON body whose `slice` field names the slice
and whose backend-specific fields confirm the real implementation is wired (not
the 503 sentinel).

---

## 2. Boot the frontend (production build)

Dev mode (`next dev`) breaks Playwright via HMR websocket. Use the production
build for the demo:

```bash
cd web
npx next build
npx next start -p 3000
```

Open `http://localhost:3000` in a fresh browser. You should land on the home
page with the **Tracer demo walkthrough** section listing four cards:

1. Step 1 — Scope discovery + ambiguity → `/intake`
2. Step 2 — Tiered retrieval → `/retrieval`
3. Step 3 — Generator + strict-verify → `/generation`
4. Step 4 — BEAT-BOTH benchmark → `/benchmark`

Click them in order.

---

## 3. Seed the benchmark artifact (one-time)

The `/benchmark` page reads from `POLARIS_BENCHMARK_RESULTS_DIR`. Seed it once
with a reproducible scoreboard so the page shows real data on first visit:

```bash
python scripts/seed_demo_benchmark.py \
    --output outputs/demo_benchmark/clinical_n10_demo
```

This runs `scripts/run_benchmark.py --skip-polaris` against
`config/benchmark/clinical_n10.json` and writes `scoreboard.json`,
`summary.md`, `report.html` to the output directory. It does NOT call
OpenRouter or Serper — it scores empty external outputs to produce a baseline
artifact that proves the UI/CLI/scoreboard chain works end-to-end.

For a real BEAT-BOTH demo (one query, billed), drop `--skip-polaris`:

```bash
python scripts/run_benchmark.py \
    --config config/benchmark/clinical_n10.json \
    --polaris-url http://127.0.0.1:8000 \
    --output outputs/demo_benchmark/clinical_n10_real
```

Set `POLARIS_BENCHMARK_RESULTS_DIR=$(pwd)/outputs/demo_benchmark` and reboot
the backend so `/benchmark` picks up the new directory.

---

## 4. Walkthrough script

| Step | Click | Expected outcome |
|---|---|---|
| 1 | Home → "Open Scope discovery + ambiguity" | `/intake` page loads |
| 2 | Type "Is high-dose aspirin effective for migraine in adults?" → submit | scope decision card shows `in_scope`, scope_class=`clinical_efficacy` |
| 3 | Top nav → Retrieval (or back home → Step 2) | `/retrieval` page loads |
| 4 | Submit same question (PICO axes auto-filled) | corpus-adequacy verdict + tier mix card |
| 5 | Top nav → Generation | `/generation` page loads |
| 6 | Click "Generate verified report" | sections render with provenance tokens; pipeline_verdict=`success` |
| 7 | Click "Download audit bundle" | `.tar.gz` + `.tar.gz.asc` GPG signature |
| 8 | Verify externally: `gpg --verify <bundle>.tar.gz.asc <bundle>.tar.gz` | "Good signature from POLARIS" |
| 9 | Top nav → Benchmark | `/benchmark` page loads with seeded scoreboard |
| 10 | Click "View report" on `clinical_n10_demo` | HTML scoreboard renders with 7 dimensions per system |

If any step fails, the runbook does not paper over — `LAW II — No Fake Working`
applies. Capture the error, halt, and surface to user.

---

## 5. Reproducing screenshots for the deck

```bash
node scripts/screenshot_walkthrough.js
```

Outputs to `.codex/walkthrough_screenshots_latest/`. Last reproducible run
captured 5 PNGs against `deepseek-v4-pro` with 4/4 verified clinical sentences.

---

## 6. Halt conditions during demo

Per CLAUDE.md §6.2 anti-degradation, halt the demo and surface to user
immediately on:

- Any `503 benchmark_results_unavailable` (env var missing)
- Any `abort_no_verified_sections` (strict-verify rejected all sentences)
- Any GPG signature verification failure
- Any latency > 30s on a single route (BEAT-BOTH thresholds: 3s intake, 30s
  retrieval, 600s generation)
- Any LLM reasoning leak in generated prose (catch via grep for "We need to
  write" / "Let me examine")

The demo is a tracer, not a stage trick. If it doesn't work clean, say so.
