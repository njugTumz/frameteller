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

const panel = (n: number, over: Json = {}) => ({
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
  ...over,
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
    narrations: [],
    animatic: null,
    share_token: null,
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

/** A told story with three characters, two drawn shots and a vague "Ember" the narration later reveals. */
async function storyBackend(page: Page, { dropDuringExport = false } = {}) {
  const ref = (id: string) => `/media/projects/p1/characters/${id}/reference`
  const state = {
    characters: [
      { id: 'ada', name: 'Ada', description: 'elderly woman with long silver hair', reference_url: ref('ada') },
      { id: 'pip', name: 'Pip', description: 'tiny young fox kit with reddish-brown fur', reference_url: ref('pip') },
      { id: 'ember', name: 'Ember', description: 'something small and orange', reference_url: ref('ember') },
    ] as Json[],
    shots: [
      { ...shot(1, panel(1)), character_ids: ['ada'], action: 'Ada climbs the lighthouse stairs.' },
      { ...shot(2, panel(2)), character_ids: ['ember'], action: 'Something small and orange moves in the reeds.' },
    ] as Json[],
    animatic: null as Json | null,
    shareToken: null as string | null,
    sharePublic: false,
    narrations: [{ session: 't', duration_ms: 10400, url: '/media/projects/p1/narration/t.wav' }] as Json[],
    posted: [] as { method: string; path: string; body: Json | null }[],
    ws: null as WebSocketRoute | null,
  }
  const project = () => ({
    id: 'p1',
    title: 'The Lighthouse',
    style: 'pencil',
    cast: { status: 'approved', characters: state.characters },
    turns: [],
    shots: state.shots,
    narrations: state.narrations,
    animatic: state.animatic,
    share_token: state.shareToken,
    share_public: state.sharePublic,
  })
  const send = (e: Json) => state.ws?.send(JSON.stringify(e))
  const recast = (from: string, to: string | null) => {
    state.shots = state.shots.map((s) => {
      const ids = s.character_ids as string[]
      if (!ids.includes(from)) return s
      const next = to ? ids.map((c) => (c === from ? to : c)) : ids.filter((c) => c !== from)
      return { ...s, character_ids: [...new Set(next)], panel: { ...(s.panel as Json), outdated: true } }
    })
  }

  await page.route(`${API}/**`, async (route) => {
    const req = route.request()
    const path = new URL(req.url()).pathname
    const method = req.method()
    const body = (method === 'GET' ? null : req.postDataJSON?.()) as Json | null
    if (method !== 'GET') state.posted.push({ method, path, body })
    const json = (status: number, b: unknown) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
    const character = /^\/projects\/p1\/cast\/(\w+)(\/merge)?$/.exec(path)
    if (path === '/healthz') return json(200, { status: 'ok' })
    if (path === '/projects/p1' && method === 'GET') return json(200, project())
    if (character && method === 'PATCH') {
      state.characters = state.characters.map((c) => (c.id === character[1] ? { ...c, name: body?.name } : c))
      return json(200, project())
    }
    if (character && method === 'DELETE') {
      state.characters = state.characters.filter((c) => c.id !== character[1])
      recast(String(character[1]), null)
      return json(200, project())
    }
    if (character?.[2]) {
      state.characters = state.characters.filter((c) => c.id !== character[1])
      recast(String(character[1]), String(body?.into))
      return json(200, project())
    }
    if (path === '/projects/p1/shots/1/panel/select') return json(200, { cached: false, mask: coat })
    if (path === '/projects/p1/shots/1/panel/layers') {
      setTimeout(() => {
        state.shots = state.shots.map((s) =>
          s.number === 1 ? { ...s, panel: panel(1, { shown_revision: 2, image_url: '/media/projects/p1/panels/s1/r1/composites/c.webp', layers: [{ ...body, deleted: false }] }) } : s,
        )
        send({ type: 'job.updated', kind: 'compose_panel', key: 'c1', status: 'succeeded', shot_id: 's1', revision: 1, message: null, progress: null })
      }, 1500)
      return json(202, { kind: 'compose_panel', key: 'c1', enqueued: true, shot_id: 's1', revision: 1 })
    }
    if (path === '/projects/p1/exports/animatic') {
      setTimeout(() => send({ type: 'job.updated', kind: 'export_animatic', key: 'e1', status: 'running', shot_id: null, revision: null, message: null, progress: 0.5 }), 200)
      if (dropDuringExport) {
        // A new studio version goes live mid-export: the socket drops, and the old server finishes the export
        // during its grace period, but its job.updated never reaches this page.
        setTimeout(() => void state.ws?.close({ code: 1012, reason: 'service restart' }), 600)
        setTimeout(() => {
          state.animatic = { url: '/media/projects/p1/exports/animatic-1.mp4', duration_ms: 12400, subtitles: Boolean(body?.subtitles), voiced: true }
        }, 2500)
        return json(202, { kind: 'export_animatic', key: 'export_animatic:p1:e1', enqueued: true, shot_id: null, revision: null })
      }
      setTimeout(() => {
        state.animatic = { url: '/media/projects/p1/exports/animatic-1.mp4', duration_ms: 12400, subtitles: Boolean(body?.subtitles), voiced: true }
        send({ type: 'job.updated', kind: 'export_animatic', key: 'e1', status: 'succeeded', shot_id: null, revision: null, message: null, progress: null })
      }, 1200)
      return json(202, { kind: 'export_animatic', key: 'e1', enqueued: true, shot_id: null, revision: null })
    }
    if (path === '/projects/p1/share' && method === 'POST') {
      state.shareToken = 'tok123'
      state.sharePublic = Boolean((body as { public?: boolean } | null)?.public)
      return json(200, { token: 'tok123', public: state.sharePublic, url: `${API}/s/tok123`, page_url: 'http://localhost:4173/s/tok123' })
    }
    if (path === '/projects/p1/share' && method === 'DELETE') {
      state.shareToken = null
      state.sharePublic = false
      return route.fulfill({ status: 204 })
    }
    if (path === '/shares/tok123') {
      if (!state.shareToken) return json(404, { error: { code: 'share_not_found', message: 'This link was turned off, or never existed.' } })
      return json(200, {
        title: 'The Lighthouse',
        style: 'pencil',
        shots: state.shots.map((s) => ({ number: s.number, framing: s.framing, action: s.action, dialogue: '', duration_ms: s.duration_ms, image_url: `/shares/tok123/panels/${s.number}` })),
        animatic: state.animatic ? { url: '/shares/tok123/animatic', duration_ms: 12400 } : null,
        public: state.sharePublic,
      })
    }
    if (path.endsWith('.mp4') || path.endsWith('/animatic')) return route.fulfill({ status: 200, contentType: 'video/mp4', body: '' })
    if (path.startsWith('/media/') || path.startsWith('/shares/')) {
      const svg = path.includes('/characters/') ? sheetSvg(path.split('/')[4] ?? '') : path.endsWith('coat.png') ? cutoutSvg : panelSvg(Number(/(?:s|panels\/)(\d+)/.exec(path)?.[1] ?? 1))
      return route.fulfill({ status: 200, contentType: 'image/svg+xml', body: svg })
    }
    return json(404, { error: { code: 'not_mocked', message: path } })
  })

  await page.routeWebSocket(/\/ws\/projects\/p1\/session$/, (ws) => {
    state.ws = ws
    ws.onMessage((message) => {
      if (typeof message !== 'string') return
      const m = JSON.parse(message) as Json
      if ('mode' in m) {
        send({ type: 'session.started', mode: m.mode })
        setTimeout(() => send({ type: 'audio.silent', after_ms: 8000, level: 0.001 }), 300)
      }
      if (m.type === 'beat') {
        // The reveal: "something small and orange" was Pip all along.
        const revealed: Json = { ...(state.shots[1] as Json), character_ids: ['pip'], action: 'Pip, the fox kit, moves in the reeds.' }
        state.shots = [state.shots[0] as Json, { ...revealed, panel: { ...(revealed.panel as Json), outdated: true } }]
        state.characters = state.characters.filter((c) => c.id !== 'ember')
        send({ type: 'transcript.partial', text: '' })
        send({ type: 'shot.updated', shot: revealed })
      }
      if (m.type === 'end') send({ type: 'session.ended', turns: 0, shots: 0, heard: false })
    })
  })
  return state
}

test('manage the cast, follow a reveal, hear the silence warning, move, export and share', async ({ page }) => {
  const backend = await storyBackend(page)
  await page.goto('/projects/p1')
  const cards = page.getByTestId('character-card')
  await expect(cards).toHaveCount(3)

  // Rename: Ada becomes Ada Vell.
  await cards.filter({ hasText: 'Ada' }).getByRole('button', { name: 'Rename' }).click()
  await page.getByLabel('New name for Ada').fill('Ada Vell')
  await page.getByRole('button', { name: 'Save' }).click()
  await expect(page.getByRole('heading', { name: 'Ada Vell' })).toBeVisible()
  expect(backend.posted.at(-1)).toEqual({ method: 'PATCH', path: '/projects/p1/cast/ada', body: { name: 'Ada Vell' } })

  // Silence warning, then a reveal: Ember turns out to be Pip.
  await page.getByRole('button', { name: 'Start telling' }).click()
  await expect(page.getByTestId('silence-notice')).toContainText('We can’t hear you')
  await expect(page.getByTestId('silence-notice').locator('strong')).not.toBeEmpty()
  await page.getByRole('button', { name: /next shot/i }).click()
  const second = page.locator('[data-testid="shot-card"][data-shot="2"]')
  await expect(second).toContainText('Pip, the fox kit, moves in the reeds.')
  await expect(second).toHaveAttribute('data-outdated', 'true')
  await expect(second.getByRole('button', { name: 'Draw again' })).toBeVisible()
  await expect(cards).toHaveCount(2) // the guessed Ember left the cast
  await page.getByRole('button', { name: 'Stop telling' }).click()
  await expect(page.getByText('We didn’t hear anything. Check your microphone.')).toBeVisible()

  // Merge Pip into Ada Vell (contrived, but it exercises the path), then remove her: shots keep their action.
  await cards.filter({ hasText: 'Pip' }).getByRole('button', { name: 'Merge into…' }).click()
  await page.getByLabel('Pip is really…').selectOption({ label: 'Ada Vell' })
  await page.getByRole('button', { name: 'Merge', exact: true }).click()
  await expect(cards).toHaveCount(1)
  expect(backend.posted.at(-1)).toEqual({ method: 'POST', path: '/projects/p1/cast/pip/merge', body: { into: 'ada' } })
  await expect(page.locator('[data-testid="shot-card"][data-shot="2"]')).toContainText('With Ada Vell')
  await cards.getByRole('button', { name: 'Remove' }).click()
  await page.getByRole('button', { name: 'Remove Ada Vell' }).click()
  await expect(cards).toHaveCount(0)
  await expect(page.locator('[data-testid="shot-card"][data-shot="1"]')).toContainText('Ada climbs the lighthouse stairs.')

  // Move the selected raincoat: saved as a layer, composited on a clean plate.
  await page.getByRole('button', { name: 'Edit the panel of shot 1' }).click()
  const canvas = page.getByTestId('panel-canvas')
  await expect(canvas.locator('canvas').first()).toBeVisible()
  const box = await canvas.boundingBox()
  if (!box) throw new Error('no canvas')
  await page.mouse.click(box.x + box.width * 0.5, box.y + box.height * 0.6)
  await expect(page.getByTestId('selection-status')).toContainText('yellow raincoat')
  await canvas.focus()
  await page.keyboard.press('Shift+ArrowRight')
  await expect(page.getByText('Preparing the background…')).toBeVisible()
  expect(backend.posted.find((p) => p.path.endsWith('/layers'))?.body).toEqual({ object_id: 'object:coat', dx: 50, dy: 0, scale: 1, deleted: false })
  await expect(page.getByText('Preparing the background…')).toHaveCount(0, { timeout: 5000 })
  await page.keyboard.press('Escape')
  await expect(page.getByRole('img', { name: /^Shot 1:/ })).toHaveAttribute('src', /composites\/c\.webp$/)

  // Export: progress, then an inline player and a download. The kept recording can be deleted.
  await expect(page.getByTestId('recording-kept')).toBeVisible()
  await page.getByLabel('Burn in subtitles').check()
  await page.getByRole('button', { name: 'Export animatic' }).click()
  await expect(page.getByText(/Rendering the animatic… 50%/)).toBeVisible()
  await expect(page.getByTestId('animatic-player')).toBeVisible({ timeout: 5000 })
  await expect(page.getByRole('link', { name: 'Download MP4' })).toHaveAttribute('href', /animatic-1\.mp4\?download=1$/)
  await expect(page.getByRole('link', { name: 'Download storyboard PDF' })).toHaveAttribute('href', `${API}/projects/p1/exports/storyboard.pdf`)
  expect(backend.posted.find((p) => p.path.endsWith('/exports/animatic'))?.body).toEqual({ subtitles: true })

  // Share: an unlisted link that previews on X, a read-only page, made public, then turned off.
  const robots = page.locator('meta[name="robots"]')
  await expect(robots).toHaveAttribute('content', 'noindex, nofollow') // the studio itself is never indexed
  await page.getByRole('button', { name: 'Create a share link' }).click()
  await expect(page.getByLabel('Share link')).toHaveValue(`${API}/s/tok123`)
  await expect(page.getByLabel('Make public')).not.toBeChecked()
  expect(backend.posted.find((p) => p.path.endsWith('/share'))?.body).toEqual({ public: false })
  await page.goto('/s/tok123')
  await expect(page.getByRole('heading', { name: 'The Lighthouse' })).toBeVisible()
  await expect(page.getByTestId('shared-shot')).toHaveCount(2)
  await expect(page.getByTestId('shared-animatic')).toBeVisible()
  await expect(robots).toHaveAttribute('content', 'noindex, nofollow') // unlisted
  await page.goto('/projects/p1')
  await page.getByLabel('Make public').click() // it ticks once the backend confirms
  await expect(page.getByLabel('Make public')).toBeChecked()
  await expect(page.getByText('Search engines may list this page.')).toBeVisible()
  await expect(page.getByLabel('Share link')).toHaveValue(`${API}/s/tok123`) // the same link
  await page.goto('/s/tok123')
  await expect(page.getByTestId('shared-shot')).toHaveCount(2)
  await expect(robots).toHaveCount(0) // public: indexable
  await page.goto('/projects/p1')
  await page.getByRole('button', { name: 'Turn off the link' }).click()
  await expect(page.getByRole('button', { name: 'Create a share link' })).toBeVisible()
  await page.goto('/s/tok123')
  await expect(page.getByText('This link was turned off, or never existed.')).toBeVisible()
  await page.getByRole('button', { name: 'Make your own' }).click()
  await expect(page).toHaveURL(/\/$/)
})

test('a socket dropped mid-export (a new studio version) still ends with the finished animatic', async ({ page }) => {
  await storyBackend(page, { dropDuringExport: true })
  await page.goto('/projects/p1')
  await expect(page.getByTestId('character-card')).toHaveCount(3)
  // Tell, then stop: the session socket stays open for job updates.
  await page.getByRole('button', { name: 'Start telling' }).click()
  await expect(page.getByTestId('silence-notice')).toBeVisible()
  await page.getByRole('button', { name: 'Stop telling' }).click()

  await page.getByRole('button', { name: 'Export animatic' }).click()
  await expect(page.getByText(/Rendering the animatic… 50%/)).toBeVisible()
  // The socket drops: the page says so, fetches the project again and finds the export there.
  await expect(page.getByText('Updating the studio, your work is safe')).toBeVisible()
  await expect(page.getByTestId('animatic-player')).toBeVisible({ timeout: 15_000 })
  await expect(page.getByRole('link', { name: 'Download MP4' })).toHaveAttribute('href', /animatic-1\.mp4\?download=1$/)
  await expect(page.getByText('Updating the studio, your work is safe')).toHaveCount(0)
})

async function statusBackend(page: Page, status: { paused: boolean; full: boolean }) {
  const posted: string[] = []
  await page.route(`${API}/**`, async (route) => {
    const req = route.request()
    const path = new URL(req.url()).pathname
    if (req.method() === 'POST') posted.push(path)
    const json = (code: number, b: unknown) => route.fulfill({ status: code, contentType: 'application/json', body: JSON.stringify(b) })
    if (path === '/healthz') return json(200, { status: 'ok' })
    if (path === '/status') return json(200, { ...status, limits: {} })
    if (path === '/shares/tok12345') return json(200, { title: 'The Lantern Cat', style: 'pencil', public: false, shots: [], animatic: null })
    if (status.paused) return json(503, { error: { code: 'paused', message: 'Frameteller is taking a short break. Back soon.' } })
    return json(404, { error: { code: 'not_found', message: 'nope' } })
  })
  return posted
}

test('the kill switch shows "back soon" but shared storyboards still open', async ({ page }) => {
  await statusBackend(page, { paused: true, full: false })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Back soon.' })).toBeVisible()
  await page.goto('/projects/p1')
  await expect(page.getByRole('heading', { name: 'Back soon.' })).toBeVisible()
  await page.goto('/s/tok12345')
  await expect(page.getByText('The Lantern Cat').first()).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Back soon.' })).toHaveCount(0)
})

test('a full studio says come back tomorrow, and the privacy page is one click away', async ({ page }) => {
  const posted = await statusBackend(page, { paused: false, full: true })
  await page.goto('/')
  await expect(page.getByText('The studio is full for today. Come back tomorrow.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Open the studio' })).toBeDisabled()
  expect(posted).toEqual([])

  await page.getByRole('link', { name: 'What we keep, and for how long' }).click()
  await expect(page.getByRole('heading', { name: 'Privacy', level: 1 })).toBeVisible()
  await expect(page.getByText(/30 days after they were last/)).toBeVisible()
  await expect(page.getByText(/does not use your content to train/)).toBeVisible()
})
