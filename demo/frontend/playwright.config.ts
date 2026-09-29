import { defineConfig } from "@playwright/test";

// Starts the real backend in replay mode (no API key, no network, no spend) on its own port.
// The frontend must be built first (npm run build); the backend serves demo/frontend/dist.
const PORT = Number(process.env.CC_TEST_PORT ?? 8799);
export const LIVE_PORT = PORT - 1;

export default defineConfig({
  testDir: "tests",
  timeout: 90_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    viewport: { width: 1440, height: 900 },
    colorScheme: "dark",
  },
  projects: [
    { name: "ui", testMatch: /.*\.spec\.ts/ },
    { name: "video", testMatch: /.*\.video\.ts/, timeout: 600_000 },
  ],
  webServer: [
    {
      command: `uv run python -m uvicorn demo.backend.app:app --host 127.0.0.1 --port ${PORT}`,
      cwd: "../..",
      url: `http://127.0.0.1:${PORT}/api/health`,
      reuseExistingServer: false,
      timeout: 60_000,
      env: { DEMO_MODE: "replay", OFFLINE: "true", USE_VECTORS: "false", ANTHROPIC_API_KEY: "" },
    },
    {
      // Live mode with zero spend: OFFLINE=true serves model calls only from the fixture
      // response cache, and the key is a dummy, so no request can reach a paid API.
      command: `uv run python -m uvicorn demo.backend.app:app --host 127.0.0.1 --port ${LIVE_PORT}`,
      cwd: "../..",
      url: `http://127.0.0.1:${LIVE_PORT}/api/health`,
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        DEMO_MODE: "live",
        OFFLINE: "true",
        USE_VECTORS: "false",
        ANTHROPIC_API_KEY: "sk-offline-test-not-a-key",
        DATA_DIR: "tests/fixtures/data",
        LEDGER_FILE: "/tmp/customs-court-playwright-ledger.jsonl",
      },
    },
  ],
});
