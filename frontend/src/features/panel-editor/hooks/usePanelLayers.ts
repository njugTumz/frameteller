import { useCallback } from 'react'
import { ApiError } from '../../../shared/api/client'
import type { Layer, Shot } from '../../../shared/api/types'
import { useStoryboardStore } from '../../storyboard/store'
import { saveLayer } from '../api'
import { NO_MOVE, clampMove, useEditorStore, type Move } from '../store'

/** The panel's saved layers as editor moves, by object id. */
export function movesFromLayers(layers: Layer[]): Record<string, Move> {
  return Object.fromEntries(layers.filter((l) => !l.deleted).map((l) => [l.object_id, { dx: l.dx, dy: l.dy, scale: l.scale }]))
}

/**
 * Moves are saved to the panel as layers: the first move of an object asks for a clean plate, and the
 * storyboard shows the composite once compose_panel finishes ("Preparing the background…" meanwhile).
 */
export function usePanelLayers(projectId: string, shot: Shot | null) {
  const save = useCallback(
    async (objectId: string, move: Move) => {
      if (!shot?.panel) return
      const revision = shot.panel.revision
      const clamped = clampMove(move)
      useEditorStore.getState().setMove(shot.id, revision, objectId, clamped)
      useStoryboardStore.getState().set({ composing: { ...useStoryboardStore.getState().composing, [shot.id]: 'queued' } })
      try {
        await saveLayer(projectId, shot.number, objectId, clamped)
        useEditorStore.getState().set({ editError: null })
      } catch (e) {
        const { [shot.id]: _gone, ...rest } = useStoryboardStore.getState().composing
        useStoryboardStore.getState().set({ composing: rest })
        useEditorStore.getState().set({ editError: e instanceof ApiError ? e.message : 'The move was not saved. Try again.' })
      }
    },
    [projectId, shot],
  )

  /** "Put everything back": every moved object home, which removes its layer. */
  const resetAll = useCallback(
    async (objectIds: string[]) => {
      if (!shot?.panel) return
      for (const id of objectIds) await save(id, NO_MOVE)
      useEditorStore.getState().resetMoves(shot.id, shot.panel.revision)
    },
    [shot, save],
  )

  return { save, resetAll }
}
