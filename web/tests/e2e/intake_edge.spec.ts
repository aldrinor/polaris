import { expect, test } from "@playwright/test";

test("French question → English-only message; intake API not called", async ({
  page,
}) => {
  let intakeCalls = 0;
  await page.route("**/api/intake", async (route) => {
    intakeCalls++;
    await route.fulfill({ status: 500, body: "should-not-be-called" });
  });

  await page.goto("/intake");
  await page
    .getByTestId("intake-question-input")
    .fill(
      "Quels sont les effets secondaires de la metformine chez les adultes?",
    );
  await page.getByTestId("intake-submit").click();

  await expect(page.getByTestId("intake-error")).toBeVisible();
  await expect(page.getByTestId("intake-error")).toContainText(
    "POLARIS currently supports English",
  );
  expect(intakeCalls).toBe(0);
});

test("PDF drop on /intake → banner appears, then dismisses", async ({
  page,
}) => {
  await page.goto("/intake");
  await expect(page.getByTestId("pdf-drop-ready")).toHaveAttribute(
    "data-ready",
    "1",
  );

  await page.evaluate(() => {
    const dt = new DataTransfer();
    dt.items.add(new File([], "test.pdf", { type: "application/pdf" }));
    window.dispatchEvent(
      new DragEvent("drop", {
        dataTransfer: dt,
        bubbles: true,
        cancelable: true,
      }),
    );
  });

  await expect(page.getByTestId("pdf-drop-banner")).toBeVisible();
  await page.getByTestId("pdf-drop-dismiss").click();
  await expect(page.getByTestId("pdf-drop-banner")).toBeHidden();
});
