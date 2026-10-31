import { useCallback } from 'react'
import { ApiError } from '../../../shared/api/client'
import type { Shot } from '../../../shared/api/types'
import type { RedrawChoice } from '../../../shared/ui/Redraw'
import { renderPanel } from '../api'
import { useStoryboardStore } from '../store'

export type DrawPanel = (shot: Shot, quality: 'draft' | 'final', redraw?: RedrawChoice) => Promise<void>

/**
 * Draw a shot's next revision now: "Draw final" in the editor, or a Redraw (ADR 0022), which remembers the
 * drawing it replaces so the card can offer Keep previous.
 */
export function usePanelRender(projectId: string): DrawPanel {
  return useCallback(
    async (shot, quality, redraw) => {
      const store = useStoryboardStore.getState()
      store.markRequested(shot.id, true)
      store.jobStarted(shot.id, { kind: 'generate_panel', status: 'queued', revision: null, message: null })
      const shown = shot.panel?.status === 'ready' && shot.panel.image_url ? shot.panel.shown_revision : null
      store.redrawFrom(shot.id, redraw ? shown : null)
      try {
        const ticket = await renderPanel(projectId, shot.number, quality, redraw)
        useStoryboardStore.getState().jobStarted(shot.id, { kind: 'generate_panel', status: 'queued', revision: ticket.revision, message: null, key: ticket.key })
      } catch (e) {
        useStoryboardStore.getState().redrawFrom(shot.id, null)
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
