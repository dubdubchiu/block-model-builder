import { defineConfig, devices } from "@playwright/test";

// Pinned to @playwright/test 1.56.1, which matches the Chromium build preinstalled in
// the cloud container (/opt/pw-browsers). Run `npm run build` first; e2e uses the preview.
// E2E_BASE_URL runs the suite against a server that's already up (e.g. the Docker image),
// with E2E_USER and E2E_PASSWORD for its password gate.
const external = process.env.E2E_BASE_URL;
const credentials =
  process.env.E2E_USER && process.env.E2E_PASSWORD ? { username: process.env.E2E_USER, password: process.env.E2E_PASSWORD } : undefined;

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  reporter: "list",
  use: { baseURL: external ?? "http://127.0.0.1:4173", screenshot: "only-on-failure", httpCredentials: credentials },
  webServer: external ? [] : [
    {
      command: "uv run uvicorn app.main:app --app-dir server --port 8000",
      cwd: "..",
      // Saved models from e2e runs go to a scratch folder, not data/models.
      env: { BM_DATA_DIR: "web/e2e-data" },
      url: "http://127.0.0.1:8000/api/health",
      reuseExistingServer: true,
      timeout: 60_000,
    },
    {
      command: "npm run preview -- --strictPort --host 127.0.0.1",
      url: "http://127.0.0.1:4173",
      reuseExistingServer: true,
    },
  ],
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
