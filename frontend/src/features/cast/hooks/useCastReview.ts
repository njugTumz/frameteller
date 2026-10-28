import { useCallback } from 'react'
import { ApiError } from '../../../shared/api/client'
import { approveCast, regenerateReference } from '../api'
import { approvalBlock, useCastStore } from '../store'

const message = (e: unknown) => (e instanceof ApiError ? e.message : 'The studio did not answer. Try again.')

export function useCastReview(projectId: string) {
  const approve = useCallback(async () => {
    const s = useCastStore.getState()
    if (s.approving || approvalBlock(s)) return
    const descriptions = Object.fromEntries(
      Object.entries(s.edits).filter(([id, text]) => {
        const current = s.characters.find((c) => c.id === id)?.description
        return text.trim() && text.trim() !== current
      }),
    )
    s.set({ approving: true, error: null })
    try {
      const review = await approveCast(projectId, descriptions)
      const redrawing = Object.fromEntries(review.redrawing.map((id) => [id, true as const]))
      useCastStore.getState().set({
        status: review.approved ? 'approved' : 'draft',
        redrawing: { ...useCastStore.getState().redrawing, ...redrawing },
        drawing: review.redrawing.length > 0 || useCastStore.getState().drawing,
        edits: review.approved ? {} : useCastStore.getState().edits,
      })
    } catch (e) {
      useCastStore.getState().set({ error: message(e) })
    } finally {
      useCastStore.getState().set({ approving: false })
    }
  }, [projectId])

  const regenerate = useCallback(
    async (characterId: string) => {
      const s = useCastStore.getState()
      s.set({ redrawing: { ...s.redrawing, [characterId]: true }, status: 'draft', error: null })
      try {
        await regenerateReference(projectId, characterId)
      } catch (e) {
        const { redrawing } = useCastStore.getState()
        const { [characterId]: _gone, ...rest } = redrawing
        useCastStore.getState().set({ redrawing: rest, error: message(e) })
      }
    },
    [projectId],
  )

  const edit = useCallback((id: string, description: string) => useCastStore.getState().edit(id, description), [])
  return { approve, regenerate, edit }
}
