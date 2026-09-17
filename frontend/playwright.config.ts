import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  use: {
    ...devices['Desktop Chrome'],
    baseURL: 'http://127.0.0.1:18080',
    headless: true,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
  webServer: {
    command: 'rm -f /tmp/taskrelay-playwright.db && uv run uvicorn taskrelaymcp.app:app --host 127.0.0.1 --port 18080',
    cwd: '..',
    url: 'http://127.0.0.1:18080/health',
    reuseExistingServer: false,
    env: {
      TASKRELAY_DATABASE_URL: 'sqlite:////tmp/taskrelay-playwright.db',
      TASKRELAY_ADMIN_USERNAME: 'e2e-admin',
      TASKRELAY_ADMIN_PASSWORD: 'e2e-temporary-password',
      TASKRELAY_ADMIN_DISPLAY_NAME: 'E2E Admin',
      TASKRELAY_SECURE_COOKIES: 'false',
      TASKRELAY_PUBLIC_ORIGIN: 'http://127.0.0.1:18080',
    },
  },
  globalTeardown: './e2e/global-teardown.ts',
});
