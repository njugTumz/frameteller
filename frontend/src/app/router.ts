import { useSyncExternalStore } from 'react'

export type Route = { name: 'start' } | { name: 'privacy' } | { name: 'judge' } | { name: 'studio'; projectId: string } | { name: 'share'; token: string } | { name: 'missing' }

const STUDIO = /^\/projects\/([A-Za-z0-9_-]{1,64})\/?$/
const SHARE = /^\/s\/([A-Za-z0-9_-]{1,64})\/?$/

export function parseRoute(pathname: string): Route {
  if (pathname === '/' || pathname === '') return { name: 'start' }
  if (pathname === '/privacy' || pathname === '/privacy/') return { name: 'privacy' }
  if (pathname === '/judge' || pathname === '/judge/') return { name: 'judge' }
  const studio = STUDIO.exec(pathname)
  if (studio?.[1]) return { name: 'studio', projectId: studio[1] }
  const share = SHARE.exec(pathname)
  if (share?.[1]) return { name: 'share', token: share[1] }
  return { name: 'missing' }
}

export function studioPath(projectId: string): string {
  return `/projects/${encodeURIComponent(projectId)}`
}

const listeners = new Set<() => void>()

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  window.addEventListener('popstate', listener)
  return () => {
    listeners.delete(listener)
    window.removeEventListener('popstate', listener)
  }
}

export function navigate(path: string): void {
  window.history.pushState(null, '', path)
  listeners.forEach((l) => l())
}

export function usePathname(): string {
  return useSyncExternalStore(subscribe, () => window.location.pathname)
}
