import { expect, test } from "@playwright/test";

test("BPEI: type → submit → modal → 3 candidates → pick → label flows to parent", async ({
  page,
}) => {
  await page.route("**/api/intake", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        error: false,
        decision: {
          status: "in_scope",
          scope_class: "clinical_efficacy",
          ambiguity_axes: [],
          clarifications_needed: [],
          provenance: {},
          decision_id: "test-decision-id",
          decided_at_utc: new Date().toISOString(),
          latency_ms: 12,
          needs_disambiguation: true,
          candidate_snippets: [
            { text: "BPEI syndrome notes", embedding: [1, 0] },
            { text: "BPEI institute notes", embedding: [0, 1] },
            { text: "BPEI chemical notes", embedding: [-1, 0] },
          ],
        },
        server_time_utc: new Date().toISOString(),
      }),
    });
  });

  await page.route("**/api/disambiguation", async (route) => {
    const body = JSON.parse(route.request().postData() ?? "{}");
    expect(Array.isArray(body.candidates)).toBe(true);
    expect(body.candidates).toHaveLength(3);
    await new Promise((resolve) => setTimeout(resolve, 100));
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        is_ambiguous: true,
        num_clusters: 3,
        clusters: [
          {
            cluster_id: 0,
            label: "syndrome",
            sample_snippets: ["BPEI syndrome..."],
          },
          {
            cluster_id: 1,
            label: "institute",
            sample_snippets: ["BPEI institute..."],
          },
          {
            cluster_id: 2,
            label: "chemical",
            sample_snippets: ["BPEI chemical..."],
          },
        ],
        server_time_utc: new Date().toISOString(),
      }),
    });
  });

  await page.goto("/intake");
  await page.getByTestId("intake-question-input").fill("BPEI");

  const t_submit = Date.now();
  await page.getByTestId("intake-submit").click();
  await expect(page.getByTestId("disambiguation-cluster-0")).toBeVisible();
  const t_modal = Date.now();

  expect(t_modal - t_submit).toBeLessThan(500);

  const cards = page.locator('[data-testid^="disambiguation-cluster-"]');
  await expect(cards).toHaveCount(3);

  await page.getByTestId("disambiguation-cluster-1").click();
  await expect(page.getByTestId("disambig-picked-label")).toHaveText(
    "institute",
  );
  await expect(page.getByTestId("disambiguation-cluster-0")).toBeHidden();
});
