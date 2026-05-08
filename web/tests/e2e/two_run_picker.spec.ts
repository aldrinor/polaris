import { expect, test } from "@playwright/test";

const URL = "/sentence_hover_test/two_run_picker";

test("picks exactly 2 runs and emits compare event", async ({ page }) => {
  await page.goto(URL);
  await page.getByTestId("run-checkbox-r1").check();
  await page.getByTestId("run-checkbox-r2").check();
  await expect(page.getByTestId("selection-count")).toHaveText(
    "2 of 2 selected",
  );
  const compare = page.getByTestId("compare-button");
  await expect(compare).toBeEnabled();
  await compare.click();
  await expect(page.getByTestId("last-compared-pair")).toHaveText("r1,r2");
});

test("compare button disabled until exactly 2 selected", async ({ page }) => {
  await page.goto(URL);
  const compare = page.getByTestId("compare-button");
  await expect(compare).toBeDisabled();
  await page.getByTestId("run-checkbox-r1").check();
  await expect(compare).toBeDisabled();
  await page.getByTestId("run-checkbox-r2").check();
  await expect(compare).toBeEnabled();
});

test("cannot select more than 2", async ({ page }) => {
  await page.goto(URL);
  await page.getByTestId("run-checkbox-r1").check();
  await page.getByTestId("run-checkbox-r2").check();
  // Use click() not check() — UI refuses the state change so check() would error.
  await page.getByTestId("run-checkbox-r3").click();
  await expect(page.getByTestId("run-checkbox-r3")).not.toBeChecked();
  await expect(page.getByTestId("selection-count")).toHaveText(
    "2 of 2 selected",
  );
});

test("unchecking a row removes it from selection", async ({ page }) => {
  await page.goto(URL);
  await page.getByTestId("run-checkbox-r1").check();
  await expect(page.getByTestId("selection-count")).toHaveText(
    "1 of 2 selected",
  );
  await page.getByTestId("run-checkbox-r1").uncheck();
  await expect(page.getByTestId("selection-count")).toHaveText(
    "0 of 2 selected",
  );
});
