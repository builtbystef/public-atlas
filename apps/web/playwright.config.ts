import { defineConfig, devices } from "@playwright/test";

/**
 * The console smoke (e2e/): the built console, served by `next start`, against the API on a
 * seeded database. `vp run test:e2e` from the repository root runs it; locally it needs
 * `vp run infra:up`, a migrated database with `public-atlas seed canada`, and `next build`.
 *
 * Both servers are started here unless they are up already (outside CI). The API address is
 * the one next.config.ts bakes into the `/api` rewrite at build time, so the smoke runs the
 * console as CI built it.
 */

const API_URL = process.env["API_URL"] ?? "http://127.0.0.1:8000";
const WEB_URL = "http://127.0.0.1:3000";
const CI = process.env["CI"] !== undefined;

export default defineConfig({
  testDir: "e2e",
  fullyParallel: true,
  forbidOnly: CI,
  reporter: CI ? "github" : "list",
  use: {
    baseURL: WEB_URL,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "uv run fastapi run --port 8000",
      cwd: "../server",
      url: `${API_URL}/health`,
      reuseExistingServer: !CI,
      timeout: 60_000,
    },
    {
      // `next start` warns that the standalone output has its own server.js; it serves the
      // build all the same, and needs no copying of static files first.
      command: "next start --port 3000",
      url: `${WEB_URL}/lists`,
      reuseExistingServer: !CI,
      env: { API_URL },
      timeout: 60_000,
    },
  ],
});
