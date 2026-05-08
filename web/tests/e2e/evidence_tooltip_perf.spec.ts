import { expect, test } from "@playwright/test";

test("100x EvidenceTooltip mount cycles all render under 100ms", async ({
  page,
}) => {
  await page.goto("/sentence_hover_test/perf");
  await page.getByTestId("run-perf").click();
  await expect(page.getByTestId("perf-results")).toHaveAttribute(
    "data-iter",
    "100",
    { timeout: 30_000 },
  );
  const raw = await page
    .getByTestId("perf-results")
    .getAttribute("data-timings");
  expect(raw).not.toBeNull();
  const timings = JSON.parse(raw ?? "[]") as number[];
  expect(timings.length).toBe(100);
  const offending = timings
    .map((t, i) => ({ t, i }))
    .filter(({ t }) => !(Number.isFinite(t) && t >= 0 && t < 100));
  if (offending.length > 0) {
    console.error("offending timings (i:t):", offending);
  }
  expect(offending).toEqual([]);
});
