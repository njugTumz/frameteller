import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../../../shared/api/client'
import type { Project } from '../../../shared/api/types'
import { useRecordingStore } from '../../recording/store'
import { getJobStatus, getProject } from '../api'
import { hasJobsInFlight, inFlightKeys, useStoryboardStore, type SyncStatus } from '../store'

const POLL_MS = 4000
const REFRESH_DEBOUNCE_MS = 250
/** A job with no job.updated for this long is checked: its events may have been lost with a dropped socket. */
export const QUIET_JOB_MS = 20_000
const WATCHDOG_MS = 5000

/**
 * Keeps the storyboard in step with the server: loads the project, fetches it again when a job finishes
 * (job.updated carries no image URL), and polls while work is in flight and no session socket is open.
 *
 * Events can be lost: the socket drops when a new studio version goes live, or the tab sleeps. So the project
 * is fetched again whenever the socket drops or reconnects, the tab becomes visible again, or a job has been
 * quiet for 20 s; quiet jobs are then asked for by key (GET /projects/{id}/jobs/{key}) and reconciled.
 */
export function useProjectSync(projectId: string, connected: boolean, onLoaded: (p: Project) => void): { status: SyncStatus; retry: () => void } {
  const status = useStoryboardStore((s) => s.sync)
  const [attempt, setAttempt] = useState(0)
  const stale = useStoryboardStore((s) => s.stale)
  const last = useRef<Project | null>(null)
  const onLoadedRef = useRef(onLoaded)
  useEffect(() => {
    onLoadedRef.current = onLoaded
  })

  const fetchNow = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const project = await getProject(projectId, signal)
        if (signal?.aborted) return
        last.current = project
        useStoryboardStore.getState().load(project)
        onLoadedRef.current(project)
        // "Updating the studio" stays until whatever was running has been seen through.
        if (useRecordingStore.getState().updating && !hasJobsInFlight(useStoryboardStore.getState())) {
          useRecordingStore.getState().set({ updating: false })
        }
      } catch (e) {
        if (signal?.aborted) return
        const { setSync } = useStoryboardStore.getState()
        if (e instanceof ApiError && e.status === 404) setSync('missing')
        else if (!last.current) setSync('unreachable') // keep showing what we have on a passing blip
      }
    },
    [projectId],
  )

  useEffect(() => {
    const controller = new AbortController()
    void fetchNow(controller.signal)
    return () => controller.abort()
  }, [fetchNow, attempt])

  useEffect(() => {
    if (!stale) return
    const t = setTimeout(() => void fetchNow(), REFRESH_DEBOUNCE_MS)
    return () => clearTimeout(t)
  }, [stale, fetchNow])

  useEffect(() => {
    if (connected) return
    const t = setInterval(() => {
      if (hasJobsInFlight(useStoryboardStore.getState())) void fetchNow()
    }, POLL_MS)
    return () => clearInterval(t)
  }, [connected, fetchNow])

  // The socket dropped or came back: whatever happened in between is only in the project.
  const wasConnected = useRef(connected)
  useEffect(() => {
    if (wasConnected.current === connected) return
    wasConnected.current = connected
    void fetchNow()
  }, [connected, fetchNow])

  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === 'visible') void fetchNow()
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => document.removeEventListener('visibilitychange', onVisible)
  }, [fetchNow])

  useEffect(() => {
    const t = setInterval(() => {
      const board = useStoryboardStore.getState()
      if (!hasJobsInFlight(board) || Date.now() - board.lastJobAt < QUIET_JOB_MS) return
      board.set({ lastJobAt: Date.now() }) // check again in 20 s at the earliest
      void (async () => {
        await fetchNow()
        for (const key of inFlightKeys(useStoryboardStore.getState())) {
          try {
            const job = await getJobStatus(projectId, key)
            useStoryboardStore.getState().resolve(key, job.status, job.message ?? null)
          } catch {
            // unreachable for now: the next check tries again
          }
        }
      })()
    }, WATCHDOG_MS)
    return () => clearInterval(t)
  }, [projectId, fetchNow])

  const retry = useCallback(() => {
    useStoryboardStore.getState().setSync('loading')
    setAttempt((n) => n + 1)
  }, [])
  return { status, retry }
}
