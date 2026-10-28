import { useCallback } from 'react'
import { ApiError } from '../../../shared/api/client'
import type { Mask, Shot, Ticket } from '../../../shared/api/types'
import { editPanel, selectObject } from '../api'
import { cachedMaskAt, instructionFor, toPanelPoint, useEditorStore } from '../store'

const message = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback)

export interface EditorActions {
  /** `cached` masks and the panel size let a click on a pre-segmented character show its outline at once. */
  select(point: { x: number; y: number }, preview: { width: number; height: number }, cached?: { masks: Mask[]; panel: { width: number; height: number } }): Promise<void>
  sendEdit(): Promise<void>
  drawFinal(): Promise<void>
}

/**
 * Click-to-select, appearance edits and the final render for one shot's panel. Edits and renders are jobs:
 * onQueued hands the ticket to the storyboard, which shows progress from job.updated.
 */
export function usePanelEditor(
  projectId: string,
  shot: Shot | null,
  onQueued: (shot: Shot, ticket: Ticket) => void,
  draw: (shot: Shot, quality: 'draft' | 'final') => Promise<void>,
): EditorActions {
  const select = useCallback(
    async (point: { x: number; y: number }, preview: { width: number; height: number }, cached?: { masks: Mask[]; panel: { width: number; height: number } }) => {
      if (!shot) return
      const s = useEditorStore.getState()
      if (s.selecting) return
      const hint = cached ? cachedMaskAt(cached.masks, toPanelPoint(point.x, point.y, preview, cached.panel)) : null
      s.set({ selecting: !hint, selectError: null, ...(hint ? { selection: { mask: hint, cached: true, ms: 0 } } : {}) })
      const started = performance.now()
      try {
        const selection = await selectObject(projectId, shot.number, point, preview)
        useEditorStore.getState().set({ selection: { ...selection, ms: Math.round(performance.now() - started) } })
      } catch (e) {
        const text = e instanceof ApiError && e.code === 'nothing_to_select' ? 'Nothing to select there. Click on a character or an object.' : message(e, 'Selecting did not work. Try again.')
        useEditorStore.getState().set({ selection: null, selectError: text })
      } finally {
        useEditorStore.getState().set({ selecting: false })
      }
    },
    [projectId, shot],
  )

  const remember = useCallback(() => {
    const image = shot?.panel?.image_url
    if (image && shot?.panel) useEditorStore.getState().set({ before: { imageUrl: image, revision: shot.panel.revision }, showBefore: false })
  }, [shot])

  const sendEdit = useCallback(async () => {
    const s = useEditorStore.getState()
    const instruction = instructionFor(s.instruction, s.selection?.mask ?? null)
    if (!shot || !instruction || s.sending) return
    s.set({ sending: true, editError: null })
    try {
      const ticket = await editPanel(projectId, shot.number, instruction)
      remember()
      onQueued(shot, ticket)
      useEditorStore.getState().set({ instruction: '' })
    } catch (e) {
      useEditorStore.getState().set({ editError: message(e, 'The change was not sent. Try again.') })
    } finally {
      useEditorStore.getState().set({ sending: false })
    }
  }, [projectId, shot, onQueued, remember])

  const drawFinal = useCallback(async () => {
    if (!shot) return
    remember()
    await draw(shot, 'final')
  }, [shot, draw, remember])

  return { select, sendEdit, drawFinal }
}
