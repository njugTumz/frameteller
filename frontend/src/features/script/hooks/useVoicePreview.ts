import { useCallback, useEffect, useRef, useState } from 'react'
import type { Voice } from '../../../shared/api/types'
import { previewUrl } from '../api'

/** Play one voice's preview at a time. Returns the voice playing, and a function to play another. */
export function useVoicePreview(): { previewing: string | null; play: (voice: Voice, language: string) => void } {
  const player = useRef<HTMLAudioElement | null>(null)
  const [previewing, setPreviewing] = useState<string | null>(null)
  useEffect(() => () => player.current?.pause(), [])
  const play = useCallback((voice: Voice, language: string) => {
    player.current?.pause()
    const audio = new Audio(previewUrl(voice, language))
    audio.onended = () => setPreviewing(null)
    audio.onerror = () => setPreviewing(null)
    player.current = audio
    setPreviewing(voice.name)
    void audio.play().catch(() => setPreviewing(null))
  }, [])
  return { previewing, play }
}
