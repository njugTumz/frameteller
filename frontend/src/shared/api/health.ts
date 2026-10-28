import { API_BASE_URL } from '../../config'

export type Wake = 'checking' | 'waking' | 'ready' | 'asleep'

export interface WakeOptions {
  /** Give up after this long. Container Apps scales staging to zero; a cold start takes 10-20 s. */
  deadlineMs?: number
  attemptTimeoutMs?: number
  retryDelayMs?: number
  onProgress?: (state: Wake) => void
  signal?: AbortSignal
  fetcher?: typeof fetch
}

const sleep = (ms: number, signal?: AbortSignal) =>
  new Promise<void>((resolve) => {
    const t = setTimeout(resolve, ms)
    signal?.addEventListener('abort', () => (clearTimeout(t), resolve()), { once: true })
  })

/** Ping /healthz until the backend answers. Reports "waking" once the first attempt fails or is slow. */
export async function wakeBackend({
  deadlineMs = 90_000,
  attemptTimeoutMs = 10_000,
  retryDelayMs = 2_000,
  onProgress,
  signal,
  fetcher = fetch,
}: WakeOptions = {}): Promise<boolean> {
  const started = Date.now()
  onProgress?.('checking')
  const slow = setTimeout(() => onProgress?.('waking'), 1_500)
  try {
    while (!signal?.aborted && Date.now() - started < deadlineMs) {
      const attempt = new AbortController()
      const timer = setTimeout(() => attempt.abort(), attemptTimeoutMs)
      try {
        const r = await fetcher(`${API_BASE_URL}/healthz`, { signal: attempt.signal, cache: 'no-store' })
        if (r.ok) {
          onProgress?.('ready')
          return true
        }
      } catch {
        // not up yet
      } finally {
        clearTimeout(timer)
      }
      onProgress?.('waking')
      await sleep(retryDelayMs, signal)
    }
    onProgress?.('asleep')
    return false
  } finally {
    clearTimeout(slow)
  }
}
