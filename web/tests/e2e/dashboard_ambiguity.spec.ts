import { expect, test } from "@playwright/test";

// I-rdy-009 (#505): F2 ambiguity detection in the main create-run flow.
// An ambiguous clinical question-only query must open the disambiguation
// modal; a failed, stale, or in-flight-superseded ambiguity scan must
// hard-block "Start run".

const ACCEPTED_SCOPE = {
  verdict: "accepted",
  rationale: "In scope for the clinical template.",
  refusals: [],
  intended_source_tiers: ["T1"],
};

/** Mock GET /templates (mount) and POST /scope/check (Check scope). */
async function mockBaseRoutes(page: import("@playwright/test").Page) {
  await page.route("**/templates", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });
  await page.route("**/scope/check", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(ACCEPTED_SCOPE),
    });
  });
}

test("ambiguous clinical question opens the disambiguation modal", async ({
  page,
}) => {
  await mockBaseRoutes(page);
  await page.route("**/ambiguity/scan", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        is_ambiguous: true,
        clusters: [
          {
            cluster_id: 0,
            representative_text:
              "BPEI is the blood pressure end-inspiration index in cardiology.",
            member_source_ids: ["m1"],
          },
          {
            cluster_id: 1,
            representative_text:
              "BPEI is a bank-protected enterprise investment instrument.",
            member_source_ids: ["f1"],
          },
        ],
        fallback_used: true,
      }),
    });
  });

  await page.goto("/dashboard");
  await page.locator("#question").fill("What is BPEI?");
  await page.getByRole("button", { name: "Check scope" }).click();

  // The disambiguation modal opens on its own — no extra click needed.
  await expect(page.getByTestId("disambiguation-cluster-0")).toBeVisible();
  await expect(
    page.locator('[data-testid^="disambiguation-cluster-"]'),
  ).toHaveCount(2);
});

test("a 503 ambiguity scan hard-blocks Start run", async ({ page }) => {
  await mockBaseRoutes(page);
  await page.route("**/ambiguity/scan", async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        detail: {
          error: true,
          code: "candidate_fetch_unavailable",
          message: "SERPER_API_KEY is unset.",
        },
      }),
    });
  });
  let runs_called = false;
  await page.route("**/runs", async (route) => {
    runs_called = true;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ run_id: "must-not-happen" }),
    });
  });

  await page.goto("/dashboard");
  await page.locator("#question").fill("What is BPEI in cardiology?");
  await page.getByRole("button", { name: "Check scope" }).click();
  // The failed scan surfaces an error.
  await expect(page.getByRole("alert")).toBeVisible();

  await page.getByRole("button", { name: "Start run" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Ambiguity check is unavailable",
  );
  expect(runs_called).toBe(false);
  expect(page.url()).toContain("/dashboard");
});

test("editing the question after a scan re-blocks Start run (stale gate)", async ({
  page,
}) => {
  await mockBaseRoutes(page);
  await page.route("**/ambiguity/scan", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        is_ambiguous: false,
        clusters: [],
        fallback_used: true,
      }),
    });
  });
  let runs_called = false;
  await page.route("**/runs", async (route) => {
    runs_called = true;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ run_id: "must-not-happen" }),
    });
  });

  await page.goto("/dashboard");
  await page.locator("#question").fill("Does aspirin reduce headaches in adults?");
  await page.getByRole("button", { name: "Check scope" }).click();
  // A successful unambiguous scan — the scope decision card appears.
  await expect(page.getByText("Scope discovery")).toBeVisible();

  // Edit the question: this invalidates the prior scan's "ok" gate.
  await page.locator("#question").fill("Does ibuprofen reduce fever in children?");
  await page.getByRole("button", { name: "Start run" }).click();
  await expect(page.getByRole("alert")).toContainText("Run Check scope first");
  expect(runs_called).toBe(false);
  expect(page.url()).toContain("/dashboard");
});

test("editing the question during an in-flight scan re-blocks Start run", async ({
  page,
}) => {
  await mockBaseRoutes(page);
  await page.route("**/ambiguity/scan", async (route) => {
    // Slow scan — opens a window to edit the question while it is in flight.
    await new Promise((resolve) => setTimeout(resolve, 600));
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        is_ambiguous: false,
        clusters: [],
        fallback_used: true,
      }),
    });
  });
  let runs_called = false;
  await page.route("**/runs", async (route) => {
    runs_called = true;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ run_id: "must-not-happen" }),
    });
  });

  await page.goto("/dashboard");
  await page.locator("#question").fill("Does aspirin reduce headaches in adults?");
  // Start the scan, then edit the question while it is still in flight —
  // the resolving scan must NOT set the gate "ok" for the edited question.
  await page.getByRole("button", { name: "Check scope" }).click();
  await page.locator("#question").fill("Does ibuprofen reduce fever in children?");
  // Wait for the (now stale) scan to resolve — Check scope re-enables.
  await expect(
    page.getByRole("button", { name: "Check scope" }),
  ).toBeEnabled();

  await page.getByRole("button", { name: "Start run" }).click();
  await expect(page.getByRole("alert")).toContainText("Run Check scope first");
  expect(runs_called).toBe(false);
  expect(page.url()).toContain("/dashboard");
});
