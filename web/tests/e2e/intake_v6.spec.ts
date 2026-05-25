// I-ux-001c sub-PR 3 (GH #884): e2e Playwright for the v6 intake page chrome.
//
// Asserts the spec from `.codex/I-ux-001c-3/brief.md` iter-4 APPROVE:
//   - Brand-red eyebrow + display H1 + tightened subtitle render
//   - Textarea is visible, accepts multi-line text, preserves maxLength=2000
//   - AutoDomainChip appears for a clear clinical question (≥2 anchor hits)
//   - AutoDomainChip is ABSENT for a deliberately off-domain question
//     (the loader's honest-fail returns null — no fabricated "custom" guess)
//
// PRESERVED behavior (covered by other tests, not re-asserted here):
//   - scope_decision_view render-in-place after submit (intake.spec.ts)
//   - /source_review handoff link (intake.spec.ts)
//   - intake-question-input testid (used across all 5 intake.* tests)
//   - maxLength=2000 cap (f2_walkthrough.spec.ts)
import { expect, test } from "@playwright/test";

const INTAKE_PATH = "/intake";

test.describe("I-ux-001c · Intake v6 chrome", () => {
  test("eyebrow + H1 + subtitle render with v6 copy", async ({ page }) => {
    await page.goto(INTAKE_PATH, { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("intake-page")).toBeVisible();
    await expect(page.getByTestId("intake-eyebrow")).toContainText(
      /ASK.*POLARIS CLINICAL RESEARCH/i,
    );
    await expect(page.getByTestId("intake-h1")).toContainText(
      "Ask the research question",
    );
    await expect(page.getByTestId("intake-subtitle")).toContainText(
      /confirms your question is answerable from clinical evidence/i,
    );
  });

  test("textarea is visible, accepts multi-line text, preserves maxLength=2000", async ({
    page,
  }) => {
    await page.goto(INTAKE_PATH, { waitUntil: "domcontentloaded" });
    const textarea = page.getByTestId("intake-question-input");
    await expect(textarea).toBeVisible();
    await expect(textarea).toHaveAttribute("maxlength", "2000");
    // Multi-line text is accepted (the v6 Textarea wraps; Input would not)
    await textarea.fill("First line of the question.\nSecond line continues.");
    const value = await textarea.inputValue();
    expect(value).toContain("\n");
  });

  test("AutoDomainChip appears for a clear clinical question", async ({
    page,
  }) => {
    await page.goto(INTAKE_PATH, { waitUntil: "domcontentloaded" });
    const textarea = page.getByTestId("intake-question-input");
    // Clinical anchors: 'RCT' + 'efficacy' + 'patients' = 3 hits ≥ 2
    await textarea.fill(
      "What does the most recent RCT show on efficacy of metformin in older patients?",
    );
    const chip = page.getByTestId("auto-domain-chip");
    await expect(chip).toBeVisible();
    await expect(chip).toHaveAttribute("data-domain", "clinical");
    await expect(chip).toContainText(/Clinical research/i);
  });

  test("AutoDomainChip is ABSENT for an off-domain question (honest-fail null)", async ({
    page,
  }) => {
    await page.goto(INTAKE_PATH, { waitUntil: "domcontentloaded" });
    const textarea = page.getByTestId("intake-question-input");
    // No domain anchors — purely generic question
    await textarea.fill("What is the meaning of life?");
    await expect(page.getByTestId("auto-domain-chip")).toHaveCount(0);
  });
});
