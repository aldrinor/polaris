// Headless browser walkthrough — captures screenshots at each stage of
// the BPEI chain. Reproducible end-to-end fitness check.
//
// Prerequisites:
//   1. Backend up:   PYTHONPATH=src python -c "from dotenv import load_dotenv; load_dotenv(); import uvicorn; uvicorn.run('polaris_v6.api.app:app', host='127.0.0.1', port=8000)"
//   2. Frontend up:  cd web && NEXT_PUBLIC_BACKEND_URL=http://127.0.0.1:8000 npx next build && npx next start -p 3738
//   3. Run from web/: cd web && node ../scripts/screenshot_walkthrough.js
//
// Outputs PNGs to .codex/walkthrough_screenshots_<date>/. Each run captures:
//   01 intake_empty       /intake page on first load
//   02 intake_typed       question filled in
//   03 intake_result      ScopeDecision rendered
//   05 retrieval_result   real Serper+SemanticScholar EvidencePool
//   07 generation_result  real OpenRouter LLM VerifiedReport
//
// On generation, expect ~3-5 minutes (4 LLM calls × ~60s with parallelism).
// Sentences are strict-verified; only those with valid provenance survive.

const { chromium } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

const OUT_DIR = path.resolve(__dirname, '../.codex/walkthrough_screenshots_latest');
fs.mkdirSync(OUT_DIR, { recursive: true });

const BASE = process.env.SCREENSHOT_BASE_URL || 'http://127.0.0.1:3738';
const QUESTION = process.env.WALKTHROUGH_QUESTION
  || 'Is aspirin effective for headache in adults?';

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();

  page.on('console', msg => {
    if (msg.type() === 'error') console.log(`[browser error]`, msg.text());
  });
  page.on('requestfailed', req => {
    console.log(`[network failed]`, req.url(), req.failure()?.errorText);
  });
  page.on('response', resp => {
    if (resp.url().includes('/api/')) {
      console.log(`[api]`, resp.status(), resp.url());
    }
  });

  console.log('1. /intake — load + fill + submit');
  await page.goto(`${BASE}/intake`, { waitUntil: 'networkidle' });
  await page.screenshot({ path: path.join(OUT_DIR, '01_intake_empty.png') });
  await page.getByTestId('intake-question-input').fill(QUESTION);
  await page.screenshot({ path: path.join(OUT_DIR, '02_intake_typed.png') });
  await page.getByTestId('intake-submit').click();
  await Promise.race([
    page.getByTestId('scope-decision-view').waitFor({ state: 'visible', timeout: 30000 }),
    page.getByTestId('intake-error').waitFor({ state: 'visible', timeout: 30000 }),
  ]);
  await page.screenshot({ path: path.join(OUT_DIR, '03_intake_result.png') });

  console.log('2. /retrieval — load + submit (real Serper+SemanticScholar)');
  await page.goto(`${BASE}/retrieval`, { waitUntil: 'networkidle' });
  await page.getByTestId('retrieval-question-input').fill(QUESTION);
  await page.getByTestId('retrieval-submit').click();
  await Promise.race([
    page.getByTestId('corpus-brief').waitFor({ state: 'visible', timeout: 60000 }),
    page.getByTestId('retrieval-error').waitFor({ state: 'visible', timeout: 60000 }),
  ]);
  await page.screenshot({
    path: path.join(OUT_DIR, '05_retrieval_result.png'),
    fullPage: true,
  });

  console.log('3. /generation — load + submit (real OpenRouter, ~3-5 min)');
  await page.goto(`${BASE}/generation`, { waitUntil: 'networkidle' });
  await page.getByTestId('generation-question-input').fill(QUESTION);
  await page.getByTestId('generation-submit').click();
  await Promise.race([
    page.getByTestId('verified-report-view').waitFor({ state: 'visible', timeout: 600000 }),
    page.getByTestId('generation-error').waitFor({ state: 'visible', timeout: 600000 }),
  ]);
  await page.screenshot({
    path: path.join(OUT_DIR, '07_generation_result.png'),
    fullPage: true,
  });

  await browser.close();
  console.log(`done — screenshots in ${OUT_DIR}`);
})().catch(e => {
  console.error('FAILED:', e.message);
  process.exit(1);
});
