import { defineConfig } from '@playwright/test'

/** The marketing page (marketing/), served with its production headers; the gallery API is faked per test. */
export default defineConfig({
  testDir: 'e2e-marketing',
  timeout: 60_000, // the screenshot tests load the 4 MB animatic from a one-process local server
  retries: 0,
  workers: 2,
  reporter: [['list']],
  use: { baseURL: 'http://127.0.0.1:4174', channel: 'chromium' },
  webServer: {
    command: 'python3 e2e-marketing/serve.py 4174',
    url: 'http://127.0.0.1:4174/',
    reuseExistingServer: !process.env.CI,
  },
})
