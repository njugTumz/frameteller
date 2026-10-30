import { expect, test, type Page } from '@playwright/test'
import { panelSvg, sheetSvg } from './fixtures'

// "Submit to gallery" with a name and a country, against a backend faked inside the browser: the suggested
// country is only used when chosen, the card and the share page show the byline, and it can be edited and removed.
const API = 'http://localhost:8000'
type Json = Record<string, unknown>
type Signed = { name: string; country: string }

const review = { outcome: 'checked', summary: 'Checked', issues: [], fix_instruction: '', model: 'muse-spark-1.3', confidence: 0.9, fixes: 0, rubrics: {} }
const LINA = { id: 'lina', name: 'Lina', description: 'a girl in a yellow raincoat', reference_url: '/media/projects/p1/characters/lina/reference', review }
const panel = (n: number) => ({ revision: 1, shown_revision: 1, status: 'ready', image_url: `/media/projects/p1/panels/s${n}/r1/image`, base_image_url: `/media/projects/p1/panels/s${n}/r1/image`, width: 1920, height: 1280, masks: [], layers: [], outdated: false, review })
const shot = (n: number) => ({ id: `s${n}`, number: n, framing: 'wide', character_ids: ['lina'], setting: 'a rooftop', action: `Lina, beat ${n}`, dialogue: '', duration_ms: 2400, source_turn_ids: [`t${n}`], episode: 1, panel: panel(n) })
const PROJECT = { id: 'p1', title: 'The Rooftop Garden', style: 'pencil', cast: { status: 'approved', characters: [LINA] }, turns: [], shots: [shot(1), shot(2)], narrations: [], animatic: null, share_token: 'tok' }

async function fakeBackend(page: Page) {
  const state = { entry: null as Json | null, posted: [] as Json[], patched: [] as Json[] }
  const mine = () => state.entry
  const card = () => ({ id: 'g1', title: 'The Rooftop Garden', style: 'pencil', episodes: 1, shots: 2, duration_ms: 4800, cover_url: '/gallery/g1/cover.webp', video_url: '/gallery/g1/video.mp4', share_url: 'http://localhost:4173/s/tok', hearts: 0, hearted: false, featured: false, published_at: '2026-10-31T06:00:00Z', creator: state.entry?.creator as Signed | undefined })
  await page.route(`${API}/**`, async (route) => {
    const req = route.request()
    const url = new URL(req.url())
    const path = url.pathname
    const json = (status: number, b: unknown) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
    if (path === '/healthz') return json(200, { status: 'ok' })
    if (path === '/voices') return json(200, { available: false, default: 'en-US-AvaMultilingualNeural', voices: [] })
    if (path === '/projects/p1') return json(200, PROJECT)
    if (path === '/gallery/countries') return json(200, { codes: ['AE', 'JP', 'KE'], suggested: 'KE' })
    if (path === '/projects/p1/gallery') {
      if (req.method() === 'POST') {
        const body = req.postDataJSON() as Json
        state.posted.push(body)
        state.entry = { id: 'g1', status: 'published', note: '', audio: body.audio, hearts: 0, featured: false, submitted_at: '2026-10-31T06:00:00Z', creator: { name: String(body.name ?? '').trim(), country: body.country ?? '' } }
        return json(202, mine())
      }
      if (req.method() === 'PATCH') {
        const body = req.postDataJSON() as Json
        state.patched.push(body)
        state.entry = { ...state.entry, creator: { name: body.name ?? '', country: body.country ?? '' } }
        return json(200, mine())
      }
      return state.entry ? json(200, mine()) : json(404, { error: { code: 'not_found', message: 'Not in the gallery' } })
    }
    if (path === '/gallery') {
      const c = card()
      const shown = !url.searchParams.get('country') || url.searchParams.get('country') === c.creator?.country
      return json(200, { entries: shown ? [c] : [], countries: c.creator?.country ? [{ code: c.creator.country, entries: 1 }] : [] })
    }
    if (path === '/shares/tok') return json(200, { title: 'The Rooftop Garden', style: 'pencil', shots: [], animatic: null, public: true, narrated_by: null, creator: state.entry?.creator ?? null })
    if (path.startsWith('/media/') || path.startsWith('/gallery/g1/')) {
      const svg = path.includes('/characters/') ? sheetSvg('Lina') : panelSvg(Number(/s(\d+)/.exec(path)?.[1] ?? 1))
      return route.fulfill({ status: 200, contentType: 'image/svg+xml', body: svg })
    }
    return json(404, { error: { code: 'not_mocked', message: path } })
  })
  return state
}

test('submit to the gallery signed with a name and a confirmed country, then edit and remove it', async ({ page }) => {
  const backend = await fakeBackend(page)
  await page.goto('/projects/p1')
  const dialog = page.getByTestId('gallery-submit')
  await expect(dialog.getByRole('button', { name: 'Submit to gallery' })).toBeDisabled()

  // The country is only a suggestion: empty until chosen.
  await expect(dialog.getByLabel('Country')).toHaveValue('')
  await expect(dialog.getByTestId('country-suggestion')).toContainText('A guess from your browser: 🇰🇪 Kenya')
  await dialog.getByLabel('Your name').fill('Captain Biscuit')
  await dialog.getByRole('button', { name: 'Use 🇰🇪 Kenya' }).click()
  await expect(dialog.getByLabel('Country')).toHaveValue('KE')
  await dialog.getByRole('radio', { name: 'Publish without audio' }).check()
  await dialog.getByRole('checkbox').check()
  await dialog.getByRole('button', { name: 'Submit to gallery' }).click()
  await expect(dialog.getByTestId('my-byline')).toContainText('Shown by Captain Biscuit · 🇰🇪 Kenya')
  expect(backend.posted[0]).toEqual({ consent: true, audio: 'none', name: 'Captain Biscuit', country: 'KE' })

  await page.goto('/gallery')
  await expect(page.getByTestId('country-count')).toHaveText('Stories from 1 country')
  await expect(page.getByTestId('gallery-byline')).toHaveText('by Captain Biscuit · 🇰🇪 Kenya')
  await page.getByLabel('Country').selectOption('KE')
  await expect(page.getByTestId('gallery-card')).toHaveCount(1)
  await page.goto('/s/tok')
  await expect(page.getByTestId('shared-byline')).toHaveText('by Captain Biscuit · 🇰🇪 Kenya')

  await page.goto('/projects/p1')
  await dialog.getByRole('button', { name: 'Edit name and country' }).click()
  await dialog.getByRole('button', { name: 'Remove name and country' }).click()
  await expect(dialog.getByTestId('my-byline')).toContainText('Shown by an anonymous storyteller')
  expect(backend.patched.at(-1)).toEqual({ name: '', country: '' })
  await page.goto('/s/tok')
  await expect(page.getByTestId('shared-byline')).toHaveText('by an anonymous storyteller')
})

test('without choosing, the suggested country is never sent', async ({ page }) => {
  const backend = await fakeBackend(page)
  await page.goto('/projects/p1')
  const dialog = page.getByTestId('gallery-submit')
  await dialog.getByRole('radio', { name: 'Publish without audio' }).check()
  await dialog.getByRole('checkbox').check()
  await dialog.getByRole('button', { name: 'Submit to gallery' }).click()
  await expect(dialog.getByTestId('my-byline')).toContainText('Shown by an anonymous storyteller')
  expect(backend.posted[0]).toEqual({ consent: true, audio: 'none', name: '', country: '' })
})
