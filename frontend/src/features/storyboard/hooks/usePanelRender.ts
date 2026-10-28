import { useCallback } from 'react'
import { ApiError } from '../../../shared/api/client'
import type { Shot } from '../../../shared/api/types'
import { renderPanel } from '../api'
import { useStoryboardStore } from '../store'

/** Draw a shot's next revision now: "Draw again" after a failure, or "Draw final" in the editor. */
export function usePanelRender(projectId: string): (shot: Shot, quality: 'draft' | 'final') => Promise<void> {
  return useCallback(
    async (shot, quality) => {
      const store = useStoryboardStore.getState()
      store.markRequested(shot.id, true)
      store.jobStarted(shot.id, { kind: 'generate_panel', status: 'queued', revision: null, message: null })
      try {
        const ticket = await renderPanel(projectId, shot.number, quality)
        useStoryboardStore.getState().jobStarted(shot.id, { kind: 'generate_panel', status: 'queued', revision: ticket.revision, message: null })
      } catch (e) {
        useStoryboardStore.getState().jobStarted(shot.id, {
          kind: 'generate_panel',
          status: 'failed',
          revision: null,
          message: e instanceof ApiError ? e.message : 'This panel could not be drawn.',
        })
      }
    },
    [projectId],
  )
}
