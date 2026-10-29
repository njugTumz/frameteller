/**
 * A random id for this browser, sent as X-Visitor-Id so the public demo can count new stories per visitor.
 * The backend only keeps a hash of it with the IP address. It is not a cookie and identifies no one.
 */
const KEY = 'frameteller.visitor'
let fallback: string | null = null

function newId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`
}

export function visitorId(): string {
  try {
    const kept = window.localStorage.getItem(KEY)
    if (kept && /^[A-Za-z0-9-]{8,64}$/.test(kept)) return kept
    const id = newId()
    window.localStorage.setItem(KEY, id)
    return id
  } catch {
    fallback ??= newId() // storage blocked: one id for this page load
    return fallback
  }
}
