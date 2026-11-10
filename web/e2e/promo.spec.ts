// Promo assets for the portfolio site: stills at the wipe's mid-point during contact, and a silent loop.
// The loop is Playwright screenshots stitched by ffmpeg (VP9 smears fine lines, so H.264 from PNGs).
// All of it is the synthetic sketch: nothing here is a result.
import { test, expect, type Browser, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { mkdirSync, rmSync } from "node:fs";
import { fileURLToPath } from "node:url";

const OUT = fileURLToPath(new URL("../../docs/promo/", import.meta.url));
const FRAMES = fileURLToPath(new URL("../test-results/promo-frames/", import.meta.url));
const CONTACT_MID = 75; // 5.0 s, inside the 4 to 6 s contact window

async function open(browser: Browser, size: { width: number; height: number }, scheme: "light" | "dark", dsf: number, query: string) {
  const ctx = await browser.newContext({ viewport: size, colorScheme: scheme, deviceScaleFactor: dsf });
  const page = await ctx.newPage();
  await page.goto(`/?${query}`);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  await page.waitForFunction(() => !!window.__limn);
  await page.waitForFunction(() => [...document.querySelectorAll("video")].every((v) => v.readyState >= 2));
  return { ctx, page };
}
const settle = (page: Page, n: number) => page.evaluate((f) => window.__limn!.seek(f), n);

test.beforeAll(() => mkdirSync(OUT, { recursive: true }));

for (const scheme of ["light", "dark"] as const) {
  test(`still 1440x900 ${scheme}`, async ({ browser }) => {
    const { ctx, page } = await open(browser, { width: 1440, height: 900 }, scheme, 1, `capture=1&frame=${CONTACT_MID}&wipe=0.5&pause=1`);
    await settle(page, CONTACT_MID);
    await page.screenshot({ path: `${OUT}limn-seam-1440x900-${scheme}.png` });
    await ctx.close();
  });
  test(`still 390 ${scheme}`, async ({ browser }) => {
    // 390 CSS px wide at 2x (780 px), the full page as a phone would scroll it
    const { ctx, page } = await open(browser, { width: 390, height: 844 }, scheme, 2, `capture=1&frame=${CONTACT_MID}&wipe=0.5&pause=1`);
    await settle(page, CONTACT_MID);
    await page.screenshot({ path: `${OUT}limn-seam-390-${scheme}.png`, fullPage: true });
    await ctx.close();
  });
}

test("loop 7 s, silent H.264", async ({ browser }) => {
  const FPS = 15, FROM = 3 * FPS, COUNT = 7 * FPS;
  rmSync(FRAMES, { recursive: true, force: true });
  mkdirSync(FRAMES, { recursive: true });
  const { ctx, page } = await open(browser, { width: 1440, height: 900 }, "light", 1, `capture=1&frame=${FROM}&wipe=0.5&pause=1`);
  for (let i = 0; i < COUNT; i++) {
    // the divider sweeps once across the stage and ends where it began
    await page.evaluate((x) => window.__limn!.setWipe(x), 0.5 + 0.3 * Math.sin((2 * Math.PI * i) / COUNT));
    await settle(page, FROM + i);
    await page.screenshot({ path: `${FRAMES}f${String(i).padStart(3, "0")}.png` });
  }
  await ctx.close();
  execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-framerate", String(FPS), "-i", `${FRAMES}f%03d.png`,
    "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p", "-c:v", "libx264", "-preset", "slow", "-crf", "15", "-movflags", "+faststart", "-an",
    "-metadata", "title=Limn the Room: ink that reads the room (synthetic sketch, not results)", `${OUT}limn-seam-loop.mp4`]);
  rmSync(FRAMES, { recursive: true, force: true });
});
