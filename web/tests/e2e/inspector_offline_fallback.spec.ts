// I-cd-021 (#631) — Disconnected reviewer drops a v1.0 .tar.gz on the
// offline Inspector route. No backend running.
//
// Builds a tar.gz from tests/fixtures/signed_bundle/v1_canonical_success/
// at test-setup time and feeds it to the file input.

import { execSync } from "node:child_process";
import { existsSync, mkdirSync } from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

const FIXTURE_DIR = path.resolve(
  process.cwd(),
  "..",
  "tests/fixtures/signed_bundle/v1_canonical_success",
);
const OUT_DIR = path.resolve(
  process.cwd(),
  "..",
  ".codex-tmp",
  "i-cd-021-bundles",
);
const TAR_GZ_PATH = path.join(OUT_DIR, "v1_canonical_success.tar.gz");

test.beforeAll(() => {
  if (!existsSync(OUT_DIR)) mkdirSync(OUT_DIR, { recursive: true });
  if (!existsSync(TAR_GZ_PATH)) {
    execSync(`tar -czf "${TAR_GZ_PATH}" -C "${FIXTURE_DIR}" .`, {
      stdio: "inherit",
    });
  }
});

test("Offline Inspector parses + renders a v1.0 tar.gz bundle in-browser", async ({
  page,
}) => {
  await page.goto("/inspector/offline");
  await expect(page.getByTestId("inspector-offline-dropzone")).toBeVisible();

  await page
    .getByTestId("inspector-offline-file-input")
    .setInputFiles(TAR_GZ_PATH);

  // Wait for InspectorView to mount in place of the dropzone.
  await expect(page.getByTestId("inspector-view")).toBeVisible({
    timeout: 15_000,
  });

  // Bundle header + verified report visible.
  await expect(page.getByTestId("inspector-view")).toContainText(
    /POLARIS|bundle|run/i,
  );

  // Metadata panel surfaces all 5 fields (Codex iter-1 P1.2 fix).
  await page.getByRole("tab", { name: "Metadata" }).click();
  await expect(page.getByTestId("metadata-panel")).toBeVisible();
  await expect(page.getByTestId("metadata-polaris-version")).not.toBeEmpty();
  await expect(page.getByTestId("metadata-generator-model")).not.toBeEmpty();
  await expect(page.getByTestId("metadata-evaluator-model")).not.toBeEmpty();
  await expect(page.getByTestId("metadata-created-at")).not.toBeEmpty();
  await expect(page.getByTestId("metadata-schema-version")).toContainText(
    "1.0",
  );

  // No error card.
  await expect(page.getByTestId("inspector-offline-error")).toHaveCount(0);
});

test("Offline Inspector rejects a malformed file with a visible error", async ({
  page,
}) => {
  await page.goto("/inspector/offline");

  // Build a junk file in temp; setInputFiles accepts a path AND a payload.
  const junkPath = path.join(OUT_DIR, "garbage.tar.gz");
  if (!existsSync(junkPath)) {
    require("node:fs").writeFileSync(junkPath, "not gzip");
  }

  await page
    .getByTestId("inspector-offline-file-input")
    .setInputFiles(junkPath);

  await expect(page.getByTestId("inspector-offline-error")).toBeVisible({
    timeout: 5_000,
  });
  await expect(page.getByTestId("inspector-offline-error")).toContainText(
    /ungzip_failed|manifest|gzip/i,
  );
});
