import { useCallback, useEffect, useState } from 'react'
import { wakeBackend, type Wake } from '../api/health'

/** Wakes the backend on mount (staging scales to zero) and offers a retry when it stays asleep. */
export function useBackendWake(): { wake: Wake; retry: () => void } {
  const [wake, setWake] = useState<Wake>('checking')
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    void wakeBackend({ signal: controller.signal, onProgress: (s) => !controller.signal.aborted && setWake(s) })
    return () => controller.abort()
  }, [attempt])
  const retry = useCallback(() => setAttempt((n) => n + 1), [])
  return { wake, retry }
}
