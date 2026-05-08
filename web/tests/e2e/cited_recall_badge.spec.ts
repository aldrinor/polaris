import { expect, test } from "@playwright/test";

test("memory-cite sentences render the prior-run badge; non-memory sentences do not", async ({
  page,
}) => {
  await page.goto("/sentence_hover_test/memory_cite");

  const kept = page.getByTestId("kept-sentence");
  await expect(kept).toHaveCount(2);

  // Sentence 0 cites ev_memory_* — badge MUST render.
  const memory_sentence = kept.nth(0);
  const sentence_id = await memory_sentence.getAttribute("data-sentence-id");
  expect(sentence_id).not.toBeNull();
  await expect(
    page.getByTestId(`prior-run-badge-${sentence_id}`),
  ).toBeVisible();
  await expect(
    page.getByTestId(`prior-run-badge-${sentence_id}`),
  ).toContainText("from prior run");
  await expect(
    page.getByTestId(`prior-run-badge-${sentence_id}`),
  ).toHaveAttribute("title", /ev_memory_/);

  // Sentence 1 has only a non-memory token — badge MUST NOT render.
  const other_sentence = kept.nth(1);
  const other_id = await other_sentence.getAttribute("data-sentence-id");
  await expect(page.getByTestId(`prior-run-badge-${other_id}`)).toHaveCount(0);
});
