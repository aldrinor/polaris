import { expect, test, type Page } from "@playwright/test";

const ISO = new Date().toISOString();
const D = {
  status: "in_scope",
  scope_class: "clinical_efficacy",
  ambiguity_axes: [],
  clarifications_needed: [],
  needs_disambiguation: false,
  is_ambiguous: false,
  provenance: {},
  decision_id: "d1",
  decided_at_utc: ISO,
  latency_ms: 1,
};
const P = {
  pool_id: "p1",
  decision_id: "d1",
  sources: [],
  adequacy: { is_adequate: true, failure_reason: null },
  queries_executed: ["q"],
  retrieval_started_at_utc: ISO,
  retrieval_finished_at_utc: ISO,
  latency_ms: 1,
  cost_usd: 0,
};
const R = {
  report_id: "r1",
  pool_id: "p1",
  decision_id: "d1",
  sections: [],
  overall_verify_pass_rate: 1,
  pipeline_verdict: "success",
  generator_model: "test-gen",
  verifier_pass_threshold: 0.4,
  started_at_utc: ISO,
  finished_at_utc: ISO,
  latency_ms: 1,
  cost_usd: 0,
};
const PREVIEW = {
  preview_bundle_id: "abcdef0123456789-aaaa",
  generator_model: "test-gen",
  polaris_version: "v6.2.0-test",
  file_count: 4,
  total_bytes: 12345,
  content_type_breakdown: {
    scope_decision: { count: 1, bytes: 1024 },
    evidence_pool: { count: 1, bytes: 2048 },
    verified_report: { count: 1, bytes: 4096 },
    source_snapshot: { count: 0, bytes: 0 },
    metadata: { count: 1, bytes: 5177 },
  },
};

async function fulfill(page: Page, path: string, body: object, status = 200) {
  await page.route(`**${path}`, async (route) => {
    const method = route.request().method();
    if (method === "OPTIONS") {
      await route.fulfill({
        status: 204,
        headers: {
          "access-control-allow-origin": "*",
          "access-control-allow-methods": "POST,OPTIONS",
          "access-control-allow-headers": "content-type",
        },
      });
      return;
    }
    if (method !== "POST") return route.continue();
    await route.fulfill({
      status,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
}

async function stub_chain(page: Page) {
  await fulfill(page, "/api/intake", {
    error: false,
    decision: D,
    server_time_utc: ISO,
  });
  await fulfill(page, "/api/retrieval", {
    error: false,
    pool: P,
    server_time_utc: ISO,
  });
  await fulfill(page, "/api/generation", {
    error: false,
    report: R,
    server_time_utc: ISO,
  });
}

test("bundle preview renders manifest summary on success", async ({ page }) => {
  await stub_chain(page);
  await fulfill(page, "/api/audit-bundle/preview", PREVIEW);
  await page.goto("/generation");
  await page.getByTestId("generation-question-input").fill("aspirin headache?");
  await page.getByTestId("generation-submit").click();
  await expect(page.getByTestId("bundle-preview")).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByTestId("bundle-preview-id")).toContainText(
    "Preview ID:",
  );
  await expect(page.getByTestId("bundle-preview-file-count")).toContainText(
    "4 files",
  );
  for (const ct of [
    "scope_decision",
    "evidence_pool",
    "verified_report",
    "source_snapshot",
    "metadata",
  ]) {
    await expect(page.getByTestId(`bundle-preview-row-${ct}`)).toBeVisible();
  }
});

test("bundle preview surfaces structured error code on failure", async ({
  page,
}) => {
  await stub_chain(page);
  await fulfill(
    page,
    "/api/audit-bundle/preview",
    {
      detail: {
        error: true,
        code: "fk_chain_mismatch",
        message: "test fk mismatch",
        report_id: "r1",
      },
    },
    400,
  );
  await page.goto("/generation");
  await page.getByTestId("generation-question-input").fill("aspirin headache?");
  await page.getByTestId("generation-submit").click();
  await expect(page.getByTestId("bundle-preview-error")).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByTestId("bundle-preview-error-code")).toHaveText(
    "fk_chain_mismatch",
  );
});
