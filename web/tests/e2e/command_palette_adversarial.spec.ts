import { expect, test } from "@playwright/test";

/**
 * I-f1-004 — Adversarial corpus: zero false-positive + correct positives.
 *
 * 22-input corpus (15 zero_match + 7 exact_one_match) verifying the
 * command palette scoring (I-f1-002 + I-f1-003) does NOT produce
 * false-positive template suggestions and DOES produce the correct
 * single suggestion for each known-positive input.
 *
 * Scope: test-only. If scoring needs fixing, that's a follow-up Issue.
 *
 * Iter-1 + iter-2 Codex empirical scoring runs verified each corpus
 * input against the current `score_template` function before this test
 * shipped. The "the" stopword (matched 5 templates via sample_question
 * substring) was replaced with "weather forecast" in iter-2.
 */

const SUGGEST_BUDGET_MS = 350;

const ZERO_MATCH_INPUTS: string[] = [
  "BPEI",
  "CDS",
  "NEC",
  "MS",
  "RAG",
  "SOTA",
  "xyz123abc",
  "🚀",
  "weather forecast",
  "quantum entanglement",
  "pizza recipe",
  "   ",
  "'); DROP TABLE templates;--",
  '"><script>alert(1)</script>',
  "‮لا",
];

const EXACT_ONE_MATCH_INPUTS: { input: string; expected_id: string }[] = [
  { input: "tirzepatide", expected_id: "clinical" },
  { input: "ozempic", expected_id: "clinical" },
  { input: "clinical drug audit", expected_id: "clinical" },
  { input: "public policy", expected_id: "policy" },
  { input: "technology assessment", expected_id: "tech" },
  { input: "due diligence", expected_id: "due_diligence" },
  { input: "custom research", expected_id: "custom" },
];

test.describe("Command palette adversarial corpus — I-f1-004", () => {
  for (const input of ZERO_MATCH_INPUTS) {
    test(`zero_match: ${JSON.stringify(input)} yields 0 items`, async ({
      page,
    }) => {
      await page.goto("/", { waitUntil: "networkidle" });
      await expect(page.getByTestId("header-sign-in-link")).toBeVisible();
      await page.keyboard.press("Control+k");
      await expect(page.getByTestId("command-palette")).toBeVisible();

      const items = page.locator('[data-testid^="palette-item-"]');
      await page.getByTestId("command-palette-input").fill(input);
      await expect(items).toHaveCount(0, { timeout: SUGGEST_BUDGET_MS });
    });
  }

  for (const { input, expected_id } of EXACT_ONE_MATCH_INPUTS) {
    test(`exact_one_match: ${JSON.stringify(input)} → ${expected_id}`, async ({
      page,
    }) => {
      await page.goto("/", { waitUntil: "networkidle" });
      await expect(page.getByTestId("header-sign-in-link")).toBeVisible();
      await page.keyboard.press("Control+k");
      await expect(page.getByTestId("command-palette")).toBeVisible();

      const items = page.locator('[data-testid^="palette-item-"]');
      await page.getByTestId("command-palette-input").fill(input);
      await expect(items).toHaveCount(1, { timeout: SUGGEST_BUDGET_MS });
      await expect(
        page.getByTestId(`palette-item-${expected_id}`),
      ).toBeVisible();
    });
  }
});
