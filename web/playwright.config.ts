import { defineConfig } from "@playwright/test";

// End-to-end tests against the real server serving the built UI (`pnpm build` first;
// `pnpm test:e2e` does both). Uses the installed Edge, so no browser download is needed;
// set PW_CHANNEL=chrome (or "" for Playwright's bundled Chromium) to change that.
const python = process.platform === "win32" ? "..\\.venv\\Scripts\\python.exe" : "../.venv/bin/python";
const port = 8765;

export default defineConfig({
  testDir: "e2e",
  timeout: 120_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    channel: process.env.PW_CHANNEL ?? "msedge",
    viewport: { width: 1600, height: 1000 },
    trace: "retain-on-failure",
  },
  webServer: {
    command: `${python} -m maskserver --no-browser --port ${port}`,
    url: `http://127.0.0.1:${port}/api/health`,
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
