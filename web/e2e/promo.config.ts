import { defineConfig } from "@playwright/test";

const PORT = 5198;
// Promo stills and loop for docs/promo/. Run: npm run promo (needs ffmpeg on PATH and the sketch fixture built).
export default defineConfig({
  testDir: ".",
  testMatch: /(promo|demo)\.spec\.ts/,
  timeout: 240_000,
  workers: 1,
  reporter: [["list"]],
  webServer: { command: `npx vite --port ${PORT} --strictPort`, port: PORT, reuseExistingServer: true, cwd: ".." },
  use: { baseURL: `http://localhost:${PORT}`, channel: "chrome" },
});
