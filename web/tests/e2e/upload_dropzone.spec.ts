import { expect, test } from "@playwright/test";

async function mockUploadEndpoint(page: import("@playwright/test").Page) {
  let calls = 0;
  await page.route("**/upload", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    calls++;
    await new Promise((r) => setTimeout(r, 50));
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({
        document_id: `doc-${calls.toString().padStart(16, "0")}`,
        filename: "test.pdf",
        bytes: 1024,
        sha256: "stub",
        classification: "UNKNOWN",
        parse_status: "completed",
        chunk_preview: [],
      }),
    });
  });
  return () => calls;
}

async function dropFile(
  page: import("@playwright/test").Page,
  name: string,
  sizeBytes: number,
) {
  await page.evaluate(
    ({ name, sizeBytes }) => {
      const dt = new DataTransfer();
      dt.items.add(
        new File([new Uint8Array(sizeBytes)], name, {
          type: "application/pdf",
        }),
      );
      const zone = document.querySelector('[data-testid="upload-dropzone"]')!;
      zone.dispatchEvent(
        new DragEvent("drop", {
          dataTransfer: dt,
          bubbles: true,
          cancelable: true,
        }),
      );
    },
    { name, sizeBytes },
  );
}

test("drop pdf under limit → completed with document_id", async ({ page }) => {
  const getCalls = await mockUploadEndpoint(page);
  await page.goto("/upload");
  await dropFile(page, "small.pdf", 1024);
  await expect(page.getByTestId("upload-doc-id")).toBeVisible();
  expect(getCalls()).toBe(1);
});

test("drop oversize → error, no upload call", async ({ page }) => {
  const getCalls = await mockUploadEndpoint(page);
  await page.goto("/upload");
  await dropFile(page, "huge.pdf", 51 * 1024 * 1024);
  await expect(page.locator('li[data-status="error"]').first()).toBeVisible();
  await expect(page.locator('li[data-status="error"]').first()).toContainText(
    "exceeds 50MB",
  );
  await page.waitForTimeout(150);
  expect(getCalls()).toBe(0);
});

test("drop multiple files → all upload", async ({ page }) => {
  const getCalls = await mockUploadEndpoint(page);
  await page.goto("/upload");
  await page.evaluate(() => {
    const dt = new DataTransfer();
    dt.items.add(
      new File([new Uint8Array(1024)], "a.pdf", { type: "application/pdf" }),
    );
    dt.items.add(
      new File([new Uint8Array(1024)], "b.pdf", { type: "application/pdf" }),
    );
    document.querySelector('[data-testid="upload-dropzone"]')!.dispatchEvent(
      new DragEvent("drop", {
        dataTransfer: dt,
        bubbles: true,
        cancelable: true,
      }),
    );
  });
  await expect(page.locator('li[data-status="completed"]')).toHaveCount(2);
  expect(getCalls()).toBe(2);
});
