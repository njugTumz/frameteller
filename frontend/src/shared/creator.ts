import type { Creator } from './api/types'

export const MAX_NAME = 40

/** How the creator signs a gallery entry. Empty strings leave a field out. */
export interface Signature {
  name: string
  country: string
}

const names = (() => {
  try {
    return new Intl.DisplayNames(['en'], { type: 'region', fallback: 'code' })
  } catch {
    return null
  }
})()

/** 🇰🇪 from "KE": the two regional indicator symbols. */
export function flag(code: string): string {
  if (!/^[A-Z]{2}$/.test(code)) return ''
  return String.fromCodePoint(...[...code].map((c) => 0x1f1e6 + c.charCodeAt(0) - 65))
}

/**
 * Whether this browser draws flag emoji as flags. Windows draws the two regional indicators as letters ("AE"),
 * and a system without an emoji font draws empty boxes; either way the flag is left out. Checked once by drawing
 * a flag on a small canvas and looking for colour: a flag has some, letters and boxes are drawn in one ink.
 */
export function detectFlagEmoji(): boolean {
  try {
    const canvas = document.createElement('canvas')
    canvas.width = canvas.height = 24
    const ctx = canvas.getContext('2d', { willReadFrequently: true })
    if (!ctx) return false
    ctx.textBaseline = 'top'
    ctx.font = '20px "Apple Color Emoji", "Segoe UI Emoji", "Noto Color Emoji", sans-serif'
    ctx.fillStyle = '#000'
    ctx.fillText(flag('US'), 0, 0)
    const { data } = ctx.getImageData(0, 0, 24, 24)
    for (let i = 0; i < data.length; i += 4) {
      const [r = 0, g = 0, b = 0, a = 0] = [data[i], data[i + 1], data[i + 2], data[i + 3]]
      if (a > 0 && Math.max(r, g, b) - Math.min(r, g, b) > 60) return true
    }
    return false
  } catch {
    return false
  }
}

let flagSupport: boolean | null = null

/** Flags are shown only where they draw as flags (see detectFlagEmoji). */
export function flagsShown(): boolean {
  flagSupport ??= detectFlagEmoji()
  return flagSupport
}

/** Check again on the next use (tests switch the canvas between a flag and letters). */
export function resetFlagSupport(): void {
  flagSupport = null
}

/** "Kenya" from "KE", or the code itself where the browser has no names. */
export function countryName(code: string): string {
  try {
    return names?.of(code) ?? code
  } catch {
    return code
  }
}

/** "🇰🇪 Kenya", or "Kenya" where flags would show as letters. */
export const country = (code: string) => (flagsShown() ? `${flag(code)} ${countryName(code)}`.trim() : countryName(code))

/** How an entry is signed: "by Ama · 🇰🇪 Kenya" ("by Ama · Kenya" without flags), "by Ama", "by a storyteller from
 * 🇰🇪 Kenya" or anonymous. */
export function byline(creator: Creator | null | undefined): string {
  const name = creator?.name.trim() ?? ''
  const code = creator?.country ?? ''
  if (name && code) return `by ${name} · ${country(code)}`
  if (name) return `by ${name}`
  if (code) return `by a storyteller from ${country(code)}`
  return 'by an anonymous storyteller'
}

/** The countries, sorted by name for the dropdown, with their ISO codes: "🇰🇪 Kenya (KE)", or "Kenya (KE)". */
export function byName(codes: string[]): { code: string; label: string }[] {
  return codes.map((code) => ({ code, label: `${country(code)} (${code})` })).sort((a, b) => countryName(a.code).localeCompare(countryName(b.code)))
}
