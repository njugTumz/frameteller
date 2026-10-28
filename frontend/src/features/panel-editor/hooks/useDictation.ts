import { useCallback, useEffect, useRef } from 'react'
import { ApiError } from '../../../shared/api/client'
import { openMicrophone, type Microphone } from '../../../shared/audio/microphone'
import { BYTES_PER_MS, wav } from '../../../shared/audio/pcm'
import { dictate } from '../api'
import { useEditorStore } from '../store'

const MAX_MS = 30_000

/** The mic button next to the edit box: record, then Muse Voice Transcribe (via the backend) fills the box. */
export function useDictation(projectId: string, openMic: typeof openMicrophone = openMicrophone) {
  const mic = useRef<Microphone | null>(null)
  const frames = useRef<ArrayBuffer[]>([])
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const finish = useCallback(async () => {
    if (timer.current) clearTimeout(timer.current)
    const m = mic.current
    mic.current = null
    if (!m) return
    await m.close()
    const bytes = frames.current.reduce((n, f) => n + f.byteLength, 0)
    const pcm = new Int16Array(bytes / 2)
    let at = 0
    for (const f of frames.current) {
      pcm.set(new Int16Array(f), at)
      at += f.byteLength / 2
    }
    frames.current = []
    const store = useEditorStore.getState()
    if (bytes < BYTES_PER_MS * 300) return store.set({ dictation: 'idle', editError: 'That was too short to hear. Talk a little longer, or type the change.' })
    store.set({ dictation: 'transcribing', editError: null })
    try {
      const text = await dictate(projectId, wav(pcm))
      const s = useEditorStore.getState()
      s.set(text ? { instruction: text } : { editError: 'Nothing was heard. Try again, or type the change.' })
    } catch (e) {
      useEditorStore.getState().set({ editError: e instanceof ApiError ? e.message : 'Dictation did not work. Type the change instead.' })
    } finally {
      useEditorStore.getState().set({ dictation: 'idle' })
    }
  }, [projectId])

  const start = useCallback(async () => {
    if (mic.current || useEditorStore.getState().dictation !== 'idle') return
    frames.current = []
    useEditorStore.getState().set({ dictation: 'recording', editError: null })
    try {
      mic.current = await openMic({
        onFrame: (pcm) => frames.current.push(pcm),
        onLevel: () => undefined,
        onLost: () => void finish(),
      })
      timer.current = setTimeout(() => void finish(), MAX_MS)
    } catch (e) {
      useEditorStore.getState().set({ dictation: 'idle', editError: e instanceof Error ? `${e.message} Type the change instead.` : 'The microphone is not available. Type the change instead.' })
    }
  }, [openMic, finish])

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current)
      void mic.current?.close()
      mic.current = null
    },
    [],
  )

  return { start, stop: finish }
}
