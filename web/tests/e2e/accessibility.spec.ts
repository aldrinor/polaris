import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

/**
 * Phase 2C.5 — WCAG 2.2-AA accessibility audit.
 *
 * For each user-facing route we run axe-core with the WCAG 2A + 2AA + 2.1AA
 * + 2.2AA + best-practice rule sets and assert zero violations. Any new
 * violation should fail CI rather than silently regress accessibility.
 *
 * Failure mode is intentionally LOUD — if axe surfaces a violation we
 * print the rule id, impact, and the affected node selectors so the fix
 * is one click away.
 */

const WCAG_TAGS = [
  "wcag2a",
  "wcag2aa",
  "wcag21a",
  "wcag21aa",
  "wcag22aa",
  "best-practice",
];

async function expectNoA11yViolations(page: import("@playwright/test").Page) {
  const results = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze();

  if (results.violations.length > 0) {
    const summary = results.violations
      .map(
        (v) =>
          `\n  - [${v.impact}] ${v.id}: ${v.description}\n    nodes: ${v.nodes
            .map(
              (n) =>
                n.target.join(" ") +
                (n.failureSummary
                  ? ` — ${n.failureSummary.replace(/\n/g, " ")}`
                  : ""),
            )
            .join("\n           ")}`,
      )
      .join("");
    throw new Error(
      `axe-core found ${results.violations.length} WCAG-AA violation(s):${summary}`,
    );
  }
}

test.describe("WCAG-AA — research dashboard", () => {
  test("/dashboard initial render is WCAG-AA clean", async ({ page }) => {
    await page.goto("/dashboard", { waitUntil: "networkidle" });
    await expectNoA11yViolations(page);
  });

  test("/dashboard after scope rejection is WCAG-AA clean", async ({
    page,
  }) => {
    await page.goto("/dashboard", { waitUntil: "networkidle" });
    await page.fill("#question", "Should I take ozempic for my diabetes?");
    await page.getByRole("button", { name: /Check scope/ }).click();
    await expect(page.getByText(/Rejected/i)).toBeVisible({ timeout: 8_000 });
    await expectNoA11yViolations(page);
  });
});

// I-cd-013a (GH#609): legacy AuditIR Inspector — migrated by I-cd-013b (#669).
test.describe.skip("WCAG-AA — Inspector golden_clinical_001", () => {
  test("Executive summary tab (default) is WCAG-AA clean", async ({ page }) => {
    await page.goto("/inspector/golden_clinical_001", {
      waitUntil: "networkidle",
    });
    await expectNoA11yViolations(page);
  });

  test("Verified sentences tab is WCAG-AA clean", async ({ page }) => {
    await page.goto("/inspector/golden_clinical_001", {
      waitUntil: "networkidle",
    });
    await page
      .getByRole("button", { name: /Verified sentences/ })
      .first()
      .click();
    await expectNoA11yViolations(page);
  });

  test("Charts tab is WCAG-AA clean", async ({ page }) => {
    await page.goto("/inspector/golden_climate_005", {
      waitUntil: "networkidle",
    });
    await page
      .getByRole("button", { name: /^Charts/ })
      .first()
      .click();
    await page.waitForSelector(".polaris-vega-chart svg", { timeout: 10_000 });
    await expectNoA11yViolations(page);
  });
});

// I-cd-013a (GH#609): legacy AuditIR Inspector — migrated by I-cd-013b (#669).
test.describe.skip("WCAG-AA — Inspector golden_housing_002 (contradictions)", () => {
  test("Contradictions tab is WCAG-AA clean", async ({ page }) => {
    await page.goto("/inspector/golden_housing_002", {
      waitUntil: "networkidle",
    });
    await page
      .getByRole("button", { name: /Contradictions/ })
      .first()
      .click();
    await expectNoA11yViolations(page);
  });
});

test.describe("WCAG-AA — dashboard upload list with files", () => {
  test('Upload list "remove" button is WCAG-AA clean (real upload)', async ({
    page,
  }) => {
    // Closes cycle-3 audit P1.1 — F-7 fixed dashboard/page.tsx:324
    // (\"remove\" button on upload list) but no test exercised it because
    // no fixture populated the upload state. This test posts a real file
    // through the live /api/upload endpoint, then asserts axe-clean once
    // the upload-list <li> renders with the destructive-class \"remove\"
    // button.
    await page.goto("/dashboard", { waitUntil: "networkidle" });

    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles({
      name: "polaris_a11y_probe.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("hello-from-a11y-probe"),
    });

    // Wait for the upload-list item to appear with our filename + the
    // \"remove\" button. The list rendering depends on POST /api/upload
    // returning successfully.
    await expect(page.getByText("polaris_a11y_probe.txt")).toBeVisible({
      timeout: 8_000,
    });
    await expect(page.getByRole("button", { name: /^remove$/ })).toBeVisible();

    await expectNoA11yViolations(page);
  });
});

// I-cd-013a (GH#609): legacy AuditIR Inspector — migrated by I-cd-013b (#669).
test.describe.skip("WCAG-AA — Inspector verified-sentence with drop_reason", () => {
  test("Verified sentences tab with a Dropped sentence is WCAG-AA clean", async ({
    page,
  }) => {
    // Exercises the inspector/[runId]/page.tsx:315 surface (the
    // \"Dropped: <reason>\" annotation) which axe never saw before because
    // no golden fixture populated drop_reason. Cycle-2 audit P1.1
    // demonstrated this was a real WCAG-AA color-contrast hazard until F-7.
    await page.goto("/inspector/golden_with_drop_reason", {
      waitUntil: "networkidle",
    });
    await page
      .getByRole("button", { name: /Verified sentences/ })
      .first()
      .click();
    await expect(page.getByText(/Dropped:/i)).toBeVisible({ timeout: 8_000 });
    await expectNoA11yViolations(page);
  });
});

test.describe("WCAG 2.5.8 target-size sweep (F-28 — broader than axe)", () => {
  // axe's target-size rule has loose overlap-detection; cycle-8 P1.1 and
  // P1.4 surfaced multiple <button>/<label>/<a role="button"> surfaces
  // that pass axe but fail strict WCAG 2.2 SC 2.5.8 AA (24x24 minimum).
  // This sweep walks every clickable element + asserts ≥24x24 directly.

  test("Dashboard — all clickable targets ≥24x24", async ({ page }) => {
    await page.goto("/dashboard", { waitUntil: "networkidle" });
    const small = await page.evaluate(() => {
      const results: Array<{
        tag: string;
        text: string;
        w: number;
        h: number;
      }> = [];
      // Exclude <label htmlFor=...> — labels paired with a form control
      // delegate the hit target to the control itself (WCAG 2.5.8 "inline"
      // exemption). The "browse files" label has no htmlFor (it wraps the
      // hidden file input directly) so it remains in scope.
      const sel =
        'button, label:not([for]), [role="button"], [role="radio"], a[href]';
      document.querySelectorAll(sel).forEach((el) => {
        if (!(el instanceof HTMLElement)) return;
        const r = el.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) return; // hidden / pre-render
        if (r.width < 24 || r.height < 24) {
          results.push({
            tag: el.tagName,
            text: (el.textContent || "").trim().slice(0, 60),
            w: Math.round(r.width),
            h: Math.round(r.height),
          });
        }
      });
      return results;
    });
    if (small.length > 0) {
      throw new Error(
        `WCAG 2.5.8 failures (${small.length} target(s) < 24x24):\n` +
          small
            .map((s) => `  - ${s.tag} "${s.text}" → ${s.w}x${s.h}px`)
            .join("\n"),
      );
    }
  });

  // I-cd-013a (GH#609): legacy AuditIR Inspector — migrated by I-cd-013b (#669).
  test.skip("Inspector golden_clinical_001 — all clickable targets ≥24x24", async ({
    page,
  }) => {
    await page.goto("/inspector/golden_clinical_001", {
      waitUntil: "networkidle",
    });
    await page
      .getByRole("button", { name: /Verified sentences/ })
      .first()
      .click();
    const small = await page.evaluate(() => {
      const results: Array<{
        tag: string;
        text: string;
        w: number;
        h: number;
      }> = [];
      const sel = 'button, label, [role="button"], a[href]';
      document.querySelectorAll(sel).forEach((el) => {
        if (!(el instanceof HTMLElement)) return;
        const r = el.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) return;
        if (r.width < 24 || r.height < 24) {
          results.push({
            tag: el.tagName,
            text: (el.textContent || "").trim().slice(0, 60),
            w: Math.round(r.width),
            h: Math.round(r.height),
          });
        }
      });
      return results;
    });
    if (small.length > 0) {
      throw new Error(
        `WCAG 2.5.8 failures (${small.length} target(s) < 24x24):\n` +
          small
            .map((s) => `  - ${s.tag} "${s.text}" → ${s.w}x${s.h}px`)
            .join("\n"),
      );
    }
  });
});

test.describe("WCAG 2.1.1 keyboard sweep — template radiogroup operable", () => {
  // F-26 (cycle-8 P1.2 root_cause) regression gate: dashboard template
  // selection MUST be reachable via Tab + activatable via Space/Enter.
  // Survived 7 prior cycles as <Card onClick> with no keyboard handler.
  test("Dashboard template radiogroup is keyboard-operable", async ({
    page,
  }) => {
    await page.goto("/dashboard", { waitUntil: "networkidle" });
    // The radiogroup should expose role="radiogroup".
    const group = page.locator('[role="radiogroup"]');
    await expect(group).toBeVisible();
    // Each template option should expose role="radio" with aria-checked.
    const radios = page.locator('[role="radio"]');
    expect(await radios.count()).toBeGreaterThanOrEqual(2);
    // Default selection.
    const initiallyChecked = await page
      .locator('[role="radio"][aria-checked="true"]')
      .count();
    expect(initiallyChecked).toBe(1);
    // Tab into the first radio + Space-activate; aria-checked moves.
    await radios.nth(1).focus();
    await page.keyboard.press("Space");
    await expect(radios.nth(1)).toHaveAttribute("aria-checked", "true");
  });
});

// I-cd-013a (GH#609): legacy AuditIR Inspector — migrated by I-cd-013b (#669).
test.describe.skip("WCAG-AA — Inspector error states", () => {
  test("Inspector destructive error banner (invalid runId) is WCAG-AA clean", async ({
    page,
  }) => {
    await page.goto("/inspector/does_not_exist_runid_404", {
      waitUntil: "networkidle",
    });
    // Error banner pattern (border-only + text-foreground font-medium) —
    // verify axe doesn't flag the destructive surface.
    await expect(page.getByText(/POLARIS backend returned 404/i)).toBeVisible({
      timeout: 8_000,
    });
    await expectNoA11yViolations(page);
  });

  test("Run-detail destructive error banner (invalid runId) is WCAG-AA clean", async ({
    page,
  }) => {
    // /runs/[runId] page also uses the destructive error pattern; verify it.
    await page.goto("/runs/does_not_exist_runid_404", {
      waitUntil: "networkidle",
    });
    await expect(page.getByText(/POLARIS backend returned 404/i)).toBeVisible({
      timeout: 8_000,
    });
    await expectNoA11yViolations(page);
  });
});
