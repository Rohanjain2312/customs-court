import { expect, test, type Page } from "@playwright/test";

// Every test runs against the real backend in replay mode (see playwright.config.ts).
// ?speed=8 plays the recorded hearings eight times faster than the compressed replay clock.
const SHOTS = "../../docs/screenshots";

async function open(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });
  await page.goto("/?speed=8");
  await expect(page.getByTestId("mode-badge")).toHaveAttribute("data-mode", "replay");
  await expect(page.getByTestId("exhibit-item").first()).toBeVisible();
  return errors;
}

async function pick(page: Page, id: string) {
  await page.locator(`[data-exhibit-id="${id}"]`).click();
}

test("every screen renders", async ({ page }) => {
  const errors = await open(page);
  expect(await page.getByTestId("exhibit-item").count()).toBeGreaterThanOrEqual(10);
  await expect(page.getByTestId("timing-note")).toContainText("compressed");
  await expect(page.getByTestId("tree-node").first()).toBeVisible();
  for (const id of ["exhibit-panel", "tree-panel", "hearing-panel", "ruling-panel", "timemachine", "cost-meter", "scoreboard"]) {
    await expect(page.getByTestId(id)).toBeVisible();
  }
  await page.screenshot({ path: `${SHOTS}/01-docket.png` });

  // Live-only intake paths say so in replay mode.
  await page.getByTestId("tab-type").click();
  await expect(page.getByTestId("replay-notice")).toBeVisible();
  await expect(page.getByTestId("typed-exhibit-input")).toBeDisabled();
  await page.getByTestId("tab-photo").click();
  await expect(page.getByTestId("replay-notice")).toBeVisible();
  await expect(page.getByTestId("photo-describe")).toBeDisabled();
  await page.screenshot({ path: `${SHOTS}/02-photo-live-only.png` });
  await page.getByTestId("tab-docket").click();

  // A single-agent hearing: counsel card, tree states, ruling, cost.
  await pick(page, "polivac-film");
  await expect(page.getByTestId("counsel-card")).toBeVisible();
  await expect(page.getByTestId("final-code")).toHaveText("3920.62.00.90");
  await expect(page.locator('[data-testid="tree-node"][data-state="chosen"]')).toHaveCount(1);
  await expect(page.locator('[data-testid="tree-node"][data-state="rejected"]').first()).toBeVisible();
  await expect(page.getByTestId("reference-code")).toContainText("3920.62.00.00");
  await expect(page.getByTestId("cost-usd")).toHaveText("$0.0499");
  expect(await page.getByTestId("counsel-step").count()).toBeGreaterThan(0);

  // Hover a rejected line: the reason shows.
  const rejected = page.locator('[data-testid="tree-node"][data-state="rejected"]').first();
  await rejected.hover();
  await expect(page.getByRole("tooltip")).toContainText(/rejected/i);
  await page.screenshot({ path: `${SHOTS}/03-single-agent-hearing.png` });
  await page.getByTestId("ruling-panel").screenshot({ path: `${SHOTS}/04-ruling.png` });

  // A multi-agent hearing through the arm toggle: advocate cards, then the adjudicator names the GRI.
  // polivac-film has a real single-agent and a real multi-agent recording (same item).
  await page.getByTestId("arm-multi").click();
  await expect(page.getByTestId("advocate-card")).toHaveCount(2);
  await expect(page.getByTestId("adjudicator-card")).toBeVisible();
  await expect(page.getByTestId("deciding-gri")).toHaveText("GRI 1");
  await expect(page.getByTestId("arm-compare")).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/05-multi-agent-hearing.png` });
  await page.getByTestId("cost-meter").screenshot({ path: `${SHOTS}/06-cost-meter.png` });

  expect(errors).toEqual([]);
});

test("objection flow re-hears the case and the code changes", async ({ page }) => {
  const errors = await open(page);
  await pick(page, "handbag-leather");
  await expect(page.getByTestId("final-code")).toHaveText("4202.21.90.00");
  await page.getByTestId("objection-button").click();
  await expect(page.getByTestId("objection-input")).toHaveValue(/PVC/);
  await page.getByTestId("ruling-panel").screenshot({ path: `${SHOTS}/07-objection-form.png` });
  await page.getByTestId("objection-submit").click();
  await expect(page.getByTestId("final-code")).toHaveText("4202.22.15.00");
  await expect(page.getByTestId("ruling-panel")).toContainText("Overrules");
  await expect(page.locator('[data-testid="tree-node"][data-state="overruled"]')).toHaveCount(1);
  await expect(page.locator('[data-testid="tree-node"][data-state="chosen"]')).toHaveAttribute("data-code", "4202.22.15.00");
  await page.screenshot({ path: `${SHOTS}/08-objection-rehearing.png` });
  expect(errors).toEqual([]);
});

test("beat the broker: guess, hear, reveal, score", async ({ page }) => {
  const errors = await open(page);
  await pick(page, "boys-tshirt");
  await expect(page.getByTestId("sealed-exhibit")).toBeVisible();
  await expect(page.getByTestId("final-code")).toHaveCount(0);
  // The reveal is locked until the court has ruled.
  await expect(page.getByTestId("broker-reveal")).toBeDisabled();
  await page.getByTestId("sealed-guess-input").fill("6109.90");
  await page.screenshot({ path: `${SHOTS}/09-broker-guess.png` });
  await page.getByTestId("sealed-lock").click();
  await expect(page.getByTestId("final-code")).toHaveText("6109.90.10.25");
  await expect(page.getByTestId("broker-reveal")).toBeEnabled();
  await page.getByTestId("broker-reveal").click();
  await expect(page.getByTestId("broker-result")).toContainText("6109.90.10.09");
  const board = page.getByTestId("scoreboard");
  await expect(board.locator('tr[data-player="human"] td').nth(1)).toHaveText("1");
  await expect(board.locator('tr[data-player="human"] td').nth(3)).toHaveText("6");
  await expect(board.locator('tr[data-player="single"] td').nth(3)).toHaveText("8");
  await page.getByTestId("broker-result").scrollIntoViewIfNeeded();
  await page.screenshot({ path: `${SHOTS}/10-broker-reveal.png` });

  // The scoreboard lasts for the session (a reload keeps it).
  await page.reload();
  await expect(page.getByTestId("scoreboard").locator('tr[data-player="human"] td').nth(1)).toHaveText("1");
  expect(errors).toEqual([]);
});

test("time machine shows a code that was split since the ruling", async ({ page }) => {
  const errors = await open(page);
  await pick(page, "vinyl-tiles");
  const tm = page.getByTestId("timemachine");
  await expect(page.getByTestId("timemachine-result")).toHaveAttribute("data-change", "removed");
  await expect(page.getByTestId("timemachine-code")).toHaveValue("3918.10.10.00");
  await expect(page.getByTestId("tm-then")).toContainText("Vinyl tile");
  await tm.scrollIntoViewIfNeeded();
  await tm.screenshot({ path: `${SHOTS}/11-time-machine-removed.png` });

  // Another year and a line that did not change.
  await page.getByTestId("timemachine-code").fill("4202.21.90.00");
  await page.getByTestId("timemachine-go").click();
  await expect(page.getByTestId("timemachine-result")).toHaveAttribute("data-change", "unchanged");
  await page.getByTestId("timemachine-year").selectOption({ index: 3 });
  await expect(page.getByTestId("timemachine-result")).toHaveAttribute("data-change", "unchanged");
  expect(errors).toEqual([]);
});

test("projector size renders the whole courtroom", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  const errors = await open(page);
  await pick(page, "wool-coat");
  await page.getByTestId("sealed-skip").click();
  await expect(page.getByTestId("final-code")).toHaveText("6202.20.11.10");
  await page.screenshot({ path: `${SHOTS}/12-projector-1920.png` });
  expect(errors).toEqual([]);
});
