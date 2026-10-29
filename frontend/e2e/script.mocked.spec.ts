import { expect, test, type Page, type WebSocketRoute } from '@playwright/test'
import { panelSvg, sheetSvg } from './fixtures'

// Three ways to tell it (ADR 0015), against a backend faked inside the browser: no network, no credits.
const API = 'http://localhost:8000'
const BRANDON = 'en-US-BrandonMultilingualNeural'
const ROOFTOP = 'Wide shot. Lena feeds the pigeons on the roof.\n\nA paper kite drifts down into her hands.\n\nEpisode 2\n\nThe kite pulls her up into the night.'

type Json = Record<string, unknown>

/**
 * 0.4 s of silence as 8 kHz mono 16-bit WAV, as a string: every header byte is below 128, so it survives the
 * text body unchanged. (The real service returns 24 kHz; the browser only has to play something.)
 */
function silentWav(ms = 400): string {
  const u32 = (n: number) => String.fromCharCode(n & 255, (n >> 8) & 255, (n >> 16) & 255, (n >> 24) & 255)
  const u16 = (n: number) => String.fromCharCode(n & 255, (n >> 8) & 255)
  const bytes = ms * 16
  return `RIFF${u32(36 + bytes)}WAVEfmt ${u32(16)}${u16(1)}${u16(1)}${u32(8000)}${u32(16000)}${u16(2)}${u16(16)}data${u32(bytes)}${'\0'.repeat(bytes)}`
}

const VOICES = {
  available: true,
  default: BRANDON,
  voices: [
    {
      name: BRANDON,
      display_name: 'Brandon',
      gender: 'Male',
      accent: 'en-US',
      languages: [
        { code: 'en', locale: 'en-US', name: 'English' },
        { code: 'fr', locale: 'fr-FR', name: 'Français' },
      ],
      preview_url: `/voices/${BRANDON}/preview`,
    },
    {
      name: 'en-GB-AdaMultilingualNeural',
      display_name: 'Ada',
      gender: 'Female',
      accent: 'en-GB',
      languages: [
        { code: 'en', locale: 'en-GB', name: 'English' },
        { code: 'fr', locale: 'fr-FR', name: 'Français' },
      ],
      preview_url: '/voices/en-GB-AdaMultilingualNeural/preview',
    },
  ],
}

const EPISODES = [
  {
    number: 1,
    paragraphs: [
      { narration: 'Lena feeds the pigeons on the roof.', direction: 'Wide shot. Lena feeds the pigeons on the roof.' },
      { narration: 'A paper kite drifts down into her hands.', direction: 'A paper kite drifts down into her hands.' },
    ],
  },
  { number: 2, paragraphs: [{ narration: 'The kite pulls her up into the night.', direction: 'The kite pulls her up into the night.' }] },
]

function shot(n: number, episode: number): Json {
  return {
    id: `s${n}`,
    number: n,
    framing: 'wide',
    character_ids: ['lena'],
    setting: 'a rooftop at night',
    action: `Lena, beat ${n}`,
    dialogue: '',
    duration_ms: 2400,
    source_turn_ids: [`r-b${n}`],
    episode,
    panel: null,
  }
}

async function fakeBackend(page: Page) {
  const state = { shots: [] as Json[], posted: [] as Json[], start: null as Json | null, controls: [] as Json[], previews: [] as string[], speech: 0, ws: null as WebSocketRoute | null }
  const project = () => ({
    id: 'p1',
    title: 'Rooftop Kite',
    style: 'pencil',
    cast: { status: 'draft', characters: [{ id: 'lena', name: 'Lena', description: 'a girl in a green coat', reference_url: '/media/projects/p1/characters/lena/reference' }] },
    turns: [],
    shots: state.shots,
    narrations: [],
    animatic: null,
    share_token: null,
  })
  await page.route(`${API}/**`, async (route) => {
    const req = route.request()
    const url = new URL(req.url())
    const path = url.pathname
    if (req.method() === 'POST') state.posted.push({ path, body: req.postDataJSON() as Json })
    const json = (status: number, b: unknown) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
    if (path === '/healthz') return json(200, { status: 'ok' })
    if (path === '/voices') return json(200, VOICES)
    if (path.startsWith('/voices/') && path.endsWith('/preview')) {
      state.previews.push(`${path.split('/')[2]} ${url.searchParams.get('language')}`)
      return route.fulfill({ status: 200, contentType: 'audio/wav', body: silentWav() })
    }
    if (path === '/projects' && req.method() === 'POST') return json(201, project())
    if (path === '/projects/p1') return json(200, project())
    if (path.startsWith('/media/projects/p1/speech/')) {
      state.speech += 1
      return route.fulfill({ status: 200, contentType: 'audio/wav', body: silentWav() })
    }
    if (path.startsWith('/media/')) return route.fulfill({ status: 200, contentType: 'image/svg+xml', body: path.includes('/characters/') ? sheetSvg('Lena') : panelSvg(1) })
    return json(404, { error: { code: 'not_mocked', message: path } })
  })
  return state
}

async function openStudio(page: Page, mode: RegExp) {
  await page.goto('/')
  await page.getByLabel('Name the story').fill('Rooftop Kite')
  await page.getByRole('radio', { name: mode }).check()
  await page.getByLabel('Your script').fill(ROOFTOP)
  await expect(page.getByText(`${ROOFTOP.length} / 4,000`)).toBeVisible()
}

test('narrate is the default way to tell it, with the microphone and Space', async ({ page }) => {
  await fakeBackend(page)
  await page.goto('/')
  await expect(page.getByRole('radio', { name: /Narrate/ })).toBeChecked()
  await expect(page.getByRole('radio', { name: /Teleprompter/ })).toBeEnabled()
  await expect(page.getByRole('radio', { name: /Read it to me/ })).toBeEnabled()
  await expect(page.getByLabel('Your script')).toHaveCount(0)
  await expect(page.getByText("You'll allow the microphone next.")).toBeVisible()
})

test('teleprompter: the script scrolls with the current paragraph highlighted, and paragraphs become shots', async ({ page }) => {
  const backend = await fakeBackend(page)
  await page.routeWebSocket(/\/ws\/projects\/p1\/session$/, (ws) => {
    backend.ws = ws
    ws.onMessage((message) => {
      if (typeof message !== 'string') return
      const m = JSON.parse(message) as Json
      const send = (e: Json) => ws.send(JSON.stringify(e))
      if ('mode' in m) {
        backend.start = m
        send({ type: 'session.started', mode: m.mode })
        send({ type: 'script.accepted', episodes: EPISODES })
        // The reader finishes the first paragraph and pauses: the server cuts it and moves on.
        setTimeout(() => {
          send({ type: 'turn.completed', turn: { id: 'r-b1', text: 'Lena feeds the pigeons on the roof.', start_ms: 0, end_ms: 2600, speaker: null, direction: 'Wide shot. Lena feeds the pigeons on the roof.', episode: 1 } })
          send({ type: 'teleprompter.advanced', paragraph: 1 })
          backend.shots.push(shot(1, 1))
          send({ type: 'shot.created', shot: shot(1, 1) })
        }, 1500)
      } else if (m.type === 'end') {
        send({ type: 'session.ended', turns: 1, shots: 1 })
      }
    })
  })
  await openStudio(page, /Teleprompter/)
  await page.getByRole('button', { name: 'Open the studio' }).click()
  await expect(page).toHaveURL(/\/projects\/p1$/)

  await page.getByRole('button', { name: 'Start telling' }).click()
  await expect(page.getByText('Listening.')).toBeVisible()
  expect(backend.start).toMatchObject({ mode: 'teleprompter', script: ROOFTOP, script_format: 'text', keep_audio: true })

  const prompter = page.getByTestId('teleprompter')
  await expect(prompter.locator('[data-state="current"]')).toHaveText('Lena feeds the pigeons on the roof.')
  await expect(prompter.locator('[data-state="next"]')).toHaveText('A paper kite drifts down into her hands.')
  await expect(prompter.locator('[data-state="current"]')).toHaveText('A paper kite drifts down into her hands.') // auto-cut
  await expect(page.getByTestId('shot-card')).toHaveCount(1)
  await expect(page.getByText('Episode 2', { exact: true })).toBeVisible()

  await page.getByRole('button', { name: 'Stop telling' }).click()
  await expect(page.getByText('Done. Tell more any time.')).toBeVisible()
})

test('read it to me: pick a voice and language, hear a preview, then listen and go on after the episode break', async ({ page }) => {
  const backend = await fakeBackend(page)
  await page.routeWebSocket(/\/ws\/projects\/p1\/session$/, (ws) => {
    backend.ws = ws
    const send = (e: Json) => ws.send(JSON.stringify(e))
    const voiced = (paragraph: number, episode: number, text: string, original: string) =>
      send({ type: 'script.voiced', paragraph, episode, text, original, audio_url: `/media/projects/p1/speech/${paragraph}.wav`, duration_ms: 400 })
    const created = (s: Json) => {
      backend.shots.push(s) // the project the studio fetches again has it too
      send({ type: 'shot.created', shot: s })
    }
    const turn = (n: number, text: string, episode: number) =>
      send({ type: 'turn.completed', turn: { id: `r-b${n}`, text, start_ms: (n - 1) * 400, end_ms: n * 400, speaker: null, direction: text, episode } })
    ws.onMessage((message) => {
      if (typeof message !== 'string') return
      const m = JSON.parse(message) as Json
      if ('mode' in m) {
        backend.start = m
        send({ type: 'session.started', mode: m.mode })
        send({ type: 'script.accepted', episodes: EPISODES })
        voiced(0, 1, 'Lena nourrit les pigeons sur le toit.', 'Lena feeds the pigeons on the roof.')
        turn(1, 'Lena nourrit les pigeons sur le toit.', 1)
        created(shot(1, 1))
        voiced(1, 1, 'Un cerf-volant en papier descend dans ses mains.', 'A paper kite drifts down into her hands.')
        turn(2, 'Un cerf-volant en papier descend dans ses mains.', 1)
        created(shot(2, 1))
        setTimeout(() => send({ type: 'script.paused', next_paragraph: 2, next_episode: 2, reason: 'episode' }), 300)
        return
      }
      backend.controls.push(m)
      if (m.type === 'pause') send({ type: 'script.paused', next_paragraph: 2, next_episode: 2, reason: 'user' })
      if (m.type === 'continue') {
        send({ type: 'script.resumed', next_paragraph: 2 })
        voiced(2, 2, 'Le cerf-volant l’emporte dans la nuit.', 'The kite pulls her up into the night.')
        turn(3, 'Le cerf-volant l’emporte dans la nuit.', 2)
        created(shot(3, 2))
        setTimeout(() => send({ type: 'session.ended', turns: 3, shots: 3 }), 200)
      }
    })
  })
  await openStudio(page, /Read it to me/)
  await expect(page.getByLabel('Keep my narration for the animatic')).toHaveCount(0)
  await page.getByRole('button', { name: 'Hear Ada' }).click()
  await expect.poll(() => backend.previews).toEqual(['en-GB-AdaMultilingualNeural en-GB']) // Ada's own English: en-US is not hers
  await page.getByRole('radio', { name: /Brandon/ }).check()
  await page.getByLabel('Language', { exact: true }).selectOption('fr-FR')
  await expect(page.getByText('the script is translated before it')).toBeVisible()
  await page.getByRole('button', { name: 'Open the studio' }).click()
  await expect(page).toHaveURL(/\/projects\/p1$/)

  await expect(page.getByText('Brandon will read it in Français.')).toBeVisible()
  await page.getByRole('button', { name: 'Read it to me' }).click()
  expect(backend.start).toMatchObject({ mode: 'read', script: ROOFTOP, voice: BRANDON, language: 'fr-FR', keep_audio: false })

  // The translated text is what the voice reads, in the script view and the transcript rail.
  await expect(page.getByTestId('teleprompter')).toContainText('Lena nourrit les pigeons sur le toit.')
  await expect(page.getByTestId('turn-card').first()).toContainText('Lena nourrit les pigeons sur le toit.')
  await expect.poll(() => backend.speech).toBeGreaterThanOrEqual(1) // the browser plays the voiced paragraphs
  await expect(page.getByText(/Episode 2 is next/)).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Episode 1' })).toHaveCount(0) // one episode drawn so far

  await page.getByRole('button', { name: 'Start episode 2 now' }).click()
  await expect(page.getByTestId('shot-card')).toHaveCount(3)
  await expect(page.getByRole('heading', { name: 'Episode 2' })).toBeVisible()
  await expect(page.getByTestId('shot-card').nth(2)).toHaveAttribute('data-shot', '1') // numbering restarts
  await expect(page.getByText('Done. Read it again any time.')).toBeVisible()
  expect(backend.controls).toEqual([{ type: 'continue' }])
})
