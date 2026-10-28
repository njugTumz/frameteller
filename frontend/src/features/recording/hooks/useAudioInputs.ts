import { useEffect, useState } from 'react'
import { listAudioInputs, type AudioInput } from '../../../shared/audio/inputs'

/** The microphones to choose from, read when `active` (after the browser allowed the microphone). */
export function useAudioInputs(active: boolean): AudioInput[] {
  const [inputs, setInputs] = useState<AudioInput[]>([])
  useEffect(() => {
    if (!active) return
    let current = true
    const read = () => void listAudioInputs().then((list) => current && setInputs(list))
    read()
    navigator.mediaDevices?.addEventListener?.('devicechange', read)
    return () => {
      current = false
      navigator.mediaDevices?.removeEventListener?.('devicechange', read)
    }
  }, [active])
  return inputs
}
