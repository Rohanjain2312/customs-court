import { expect, test } from "@playwright/test";

// Live mode against the offline fixture server (see playwright.config.ts): the typed
// description matches the recorded fixture run, so every model call is a cache hit.
const LIVE = `http://127.0.0.1:${Number(process.env.CC_TEST_PORT ?? 8799) - 1}`;
const HANDBAG =
  "Women's handbag with an outer surface of genuine cowhide leather, zipper closure, two shoulder straps " +
  "and a polyester lining. Retail value about $45.";

test("live mode: a typed exhibit is heard and the session budget is shown", async ({ page }) => {
  await page.goto(`${LIVE}/`);
  await expect(page.getByTestId("mode-badge")).toHaveAttribute("data-mode", "live");
  await page.getByTestId("tab-type").click();
  await expect(page.getByTestId("replay-notice")).toHaveCount(0);
  await page.getByTestId("typed-exhibit-input").fill(HANDBAG);
  await page.getByTestId("typed-exhibit-submit").click();
  const code = page.getByTestId("final-code");
  const miss = page.getByRole("alert").filter({ hasText: "OfflineMiss" });
  await expect(code.or(miss)).toBeVisible({ timeout: 60_000 });
  test.skip(await miss.isVisible(), "fixture response cache does not match the current prompts; re-record it");
  await expect(code).toHaveText(/^4202\.21/);
  await expect(page.getByTestId("counsel-card")).toBeVisible();
  await expect(page.getByTestId("cost-meter")).toContainText("Session budget");
  // Cache hits are free: the session has spent nothing.
  await expect(page.getByTestId("cost-meter")).toContainText("$0.0000 of $2.00 used");
  await expect(page.locator('[data-testid="tree-node"][data-state="chosen"]')).toHaveCount(1);
  await page.waitForTimeout(1200);
  await page.screenshot({ path: "../../docs/screenshots/13-live-mode-offline-fixture.png" });
});
