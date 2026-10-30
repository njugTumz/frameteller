import { useCallback } from 'react'
import { ApiError } from '../../../shared/api/client'
import type { Character } from '../../../shared/api/types'
import { approveCast, regenerateLook, regenerateReference } from '../api'
import { approvalBlock, useCastStore } from '../store'

/** The text a key's sheet is drawn from: a character's description, or a look's clothes ("wren/farmer_costume"). */
function currentText(characters: Character[], key: string): string | undefined {
  const [id, look] = key.split('/')
  const c = characters.find((x) => x.id === id)
  return look ? c?.looks?.find((l) => l.id === look)?.clothes : c?.description
}

const message = (e: unknown) => (e instanceof ApiError ? e.message : 'The studio did not answer. Try again.')

export function useCastReview(projectId: string) {
  const approve = useCallback(async () => {
    const s = useCastStore.getState()
    if (s.approving || approvalBlock(s)) return
    const descriptions = Object.fromEntries(
      Object.entries(s.edits).filter(([key, text]) => text.trim() && text.trim() !== currentText(s.characters, key)),
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
        const [id = characterId, look] = characterId.split('/')
        await (look ? regenerateLook(projectId, id, look) : regenerateReference(projectId, characterId))
      } catch (e) {
        const { redrawing } = useCastStore.getState()
        const { [characterId]: _gone, ...rest } = redrawing
        useCastStore.getState().set({ redrawing: rest, error: message(e) })
      }
    },
    [projectId],
  )

  /** A sheet that failed: draw it again with the description as the user has just edited it. */
  const redrawWith = useCallback(
    async (characterId: string) => {
      const s = useCastStore.getState()
      const text = s.edits[characterId]?.trim()
      if (!text) return regenerate(characterId)
      s.set({ redrawing: { ...s.redrawing, [characterId]: true }, status: 'draft', error: null })
      try {
        await approveCast(projectId, { [characterId]: text })
      } catch (e) {
        const { [characterId]: _gone, ...rest } = useCastStore.getState().redrawing
        useCastStore.getState().set({ redrawing: rest, error: message(e) })
      }
    },
    [projectId, regenerate],
  )

  const edit = useCallback((id: string, description: string) => useCastStore.getState().edit(id, description), [])
  return { approve, regenerate, redrawWith, edit }
}
