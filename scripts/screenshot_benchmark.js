// Slice 5 benchmark page screenshot — captures /benchmark with real
// scoreboard data, complementing slices 1-3 already in
// screenshot_walkthrough.js.
const { chromium } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

const OUT_DIR = path.resolve(__dirname, '../.codex/walkthrough_screenshots_latest');
fs.mkdirSync(OUT_DIR, { recursive: true });

const BASE = process.env.SCREENSHOT_BASE_URL || 'http://127.0.0.1:3737';

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1200 } });
  const page = await ctx.newPage();
  page.on('response', resp => {
    if (resp.url().includes('/api/')) console.log(`[api]`, resp.status(), resp.url());
  });

  console.log('1. /benchmark — load list');
  await page.goto(`${BASE}/benchmark`, { waitUntil: 'networkidle' });
  await page.screenshot({
    path: path.join(OUT_DIR, '08_benchmark_list.png'),
    fullPage: true,
  });

  // Click the seeded benchmark button (testid pattern: benchmark-link-<id>)
  const linkBtn = page.getByTestId('benchmark-link-clinical_n10_demo');
  if (await linkBtn.isVisible().catch(() => false)) {
    console.log('2. /benchmark — click clinical_n10_demo');
    await linkBtn.click();
    await page.getByTestId('benchmark-board').waitFor({
      state: 'visible',
      timeout: 15000,
    }).catch(() => null);
    await page.waitForLoadState('networkidle');
    await page.screenshot({
      path: path.join(OUT_DIR, '09_benchmark_scoreboard.png'),
      fullPage: true,
    });
  } else {
    console.log('2. clinical_n10_demo button not visible; skipping click');
  }

  await browser.close();
  console.log(`done — screenshots in ${OUT_DIR}`);
})().catch(e => {
  console.error('FAILED:', e.message);
  process.exit(1);
});
