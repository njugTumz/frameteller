import { expect, test, type Page, type WebSocketRoute } from '@playwright/test'
import { cutoutSvg, panelSvg, sheetSvg } from './fixtures'

// The whole studio against a backend faked inside the browser: no network, no credits.
const API = 'http://localhost:8000'

type Json = Record<string, unknown>

function shot(n: number, panel: Json | null = null): Json {
  return {
    id: `s${n}`,
    number: n,
    framing: n === 1 ? 'wide' : 'close_up',
    character_ids: ['mira'],
    setting: 'a rainy alley at night',
    action: n === 1 ? 'Mira walks home alone through the rain.' : 'Mira kneels by a wooden crate.',
    dialogue: '',
    duration_ms: 5200,
    source_turn_ids: [`t-b${n}`],
    panel,
  }
}

const panel = (n: number) => ({
  revision: 1,
  status: 'ready',
  image_url: `/media/projects/p1/panels/s${n}/r1/image`,
  width: 1920,
  height: 1280,
  masks: [],
})

const coat = { id: 'object:coat', label: 'yellow raincoat', character_id: null, box: { left: 850, top: 600, right: 1150, bottom: 930 }, cutout_url: '/media/projects/p1/m/coat.png' }

async function fakeBackend(page: Page) {
  const state = { shots: [] as Json[], cast: 'draft', posted: [] as Json[], frames: [] as { bytes: number; at: number }[], ws: null as WebSocketRoute | null }
  const project = () => ({
    id: 'p1',
    title: 'The Lantern Cat',
    style: 'paper_cutout',
    cast: { status: state.cast, characters: [{ id: 'mira', name: 'Mira', description: 'a girl in a yellow raincoat with a red scarf', reference_url: '/media/projects/p1/characters/mira/reference' }] },
    turns: [],
    shots: state.shots,
  })

  await page.route(`${API}/**`, async (route) => {
    const req = route.request()
    const path = new URL(req.url()).pathname
    const body = req.postDataJSON?.() as Json | null
    if (req.method() === 'POST') state.posted.push({ path, body })
    const json = (status: number, b: unknown) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
    if (path === '/healthz') return json(200, { status: 'ok' })
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
      }, 400)
      return json(202, { kind: 'generate_panel', key: `k${n}`, enqueued: true, shot_id: `s${n}`, revision: 1 })
    }
    if (path.endsWith('/panel/select')) return json(200, { cached: false, mask: coat })
    if (path.startsWith('/media/')) {
      const svg = path.includes('/characters/') ? sheetSvg('Mira') : path.endsWith('coat.png') ? cutoutSvg : panelSvg(Number(/s(\d+)/.exec(path)?.[1] ?? 1))
      return route.fulfill({ status: 200, contentType: 'image/svg+xml', body: svg })
    }
    return json(404, { error: { code: 'not_mocked', message: path } })
  })

  await page.routeWebSocket(/\/ws\/projects\/p1\/session$/, (ws) => {
    state.ws = ws
    let beats = 0
    ws.onMessage((message) => {
      if (typeof message !== 'string') {
        state.frames.push({ bytes: message.length, at: Date.now() })
        return
      }
      const m = JSON.parse(message) as Json
      const send = (e: Json) => ws.send(JSON.stringify(e))
      if ('mode' in m) send({ type: 'session.started', mode: m.mode })
      if (m.type === 'beat') {
        beats += 1
        const text = beats === 1 ? 'Scene one. Night. Mira walks home alone.' : 'She hears a sound under a crate.'
        send({ type: 'transcript.partial', text: '' })
        send({ type: 'turn.completed', turn: { id: `t-b${beats}`, text, start_ms: (beats - 1) * 3000, end_ms: beats * 3000, speaker: null } })
        state.shots = [...state.shots, shot(beats)]
        send({ type: 'shot.created', shot: shot(beats) })
        if (beats === 1) setTimeout(() => send({ type: 'cast.proposed', characters: project().cast.characters }), 300)
      } else if (m.type === 'end') {
        send({ type: 'session.ended', turns: beats, shots: beats })
      }
    })
  })
  return state
}

test('narrate, cut two shots, approve the cast, see drafts, and select an object', async ({ page }) => {
  const backend = await fakeBackend(page)
  await page.goto('/')
  await page.getByLabel('Name the story').fill('The Lantern Cat')
  await page.getByText('Paper cutout', { exact: true }).click()
  await expect(page.getByRole('radio', { name: /co-direct/i })).toBeDisabled()
  await page.getByRole('button', { name: 'Open the studio' }).click()
  await expect(page).toHaveURL(/\/projects\/p1$/)
  expect(backend.posted[0]).toEqual({ path: '/projects', body: { title: 'The Lantern Cat', style: 'paper_cutout' } })

  await page.getByRole('button', { name: 'Start telling' }).click()
  await expect(page.getByText('Listening.')).toBeVisible()

  // Audio: 80 ms frames of 24 kHz mono s16le (3,840 bytes), at real-time pace.
  // (Machines without a sound card take a second or so to start the audio clock.)
  await expect.poll(() => backend.frames.length, { timeout: 10_000 }).toBeGreaterThan(25)
  // Pace over a fresh window: the audio held while the session connected arrives in one burst first.
  const before = backend.frames.length
  await page.waitForTimeout(2000)
  const perSecond = (backend.frames.length - before) / 2
  expect(backend.frames.every((f) => f.bytes === 3840)).toBe(true)
  expect(perSecond).toBeGreaterThanOrEqual(10)
  expect(perSecond).toBeLessThanOrEqual(15)

  await page.keyboard.press('Space')
  await expect(page.getByTestId('shot-card')).toHaveCount(1)
  await expect(page.getByTestId('turn-card').first()).toContainText('Scene one.')
  await page.getByRole('button', { name: /next shot/i }).click()
  await expect(page.getByTestId('shot-card')).toHaveCount(2)
  await expect(page.getByText('Waiting for the cast')).toHaveCount(2)

  await page.getByRole('button', { name: 'Stop telling' }).click()
  await expect(page.getByText('Done. Tell more any time.')).toBeVisible()

  await expect(page.getByRole('img', { name: 'Reference sheet for Mira' })).toBeVisible()
  await page.getByRole('button', { name: 'Approve cast' }).click()
  await expect(page.getByRole('img', { name: /^Shot \d:/ })).toHaveCount(2)
  expect(backend.posted.filter((p) => String(p.path).endsWith('/panel')).map((p) => p.body)).toEqual([{ quality: 'draft' }, { quality: 'draft' }])

  await page.getByRole('button', { name: 'Edit the panel of shot 1' }).click()
  const canvas = page.getByTestId('panel-canvas')
  await expect(canvas.locator('canvas').first()).toBeVisible()
  const box = await canvas.boundingBox()
  if (!box) throw new Error('no canvas')
  await page.mouse.click(box.x + box.width * 0.5, box.y + box.height * 0.6)
  await expect(page.getByTestId('selection-status')).toContainText('yellow raincoat')
  const select = backend.posted.find((p) => String(p.path).endsWith('/select'))?.body as Json
  // Preview pixels inside the 2 px frame border; the box is fractional, so allow a pixel of rounding.
  expect(Math.abs(Number(select.preview_width) - (box.width - 4))).toBeLessThanOrEqual(1)
  await page.keyboard.press('Escape')
  await expect(page.getByTestId('panel-editor')).toHaveCount(0)
})

test('a blocked microphone says how to allow it', async ({ browser }) => {
  const context = await browser.newContext({ permissions: [] })
  const page = await context.newPage()
  await page.addInitScript(() => {
    navigator.mediaDevices.getUserMedia = () => Promise.reject(new DOMException('denied', 'NotAllowedError'))
  })
  await fakeBackend(page)
  await page.goto('/projects/p1')
  await page.getByRole('button', { name: 'Start telling' }).click()
  await expect(page.getByRole('alert')).toContainText('Allow the microphone to start telling.')
  await expect(page.getByRole('alert')).toContainText('address bar')
  await context.close()
})
