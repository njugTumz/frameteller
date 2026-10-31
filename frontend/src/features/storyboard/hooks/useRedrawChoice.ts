import { useCallback, useState } from 'react'
import { ApiError } from '../../../shared/api/client'
import type { Shot } from '../../../shared/api/types'
import { restorePanelVersion } from '../api'
import { useStoryboardStore } from '../store'

/** Use new / Keep previous after a Redraw, and Use this on any earlier version in the editor (ADR 0022). */
export function useRedrawChoice(projectId: string) {
  /** The drawing being brought back. */
  const [busy, setBusy] = useState<{ shotId: string; revision: number } | null>(null)
  /** Why bringing a drawing back failed, by shot. */
  const [error, setError] = useState<{ shotId: string; message: string } | null>(null)

  const useNew = useCallback((shot: Shot) => useStoryboardStore.getState().redrawFrom(shot.id, null), [])

  const restore = useCallback(
    async (shot: Shot, revision: number) => {
      setBusy({ shotId: shot.id, revision })
      setError(null)
      try {
        const project = await restorePanelVersion(projectId, shot.number, revision)
        const store = useStoryboardStore.getState()
        store.redrawFrom(shot.id, null)
        store.load(project)
      } catch (e) {
        setError({ shotId: shot.id, message: e instanceof ApiError ? e.message : 'That drawing could not be brought back. Try again.' })
      } finally {
        setBusy(null)
      }
    },
    [projectId],
  )

  return { busy, error, useNew, restore }
}
