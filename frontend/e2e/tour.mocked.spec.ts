import { expect, test, type Page, type WebSocketRoute } from '@playwright/test'
import { cutoutSvg, panelSvg, sheetSvg } from './fixtures'

// The guided tour over the real "Try a sample story", against a backend faked inside the browser: every step
// moves on because the studio's real elements appear (session events, the cast approved, an object selected).
const API = 'http://localhost:8000'
const AVA = 'en-US-AvaMultilingualNeural'

type Json = Record<string, unknown>

const english = [{ code: 'en', locale: 'en-US', name: 'English' }]
const VOICES = {
  available: true,
  default: AVA,
  voices: [
    { name: AVA, display_name: 'Ava', gender: 'Female', accent: 'en-US', languages: english, preview_url: `/voices/${AVA}/preview` },
    { name: 'en-US-BrandonMultilingualNeural', display_name: 'Brandon', gender: 'Male', accent: 'en-US', languages: english, preview_url: '/voices/b/preview' },
  ],
}
const review = { outcome: 'checked', summary: 'Checked', issues: [], fix_instruction: '', model: 'muse-spark-1.3', confidence: 0.9, fixes: 0, rubrics: {} }
const LINA = { id: 'lina', name: 'Lina', description: 'a ten-year-old girl with curly black hair and a yellow raincoat', reference_url: '/media/projects/p1/characters/lina/reference', review }
const coat = { id: 'object:coat', label: 'yellow raincoat', character_id: null, box: { left: 850, top: 600, right: 1150, bottom: 930 }, cutout_url: '/media/projects/p1/m/coat.png' }

function shot(n: number, panel: Json | null = null): Json {
  return { id: `s${n}`, number: n, framing: 'wide', character_ids: ['lina'], setting: 'a rooftop garden at sunset', action: `Lina, beat ${n}`, dialogue: '', duration_ms: 2400, source_turn_ids: [`r-b${n}`], episode: 1, panel }
}
const panel = (n: number) => ({
  revision: 1,
  shown_revision: 1,
  status: 'ready',
  image_url: `/media/projects/p1/panels/s${n}/r1/image`,
  base_image_url: `/media/projects/p1/panels/s${n}/r1/image`,
  width: 1920,
  height: 1280,
  masks: [],
  layers: [],
  outdated: false,
  review,
})

async function fakeBackend(page: Page) {
  const state = { shots: [] as Json[], cast: 'draft', characters: [] as Json[], posted: [] as Json[], start: null as Json | null, ws: null as WebSocketRoute | null }
  const project = () => ({
    id: 'p1',
    title: 'The Rooftop Garden',
    style: 'pencil',
    cast: { status: state.cast, characters: state.characters },
    turns: [],
    shots: state.shots,
    narrations: [],
    animatic: null,
    share_token: null,
  })
  await page.route(`${API}/**`, async (route) => {
    const req = route.request()
    const path = new URL(req.url()).pathname
    if (req.method() === 'POST') state.posted.push({ path, body: req.postDataJSON() as Json })
    const json = (status: number, b: unknown) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
    if (path === '/healthz') return json(200, { status: 'ok' })
    if (path === '/voices') return json(200, VOICES)
    if (path === '/projects' && req.method() === 'POST') return json(201, project())
    if (path === '/projects/p1') return json(200, project())
    if (path === '/projects/p1/cast/approve') {
      state.cast = 'approved'
      return json(200, { approved: true, redrawing: [], job_key: null })
    }
    const render = /^\/projects\/p1\/shots\/(\d+)\/panel$/.exec(path)
    if (render) {
      const n = Number(render[1])
      setTimeout(() => {
        state.shots = state.shots.map((s) => (s.number === n ? shot(n, panel(n)) : s))
        state.ws?.send(JSON.stringify({ type: 'job.updated', kind: 'generate_panel', key: `k${n}`, status: 'succeeded', shot_id: `s${n}`, revision: 1, message: null }))
      }, 300)
      return json(202, { kind: 'generate_panel', key: `k${n}`, enqueued: true, shot_id: `s${n}`, revision: 1 })
    }
    if (path.endsWith('/panel/select')) return json(200, { cached: false, mask: coat })
    if (path.startsWith('/media/projects/p1/speech/')) return route.fulfill({ status: 200, contentType: 'audio/wav', body: '' })
    if (path.startsWith('/media/')) {
      const svg = path.includes('/characters/') ? sheetSvg('Lina') : path.endsWith('coat.png') ? cutoutSvg : panelSvg(Number(/s(\d+)/.exec(path)?.[1] ?? 1))
      return route.fulfill({ status: 200, contentType: 'image/svg+xml', body: svg })
    }
    return json(404, { error: { code: 'not_mocked', message: path } })
  })
  await page.routeWebSocket(/\/ws\/projects\/p1\/session$/, (ws) => {
    state.ws = ws
    const send = (e: Json) => ws.send(JSON.stringify(e))
    ws.onMessage((message) => {
      if (typeof message !== 'string') return
      const m = JSON.parse(message) as Json
      if (!('mode' in m)) return
      state.start = m
      send({ type: 'session.started', mode: m.mode })
      send({ type: 'script.accepted', episodes: [{ number: 1, paragraphs: [{ narration: 'A busy city at sunset.', direction: 'Wide shot. A busy city at sunset.' }, { narration: 'Lina waters tomato plants.', direction: 'Medium shot. Lina waters tomato plants.' }] }] })
      for (const [i, text] of ['A busy city at sunset.', 'Lina waters tomato plants.'].entries()) {
        const n = i + 1
        send({ type: 'script.voiced', paragraph: i, episode: 1, text, original: text, audio_url: `/media/projects/p1/speech/${i}.wav`, duration_ms: 400 })
        send({ type: 'turn.completed', turn: { id: `r-b${n}`, text, start_ms: i * 400, end_ms: n * 400, speaker: null, direction: text, episode: 1 } })
        state.shots.push(shot(n))
        send({ type: 'shot.created', shot: shot(n) })
      }
      setTimeout(() => {
        state.characters = [LINA]
        send({ type: 'cast.proposed', characters: [LINA] })
        send({ type: 'session.ended', turns: 2, shots: 2 })
      }, 300)
    })
  })
  return state
}

const card = (page: Page) => page.getByTestId('tour-card')

async function expectStep(page: Page, id: string, progress: string, phase = 'ready') {
  await expect(card(page)).toHaveAttribute('data-step', id)
  await expect(card(page)).toHaveAttribute('data-phase', phase)
  await expect(page.getByTestId('tour-progress')).toHaveText(progress)
}

test('the guided tour runs the sample story with Ava, step by step, through to Narrate', async ({ page }) => {
  const backend = await fakeBackend(page)
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'New here? Take the 2-minute tour' })).toBeVisible()
  await page.getByTestId('tour-offer').getByRole('button', { name: 'Take the tour' }).click()

  await expectStep(page, 'modes', '1 of 12')
  await expect(page.getByRole('radio', { name: /Read it to me/ })).toBeChecked()
  await expect(page.getByRole('heading', { name: 'Three ways to tell a story' })).toBeFocused()
  await card(page).getByRole('button', { name: 'Next' }).click()

  await expectStep(page, 'voice', '2 of 12')
  await expect(card(page)).toContainText("This one's Ava")
  await expect(page.getByRole('radio', { name: /Ava/ })).toBeChecked()
  await expect(page.getByTestId('tour-highlight')).toBeVisible()
  await card(page).getByRole('button', { name: 'Start the sample story' }).click()
  await expect(page).toHaveURL(/\/projects\/p1$/)
  expect(backend.posted[0]).toEqual({ path: '/projects', body: { title: 'The Rooftop Garden', style: 'pencil' } })

  // Nothing has been read yet: the card says what to do, and Back can't leave the studio.
  await expectStep(page, 'script', '3 of 12', 'waiting')
  await expect(card(page)).toContainText('Press Read it to me.')
  await expect(card(page).getByRole('button', { name: 'Back' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Read it to me' }).click()
  await expect.poll(() => backend.start).toMatchObject({ mode: 'read', voice: AVA, language: 'en-US' })
  await expectStep(page, 'script', '3 of 12')
  await card(page).getByRole('button', { name: 'Next' }).click()

  await expectStep(page, 'shot', '4 of 12')
  await expect(card(page)).toContainText('Muse Spark directs each paragraph into a shot')
  await card(page).getByRole('button', { name: 'Next' }).click()

  // The visitor's turn: Next waits for the real Approve cast.
  await expectStep(page, 'cast', '5 of 12', 'your-turn')
  await expect(card(page)).toContainText('Muse Image draws a reference sheet per character')
  await expect(card(page).getByRole('button', { name: 'Next' })).toBeDisabled()
  await page.getByRole('button', { name: 'Approve cast' }).click()

  await expectStep(page, 'supervisor', '6 of 12')
  await expect(card(page)).toContainText('Muse Glimmer when warm, Muse Spark otherwise')
  await card(page).getByRole('button', { name: 'Next' }).click()

  await expectStep(page, 'panels', '7 of 12')
  await expect(card(page)).toContainText('Muse Image draws with the approved cast')
  await card(page).getByRole('button', { name: 'Next' }).click()

  await expectStep(page, 'select', '8 of 12', 'waiting')
  await expect(card(page)).toContainText('Click a drawn panel to open it.')
  await page.getByRole('button', { name: 'Edit the panel of shot 1' }).click()
  await expectStep(page, 'select', '8 of 12', 'your-turn') // the card now lives inside the editor dialog
  await expect(page.getByTestId('panel-editor').getByTestId('tour-card')).toHaveCount(1)
  const canvas = page.getByTestId('panel-canvas')
  await expect(canvas.locator('canvas').first()).toBeVisible()
  const box = await canvas.boundingBox()
  if (!box) throw new Error('no canvas')
  await page.mouse.click(box.x + box.width * 0.5, box.y + box.height * 0.6)
  await expect(page.getByTestId('selection-status')).toContainText('yellow raincoat')

  await expectStep(page, 'edit', '9 of 12')
  await expect(card(page)).toContainText('Change how it looks')
  await card(page).getByRole('button', { name: 'Next' }).click()

  await expectStep(page, 'export', '10 of 12', 'blocked')
  await expect(card(page)).toContainText('Close the panel editor')
  await page.getByTestId('panel-editor').getByRole('button', { name: 'Close', exact: true }).click()
  await expectStep(page, 'export', '10 of 12')
  await expect(card(page)).toContainText('Export an animatic, with captions')
  await card(page).getByRole('button', { name: 'Next' }).click()

  await expectStep(page, 'share', '11 of 12')
  await card(page).getByRole('button', { name: 'Next' }).click()

  await expectStep(page, 'narrate', '12 of 12')
  await expect(card(page)).toContainText('Muse Voice Transcribe listens as you talk')
  await card(page).getByRole('button', { name: 'Narrate a story' }).click()
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole('radio', { name: /Narrate/ })).toBeChecked()
  await expect(card(page)).toHaveCount(0)
  expect(await page.evaluate(() => localStorage.getItem('frameteller.tour-seen'))).toBe('1')
  await page.reload()
  await expect(page.getByTestId('tour-offer')).toHaveCount(0) // seen: not offered again
  await expect(page.getByRole('button', { name: 'Take the tour' })).toBeVisible() // still in the header
})

test('on a phone the tour card docks at the bottom, and Esc closes it', async ({ page }) => {
  await fakeBackend(page)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  await page.getByRole('button', { name: 'Take the tour' }).first().click()
  await expectStep(page, 'modes', '1 of 12')
  const b = await card(page).boundingBox()
  if (!b) throw new Error('no card')
  expect(Math.round(b.x)).toBe(16)
  expect(Math.round(b.x + b.width)).toBe(390 - 16)
  expect(Math.round(b.y + b.height)).toBe(844 - 16)
  await page.keyboard.press('Escape')
  await expect(card(page)).toHaveCount(0)
  expect(await page.evaluate(() => localStorage.getItem('frameteller.tour-seen'))).toBe('1')
})
