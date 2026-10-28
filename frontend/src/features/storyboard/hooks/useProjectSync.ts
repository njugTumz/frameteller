import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../../../shared/api/client'
import type { Project } from '../../../shared/api/types'
import { getProject } from '../api'
import { useStoryboardStore, type SyncStatus } from '../store'

const POLL_MS = 4000
const REFRESH_DEBOUNCE_MS = 250

function hasWorkInFlight(project: Project | null): boolean {
  return !!project?.shots.some((s) => s.panel?.status === 'pending')
}

/**
 * Keeps the storyboard in step with the server: loads the project, fetches it again when a job finishes
 * (job.updated carries no image URL), and polls while panels are drawing and no session socket is open.
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
      if (hasWorkInFlight(last.current) || Object.values(useStoryboardStore.getState().jobs).some((j) => j.status === 'queued' || j.status === 'running')) {
        void fetchNow()
      }
    }, POLL_MS)
    return () => clearInterval(t)
  }, [connected, fetchNow])

  const retry = useCallback(() => {
    useStoryboardStore.getState().setSync('loading')
    setAttempt((n) => n + 1)
  }, [])
  return { status, retry }
}
