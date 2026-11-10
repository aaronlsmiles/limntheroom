// One smoke at 1440 and 390, light and dark (the four projects in playwright.config.ts):
// the page loads, the stage, wipe, overlay, timeline and text equivalent work, and the console stays clean.
import { test, expect, type Page } from "@playwright/test";

function watch(page: Page) {
  const bad: string[] = [];
  page.on("console", (m) => { if (m.type() === "error" || m.type() === "warning") bad.push(`console.${m.type()}: ${m.text()}`); });
  page.on("pageerror", (e) => bad.push(`pageerror: ${e.message}`));
  // a seek cancels the video's open range request (net::ERR_ABORTED): the browser doing its job, not a failure
  page.on("requestfailed", (r) => { if (!(/\.mp4$/.test(r.url()) && r.failure()?.errorText === "net::ERR_ABORTED")) bad.push(`requestfailed: ${r.url()} ${r.failure()?.errorText}`); });
  page.on("response", (r) => { if (r.status() >= 400) bad.push(`http ${r.status()}: ${r.url()}`); });
  return bad;
}

const painted = (page: Page) => page.getByTestId("overlay").evaluate((c: HTMLCanvasElement) => {
  const d = c.getContext("2d")!.getImageData(0, 0, c.width, c.height).data;
  let n = 0;
  for (let i = 3; i < d.length; i += 4) if (d[i] > 0) n++;
  return n;
});

test("the seam view loads, wipes, overlays, seeks and keeps the console clean", async ({ page }) => {
  const bad = watch(page);
  await page.goto("/?pause=1&frame=75&wipe=0.5");
  await expect(page.getByRole("heading", { level: 1, name: "The seam view" })).toBeVisible();
  await expect(page.getByTestId("synthetic-label")).toBeVisible();
  await expect(page.getByTestId("synthetic-label")).toContainText("synthetic sketch");
  await page.evaluate(() => document.fonts.ready);

  // both clips decode and sit on the requested frame
  await expect.poll(() => page.evaluate(() => [...document.querySelectorAll("video")].every((v) => v.readyState >= 2 && !v.error))).toBe(true);
  await expect(page.getByTestId("clock")).toContainText("0:05.0");

  // the overlay is drawn: kept (gold) and limned (hatch) cells during contact
  await expect.poll(() => painted(page)).toBeGreaterThan(1000);
  await expect(page.getByTestId("kept-now")).toContainText("%");
  await expect(page.getByTestId("text-equivalent")).toContainText("kept");

  // the divider is a slider: arrow keys and a drag move it, and it stays inside the stage
  const divider = page.getByRole("slider", { name: /Wipe divider/ });
  await expect(divider).toHaveAttribute("aria-valuenow", "50");
  await divider.focus();
  await page.keyboard.press("ArrowRight");
  await expect(divider).toHaveAttribute("aria-valuenow", "52");
  await page.keyboard.press("Shift+ArrowLeft");
  await expect(divider).toHaveAttribute("aria-valuenow", "42");
  const stage = page.getByRole("group", { name: /compared with a wipe/ });
  await stage.scrollIntoViewIfNeeded();
  const box = (await stage.boundingBox())!;
  const handle = (await divider.boundingBox())!;
  await page.mouse.move(handle.x + handle.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.75, box.y + box.height / 2, { steps: 5 });
  await page.mouse.up();
  const dragged = Number(await divider.getAttribute("aria-valuenow"));
  expect(dragged).toBeGreaterThan(70);
  expect(dragged).toBeLessThanOrEqual(98);

  // the timeline seeks on a click, and a cue button jumps to its time
  const tl = page.getByRole("slider", { name: "Playhead" });
  await tl.scrollIntoViewIfNeeded();
  const tb = (await tl.boundingBox())!;
  await page.mouse.click(tb.x + tb.width * 0.2, tb.y + tb.height / 2);
  await expect.poll(async () => Number(await tl.getAttribute("aria-valuenow"))).toBeLessThan(60);
  await page.getByRole("button", { name: /cue 2: glass lifted/ }).click();
  await expect(page.getByTestId("clock")).toContainText("0:07.0");

  // switching to the take hides the render's divider and overlay; back to the wipe restores them
  await page.getByRole("radio", { name: "Take" }).check({ force: true });
  await expect(page.getByRole("slider", { name: /Wipe divider/ })).toHaveCount(0);
  await page.getByRole("radio", { name: "Wipe" }).check({ force: true });
  await expect(page.getByRole("slider", { name: /Wipe divider/ })).toBeVisible();

  // the theme toggle flips the page between paper and ink
  const before = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  await page.getByRole("button", { name: /Switch to the/ }).click();
  expect(await page.evaluate(() => getComputedStyle(document.body).backgroundColor)).not.toBe(before);

  // nothing overflows the viewport sideways
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);

  expect(bad, "console, page errors and failed requests").toEqual([]);
});

test("playing: the overlay follows the presented frames and the console stays clean", async ({ page }) => {
  const bad = watch(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  // autoplay is muted; the clock must advance (skipped under reduced motion, which starts paused)
  const t0 = await page.getByTestId("clock").innerText();
  await expect.poll(async () => page.getByTestId("clock").innerText(), { timeout: 8000 }).not.toBe(t0);
  expect(bad).toEqual([]);
});
