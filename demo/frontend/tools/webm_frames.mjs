// Capture frames from docs/demo.webm by playing it in Chromium (the Playwright ffmpeg build has no image
// encoders, and Playwright's webm has no seek index, so seeking does not work).
// Usage: (cd docs && python3 -m http.server 8801 &) ; node tools/webm_frames.mjs http://127.0.0.1:8801/demo.webm <outdir> [fps] [width]
import { chromium } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";

const [, , src, outdir, fpsArg = "4", widthArg = "720"] = process.argv;
const fps = Number(fpsArg);
const width = Number(widthArg);
mkdirSync(outdir, { recursive: true });
const browser = await chromium.launch({ args: ["--autoplay-policy=no-user-gesture-required"] });
const page = await browser.newPage();
let n = 0;
await page.exposeFunction("saveFrame", (b64) => {
  writeFileSync(`${outdir}/f_${String(n++).padStart(4, "0")}.png`, Buffer.from(b64, "base64"));
});
await page.goto(src);
await page.evaluate(
  ({ fps, width }) =>
    new Promise((done) => {
      const v = document.querySelector("video");
      v.muted = true;
      const height = Math.round((width * v.videoHeight) / v.videoWidth);
      const c = document.createElement("canvas");
      c.width = width;
      c.height = height;
      const ctx = c.getContext("2d");
      v.addEventListener("ended", () => done(), { once: true });
      v.play();
      setInterval(() => {
        ctx.drawImage(v, 0, 0, width, height);
        window.saveFrame(c.toDataURL("image/png").split(",")[1]);
      }, 1000 / fps);
    }),
  { fps, width },
);
await browser.close();
console.log(`${n} frames`);
