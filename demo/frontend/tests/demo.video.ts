import { readFileSync, mkdirSync, copyFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";

// Records docs/demo.webm with on-screen captions from demo/video_script.md. No human needed.
// Run: npx playwright test --project=video   (the backend starts in replay mode, see the config)

const SCRIPT = "../video_script.md";
const OUT = "../../docs/demo.webm";
const SIZE = { width: 1280, height: 720 };

function captions(): Map<string, { hold: number; text: string }> {
  const rows = readFileSync(SCRIPT, "utf8")
    .split("\n")
    .filter((l) => /^\|\s*[a-z_]+\s*\|\s*\d+/.test(l));
  return new Map(
    rows.map((l) => {
      const [, id, hold, text] = l.split("|").map((c) => c.trim());
      return [id ?? "", { hold: Number(hold), text: text ?? "" }];
    }),
  );
}

async function caption(page: Page, text: string) {
  await page.evaluate((t) => {
    let el = document.getElementById("cc-caption");
    if (!el) {
      el = document.createElement("div");
      el.id = "cc-caption";
      el.setAttribute(
        "style",
        [
          "position:fixed",
          "left:50%",
          "bottom:22px",
          "transform:translateX(-50%)",
          "z-index:9999",
          "max-width:980px",
          "width:calc(100% - 80px)",
          "padding:12px 20px",
          "border-radius:6px",
          "background:rgba(8,11,19,0.93)",
          "border:1px solid rgba(227,185,87,0.75)",
          "box-shadow:0 10px 30px rgba(0,0,0,0.6)",
          "color:#f3ead6",
          "font:500 19px/1.4 'IBM Plex Sans',system-ui,sans-serif",
          "text-align:center",
          "pointer-events:none",
          "transition:opacity .25s",
        ].join(";"),
      );
      document.body.appendChild(el);
    }
    el.style.opacity = "0";
    window.setTimeout(() => {
      if (!el) return;
      el.textContent = t;
      el.style.opacity = "1";
    }, 200);
  }, text);
}

async function scrollTo(page: Page, testid: string, block: "start" | "center" = "start") {
  await page.getByTestId(testid).evaluate((el, b) => el.scrollIntoView({ behavior: "smooth", block: b }), block);
  await page.waitForTimeout(700);
}

async function scrollTop(page: Page) {
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
  await page.waitForTimeout(700);
}

test("record the demo video", async ({ browser }) => {
  const cap = captions();
  const context = await browser.newContext({ viewport: SIZE, recordVideo: { dir: "test-results/video", size: SIZE }, colorScheme: "dark" });
  const page = await context.newPage();
  const step = async (id: string, action?: () => Promise<void>) => {
    const c = cap.get(id);
    if (!c) throw new Error(`No caption row "${id}" in ${SCRIPT}`);
    await caption(page, c.text);
    if (action) await action();
    await page.waitForTimeout(c.hold * 1000);
  };

  await page.goto("/");
  await expect(page.getByTestId("exhibit-item").first()).toBeVisible();
  await page.waitForTimeout(800);

  await step("intro");
  await step("docket", async () => {
    await page.getByTestId("exhibit-panel").locator(".overflow-y-auto").first().evaluate((el) => el.scrollBy({ top: 260, behavior: "smooth" }));
    await page.waitForTimeout(1500);
    await page.getByTestId("exhibit-panel").locator(".overflow-y-auto").first().evaluate((el) => el.scrollTo({ top: 0, behavior: "smooth" }));
  });

  // Objection flow.
  await step("handbag", async () => {
    await page.locator('[data-exhibit-id="handbag-leather"]').click();
  });
  await expect(page.getByTestId("final-code")).toHaveText("4202.21.90.00", { timeout: 60_000 });
  await step("tree", async () => {
    const rejected = page.locator('[data-testid="tree-node"][data-state="rejected"]').first();
    if (await rejected.count()) await rejected.hover();
  });
  await page.mouse.move(5, 5);
  await step("ruling", async () => scrollTo(page, "ruling-panel"));
  await step("objection", async () => {
    await page.getByTestId("objection-button").click();
  });
  await step("rehearing", async () => {
    await page.getByTestId("objection-submit").click();
  });
  await expect(page.getByTestId("final-code")).toHaveText("4202.22.15.00", { timeout: 60_000 });
  await step("overruled", async () => {
    await scrollTop(page);
    const over = page.locator('[data-testid="tree-node"][data-state="overruled"]').first();
    if (await over.count()) await over.hover();
  });
  await page.mouse.move(5, 5);

  // Beat the Broker.
  await step("broker", async () => {
    await page.locator('[data-exhibit-id="wool-coat"]').scrollIntoViewIfNeeded();
    await page.locator('[data-exhibit-id="wool-coat"]').click();
  });
  await step("guess", async () => {
    await page.getByTestId("sealed-guess-input").pressSequentially("6102.10", { delay: 120 });
    await page.getByTestId("sealed-lock").click();
  });
  await step("broker_hearing");
  await expect(page.getByTestId("final-code")).toHaveText("6202.20.11.10", { timeout: 60_000 });
  await step("missing", async () => scrollTo(page, "ruling-panel"));
  await step("reveal", async () => {
    await scrollTo(page, "broker-reveal", "center");
    await page.getByTestId("broker-reveal").click();
    await page.waitForTimeout(400);
    await scrollTo(page, "scoreboard", "center");
  });

  // Time machine.
  await step("timemachine", async () => {
    await scrollTop(page);
    await page.locator('[data-exhibit-id="vinyl-tiles"]').click();
  });
  await expect(page.getByTestId("timemachine-result")).toHaveAttribute("data-change", "removed", { timeout: 30_000 });
  await step("timemachine_diff", async () => scrollTo(page, "timemachine", "center"));
  await step("cost", async () => scrollTo(page, "cost-meter", "center"));
  await step("outro", async () => scrollTop(page));

  const video = page.video();
  await context.close();
  mkdirSync("../../docs", { recursive: true });
  if (video) copyFileSync(await video.path(), OUT);
});
