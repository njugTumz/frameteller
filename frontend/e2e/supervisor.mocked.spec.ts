import { expect, test, type Page } from '@playwright/test'
import { panelSvg, sheetSvg } from './fixtures'

// The continuity supervisor's badges, feed and buttons against a backend faked inside the browser.
const API = 'http://localhost:8000'

type Json = Record<string, unknown>

const VEST = { rule_id: 'CONT-04', severity: 'major', description: 'Pip wears a blue vest that is not on his reference sheet' }
const SWEATER = { rule_id: 'CAST-04', severity: 'major', description: 'Pip wears a green sweater that is not in his description' }

const review = (over: Json = {}) => ({
  outcome: 'checked',
  summary: 'Checked',
  issues: [],
  fix_instruction: '',
  model: 'muse-glimmer',
  confidence: 0.9,
  fixes: 0,
  rubrics: { 'panel-continuity': 'abc123def456', shot: '0123456789ab' },
  ...over,
})

const entry = (n: number, outcome: string, message: string, model = 'muse-glimmer') => ({
  at: `2026-10-29T12:00:0${n}+00:00`,
  subject: `Shot ${n}`,
  outcome,
  message,
  rule_ids: outcome === 'checked' ? [] : ['CONT-04'],
  model,
  shot_id: `s${n}`,
  character_id: null,
})

function shot(n: number, revision: number, rev: Json): Json {
  return {
    id: `s${n}`,
    number: n,
    framing: 'medium',
    character_ids: ['pip'],
    setting: 'inside the lighthouse at night',
    action: n === 1 ? 'Pip shakes the rain off his fur.' : 'Pip curls up by the fire.',
    dialogue: '',
    duration_ms: 4000,
    source_turn_ids: [`t-b${n}`],
    panel: {
      revision,
      shown_revision: revision,
      status: 'ready',
      image_url: `/media/projects/p1/panels/s${n}/r${revision}/image`,
      base_image_url: `/media/projects/p1/panels/s${n}/r${revision}/image`,
      width: 1920,
      height: 1280,
      masks: [],
      layers: [],
      outdated: false,
      review: rev,
    },
  }
}

async function supervisedBackend(page: Page) {
  const state = {
    posted: [] as Json[],
    fixed: false,
    sheet: review({ outcome: 'needs_user', summary: SWEATER.description, issues: [SWEATER], fix_instruction: 'remove the sweater', model: 'muse-spark-1.3' }) as Json,
    checks: true,
  }
  const project = () => ({
    id: 'p1',
    title: 'The Lighthouse',
    style: 'pencil',
    cast: {
      status: 'draft',
      characters: [{ id: 'pip', name: 'Pip', description: 'a tiny young orange fox', reference_url: '/media/projects/p1/characters/pip/reference', review: state.sheet }],
    },
    turns: [],
    shots: [
      shot(1, 1, review()),
      state.fixed
        ? shot(2, 3, review({ outcome: 'fixed', summary: 'Fixed: remove the blue vest', fixes: 0, model: 'muse-spark-1.3' }))
        : shot(2, 1, review({ outcome: 'needs_user', summary: 'Needs your eye', issues: [VEST], fix_instruction: 'remove the blue vest', confidence: 0.4 })),
    ],
    narrations: [],
    animatic: null,
    share_token: null,
    continuity_checks: state.checks,
    supervisor: [
      entry(1, 'checked', 'Shot 1: checked, no continuity issues.'),
      entry(2, 'needs_user', 'Shot 2 needs your eye: Pip wears a blue vest that is not on his reference sheet (CONT-04; the reviewer was not sure).'),
      ...(state.fixed ? [entry(3, 'checked', 'Shot 2: checked, no continuity issues.', 'muse-spark-1.3')] : []),
    ],
  })

  await page.route(`${API}/**`, async (route) => {
    const req = route.request()
    const path = new URL(req.url()).pathname
    const body = (req.postDataJSON?.() as Json | null) ?? null
    if (req.method() !== 'GET') state.posted.push({ method: req.method(), path, body })
    const json = (status: number, b: unknown) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
    if (path === '/healthz') return json(200, { status: 'ok' })
    if (path === '/status') return json(200, { open: true, paused: false, full: false, message: null })
    if (path === '/projects/p1' && req.method() === 'PATCH') {
      state.checks = Boolean(body?.continuity_checks)
      return json(200, project())
    }
    if (path === '/projects/p1') return json(200, project())
    if (path === '/projects/p1/shots/2/panel/review/apply') {
      setTimeout(() => (state.fixed = true), 300) // the edit runs, then the supervisor checks it again
      return json(202, { kind: 'edit_panel', key: 'edit_panel:p1:s2:r2', enqueued: true, shot_id: 's2', revision: 2 })
    }
    if (path === '/projects/p1/cast/pip/review/accept') {
      state.sheet = { ...state.sheet, outcome: 'accepted' }
      return json(200, project())
    }
    if (path.startsWith('/projects/p1/jobs/')) return json(200, { key: path.split('/').at(-1), status: state.fixed ? 'succeeded' : 'running', message: null })
    if (path.startsWith('/media/')) {
      const svg = path.includes('/characters/') ? sheetSvg('Pip') : panelSvg(Number(/s(\d+)/.exec(path)?.[1] ?? 1))
      return route.fulfill({ status: 200, contentType: 'image/svg+xml', body: svg })
    }
    return json(404, { error: { code: 'not_mocked', message: path } })
  })
  return state
}

test('badges, the supervisor feed, apply a suggested fix, accept a sheet and turn the checks off', async ({ page }) => {
  const backend = await supervisedBackend(page)
  await page.goto('/projects/p1')

  const first = page.locator('[data-testid="shot-card"][data-shot="1"]')
  const second = page.locator('[data-testid="shot-card"][data-shot="2"]')
  await expect(first.getByTestId('review-badge')).toHaveText(/Checked/)
  await expect(first.getByTestId('review-badge')).toHaveAttribute('title', 'Checked by Muse Glimmer')
  await first.getByTestId('review-badge').hover()
  await expect(first.getByTestId('review-badge')).toContainText('Checked by Muse Glimmer')
  await expect(second.getByTestId('review-badge')).toHaveText(/Needs your eye/)
  await expect(second.getByTestId('needs-your-eye')).toContainText('Pip wears a blue vest that is not on his reference sheet')

  const feed = page.getByTestId('supervisor-feed')
  await expect(feed.getByRole('listitem')).toHaveCount(2)
  await expect(feed.getByRole('listitem').nth(1)).toContainText('Shot 2 needs your eye')

  // Apply the suggested fix: an edit job, followed like any other until the fixed panel is checked again.
  // No session socket is open here, so the job is settled by the quiet-job check (20 s), as any render would be.
  await second.getByRole('button', { name: 'Apply suggested fix' }).click()
  expect(backend.posted.at(-1)).toEqual({ method: 'POST', path: '/projects/p1/shots/2/panel/review/apply', body: null })
  await expect(second).toHaveAttribute('data-phase', 'queued')
  await expect(second.getByTestId('review-badge')).toHaveText(/Fixed: remove the blue vest/, { timeout: 40_000 })
  await expect(second.getByTestId('needs-your-eye')).toHaveCount(0)
  await expect(feed.getByRole('listitem')).toHaveCount(3)

  // The cast tray shows the sheet's rubric issue before approval; accept it as it is.
  const pip = page.getByTestId('character-card')
  await expect(pip.getByTestId('needs-your-eye')).toContainText('Pip wears a green sweater')
  await expect(pip.getByRole('button', { name: 'Apply fix' })).toBeVisible()
  await pip.getByRole('button', { name: 'Accept anyway' }).click()
  await expect.poll(() => backend.posted.at(-1)?.path).toBe('/projects/p1/cast/pip/review/accept')
  await expect(pip.getByTestId('review-badge')).toHaveText(/Accepted/)

  // Turn the checks off for this project.
  await feed.getByRole('checkbox', { name: 'Continuity checks' }).uncheck()
  await expect.poll(() => backend.posted.at(-1)).toEqual({ method: 'PATCH', path: '/projects/p1', body: { continuity_checks: false } })
  await expect(feed.getByRole('checkbox', { name: 'Continuity checks' })).not.toBeChecked()
})
