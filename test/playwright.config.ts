import { defineConfig, devices } from '@playwright/test';
import path from 'path';

const BASE_URL = process.env.BASE_URL || 'http://localhost:8000';

export default defineConfig({
  testDir: './e2e',
  globalSetup: path.resolve(__dirname, 'globalSetup.ts'),
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [['html', { open: 'never' }], ['list']],
  timeout: 30000,
  expect: {
    timeout: 10000,
  },
  use: {
    baseURL: BASE_URL,
    screenshot: 'only-on-failure',
    trace: 'on-first-retry',
    video: 'off',
    actionTimeout: 10000,
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1440, height: 900 },
      },
    },
  ],
  // No webServer block — the backend must be running before tests are launched.
  // See README.md for startup instructions.
});
