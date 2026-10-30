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

/** "Kenya" from "KE", or the code itself where the browser has no names. */
export function countryName(code: string): string {
  try {
    return names?.of(code) ?? code
  } catch {
    return code
  }
}

/** "🇰🇪 Kenya" */
export const country = (code: string) => `${flag(code)} ${countryName(code)}`.trim()

/** How an entry is signed: "by Ama · 🇰🇪 Kenya", "by Ama", "by a storyteller from 🇰🇪 Kenya" or anonymous. */
export function byline(creator: Creator | null | undefined): string {
  const name = creator?.name.trim() ?? ''
  const code = creator?.country ?? ''
  if (name && code) return `by ${name} · ${country(code)}`
  if (name) return `by ${name}`
  if (code) return `by a storyteller from ${country(code)}`
  return 'by an anonymous storyteller'
}

/** The countries, sorted by name for the dropdown. */
export function byName(codes: string[]): { code: string; label: string }[] {
  return codes.map((code) => ({ code, label: `${flag(code)} ${countryName(code)} (${code})` })).sort((a, b) => countryName(a.code).localeCompare(countryName(b.code)))
}
