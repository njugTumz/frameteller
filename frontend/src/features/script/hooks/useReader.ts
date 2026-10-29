import { useEffect, useState } from 'react'
import type { ServerEvent } from '../../../shared/events'
import { useRecordingStore } from '../../recording/store'
import { Reader, type ReaderDeps } from '../session/reader'
import { useScriptStore } from '../store'

/** The "Read it to me" controller for one project. Unmounting stops the voice and closes the socket. */
export function useReader(projectId: string, onEvent: (e: ServerEvent) => void, overrides: Pick<ReaderDeps, 'socketFactory' | 'player'> = {}): Reader {
  const [reader] = useState(() => new Reader(projectId, { recording: useRecordingStore, script: useScriptStore, ...overrides }))
  useEffect(() => reader.use(onEvent))
  useEffect(() => () => reader.dispose(), [reader])
  return reader
}
