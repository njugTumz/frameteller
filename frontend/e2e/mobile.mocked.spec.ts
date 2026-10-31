import { expect, test, type Locator, type Page } from '@playwright/test'
import { audit, onScreen } from './support/audit'
import { API, phoneBackend } from './support/phoneBackend'

// Every screen on phones (iPhone 14 in WebKit, Pixel 7 in Chromium, portrait and landscape; see the device
// projects in playwright.config.ts): no sideways scroll, no overlapping or clipped header, taps of 44 px or
// more, inputs of 16 px or more (no zoom on iOS), tour cards on screen, and the microphone flow.
const SCRIPT = 'A busy city at sunset.\n\nLina waters tomato plants.'
const phone = () => test.info().project.name.startsWith('phone')
test.beforeEach(() => test.skip(!phone(), 'phone projects only'))

/** A header action: in the ☰ menu on narrow phones, in the bar (or the page) from 720 px. */
async function headerItem(page: Page, name: string | RegExp, role: 'button' | 'link' = 'link'): Promise<Locator> {
  const header = page.locator('header').first()
  const direct = header.getByRole(role, { name, exact: typeof name === 'string' })
  if (await direct.isVisible()) return direct
  const menu = header.getByRole('button', { name: 'Menu' })
  // From 720 px (a phone turned sideways) the bar shows its actions, and the page its own (Report a problem).
  if (!(await menu.isVisible())) return page.getByRole('main').getByRole(role, { name, exact: typeof name === 'string' })
  if ((await menu.getAttribute('aria-expanded')) !== 'true') await menu.click()
  return page.getByTestId('header-menu').getByRole(role, { name, exact: typeof name === 'string' })
}

async function openStudio(page: Page, mode: RegExp, script = true) {
  await page.goto('/')
  await page.getByLabel('Name the story').fill('Rooftop Kite')
  await page.getByRole('radio', { name: mode }).check()
  if (script) await page.getByLabel('Your script').fill(SCRIPT)
  await page.getByRole('button', { name: 'Open the studio' }).click()
  await expect(page).toHaveURL(/\/projects\/p1$/)
}

test('start page and the header menu', async ({ page }, info) => {
  await phoneBackend(page)
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'New here? Take the 2-minute tour' })).toBeVisible()
  await audit(page, info, 'start')

  const header = page.locator('header').first()
  const narrow = (page.viewportSize()?.width ?? 0) < 720
  const menu = header.getByRole('button', { name: 'Menu' })
  if (narrow) {
    await expect(header.getByRole('link', { name: 'Gallery' })).toBeHidden()
    const box = await menu.boundingBox()
    expect(box && box.width >= 44 && box.height >= 44).toBe(true)
    await expect(menu).toHaveAttribute('aria-expanded', 'false')
    await menu.click()
    await expect(menu).toHaveAttribute('aria-expanded', 'true')
    const panel = page.getByTestId('header-menu')
    await expect(panel).toHaveAttribute('id', (await menu.getAttribute('aria-controls')) ?? '')
    await expect(panel.getByRole('button', { name: 'Take the tour' })).toBeFocused()
    for (const link of ['Gallery', 'Privacy']) await expect(panel.getByRole('link', { name: link })).toBeVisible()
    await expect(panel.getByRole('radio', { name: 'Dark' })).toBeVisible()
    await audit(page, info, 'start-menu')
    await panel.getByText('Dark', { exact: true }).click() // the label is the tap target
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
    await page.keyboard.press('Escape')
    await expect(panel).toBeHidden()
    await expect(menu).toBeFocused()
    // An outside tap closes it too.
    await menu.click()
    await page.getByRole('heading', { name: 'New here? Take the 2-minute tour' }).click()
    await expect(panel).toBeHidden()
  }
  // The tour starts from the header, wherever it lives.
  await (await headerItem(page, 'Take the tour', 'button')).click()
  const card = page.getByTestId('tour-card')
  await expect(card).toHaveAttribute('data-step', 'modes')
  await expect(page.getByTestId('header-menu')).toBeHidden()
  await expect.poll(() => onScreen(page, card)).toBe(true)
  await audit(page, info, 'tour-1')
  await card.getByRole('button', { name: 'Next' }).click()
  await expect(card).toHaveAttribute('data-step', 'voice')
  await expect.poll(() => onScreen(page, card)).toBe(true)
  await audit(page, info, 'tour-2')
})

test('narrate: the microphone, a big Next shot button, and Stop', async ({ page }, info) => {
  const backend = await phoneBackend(page)
  await openStudio(page, /Narrate/, false)
  await audit(page, info, 'studio-narrate')
  await page.getByRole('button', { name: 'Start telling' }).click()
  await expect(page.getByText('Listening.')).toBeVisible()
  const next = page.getByRole('button', { name: /next shot/i })
  await expect(next).toBeVisible()
  const box = await next.boundingBox()
  expect(box && box.height >= 56 && box.width >= 160, `Next shot is ${box?.width}x${box?.height}`).toBe(true)
  await expect(next.locator('kbd')).toBeHidden() // no Space hint on a touch screen
  await audit(page, info, 'studio-listening')
  await next.tap()
  await expect(page.getByTestId('shot-card')).toHaveCount(1)
  await expect.poll(() => backend.frames).toBeGreaterThan(0) // the microphone streams
  await page.getByRole('button', { name: 'Stop telling' }).click()
  await expect(page.getByText(/Done\./)).toBeVisible()
})

test('a phone locked mid-narration pauses cleanly, says so, and keeps every shot', async ({ page }, info) => {
  const backend = await phoneBackend(page)
  await openStudio(page, /Narrate/, false)
  await page.getByRole('button', { name: 'Start telling' }).click()
  await expect(page.getByText('Listening.')).toBeVisible()
  await page.getByRole('button', { name: /next shot/i }).tap()
  await expect(page.getByTestId('shot-card')).toHaveCount(1)
  // Locking the phone hides the page, and iOS ends the microphone track.
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' })
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => true })
    document.dispatchEvent(new Event('visibilitychange'))
  })
  await expect(page.getByTestId('paused-notice')).toContainText('Paused when the screen locked')
  await page.getByTestId('paused-notice').scrollIntoViewIfNeeded()
  await audit(page, info, 'studio-paused')
  await expect(page.getByRole('button', { name: /next shot/i })).toBeDisabled() // the microphone is off
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'visible' })
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => false })
    document.dispatchEvent(new Event('visibilitychange'))
  })
  await expect(page.getByTestId('shot-card')).toHaveCount(1) // never lost
  const again = page.getByRole('button', { name: /^(Start telling|Tell more)$/ })
  await expect(again).toBeEnabled() // go on where you left off
  await again.click()
  await expect(page.getByText('Listening.')).toBeVisible()
  expect(backend.starts.length).toBe(2)
})

test('teleprompter on a phone', async ({ page }, info) => {
  await phoneBackend(page)
  await openStudio(page, /Teleprompter/)
  await page.getByRole('button', { name: 'Start telling' }).click()
  await expect(page.getByTestId('teleprompter').locator('[data-state="current"]')).toHaveText('A busy city at sunset.')
  await audit(page, info, 'studio-teleprompter')
  await page.getByRole('button', { name: 'Stop telling' }).click()
})

test('read it to me, approve the cast, and Redraw', async ({ page }, info) => {
  await phoneBackend(page)
  await page.goto('/')
  await page.getByRole('radio', { name: /Read it to me/ }).check()
  await page.getByLabel('Your script').fill(SCRIPT)
  await audit(page, info, 'start-read')
  await page.getByLabel('Name the story').fill('Rooftop Kite')
  await page.getByRole('button', { name: 'Open the studio' }).click()
  await page.getByRole('button', { name: 'Read it to me' }).click()
  await expect(page.getByTestId('shot-card')).toHaveCount(2)
  await expect(page.getByRole('button', { name: 'Approve cast' })).toBeVisible()
  await audit(page, info, 'studio-cast')
  await page.getByRole('button', { name: 'Approve cast' }).click()
  const shot = page.locator('[data-testid="shot-card"][data-shot="1"]')
  await expect(shot.getByRole('img', { name: /^Shot 1:/ })).toBeVisible({ timeout: 15_000 })
  await shot.getByRole('button', { name: 'Redraw shot 1' }).click()
  await expect(shot.getByTestId('redraw-box')).toBeVisible()
  await shot.getByTestId('redraw-box').scrollIntoViewIfNeeded()
  await audit(page, info, 'studio-redraw')
})

/** A one-finger drag with real touch input (Chromium, over CDP): Konva drags on touch events. */
async function touchDrag(page: Page, from: { x: number; y: number }, to: { x: number; y: number }) {
  const cdp = await page.context().newCDPSession(page)
  const touch = (type: 'touchStart' | 'touchMove' | 'touchEnd', p?: { x: number; y: number }) => cdp.send('Input.dispatchTouchEvent', { type, touchPoints: p ? [p] : [] })
  await touch('touchStart', from)
  for (let i = 1; i <= 8; i++) await touch('touchMove', { x: from.x + ((to.x - from.x) * i) / 8, y: from.y + ((to.y - from.y) * i) / 8 })
  await touch('touchEnd')
}

test('panel editor: tap to select, drag with a finger', async ({ page }, info) => {
  const backend = await phoneBackend(page, { drawn: true })
  await page.goto('/projects/p1')
  await page.getByRole('button', { name: 'Edit the panel of shot 1' }).click()
  const canvas = page.getByTestId('panel-canvas')
  await expect(canvas.locator('canvas').first()).toBeVisible()
  await audit(page, info, 'editor')
  await canvas.scrollIntoViewIfNeeded()
  const box = await canvas.boundingBox()
  if (!box) throw new Error('no canvas')
  const at = { x: box.x + box.width * 0.5, y: box.y + box.height * 0.6 }
  await page.touchscreen.tap(at.x, at.y)
  await expect(page.getByTestId('selection-status')).toContainText('yellow raincoat')
  await audit(page, info, 'editor-selected')
  await expect.poll(() => onScreen(page, canvas)).toBe(true) // the whole panel, also sideways
  if (page.context().browser()?.browserType().name() !== 'chromium') {
    test.info().annotations.push({ type: 'note', description: 'touch drag: Playwright’s WebKit cannot make touch events; the Chromium phones cover it' })
    return
  }
  await page.waitForTimeout(300) // the cut-out image loads
  await touchDrag(page, at, { x: at.x + box.width * 0.15, y: at.y })
  await expect.poll(() => backend.posted.find((p) => p.path.endsWith('/layers'))?.body?.dx as number | undefined).toBeGreaterThan(0)
})

test('export, play with sound, share, and the gallery submit dialog', async ({ page }, info) => {
  await phoneBackend(page, { drawn: true })
  await page.goto('/projects/p1')
  await page.getByRole('button', { name: 'Export animatic' }).click()
  const player = page.getByTestId('animatic-player')
  await expect(player).toBeVisible({ timeout: 10_000 })
  await player.scrollIntoViewIfNeeded()
  await audit(page, info, 'studio-export')
  await page.getByRole('button', { name: 'Play with sound' }).tap()
  await expect(page.getByRole('button', { name: 'Play with sound' })).toHaveCount(0)
  expect(await player.evaluate((v: HTMLVideoElement) => v.muted || v.volume < 1)).toBe(false) // with sound
  await page.getByTestId('gallery-submit').scrollIntoViewIfNeeded()
  await audit(page, info, 'studio-gallery-submit')
  await (await headerItem(page, 'Report a problem', 'button')).click()
  await expect(page.getByRole('textbox', { name: /What went wrong/ })).toBeFocused()
  await audit(page, info, 'studio-report')
})

test('share page', async ({ page }, info) => {
  await phoneBackend(page)
  await page.goto('/s/tok')
  await expect(page.getByTestId('shared-shot')).toHaveCount(2)
  await audit(page, info, 'share')
  await expect(page.getByTestId('shared-animatic')).toBeVisible()
})

test('gallery and its report dialog', async ({ page }, info) => {
  await phoneBackend(page)
  await page.goto('/gallery')
  await expect(page.getByTestId('gallery-card')).toHaveCount(2)
  await audit(page, info, 'gallery')
  const first = page.getByTestId('gallery-card').first()
  await first.getByRole('button', { name: 'Report', exact: true }).first().click()
  await first.getByRole('button', { name: 'Report', exact: true }).last().scrollIntoViewIfNeeded()
  await audit(page, info, 'gallery-report')
  await first.getByRole('button', { name: /Play .* with sound/ }).click()
  await expect(first.locator('video')).toBeVisible()
})

test('privacy page', async ({ page }, info) => {
  await phoneBackend(page)
  await page.goto('/privacy')
  await expect(page.getByRole('heading', { name: 'Privacy', level: 1 })).toBeVisible()
  await audit(page, info, 'privacy')
})

test('admin page', async ({ page }, info) => {
  await phoneBackend(page)
  await page.goto('/admin#test-admin-token')
  await expect(page.getByText('The Rooftop Garden').first()).toBeVisible()
  await audit(page, info, 'admin')
  for (const tab of await page.getByRole('tab').all()) {
    await tab.click()
    await audit(page, info, `admin-${((await tab.textContent()) ?? '').trim().toLowerCase().replace(/\W+/g, '-')}`)
  }
  void API
})
