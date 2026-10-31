import { expect, test, type Page } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'

// frameteller.com: the calls to action follow the launch, the gallery comes from the public API (faked here),
// and the page works at phone and desktop widths, light and dark, with reduced motion.
const LAUNCH = new Date('2026-11-02T17:00:00Z')
const BEFORE = new Date('2026-11-01T09:00:00Z')
const AFTER = new Date('2026-11-02T18:00:00Z')
const API = 'https://api.frameteller.com'
const SHOTS = resolve(process.env.MARKETING_SHOTS ?? '../spikes/out/marketing') // gitignored

interface Entry { id: string; title: string; share_url: string; cover_url: string; creator: { name: string; country: string } }

function entry(n: number, title: string, name = 'Frameteller team', country = ''): Entry {
  return { id: `e${n}`, title, share_url: `https://app.frameteller.com/s/t${n}`, cover_url: `/gallery/e${n}/cover.webp`, creator: { name, country } }
}

const COVER = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 3 2"><rect width="3" height="2" fill="#d9c7a3"/></svg>'

async function gallery(page: Page, featured: Entry[] | number, newest: Entry[] | number = []) {
  await page.route(`${API}/gallery?view=*`, (route) => {
    const view = new URL(route.request().url()).searchParams.get('view')
    const answer = view === 'featured' ? featured : newest
    return typeof answer === 'number'
      ? route.fulfill({ status: answer, body: '' })
      : route.fulfill({ json: { entries: answer, countries: [] }, headers: { 'Access-Control-Allow-Origin': '*' } })
  })
  await page.route(`${API}/gallery/*/cover.webp`, (route) => route.fulfill({ body: COVER, contentType: 'image/svg+xml' }))
}

async function open(page: Page, at: Date) {
  await page.clock.install({ time: at })
  await page.goto('/')
}

const hero = (page: Page) => page.locator('.hero .ctas')
const header = (page: Page) => page.locator('header.top')
const background = (page: Page, selector: string) =>
  page.locator(selector).first().evaluate((el) => getComputedStyle(el).backgroundColor)

test('before the launch, "Watch a story" and "Explore the gallery" are the primary buttons everywhere', async ({ page }) => {
  await gallery(page, [])
  await open(page, BEFORE)
  for (const where of [hero(page), page.locator('.countdown .ctas')]) {
    await expect(where.getByRole('link', { name: 'Watch a story' })).toBeVisible()
    await expect(where.getByRole('link', { name: 'Explore the gallery' })).toBeVisible()
    await expect(where.getByRole('link', { name: 'Try Frameteller' })).toBeHidden()
  }
  await expect(header(page).getByRole('link', { name: 'Watch a story' })).toBeVisible()
  await expect(header(page).getByRole('link', { name: 'Try Frameteller' })).toBeHidden()
  expect(await background(page, '.hero .cta-gallery')).toBe(await background(page, '.hero .cta-watch')) // both primary
  await expect(page.locator('.hero .cta-gallery')).toHaveAttribute('href', 'https://app.frameteller.com/gallery')
  await expect(page.getByRole('heading', { name: 'The live demo opens soon' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Live now: tell your story' })).toBeHidden() // only one of the two
  await expect(page.locator('#cd-after')).toHaveAttribute('hidden', '') // hidden, not just styled away
  expect(await page.locator('#cd-before').getAttribute('hidden')).toBeNull()
  await expect(page.locator('#d')).toHaveText('1')
})

test('at zero, without a reload, "Try Frameteller" becomes primary and the countdown says "Live now"', async ({ page }) => {
  await gallery(page, [])
  await open(page, new Date(LAUNCH.getTime() - 3000))
  await expect(hero(page).getByRole('link', { name: 'Watch a story' })).toBeVisible()
  await page.clock.runFor(5000)
  for (const where of [hero(page), page.locator('.countdown .ctas'), header(page)]) {
    await expect(where.getByRole('link', { name: 'Try Frameteller' })).toBeVisible()
    await expect(where.getByRole('link', { name: 'Try Frameteller' })).toHaveAttribute('href', 'https://app.frameteller.com')
    await expect(where.getByRole('link', { name: 'Watch a story' })).toBeHidden()
  }
  await expect(hero(page).getByRole('link', { name: 'Explore the gallery' })).toBeVisible()
  expect(await background(page, '.hero .cta-gallery')).toBe('rgba(0, 0, 0, 0)') // secondary: outlined
  expect(await background(page, '.hero .cta-try')).not.toBe('rgba(0, 0, 0, 0)')
  await expect(page.getByRole('heading', { name: 'Live now: tell your story' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'The live demo opens soon' })).toBeHidden()
  await expect(page.locator('#cd-before')).toHaveAttribute('hidden', '')
  expect(await page.locator('#cd-after').getAttribute('hidden')).toBeNull()
})

test('after the launch, the page opens live', async ({ page }) => {
  await gallery(page, [])
  await open(page, AFTER)
  await expect(header(page).getByRole('link', { name: 'Try Frameteller' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Live now: tell your story' })).toBeVisible()
})

test('the Night Baker plays muted on a loop, and "Play with sound" restarts it with sound', async ({ page }) => {
  await gallery(page, [])
  await open(page, BEFORE)
  const film = page.locator('#film')
  await expect(film).toHaveAttribute('src', 'video/night-baker.mp4')
  expect(await film.evaluate((v: HTMLVideoElement) => [v.muted, v.loop, v.autoplay])).toEqual([true, true, false])
  const box = await page.locator('#screen').boundingBox()
  expect(box && box.width / box.height).toBeCloseTo(1.5, 1) // a fixed 3:2 screen: nothing shifts as it loads
  await page.getByRole('button', { name: 'Play with sound' }).click()
  expect(await film.evaluate((v: HTMLVideoElement) => [v.muted, v.controls])).toEqual([false, true])
  await expect(page.getByRole('button', { name: 'Play with sound' })).toBeHidden()
})

test('"Watch a story" scrolls to the video and plays it with sound', async ({ page }) => {
  await gallery(page, [])
  await page.setViewportSize({ width: 390, height: 844 })
  await open(page, BEFORE)
  await expect(page.locator('#story')).toHaveCount(1)
  await expect(page.locator('#story #film')).toHaveCount(1) // the anchor is the hero video's own sheet
  await page.locator('#story').evaluate(() => window.scrollTo(0, 0))
  await page.locator('.countdown').getByRole('link', { name: 'Watch a story' }).click()
  await expect(page.locator('#story')).toBeInViewport()
  await expect(page.locator('#film')).toBeInViewport()
  expect(await page.locator('#film').evaluate((v: HTMLVideoElement) => v.muted)).toBe(false)
})

test('with reduced motion, the poster stands still with a play button', async ({ browser }) => {
  const context = await browser.newContext({ reducedMotion: 'reduce' })
  const page = await context.newPage()
  await gallery(page, [])
  await open(page, BEFORE)
  const film = page.locator('#film')
  await expect(page.locator('#screen')).toHaveClass(/still/)
  expect(await film.getAttribute('src')).toBeNull() // nothing loads or moves until asked
  await expect(film).toHaveAttribute('poster', 'img/night-baker-poster-960.webp')
  await page.getByRole('button', { name: 'Play with sound' }).click()
  await expect(film).toHaveAttribute('src', 'video/night-baker.mp4')
  await context.close()
})

test('the gallery shows six stories at most, featured first, each linking to its share page', async ({ page }) => {
  const featured = [entry(1, 'The Night Baker')]
  const newest = [entry(1, 'The Night Baker'), entry(2, 'The Rooftop Garden'), entry(3, 'The Lighthouse Fox', '', 'FR'),
    entry(4, 'Four'), entry(5, 'Five', 'Ama', ''), entry(6, 'Six'), entry(7, 'Seven')]
  await gallery(page, featured, newest)
  await open(page, BEFORE)
  const section = page.getByRole('region', { name: 'From the gallery' })
  await expect(section).toBeVisible()
  const cards = section.getByRole('listitem')
  await expect(cards).toHaveCount(6)
  await expect(cards.first().getByRole('heading')).toHaveText('The Night Baker')
  await expect(cards.first().getByRole('paragraph')).toHaveText('by Frameteller team') // a name and no country
  await expect(cards.nth(2).getByRole('paragraph')).toHaveText('by an anonymous storyteller · France')
  await expect(cards.nth(4).getByRole('paragraph')).toHaveText('by Ama')
  await expect(cards.first().getByRole('link')).toHaveAttribute('href', 'https://app.frameteller.com/s/t1')
  await expect(cards.first().getByRole('img')).toHaveAttribute('src', `${API}/gallery/e1/cover.webp`)
  await expect(cards.first().getByRole('img')).toHaveAttribute('alt', 'The first panel of The Night Baker')
  await expect(section.getByRole('link', { name: 'See all stories' })).toHaveAttribute('href', 'https://app.frameteller.com/gallery')
})

test('the gallery strip shows the three seed stories, each "by Frameteller team"', async ({ page }) => {
  const stories = ['The Night Baker', 'The Rooftop Garden', 'The Lighthouse Fox'].map((t, i) => entry(i + 1, t))
  await gallery(page, [stories[0]], stories)
  await open(page, BEFORE)
  const cards = page.getByRole('region', { name: 'From the gallery' }).getByRole('listitem')
  await expect(cards).toHaveCount(3)
  await expect(cards.getByRole('heading')).toHaveText(['The Night Baker', 'The Rooftop Garden', 'The Lighthouse Fox'])
  await expect(cards.getByRole('paragraph')).toHaveText(Array(3).fill('by Frameteller team'))
})

for (const [label, featured, newest] of [
  ['fails', 500, 500],
  ['is empty', [], []],
] as const) {
  test(`the gallery section hides when the API ${label}`, async ({ page }) => {
    await gallery(page, featured as Entry[] | number, newest as Entry[] | number)
    await open(page, BEFORE)
    await page.waitForLoadState('networkidle')
    await expect(page.getByRole('heading', { name: 'From the gallery' })).toBeHidden()
    await expect(page.getByRole('heading', { name: "Who it's for" })).toBeVisible()
  })
}

test('the FAQ opens from the keyboard, and the page carries FAQPage data', async ({ page }) => {
  await gallery(page, [])
  await open(page, BEFORE)
  const question = page.locator('summary', { hasText: 'Which languages?' })
  await question.focus()
  await page.keyboard.press('Enter')
  await expect(page.getByText('English, French, Spanish, Hindi, Arabic and Portuguese.')).toBeVisible()
  await page.keyboard.press('Enter')
  await expect(page.getByText('English, French, Spanish, Hindi, Arabic and Portuguese.')).toBeHidden()
  const data = await page.locator('script[type="application/ld+json"]').allTextContents()
  const faq = data.map((t) => JSON.parse(t)).find((d) => d['@type'] === 'FAQPage')
  expect(faq.mainEntity).toHaveLength(7)
  await expect(page.locator('details')).toHaveCount(7)
  await page.locator('summary', { hasText: 'What happens to my recording?' }).click()
  await expect(page.getByRole('link', { name: 'privacy page' })).toHaveAttribute('href', 'https://app.frameteller.com/privacy')
})

test('the build log shows the latest 3, then all of them', async ({ page }) => {
  await gallery(page, [])
  await open(page, BEFORE)
  const log = page.locator('#log > li')
  await expect(log.nth(0)).toContainText('Stories you can watch today')
  await expect(log.nth(2)).toBeVisible()
  await expect(log.nth(3)).toBeHidden()
  const all = page.getByRole('button', { name: 'Show all' })
  await all.click()
  await expect(log.nth(3)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Show the latest 3' })).toHaveAttribute('aria-expanded', 'true')
})

test('the page never names a Meta model, and the footer links the gallery, privacy and X', async ({ page }) => {
  await gallery(page, [])
  await open(page, BEFORE)
  await page.getByRole('button', { name: 'Show all' }).click()
  const text = await page.locator('body').innerText()
  expect(text).not.toMatch(/\b(Muse|Spark|Glimmer|Wonder|SAM|Llama)\b/)
  const footer = page.getByRole('contentinfo')
  await expect(footer.getByRole('link', { name: 'Gallery' })).toHaveAttribute('href', 'https://app.frameteller.com/gallery')
  await expect(footer.getByRole('link', { name: 'Privacy' })).toHaveAttribute('href', 'https://app.frameteller.com/privacy')
  await expect(footer.getByRole('link', { name: 'Follow on X' })).toBeVisible()
  await expect(footer).toContainText('Built for the Meta Global AI Developer Hackathon, Oct 26 – Nov 4, 2026')
})

for (const width of [390, 1280]) {
  for (const scheme of ['light', 'dark'] as const) {
    for (const [moment, at] of [['before', BEFORE], ['after', AFTER]] as const) {
      test(`${width}px, ${scheme}, ${moment} the launch: no sideways scroll, nothing unreadable`, async ({ browser }) => {
        const context = await browser.newContext({ viewport: { width, height: 900 }, colorScheme: scheme })
        const page = await context.newPage()
        await gallery(page, [entry(1, 'The Night Baker'), entry(2, 'The Rooftop Garden'), entry(3, 'The Lighthouse Fox')])
        await open(page, at)
        await page.waitForLoadState('networkidle')
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width)
        const primary = moment === 'before' ? 'Watch a story' : 'Try Frameteller'
        await expect(page.locator('header.top').getByRole('link', { name: primary })).toBeVisible()
        mkdirSync(SHOTS, { recursive: true })
        await page.screenshot({ path: `${SHOTS}/${moment}-${width}-${scheme}.png` })
        await page.screenshot({ path: `${SHOTS}/${moment}-${width}-${scheme}-full.png`, fullPage: true })
        await context.close()
      })
    }
  }
}
