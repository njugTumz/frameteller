import { useStoryEditsStore } from '../../features/story-edits/store'
import { useCastStore } from '../../features/cast/store'
import { useRecordingStore } from '../../features/recording/store'
import { useScriptStore } from '../../features/script/store'
import { useStoryboardStore } from '../../features/storyboard/store'
import type { Project } from '../../shared/api/types'
import type { ServerEvent } from '../../shared/events'

/** Fan one session event out to the feature stores. The recording store gets it from the narration itself. */
export function dispatchEvent(e: ServerEvent): void {
  useStoryboardStore.getState().apply(e)
  useCastStore.getState().apply(e)
  useScriptStore.getState().apply(e)
}

/** A fresh copy of the project (the storyboard store has already taken its shots). */
export function projectLoaded(p: Project): void {
  useCastStore.getState().load(p)
  const r = useRecordingStore.getState()
  if (r.turns.length === 0 && p.turns.length > 0) r.loadTurns(p.turns)
}

export function resetStudio(): void {
  useStoryboardStore.getState().reset()
  useCastStore.getState().reset()
  useRecordingStore.getState().reset()
  useScriptStore.getState().reset()
  useStoryEditsStore.getState().reset()
}
