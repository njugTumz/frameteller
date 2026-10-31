import { useEffect, useRef } from 'react'

/**
 * Calls `onLock` when the page is hidden: the phone locked, the app switched, the tab went to the background.
 * Browsers stop (iOS) or silence the microphone there, so telling pauses cleanly instead of failing.
 */
export function usePauseOnLock(onLock: () => void): void {
  const latest = useRef(onLock)
  useEffect(() => {
    latest.current = onLock
  })
  useEffect(() => {
    const hidden = () => document.visibilityState === 'hidden' && latest.current()
    document.addEventListener('visibilitychange', hidden)
    window.addEventListener('pagehide', hidden)
    return () => {
      document.removeEventListener('visibilitychange', hidden)
      window.removeEventListener('pagehide', hidden)
    }
  }, [])
}
