import { expect, test } from "@playwright/test";

const DOC_ID = "doc-preview-id-0001";

test("open preview → click chunk → mark wraps text in iframe", async ({
  page,
}) => {
  await page.route("**/upload", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({
        document_id: DOC_ID,
        filename: "doc.md",
        bytes: 100,
        sha256: "stub",
        classification: "UNKNOWN",
        parse_status: "completed",
        chunk_preview: ["alpha sentence here", "beta sentence here"],
        content: "alpha sentence here\nbeta sentence here",
        html: "<p>alpha sentence here</p><p>beta sentence here</p>",
      }),
    });
  });
  await page.route(`**/upload/${DOC_ID}`, async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        document_id: DOC_ID,
        filename: "doc.md",
        bytes: 100,
        sha256: "stub",
        classification: "UNKNOWN",
        parse_status: "completed",
        chunk_preview: ["alpha sentence here", "beta sentence here"],
        content: "alpha sentence here\nbeta sentence here",
        html: "<p>alpha sentence here</p><p>beta sentence here</p>",
      }),
    });
  });

  await page.goto("/upload");
  await page.evaluate(() => {
    const dt = new DataTransfer();
    dt.items.add(
      new File([new Uint8Array(100)], "doc.md", { type: "text/markdown" }),
    );
    document.querySelector('[data-testid="upload-dropzone"]')!.dispatchEvent(
      new DragEvent("drop", {
        dataTransfer: dt,
        bubbles: true,
        cancelable: true,
      }),
    );
  });

  // Open preview button visible
  const openBtn = page.locator('[data-testid^="open-preview-"]').first();
  await expect(openBtn).toBeVisible();
  await openBtn.click();

  // Preview iframe rendered
  const iframe = page.locator('[data-testid="preview-iframe"]');
  await expect(iframe).toBeVisible();

  // Click chunk-1 (the "beta" chunk)
  await page.getByTestId("chunk-1").click();

  // Inspect iframe contentDocument for the <mark> element
  const markText = await page.evaluate(() => {
    const iframe = document.querySelector(
      '[data-testid="preview-iframe"]',
    ) as HTMLIFrameElement | null;
    const mark = iframe?.contentDocument?.querySelector(
      "mark[data-polaris-mark]",
    );
    return mark?.textContent ?? null;
  });

  expect(markText).toBe("beta sentence here");
});
