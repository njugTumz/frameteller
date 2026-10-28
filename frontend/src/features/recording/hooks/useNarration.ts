import { useEffect, useState } from 'react'
import type { ServerEvent } from '../../../shared/events'
import { Narration, type NarrationDeps } from '../session/narration'
import { useRecordingStore } from '../store'

/** The narration controller for one project. Unmounting turns the mic off and closes the socket. */
export function useNarration(
  projectId: string,
  extraKeywords: readonly string[],
  onEvent: (e: ServerEvent) => void,
  overrides: Pick<NarrationDeps, 'openMic' | 'socketFactory'> = {},
): Narration {
  const [narration] = useState(() => new Narration(projectId, { store: useRecordingStore, ...overrides }))
  useEffect(() => narration.use({ onEvent, extraKeywords }))
  useEffect(() => {
    narration.attach()
    return () => narration.dispose()
  }, [narration])
  return narration
}
