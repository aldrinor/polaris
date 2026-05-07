import { expect, test } from "@playwright/test";

test("create + edit + save evidence contract", async ({ page }) => {
  await page.goto("/contracts");
  await page.getByTestId("ce-question").fill("Does aspirin reduce headache?");
  await page.getByTestId("ce-by").fill("operator-1");
  await page.getByTestId("ce-ent-name-0").fill("aspirin");
  await page.getByTestId("ce-claim-stmt-0").fill("aspirin reduces headache");
  await page.getByTestId("ce-claim-ents-0").fill("aspirin");
  const dl_promise = page.waitForEvent("download", { timeout: 10_000 });
  await page.getByTestId("contract-submit").click();
  await expect(page.getByTestId("contract-saved")).toBeVisible({
    timeout: 10_000,
  });
  const download = await dl_promise;
  expect(download.suggestedFilename()).toMatch(/^contract_[a-f0-9]{8}\.json$/);
});
