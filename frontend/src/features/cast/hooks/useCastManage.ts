import { useCallback } from 'react'
import { ApiError } from '../../../shared/api/client'
import type { Project } from '../../../shared/api/types'
import { mergeCharacter, removeCharacter, renameCharacter } from '../api'
import { useCastStore } from '../store'

const message = (e: unknown) => (e instanceof ApiError ? e.message : 'The studio did not answer. Try again.')

/** Rename, remove and merge characters. Each returns the whole project, which onProject loads everywhere. */
export function useCastManage(projectId: string, onProject: (p: Project) => void) {
  const run = useCallback(
    async (change: () => Promise<Project>) => {
      useCastStore.getState().set({ managing: true, error: null })
      try {
        onProject(await change())
      } catch (e) {
        useCastStore.getState().set({ error: message(e) })
      } finally {
        useCastStore.getState().set({ managing: false })
      }
    },
    [onProject],
  )
  return {
    rename: (id: string, name: string) => void run(() => renameCharacter(projectId, id, name.trim())),
    remove: (id: string) => void run(() => removeCharacter(projectId, id)),
    merge: (id: string, into: string) => void run(() => mergeCharacter(projectId, id, into)),
  }
}
