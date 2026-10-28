import { useEffect } from 'react'
import { ApiError } from '../../../shared/api/client'
import type { Shot } from '../../../shared/api/types'
import { renderPanel } from '../api'
import { useStoryboardStore } from '../store'

/** Shots that should get a draft now: never drawn, nothing queued, not asked for yet, and their cast approved. */
export function shotsToDraft(shots: Shot[], jobs: Record<string, unknown>, requested: Record<string, true>, canDraw: (s: Shot) => boolean): Shot[] {
  return shots.filter((s) => !s.panel && !jobs[s.id] && !requested[s.id] && canDraw(s))
}

/**
 * Draws a draft panel for every shot as soon as its cast is approved (ADR 0004): straight after approval for
 * the shots so far, then for each new shot as it arrives. Renders run as background jobs; nothing waits here.
 */
export function useAutoDraft(projectId: string, canDraw: (s: Shot) => boolean): void {
  const shots = useStoryboardStore((s) => s.shots)
  const jobs = useStoryboardStore((s) => s.jobs)
  const requested = useStoryboardStore((s) => s.requested)
  const loaded = useStoryboardStore((s) => s.loaded)

  useEffect(() => {
    if (!loaded) return
    const store = useStoryboardStore.getState()
    for (const shot of shotsToDraft(shots, jobs, requested, canDraw)) {
      store.markRequested(shot.id, true)
      renderPanel(projectId, shot.number, 'draft')
        .then((t) => store.jobStarted(shot.id, { kind: 'generate_panel', status: 'queued', revision: t.revision, message: null }))
        .catch((e: unknown) => {
          // 409: the cast went back to draft (a new character); it is requested again after approval.
          if (e instanceof ApiError && e.status === 409) return store.markRequested(shot.id, false)
          store.jobStarted(shot.id, { kind: 'generate_panel', status: 'failed', revision: null, message: e instanceof Error ? e.message : 'This panel could not be drawn.' })
        })
    }
  }, [projectId, shots, jobs, requested, loaded, canDraw])
}
