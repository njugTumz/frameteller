import { expect, type Page, type TestInfo } from '@playwright/test'
import { resolve } from 'node:path'

/** What a phone screen must never do: scroll sideways, clip or overlap header text, offer small taps, zoom on focus. */
export interface Finding {
  rule: 'horizontal-scroll' | 'tap-target' | 'input-font' | 'header-overlap' | 'off-screen'
  what: string
}

export async function findings(page: Page): Promise<Finding[]> {
  return page.evaluate(() => {
    const out: { rule: string; what: string }[] = []
    const vw = window.innerWidth
    const doc = document.documentElement
    if (doc.scrollWidth > vw + 1) out.push({ rule: 'horizontal-scroll', what: `page is ${doc.scrollWidth}px wide in a ${vw}px window` })
    const name = (el: Element) =>
      `${el.tagName.toLowerCase()} "${(el.getAttribute('aria-label') ?? el.textContent ?? '').trim().replace(/\s+/g, ' ').slice(0, 40)}"`
    const visible = (el: Element) => {
      const r = el.getBoundingClientRect()
      const s = getComputedStyle(el)
      return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && Number(s.opacity) > 0
    }
    // Links inside running text are exempt (WCAG 2.5.8 inline exception); so are hidden native inputs whose label is the target.
    const inline = (el: Element) => {
      if (el.closest('nav, header')) return false
      // A link in a sentence, or a word of the transcript that can be tapped to fix it (Fix words does the same at 44 px).
      if (el.tagName === 'BUTTON' && el.getAttribute('tabindex') === '-1' && el.closest('p')) return true
      const around = Array.from(el.parentElement?.childNodes ?? []).filter((n) => n !== el)
      return el.tagName === 'A' && around.some((n) => n.nodeType === Node.TEXT_NODE && (n.textContent ?? '').trim().length > 0)
    }
    const target = (el: Element) => {
      if (el instanceof HTMLInputElement && (el.type === 'radio' || el.type === 'checkbox')) return el.closest('label') ?? (el.id ? document.querySelector(`label[for="${el.id}"]`) : null) ?? el
      return el
    }
    const seen = new Set<Element>()
    for (const el of Array.from(document.querySelectorAll('a[href], button, select, input, textarea, [role="button"], summary'))) {
      if (!visible(el) || inline(el) || (el.getBoundingClientRect().width <= 1 && el.getBoundingClientRect().height <= 1) || el.closest('[aria-hidden="true"], [inert], video')) continue
      if (el instanceof HTMLInputElement && el.type === 'range') continue
      const t = target(el)
      if (seen.has(t)) continue
      seen.add(t)
      const r = t.getBoundingClientRect()
      if (r.bottom < 0 || r.top > window.innerHeight * 20) continue
      if (Math.round(r.width) < 44 || Math.round(r.height) < 44) out.push({ rule: 'tap-target', what: `${name(el)} is ${Math.round(r.width)}x${Math.round(r.height)}` })
      if ((el instanceof HTMLInputElement && !['radio', 'checkbox', 'range', 'file', 'button', 'submit'].includes(el.type)) || el instanceof HTMLTextAreaElement || el instanceof HTMLSelectElement) {
        const size = parseFloat(getComputedStyle(el).fontSize)
        if (size < 16) out.push({ rule: 'input-font', what: `${name(el)} has a ${size}px font` })
      }
    }
    const header = document.querySelector('header')
    if (header) {
      const parts = Array.from(header.querySelectorAll('a, button, h1, fieldset, [data-testid="judge-badge"]')).filter(visible)
      const boxes = parts.map((p) => [p, p.getBoundingClientRect()] as const)
      for (const [i, [a, ra]] of boxes.entries()) {
        if (ra.right > vw + 1 || ra.left < -1) out.push({ rule: 'header-overlap', what: `${name(a)} is cut off at the edge` })
        for (const [b, rb] of boxes.slice(i + 1)) {
          if (a.contains(b) || b.contains(a)) continue
          const overlap = Math.min(ra.right, rb.right) - Math.max(ra.left, rb.left) > 1 && Math.min(ra.bottom, rb.bottom) - Math.max(ra.top, rb.top) > 1
          if (overlap) out.push({ rule: 'header-overlap', what: `${name(a)} overlaps ${name(b)}` })
        }
      }
      const text = Array.from(header.querySelectorAll('span, h1, a, button')).filter((e) => visible(e) && e.scrollWidth > e.clientWidth + 1 && getComputedStyle(e).textOverflow !== 'ellipsis')
      for (const e of text) out.push({ rule: 'header-overlap', what: `${name(e)} text is clipped` })
    }
    return out as never
  })
}

/** Screenshot the screen for the report, then fail softly on every finding (so one run lists them all). */
export async function audit(page: Page, info: TestInfo, screen: string, { allow = [] as RegExp[] } = {}) {
  await page.evaluate(() => document.fonts.ready)
  const dir = resolve('../spikes/out/mobile', process.env.AUDIT_LABEL ?? 'after', info.project.name)
  await page.screenshot({ path: `${dir}/${screen}.png` })
  const header = page.locator('header').first()
  if (await header.isVisible()) await header.screenshot({ path: `${dir}/${screen}-header.png` })
  const found = (await findings(page)).filter((f) => !allow.some((a) => a.test(f.what)))
  expect.soft(found, `${screen} on ${info.project.name}`).toEqual([])
}

/** The element is entirely inside the window. */
export async function onScreen(page: Page, selector: ReturnType<Page['locator']>) {
  const b = await selector.boundingBox()
  const v = page.viewportSize()
  return !!b && !!v && b.x >= 0 && b.y >= 0 && b.x + b.width <= v.width + 0.5 && b.y + b.height <= v.height + 0.5
}
