import { expect, test } from "@playwright/test";

const DOC_A = "doc-evidence-toggle-A";
const DOC_B = "doc-evidence-toggle-B";

test("evidence toggle: 2 docs upload → both included → toggle off → only one in selection", async ({
  page,
}) => {
  let postCount = 0;
  await page.route("**/upload", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    postCount++;
    const docId = postCount === 1 ? DOC_A : DOC_B;
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({
        document_id: docId,
        filename: `f${postCount}.md`,
        bytes: 100,
        sha256: "stub",
        classification: "UNKNOWN",
        parse_status: "completed",
        chunk_preview: ["chunk a", "chunk b"],
        content: "chunk a\nchunk b",
        html: "<p>chunk a</p><p>chunk b</p>",
      }),
    });
  });

  await page.goto("/upload");

  // Drop two .md files
  await page.evaluate(() => {
    const dt = new DataTransfer();
    dt.items.add(
      new File([new Uint8Array(100)], "a.md", { type: "text/markdown" }),
    );
    dt.items.add(
      new File([new Uint8Array(100)], "b.md", { type: "text/markdown" }),
    );
    document.querySelector('[data-testid="upload-dropzone"]')!.dispatchEvent(
      new DragEvent("drop", {
        dataTransfer: dt,
        bubbles: true,
        cancelable: true,
      }),
    );
  });

  // Both completed; both included by default
  await expect(page.locator('[data-testid^="include-toggle-"]')).toHaveCount(2);
  const indicator = page.getByTestId("selected-doc-ids");
  await expect(indicator).toContainText(DOC_A);
  await expect(indicator).toContainText(DOC_B);

  // Toggle off the first
  const firstToggle = page.locator('[data-testid^="include-toggle-"]').first();
  await firstToggle.uncheck();

  // Indicator should now only contain ONE doc id
  const text = (await indicator.textContent()) ?? "";
  const idCount = (text.match(/doc-evidence-toggle-/g) ?? []).length;
  expect(idCount).toBe(1);

  // Toggle back on
  await firstToggle.check();
  await expect(indicator).toContainText(DOC_A);
  await expect(indicator).toContainText(DOC_B);
});
