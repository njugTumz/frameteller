import { defineConfig } from '@playwright/test'

/**
 * Two suites:
 * - mocked: REST and the session WebSocket are faked inside the browser. No backend, no credits; runs in CI.
 * - live (opt-in, E2E_LIVE=1): a real backend and Meta's models, narrating spikes/fixtures/narration.wav.
 *   Point it at a running app with E2E_APP_URL (and the app at its backend with VITE_API_BASE_URL).
 */
const live = process.env.E2E_LIVE === '1'
const appUrl = process.env.E2E_APP_URL
const wav = process.env.E2E_WAV ?? `${process.cwd()}/../spikes/fixtures/narration.wav`

export default defineConfig({
  testDir: 'e2e',
  testMatch: live ? /live\.spec\.ts/ : /mocked\.spec\.ts/,
  timeout: live ? 6 * 60_000 : 60_000,
  retries: 0,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: appUrl ?? 'http://localhost:4173',
    viewport: { width: 1280, height: 800 },
    channel: 'chromium', // the full build: the headless shell's fake microphone is silent
    permissions: ['microphone'],
    video: live ? { mode: 'on', size: { width: 1280, height: 800 } } : 'off',
    launchOptions: {
      args: [
        '--use-fake-ui-for-media-stream',
        '--use-fake-device-for-media-stream',
        // %noloop: play the narration once, then silence.
        ...(live ? [`--use-file-for-fake-audio-capture=${wav}%noloop`] : []),
        '--autoplay-policy=no-user-gesture-required',
        // Machines without a sound card (CI, servers) stall Chromium's audio clock: no worklet would run.
        '--disable-features=AudioServiceSandbox,AudioServiceOutOfProcess',
        '--alsa-output-device=null',
      ],
    },
  },
  webServer: appUrl
    ? undefined
    : {
        command: 'npm run build && npm run preview',
        url: 'http://localhost:4173',
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
      },
})
