import { expect, test, type Page } from '@playwright/test'
import { panelSvg, sheetSvg } from './fixtures'

// Redraw (ADR 0022) against a backend faked inside the browser: what should change, the drawing kept on screen
// while the new one is drawn, Keep previous, a refusal with its suggested change, and the phone layout.
const API = 'http://localhost:8000'

type Json = Record<string, unknown>
const image = (r: number) => `/media/projects/p1/panels/s1/r${r}/image`

async function redrawBackend(page: Page, { refuse = false } = {}) {
  const state = {
    posted: [] as Json[],
    revision: 1,
    shownImage: 1, // the drawing revision `revision` shows
    versions: [] as { revision: number; image: number }[],
    drawing: false,
    suggestion: null as string | null,
  }
  const panel = () => ({
    revision: state.revision,
    shown_revision: state.revision,
    status: 'ready',
    image_url: image(state.shownImage),
    base_image_url: image(state.shownImage),
    width: 1920,
    height: 1280,
    masks: [],
    layers: [],
    outdated: false,
    review: null,
    versions: state.versions.map((v) => ({ revision: v.revision, image_url: image(v.image), width: 1920, height: 1280 })),
    suggested_change: state.suggestion,
  })
  const project = () => ({
    id: 'p1',
    title: 'The Lighthouse',
    style: 'pencil',
    cast: {
      status: 'approved',
      characters: [{ id: 'pip', name: 'Pip', description: 'a tiny orange fox with a white-tipped tail', reference_url: '/media/projects/p1/characters/pip/reference' }],
    },
    turns: [],
    shots: [
      {
        id: 's1',
        number: 1,
        framing: 'medium',
        character_ids: ['pip'],
        setting: 'a lighthouse balcony at dusk',
        action: 'Pip watches the boats come home.',
        dialogue: '',
        duration_ms: 4000,
        source_turn_ids: ['t1'],
        panel: panel(),
      },
    ],
    narrations: [],
    animatic: null,
    share_token: null,
    continuity_checks: false,
    supervisor: [],
  })

  await page.route(`${API}/**`, async (route) => {
    const req = route.request()
    const path = new URL(req.url()).pathname
    const body = (req.postDataJSON?.() as Json | null) ?? null
    if (req.method() !== 'GET') state.posted.push({ method: req.method(), path, body })
    const json = (status: number, b: unknown) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
    if (path === '/healthz') return json(200, { status: 'ok' })
    if (path === '/status') return json(200, { open: true, paused: false, full: false, message: null })
    if (path === '/projects/p1') return json(200, project())
    if (path === '/projects/p1/shots/1/panel' && req.method() === 'POST') {
      state.drawing = true
      setTimeout(() => {
        state.drawing = false
        if (refuse) {
          state.suggestion = 'keep it calm and friendly: Pip watches the boats come home'
          return
        }
        state.versions = [{ revision: state.revision, image: state.shownImage }, ...state.versions]
        state.revision += 1
        state.shownImage = state.revision
      }, 1500)
      return json(202, { kind: 'generate_panel', key: `generate_panel:p1:s1:r${state.revision + 1}`, enqueued: true, shot_id: 's1', revision: state.revision + 1 })
    }
    const restore = /^\/projects\/p1\/shots\/1\/panel\/versions\/(\d+)$/.exec(path)
    if (restore) {
      const wanted = state.versions.find((v) => v.revision === Number(restore[1]))
      if (!wanted) return json(404, { error: { code: 'object_not_found', message: 'No such drawing.' } })
      state.versions = [{ revision: state.revision, image: state.shownImage }, ...state.versions.filter((v) => v !== wanted)]
      state.revision += 1
      state.shownImage = wanted.image
      return json(200, project())
    }
    if (path.startsWith('/projects/p1/jobs/')) {
      if (state.drawing) return json(200, { key: path.split('/').at(-1), status: 'running', message: null })
      return refuse
        ? json(200, { key: path.split('/').at(-1), status: 'failed', message: "Muse Image's safety filter turned this frame down twice. Redraw it and say plainly what happens, by look and action, or use the suggested change." })
        : json(200, { key: path.split('/').at(-1), status: 'succeeded', message: null })
    }
    if (path.startsWith('/media/')) {
      const svg = path.includes('/characters/') ? sheetSvg('Pip') : panelSvg(Number(/r(\d+)\/image/.exec(path)?.[1] ?? 1))
      return route.fulfill({ status: 200, contentType: 'image/svg+xml', body: svg })
    }
    return json(404, { error: { code: 'not_mocked', message: path } })
  })
  return state
}

const card = (page: Page) => page.locator('[data-testid="shot-card"][data-shot="1"]')

test('Redraw with what should change, the drawing kept while drawing, then Keep previous', async ({ page }) => {
  const backend = await redrawBackend(page)
  await page.goto('/projects/p1')

  const shot = card(page)
  await expect(shot.getByRole('img', { name: /Shot 1/ })).toHaveAttribute('src', /r1\/image/)
  await shot.getByRole('button', { name: 'Redraw shot 1' }).click()
  await shot.getByRole('textbox', { name: /What should change/ }).fill('make it night')
  await shot.getByRole('button', { name: 'Redraw', exact: true }).click()
  await expect.poll(() => backend.posted.at(-1)).toEqual({
    method: 'POST',
    path: '/projects/p1/shots/1/panel',
    body: { quality: 'draft', redraw: true, change: 'make it night', surprise: false },
  })

  // Never a blank or silent wait: the drawing before stays, with how long it takes.
  await expect(shot.getByRole('img', { name: /the drawing before/ })).toHaveAttribute('src', /r1\/image/)
  await expect(shot.getByTestId('drawing-overlay')).toBeVisible()

  // The new drawing arrives (the quiet-job check settles it with no session socket open), then the choice.
  const choice = shot.getByTestId('redraw-choice')
  await expect(choice).toBeVisible({ timeout: 40_000 })
  await expect(shot.getByRole('img', { name: /^Shot 1:/ })).toHaveAttribute('src', /r2\/image/)
  await choice.getByRole('button', { name: 'Keep previous' }).click()
  await expect.poll(() => backend.posted.at(-1)?.path).toBe('/projects/p1/shots/1/panel/versions/1')
  await expect(choice).toHaveCount(0)
  await expect(shot.getByRole('img', { name: /^Shot 1:/ })).toHaveAttribute('src', /r1\/image/)

  // And back again later, from the panel's versions in the editor.
  await shot.getByRole('button', { name: 'Edit the panel of shot 1' }).click()
  const editor = page.getByTestId('panel-editor')
  await expect(editor.getByTestId('versions').getByRole('img', { name: 'Shot 1, revision 2' })).toBeVisible()
  await expect(editor.getByRole('button', { name: 'Draw final' })).toBeVisible()
  await expect(editor.getByRole('button', { name: 'Redraw shot 1' })).toBeVisible()
  await editor.getByRole('button', { name: 'Use revision 2 again' }).click()
  await expect.poll(() => backend.posted.at(-1)?.path).toBe('/projects/p1/shots/1/panel/versions/2')
})

test('Surprise me, and a refusal that says what to change and offers the suggested change', async ({ page }) => {
  const backend = await redrawBackend(page, { refuse: true })
  await page.goto('/projects/p1')

  const shot = card(page)
  await shot.getByRole('button', { name: 'Redraw shot 1' }).click()
  await shot.getByRole('button', { name: 'Surprise me' }).click()
  await expect.poll(() => backend.posted.at(-1)?.body).toEqual({ quality: 'draft', redraw: true, change: '', surprise: true })

  await expect(shot.getByRole('alert')).toContainText('say plainly what happens', { timeout: 40_000 })
  await expect(shot.getByRole('img', { name: /the drawing before/ })).toHaveAttribute('src', /r1\/image/) // no dead end
  const box = shot.getByRole('textbox', { name: /What should change/ })
  await expect(box).toHaveValue('keep it calm and friendly: Pip watches the boats come home')
  await shot.getByRole('button', { name: 'Redraw', exact: true }).click()
  await expect.poll(() => backend.posted.at(-1)?.body).toEqual({
    quality: 'draft',
    redraw: true,
    change: 'keep it calm and friendly: Pip watches the boats come home',
    surprise: false,
  })
})

test.describe('on a phone', () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true })

  test('Redraw is a visible button with its label, and its box fits the screen', async ({ page }) => {
    await redrawBackend(page)
    await page.goto('/projects/p1')
    const redraw = card(page).getByRole('button', { name: 'Redraw shot 1' })
    await redraw.scrollIntoViewIfNeeded()
    await expect(redraw).toBeVisible()
    await expect(redraw).toHaveText('Redraw')
    await redraw.tap()
    const box = card(page).getByTestId('redraw-box')
    await expect(box.getByRole('button', { name: 'Surprise me' })).toBeVisible()
    const width = await page.evaluate(() => document.documentElement.scrollWidth)
    expect(width).toBeLessThanOrEqual(390)
    const bounds = await box.boundingBox()
    expect(bounds && bounds.x >= 0 && bounds.x + bounds.width <= 390).toBe(true)
  })
})
