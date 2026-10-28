import { useCallback } from 'react'
import { ApiError } from '../../../shared/api/client'
import { saveKeepAudio } from '../../../shared/consent'
import { parseNames, saveNames } from '../../../shared/keywords'
import { createProject } from '../api'
import { useStartStore } from '../store'

/** Create the project, remember the names typed for it, and hand its id on (the app opens the studio). */
export function useStartStory(onCreated: (projectId: string) => void): () => Promise<void> {
  return useCallback(async () => {
    const s = useStartStore.getState()
    if (s.creating) return
    s.setCreating(true)
    s.setError(null)
    try {
      const project = await createProject(s.title.trim() || 'Untitled story', s.style)
      saveNames(project.id, parseNames(s.names))
      saveKeepAudio(project.id, s.keepAudio)
      onCreated(project.id)
    } catch (e) {
      s.setError(e instanceof ApiError ? e.message : 'Something went wrong. Try again.')
    } finally {
      useStartStore.getState().setCreating(false)
    }
  }, [onCreated])
}
