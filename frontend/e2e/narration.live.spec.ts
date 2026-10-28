import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { expect, test, type Page } from '@playwright/test'
import { liveWav, outDir, sourceWav } from '../playwright.config'
import { alignSent, BEATS_MS, BYTES_PER_MS, envelope, LEAD_MS, pcm, readWav } from './narration'

/**
 * Opt-in (E2E_LIVE=1), spends Meta credits (about USD 0.15-0.20): the real backend and models, narrating
 * spikes/fixtures/narration.wav through Chromium's fake microphone with a beat at each paragraph. Then it
 * moves an object (one clean plate), exports the animatic, downloads it and the storyboard PDF to spikes/out,
 * and makes a share link.
 *
 *   E2E_API_URL   the backend the app talks to (default http://localhost:8000), for project reads
 *   E2E_APP_URL   a running app (staging); otherwise the config builds and previews the local app
 *   E2E_TARGET    names the outputs in spikes/out: frameteller-e2e-<target>.webm and .json (default local)
 *   E2E_SPEND_LOG a local backend's spend log, to report what the run cost
 *   E2E_SCREENSHOTS=1 also save the studio, light and dark, to docs/img
 */
const API = process.env.E2E_API_URL ?? 'http://localhost:8000'
const TARGET = process.env.E2E_TARGET ?? 'local'
const SPEND_LOG = process.env.E2E_SPEND_LOG
const SHOTS = BEATS_MS.length

test.skip(!existsSync(sourceWav), `needs the narration recording at ${sourceWav}`)
test.skip(!!process.env.CI && !process.env.MODEL_API_KEY, 'needs a backend with a Meta key')

interface Mask { label: string; box: { left: number; top: number; right: number; bottom: number } }
type Panel = { width: number; height: number; masks: Mask[] } | null

const timeline: { at_s: number; step: string }[] = []
let projectId = ''
const outputs: Record<string, string> = {}
let t0 = Date.now()
const mark = (step: string) => {
  timeline.push({ at_s: Math.round((Date.now() - t0) / 100) / 10, step })
  console.log(`${timeline.at(-1)?.at_s.toFixed(1).padStart(6)} s  ${step}`)
}

/** Count the audio the app sends, and keep it for lining up with the file. */
function recordSentAudio(page: Page) {
  const sent = { bytes: 0, chunks: [] as Uint8Array[] }
  page.on('websocket', (ws) => {
    if (!ws.url().includes('/session')) return
    ws.on('framesent', ({ payload }) => {
      if (typeof payload === 'string') return
      const bytes = new Uint8Array(payload)
      sent.bytes += bytes.length
      sent.chunks.push(bytes)
    })
  })
  return sent
}

test('narrate six paragraphs, approve the cast, get drafts and select an object', async ({ page, request }) => {
  const sent = recordSentAudio(page)
  const narration = readWav(liveWav)
  const durationMs = (narration.samples.length / narration.rate) * 1000

  await page.goto('/')
  await page.getByLabel('Name the story').fill('The Lantern Cat')
  await page.getByLabel(/Names in the story/).fill('Mira')
  await page.getByRole('button', { name: 'Open the studio' }).click()
  await expect(page).toHaveURL(/\/projects\/[0-9a-f]+$/)
  projectId = new URL(page.url()).pathname.split('/').at(-1) ?? ''

  t0 = Date.now()
  mark(`project ${projectId}`)
  await page.getByRole('button', { name: 'Start telling' }).click()
  await expect(page.getByText('Listening.')).toBeVisible({ timeout: 30_000 }) // staging may be waking up
  mark('listening')

  // Line up what was sent with the file once there is speech to compare (a couple of seconds, well before the
  // first beat), then beat at each paragraph.
  await expect.poll(() => sent.bytes / BYTES_PER_MS, { timeout: 30_000, intervals: [100] }).toBeGreaterThan(LEAD_MS + 500)
  const sentEnvelope = envelope(pcm(concat(sent.chunks)), BYTES_PER_MS * 500) // the app sends 24 kHz
  const { lagMs, score } = alignSent(sentEnvelope, envelope(narration.samples, narration.rate), LEAD_MS + 1000)
  mark(`aligned: the first audio sent was ${lagMs} ms into the file (correlation ${score.toFixed(2)})`)
  expect(score).toBeGreaterThan(0.5)
  const position = () => sent.bytes / BYTES_PER_MS + lagMs - LEAD_MS // ms into the narration itself

  for (const [i, beat] of BEATS_MS.entries()) {
    await expect.poll(position, { timeout: 60_000, intervals: [20] }).toBeGreaterThanOrEqual(beat)
    await page.getByRole('button', { name: /next shot/i }).click()
    mark(`beat ${i + 1} at ${Math.round(position())} ms of narration (target ${beat})`)
  }
  await expect.poll(position, { timeout: 60_000, intervals: [100] }).toBeGreaterThan(durationMs - LEAD_MS + 500)
  await page.getByRole('button', { name: 'Stop telling' }).click()
  mark('stop telling')

  const cards = page.getByTestId('shot-card')
  await expect(cards).toHaveCount(SHOTS, { timeout: 90_000 })
  mark(`${SHOTS} shot cards`)
  await expect(page.getByText('Done. Tell more any time.')).toBeVisible({ timeout: 60_000 })

  // Names are whatever the transcriber heard ("Mira" once came back as "Mirror"), so wait for every sheet.
  const characters = page.getByTestId('character-card')
  await expect(characters.first()).toBeVisible({ timeout: 60_000 })
  mark(`cast proposed: ${(await characters.getByRole('heading').allTextContents()).join(', ')}`)
  await expect
    .poll(async () => (await page.getByRole('img', { name: /^Reference sheet for / }).count()) - (await characters.count()), { timeout: 180_000 })
    .toBe(0)
  const approve = page.getByRole('button', { name: 'Approve cast' })
  await expect(approve).toBeEnabled({ timeout: 180_000 })
  mark('cast sheets drawn')
  await approve.click()
  mark('approve cast')

  await expect(page.locator('[data-testid="shot-card"][data-phase="drawing"]').first()).toBeVisible({ timeout: 30_000 })
  mark('drawing drafts')
  await expect(page.getByRole('img', { name: /^Shot 1:/ })).toBeVisible({ timeout: 180_000 })
  mark('first draft panel')
  await expect(page.getByRole('img', { name: /^Shot \d:/ })).toHaveCount(SHOTS, { timeout: 240_000 })
  mark(`all ${SHOTS} draft panels`)

  if (process.env.E2E_SCREENSHOTS === '1') {
    mkdirSync('../docs/img', { recursive: true })
    await page.screenshot({ path: '../docs/img/studio-light.png' })
    await page.emulateMedia({ colorScheme: 'dark' })
    await page.waitForTimeout(600) // let colour transitions finish
    await page.screenshot({ path: '../docs/img/studio-dark.png' })
    await page.emulateMedia({ colorScheme: 'light' })
  }

  // Panel 1's objects are segmented in the background after its render; click the centre of the first one.
  let panel: Panel = null
  await expect
    .poll(async () => {
      const project = (await (await request.get(`${API}/projects/${projectId}`)).json()) as { shots: { panel: Panel }[] }
      panel = project.shots[0]?.panel ?? null
      return panel?.masks.length ?? 0
    }, { timeout: 120_000, intervals: [2000] })
    .toBeGreaterThan(0)
  mark('panel 1 segmented')
  const ready = panel as Panel
  const mask = ready?.masks[0]
  if (!ready || !mask) throw new Error('no mask')

  await page.getByRole('button', { name: 'Edit the panel of shot 1' }).click()
  const canvas = page.getByTestId('panel-canvas')
  await expect(canvas.locator('canvas').first()).toBeVisible()
  const box = await canvas.boundingBox()
  if (!box) throw new Error('no canvas')
  const scale = (box.width - 4) / ready.width // inside the 2 px frame border
  const x = box.x + 2 + ((mask.box.left + mask.box.right) / 2) * scale
  const y = box.y + 2 + ((mask.box.top + mask.box.bottom) / 2) * scale
  await page.mouse.click(x, y)
  await expect(page.getByTestId('selection-status')).toContainText(mask.label, { timeout: 30_000 })
  mark(`selected "${mask.label}" on panel 1`)
  await page.waitForTimeout(1500) // let the video show the outline

  // Move it: saved as a layer and composited on a clean plate (one Muse Image edit).
  await canvas.focus()
  await page.keyboard.press('Shift+ArrowRight')
  await expect(page.getByText('Preparing the background…')).toBeVisible({ timeout: 10_000 })
  mark('move saved; preparing the background')
  await expect(page.getByText('Preparing the background…')).toHaveCount(0, { timeout: 180_000 })
  mark('clean plate and composite ready')
  await page.keyboard.press('Escape')
  await expect(page.getByRole('img', { name: /^Shot 1:/ })).toHaveAttribute('src', /\/composites\//, { timeout: 30_000 })

  // Export the animatic with the narrator's voice and subtitles.
  await page.getByLabel('Burn in subtitles').check()
  await page.getByRole('button', { name: 'Export animatic' }).click()
  mark('export animatic')
  await expect(page.getByTestId('animatic-player')).toBeVisible({ timeout: 360_000 }) // about 90 s on staging
  mark('animatic ready')
  const project = (await (await request.get(`${API}/projects/${projectId}`)).json()) as { animatic: { url: string; duration_ms: number; voiced: boolean } }
  mark(`animatic ${project.animatic.duration_ms} ms, voiced ${project.animatic.voiced}`)
  mkdirSync(outDir, { recursive: true })
  outputs.mp4 = `${outDir}/frameteller-e2e-${TARGET}.mp4`
  writeFileSync(outputs.mp4, await (await request.get(`${API}${project.animatic.url}`)).body())
  outputs.pdf = `${outDir}/frameteller-e2e-${TARGET}-storyboard.pdf`
  const pdf = await request.get(`${API}/projects/${projectId}/exports/storyboard.pdf`)
  expect(pdf.headers()['content-type']).toBe('application/pdf')
  writeFileSync(outputs.pdf, await pdf.body())
  mark('saved the MP4 and the PDF')
  await page.getByTestId('animatic-player').scrollIntoViewIfNeeded()
  await page.waitForTimeout(1500)

  // Share it: the stub previews on X; the page is read-only.
  await page.getByRole('button', { name: 'Create a share link' }).click()
  const link = await page.getByLabel('Share link').inputValue()
  outputs.share = link
  const stub = await (await request.get(link, { maxRedirects: 0 })).text()
  expect(stub).toContain('og:image')
  mark(`share link ${link}`)
  const token = link.split('/').at(-1) ?? ''
  await page.goto(`/s/${token}`)
  await expect(page.getByTestId('shared-shot')).toHaveCount(SHOTS)
  await expect(page.getByTestId('shared-animatic')).toBeVisible()
  mark('share page shows the panels and the animatic')
  await page.waitForTimeout(1500)
})

// Pass or fail: the video, the timeline and (for a local backend) the spend go to spikes/out.
test.afterEach(async ({ page }, info) => {
  const name = `${outDir}/frameteller-e2e-${TARGET}${info.status === 'passed' ? '' : '-failed'}`
  const spend = SPEND_LOG && existsSync(SPEND_LOG) && projectId ? spendFor(SPEND_LOG, projectId) : null
  const report = { target: TARGET, status: info.status, project_id: projectId, timeline, spend, outputs }
  writeFileSync(`${name}.json`, JSON.stringify(report, null, 2))
  if (spend) console.log(`spend USD ${spend.total_usd} ${JSON.stringify(spend.by_model)}`)
  const video = page.video()
  await page.close()
  if (video) await video.saveAs(`${name}.webm`)
})

function concat(chunks: Uint8Array[]): Uint8Array {
  const out = new Uint8Array(chunks.reduce((n, c) => n + c.length, 0))
  let at = 0
  for (const c of chunks) {
    out.set(c, at)
    at += c.length
  }
  return out
}

function spendFor(log: string, projectId: string) {
  const byModel: Record<string, number> = {}
  for (const line of readFileSync(log, 'utf8').split('\n')) {
    if (!line.trim()) continue
    const row = JSON.parse(line) as { type?: string; project_id?: string; model?: string; cost_usd?: number | null }
    if (row.type !== 'usage' || row.project_id !== projectId || !row.model) continue
    byModel[row.model] = (byModel[row.model] ?? 0) + (row.cost_usd ?? 0)
  }
  const total = Object.values(byModel).reduce((a, b) => a + b, 0)
  return { total_usd: Math.round(total * 10_000) / 10_000, by_model: byModel }
}
