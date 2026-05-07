import { expect, test, type Page } from "@playwright/test";

const DOC_ID = "doc-test-id-0001";

async function dropFile(page: Page) {
  await page.evaluate(() => {
    const dt = new DataTransfer();
    dt.items.add(
      new File([new Uint8Array(1024)], "queued.pdf", {
        type: "application/pdf",
      }),
    );
    document.querySelector('[data-testid="upload-dropzone"]')!.dispatchEvent(
      new DragEvent("drop", {
        dataTransfer: dt,
        bubbles: true,
        cancelable: true,
      }),
    );
  });
}

test("watches parse-status progression queued → completed", async ({
  page,
}) => {
  let getCalls = 0;
  await page.route("**/upload", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({
        document_id: DOC_ID,
        filename: "queued.pdf",
        bytes: 1024,
        sha256: "stub",
        classification: "UNKNOWN",
        parse_status: "queued",
        chunk_preview: [],
      }),
    });
  });
  await page.route(`**/upload/${DOC_ID}`, async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    getCalls++;
    const isComplete = getCalls >= 2;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        document_id: DOC_ID,
        filename: "queued.pdf",
        bytes: 1024,
        sha256: "stub",
        classification: "UNKNOWN",
        parse_status: isComplete ? "completed" : "queued",
        chunk_preview: isComplete ? ["c1", "c2", "c3"] : ["c1"],
      }),
    });
  });

  await page.goto("/upload");
  await dropFile(page);

  // Initial: parsing visible
  await expect(page.getByTestId(/upload-parse-/).first()).toContainText(
    "parsing",
  );

  // After progression: completed visible
  await expect(page.getByTestId(/upload-parse-/).first()).toContainText(
    "completed · 3 chunks",
    { timeout: 5000 },
  );

  // Polling stops after completed (cap-of-2 polls)
  await page.waitForTimeout(1500);
  expect(getCalls).toBeLessThanOrEqual(3);
});
