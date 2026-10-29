import { useCallback } from 'react'
import { ApiError } from '../../../shared/api/client'
import { saveKeepAudio } from '../../../shared/consent'
import { parseNames, saveNames } from '../../../shared/keywords'
import { MAX_SCRIPT_CHARS, saveChoice } from '../../script/choice'
import { createProject } from '../api'
import { SAMPLE_CHOICE, SAMPLE_STORY } from '../sample'
import { useStartStore } from '../store'

/** Create the project, remember the names typed for it, and hand its id on (the app opens the studio). */
export function useStartStory(onCreated: (projectId: string) => void): () => Promise<void> {
  return useCallback(async () => {
    const s = useStartStore.getState()
    if (s.creating) return
    if (s.mode !== 'narrate' && !s.script.trim()) return s.setError('Paste or upload your script first.')
    if (s.script.length > MAX_SCRIPT_CHARS && s.mode !== 'narrate') {
      return s.setError(`Scripts can be up to ${MAX_SCRIPT_CHARS.toLocaleString('en-US')} characters. Shorten this one, or split it into another story.`)
    }
    s.setCreating(true)
    s.setError(null)
    try {
      const project = await createProject(s.title.trim() || 'Untitled story', s.style)
      saveNames(project.id, parseNames(s.names))
      saveKeepAudio(project.id, s.keepAudio)
      saveChoice(project.id, { mode: s.mode, script: s.mode === 'narrate' ? '' : s.script, format: s.format, voice: s.voice, language: s.language })
      onCreated(project.id)
    } catch (e) {
      s.setError(e instanceof ApiError ? e.message : 'Something went wrong. Try again.')
    } finally {
      useStartStore.getState().setCreating(false)
    }
  }, [onCreated])
}

/** "Try a sample story": the built-in script, read by the Brandon voice, in a new project of its own. */
export function useSampleStory(onCreated: (projectId: string) => void): () => Promise<void> {
  return useCallback(async () => {
    const s = useStartStore.getState()
    if (s.creating) return
    s.setCreating(true)
    s.setError(null)
    try {
      const project = await createProject(SAMPLE_STORY.title, SAMPLE_STORY.style)
      saveNames(project.id, parseNames(SAMPLE_STORY.names))
      saveKeepAudio(project.id, true)
      saveChoice(project.id, SAMPLE_CHOICE)
      onCreated(project.id)
    } catch (e) {
      s.setError(e instanceof ApiError ? e.message : 'Something went wrong. Try again.')
    } finally {
      useStartStore.getState().setCreating(false)
    }
  }, [onCreated])
}
