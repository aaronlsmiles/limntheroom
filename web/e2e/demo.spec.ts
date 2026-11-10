// The site's placeholder demo, recorded from the end-to-end rehearsal (?data=rehearsal): a silent film of
// the whole clip with the wipe sweeping, its poster, and three stills (before, at and after contact).
// Run: npx playwright test -c e2e/promo.config.ts demo (needs ffmpeg and tools/rehearsal_to_web.py run first).
// Everything here is the synthetic rehearsal: drawn shapes and a stub agent, not a take. Nothing is a result.
import { test, expect, type Browser, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, rmSync } from "node:fs";
import { fileURLToPath } from "node:url";

const OUT = fileURLToPath(new URL("../../docs/promo/", import.meta.url));
const FRAMES = fileURLToPath(new URL("../test-results/demo-frames/", import.meta.url));
const META = JSON.parse(readFileSync(fileURLToPath(new URL("../public/rehearsal/seam.json", import.meta.url)), "utf8"));
const FPS: number = META.fps;
const N: number = META.frames;
const contact = (META.series.contact as number[]).map((c, i) => (c ? i : -1)).filter((i) => i >= 0);
const C0 = contact[0], C1 = contact[contact.length - 1];

async function open(browser: Browser, frame: number, wipe = 0.5) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: "light", deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  await page.goto(`/?data=rehearsal&capture=1&frame=${frame}&wipe=${wipe}&pause=1`);
  await expect(page.getByTestId("synthetic-label")).toHaveText(/synthetic rehearsal, not results/);
  await page.evaluate(() => document.fonts.ready);
  await page.waitForFunction(() => !!window.__limn);
  await page.waitForFunction(() => [...document.querySelectorAll("video")].every((v) => v.readyState >= 2));
  return { ctx, page };
}
const settle = (page: Page, n: number) => page.evaluate((f) => window.__limn!.seek(f), n);

test.beforeAll(() => mkdirSync(OUT, { recursive: true }));

test("rehearsal stills: before, at and after contact", async ({ browser }) => {
  const at = { before: Math.max(0, C0 - 2 * FPS), contact: Math.round((C0 + C1) / 2), after: Math.min(N - 1, C1 + 2 * FPS) };
  // the divider left of the glass, so the render side shows the shape at it
  const { ctx, page } = await open(browser, at.before, 0.36);
  for (const [name, f] of Object.entries(at)) {
    await settle(page, f);
    await page.screenshot({ path: `${OUT}limn-rehearsal-${name}.png` });
  }
  await ctx.close();
});

test("rehearsal demo film, silent H.264", async ({ browser }) => {
  rmSync(FRAMES, { recursive: true, force: true });
  mkdirSync(FRAMES, { recursive: true });
  const { ctx, page } = await open(browser, 0);
  for (let i = 0; i < N; i++) {
    // two slow sweeps of the divider across the whole clip, starting and ending at the middle
    await page.evaluate((x) => window.__limn!.setWipe(x), 0.5 + 0.32 * Math.sin((4 * Math.PI * i) / N));
    await settle(page, i);
    await page.screenshot({ path: `${FRAMES}f${String(i).padStart(3, "0")}.png` });
  }
  await ctx.close();
  const title = "Limn the Room: the seam view on the end-to-end rehearsal (synthetic, not results)";
  execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-framerate", String(FPS), "-i", `${FRAMES}f%03d.png`,
    "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p", "-c:v", "libx264", "-preset", "slow", "-crf", "20",
    "-movflags", "+faststart", "-an", "-metadata", `title=${title}`, `${OUT}limn-rehearsal-demo.mp4`]);
  execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-i", `${FRAMES}f${String(Math.round((C0 + C1) / 2)).padStart(3, "0")}.png`,
    "-q:v", "3", `${OUT}limn-rehearsal-demo-poster.jpg`]);
  rmSync(FRAMES, { recursive: true, force: true });
});
