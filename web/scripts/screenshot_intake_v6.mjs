import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const out = "./p2shots/I-ux-001c-sub-pr-3";
mkdirSync(out, { recursive: true });

const url = process.env.INTAKE_URL ?? "http://127.0.0.1:3739/intake";

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();

await page.goto(url, { waitUntil: "networkidle" });
await page.screenshot({ path: `${out}/intake_desktop_1440.png`, fullPage: true });

const textarea = page.getByTestId("intake-question-input");
await textarea.click();
await page.keyboard.type("What does the most recent RCT show on efficacy of metformin in older patients?", { delay: 5 });

// Verify chip mounts
try {
  await page.waitForSelector('[data-testid="auto-domain-chip"]', { state: "visible", timeout: 5000 });
  console.log("CHIP visible");
} catch (e) {
  console.log("CHIP NOT VISIBLE — dumping page state");
  const html = await page.evaluate(() => document.body.innerHTML.substring(0, 4000));
  console.log("BODY HTML 4k:", html.length, "chars");
  console.log("textarea value:", await textarea.inputValue());
}

await page.screenshot({ path: `${out}/intake_desktop_chip_clinical.png`, fullPage: true });

await page.setViewportSize({ width: 768, height: 1024 });
await page.goto(url, { waitUntil: "networkidle" });
await page.screenshot({ path: `${out}/intake_tablet_768.png`, fullPage: true });

await page.setViewportSize({ width: 390, height: 844 });
await page.goto(url, { waitUntil: "networkidle" });
await page.screenshot({ path: `${out}/intake_mobile_390.png`, fullPage: true });

await browser.close();
console.log("OK", out);
