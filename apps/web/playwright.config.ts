import { defineConfig, devices } from "@playwright/test";

/**
 * The console smoke (e2e/): the built console, served by `next start`, against the API on a
 * database of its own. `vp run test:e2e` from the repository root runs it; locally it needs
 * `vp run infra:up` and `next build`.
 *
 * Both servers are started here, on ports of their own, so the development servers can keep
 * running and are never used by mistake. The API's script (apps/server/tests/console_api.py)
 * drops and rebuilds `public_atlas_e2e`, migrated and seeded with Canada, before it serves.
 * The console reads `API_URL` at run time, so it runs as CI built it.
 */

const API_URL = "http://127.0.0.1:8100";
const WEB_URL = "http://127.0.0.1:3100";
const CI = process.env["CI"] !== undefined;

// The specs call the API directly; workers load this file too, so they read the same address.
process.env["API_URL"] = API_URL;

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
      command: "uv run python tests/console_api.py 8100",
      cwd: "../server",
      url: `${API_URL}/health`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      // `next start` warns that the standalone output has its own server.js; it serves the
      // build all the same, and needs no copying of static files first.
      command: "next start --port 3100",
      url: `${WEB_URL}/lists`,
      reuseExistingServer: false,
      env: { API_URL },
      timeout: 60_000,
    },
  ],
});
