import { useCallback, useState } from 'react'

const KEY = 'frameteller.guide-seen'

function seen(): boolean {
  try {
    return window.localStorage.getItem(KEY) === '1'
  } catch {
    return false
  }
}

/** The three-step guide shows on a browser's first visit until dismissed (or always, if storage is blocked). */
export function useFirstVisit(): { show: boolean; dismiss: () => void } {
  const [show, setShow] = useState(() => !seen())
  const dismiss = useCallback(() => {
    setShow(false)
    try {
      window.localStorage.setItem(KEY, '1')
    } catch {
      // storage blocked: hidden for this page only
    }
  }, [])
  return { show, dismiss }
}
