import { defineConfig } from "@playwright/test";

const sizes = [{ name: "desktop", width: 1440, height: 900 }, { name: "phone", width: 390, height: 844 }];
const schemes = ["light", "dark"] as const;
const PORT = 5198;

// channel "chrome": the clips are H.264, which Playwright's bundled Chromium cannot decode.
export default defineConfig({
  testDir: ".",
  testIgnore: /promo\.spec\.ts/,
  timeout: 30_000,
  fullyParallel: true,
  reporter: [["list"]],
  webServer: { command: `npx vite --port ${PORT} --strictPort`, port: PORT, reuseExistingServer: true, cwd: ".." },
  use: { baseURL: `http://localhost:${PORT}`, channel: "chrome" },
  projects: sizes.flatMap((s) => schemes.map((c) => ({
    name: `${s.name}-${c}`,
    use: { viewport: { width: s.width, height: s.height }, colorScheme: c, hasTouch: s.name === "phone" },
  }))),
});
