import { useCallback, useEffect, useRef } from 'react'
import { ApiError } from '../../../shared/api/client'
import type { Project } from '../../../shared/api/types'
import { useRecordingStore } from '../../recording/store'
import { deleteShot, mergeBeats, removeBeat } from '../api'
import { UNDO_MS, useStoryEditsStore, type PendingRemoval } from '../store'

const message = (e: unknown) => (e instanceof ApiError ? e.message : 'The studio did not answer. Try again.')

/**
 * Remove a beat or delete a shot with Undo: the card leaves the view at once, and the change is sent when the
 * 10-second toast goes (or sooner: before an export, another removal, or leaving the page). Merges go at once.
 */
export function useStoryEdits(projectId: string, onProject: (p: Project) => void) {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const loaded = useCallback(
    (p: Project) => {
      onProject(p)
      useRecordingStore.getState().loadTurns(p.turns) // the beats as the server now has them
    },
    [onProject],
  )

  const flush = useCallback(async () => {
    const store = useStoryEditsStore.getState()
    const pending = store.pending
    if (timer.current) clearTimeout(timer.current)
    timer.current = null
    if (!pending) return
    store.set({ pending: null, error: null })
    try {
      loaded(await (pending.kind === 'beat' ? removeBeat(projectId, pending.id) : deleteShot(projectId, pending.id)))
    } catch (e) {
      useStoryEditsStore.getState().set({ error: message(e) })
    } finally {
      useStoryEditsStore.getState().show(pending.id)
    }
  }, [projectId, loaded])

  const remove = useCallback(
    (removal: PendingRemoval) => {
      void flush() // one Undo at a time: the earlier removal goes now
      const store = useStoryEditsStore.getState()
      store.hide(removal.id)
      store.set({ pending: removal, error: null })
      timer.current = setTimeout(() => void flush(), UNDO_MS)
    },
    [flush],
  )

  const undo = useCallback(() => {
    const { pending } = useStoryEditsStore.getState()
    if (timer.current) clearTimeout(timer.current)
    timer.current = null
    if (!pending) return
    useStoryEditsStore.getState().show(pending.id)
    useStoryEditsStore.getState().set({ pending: null })
  }, [])

  const merge = useCallback(
    async (turnId: string, other: 'previous' | 'next') => {
      await flush()
      useStoryEditsStore.getState().set({ busy: true, error: null })
      try {
        loaded(await mergeBeats(projectId, turnId, other))
      } catch (e) {
        useStoryEditsStore.getState().set({ error: message(e) })
      } finally {
        useStoryEditsStore.getState().set({ busy: false })
      }
    },
    [projectId, flush, loaded],
  )

  // Leaving the studio (another page, a closed tab) sends what is pending rather than dropping it.
  useEffect(() => {
    const leave = () => void flush()
    window.addEventListener('pagehide', leave)
    return () => {
      window.removeEventListener('pagehide', leave)
      leave()
    }
  }, [flush])

  return { remove, undo, merge, flush }
}
